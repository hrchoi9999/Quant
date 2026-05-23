# build_valuation_ai_challenger_shadow_tracker.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PRICE_DB = ROOT / "data" / "db" / "price.db"
REPORT_DIR = ROOT / "reports" / "valuation_ai"
ADMIN_CURRENT_DIR = ROOT / "service_platform" / "web" / "admin_data" / "current"
CURRENT_JSON = ADMIN_CURRENT_DIR / "valuation_ai_challenger_current.json"
MODEL_CODE = "AI-GROWTH-VALUATION-V01"
MODEL_NAME_KR = "주가수준평가AI"

HORIZONS = {"1w": 5, "2w": 10, "1m": 21, "2m": 42, "3m": 63, "6m": 126, "1y": 252}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build live shadow performance payload for valuation AI challenger overlay.")
    parser.add_argument("--current-json", default=str(CURRENT_JSON))
    parser.add_argument("--performance-asof", required=True)
    parser.add_argument("--out-dir", default=str(REPORT_DIR))
    parser.add_argument("--admin-current-dir", default=str(ADMIN_CURRENT_DIR))
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_prices(tickers: list[str], max_date: str) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    with sqlite3.connect(str(PRICE_DB)) as con:
        df = pd.read_sql_query(
            f"""
            SELECT ticker, date, close
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date <= ?
              AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            con,
            params=[*tickers, max_date],
        )
    if df.empty:
        return df
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["ticker", "date", "close"])


def max_drawdown(closes: pd.Series) -> float | None:
    vals = pd.to_numeric(closes, errors="coerce").dropna()
    if len(vals) < 2:
        return None
    dd = vals / vals.cummax() - 1.0
    return round(float(dd.min()), 6)


def sharpe_ratio(closes: pd.Series) -> float | None:
    vals = pd.to_numeric(closes, errors="coerce").dropna()
    if len(vals) < 3:
        return None
    returns = vals.pct_change().dropna()
    std = float(returns.std(ddof=0))
    if std == 0:
        return None
    return round(float(returns.mean()) / std * np.sqrt(252), 6)


def calc_window(price_frame: pd.DataFrame, start_date: pd.Timestamp, asof_date: pd.Timestamp, trading_days: int | None = None) -> dict[str, Any]:
    hist = price_frame[(price_frame["date"] >= start_date) & (price_frame["date"] <= asof_date)].sort_values("date").reset_index(drop=True)
    if hist.empty:
        return {"return": None, "mdd": None, "sharpe": None, "end_date": None, "trading_days_seen": 0, "available": 0}
    if trading_days is not None and len(hist) <= trading_days:
        return {"return": None, "mdd": None, "sharpe": None, "end_date": None, "trading_days_seen": int(len(hist)), "available": 0}
    target_idx = len(hist) - 1 if trading_days is None else int(trading_days)
    if target_idx <= 0:
        return {"return": None, "mdd": None, "sharpe": None, "end_date": None, "trading_days_seen": int(len(hist)), "available": 0}
    window = hist.iloc[: target_idx + 1].copy()
    start_close = float(window.iloc[0]["close"])
    end_close = float(window.iloc[-1]["close"])
    ret = None if start_close <= 0 else round(end_close / start_close - 1.0, 6)
    return {
        "return": ret,
        "mdd": max_drawdown(window["close"]),
        "sharpe": sharpe_ratio(window["close"]),
        "end_date": pd.Timestamp(window.iloc[-1]["date"]).strftime("%Y-%m-%d"),
        "trading_days_seen": int(len(hist)),
        "available": 1,
    }


def track_start(row: dict[str, Any], fallback_asof: str) -> pd.Timestamp:
    for key in ["snapshot_date", "week_end"]:
        value = row.get(key)
        if value:
            ts = pd.to_datetime(value, errors="coerce")
            if not pd.isna(ts):
                return pd.Timestamp(ts).normalize()
    return pd.Timestamp(fallback_asof)


def confidence_bucket(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if np.isnan(score):
        return "unknown"
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def build_detail(payload: dict[str, Any], performance_asof: str) -> list[dict[str, Any]]:
    candidates = payload.get("candidates", [])
    tickers = sorted({str(row.get("security_code", "")).zfill(6) for row in candidates if row.get("security_code")})
    prices = load_prices(tickers, performance_asof)
    price_groups = {ticker: frame for ticker, frame in prices.groupby("ticker")} if not prices.empty else {}
    asof_ts = pd.Timestamp(performance_asof)
    rows: list[dict[str, Any]] = []
    for row in candidates:
        ticker = str(row.get("security_code", "")).zfill(6)
        start = track_start(row, payload.get("as_of_date") or performance_asof)
        price_frame = price_groups.get(ticker)
        item = {
            "ai_model_code": MODEL_CODE,
            "ai_model_name_ko": MODEL_NAME_KR,
            "source_as_of_date": payload.get("as_of_date"),
            "performance_asof_date": performance_asof,
            "scope": row.get("scope"),
            "model_code": row.get("model_code"),
            "security_code": ticker,
            "display_name": row.get("display_name"),
            "rank_no": row.get("rank_no"),
            "score": row.get("score"),
            "score_basis": row.get("score_basis"),
            "weight": row.get("weight"),
            "candidate_bucket": row.get("candidate_bucket"),
            "track_start_date": start.strftime("%Y-%m-%d"),
            "champion_state": row.get("champion_state"),
            "champion_score": row.get("champion_score"),
            "challenger_state": row.get("challenger_state"),
            "challenger_score": row.get("challenger_score"),
            "challenger_change_label": row.get("challenger_change_label"),
            "risk_state": row.get("risk_state"),
            "risk_score": row.get("risk_score"),
            "risk_change_label": row.get("risk_change_label"),
            "risk_tag": row.get("risk_tag"),
            "qm_quantmarket_theme_bucket": row.get("qm_quantmarket_theme_bucket"),
            "qm_theme_momentum_score": row.get("qm_theme_momentum_score"),
            "qm_theme_mapping_confidence": row.get("qm_theme_mapping_confidence"),
            "qm_theme_confidence_bucket": confidence_bucket(row.get("qm_theme_mapping_confidence")),
            "qm_risk_score": row.get("qm_risk_score"),
            "qm_market_stress_score": row.get("qm_market_stress_score"),
        }
        if price_frame is None or price_frame.empty:
            current = {"return": None, "mdd": None, "sharpe": None, "end_date": None, "trading_days_seen": 0, "available": 0}
        else:
            current = calc_window(price_frame, start, asof_ts, None)
        item["live_current_return"] = current["return"]
        item["live_current_mdd"] = current["mdd"]
        item["live_current_sharpe"] = current["sharpe"]
        item["live_current_end_date"] = current["end_date"]
        item["live_current_trading_days_seen"] = current["trading_days_seen"]
        for horizon, days in HORIZONS.items():
            metrics = current if horizon == "current" else calc_window(price_frame, start, asof_ts, days) if price_frame is not None else {"return": None, "mdd": None, "sharpe": None, "end_date": None, "trading_days_seen": 0, "available": 0}
            item[f"live_ret_{horizon}"] = metrics["return"]
            item[f"live_mdd_{horizon}"] = metrics["mdd"]
            item[f"live_sharpe_{horizon}"] = metrics["sharpe"]
            item[f"live_ret_{horizon}_available"] = metrics["available"]
            item[f"live_ret_{horizon}_trading_days_seen"] = metrics["trading_days_seen"]
        rows.append(item)
    return rows


def metric_row(rows: list[dict[str, Any]], group_type: str, group_value: str, horizon: str) -> dict[str, Any]:
    ret_col = "live_current_return" if horizon == "current" else f"live_ret_{horizon}"
    mdd_col = "live_current_mdd" if horizon == "current" else f"live_mdd_{horizon}"
    sharpe_col = "live_current_sharpe" if horizon == "current" else f"live_sharpe_{horizon}"
    vals = pd.to_numeric(pd.Series([r.get(ret_col) for r in rows]), errors="coerce").dropna()
    mdds = pd.to_numeric(pd.Series([r.get(mdd_col) for r in rows]), errors="coerce").dropna()
    sharpes = pd.to_numeric(pd.Series([r.get(sharpe_col) for r in rows]), errors="coerce").dropna()
    return {
        "group_type": group_type,
        "group_value": group_value,
        "horizon": horizon,
        "candidate_count": len(rows),
        "sample_count": int(len(vals)),
        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
        "median_return": None if vals.empty else round(float(vals.median()), 6),
        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
        "mdd_sample_count": int(len(mdds)),
        "avg_mdd": None if mdds.empty else round(float(mdds.mean()), 6),
        "sharpe_sample_count": int(len(sharpes)),
        "avg_sharpe": None if sharpes.empty else round(float(sharpes.mean()), 6),
    }


def build_summary(detail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {("all", "all"): detail}
    for key in [
        "scope",
        "model_code",
        "champion_state",
        "challenger_state",
        "challenger_change_label",
        "risk_state",
        "risk_change_label",
        "risk_tag",
        "qm_quantmarket_theme_bucket",
        "qm_theme_confidence_bucket",
    ]:
        bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in detail:
            bucket[str(row.get(key))].append(row)
        for value, frame in bucket.items():
            groups[(key, value)] = frame
    for (group_type, group_value), frame in groups.items():
        for horizon in ["current", *HORIZONS.keys()]:
            rows.append(metric_row(frame, group_type, group_value, horizon))
    return rows


def main() -> None:
    args = parse_args()
    current_payload = load_json(Path(args.current_json))
    detail = build_detail(current_payload, args.performance_asof)
    summary = build_summary(detail)
    out_dir = Path(args.out_dir)
    admin_current_dir = Path(args.admin_current_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    admin_current_dir.mkdir(parents=True, exist_ok=True)
    source_token = str(current_payload.get("as_of_date", args.performance_asof)).replace("-", "")
    perf_token = args.performance_asof.replace("-", "")
    detail_csv = out_dir / f"valuation_ai_challenger_shadow_detail_{source_token}_to_{perf_token}.csv"
    summary_csv = out_dir / f"valuation_ai_challenger_shadow_summary_{source_token}_to_{perf_token}.csv"
    report_json = out_dir / f"valuation_ai_challenger_shadow_performance_{source_token}_to_{perf_token}.json"
    current_json = admin_current_dir / "valuation_ai_challenger_shadow_performance.json"
    pd.DataFrame(detail).to_csv(detail_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame(summary).to_csv(summary_csv, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "valuation_ai_challenger_shadow_performance",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KR,
        "source_as_of_date": current_payload.get("as_of_date"),
        "performance_asof_date": args.performance_asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metric_basis": "live_price_tracking_after_candidate_snapshot",
        "horizons": ["current", *HORIZONS.keys()],
        "summary": summary,
        "detail": detail,
        "outputs": {
            "detail_csv": str(detail_csv),
            "summary_csv": str(summary_csv),
            "report_json": str(report_json),
            "admin_current_json": str(current_json),
        },
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    current_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "detail_rows": len(detail), "summary_rows": len(summary), "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
