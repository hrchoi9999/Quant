from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(r"D:\Quant")
SIGNAL_REPORT_DIR = ROOT / r"reports\ai_overlay_v01"
VALUATION_REPORT_DIR = ROOT / r"reports\valuation_ai"

SIGNAL_MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
SIGNAL_MODEL_NAME_KO = "퀀트후보검증AI"
VALUATION_MODEL_CODE = "AI-GROWTH-VALUATION-V01"
VALUATION_MODEL_NAME_KO = "주가수준평가AI"

HORIZONS = ["current", "1w", "2w", "1m", "2m", "3m", "6m", "1y"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a combined monitor for candidate validation AI and valuation AI."
    )
    parser.add_argument("--asof", required=True, help="Source snapshot date, YYYY-MM-DD")
    parser.add_argument("--performance-asof", help="Performance as-of date, defaults to --asof")
    parser.add_argument("--signal-report-dir", default=str(SIGNAL_REPORT_DIR))
    parser.add_argument("--valuation-report-dir", default=str(VALUATION_REPORT_DIR))
    return parser.parse_args()


def read_csv(path: Path, dtype: dict[str, Any] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=dtype, low_memory=False)


def latest_signal_rows(signal: pd.DataFrame) -> pd.DataFrame:
    if signal.empty:
        return signal
    frame = signal.copy()
    frame["scope_key"] = frame["scope_key"].astype(str)
    frame["model_id"] = frame["model_id"].astype(str)
    frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
    frame["_event_sort"] = pd.to_datetime(frame.get("event_date"), errors="coerce")
    frame["_scored_sort"] = pd.to_datetime(frame.get("scored_at"), errors="coerce")
    frame = frame.sort_values(["scope_key", "model_id", "ticker", "_event_sort", "_scored_sort"])
    frame = frame.drop_duplicates(["scope_key", "model_id", "ticker"], keep="last")
    return frame.drop(columns=[col for col in ["_event_sort", "_scored_sort"] if col in frame.columns])


def normalize_valuation(valuation: pd.DataFrame) -> pd.DataFrame:
    if valuation.empty:
        return valuation
    frame = valuation.copy()
    frame["scope"] = frame["scope"].astype(str)
    frame["model_code"] = frame["model_code"].astype(str)
    frame["security_code"] = frame["security_code"].astype(str).str.zfill(6)
    return frame


def attach_performance(base: pd.DataFrame, perf: pd.DataFrame) -> pd.DataFrame:
    if base.empty or perf.empty:
        return base
    perf_frame = perf.copy()
    perf_frame["scope"] = perf_frame["scope"].astype(str)
    perf_frame["model_code"] = perf_frame["model_code"].astype(str)
    perf_frame["security_code"] = perf_frame["security_code"].astype(str).str.zfill(6)
    perf_cols = [
        "scope",
        "model_code",
        "security_code",
        "track_start_date",
        "live_current_return",
        "live_current_mdd",
        "live_current_sharpe",
        "live_current_trading_days_seen",
    ]
    for horizon in HORIZONS:
        if horizon == "current":
            continue
        perf_cols.extend(
            [
                f"live_ret_{horizon}",
                f"live_mdd_{horizon}",
                f"live_sharpe_{horizon}",
                f"live_ret_{horizon}_available",
                f"live_ret_{horizon}_trading_days_seen",
            ]
        )
    perf_cols = [col for col in perf_cols if col in perf_frame.columns]
    return base.merge(
        perf_frame[perf_cols],
        on=["scope", "model_code", "security_code"],
        how="left",
    )


def build_combined(signal: pd.DataFrame, valuation: pd.DataFrame, performance: pd.DataFrame) -> pd.DataFrame:
    valuation = normalize_valuation(valuation)
    signal = latest_signal_rows(signal)
    if valuation.empty:
        return pd.DataFrame()
    out = valuation.merge(
        signal,
        left_on=["scope", "model_code", "security_code"],
        right_on=["scope_key", "model_id", "ticker"],
        how="left",
        suffixes=("", "_signal"),
    )
    out["signal_model_code"] = SIGNAL_MODEL_CODE
    out["signal_model_name_ko"] = SIGNAL_MODEL_NAME_KO
    out["valuation_model_code"] = VALUATION_MODEL_CODE
    out["valuation_model_name_ko"] = VALUATION_MODEL_NAME_KO
    for col, fallback in [
        ("ai_shadow_decision", "AI_MISSING"),
        ("ai_model_specific_tag", "MS_MISSING"),
        ("ai_shadow_tags", "MISSING"),
        ("champion_state", "OUT_OF_SCOPE_OR_MISSING"),
        ("challenger_state", "OUT_OF_SCOPE_OR_MISSING"),
        ("risk_tag", "out_of_scope"),
    ]:
        if col not in out.columns:
            out[col] = fallback
        out[col] = out[col].fillna(fallback).astype(str)
    return attach_performance(out, performance)


def metric_row(frame: pd.DataFrame, group_type: str, group_value: str, horizon: str) -> dict[str, Any]:
    if horizon == "current":
        ret_col = "live_current_return"
        mdd_col = "live_current_mdd"
        sharpe_col = "live_current_sharpe"
    else:
        ret_col = f"live_ret_{horizon}"
        mdd_col = f"live_mdd_{horizon}"
        sharpe_col = f"live_sharpe_{horizon}"
    vals = pd.to_numeric(frame.get(ret_col), errors="coerce").dropna()
    mdds = pd.to_numeric(frame.get(mdd_col), errors="coerce").dropna()
    sharpes = pd.to_numeric(frame.get(sharpe_col), errors="coerce").dropna()
    return {
        "group_type": group_type,
        "group_value": group_value,
        "horizon": horizon,
        "candidate_count": int(len(frame)),
        "sample_count": int(len(vals)),
        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
        "median_return": None if vals.empty else round(float(vals.median()), 6),
        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
        "mdd_sample_count": int(len(mdds)),
        "avg_mdd": None if mdds.empty else round(float(mdds.mean()), 6),
        "sharpe_sample_count": int(len(sharpes)),
        "avg_sharpe": None if sharpes.empty else round(float(sharpes.mean()), 6),
    }


def build_summary(combined: pd.DataFrame) -> pd.DataFrame:
    if combined.empty:
        return pd.DataFrame()
    group_defs = {
        "all": ["_all"],
        "signal_model_specific_tag": ["ai_model_specific_tag"],
        "signal_decision": ["ai_shadow_decision"],
        "valuation_champion_state": ["champion_state"],
        "valuation_challenger_state": ["challenger_state"],
        "valuation_risk_tag": ["risk_tag"],
        "ms_tag_x_champion_state": ["ai_model_specific_tag", "champion_state"],
        "ms_tag_x_challenger_state": ["ai_model_specific_tag", "challenger_state"],
        "ms_tag_x_risk_tag": ["ai_model_specific_tag", "risk_tag"],
        "decision_x_champion_state": ["ai_shadow_decision", "champion_state"],
        "decision_x_risk_tag": ["ai_shadow_decision", "risk_tag"],
    }
    frame = combined.copy()
    frame["_all"] = "all"
    rows: list[dict[str, Any]] = []
    for group_type, cols in group_defs.items():
        grouped = frame.groupby(cols, dropna=False)
        for keys, part in grouped:
            if not isinstance(keys, tuple):
                keys = (keys,)
            group_value = " | ".join(str(value) for value in keys)
            for horizon in HORIZONS:
                rows.append(metric_row(part, group_type, group_value, horizon))
    return pd.DataFrame(rows)


def fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def fmt_num(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.2f}"


def summary_table(summary: pd.DataFrame, group_type: str, horizon: str = "current", max_rows: int = 20) -> list[str]:
    frame = summary[(summary["group_type"].eq(group_type)) & (summary["horizon"].eq(horizon))].copy()
    if frame.empty:
        return ["N/A"]
    frame = frame.sort_values(["sample_count", "candidate_count", "group_value"], ascending=[False, False, True]).head(max_rows)
    lines = [
        "| group | candidates | samples | avg return | win rate | avg mdd | avg sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in frame.iterrows():
        lines.append(
            "| {group} | {candidates} | {samples} | {ret} | {win} | {mdd} | {sharpe} |".format(
                group=row.get("group_value"),
                candidates=int(row.get("candidate_count") or 0),
                samples=int(row.get("sample_count") or 0),
                ret=fmt_pct(row.get("avg_return")),
                win=fmt_pct(row.get("win_rate")),
                mdd=fmt_pct(row.get("avg_mdd")),
                sharpe=fmt_num(row.get("avg_sharpe")),
            )
        )
    return lines


def write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    lines = [
        f"# AI Combined Candidate Validation Monitor - {payload['source_as_of_date']} to {payload['performance_asof_date']}",
        "",
        f"- Signal model: {SIGNAL_MODEL_NAME_KO} (`{SIGNAL_MODEL_CODE}`)",
        f"- Valuation model: {VALUATION_MODEL_NAME_KO} (`{VALUATION_MODEL_CODE}`)",
        "- Purpose: 퀀트후보검증AI tag와 주가수준평가AI state를 결합해 admin-only shadow 관찰",
        "",
        "## Availability",
        "",
    ]
    availability = pd.DataFrame(payload["availability"])
    if availability.empty:
        lines.append("N/A")
    else:
        lines.extend(
            [
                "| horizon | candidates | samples | avg return | win rate |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for _, row in availability.iterrows():
            lines.append(
                f"| {row['horizon']} | {int(row['candidate_count'])} | {int(row['sample_count'])} | {fmt_pct(row['avg_return'])} | {fmt_pct(row['win_rate'])} |"
            )
    for title, group_type in [
        ("Model-Specific Tag x Champion State", "ms_tag_x_champion_state"),
        ("Model-Specific Tag x Challenger State", "ms_tag_x_challenger_state"),
        ("Model-Specific Tag x Risk Tag", "ms_tag_x_risk_tag"),
        ("Signal Decision x Champion State", "decision_x_champion_state"),
        ("Signal Decision x Risk Tag", "decision_x_risk_tag"),
    ]:
        lines.extend(["", f"## {title}", ""])
        lines.extend(summary_table(summary, group_type))
    lines.extend(
        [
            "",
            "## Operating Notes",
            "",
            "- `MS_CONFIRM + FAIR/UNDERVALUED`는 강화 후보 관찰군이다.",
            "- `MS_CONFIRM + OVERHEATED`는 후보 품질은 좋지만 신규 진입 가격 주의군이다.",
            "- `MS_RISK_REVIEW + AVOID/risk_caution`은 보류 또는 제외 검토군이다.",
            "- 1W 이상 horizon은 충분한 거래일이 지나기 전까지 N/A가 정상이다.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    perf_asof = args.performance_asof or args.asof
    source_token = args.asof.replace("-", "")
    perf_token = perf_asof.replace("-", "")
    signal_dir = Path(args.signal_report_dir)
    valuation_dir = Path(args.valuation_report_dir)
    signal = read_csv(signal_dir / f"ai_overlay_shadow_scores_{source_token}.csv", dtype={"ticker": str})
    valuation = read_csv(valuation_dir / f"valuation_ai_challenger_current_candidates_{source_token}.csv", dtype={"security_code": str})
    performance = read_csv(valuation_dir / f"valuation_ai_challenger_shadow_detail_{source_token}_to_{perf_token}.csv", dtype={"security_code": str})
    combined = build_combined(signal, valuation, performance)
    summary = build_summary(combined)

    detail_csv = valuation_dir / f"ai_combined_candidate_validation_detail_{source_token}_to_{perf_token}.csv"
    summary_csv = valuation_dir / f"ai_combined_candidate_validation_summary_{source_token}_to_{perf_token}.csv"
    json_path = valuation_dir / f"ai_combined_candidate_validation_{source_token}_to_{perf_token}.json"
    md_path = valuation_dir / f"ai_combined_candidate_validation_{source_token}_to_{perf_token}.md"
    combined.to_csv(detail_csv, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    availability: list[dict[str, Any]] = []
    all_summary = summary[summary["group_type"].eq("all")]
    for horizon in HORIZONS:
        row_frame = all_summary[all_summary["horizon"].eq(horizon)]
        if row_frame.empty:
            continue
        row = row_frame.iloc[0]
        availability.append(
            {
                "horizon": horizon,
                "candidate_count": int(row.get("candidate_count") or 0),
                "sample_count": int(row.get("sample_count") or 0),
                "avg_return": None if pd.isna(row.get("avg_return")) else float(row.get("avg_return")),
                "win_rate": None if pd.isna(row.get("win_rate")) else float(row.get("win_rate")),
            }
        )
    payload = {
        "source_name": "ai_combined_candidate_validation_monitor",
        "schema_version": "1.0",
        "visibility": "internal_research",
        "source_as_of_date": args.asof,
        "performance_asof_date": perf_asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "signal_model_code": SIGNAL_MODEL_CODE,
        "signal_model_name_ko": SIGNAL_MODEL_NAME_KO,
        "valuation_model_code": VALUATION_MODEL_CODE,
        "valuation_model_name_ko": VALUATION_MODEL_NAME_KO,
        "candidate_count": int(len(combined)),
        "summary_rows": int(len(summary)),
        "availability": availability,
        "outputs": {
            "detail_csv": str(detail_csv),
            "summary_csv": str(summary_csv),
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, payload, summary)
    print(json.dumps({"status": "ok", **payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
