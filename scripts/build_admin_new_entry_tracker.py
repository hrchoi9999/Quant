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
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"
PRICE_DB = ROOT / r"data\db\price.db"
OUT_DIR = ROOT / r"service_platform\web\admin_data\current"
OUT_PATH = OUT_DIR / "admin_new_entry_tracker.json"

USER_MODEL_META = {
    "stable": {"user_model_name": "안정형", "mapped_internal_models": ["S6"]},
    "balanced": {"user_model_name": "균형형", "mapped_internal_models": ["S2", "S5"]},
    "growth": {"user_model_name": "성장형", "mapped_internal_models": ["S3", "S4"]},
}
T_BUCKET_RANK = {"observe": 1, "near": 2, "confirmed": 3}
RETURN_HORIZONS = (("1w", 5), ("2w", 10), ("1m", 21), ("3m", 63))
WEIGHT_EPS = 1e-8


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


def _week_end(date_str: str) -> str:
    dt = pd.Timestamp(date_str)
    shift = (4 - dt.weekday()) % 7
    return (dt + pd.Timedelta(days=shift)).strftime("%Y-%m-%d")


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


def _forward_returns(price_points: list[PricePoint], event_date: str) -> tuple[dict[str, Any], float | None, str | None]:
    if not price_points:
        return {label: None for label, _ in RETURN_HORIZONS}, None, None
    dates = [point.date for point in price_points]
    closes = [point.close for point in price_points]
    event_ts = pd.Timestamp(event_date)
    start_idx = next((idx for idx, dt in enumerate(dates) if dt >= event_ts), None)
    if start_idx is None:
        return {label: None for label, _ in RETURN_HORIZONS}, None, None
    start_price = closes[start_idx]
    metrics: dict[str, Any] = {}
    for label, offset in RETURN_HORIZONS:
        target_idx = start_idx + offset
        if target_idx >= len(closes):
            metrics[label] = None
        else:
            metrics[label] = round(closes[target_idx] / start_price - 1.0, 6)
    latest_idx = len(closes) - 1
    current_return = round(closes[latest_idx] / start_price - 1.0, 6)
    latest_price_date = dates[latest_idx].strftime("%Y-%m-%d")
    return metrics, current_return, latest_price_date


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
                        "week_end": _week_end(curr["asof_date"]),
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
        returns, current_return, latest_price_date = _forward_returns(prices.get(row["security_code"], []), row["event_date"])
        row["forward_returns"] = returns
        row["current_return"] = current_return
        row["latest_price_date"] = latest_price_date
    return rows


def build_internal_rows(asof: str) -> list[dict[str, Any]]:
    if not SERVICE_ANALYTICS_DB.exists():
        return []
    with sqlite3.connect(str(SERVICE_ANALYTICS_DB)) as con:
        df = pd.read_sql_query(
            """
            SELECT model_code, week_end, change_type, ticker, name, delta_weight
            FROM analytics_model_change_log
            WHERE change_type IN ('new', 'increase')
            ORDER BY model_code, week_end, ticker
            """,
            con,
        )
    if df.empty:
        return []
    df["week_end"] = pd.to_datetime(df["week_end"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    latest_events = (
        df.groupby(["model_code", "ticker"], as_index=False)["week_end"]
        .max()
        .rename(columns={"week_end": "latest_event_date"})
    )
    latest_event_map = {(row.model_code, row.ticker): row.latest_event_date for row in latest_events.itertuples()}
    seen_new: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for row in df.itertuples():
        if row.change_type == "increase":
            event_type = "weight_increase"
        else:
            event_type = "re_entry" if (row.model_code, row.ticker) in seen_new else "new_entry"
            seen_new.add((row.model_code, row.ticker))
        rows.append(
            {
                "scope": "internal",
                "model_code": row.model_code,
                "model_key": row.model_code,
                "event_type": event_type,
                "event_date": row.week_end,
                "week_end": row.week_end,
                "security_code": row.ticker,
                "display_name": row.name or row.ticker,
                "delta_weight": round(float(row.delta_weight or 0.0), 6),
                "is_current": latest_event_map.get((row.model_code, row.ticker)) == row.week_end,
            }
        )
    tickers = {row["security_code"] for row in rows if row.get("security_code")}
    prices = _load_price_points(tickers, asof)
    for row in rows:
        returns, current_return, latest_price_date = _forward_returns(prices.get(row["security_code"], []), row["event_date"])
        row["forward_returns"] = returns
        row["current_return"] = current_return
        row["latest_price_date"] = latest_price_date
    return rows


def build_tseries_rows(asof: str) -> list[dict[str, Any]]:
    if not TSERIES_DB.exists():
        return []
    with sqlite3.connect(str(TSERIES_DB)) as con:
        hist = pd.read_sql_query(
            """
            SELECT model_code, signal_date, candidate_bucket, ticker, name, stage1_prob, stage2_prob
            FROM ts_candidates_history
            WHERE model_code IN ('T-STOCK-V01', 'T-ETF-V01')
            """,
            con,
        )
        latest = pd.read_sql_query(
            """
            SELECT model_code, asof_date, ticker
            FROM ts_candidates_latest
            WHERE model_code IN ('T-STOCK-V01', 'T-ETF-V01')
            """,
            con,
        )
    if hist.empty:
        return []
    hist["signal_date"] = pd.to_datetime(hist["signal_date"]).dt.strftime("%Y-%m-%d")
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    hist["bucket_rank"] = hist["candidate_bucket"].map(T_BUCKET_RANK).fillna(0)
    hist = (
        hist.sort_values(["model_code", "signal_date", "ticker", "bucket_rank", "stage2_prob", "stage1_prob"], ascending=[True, True, True, False, False, False], na_position="last")
        .drop_duplicates(["model_code", "signal_date", "ticker"], keep="first")
    )
    current_tickers = {(row.model_code, row.ticker) for row in latest.itertuples()}
    rows: list[dict[str, Any]] = []
    for model_code, frame in hist.groupby("model_code"):
        frame = frame.sort_values(["signal_date", "ticker"])
        seen_before: set[str] = set()
        prev_by_ticker: dict[str, str] = {}
        first_signal_date = frame["signal_date"].min()
        baseline = frame.loc[frame["signal_date"] == first_signal_date, "ticker"].tolist()
        seen_before.update(baseline)
        prev_signal_frame = frame.loc[frame["signal_date"] == first_signal_date, ["ticker", "candidate_bucket"]]
        prev_by_ticker = dict(zip(prev_signal_frame["ticker"], prev_signal_frame["candidate_bucket"]))
        for signal_date in sorted(d for d in frame["signal_date"].unique() if d != first_signal_date):
            current = frame.loc[frame["signal_date"] == signal_date].copy()
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
                        "week_end": _week_end(signal_date),
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
        returns, current_return, latest_price_date = _forward_returns(prices.get(row["security_code"], []), row["event_date"])
        row["forward_returns"] = returns
        row["current_return"] = current_return
        row["latest_price_date"] = latest_price_date
    return rows


def build_payload(asof: str) -> dict[str, Any]:
    user_rows = build_user_rows(asof)
    internal_rows = build_internal_rows(asof)
    tseries_rows = build_tseries_rows(asof)
    internal_latest_week_end = max((row["week_end"] for row in internal_rows), default=None)
    tseries_latest = {
        row["model_code"]: max(
            (item["event_date"] for item in tseries_rows if item["model_code"] == row["model_code"]),
            default=None,
        )
        for row in [{"model_code": "T-STOCK-V01"}, {"model_code": "T-ETF-V01"}]
    }
    return {
        "source_name": "handoff:admin_new_entry_tracker",
        "schema_version": "v1",
        "visibility": "admin_only",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "freshness": {
            "user_latest_asof": max((row["event_date"] for row in user_rows), default=None),
            "internal_latest_week_end": internal_latest_week_end,
            "tstock_latest_event_date": tseries_latest.get("T-STOCK-V01"),
            "tetf_latest_event_date": tseries_latest.get("T-ETF-V01"),
        },
        "summary": {
            "user_models": _summary_rows(user_rows, "service_profile"),
            "internal_models": _summary_rows(internal_rows, "model_code"),
            "tseries_models": _summary_rows(tseries_rows, "model_code"),
        },
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
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
