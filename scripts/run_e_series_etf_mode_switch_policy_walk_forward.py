from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_e_series_etf_selection_policy_ablation import (
    _ensure_scores,
    _load_inputs,
    _portfolio_summary,
    _records,
    _safe_float,
    _select_adaptive_policy,
    _select_fixed_policy,
)
from scripts.run_e_series_etf_selection_policy_walk_forward import _period_returns
from scripts.run_e_series_etf_tail_risk_policy_walk_forward import _tail_maps_from_history


REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
STRATEGY_MODEL_CODE = "E-ETF-V01"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"
STRESS_SCORE_THRESHOLD = 2.5
DRAWDOWN_PRESSURE_THRESHOLD = 2.5
RISK_OFF_SCORE_THRESHOLD = 2.5
MARKET_MDD_STRESS_THRESHOLD = -0.12


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _market_mode(eval_frame: pd.DataFrame) -> str:
    if "e_market_mode" not in eval_frame.columns or eval_frame.empty:
        return "neutral"
    mode = eval_frame["e_market_mode"].dropna().astype(str)
    if mode.empty:
        return "neutral"
    return str(mode.mode().iloc[0])


def _num_series(eval_frame: pd.DataFrame, col: str) -> pd.Series:
    values = eval_frame[col] if col in eval_frame.columns else pd.Series(np.nan, index=eval_frame.index)
    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]
    return pd.to_numeric(values, errors="coerce")


def _is_market_stress(eval_frame: pd.DataFrame) -> bool:
    stress = _num_series(eval_frame, "qm_risk_market_stress_score")
    drawdown = _num_series(eval_frame, "qm_risk_drawdown_pressure_score")
    crash = _num_series(eval_frame, "qm_risk_crash_warning_flag")
    risk_off = _num_series(eval_frame, "qm_market_risk_off_score")
    market_mdd = _num_series(eval_frame, "qm_market_market_mdd_3m")
    if crash.notna().any() and float(crash.median()) >= 0.5:
        return True
    if stress.notna().any() and float(stress.median()) >= STRESS_SCORE_THRESHOLD:
        return True
    if (
        stress.notna().any()
        and drawdown.notna().any()
        and float(stress.median()) >= 2.0
        and float(drawdown.median()) >= DRAWDOWN_PRESSURE_THRESHOLD
    ):
        return True
    if (
        risk_off.notna().any()
        and market_mdd.notna().any()
        and float(risk_off.median()) >= RISK_OFF_SCORE_THRESHOLD
        and float(market_mdd.median()) <= MARKET_MDD_STRESS_THRESHOLD
    ):
        return True
    return False


def _retag_policy(frame: pd.DataFrame, policy: str, label: str) -> pd.DataFrame:
    out = frame.copy()
    out["policy"] = policy
    out["policy_label"] = label
    return out


def _select_eval_date(
    eval_frame: pd.DataFrame,
    role_map: dict[str, str],
    asset_map: dict[str, str],
) -> pd.DataFrame:
    mode = _market_mode(eval_frame)
    stress = _is_market_stress(eval_frame)

    baseline = _select_fixed_policy(eval_frame, "baseline_top3_role")
    growth = _select_fixed_policy(eval_frame, "hybrid_b50_ai50_top3_role")
    quality = _select_fixed_policy(eval_frame, "ai_quality_guard_top3_role")
    tail_asset = _select_adaptive_policy(eval_frame, "wf_tail_asset_policy", role_map={}, asset_map=asset_map)
    tail_role_asset = _select_adaptive_policy(
        eval_frame,
        "wf_tail_role_asset_policy",
        role_map=role_map,
        asset_map=asset_map,
    )

    parts = [baseline, growth, quality, tail_asset, tail_role_asset]

    if stress:
        parts.append(_retag_policy(tail_asset, "mode_switch_stress_tail_asset", "Hybrid in normal, tail asset in stress"))
        parts.append(_retag_policy(quality, "mode_switch_stress_quality_guard", "Hybrid in normal, quality guard in stress"))
    else:
        parts.append(_retag_policy(growth, "mode_switch_stress_tail_asset", "Hybrid in normal, tail asset in stress"))
        parts.append(_retag_policy(growth, "mode_switch_stress_quality_guard", "Hybrid in normal, quality guard in stress"))

    if mode == "risk_off":
        parts.append(_retag_policy(tail_asset, "mode_switch_riskoff_tail_asset", "Hybrid unless risk-off, tail asset in risk-off"))
        parts.append(_retag_policy(quality, "mode_switch_riskoff_quality_guard", "Hybrid unless risk-off, quality guard in risk-off"))
        parts.append(_retag_policy(tail_role_asset, "mode_switch_riskoff_tail_role_asset", "Hybrid unless risk-off, tail role+asset in risk-off"))
    else:
        parts.append(_retag_policy(growth, "mode_switch_riskoff_tail_asset", "Hybrid unless risk-off, tail asset in risk-off"))
        parts.append(_retag_policy(growth, "mode_switch_riskoff_quality_guard", "Hybrid unless risk-off, quality guard in risk-off"))
        parts.append(_retag_policy(growth, "mode_switch_riskoff_tail_role_asset", "Hybrid unless risk-off, tail role+asset in risk-off"))

    out = pd.concat([part for part in parts if not part.empty], ignore_index=True)
    out["switch_eval_mode"] = mode
    out["switch_eval_stress"] = bool(stress)
    return out


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    lines = [
        "# E-Series ETF Mode Switch Policy Walk-Forward",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- sleeve model: `{payload['sleeve_model_code']}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- valid start: `{payload['valid_start']}`",
        f"- lookback days: `{payload['lookback_days']}`",
        f"- label lag days: `{payload['label_lag_days']}`",
        f"- evaluated dates: `{payload['evaluated_dates']}`",
        f"- stress dates: `{payload['stress_dates']}`",
        f"- risk-off dates: `{payload['risk_off_dates']}`",
        "",
        "## Portfolio Summary",
        "",
        "| policy | avg 1M ret | return delta | win | risk adj | risk adj delta | MDD proxy | worst 1M | worst delta | compounded |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['policy']}` | {_fmt_pct(row.get('avg_1m_ret'))} | {_fmt_pct(row.get('avg_1m_ret_delta'))} | "
            f"{_fmt_pct(row.get('win_rate'))} | {_fmt_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_fmt_pct(row.get('avg_1m_risk_adj_delta'))} | {_fmt_pct(row.get('avg_1m_mdd_proxy'))} | "
            f"{_fmt_pct(row.get('worst_1m_ret'))} | {_fmt_pct(row.get('worst_1m_ret_delta'))} | "
            f"{_fmt_pct(row.get('compounded_validation_return'))} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- 이 실험은 normal 구간에서는 성장형 hybrid 50/50을 유지하고, risk-off 또는 stress 구간에서 tail-risk policy로 전환하는 규칙을 검증합니다.",
            "- 전환 규칙이 대표 후보가 되려면 hybrid 50/50 대비 tail-risk를 줄이면서 누적 수익률 훼손이 제한적이어야 합니다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_mode_switch(
    asof: str,
    valid_start: str,
    lookback_days: int,
    label_lag_days: int,
    min_segment_rows: int,
) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    data = _ensure_scores(_load_inputs(asof))
    data["signal_dt"] = pd.to_datetime(data["signal_date"], errors="coerce")
    data = data[data["signal_dt"].notna()].copy()
    eval_dates = sorted(
        dt
        for dt in data.loc[
            (data["signal_dt"] >= pd.Timestamp(valid_start)) & (data["signal_dt"] <= pd.Timestamp(asof)),
            "signal_dt",
        ].dropna().unique()
    )

    selected_parts: list[pd.DataFrame] = []
    map_rows: list[dict[str, Any]] = []
    for eval_dt in eval_dates:
        history_end = pd.Timestamp(eval_dt) - pd.Timedelta(days=label_lag_days)
        history_start = pd.Timestamp(eval_dt) - pd.Timedelta(days=lookback_days)
        history = data[(data["signal_dt"] >= history_start) & (data["signal_dt"] <= history_end)].copy()
        eval_frame = data[data["signal_dt"].eq(eval_dt)].copy()
        if history.empty or eval_frame.empty:
            continue
        role_map, asset_map, _ = _tail_maps_from_history(history, min_segment_rows)
        selected = _select_eval_date(eval_frame, role_map, asset_map)
        selected["policy_train_start"] = history_start.date().isoformat()
        selected["policy_train_end"] = history_end.date().isoformat()
        selected_parts.append(selected)
        map_rows.append(
            {
                "signal_date": pd.Timestamp(eval_dt).date().isoformat(),
                "history_start": history_start.date().isoformat(),
                "history_end": history_end.date().isoformat(),
                "history_rows": int(len(history)),
                "e_market_mode": _market_mode(eval_frame),
                "is_market_stress": bool(_is_market_stress(eval_frame)),
                "role_policy_map": json.dumps(role_map, ensure_ascii=False, sort_keys=True),
                "asset_policy_map": json.dumps(asset_map, ensure_ascii=False, sort_keys=True),
            }
        )

    if not selected_parts:
        raise SystemExit("no mode-switch evaluation rows")

    selected_all = pd.concat(selected_parts, ignore_index=True)
    periods = _period_returns(selected_all)
    summary = _portfolio_summary(periods)
    maps = pd.DataFrame(map_rows)

    selected_path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_selected_{token}.csv"
    periods_path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_periods_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_summary_{token}.csv"
    maps_path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_maps_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_mode_switch_policy_walk_forward_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_policy_walk_forward_current.json"

    selected_all.to_csv(selected_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    maps.to_csv(maps_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_mode_switch_policy_walk_forward",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "valid_start": valid_start,
        "lookback_days": lookback_days,
        "label_lag_days": label_lag_days,
        "min_segment_rows": min_segment_rows,
        "stress_rule": {
            "stress_score_threshold": STRESS_SCORE_THRESHOLD,
            "drawdown_pressure_threshold": DRAWDOWN_PRESSURE_THRESHOLD,
            "risk_off_score_threshold": RISK_OFF_SCORE_THRESHOLD,
            "market_mdd_stress_threshold": MARKET_MDD_STRESS_THRESHOLD,
            "crash_warning_flag_threshold": 0.5,
            "note": "risk_off mode is handled separately; stress is reserved for acute risk conditions.",
        },
        "evaluated_dates": int(maps.shape[0]),
        "stress_dates": int(maps["is_market_stress"].sum()) if "is_market_stress" in maps.columns else 0,
        "risk_off_dates": int(maps["e_market_mode"].astype(str).eq("risk_off").sum()) if "e_market_mode" in maps.columns else 0,
        "best_portfolio_policy": _records(summary.head(1)),
        "portfolio_summary": _records(summary),
        "recent_policy_maps": _records(maps.tail(5)),
        "outputs": {
            "selected_csv": str(selected_path),
            "periods_csv": str(periods_path),
            "summary_csv": str(summary_path),
            "maps_csv": str(maps_path),
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
    parser = argparse.ArgumentParser(description="Walk-forward validate E-series ETF market-mode switching policy.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--label-lag-days", type=int, default=31)
    parser.add_argument("--min-segment-rows", type=int, default=24)
    args = parser.parse_args()
    payload = run_mode_switch(
        str(args.asof),
        str(args.valid_start),
        int(args.lookback_days),
        int(args.label_lag_days),
        int(args.min_segment_rows),
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "strategy_model_code": payload["strategy_model_code"],
                "as_of_date": payload["as_of_date"],
                "evaluated_dates": payload["evaluated_dates"],
                "stress_dates": payload["stress_dates"],
                "risk_off_dates": payload["risk_off_dates"],
                "best_portfolio_policy": payload["best_portfolio_policy"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
