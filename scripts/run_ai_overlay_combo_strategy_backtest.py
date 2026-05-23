from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / r"reports\ai_overlay_backtest"

POLICIES = [
    "baseline",
    "risk_tilt_renorm",
    "valuation_tilt_renorm",
    "rank_delta_tilt_renorm",
    "combo_equal_renorm",
    "combo_equal_cash",
]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _path(prefix: str, asof: str) -> Path:
    return OUT_DIR / f"{prefix}_{_token(asof)}.csv"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"missing input file: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in ["snapshot_date", "week_end", "next_snapshot_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def _strategy_family(scope_key: str, model_id: str) -> str:
    model = str(model_id).upper()
    scope = str(scope_key).lower()
    if model.startswith("S"):
        return "S"
    if model.startswith("T"):
        return "T"
    if model.startswith("I"):
        return "I"
    if model.startswith("C"):
        return "C"
    if scope == "user":
        return "USER"
    return "OTHER"


def _load_scored(asof: str) -> pd.DataFrame:
    base = _read_csv(_path("candidate_rank_delta_ai_weekly_overlay_scored", asof))
    downside = _read_csv(_path("downside_risk_ai_weekly_overlay_scored", asof))
    valuation = _read_csv(_path("valuation_ai_weekly_overlay_scored", asof))
    keys = ["scope_key", "model_id", "ticker", "snapshot_date", "week_end"]
    base = base.drop_duplicates(keys, keep="last").copy()
    downside = downside.drop_duplicates(keys, keep="last").copy()
    valuation = valuation.drop_duplicates(keys, keep="last").copy()

    risk_cols = keys + ["downside_risk_prob", "downside_risk_tag"]
    val_cols = keys + [
        "valuation_asof_date",
        "valuation_ai_score",
        "valuation_state",
        "valuation_safety_score",
        "growth_quality_score",
        "downside_risk_score",
    ]
    out = base.merge(downside[[c for c in risk_cols if c in downside.columns]], on=keys, how="left")
    out = out.merge(valuation[[c for c in val_cols if c in valuation.columns]], on=keys, how="left")
    out["strategy_family"] = [_strategy_family(a, b) for a, b in zip(out["scope_key"], out["model_id"])]
    out["downside_risk_tag"] = out["downside_risk_tag"].fillna("risk_unknown")
    out["valuation_state"] = out["valuation_state"].fillna("OUT_OF_SCOPE_OR_MISSING")
    out["rank_delta_decision"] = out["rank_delta_decision"].fillna("rank_observe")
    return out


def _initial_weights(frame: pd.DataFrame) -> pd.Series:
    w = pd.to_numeric(frame.get("weight"), errors="coerce")
    if w.notna().sum() and float(w.fillna(0).sum()) > 0:
        w = w.fillna(0).clip(lower=0)
        return w / w.sum()
    return pd.Series(1.0 / len(frame), index=frame.index)


def _risk_multiplier(frame: pd.DataFrame) -> pd.Series:
    return frame["downside_risk_tag"].map(
        {
            "risk_clear": 1.10,
            "risk_watch": 0.85,
            "risk_caution": 0.55,
            "risk_exit_watch": 0.20,
        }
    ).fillna(0.75)


def _valuation_multiplier(frame: pd.DataFrame) -> pd.Series:
    return frame["valuation_state"].map(
        {
            "UNDERVALUED": 1.15,
            "FAIR": 1.00,
            "OVERHEATED": 0.70,
            "AVOID": 0.30,
            "OUT_OF_SCOPE_OR_MISSING": 0.75,
        }
    ).fillna(0.75)


def _rank_delta_multiplier(frame: pd.DataFrame) -> pd.Series:
    return frame["rank_delta_decision"].map(
        {
            "rank_upgrade_candidate": 1.15,
            "rank_upgrade_watch": 1.05,
            "rank_hold": 1.00,
            "rank_downgrade_watch": 0.80,
            "rank_downgrade_candidate": 0.60,
            "rank_drop_watch": 0.50,
            "rank_drop_candidate": 0.25,
            "rank_observe": 0.80,
        }
    ).fillna(0.80)


def _policy_weights(frame: pd.DataFrame, policy: str) -> pd.Series:
    base = _initial_weights(frame)
    if policy == "baseline":
        return base
    if policy == "risk_tilt_renorm":
        raw = base * _risk_multiplier(frame)
    elif policy == "valuation_tilt_renorm":
        raw = base * _valuation_multiplier(frame)
    elif policy == "rank_delta_tilt_renorm":
        raw = base * _rank_delta_multiplier(frame)
    elif policy in {"combo_equal_renorm", "combo_equal_cash"}:
        raw = base * _risk_multiplier(frame) * _valuation_multiplier(frame) * _rank_delta_multiplier(frame)
        if policy == "combo_equal_cash":
            return raw
    else:
        raise ValueError(policy)
    return raw / raw.sum() if float(raw.sum()) > 0 else base


def _run_backtest(scored: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdings: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    group_cols = ["strategy_family", "scope_key", "model_id", "snapshot_date", "next_snapshot_date"]
    for keys, frame in scored.groupby(group_cols, dropna=False):
        strategy_family, scope_key, model_id, snapshot_date, next_snapshot_date = keys
        frame = frame.sort_values(["rank_no", "ticker"]).copy()
        ret = pd.to_numeric(frame["period_return"], errors="coerce")
        for policy in POLICIES:
            weights = _policy_weights(frame, policy)
            valid = frame.loc[ret.notna()]
            valid_weights = weights.loc[valid.index]
            period_return = float((valid["period_return"] * valid_weights).sum()) if not valid.empty else np.nan
            rows.append(
                {
                    "strategy_family": strategy_family,
                    "scope_key": scope_key,
                    "model_id": model_id,
                    "snapshot_date": snapshot_date,
                    "next_snapshot_date": next_snapshot_date,
                    "policy": policy,
                    "selected_count": int(len(frame)),
                    "priced_count": int(ret.notna().sum()),
                    "removed_weight": round(float(1.0 - weights.sum()), 8) if policy.endswith("_cash") else 0.0,
                    "period_return": round(period_return, 8) if not np.isnan(period_return) else np.nan,
                    "risk_caution_plus_count": int(frame["downside_risk_tag"].isin(["risk_caution", "risk_exit_watch"]).sum()),
                    "valuation_avoid_overheated_count": int(frame["valuation_state"].isin(["AVOID", "OVERHEATED"]).sum()),
                    "rank_drop_watch_plus_count": int(frame["rank_delta_decision"].isin(["rank_drop_candidate", "rank_drop_watch"]).sum()),
                }
            )
            part = frame.copy()
            part["policy"] = policy
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


def _nav_mdd(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    nav = (1.0 + returns.fillna(0)).cumprod()
    dd = nav / nav.cummax() - 1.0
    return round(float(dd.min()), 8)


def _summarize(periods: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, frame in periods.groupby([*group_cols, "policy"], dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        base = dict(zip([*group_cols, "policy"], keys))
        r = pd.to_numeric(frame["period_return"], errors="coerce").dropna()
        rows.append(
            {
                **base,
                "periods": int(len(frame)),
                "priced_periods": int(len(r)),
                "avg_period_return": round(float(r.mean()), 8) if not r.empty else np.nan,
                "median_period_return": round(float(r.median()), 8) if not r.empty else np.nan,
                "win_rate": round(float((r > 0).mean()), 6) if not r.empty else np.nan,
                "downside_period_rate": round(float((r <= -0.03).mean()), 6) if not r.empty else np.nan,
                "worst_period_return": round(float(r.min()), 8) if not r.empty else np.nan,
                "compounded_return": round(float((1.0 + r).prod() - 1.0), 8) if not r.empty else np.nan,
                "nav_mdd": _nav_mdd(r),
                "avg_removed_weight": round(float(frame["removed_weight"].mean()), 8),
                "avg_risk_caution_plus_count": round(float(frame["risk_caution_plus_count"].mean()), 4),
                "avg_valuation_avoid_overheated_count": round(float(frame["valuation_avoid_overheated_count"].mean()), 4),
                "avg_rank_drop_watch_plus_count": round(float(frame["rank_drop_watch_plus_count"].mean()), 4),
            }
        )
    return pd.DataFrame(rows)


def _best_vs_baseline(summary: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    baseline = summary[summary["policy"].eq("baseline")][
        [*group_cols, "avg_period_return", "win_rate", "nav_mdd", "compounded_return"]
    ].rename(
        columns={
            "avg_period_return": "baseline_avg_period_return",
            "win_rate": "baseline_win_rate",
            "nav_mdd": "baseline_nav_mdd",
            "compounded_return": "baseline_compounded_return",
        }
    )
    joined = summary[~summary["policy"].eq("baseline")].merge(baseline, on=group_cols, how="left")
    joined["avg_return_delta"] = joined["avg_period_return"] - joined["baseline_avg_period_return"]
    joined["nav_mdd_delta"] = joined["nav_mdd"] - joined["baseline_nav_mdd"]
    joined["win_rate_delta"] = joined["win_rate"] - joined["baseline_win_rate"]
    joined = joined.dropna(subset=["avg_return_delta"])
    joined = joined.sort_values([*group_cols, "avg_return_delta"], ascending=[*[True] * len(group_cols), False])
    return joined.groupby(group_cols, dropna=False).head(1).reset_index(drop=True)


def _fmt_pct(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _write_report(asof: str, best_model: pd.DataFrame, best_family: pd.DataFrame, out_dir: Path) -> Path:
    path = out_dir / f"AI_OVERLAY_COMBO_STRATEGY_BACKTEST_{_token(asof)}.md"
    lines = [
        "# AI Overlay Combo Strategy Backtest",
        "",
        f"- asof: {asof}",
        "- scope: stock-only strategy rankings; ETF excluded from S/T/I overlay test",
        "- C-series note: current weekly candidate payload has no independent C-series portfolio rows, so C-series is not evaluated here.",
        "",
        "## Best Policy by Family",
        "",
        "| family | policy | avg ret | delta | win | nav MDD | MDD delta |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in best_family.iterrows():
        lines.append(
            f"| {row['strategy_family']} | {row['policy']} | {_fmt_pct(row['avg_period_return'])} | "
            f"{_fmt_pct(row['avg_return_delta'])} | {_fmt_pct(row['win_rate'])} | {_fmt_pct(row['nav_mdd'])} | "
            f"{_fmt_pct(row['nav_mdd_delta'])} |"
        )
    lines.extend(
        [
            "",
            "## Best Policy by Model",
            "",
            "| family | scope | model | policy | avg ret | delta | win | nav MDD | MDD delta |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in best_model.iterrows():
        lines.append(
            f"| {row['strategy_family']} | {row['scope_key']} | {row['model_id']} | {row['policy']} | "
            f"{_fmt_pct(row['avg_period_return'])} | {_fmt_pct(row['avg_return_delta'])} | "
            f"{_fmt_pct(row['win_rate'])} | {_fmt_pct(row['nav_mdd'])} | {_fmt_pct(row['nav_mdd_delta'])} |"
        )
    lines.extend(
        [
            "",
            "## Policy Definitions",
            "",
            "- `risk_tilt_renorm`: 하락위험예측AI tag 기반 비중 조정 후 100% 재투자.",
            "- `valuation_tilt_renorm`: 주가수준평가AI state 기반 비중 조정 후 100% 재투자.",
            "- `rank_delta_tilt_renorm`: 후보순위조정AI decision 기반 비중 조정 후 100% 재투자.",
            "- `combo_equal_renorm`: 세 AI multiplier를 모두 곱한 뒤 100% 재투자.",
            "- `combo_equal_cash`: 세 AI multiplier를 모두 곱하고 남는 비중은 현금으로 보유.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest combined AI overlays by strategy model.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    asof = str(args.asof)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    token = _token(asof)

    scored = _load_scored(asof)
    holdings, periods = _run_backtest(scored)
    summary_model = _summarize(periods, ["strategy_family", "scope_key", "model_id"]).sort_values(
        ["strategy_family", "scope_key", "model_id", "policy"]
    )
    summary_family = _summarize(periods, ["strategy_family"]).sort_values(["strategy_family", "policy"])
    best_model = _best_vs_baseline(summary_model, ["strategy_family", "scope_key", "model_id"])
    best_family = _best_vs_baseline(summary_family, ["strategy_family"])

    scored_path = out_dir / f"ai_overlay_combo_strategy_scored_{token}.csv"
    holdings_path = out_dir / f"ai_overlay_combo_strategy_holdings_{token}.csv"
    periods_path = out_dir / f"ai_overlay_combo_strategy_periods_{token}.csv"
    summary_model_path = out_dir / f"ai_overlay_combo_strategy_summary_by_model_{token}.csv"
    summary_family_path = out_dir / f"ai_overlay_combo_strategy_summary_by_family_{token}.csv"
    best_model_path = out_dir / f"ai_overlay_combo_strategy_best_by_model_{token}.csv"
    best_family_path = out_dir / f"ai_overlay_combo_strategy_best_by_family_{token}.csv"
    json_path = out_dir / f"ai_overlay_combo_strategy_backtest_{token}.json"
    md_path = _write_report(asof, best_model, best_family, out_dir)

    scored.to_csv(scored_path, index=False, encoding="utf-8-sig")
    holdings.to_csv(holdings_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary_model.to_csv(summary_model_path, index=False, encoding="utf-8-sig")
    summary_family.to_csv(summary_family_path, index=False, encoding="utf-8-sig")
    best_model.to_csv(best_model_path, index=False, encoding="utf-8-sig")
    best_family.to_csv(best_family_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asof": asof,
        "policies": POLICIES,
        "scored_rows": int(len(scored)),
        "period_rows": int(len(periods)),
        "holdings_rows": int(len(holdings)),
        "families": sorted(scored["strategy_family"].dropna().unique().tolist()),
        "outputs": {
            "scored_csv": str(scored_path),
            "holdings_csv": str(holdings_path),
            "periods_csv": str(periods_path),
            "summary_by_model_csv": str(summary_model_path),
            "summary_by_family_csv": str(summary_family_path),
            "best_by_model_csv": str(best_model_path),
            "best_by_family_csv": str(best_family_path),
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
