from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_ai_overlay_combo_strategy_backtest as combo  # noqa: E402


OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

DEFAULT_POLICY = "combo_equal_renorm"
POLICY_MAP = {
    ("internal", "S2"): "valuation_tilt_renorm",
    ("internal", "S2_PIT_V01"): "rank_delta_tilt_renorm",
    ("internal", "S3"): "combo_equal_renorm",
    ("internal", "S3_CORE2"): "combo_equal_renorm",
    ("internal", "S3_ACCEL_V01"): "risk_tilt_renorm",
    ("internal", "I-STOCK-STRONG-RSI-V01"): "combo_equal_renorm",
    ("tseries", "T-STOCK-V01"): "combo_equal_renorm",
    ("user", "growth"): "combo_equal_renorm",
    ("user", "stable"): "rank_delta_tilt_renorm",
    ("user", "balanced"): "rank_delta_tilt_renorm",
}


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _map_policy(scope_key: str, model_id: str) -> str:
    return POLICY_MAP.get((str(scope_key), str(model_id)), DEFAULT_POLICY)


def _run_policy_map(scored: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdings: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    group_cols = ["strategy_family", "scope_key", "model_id", "snapshot_date", "next_snapshot_date"]
    for keys, frame in scored.groupby(group_cols, dropna=False):
        strategy_family, scope_key, model_id, snapshot_date, next_snapshot_date = keys
        frame = frame.sort_values(["rank_no", "ticker"]).copy()
        ret = pd.to_numeric(frame["period_return"], errors="coerce")
        policy = _map_policy(scope_key, model_id)
        base_weights = combo._policy_weights(frame, "baseline")
        policy_weights = combo._policy_weights(frame, policy)
        valid = frame.loc[ret.notna()]
        base_return = float((valid["period_return"] * base_weights.loc[valid.index]).sum()) if not valid.empty else np.nan
        policy_return = float((valid["period_return"] * policy_weights.loc[valid.index]).sum()) if not valid.empty else np.nan
        rows.extend(
            [
                {
                    "strategy_family": strategy_family,
                    "scope_key": scope_key,
                    "model_id": model_id,
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": "baseline",
                    "mapped_policy": policy,
                    "selected_count": int(len(frame)),
                    "priced_count": int(ret.notna().sum()),
                    "removed_weight": 0.0,
                    "period_return": round(base_return, 8) if not np.isnan(base_return) else np.nan,
                    "risk_caution_plus_count": int(frame["downside_risk_tag"].isin(["risk_caution", "risk_exit_watch"]).sum()),
                    "valuation_avoid_overheated_count": int(frame["valuation_state"].isin(["AVOID", "OVERHEATED"]).sum()),
                    "rank_drop_watch_plus_count": int(frame["rank_delta_decision"].isin(["rank_drop_candidate", "rank_drop_watch"]).sum()),
                },
                {
                    "strategy_family": strategy_family,
                    "scope_key": scope_key,
                    "model_id": model_id,
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": "policy_map",
                    "mapped_policy": policy,
                    "selected_count": int(len(frame)),
                    "priced_count": int(ret.notna().sum()),
                    "removed_weight": round(float(1.0 - policy_weights.sum()), 8) if policy.endswith("_cash") else 0.0,
                    "period_return": round(policy_return, 8) if not np.isnan(policy_return) else np.nan,
                    "risk_caution_plus_count": int(frame["downside_risk_tag"].isin(["risk_caution", "risk_exit_watch"]).sum()),
                    "valuation_avoid_overheated_count": int(frame["valuation_state"].isin(["AVOID", "OVERHEATED"]).sum()),
                    "rank_drop_watch_plus_count": int(frame["rank_delta_decision"].isin(["rank_drop_candidate", "rank_drop_watch"]).sum()),
                },
            ]
        )
        for label, weights in [("baseline", base_weights), ("policy_map", policy_weights)]:
            part = frame.copy()
            part["policy"] = label
            part["mapped_policy"] = policy
            part["policy_weight"] = weights
            holdings.append(
                part[
                    [
                        "strategy_family",
                        "scope_key",
                        "model_id",
                        "snapshot_date",
                        "next_snapshot_date",
                        "policy",
                        "mapped_policy",
                        "ticker",
                        "name",
                        "rank_no",
                        "score",
                        "weight",
                        "policy_weight",
                        "period_return",
                        "downside_risk_tag",
                        "valuation_state",
                        "rank_delta_decision",
                    ]
                ]
            )
    return (
        pd.concat(holdings, ignore_index=True) if holdings else pd.DataFrame(),
        pd.DataFrame(rows),
    )


def _best_vs_baseline(summary: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    base = summary[summary["policy"].eq("baseline")][
        [*group_cols, "avg_period_return", "win_rate", "nav_mdd", "compounded_return"]
    ].rename(
        columns={
            "avg_period_return": "baseline_avg_period_return",
            "win_rate": "baseline_win_rate",
            "nav_mdd": "baseline_nav_mdd",
            "compounded_return": "baseline_compounded_return",
        }
    )
    mapped = summary[summary["policy"].eq("policy_map")].merge(base, on=group_cols, how="left")
    mapped["avg_return_delta"] = mapped["avg_period_return"] - mapped["baseline_avg_period_return"]
    mapped["win_rate_delta"] = mapped["win_rate"] - mapped["baseline_win_rate"]
    mapped["nav_mdd_delta"] = mapped["nav_mdd"] - mapped["baseline_nav_mdd"]
    return mapped


def _fmt_pct(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _write_report(asof: str, mapped_family: pd.DataFrame, mapped_model: pd.DataFrame, out_dir: Path) -> Path:
    path = out_dir / f"AI_OVERLAY_POLICY_MAP_BACKTEST_{_token(asof)}.md"
    lines = [
        "# AI Overlay Policy Map Backtest",
        "",
        f"- asof: {asof}",
        "- purpose: validate model-specific AI overlay policy map against each model baseline.",
        "- C-series note: no independent C-series weekly candidate rows were available in the current payload.",
        "",
        "## Policy Map",
        "",
        "| scope | model | mapped policy |",
        "| --- | --- | --- |",
    ]
    for (scope, model), policy in sorted(POLICY_MAP.items()):
        lines.append(f"| {scope} | {model} | {policy} |")
    lines.extend(
        [
            "",
            "## Family Summary",
            "",
            "| family | avg ret | baseline | delta | win | win delta | nav MDD | MDD delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in mapped_family.iterrows():
        lines.append(
            f"| {row['strategy_family']} | {_fmt_pct(row['avg_period_return'])} | "
            f"{_fmt_pct(row['baseline_avg_period_return'])} | {_fmt_pct(row['avg_return_delta'])} | "
            f"{_fmt_pct(row['win_rate'])} | {_fmt_pct(row['win_rate_delta'])} | "
            f"{_fmt_pct(row['nav_mdd'])} | {_fmt_pct(row['nav_mdd_delta'])} |"
        )
    lines.extend(
        [
            "",
            "## Model Summary",
            "",
            "| family | scope | model | mapped policy | avg ret | baseline | delta | win | nav MDD | MDD delta |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in mapped_model.iterrows():
        lines.append(
            f"| {row['strategy_family']} | {row['scope_key']} | {row['model_id']} | {row['mapped_policy']} | "
            f"{_fmt_pct(row['avg_period_return'])} | {_fmt_pct(row['baseline_avg_period_return'])} | "
            f"{_fmt_pct(row['avg_return_delta'])} | {_fmt_pct(row['win_rate'])} | "
            f"{_fmt_pct(row['nav_mdd'])} | {_fmt_pct(row['nav_mdd_delta'])} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest a model-specific AI overlay policy map.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    asof = str(args.asof)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    token = _token(asof)

    scored = combo._load_scored(asof)
    holdings, periods = _run_policy_map(scored)
    summary_model = combo._summarize(periods, ["strategy_family", "scope_key", "model_id"]).sort_values(
        ["strategy_family", "scope_key", "model_id", "policy"]
    )
    summary_family = combo._summarize(periods, ["strategy_family"]).sort_values(["strategy_family", "policy"])
    mapped_model = _best_vs_baseline(summary_model, ["strategy_family", "scope_key", "model_id"])
    mapped_family = _best_vs_baseline(summary_family, ["strategy_family"])
    if not mapped_model.empty:
        mapped_model["mapped_policy"] = [
            _map_policy(scope_key, model_id)
            for scope_key, model_id in zip(mapped_model["scope_key"], mapped_model["model_id"])
        ]

    periods_path = out_dir / f"ai_overlay_policy_map_periods_{token}.csv"
    holdings_path = out_dir / f"ai_overlay_policy_map_holdings_{token}.csv"
    summary_model_path = out_dir / f"ai_overlay_policy_map_summary_by_model_{token}.csv"
    summary_family_path = out_dir / f"ai_overlay_policy_map_summary_by_family_{token}.csv"
    mapped_model_path = out_dir / f"ai_overlay_policy_map_vs_baseline_by_model_{token}.csv"
    mapped_family_path = out_dir / f"ai_overlay_policy_map_vs_baseline_by_family_{token}.csv"
    json_path = out_dir / f"ai_overlay_policy_map_backtest_{token}.json"
    md_path = _write_report(asof, mapped_family, mapped_model, out_dir)

    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    holdings.to_csv(holdings_path, index=False, encoding="utf-8-sig")
    summary_model.to_csv(summary_model_path, index=False, encoding="utf-8-sig")
    summary_family.to_csv(summary_family_path, index=False, encoding="utf-8-sig")
    mapped_model.to_csv(mapped_model_path, index=False, encoding="utf-8-sig")
    mapped_family.to_csv(mapped_family_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asof": asof,
        "default_policy": DEFAULT_POLICY,
        "policy_map": {f"{scope}/{model}": policy for (scope, model), policy in sorted(POLICY_MAP.items())},
        "period_rows": int(len(periods)),
        "holdings_rows": int(len(holdings)),
        "outputs": {
            "periods_csv": str(periods_path),
            "holdings_csv": str(holdings_path),
            "summary_by_model_csv": str(summary_model_path),
            "summary_by_family_csv": str(summary_family_path),
            "vs_baseline_by_model_csv": str(mapped_model_path),
            "vs_baseline_by_family_csv": str(mapped_family_path),
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
