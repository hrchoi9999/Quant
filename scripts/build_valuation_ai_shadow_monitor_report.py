from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "valuation_ai"
ADMIN_CURRENT_DIR = ROOT / "service_platform" / "web" / "admin_data" / "current"
CURRENT_JSON = ADMIN_CURRENT_DIR / "valuation_ai_challenger_current.json"
PERFORMANCE_JSON = ADMIN_CURRENT_DIR / "valuation_ai_challenger_shadow_performance.json"
ADMIN_MONITOR_JSON = ADMIN_CURRENT_DIR / "valuation_ai_shadow_monitor.json"

HORIZON_ORDER = ["current", "1w", "2w", "1m", "2m", "3m", "6m", "1y"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an operator report for QM theme challenger and QM risk shadow tracking."
    )
    parser.add_argument("--current-json", default=str(CURRENT_JSON))
    parser.add_argument("--performance-json", default=str(PERFORMANCE_JSON))
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    parser.add_argument("--admin-current-dir", default=str(ADMIN_CURRENT_DIR))
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def pct(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return "N/A"
    return f"{number * 100:.2f}%"


def num(value: Any, digits: int = 3) -> str:
    number = safe_float(value)
    if number is None:
        return "N/A"
    return f"{number:.{digits}f}"


def group_frame(summary: pd.DataFrame, group_type: str, horizon: str) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    frame = summary[
        summary["group_type"].eq(group_type) & summary["horizon"].eq(horizon)
    ].copy()
    if frame.empty:
        return frame
    return frame.sort_values(["sample_count", "candidate_count", "group_value"], ascending=[False, False, True])


def metric_row_from_frame(frame: pd.DataFrame, group_type: str, group_value: str, horizon: str) -> dict[str, Any]:
    ret_col = "live_current_return" if horizon == "current" else f"live_ret_{horizon}"
    mdd_col = "live_current_mdd" if horizon == "current" else f"live_mdd_{horizon}"
    sharpe_col = "live_current_sharpe" if horizon == "current" else f"live_sharpe_{horizon}"
    vals = pd.to_numeric(frame.get(ret_col, pd.Series(dtype=float)), errors="coerce").dropna()
    mdds = pd.to_numeric(frame.get(mdd_col, pd.Series(dtype=float)), errors="coerce").dropna()
    sharpes = pd.to_numeric(frame.get(sharpe_col, pd.Series(dtype=float)), errors="coerce").dropna()
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


def summarize_detail(frame: pd.DataFrame, group_type: str) -> pd.DataFrame:
    if frame.empty or group_type not in frame.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for group_value, group in frame.groupby(group_type, dropna=False):
        label = "None" if pd.isna(group_value) else str(group_value)
        for horizon in HORIZON_ORDER:
            rows.append(metric_row_from_frame(group, group_type, label, horizon))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["horizon", "sample_count", "candidate_count", "group_value"], ascending=[True, False, False, True])


def stock_only(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    if "champion_state" in out.columns:
        out = out[~out["champion_state"].eq("OUT_OF_SCOPE_OR_MISSING")]
    if "risk_tag" in out.columns:
        out = out[~out["risk_tag"].eq("out_of_scope")]
    return out.copy()


def ticker_snapshot_detail(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty or "security_code" not in detail.columns:
        return pd.DataFrame()
    frame = detail.copy()
    if "track_start_date" not in frame.columns:
        frame["track_start_date"] = ""
    frame["_rank_sort"] = pd.to_numeric(frame.get("rank_no"), errors="coerce")
    frame["_has_return"] = pd.to_numeric(frame.get("live_current_return"), errors="coerce").notna().astype(int)
    sort_cols = ["security_code", "track_start_date", "_has_return", "_rank_sort", "scope", "model_code"]
    frame = frame.sort_values(sort_cols, ascending=[True, True, False, True, True, True])
    frame = frame.drop_duplicates(["security_code", "track_start_date"], keep="first")
    return frame.drop(columns=["_rank_sort", "_has_return"], errors="ignore").reset_index(drop=True)


def markdown_table(frame: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    if frame.empty:
        return ["N/A"]
    rows = frame.head(max_rows).copy()
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in rows.iterrows():
        values: list[str] = []
        for col in columns:
            raw = row.get(col)
            if col in {"avg_return", "median_return", "win_rate", "avg_mdd"}:
                values.append(pct(raw))
            elif col == "avg_sharpe":
                values.append(num(raw, 2))
            elif col in {"candidate_count", "sample_count"}:
                values.append(str(int(raw)) if pd.notna(raw) else "0")
            else:
                values.append(str(raw) if pd.notna(raw) else "N/A")
        lines.append("| " + " | ".join(values) + " |")
    return lines


def table_records(frame: pd.DataFrame, group_type: str, horizon: str) -> list[dict[str, Any]]:
    rows = group_frame(frame, group_type, horizon)
    if rows.empty:
        return []
    return rows.where(pd.notna(rows), None).to_dict(orient="records")


def top_candidates(detail: pd.DataFrame, label: str, count: int = 10) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    frame = detail[detail["challenger_change_label"].eq(label)].copy()
    if frame.empty:
        return frame
    sort_cols = [col for col in ["scope", "model_code", "rank_no"] if col in frame.columns]
    if sort_cols:
        frame = frame.sort_values(sort_cols)
    return frame.head(count)


def candidate_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["N/A"]
    columns = [
        "scope",
        "model_code",
        "security_code",
        "display_name",
        "rank_no",
        "champion_state",
        "challenger_state",
        "risk_tag",
        "qm_quantmarket_theme_bucket",
    ]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame[columns].iterrows():
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return lines


def build_group_exports(summary: pd.DataFrame, out_dir: Path, source_token: str, perf_token: str) -> dict[str, str]:
    exports: dict[str, str] = {}
    for group_type in [
        "challenger_change_label",
        "risk_tag",
        "risk_state",
        "qm_quantmarket_theme_bucket",
        "qm_theme_confidence_bucket",
    ]:
        frame = summary[summary["group_type"].eq(group_type)].copy()
        path = out_dir / f"valuation_ai_shadow_monitor_{group_type}_{source_token}_to_{perf_token}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        exports[group_type] = str(path)
    return exports


def build_security_snapshot_exports(
    detail: pd.DataFrame,
    out_dir: Path,
    source_token: str,
    perf_token: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    ticker_detail = ticker_snapshot_detail(detail)
    ticker_stock_detail = stock_only(ticker_detail)
    exports: dict[str, str] = {}

    detail_path = out_dir / f"valuation_ai_shadow_monitor_ticker_snapshot_detail_{source_token}_to_{perf_token}.csv"
    stock_detail_path = out_dir / f"valuation_ai_shadow_monitor_stock_ticker_snapshot_detail_{source_token}_to_{perf_token}.csv"
    ticker_detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    ticker_stock_detail.to_csv(stock_detail_path, index=False, encoding="utf-8-sig")
    exports["ticker_snapshot_detail"] = str(detail_path)
    exports["stock_ticker_snapshot_detail"] = str(stock_detail_path)

    for group_type in ["challenger_change_label", "risk_tag", "risk_state", "qm_quantmarket_theme_bucket", "qm_theme_confidence_bucket"]:
        ticker_summary = summarize_detail(ticker_detail, group_type)
        stock_summary = summarize_detail(ticker_stock_detail, group_type)
        ticker_path = out_dir / f"valuation_ai_shadow_monitor_ticker_snapshot_{group_type}_{source_token}_to_{perf_token}.csv"
        stock_path = out_dir / f"valuation_ai_shadow_monitor_stock_ticker_snapshot_{group_type}_{source_token}_to_{perf_token}.csv"
        ticker_summary.to_csv(ticker_path, index=False, encoding="utf-8-sig")
        stock_summary.to_csv(stock_path, index=False, encoding="utf-8-sig")
        exports[f"ticker_snapshot_{group_type}"] = str(ticker_path)
        exports[f"stock_ticker_snapshot_{group_type}"] = str(stock_path)
    return ticker_detail, ticker_stock_detail, exports


def main() -> None:
    args = parse_args()
    current = load_json(Path(args.current_json))
    performance = load_json(Path(args.performance_json))
    out_dir = Path(args.out_dir)
    admin_current_dir = Path(args.admin_current_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    admin_current_dir.mkdir(parents=True, exist_ok=True)

    candidates = pd.DataFrame(current.get("candidates", []))
    detail = pd.DataFrame(performance.get("detail", []))
    summary = pd.DataFrame(performance.get("summary", []))

    source_asof = str(performance.get("source_as_of_date") or current.get("as_of_date") or "")
    perf_asof = str(performance.get("performance_asof_date") or "")
    source_token = source_asof.replace("-", "") or "unknown"
    perf_token = perf_asof.replace("-", "") or "unknown"

    exports = build_group_exports(summary, out_dir, source_token, perf_token)
    ticker_detail, stock_ticker_detail, ticker_exports = build_security_snapshot_exports(detail, out_dir, source_token, perf_token)
    exports.update(ticker_exports)
    report_json = out_dir / f"valuation_ai_shadow_monitor_{source_token}_to_{perf_token}.json"
    report_md = out_dir / f"valuation_ai_shadow_monitor_{source_token}_to_{perf_token}.md"
    admin_monitor_json = admin_current_dir / ADMIN_MONITOR_JSON.name

    availability = []
    for horizon in HORIZON_ORDER:
        frame = group_frame(summary, "all", horizon)
        if frame.empty:
            continue
        row = frame.iloc[0].to_dict()
        availability.append(
            {
                "horizon": horizon,
                "candidate_count": int(row.get("candidate_count") or 0),
                "sample_count": int(row.get("sample_count") or 0),
                "avg_return": row.get("avg_return"),
                "win_rate": row.get("win_rate"),
            }
        )

    theme_ticker = summarize_detail(stock_ticker_detail, "challenger_change_label")
    risk_ticker = summarize_detail(stock_ticker_detail, "risk_tag")

    payload = {
        "source_name": "valuation_ai_shadow_monitor",
        "schema_version": "1.0",
        "visibility": "internal_research",
        "model_code": current.get("model_code") or performance.get("model_code"),
        "model_name_ko": current.get("model_name_ko") or performance.get("model_name_ko") or "주가수준평가AI",
        "source_as_of_date": source_asof,
        "performance_asof_date": perf_asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": int(len(candidates)),
        "detail_count": int(len(detail)),
        "summary_count": int(len(summary)),
        "tracking_basis_counts": {
            "candidate_rows": int(len(detail)),
            "ticker_snapshots": int(len(ticker_detail)),
            "stock_ticker_snapshots": int(len(stock_ticker_detail)),
        },
        "availability": availability,
        "state_counts": current.get("state_counts") or {},
        "monitor_tables": {
            "theme_challenger_candidate_current": table_records(summary, "challenger_change_label", "current"),
            "theme_challenger_stock_ticker_current": table_records(theme_ticker, "challenger_change_label", "current"),
            "risk_tag_candidate_current": table_records(summary, "risk_tag", "current"),
            "risk_tag_stock_ticker_current": table_records(risk_ticker, "risk_tag", "current"),
        },
        "outputs": {"markdown": str(report_md), "json": str(report_json), "admin_current_json": str(admin_monitor_json), **exports},
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_monitor_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = [
        f"# Valuation AI Shadow Monitor - {source_asof} to {perf_asof}",
        "",
        "- Model name: 주가수준평가AI",
        "",
        "## Scope",
        "",
        "- Champion: LOCAL_MARKET remains reference only.",
        "- Challenger: QM_MARKET_THEME is tracked by upgrade/downgrade and theme bucket.",
        "- Risk overlay: QM_MARKET_RISK is tracked as caution/watch/clear tag, not as a recommendation model.",
        "- ETF rows remain out-of-scope for stock valuation AI.",
        "",
        "## Tracking Basis",
        "",
        "| basis | count | note |",
        "| --- | --- | --- |",
        f"| candidate_rows | {len(detail)} | Raw model candidate rows. A ticker can appear in multiple S/T/I/user models. |",
        f"| ticker_snapshots | {len(ticker_detail)} | Deduplicated by security_code and track_start_date. |",
        f"| stock_ticker_snapshots | {len(stock_ticker_detail)} | Ticker snapshots after excluding valuation out-of-scope rows such as ETFs. |",
        "",
        "## Performance Availability",
        "",
    ]
    lines.extend(markdown_table(pd.DataFrame(availability), ["horizon", "candidate_count", "sample_count", "avg_return", "win_rate"]))
    lines.extend(["", "## QM-THEME Challenger Cohorts - Candidate Rows", ""])
    lines.extend(markdown_table(group_frame(summary, "challenger_change_label", "current"), ["group_value", "candidate_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"]))
    lines.extend(["", "## QM-THEME Challenger Cohorts - Stock Ticker Snapshots", ""])
    lines.extend(markdown_table(group_frame(theme_ticker, "challenger_change_label", "current"), ["group_value", "candidate_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"]))
    lines.extend(["", "## QM-RISK Tag Cohorts - Candidate Rows", ""])
    lines.extend(markdown_table(group_frame(summary, "risk_tag", "current"), ["group_value", "candidate_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"]))
    lines.extend(["", "## QM-RISK Tag Cohorts - Stock Ticker Snapshots", ""])
    lines.extend(markdown_table(group_frame(risk_ticker, "risk_tag", "current"), ["group_value", "candidate_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"]))
    lines.extend(["", "## Theme Bucket Cohorts", ""])
    lines.extend(markdown_table(group_frame(summary, "qm_quantmarket_theme_bucket", "current"), ["group_value", "candidate_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"]))
    lines.extend(["", "## Theme Mapping Confidence Cohorts", ""])
    lines.extend(markdown_table(group_frame(summary, "qm_theme_confidence_bucket", "current"), ["group_value", "candidate_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"]))
    lines.extend(["", "## Upgrade Watchlist", ""])
    lines.extend(candidate_table(top_candidates(candidates, "upgrade")))
    lines.extend(["", "## Downgrade Watchlist", ""])
    lines.extend(candidate_table(top_candidates(candidates, "downgrade")))
    lines.extend(
        [
            "",
            "## Operating Notes",
            "",
            "- If source_as_of_date equals performance_asof_date, 1W and longer horizons should remain N/A.",
            "- Promotion review should wait for at least 4 to 8 weeks of live samples.",
            "- Risk tags should be judged by downside avoidance and MDD, not by raw return alone.",
        ]
    )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
