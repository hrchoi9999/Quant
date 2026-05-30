from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / "reports" / "redbot_user_reports"
SERVICE_ANALYTICS_DB = ROOT / r"data\db\service_analytics.db"
QUANT_SERVICE_DB = ROOT / r"data\db\quant_service.db"
QUANT_SERVICE_DETAIL_DB = ROOT / r"data\db\quant_service_detail.db"
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"
ISERIES_DB = ROOT / r"data\db\i_series_operational.db"
PRICE_DB = ROOT / r"data\db\price.db"
OUT_DIR = ROOT / r"service_platform\web\admin_data\current"
OUT_PATH = OUT_DIR / "admin_new_entry_tracker.json"

USER_MODEL_META = {
    "stable": {"user_model_name": "안정형", "mapped_internal_models": ["S6"]},
    "balanced": {"user_model_name": "균형형", "mapped_internal_models": ["S2", "S5"]},
    "growth": {"user_model_name": "성장형", "mapped_internal_models": ["S3", "S4"]},
}
INTERNAL_MODEL_CODES = ("S2", "S2_PIT_V01", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5", "S6")
ISERIES_MODEL_CODES = ("I-STOCK-STRONG-RSI-V01",)
TSERIES_MODEL_CODES = ("T-STOCK-V01", "T-ETF-V01")
T_BUCKET_RANK = {
    "observe": 1,
    "historical_stage1": 2,
    "near": 2,
    "historical_stage2": 3,
    "confirmed": 3,
}
RETURN_HORIZONS = (("1w", 5), ("2w", 10), ("1m", 21), ("2m", 42), ("3m", 63), ("6m", 126), ("1y", 252))
CALENDAR_WINDOWS = {
    "1w": pd.DateOffset(weeks=1),
    "2w": pd.DateOffset(weeks=2),
    "1m": pd.DateOffset(months=1),
    "2m": pd.DateOffset(months=2),
    "3m": pd.DateOffset(months=3),
    "6m": pd.DateOffset(months=6),
    "1y": pd.DateOffset(years=1),
}
WEIGHT_EPS = 1e-8
ACTUAL_LIVE_START_DATES = {
    "user_models": {
        "stable": "2026-03-18",
        "balanced": "2026-03-18",
        "growth": "2026-03-18",
    },
    "internal_models": {
        "S2": "2026-03-12",
        "S3": "2026-03-12",
        "S3_CORE2": "2026-03-12",
        "S4": "2026-03-17",
        "S5": "2026-03-17",
        "S6": "2026-03-17",
        "S2_PIT_V01": "2026-04-23",
        "S3_ACCEL_V01": "2026-04-23",
        "I-STOCK-STRONG-RSI-V01": "2026-04-29",
    },
    "tseries_models": {
        "T-STOCK-V01": "2026-04-01",
        "T-ETF-V01": "2026-04-01",
    },
}
ACTUAL_LIVE_METRICS = ("current_return", "1w", "2w", "1m", "2m", "3m", "6m", "1y")
EARLIEST_ACTUAL_LIVE_START_DATE = min(
    pd.Timestamp(value)
    for starts_by_scope in ACTUAL_LIVE_START_DATES.values()
    for value in starts_by_scope.values()
)


@dataclass(frozen=True)
class PricePoint:
    date: pd.Timestamp
    close: float


def _normalize_code(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.upper() in {"CASH", "NONE", "NAN"}:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else None


def _week_end(date_str: str, cap_date: str | None = None) -> str:
    dt = pd.Timestamp(date_str)
    shift = (4 - dt.weekday()) % 7
    week_end = dt + pd.Timedelta(days=shift)
    if cap_date:
        cap_ts = pd.Timestamp(cap_date)
        if week_end > cap_ts:
            week_end = cap_ts
    return week_end.strftime("%Y-%m-%d")


def _load_price_points(tickers: set[str], asof: str) -> dict[str, list[PricePoint]]:
    if not tickers:
        return {}
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
            params=[*sorted(tickers), asof],
        )
    if df.empty:
        return {}
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    grouped: dict[str, list[PricePoint]] = {}
    for ticker, frame in df.groupby("ticker"):
        grouped[str(ticker)] = [PricePoint(date=row.date, close=float(row.close)) for row in frame.itertuples()]
    return grouped


def _empty_forward_returns() -> dict[str, Any]:
    return {label: None for label, _ in RETURN_HORIZONS}


def _empty_forward_risk_metrics() -> dict[str, Any]:
    return {label: {"mdd": None, "sharpe": None} for label, _ in RETURN_HORIZONS}


def _path_risk_metrics(closes: list[float], start_idx: int, end_idx: int) -> dict[str, Any]:
    segment = [float(value) for value in closes[start_idx : end_idx + 1] if value is not None]
    if len(segment) < 2:
        return {"mdd": None, "sharpe": None}
    peak = segment[0]
    mdd = 0.0
    returns: list[float] = []
    prev = segment[0]
    for close in segment[1:]:
        if close > peak:
            peak = close
        if peak > 0:
            drawdown = close / peak - 1.0
            if drawdown < mdd:
                mdd = drawdown
        if prev > 0:
            returns.append(close / prev - 1.0)
        prev = close
    if len(returns) > 1:
        mean_ret = sum(returns) / float(len(returns))
        variance = sum((value - mean_ret) ** 2 for value in returns) / float(len(returns))
        vol = variance ** 0.5
    else:
        mean_ret = 0.0
        vol = 0.0
    sharpe = None if vol <= 0 else float(mean_ret / vol * (252.0 ** 0.5))
    return {
        "mdd": round(mdd, 6),
        "sharpe": None if sharpe is None else round(sharpe, 6),
    }


def _forward_returns(
    price_points: list[PricePoint], event_date: str, include_risk_metrics: bool = True
) -> tuple[dict[str, Any], dict[str, Any], float | None, dict[str, Any], str | None]:
    if not price_points:
        return _empty_forward_returns(), _empty_forward_risk_metrics(), None, {"mdd": None, "sharpe": None}, None
    dates = [point.date for point in price_points]
    closes = [point.close for point in price_points]
    event_ts = pd.Timestamp(event_date)
    start_idx = next((idx for idx, dt in enumerate(dates) if dt >= event_ts), None)
    if start_idx is None:
        return _empty_forward_returns(), _empty_forward_risk_metrics(), None, {"mdd": None, "sharpe": None}, None
    start_price = closes[start_idx]
    metrics: dict[str, Any] = {}
    risk_metrics: dict[str, Any] = {}
    for label, offset in RETURN_HORIZONS:
        if label in {"1w", "2w"}:
            target_idx = start_idx + offset
        else:
            month_offsets = {"1m": 1, "2m": 2, "3m": 3, "6m": 6}
            if label in month_offsets:
                target_ts = event_ts + pd.DateOffset(months=month_offsets[label])
            elif label == "1y":
                target_ts = event_ts + pd.DateOffset(years=1)
            else:
                target_ts = None
            target_idx = None if target_ts is None else next((idx for idx, dt in enumerate(dates) if dt >= target_ts), None)
        if target_idx is None or target_idx >= len(closes):
            metrics[label] = None
            risk_metrics[label] = {"mdd": None, "sharpe": None}
        else:
            metrics[label] = round(closes[target_idx] / start_price - 1.0, 6)
            risk_metrics[label] = (
                _path_risk_metrics(closes, start_idx, target_idx)
                if include_risk_metrics
                else {"mdd": None, "sharpe": None}
            )
    latest_idx = len(closes) - 1
    current_return = round(closes[latest_idx] / start_price - 1.0, 6)
    current_risk = (
        _path_risk_metrics(closes, start_idx, latest_idx)
        if include_risk_metrics
        else {"mdd": None, "sharpe": None}
    )
    latest_price_date = dates[latest_idx].strftime("%Y-%m-%d")
    return metrics, risk_metrics, current_return, current_risk, latest_price_date


def _summary_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    summary = (
        df.groupby([key, "event_type"], dropna=False, as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values([key, "event_type"])
    )
    return summary.to_dict(orient="records")


def _metric_summary(values: list[float], mdds: list[float] | None = None, sharpes: list[float] | None = None) -> dict[str, Any]:
    mdd_series = pd.Series(mdds or [], dtype="float64").dropna()
    sharpe_series = pd.Series(sharpes or [], dtype="float64").dropna()
    if not values:
        return {
            "sample_count": 0,
            "avg_return": None,
            "median_return": None,
            "win_rate": None,
            "mdd_sample_count": int(mdd_series.size),
            "avg_mdd": None if mdd_series.empty else round(float(mdd_series.mean()), 6),
            "median_mdd": None if mdd_series.empty else round(float(mdd_series.median()), 6),
            "sharpe_sample_count": int(sharpe_series.size),
            "avg_sharpe": None if sharpe_series.empty else round(float(sharpe_series.mean()), 6),
            "median_sharpe": None if sharpe_series.empty else round(float(sharpe_series.median()), 6),
        }
    series = pd.Series(values, dtype="float64").dropna()
    if series.empty:
        return {
            "sample_count": 0,
            "avg_return": None,
            "median_return": None,
            "win_rate": None,
            "mdd_sample_count": int(mdd_series.size),
            "avg_mdd": None if mdd_series.empty else round(float(mdd_series.mean()), 6),
            "median_mdd": None if mdd_series.empty else round(float(mdd_series.median()), 6),
            "sharpe_sample_count": int(sharpe_series.size),
            "avg_sharpe": None if sharpe_series.empty else round(float(sharpe_series.mean()), 6),
            "median_sharpe": None if sharpe_series.empty else round(float(sharpe_series.median()), 6),
        }
    return {
        "sample_count": int(series.size),
        "avg_return": round(float(series.mean()), 6),
        "median_return": round(float(series.median()), 6),
        "win_rate": round(float((series > 0).mean()), 6),
        "mdd_sample_count": int(mdd_series.size),
        "avg_mdd": None if mdd_series.empty else round(float(mdd_series.mean()), 6),
        "median_mdd": None if mdd_series.empty else round(float(mdd_series.median()), 6),
        "sharpe_sample_count": int(sharpe_series.size),
        "avg_sharpe": None if sharpe_series.empty else round(float(sharpe_series.mean()), 6),
        "median_sharpe": None if sharpe_series.empty else round(float(sharpe_series.median()), 6),
    }


def _actual_live_model_summary(
    *,
    rows: list[dict[str, Any]],
    model_key: str,
    live_start_date: str,
    model_id_field: str,
) -> dict[str, Any]:
    start_ts = pd.Timestamp(live_start_date)
    live_rows = [
        row
        for row in rows
        if str(row.get(model_id_field)) == model_key
        and row.get("event_date")
        and pd.Timestamp(str(row["event_date"])) >= start_ts
    ]
    metrics: dict[str, Any] = {}
    for metric in ACTUAL_LIVE_METRICS:
        values: list[float] = []
        mdds: list[float] = []
        sharpes: list[float] = []
        for row in live_rows:
            raw_value = row.get("current_return") if metric == "current_return" else (row.get("forward_returns") or {}).get(metric)
            value = _safe_float(raw_value)
            if value is not None:
                values.append(value)
            risk_payload = row.get("current_risk_metrics") if metric == "current_return" else (row.get("forward_risk_metrics") or {}).get(metric)
            if isinstance(risk_payload, dict):
                mdd = _safe_float(risk_payload.get("mdd"))
                sharpe = _safe_float(risk_payload.get("sharpe"))
                if mdd is not None:
                    mdds.append(mdd)
                if sharpe is not None:
                    sharpes.append(sharpe)
        metrics[metric] = _metric_summary(values, mdds, sharpes)
    return {
        model_id_field: model_key,
        "live_start_date": live_start_date,
        "source_event_count": len([row for row in rows if str(row.get(model_id_field)) == model_key]),
        "live_event_count": len(live_rows),
        "latest_live_event_date": max((str(row.get("event_date")) for row in live_rows if row.get("event_date")), default=None),
        "metric_basis": "actual_market_price_forward_return_since_live_start",
        "metrics": metrics,
    }


def build_actual_live_performance_summary(
    user_rows: list[dict[str, Any]],
    internal_rows: list[dict[str, Any]],
    tseries_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    user_summary = [
        _actual_live_model_summary(
            rows=user_rows,
            model_key=profile,
            live_start_date=live_start_date,
            model_id_field="service_profile",
        )
        for profile, live_start_date in ACTUAL_LIVE_START_DATES["user_models"].items()
    ]
    internal_summary = [
        _actual_live_model_summary(
            rows=internal_rows,
            model_key=model_code,
            live_start_date=live_start_date,
            model_id_field="model_code",
        )
        for model_code, live_start_date in ACTUAL_LIVE_START_DATES["internal_models"].items()
    ]
    tseries_summary = [
        _actual_live_model_summary(
            rows=tseries_rows,
            model_key=model_code,
            live_start_date=live_start_date,
            model_id_field="model_code",
        )
        for model_code, live_start_date in ACTUAL_LIVE_START_DATES["tseries_models"].items()
    ]
    return {
        "metric_basis": "actual_market_price_forward_return_since_live_start",
        "description": "운영 시작일 이후 모델 편입 이벤트의 실제 시장가격 기반 성과 추적입니다. 백테스트 NAV 성과와 분리해서 사용해야 합니다.",
        "horizons": list(ACTUAL_LIVE_METRICS),
        "user_models": user_summary,
        "internal_models": internal_summary,
        "tseries_models": tseries_summary,
    }


def _ranking_summary_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    summary = (
        df.groupby([key], dropna=False, as_index=False)
        .agg(row_count=("security_code", "size"), week_count=("week_end", "nunique"))
        .sort_values([key])
    )
    return summary.to_dict(orient="records")


def _safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calc_nav_window_stats(nav_df: pd.DataFrame, label: str) -> tuple[float | None, float | None]:
    if nav_df.empty:
        return None, None
    latest_date = nav_df["date"].iloc[-1]
    start_date = latest_date - CALENDAR_WINDOWS[label]
    seg = nav_df.loc[nav_df["date"] >= start_date].copy()
    if len(seg) < 2:
        return None, None
    returns = seg["nav"].pct_change().dropna()
    vol = float(returns.std(ddof=0)) if len(returns) > 1 else 0.0
    elapsed_days = max((seg["date"].iloc[-1] - seg["date"].iloc[0]).days, 1)
    periods_per_year = max(len(returns) / elapsed_days * 365.25, 1.0)
    sharpe = None if vol <= 0 else float((returns.mean() / vol) * (periods_per_year ** 0.5))
    peak = seg["nav"].cummax()
    mdd = float((seg["nav"] / peak - 1.0).min())
    return mdd, sharpe


def _build_nav_summary_payload(
    *,
    model_code: str,
    display_name: str,
    asof_date: str,
    nav_df: pd.DataFrame,
    sample_count: int | None,
    metric_basis: str,
) -> dict[str, Any] | None:
    if nav_df.empty:
        return None
    nav = nav_df.copy()
    nav["date"] = pd.to_datetime(nav["date"], errors="coerce")
    nav["nav"] = pd.to_numeric(nav["nav"], errors="coerce")
    nav = nav.dropna(subset=["date", "nav"]).sort_values("date").reset_index(drop=True)
    if len(nav) < 2:
        return None
    latest_nav = float(nav["nav"].iloc[-1])
    periods: dict[str, float | None] = {}
    for label, offset in CALENDAR_WINDOWS.items():
        target_date = nav["date"].iloc[-1] - offset
        candidates = nav.index[(nav.index < len(nav) - 1) & (nav["date"] <= target_date)]
        if len(candidates) == 0:
            periods[label] = None
            continue
        start_idx = int(candidates[-1])
        start_nav = float(nav["nav"].iloc[start_idx])
        periods[label] = None if start_nav == 0 else round(latest_nav / start_nav - 1.0, 6)
    first_nav = float(nav["nav"].iloc[0])
    itd_return = None if first_nav == 0 else round(latest_nav / first_nav - 1.0, 6)
    elapsed_years = max((nav["date"].iloc[-1] - nav["date"].iloc[0]).days / 365.25, 1.0 / 252.0)
    cagr = None if first_nav <= 0 else round((latest_nav / first_nav) ** (1.0 / elapsed_years) - 1.0, 6)
    mdd_1y, sharpe_1y = _calc_nav_window_stats(nav, "1y")
    return {
        "model_code": model_code,
        "display_name": display_name,
        "asof_date": asof_date,
        "trailing_1w": periods["1w"],
        "trailing_2w": periods["2w"],
        "trailing_1m": periods["1m"],
        "trailing_2m": periods["2m"],
        "trailing_3m": periods["3m"],
        "trailing_6m": periods["6m"],
        "trailing_1y": periods["1y"],
        "itd_return": itd_return,
        "cagr": cagr,
        "cagr_1y": periods["1y"],
        "mdd_1y": None if mdd_1y is None else round(mdd_1y, 6),
        "sharpe_1y": None if sharpe_1y is None else round(sharpe_1y, 6),
        "sample_count": sample_count,
        "metric_basis": metric_basis,
        "period_returns": {
            "1w": periods["1w"],
            "2w": periods["2w"],
            "1m": periods["1m"],
            "2m": periods["2m"],
            "3m": periods["3m"],
            "6m": periods["6m"],
            "1y": periods["1y"],
            "itd": itd_return,
        },
    }


def _enrich_rows_with_weekly_rank(
    rows: list[dict[str, Any]],
    ranking_rows: list[dict[str, Any]],
    model_field: str,
) -> list[dict[str, Any]]:
    rank_index = {
        (str(rank_row.get(model_field)), str(rank_row.get("week_end")), str(rank_row.get("security_code"))): rank_row
        for rank_row in ranking_rows
        if rank_row.get(model_field) and rank_row.get("week_end") and rank_row.get("security_code")
    }
    enriched: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get(model_field)), str(row.get("week_end")), str(row.get("security_code")))
        rank_row = rank_index.get(key)
        updated = dict(row)
        if rank_row:
            updated["weekly_snapshot_date"] = rank_row.get("snapshot_date")
            updated["weekly_rank_no"] = rank_row.get("rank_no")
            updated["weekly_score"] = rank_row.get("score")
            updated["weekly_score_basis"] = rank_row.get("score_basis")
            updated["weekly_weight"] = rank_row.get("weight")
            updated["snapshot_date"] = rank_row.get("snapshot_date")
            updated["rank_no"] = rank_row.get("rank_no")
            updated["score"] = rank_row.get("score")
            updated["score_basis"] = rank_row.get("score_basis")
            updated["weight"] = rank_row.get("weight")
            if "candidate_bucket" in rank_row:
                updated["weekly_candidate_bucket"] = rank_row.get("candidate_bucket")
                updated["candidate_bucket"] = rank_row.get("candidate_bucket")
            if "stage1_prob" in rank_row:
                updated["weekly_stage1_prob"] = rank_row.get("stage1_prob")
            if "stage2_prob" in rank_row:
                updated["weekly_stage2_prob"] = rank_row.get("stage2_prob")
        enriched.append(updated)
    return enriched


def _load_user_snapshots() -> dict[str, list[dict[str, Any]]]:
    snapshots: dict[str, list[dict[str, Any]]] = {}
    for profile in USER_MODEL_META:
        rows: list[dict[str, Any]] = []
        for path in sorted(REPORT_DIR.glob(f"redbot_user_report_{profile}_*.json")):
            token = path.stem.rsplit("_", 1)[-1]
            asof = f"{token[:4]}-{token[4:6]}-{token[6:8]}"
            payload = json.loads(path.read_text(encoding="utf-8"))
            holdings = []
            portfolio_items = payload.get("model_portfolio") or payload.get("recommended_portfolio") or []
            for item in portfolio_items:
                code = _normalize_code(item.get("security_code"))
                if code is None:
                    continue
                holdings.append(
                    {
                        "ticker": code,
                        "display_name": item.get("display_name") or code,
                        "weight": float(item.get("target_weight") or 0.0),
                        "asset_group": item.get("asset_group"),
                    }
                )
            rows.append({"asof_date": asof, "holdings": holdings})
        snapshots[profile] = rows
    return snapshots


def build_user_weekly_rank_rows(asof: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    snapshots = _load_user_snapshots()
    for profile, history in snapshots.items():
        if not history:
            continue
        for snapshot in history:
            ranked_holdings = sorted(
                [
                    item
                    for item in snapshot["holdings"]
                    if item.get("ticker") and float(item.get("weight") or 0.0) > WEIGHT_EPS
                ],
                key=lambda item: (-float(item.get("weight") or 0.0), str(item.get("display_name") or item.get("ticker"))),
            )
            for rank_no, item in enumerate(ranked_holdings, start=1):
                weight = round(float(item.get("weight") or 0.0), 6)
                rows.append(
                    {
                        "scope": "user",
                        "service_profile": profile,
                        "model_key": profile,
                        "user_model_name": USER_MODEL_META[profile]["user_model_name"],
                        "week_end": _week_end(snapshot["asof_date"], asof),
                        "snapshot_date": snapshot["asof_date"],
                        "security_code": item["ticker"],
                        "display_name": item.get("display_name") or item["ticker"],
                        "rank_no": rank_no,
                        "score": weight,
                        "score_basis": "target_weight_proxy",
                        "weight": weight,
                        "is_latest_snapshot": snapshot["asof_date"] == history[-1]["asof_date"],
                    }
                )
    return rows


def build_user_rows(asof: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    snapshots = _load_user_snapshots()
    for profile, history in snapshots.items():
        if len(history) < 2:
            continue
        ever_seen: set[str] = set()
        latest_holdings = {item["ticker"] for item in history[-1]["holdings"] if item["weight"] > WEIGHT_EPS}
        first_snapshot = history[0]
        for item in first_snapshot["holdings"]:
            if item["weight"] > WEIGHT_EPS:
                ever_seen.add(item["ticker"])
        for prev, curr in zip(history[:-1], history[1:]):
            prev_map = {item["ticker"]: item for item in prev["holdings"]}
            curr_map = {item["ticker"]: item for item in curr["holdings"]}
            for ticker in sorted(set(prev_map) | set(curr_map)):
                prev_weight = float(prev_map.get(ticker, {}).get("weight", 0.0) or 0.0)
                curr_weight = float(curr_map.get(ticker, {}).get("weight", 0.0) or 0.0)
                if curr_weight <= WEIGHT_EPS:
                    continue
                display_name = curr_map.get(ticker, prev_map.get(ticker, {})).get("display_name", ticker)
                asset_group = curr_map.get(ticker, prev_map.get(ticker, {})).get("asset_group")
                if prev_weight <= WEIGHT_EPS and curr_weight > WEIGHT_EPS:
                    event_type = "re_entry" if ticker in ever_seen else "new_entry"
                elif prev_weight > WEIGHT_EPS and curr_weight > prev_weight + WEIGHT_EPS:
                    event_type = "weight_increase"
                else:
                    ever_seen.add(ticker)
                    continue
                rows.append(
                    {
                        "scope": "user",
                        "service_profile": profile,
                        "user_model_name": USER_MODEL_META[profile]["user_model_name"],
                        "model_key": profile,
                        "event_type": event_type,
                        "event_date": curr["asof_date"],
                        "week_end": _week_end(curr["asof_date"], asof),
                        "security_code": ticker,
                        "display_name": display_name,
                        "asset_group": asset_group,
                        "prev_weight": round(prev_weight, 6),
                        "curr_weight": round(curr_weight, 6),
                        "delta_weight": round(curr_weight - prev_weight, 6),
                        "is_current": ticker in latest_holdings,
                    }
                )
                ever_seen.add(ticker)
    tickers = {row["security_code"] for row in rows if row.get("security_code")}
    prices = _load_price_points(tickers, asof)
    for row in rows:
        include_risk = pd.Timestamp(str(row["event_date"])) >= EARLIEST_ACTUAL_LIVE_START_DATE
        returns, risk_metrics, current_return, current_risk, latest_price_date = _forward_returns(
            prices.get(row["security_code"], []), row["event_date"], include_risk
        )
        row["forward_returns"] = returns
        row["forward_risk_metrics"] = risk_metrics
        row["current_return"] = current_return
        row["current_risk_metrics"] = current_risk
        row["latest_price_date"] = latest_price_date
    return rows


def build_internal_weekly_rank_rows(asof: str) -> list[dict[str, Any]]:
    if not QUANT_SERVICE_DB.exists() or not QUANT_SERVICE_DETAIL_DB.exists():
        return []
    with sqlite3.connect(str(QUANT_SERVICE_DB)) as core_con:
        published = pd.read_sql_query(
            """
            SELECT model_code, published_run_id
            FROM pub_model_current
            WHERE model_code IN ('S2', 'S2_PIT_V01', 'S3', 'S3_CORE2', 'S3_ACCEL_V01', 'S4', 'S5', 'S6')
            ORDER BY model_code
            """,
            core_con,
        )
    if published.empty:
        return []
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(str(QUANT_SERVICE_DETAIL_DB)) as detail_con, sqlite3.connect(str(PRICE_DB)) as price_con:
        names = pd.read_sql_query("SELECT ticker, name FROM instrument_master", price_con)
        names["ticker"] = names["ticker"].astype(str).str.zfill(6)
        name_map = dict(zip(names["ticker"], names["name"]))
        for published_row in published.itertuples(index=False):
            model_code = str(published_row.model_code)
            hist = pd.read_sql_query(
                """
                SELECT date, ticker, rank_no, weight, score
                FROM run_holdings_history
                WHERE run_id = ?
                  AND date <= ?
                  AND ticker IS NOT NULL
                ORDER BY date, rank_no, ticker
                """,
                detail_con,
                params=[str(published_row.published_run_id), asof],
            )
            if hist.empty:
                continue
            hist["date"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m-%d")
            hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
            hist["week_end"] = hist["date"].map(lambda value: _week_end(value, asof))
            hist["rank_no"] = pd.to_numeric(hist["rank_no"], errors="coerce")
            hist["weight"] = pd.to_numeric(hist["weight"], errors="coerce")
            hist["score"] = pd.to_numeric(hist["score"], errors="coerce")
            hist = (
                hist.sort_values(
                    ["week_end", "ticker", "date", "rank_no", "score", "weight"],
                    ascending=[True, True, False, True, False, False],
                    na_position="last",
                )
                .drop_duplicates(["week_end", "ticker"], keep="first")
            )
            latest_snapshot_date = hist["date"].max() if not hist.empty else None
            for row in hist.itertuples(index=False):
                weight = _safe_float(row.weight)
                score = _safe_float(row.score)
                rows.append(
                    {
                        "scope": "internal",
                        "model_code": model_code,
                        "model_key": model_code,
                        "week_end": row.week_end,
                        "snapshot_date": row.date,
                        "security_code": row.ticker,
                        "display_name": name_map.get(row.ticker) or row.ticker,
                        "rank_no": None if pd.isna(row.rank_no) else int(float(row.rank_no)),
                        "score": round(score, 6) if score is not None else None,
                        "score_basis": "model_score" if score is not None else "weight_proxy",
                        "weight": round(weight, 6) if weight is not None else None,
                        "is_latest_snapshot": row.date == latest_snapshot_date,
                    }
                )
    return rows


def build_iseries_weekly_rank_rows(asof: str) -> list[dict[str, Any]]:
    if not ISERIES_DB.exists():
        return []
    with sqlite3.connect(str(ISERIES_DB)) as con:
        hist = pd.read_sql_query(
            """
            SELECT model_code, signal_date, candidate_bucket, ticker, name,
                   portfolio_rank_no, universe_rank_no, universe_rank_score,
                   i_raw_score, display_score, i_signal
            FROM is_candidates_history
            WHERE model_code IN ('I-STOCK-STRONG-RSI-V01')
              AND signal_date <= ?
            ORDER BY signal_date, portfolio_rank_no, ticker
            """,
            con,
            params=[asof],
        )
    if hist.empty:
        return []
    hist["signal_date"] = pd.to_datetime(hist["signal_date"]).dt.strftime("%Y-%m-%d")
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    hist["week_end"] = hist["signal_date"].map(lambda value: _week_end(value, asof))
    rows: list[dict[str, Any]] = []
    for row in hist.itertuples(index=False):
        raw_score = _safe_float(row.i_raw_score)
        rank_score = _safe_float(row.universe_rank_score)
        rows.append(
            {
                "scope": "internal",
                "model_code": str(row.model_code),
                "model_key": str(row.model_code),
                "week_end": row.week_end,
                "snapshot_date": row.signal_date,
                "security_code": row.ticker,
                "display_name": row.name or row.ticker,
                "rank_no": None if pd.isna(row.portfolio_rank_no) else int(float(row.portfolio_rank_no)),
                "score": round(raw_score, 6) if raw_score is not None else None,
                "score_basis": "i_raw_score",
                "weight": None,
                "candidate_bucket": row.candidate_bucket,
                "universe_rank_no": None if pd.isna(row.universe_rank_no) else int(float(row.universe_rank_no)),
                "universe_rank_score": round(rank_score, 6) if rank_score is not None else None,
                "display_score": _safe_float(row.display_score),
                "i_signal": row.i_signal,
                "is_latest_snapshot": row.signal_date == hist["signal_date"].max(),
            }
        )
    return rows


def build_internal_rows(asof: str) -> list[dict[str, Any]]:
    if not QUANT_SERVICE_DB.exists() or not QUANT_SERVICE_DETAIL_DB.exists():
        return []

    with sqlite3.connect(str(QUANT_SERVICE_DB)) as core_con:
        published = pd.read_sql_query(
            """
            SELECT model_code, published_run_id
            FROM pub_model_current
            WHERE model_code IN ('S2', 'S2_PIT_V01', 'S3', 'S3_CORE2', 'S3_ACCEL_V01', 'S4', 'S5', 'S6')
            ORDER BY model_code
            """,
            core_con,
        )
    if published.empty:
        return []

    rows: list[dict[str, Any]] = []
    with sqlite3.connect(str(QUANT_SERVICE_DETAIL_DB)) as detail_con, sqlite3.connect(str(PRICE_DB)) as price_con:
        names = pd.read_sql_query(
            """
            SELECT ticker, name
            FROM instrument_master
            """,
            price_con,
        )
        names["ticker"] = names["ticker"].astype(str).str.zfill(6)
        name_map = dict(zip(names["ticker"], names["name"]))

        for published_row in published.itertuples(index=False):
            model_code = str(published_row.model_code)
            run_id = str(published_row.published_run_id)
            hist = pd.read_sql_query(
                """
                SELECT date, ticker, weight
                FROM run_holdings_history
                WHERE run_id = ?
                  AND ticker IS NOT NULL
                ORDER BY date, ticker
                """,
                detail_con,
                params=[run_id],
            )
            if hist.empty:
                continue
            hist["date"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m-%d")
            hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
            hist["weight"] = pd.to_numeric(hist["weight"], errors="coerce")
            hist = hist.loc[hist["ticker"].str.upper() != "CASH"].copy()
            if hist.empty:
                continue

            normalized_frames: list[pd.DataFrame] = []
            for event_date, frame in hist.groupby("date", sort=True):
                current = frame.copy()
                if current["weight"].isna().all():
                    current["weight"] = 1.0 / max(len(current), 1)
                else:
                    current["weight"] = current["weight"].fillna(0.0)
                current = current.loc[current["weight"] > WEIGHT_EPS].copy()
                normalized_frames.append(current)
            if not normalized_frames:
                continue

            normalized = pd.concat(normalized_frames, ignore_index=True)
            latest_date = max(normalized["date"])
            latest_holdings = set(normalized.loc[normalized["date"] == latest_date, "ticker"])
            seen_before: set[str] = set()
            prev_map: dict[str, float] = {}

            for event_date in sorted(normalized["date"].unique()):
                current = normalized.loc[normalized["date"] == event_date].copy()
                current_map = (
                    current.groupby("ticker", as_index=True)["weight"]
                    .sum()
                    .to_dict()
                )
                for ticker in sorted(current_map):
                    curr_weight = float(current_map[ticker])
                    prev_weight = float(prev_map.get(ticker, 0.0))
                    if ticker not in prev_map:
                        event_type = "re_entry" if ticker in seen_before else "new_entry"
                    elif curr_weight > prev_weight + WEIGHT_EPS:
                        event_type = "weight_increase"
                    else:
                        continue
                    rows.append(
                        {
                            "scope": "internal",
                            "model_code": model_code,
                            "model_key": model_code,
                            "event_type": event_type,
                            "event_date": event_date,
                            "week_end": _week_end(event_date, asof),
                            "security_code": ticker,
                            "display_name": name_map.get(ticker) or ticker,
                            "prev_weight": round(prev_weight, 6),
                            "curr_weight": round(curr_weight, 6),
                            "delta_weight": round(curr_weight - prev_weight, 6),
                            "is_current": ticker in latest_holdings,
                            "source_run_id": run_id,
                        }
                    )
                seen_before.update(current_map.keys())
                prev_map = current_map

    tickers = {row["security_code"] for row in rows if row.get("security_code")}
    prices = _load_price_points(tickers, asof)
    for row in rows:
        include_risk = pd.Timestamp(str(row["event_date"])) >= EARLIEST_ACTUAL_LIVE_START_DATE
        returns, risk_metrics, current_return, current_risk, latest_price_date = _forward_returns(
            prices.get(row["security_code"], []), row["event_date"], include_risk
        )
        row["forward_returns"] = returns
        row["forward_risk_metrics"] = risk_metrics
        row["current_return"] = current_return
        row["current_risk_metrics"] = current_risk
        row["latest_price_date"] = latest_price_date
    return rows


def build_iseries_rows(asof: str) -> list[dict[str, Any]]:
    if not ISERIES_DB.exists():
        return []
    with sqlite3.connect(str(ISERIES_DB)) as con:
        hist = pd.read_sql_query(
            """
            SELECT model_code, signal_date, candidate_bucket, ticker, name,
                   portfolio_rank_no, universe_rank_no, universe_rank_score,
                   i_raw_score, display_score, i_signal
            FROM is_candidates_history
            WHERE model_code IN ('I-STOCK-STRONG-RSI-V01')
              AND signal_date <= ?
            ORDER BY signal_date, portfolio_rank_no, ticker
            """,
            con,
            params=[asof],
        )
        latest = pd.read_sql_query(
            """
            SELECT model_code, asof_date, ticker
            FROM is_candidates_latest
            WHERE model_code IN ('I-STOCK-STRONG-RSI-V01')
              AND asof_date <= ?
            """,
            con,
            params=[asof],
        )
    if hist.empty:
        return []
    hist["signal_date"] = pd.to_datetime(hist["signal_date"]).dt.strftime("%Y-%m-%d")
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    if not latest.empty:
        latest["asof_date"] = pd.to_datetime(latest["asof_date"]).dt.strftime("%Y-%m-%d")
        latest["ticker"] = latest["ticker"].astype(str).str.zfill(6)
        latest_dates = latest.groupby("model_code")["asof_date"].max().to_dict()
        current_tickers = {
            (row.model_code, row.ticker)
            for row in latest.itertuples(index=False)
            if row.asof_date == latest_dates.get(row.model_code)
        }
    else:
        current_tickers = set()

    rows: list[dict[str, Any]] = []
    bucket_rank = {"candidate": 1, "core": 2}
    for model_code, frame in hist.groupby("model_code"):
        first_signal_date = frame["signal_date"].min()
        seen_before = set(frame.loc[frame["signal_date"] == first_signal_date, "ticker"].tolist())
        prev_by_ticker = dict(
            zip(
                frame.loc[frame["signal_date"] == first_signal_date, "ticker"],
                frame.loc[frame["signal_date"] == first_signal_date, "candidate_bucket"],
            )
        )
        for signal_date in sorted(d for d in frame["signal_date"].unique() if d != first_signal_date):
            current = frame.loc[frame["signal_date"] == signal_date].copy()
            current_map = dict(zip(current["ticker"], current["candidate_bucket"]))
            for item in current.itertuples(index=False):
                prev_bucket = prev_by_ticker.get(item.ticker)
                if prev_bucket is None:
                    event_type = "re_entry" if item.ticker in seen_before else "new_entry"
                elif bucket_rank.get(str(item.candidate_bucket), 0) > bucket_rank.get(str(prev_bucket), 0):
                    # I-series is exposed in the internal-model surface, where bucket upgrades
                    # are treated like an increase rather than a T-series-style promotion.
                    event_type = "weight_increase"
                else:
                    continue
                raw_score = _safe_float(item.i_raw_score)
                rank_score = _safe_float(item.universe_rank_score)
                rows.append(
                    {
                        "scope": "internal",
                        "model_code": str(model_code),
                        "model_key": str(model_code),
                        "event_type": event_type,
                        "event_date": signal_date,
                        "week_end": _week_end(signal_date, asof),
                        "security_code": item.ticker,
                        "display_name": item.name or item.ticker,
                        "from_bucket": prev_bucket,
                        "to_bucket": item.candidate_bucket,
                        "rank_no": None if pd.isna(item.portfolio_rank_no) else int(float(item.portfolio_rank_no)),
                        "score": round(raw_score, 6) if raw_score is not None else None,
                        "score_basis": "i_raw_score",
                        "weight": None,
                        "candidate_bucket": item.candidate_bucket,
                        "universe_rank_no": None if pd.isna(item.universe_rank_no) else int(float(item.universe_rank_no)),
                        "universe_rank_score": round(rank_score, 6) if rank_score is not None else None,
                        "display_score": _safe_float(item.display_score),
                        "i_signal": item.i_signal,
                        "is_current": (str(model_code), item.ticker) in current_tickers,
                    }
                )
                seen_before.add(item.ticker)
            prev_by_ticker = current_map
            seen_before.update(current_map.keys())
    tickers = {row["security_code"] for row in rows if row.get("security_code")}
    prices = _load_price_points(tickers, asof)
    for row in rows:
        include_risk = pd.Timestamp(str(row["event_date"])) >= EARLIEST_ACTUAL_LIVE_START_DATE
        returns, risk_metrics, current_return, current_risk, latest_price_date = _forward_returns(
            prices.get(row["security_code"], []), row["event_date"], include_risk
        )
        row["forward_returns"] = returns
        row["forward_risk_metrics"] = risk_metrics
        row["current_return"] = current_return
        row["current_risk_metrics"] = current_risk
        row["latest_price_date"] = latest_price_date
    return rows


def build_internal_model_performance_summary(asof: str) -> list[dict[str, Any]]:
    if not QUANT_SERVICE_DB.exists():
        return []
    summaries: list[dict[str, Any]] = []
    with sqlite3.connect(str(QUANT_SERVICE_DB)) as con:
        published = pd.read_sql_query(
            f"""
            SELECT model_code, display_name, data_asof, latest_holdings_count
            FROM pub_model_current
            WHERE model_code IN ({",".join(["?"] * len(INTERNAL_MODEL_CODES))})
            ORDER BY model_code
            """,
            con,
            params=list(INTERNAL_MODEL_CODES),
        )
        if published.empty:
            return []
        for row in published.itertuples(index=False):
            nav = pd.read_sql_query(
                """
                SELECT date, nav
                FROM pub_model_nav_history
                WHERE model_code = ?
                ORDER BY date
                """,
                con,
                params=[str(row.model_code)],
            )
            summary = _build_nav_summary_payload(
                model_code=str(row.model_code),
                display_name=str(row.display_name),
                asof_date=str(row.data_asof or asof),
                nav_df=nav,
                sample_count=None if pd.isna(row.latest_holdings_count) else int(row.latest_holdings_count),
                metric_basis="published_backtest",
            )
            if summary is not None:
                summaries.append(summary)
    if ISERIES_DB.exists():
        with sqlite3.connect(str(ISERIES_DB)) as con:
            meta = pd.read_sql_query(
                """
                SELECT model_code, display_name, asof_date
                FROM is_meta_models
                WHERE model_code IN ('I-STOCK-STRONG-RSI-V01')
                """,
                con,
            )
            for row in meta.itertuples(index=False):
                nav = pd.read_sql_query(
                    """
                    SELECT date, nav
                    FROM is_backtest_nav
                    WHERE date <= ?
                    ORDER BY date
                    """,
                    con,
                    params=[asof],
                )
                latest_count = con.execute(
                    """
                    SELECT count(*)
                    FROM is_candidates_latest
                    WHERE model_code = ?
                      AND asof_date <= ?
                    """,
                    (str(row.model_code), asof),
                ).fetchone()[0]
                summary = _build_nav_summary_payload(
                    model_code=str(row.model_code),
                    display_name=str(row.display_name),
                    asof_date=str(row.asof_date or asof),
                    nav_df=nav,
                    sample_count=int(latest_count),
                    metric_basis="i_series_shadow_backtest",
                )
                if summary is not None:
                    summaries.append(summary)
    return summaries


def build_tseries_weekly_rank_rows(asof: str) -> list[dict[str, Any]]:
    if not TSERIES_DB.exists():
        return []
    with sqlite3.connect(str(TSERIES_DB)) as con:
        hist = pd.read_sql_query(
            """
            SELECT model_code, signal_date AS event_date, candidate_bucket, ticker, name, stage1_prob, stage2_prob
            FROM ts_candidates_history
            WHERE model_code IN ('T-STOCK-V01', 'T-ETF-V01')
              AND signal_date <= ?
            """,
            con,
            params=[asof],
        )
        latest = pd.read_sql_query(
            """
            SELECT model_code, asof_date AS event_date, candidate_bucket, ticker, name, stage1_prob, stage2_prob
            FROM ts_candidates_latest
            WHERE model_code IN ('T-STOCK-V01', 'T-ETF-V01')
              AND asof_date <= ?
            """,
            con,
            params=[asof],
        )
    snapshots = pd.concat([hist, latest], ignore_index=True)
    if snapshots.empty:
        return []
    snapshots["event_date"] = pd.to_datetime(snapshots["event_date"]).dt.strftime("%Y-%m-%d")
    snapshots["ticker"] = snapshots["ticker"].astype(str).str.zfill(6)
    snapshots["candidate_bucket"] = snapshots["candidate_bucket"].astype(str)
    snapshots["bucket_rank"] = snapshots["candidate_bucket"].map(T_BUCKET_RANK).fillna(0)
    snapshots = (
        snapshots.sort_values(
            ["model_code", "event_date", "ticker", "bucket_rank", "stage2_prob", "stage1_prob"],
            ascending=[True, True, True, False, False, False],
            na_position="last",
        )
        .drop_duplicates(["model_code", "event_date", "ticker"], keep="first")
    )
    if latest.empty:
        return []
    latest["event_date"] = pd.to_datetime(latest["event_date"]).dt.strftime("%Y-%m-%d")
    latest_dates = latest.groupby("model_code")["event_date"].max().to_dict()
    rows: list[dict[str, Any]] = []
    for model_code, frame in snapshots.groupby("model_code"):
        frame["week_end"] = frame["event_date"].map(lambda value: _week_end(value, asof))
        frame = frame.sort_values(
            ["week_end", "ticker", "bucket_rank", "stage2_prob", "stage1_prob", "event_date"],
            ascending=[True, True, False, False, False, False],
            na_position="last",
        )
        frame = frame.drop_duplicates(["week_end", "ticker"], keep="first")
        latest_snapshot_date = frame["event_date"].max() if not frame.empty else None
        for week_end, week_frame in frame.groupby("week_end", sort=True):
            week_frame = week_frame.sort_values(
                ["bucket_rank", "stage2_prob", "stage1_prob", "ticker"],
                ascending=[False, False, False, True],
                na_position="last",
            )
            for rank_no, item in enumerate(week_frame.itertuples(index=False), start=1):
                stage1_prob = _safe_float(item.stage1_prob)
                stage2_prob = _safe_float(item.stage2_prob)
                score = stage2_prob if stage2_prob is not None else stage1_prob
                rows.append(
                    {
                        "scope": "tseries",
                        "model_code": model_code,
                        "model_key": model_code,
                        "week_end": week_end,
                        "snapshot_date": item.event_date,
                        "security_code": item.ticker,
                        "display_name": item.name or item.ticker,
                        "rank_no": rank_no,
                        "score": round(score, 6) if score is not None else None,
                        "score_basis": "stage2_prob" if stage2_prob is not None else "stage1_prob",
                        "candidate_bucket": item.candidate_bucket,
                        "weight": None,
                        "stage1_prob": round(stage1_prob, 6) if stage1_prob is not None else None,
                        "stage2_prob": round(stage2_prob, 6) if stage2_prob is not None else None,
                        "is_latest_snapshot": item.event_date == latest_snapshot_date,
                    }
                )
    return rows


def build_tseries_rows(asof: str) -> list[dict[str, Any]]:
    if not TSERIES_DB.exists():
        return []
    with sqlite3.connect(str(TSERIES_DB)) as con:
        hist = pd.read_sql_query(
            """
            SELECT model_code, signal_date AS event_date, candidate_bucket, ticker, name, stage1_prob, stage2_prob
            FROM ts_candidates_history
            WHERE model_code IN ('T-STOCK-V01', 'T-ETF-V01')
              AND signal_date <= ?
            """,
            con,
            params=[asof],
        )
        latest = pd.read_sql_query(
            """
            SELECT model_code, asof_date AS event_date, candidate_bucket, ticker, name, stage1_prob, stage2_prob
            FROM ts_candidates_latest
            WHERE model_code IN ('T-STOCK-V01', 'T-ETF-V01')
              AND asof_date <= ?
            """,
            con,
            params=[asof],
        )
    snapshots = pd.concat([hist, latest], ignore_index=True)
    if snapshots.empty:
        return []
    snapshots["event_date"] = pd.to_datetime(snapshots["event_date"]).dt.strftime("%Y-%m-%d")
    snapshots["ticker"] = snapshots["ticker"].astype(str).str.zfill(6)
    snapshots["candidate_bucket"] = snapshots["candidate_bucket"].astype(str)
    snapshots["bucket_rank"] = snapshots["candidate_bucket"].map(T_BUCKET_RANK).fillna(0)
    snapshots = (
        snapshots.sort_values(
            ["model_code", "event_date", "ticker", "bucket_rank", "stage2_prob", "stage1_prob"],
            ascending=[True, True, True, False, False, False],
            na_position="last",
        )
        .drop_duplicates(["model_code", "event_date", "ticker"], keep="first")
    )
    current_tickers: set[tuple[str, str]] = set()
    if not latest.empty:
        latest["event_date"] = pd.to_datetime(latest["event_date"]).dt.strftime("%Y-%m-%d")
        latest["ticker"] = latest["ticker"].astype(str).str.zfill(6)
        latest_dates = latest.groupby("model_code")["event_date"].max().to_dict()
        current_tickers = {
            (row.model_code, row.ticker)
            for row in latest.itertuples()
            if row.event_date == latest_dates.get(row.model_code)
        }
    rows: list[dict[str, Any]] = []
    for model_code, frame in snapshots.groupby("model_code"):
        frame = frame.sort_values(["event_date", "ticker"])
        seen_before: set[str] = set()
        prev_by_ticker: dict[str, str] = {}
        first_signal_date = frame["event_date"].min()
        baseline = frame.loc[frame["event_date"] == first_signal_date, "ticker"].tolist()
        seen_before.update(baseline)
        prev_signal_frame = frame.loc[frame["event_date"] == first_signal_date, ["ticker", "candidate_bucket"]]
        prev_by_ticker = dict(zip(prev_signal_frame["ticker"], prev_signal_frame["candidate_bucket"]))
        for signal_date in sorted(d for d in frame["event_date"].unique() if d != first_signal_date):
            current = frame.loc[frame["event_date"] == signal_date].copy()
            current_map = dict(zip(current["ticker"], current["candidate_bucket"]))
            for ticker, bucket in current_map.items():
                prev_bucket = prev_by_ticker.get(ticker)
                if prev_bucket is None:
                    event_type = "re_entry" if ticker in seen_before else "new_entry"
                elif T_BUCKET_RANK.get(bucket, 0) > T_BUCKET_RANK.get(prev_bucket, 0):
                    event_type = "promotion"
                else:
                    continue
                source_row = current.loc[current["ticker"] == ticker].iloc[0]
                rows.append(
                    {
                        "scope": "tseries",
                        "model_code": model_code,
                        "model_key": model_code,
                        "event_type": event_type,
                        "event_date": signal_date,
                        "week_end": _week_end(signal_date, asof),
                        "security_code": ticker,
                        "display_name": source_row["name"] or ticker,
                        "from_bucket": prev_bucket,
                        "to_bucket": bucket,
                        "stage1_prob": None if pd.isna(source_row["stage1_prob"]) else round(float(source_row["stage1_prob"]), 6),
                        "stage2_prob": None if pd.isna(source_row["stage2_prob"]) else round(float(source_row["stage2_prob"]), 6),
                        "is_current": (model_code, ticker) in current_tickers,
                    }
                )
                seen_before.add(ticker)
            prev_by_ticker = current_map
            seen_before.update(current_map.keys())
    tickers = {row["security_code"] for row in rows if row.get("security_code")}
    prices = _load_price_points(tickers, asof)
    for row in rows:
        include_risk = pd.Timestamp(str(row["event_date"])) >= EARLIEST_ACTUAL_LIVE_START_DATE
        returns, risk_metrics, current_return, current_risk, latest_price_date = _forward_returns(
            prices.get(row["security_code"], []), row["event_date"], include_risk
        )
        row["forward_returns"] = returns
        row["forward_risk_metrics"] = risk_metrics
        row["current_return"] = current_return
        row["current_risk_metrics"] = current_risk
        row["latest_price_date"] = latest_price_date
    return rows


def _load_price_wide(tickers: set[str], asof: str) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    with sqlite3.connect(str(PRICE_DB)) as con:
        px = pd.read_sql_query(
            f"""
            SELECT ticker, date, close
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date <= ?
              AND close IS NOT NULL
            ORDER BY date, ticker
            """,
            con,
            params=[*sorted(tickers), asof],
            parse_dates=["date"],
        )
    if px.empty:
        return pd.DataFrame()
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px = px.dropna(subset=["close"])
    return px.pivot(index="date", columns="ticker", values="close").sort_index().ffill()


def _simulate_ranked_proxy_nav(
    ranking_rows: list[dict[str, Any]],
    *,
    asof: str,
    top_n: int = 20,
) -> tuple[pd.DataFrame, int]:
    if not ranking_rows:
        return pd.DataFrame(columns=["date", "nav"]), 0
    frame = pd.DataFrame(ranking_rows)
    if frame.empty:
        return pd.DataFrame(columns=["date", "nav"]), 0
    frame["snapshot_date"] = pd.to_datetime(frame["snapshot_date"], errors="coerce")
    frame["rank_no"] = pd.to_numeric(frame["rank_no"], errors="coerce")
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    frame = frame.dropna(subset=["snapshot_date", "rank_no"])
    if frame.empty:
        return pd.DataFrame(columns=["date", "nav"]), 0
    tickers = {str(t).zfill(6) for t in frame["security_code"].astype(str)}
    price_wide = _load_price_wide(tickers, asof)
    if price_wide.empty:
        return pd.DataFrame(columns=["date", "nav"]), 0
    returns = price_wide.pct_change().fillna(0.0)
    snapshots: list[tuple[pd.Timestamp, list[str]]] = []
    latest_count = 0
    for snapshot_date, snap in frame.groupby("snapshot_date", sort=True):
        snap = snap.sort_values(["rank_no", "score", "security_code"], ascending=[True, False, True], na_position="last")
        chosen = [str(code).zfill(6) for code in snap["security_code"].tolist()[:top_n]]
        chosen = [ticker for ticker in chosen if ticker in price_wide.columns]
        if not chosen:
            continue
        snapshots.append((pd.Timestamp(snapshot_date), chosen))
        latest_count = len(chosen)
    if not snapshots:
        return pd.DataFrame(columns=["date", "nav"]), 0
    nav = 1.0
    rows = [{"date": snapshots[0][0], "nav": nav}]
    for idx, (start, chosen) in enumerate(snapshots):
        end = snapshots[idx + 1][0] if idx + 1 < len(snapshots) else price_wide.index.max()
        period = returns.loc[(returns.index > start) & (returns.index <= end), chosen]
        if period.empty:
            continue
        weight = 1.0 / float(len(chosen))
        for day, day_ret in period.iterrows():
            nav *= 1.0 + float(day_ret.fillna(0.0).mean() if len(chosen) > 0 else 0.0)
            rows.append({"date": day, "nav": nav})
    return pd.DataFrame(rows), latest_count


def build_tseries_model_performance_summary(asof: str, ranking_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not TSERIES_DB.exists():
        return []
    display_names: dict[str, str] = {}
    with sqlite3.connect(str(TSERIES_DB)) as con:
        meta = pd.read_sql_query(
            f"""
            SELECT model_code, display_name
            FROM ts_meta_models
            WHERE model_code IN ({",".join(["?"] * len(TSERIES_MODEL_CODES))})
            ORDER BY model_code
            """,
            con,
            params=list(TSERIES_MODEL_CODES),
        )
        display_names = {str(row.model_code): str(row.display_name) for row in meta.itertuples(index=False)}
    summaries: list[dict[str, Any]] = []
    for model_code in TSERIES_MODEL_CODES:
        model_rows = [row for row in ranking_rows if row.get("model_code") == model_code]
        nav_df, latest_count = _simulate_ranked_proxy_nav(model_rows, asof=asof, top_n=20)
        summary = _build_nav_summary_payload(
            model_code=model_code,
            display_name=display_names.get(model_code, model_code),
            asof_date=asof,
            nav_df=nav_df,
            sample_count=latest_count,
            metric_basis="weekly_top20_equal_weight_proxy",
        )
        if summary is not None:
            summaries.append(summary)
    return summaries


def build_weekly_rankings(asof: str) -> dict[str, Any]:
    user_rows = build_user_weekly_rank_rows(asof)
    internal_rows = build_internal_weekly_rank_rows(asof) + build_iseries_weekly_rank_rows(asof)
    tseries_rows = build_tseries_weekly_rank_rows(asof)
    return {
        "summary": {
            "user_models": _ranking_summary_rows(user_rows, "service_profile"),
            "internal_models": _ranking_summary_rows(internal_rows, "model_code"),
            "tseries_models": _ranking_summary_rows(tseries_rows, "model_code"),
        },
        "user_models": user_rows,
        "internal_models": internal_rows,
        "tseries_models": tseries_rows,
    }


def build_payload(asof: str) -> dict[str, Any]:
    weekly_rankings = build_weekly_rankings(asof)
    user_rows = _enrich_rows_with_weekly_rank(build_user_rows(asof), weekly_rankings["user_models"], "service_profile")
    internal_rows = _enrich_rows_with_weekly_rank(build_internal_rows(asof) + build_iseries_rows(asof), weekly_rankings["internal_models"], "model_code")
    tseries_rows = _enrich_rows_with_weekly_rank(build_tseries_rows(asof), weekly_rankings["tseries_models"], "model_code")
    model_performance_summary = {
        "internal_models": build_internal_model_performance_summary(asof),
        "tseries_models": build_tseries_model_performance_summary(asof, weekly_rankings["tseries_models"]),
    }
    actual_live_performance_summary = build_actual_live_performance_summary(user_rows, internal_rows, tseries_rows)
    internal_latest_week_end = max((row["week_end"] for row in internal_rows), default=None)
    internal_latest_event_date = max((row["event_date"] for row in internal_rows), default=None)
    tseries_latest = {
        row["model_code"]: max(
            (item["event_date"] for item in tseries_rows if item["model_code"] == row["model_code"]),
            default=None,
        )
        for row in [{"model_code": "T-STOCK-V01"}, {"model_code": "T-ETF-V01"}]
    }
    return {
        "source_name": "handoff:admin_new_entry_tracker",
        "schema_version": "v2",
        "visibility": "admin_only",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "freshness": {
            "user_latest_asof": max((row["event_date"] for row in user_rows), default=None),
            "internal_latest_event_date": internal_latest_event_date,
            "internal_latest_week_end": internal_latest_week_end,
            "tstock_latest_event_date": tseries_latest.get("T-STOCK-V01"),
            "tetf_latest_event_date": tseries_latest.get("T-ETF-V01"),
        },
        "summary": {
            "user_models": _summary_rows(user_rows, "service_profile"),
            "internal_models": _summary_rows(internal_rows, "model_code"),
            "tseries_models": _summary_rows(tseries_rows, "model_code"),
        },
        "model_performance_summary": model_performance_summary,
        "actual_live_performance_summary": actual_live_performance_summary,
        "weekly_rankings": weekly_rankings,
        "user_models": user_rows,
        "internal_models": internal_rows,
        "tseries_models": tseries_rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build admin-only new entry tracker payload.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    payload = build_payload(str(args.asof))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = OUT_PATH.with_name(f"{OUT_PATH.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(OUT_PATH)
    print(
        json.dumps(
            {
                "out_path": str(OUT_PATH),
                "as_of_date": payload["as_of_date"],
                "user_rows": len(payload["user_models"]),
                "internal_rows": len(payload["internal_models"]),
                "tseries_rows": len(payload["tseries_models"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
