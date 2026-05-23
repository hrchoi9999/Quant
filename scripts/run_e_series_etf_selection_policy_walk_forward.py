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
    _best_policy_map,
    _candidate_policies,
    _ensure_scores,
    _json_value,
    _load_inputs,
    _portfolio_summary,
    _records,
    _safe_float,
    _select_adaptive_policy,
    _select_fixed_policy,
    _segment_policy_stats,
)


REPORT_DIR = ROOT / r"reports\e_series_etf"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
STRATEGY_MODEL_CODE = "E-ETF-V01"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _period_returns(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (policy, signal_date), frame in selected.groupby(["policy", "signal_date"], dropna=False):
        valid = frame[frame["fwd_ret_1m"].notna()].copy()
        weights = pd.to_numeric(valid["policy_weight"], errors="coerce").fillna(0)
        rows.append(
            {
                "policy": policy,
                "signal_date": signal_date,
                "regime_mode": frame["e_market_mode"].mode().iloc[0] if not frame.empty else None,
                "selected_count": int(len(frame)),
                "priced_count": int(len(valid)),
                "effective_weight": _safe_float(weights.sum()),
                "period_return": _safe_float((valid["fwd_ret_1m"] * weights).sum()),
                "period_risk_adj": _safe_float((valid["risk_adj_1m"] * weights).sum()),
                "period_path_mdd_proxy": _safe_float((valid["path_mdd_1m"] * weights).sum()),
            }
        )
    return pd.DataFrame(rows)


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _policy_maps_from_history(history: pd.DataFrame, min_rows: int) -> tuple[dict[str, str], dict[str, str]]:
    role_stats = _segment_policy_stats(history, "e_series_role")
    asset_stats = _segment_policy_stats(history, "e_asset_bucket")
    segment_stats = pd.concat([role_stats, asset_stats], ignore_index=True)
    role_map = _best_policy_map(segment_stats, "e_series_role", min_rows=min_rows)
    asset_map = _best_policy_map(segment_stats, "e_asset_bucket", min_rows=min_rows)
    return role_map, asset_map


def _select_eval_date(
    eval_frame: pd.DataFrame,
    role_map: dict[str, str],
    asset_map: dict[str, str],
) -> pd.DataFrame:
    parts = [
        _select_fixed_policy(eval_frame, "baseline_top3_role"),
        _select_fixed_policy(eval_frame, "hybrid_b50_ai50_top3_role"),
        _select_fixed_policy(eval_frame, "hybrid_b70_ai30_top3_role"),
        _select_adaptive_policy(eval_frame, "wf_role_adaptive_policy", role_map),
        _select_adaptive_policy(eval_frame, "wf_asset_adaptive_policy", role_map={}, asset_map=asset_map),
        _select_adaptive_policy(eval_frame, "wf_role_asset_adaptive_policy", role_map=role_map, asset_map=asset_map),
    ]
    return pd.concat([part for part in parts if not part.empty], ignore_index=True)


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    lines = [
        "# E-Series ETF Selection Policy Walk-Forward",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- sleeve model: `{payload['sleeve_model_code']}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- valid start: `{payload['valid_start']}`",
        f"- lookback days: `{payload['lookback_days']}`",
        f"- label lag days: `{payload['label_lag_days']}`",
        f"- evaluated dates: `{payload['evaluated_dates']}`",
        "",
        "## Portfolio Summary",
        "",
        "| policy | avg 1M ret | return delta | win | risk adj | risk adj delta | MDD proxy | worst 1M | compounded |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['policy']}` | {_fmt_pct(row.get('avg_1m_ret'))} | {_fmt_pct(row.get('avg_1m_ret_delta'))} | "
            f"{_fmt_pct(row.get('win_rate'))} | {_fmt_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_fmt_pct(row.get('avg_1m_risk_adj_delta'))} | {_fmt_pct(row.get('avg_1m_mdd_proxy'))} | "
            f"{_fmt_pct(row.get('worst_1m_ret'))} | {_fmt_pct(row.get('compounded_validation_return'))} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- 이 결과는 각 평가일 이전의 과거 구간으로 role/asset별 best policy를 선택한 뒤 다음 평가일에 적용한 walk-forward 검증입니다.",
            "- 1M forward label 누수를 줄이기 위해 평가일 직전 31일은 policy 선택 데이터에서 제외합니다.",
            "- adaptive policy가 여기서도 baseline과 fixed hybrid를 이기면 운영 후보로 한 단계 더 가까워집니다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_walk_forward(
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
        role_map, asset_map = _policy_maps_from_history(history, min_segment_rows)
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
                "role_policy_map": json.dumps(role_map, ensure_ascii=False, sort_keys=True),
                "asset_policy_map": json.dumps(asset_map, ensure_ascii=False, sort_keys=True),
            }
        )

    if not selected_parts:
        raise SystemExit("no walk-forward evaluation rows")

    selected_all = pd.concat(selected_parts, ignore_index=True)
    periods = _period_returns(selected_all)
    summary = _portfolio_summary(periods)
    maps = pd.DataFrame(map_rows)

    selected_path = REPORT_DIR / f"e_series_etf_selection_policy_walk_forward_selected_{token}.csv"
    periods_path = REPORT_DIR / f"e_series_etf_selection_policy_walk_forward_periods_{token}.csv"
    summary_path = REPORT_DIR / f"e_series_etf_selection_policy_walk_forward_summary_{token}.csv"
    maps_path = REPORT_DIR / f"e_series_etf_selection_policy_walk_forward_maps_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_selection_policy_walk_forward_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_selection_policy_walk_forward_{token}.md"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_selection_policy_walk_forward_current.json"

    selected_all.to_csv(selected_path, index=False, encoding="utf-8-sig")
    periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    maps.to_csv(maps_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_selection_policy_walk_forward",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "valid_start": valid_start,
        "lookback_days": lookback_days,
        "label_lag_days": label_lag_days,
        "min_segment_rows": min_segment_rows,
        "candidate_policies": _candidate_policies(),
        "evaluated_dates": int(maps.shape[0]),
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
    parser = argparse.ArgumentParser(description="Walk-forward validate E-series ETF adaptive selection policy.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--label-lag-days", type=int, default=31)
    parser.add_argument("--min-segment-rows", type=int, default=12)
    args = parser.parse_args()
    payload = run_walk_forward(
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
                "best_portfolio_policy": payload["best_portfolio_policy"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
