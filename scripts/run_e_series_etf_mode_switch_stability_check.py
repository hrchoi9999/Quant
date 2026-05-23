from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_e_series_etf_mode_switch_policy_walk_forward import _market_mode
from scripts.run_e_series_etf_mode_switch_turnover_buffer import (
    _period_returns,
    _records,
    _safe_float,
    _simulate_policy,
    _load_returns,
)


REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
STRATEGY_MODEL_CODE = "E-ETF-V01"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"
BASE_POLICY = "hybrid_b50_ai50_top3_role"
TAIL_POLICY = "wf_tail_asset_policy"
TARGET_POLICY = "mode_switch_stress_tail_asset"
BUFFER_POLICY = "mode_switch_buffer_70"
NO_TRADE_BUFFER = 0.70


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return _safe_float(value)
    if pd.isna(value):
        return None
    return value


def _to_records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    use = df.head(limit) if limit is not None else df
    return [{key: _json_value(value) for key, value in row.items()} for row in use.to_dict("records")]


def _stress_flag(row: pd.Series, cfg: dict[str, float]) -> bool:
    crash = pd.to_numeric(pd.Series([row.get("qm_risk_crash_warning_flag")]), errors="coerce").iloc[0]
    stress = pd.to_numeric(pd.Series([row.get("qm_risk_market_stress_score")]), errors="coerce").iloc[0]
    drawdown = pd.to_numeric(pd.Series([row.get("qm_risk_drawdown_pressure_score")]), errors="coerce").iloc[0]
    risk_off = pd.to_numeric(pd.Series([row.get("qm_market_risk_off_score")]), errors="coerce").iloc[0]
    market_mdd = pd.to_numeric(pd.Series([row.get("qm_market_market_mdd_3m")]), errors="coerce").iloc[0]
    if pd.notna(crash) and float(crash) >= cfg["crash"]:
        return True
    if pd.notna(stress) and float(stress) >= cfg["stress"]:
        return True
    if pd.notna(stress) and pd.notna(drawdown) and float(stress) >= cfg["stress_combo"] and float(drawdown) >= cfg["drawdown"]:
        return True
    if pd.notna(risk_off) and pd.notna(market_mdd) and float(risk_off) >= cfg["risk_off"] and float(market_mdd) <= cfg["market_mdd"]:
        return True
    return False


def _load_selected(asof: str) -> pd.DataFrame:
    path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_selected_{_token(asof)}.csv"
    if not path.exists():
        raise SystemExit(f"missing selected CSV: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["policy_weight"] = pd.to_numeric(df["policy_weight"], errors="coerce").fillna(0)
    return df


def _date_context(selected: pd.DataFrame) -> pd.DataFrame:
    keep_cols = [
        "signal_date",
        "e_market_mode",
        "qm_risk_crash_warning_flag",
        "qm_risk_market_stress_score",
        "qm_risk_drawdown_pressure_score",
        "qm_market_risk_off_score",
        "qm_market_market_mdd_3m",
    ]
    frame = selected[selected["policy"].eq(BASE_POLICY)].copy()
    for col in keep_cols:
        if col not in frame.columns:
            frame[col] = np.nan
    rows = []
    for signal_date, group in frame.groupby("signal_date", dropna=False):
        row = {"signal_date": signal_date, "e_market_mode": _market_mode(group)}
        for col in keep_cols[2:]:
            vals = pd.to_numeric(group[col], errors="coerce").dropna()
            row[col] = float(vals.median()) if not vals.empty else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values("signal_date").reset_index(drop=True)


def _target_for_variant(selected: pd.DataFrame, states: pd.DataFrame, variant: str) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, state in states.iterrows():
        source_policy = TAIL_POLICY if bool(state["is_stress"]) else BASE_POLICY
        part = selected[
            selected["signal_date"].eq(state["signal_date"]) & selected["policy"].eq(source_policy)
        ].copy()
        part["policy"] = variant
        part["policy_label"] = f"{BASE_POLICY} normal, {TAIL_POLICY} stress"
        part["switch_eval_stress"] = bool(state["is_stress"])
        part["switch_eval_mode"] = state.get("e_market_mode")
        parts.append(part)
    return pd.concat([part for part in parts if not part.empty], ignore_index=True)


def _state_metrics(states: pd.DataFrame) -> dict[str, Any]:
    flags = states["is_stress"].astype(bool).tolist()
    transitions = sum(1 for idx in range(1, len(flags)) if flags[idx] != flags[idx - 1])
    singletons = 0
    for idx, flag in enumerate(flags):
        prev_same = idx > 0 and flags[idx - 1] == flag
        next_same = idx + 1 < len(flags) and flags[idx + 1] == flag
        if not prev_same and not next_same:
            singletons += 1
    return {
        "evaluated_dates": int(len(flags)),
        "stress_dates": int(sum(flags)),
        "normal_dates": int(len(flags) - sum(flags)),
        "state_transitions": int(transitions),
        "single_month_flips": int(singletons),
        "transition_rate": _safe_float(transitions / max(len(flags) - 1, 1)),
    }


def _period_summary(periods: pd.DataFrame, policy_name: str, variant: str) -> dict[str, Any]:
    frame = periods[periods["policy"].eq(policy_name)].copy()
    net = pd.to_numeric(frame["net_return"], errors="coerce").dropna()
    risk = pd.to_numeric(frame["net_risk_adj"], errors="coerce").dropna()
    turnover = pd.to_numeric(frame["actual_turnover"], errors="coerce").dropna()
    return {
        "variant": variant,
        "policy": policy_name,
        "priced_periods": int(len(net)),
        "avg_net_1m_ret": _safe_float(net.mean()),
        "avg_net_1m_risk_adj": _safe_float(risk.mean()),
        "worst_net_1m_ret": _safe_float(net.min()),
        "compounded_net_return": _safe_float((1.0 + net).prod() - 1.0) if not net.empty else None,
        "avg_turnover": _safe_float(turnover.mean()),
        "max_turnover": _safe_float(turnover.max()),
        "skipped_periods": int(frame["rebalance_skipped"].sum()) if "rebalance_skipped" in frame.columns else 0,
    }


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    def pct(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""
        return f"{float(value):.2%}"

    lines = [
        "# E-Series ETF Mode Switch Stability Check",
        "",
        f"- as-of: `{payload['as_of_date']}`",
        f"- target: `{TARGET_POLICY}`",
        f"- buffer policy: `{BUFFER_POLICY}`",
        "",
        "| variant | stress dates | transitions | single flips | avg net 1M | risk adj | worst | compounded | avg turnover | skipped |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['variant']}` | {int(row['stress_dates'])} | {int(row['state_transitions'])} | {int(row['single_month_flips'])} | "
            f"{pct(row['avg_net_1m_ret'])} | {pct(row['avg_net_1m_risk_adj'])} | {pct(row['worst_net_1m_ret'])} | "
            f"{pct(row['compounded_net_return'])} | {pct(row['avg_turnover'])} | {int(row['skipped_periods'])} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- loose/base/tight stress threshold에서 성과 순위와 손실 방어가 크게 바뀌지 않으면 전환 규칙은 안정적이다.",
            "- single flips가 높으면 국면 판단이 흔들린다는 의미다.",
            "- buffer는 작은 포트폴리오 변화를 무시하므로, 전환 규칙의 노이즈를 줄이는 역할을 한다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_check(asof: str, cost_bps: float) -> dict[str, Any]:
    selected = _load_selected(asof)
    returns = _load_returns(asof)
    context = _date_context(selected)
    configs = {
        "loose": {"crash": 0.5, "stress": 2.3, "stress_combo": 1.8, "drawdown": 2.3, "risk_off": 2.3, "market_mdd": -0.10},
        "base": {"crash": 0.5, "stress": 2.5, "stress_combo": 2.0, "drawdown": 2.5, "risk_off": 2.5, "market_mdd": -0.12},
        "tight": {"crash": 0.5, "stress": 2.7, "stress_combo": 2.2, "drawdown": 2.7, "risk_off": 2.7, "market_mdd": -0.14},
    }
    selected_parts = []
    state_rows = []
    for variant, cfg in configs.items():
        states = context.copy()
        states["variant"] = variant
        states["is_stress"] = states.apply(lambda row: _stress_flag(row, cfg), axis=1)
        state_rows.append(states)
        target = _target_for_variant(selected, states, f"{TARGET_POLICY}_{variant}")
        selected_parts.append(_simulate_policy(target, f"{BUFFER_POLICY}_{variant}", None, NO_TRADE_BUFFER))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        simulated = pd.concat([part for part in selected_parts if not part.empty], ignore_index=True)
        states_all = pd.concat(state_rows, ignore_index=True)

    _, periods = _period_returns(simulated, returns, cost_bps)
    current_holdings = simulated[simulated["signal_date"].eq(asof)].copy()
    if not current_holdings.empty:
        meta_cols = [
            "ticker",
            "name",
            "e_series_role",
            "e_asset_bucket",
            "e_market_mode",
        ]
        meta_frame = selected[[col for col in meta_cols if col in selected.columns]].copy()
        for col in [col for col in meta_cols if col != "ticker" and col in meta_frame.columns]:
            meta_frame[col] = meta_frame[col].replace("", np.nan)
        meta = (
            meta_frame.sort_values("ticker")
            .groupby("ticker", as_index=False)
            .agg(lambda series: series.dropna().iloc[0] if not series.dropna().empty else np.nan)
        )
        current_holdings = current_holdings.merge(meta, on="ticker", how="left")
        current_holdings["candidate_type"] = np.where(
            current_holdings["policy"].astype(str).str.endswith("_tight"),
            "shadow_candidate",
            np.where(current_holdings["policy"].astype(str).str.endswith("_base"), "current_candidate", "sensitivity_candidate"),
        )
    rows = []
    for variant in configs:
        metrics = _state_metrics(states_all[states_all["variant"].eq(variant)])
        perf = _period_summary(periods, f"{BUFFER_POLICY}_{variant}", variant)
        rows.append({**metrics, **perf})
    summary = pd.DataFrame(rows)
    base = summary[summary["variant"].eq("base")].iloc[0]
    for col in ["avg_net_1m_ret", "avg_net_1m_risk_adj", "worst_net_1m_ret", "compounded_net_return", "avg_turnover"]:
        summary[f"{col}_delta_vs_base"] = pd.to_numeric(summary[col], errors="coerce") - pd.to_numeric(base[col], errors="coerce")
    summary = summary.sort_values("avg_net_1m_risk_adj", ascending=False)

    token = _token(asof)
    selected_path = REPORT_DIR / f"e_series_etf_mode_switch_stability_check_selected_{token}.csv"
    current_holdings_path = REPORT_DIR / f"e_series_etf_mode_switch_stability_check_current_holdings_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_mode_switch_stability_check_summary_{token}.csv"
    states_path = REPORT_DIR / f"e_series_etf_mode_switch_stability_check_states_{token}.csv"
    periods_path = REPORT_DIR / f"e_series_etf_mode_switch_stability_check_periods_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_mode_switch_stability_check_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_mode_switch_stability_check_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_stability_check_current.json"
    simulated.to_csv(selected_path, index=False, encoding="utf-8-sig")
    current_holdings.to_csv(current_holdings_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    states_all.to_csv(states_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    payload = {
        "status": "ok",
        "source_name": "e_series_etf_mode_switch_stability_check",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "target_policy": TARGET_POLICY,
        "buffer_policy": BUFFER_POLICY,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cost_bps": float(cost_bps),
        "summary": _to_records(summary),
        "current_holdings": _to_records(
            current_holdings.sort_values(["policy", "policy_weight", "ticker"], ascending=[True, False, True])
        ),
        "current_candidates": {
            "current": "mode_switch_buffer_70_base",
            "shadow": "mode_switch_buffer_70_tight",
            "sensitivity": "mode_switch_buffer_70_loose",
        },
        "outputs": {
            "selected_csv": str(selected_path),
            "current_holdings_csv": str(current_holdings_path),
            "summary_csv": str(summary_path),
            "states_csv": str(states_path),
            "periods_csv": str(periods_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, summary)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Check stability of E-series ETF mode-switch rule.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()
    payload = run_check(str(args.asof), float(args.cost_bps))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "as_of_date": payload["as_of_date"],
                "summary": payload["summary"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
