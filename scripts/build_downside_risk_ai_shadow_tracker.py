from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / r"reports\downside_risk_ai_v01"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
PRICE_DB = ROOT / r"data\db\price.db"

MODEL_CODE = "AI-DOWNSIDE-RISK-V01"
MODEL_NAME_KO = "하락위험예측AI"
HORIZONS = {"1w": 5, "2w": 10, "1m": 21}
SCORE_FILE_RE = re.compile(r"^downside_risk_ai_current_scores_(\d{8})\.csv$")


def _score_files(shadow_asof: str, performance_asof: str, lookback_days: int) -> list[Path]:
    perf_ts = pd.Timestamp(performance_asof)
    if shadow_asof != "all":
        path = REPORT_DIR / f"downside_risk_ai_current_scores_{shadow_asof.replace('-', '')}.csv"
        return [path] if path.exists() else []
    min_ts = perf_ts - pd.Timedelta(days=int(lookback_days))
    files = []
    for path in REPORT_DIR.glob("downside_risk_ai_current_scores_*.csv"):
        match = SCORE_FILE_RE.match(path.name)
        if not match:
            continue
        ts = pd.Timestamp(datetime.strptime(match.group(1), "%Y%m%d").date())
        if min_ts <= ts <= perf_ts:
            files.append(path)
    return sorted(files)


def _load_scores(files: list[Path]) -> pd.DataFrame:
    frames = []
    for path in files:
        token = SCORE_FILE_RE.match(path.name).group(1) if SCORE_FILE_RE.match(path.name) else ""
        frame = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
        frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
        frame["shadow_asof_date"] = datetime.strptime(token, "%Y%m%d").strftime("%Y-%m-%d") if token else frame.get("as_of_date")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _load_prices(tickers: list[str], max_date: str) -> pd.DataFrame:
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


def _max_drawdown(closes: pd.Series) -> float | None:
    vals = pd.to_numeric(closes, errors="coerce").dropna()
    if len(vals) < 2:
        return None
    dd = vals / vals.cummax() - 1.0
    return round(float(dd.min()), 6)


def _window(price_frame: pd.DataFrame, start_date: pd.Timestamp, asof_date: pd.Timestamp, trading_days: int) -> dict[str, Any]:
    hist = price_frame[(price_frame["date"] >= start_date) & (price_frame["date"] <= asof_date)].sort_values("date").reset_index(drop=True)
    if hist.empty or len(hist) <= trading_days:
        return {"return": None, "mdd": None, "end_date": None, "trading_days_seen": int(len(hist)), "available": 0}
    window = hist.iloc[: trading_days + 1].copy()
    start_close = float(window.iloc[0]["close"])
    end_close = float(window.iloc[-1]["close"])
    return {
        "return": None if start_close <= 0 else round(end_close / start_close - 1.0, 6),
        "mdd": _max_drawdown(window["close"]),
        "end_date": pd.Timestamp(window.iloc[-1]["date"]).strftime("%Y-%m-%d"),
        "trading_days_seen": int(len(hist)),
        "available": 1,
    }


def _tracker_role(row: pd.Series) -> str:
    if str(row.get("scope_key")) == "tseries" and str(row.get("model_id")) == "T-STOCK-V01":
        return "t_stock_specific_challenger"
    return "common_champion"


def _build_detail(scores: pd.DataFrame, performance_asof: str) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame()
    scores = scores.copy()
    scores["tracker_role"] = scores.apply(_tracker_role, axis=1)
    scores["event_date"] = pd.to_datetime(scores["event_date"], errors="coerce")
    scores["shadow_asof_date"] = pd.to_datetime(scores["shadow_asof_date"], errors="coerce")
    scores = scores.dropna(subset=["ticker", "event_date", "shadow_asof_date"])
    prices = _load_prices(sorted(scores["ticker"].dropna().unique().tolist()), performance_asof)
    price_groups = {ticker: frame for ticker, frame in prices.groupby("ticker")} if not prices.empty else {}
    asof_ts = pd.Timestamp(performance_asof)
    rows = []
    for row in scores.to_dict(orient="records"):
        ticker = str(row.get("ticker")).zfill(6)
        start = max(pd.Timestamp(row["event_date"]), pd.Timestamp(row["shadow_asof_date"]))
        price_frame = price_groups.get(ticker)
        item = {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KO,
            "shadow_asof_date": pd.Timestamp(row["shadow_asof_date"]).strftime("%Y-%m-%d"),
            "performance_asof_date": performance_asof,
            "tracker_role": row.get("tracker_role"),
            "scope_key": row.get("scope_key"),
            "model_id": row.get("model_id"),
            "ticker": ticker,
            "name": row.get("name"),
            "event_date": pd.Timestamp(row["event_date"]).strftime("%Y-%m-%d"),
            "track_start_date": start.strftime("%Y-%m-%d"),
            "downside_risk_prob": row.get("downside_risk_prob"),
            "downside_risk_tag": row.get("downside_risk_tag"),
            "action_hint": row.get("action_hint"),
        }
        for horizon, days in HORIZONS.items():
            metrics = _window(price_frame, start, asof_ts, days) if price_frame is not None else {"return": None, "mdd": None, "end_date": None, "trading_days_seen": 0, "available": 0}
            item[f"live_ret_{horizon}"] = metrics["return"]
            item[f"live_mdd_{horizon}"] = metrics["mdd"]
            item[f"live_ret_{horizon}_end_date"] = metrics["end_date"]
            item[f"live_ret_{horizon}_available"] = metrics["available"]
            item[f"live_ret_{horizon}_trading_days_seen"] = metrics["trading_days_seen"]
        rows.append(item)
    return pd.DataFrame(rows)


def _metric_row(frame: pd.DataFrame, group_type: str, group_value: str, horizon: str) -> dict[str, Any]:
    vals = pd.to_numeric(frame.get(f"live_ret_{horizon}"), errors="coerce").dropna()
    mdds = pd.to_numeric(frame.get(f"live_mdd_{horizon}"), errors="coerce").dropna()
    return {
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "group_type": group_type,
        "group_value": str(group_value),
        "horizon": horizon,
        "candidate_count": int(len(frame)),
        "sample_count": int(len(vals)),
        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
        "median_return": None if vals.empty else round(float(vals.median()), 6),
        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
        "avg_mdd": None if mdds.empty else round(float(mdds.mean()), 6),
        "bad_return_rate": None if vals.empty else round(float((vals < 0).mean()), 6),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    rows = []
    group_cols = [
        ("all", None),
        ("tracker_role", "tracker_role"),
        ("risk_tag", "downside_risk_tag"),
        ("tracker_role_risk_tag", ["tracker_role", "downside_risk_tag"]),
        ("source_model", ["scope_key", "model_id"]),
    ]
    for group_type, cols in group_cols:
        if cols is None:
            groups = [("all", detail)]
        elif isinstance(cols, list):
            groups = [("|".join(str(x) for x in key), frame) for key, frame in detail.groupby(cols, dropna=False)]
        else:
            groups = [(key, frame) for key, frame in detail.groupby(cols, dropna=False)]
        for group_value, frame in groups:
            for horizon in HORIZONS:
                rows.append(_metric_row(frame, group_type, str(group_value), horizon))
    return pd.DataFrame(rows)


def build_tracker(shadow_asof: str, performance_asof: str, lookback_days: int) -> dict[str, Any]:
    files = _score_files(shadow_asof, performance_asof, lookback_days)
    scores = _load_scores(files)
    detail = _build_detail(scores, performance_asof)
    summary = _summary(detail)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    source_token = shadow_asof.replace("-", "") if shadow_asof != "all" else "all"
    perf_token = performance_asof.replace("-", "")
    detail_path = REPORT_DIR / f"downside_risk_ai_shadow_detail_{source_token}_to_{perf_token}.csv"
    summary_path = REPORT_DIR / f"downside_risk_ai_shadow_summary_{source_token}_to_{perf_token}.csv"
    report_path = REPORT_DIR / f"downside_risk_ai_shadow_tracker_{source_token}_to_{perf_token}.json"
    current_path = ADMIN_CURRENT_DIR / "downside_risk_ai_shadow_tracker.json"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "downside_risk_ai_shadow_tracker",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "shadow_asof": shadow_asof,
        "performance_asof_date": performance_asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tracker_roles": ["common_champion", "t_stock_specific_challenger"],
        "horizons": list(HORIZONS.keys()),
        "score_files": [str(path) for path in files],
        "summary": summary.where(pd.notna(summary), None).to_dict(orient="records"),
        "detail_sample": detail.head(200).where(pd.notna(detail.head(200)), None).to_dict(orient="records"),
        "outputs": {
            "detail_csv": str(detail_path),
            "summary_csv": str(summary_path),
            "report_json": str(report_path),
            "admin_current_json": str(current_path),
        },
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    current_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build live shadow tracker for AI-DOWNSIDE-RISK-V01.")
    parser.add_argument("--shadow-asof", default="all")
    parser.add_argument("--performance-asof", required=True)
    parser.add_argument("--lookback-days", type=int, default=120)
    args = parser.parse_args()
    payload = build_tracker(args.shadow_asof, args.performance_asof, args.lookback_days)
    print(
        json.dumps(
            {
                "status": "ok",
                "summary_rows": len(payload["summary"]),
                "score_files": len(payload["score_files"]),
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
