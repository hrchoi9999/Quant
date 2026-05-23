from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.krx_openapi import fetch_etf_daily, iter_bas_dd, load_api_key

DEFAULT_DB = ROOT / "data" / "db" / "price.db"
METRIC_COLUMNS = [
    "ticker",
    "date",
    "close",
    "nav",
    "premium_discount",
    "premium_discount_abs",
    "premium_discount_quality_flag",
    "aum",
    "aum_log",
    "mcap",
    "list_shares",
    "underlying_index_name",
    "underlying_index_level",
    "underlying_index_change",
    "underlying_index_return_pct",
    "etf_return_pct",
    "daily_tracking_gap_pct",
    "daily_tracking_gap_abs_pct",
]


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _read_tickers(path: str, ticker_col: str) -> set[str] | None:
    if not path:
        return None
    df = pd.read_csv(Path(path), dtype={ticker_col: "string"})
    if ticker_col not in df.columns:
        raise ValueError(f"missing ticker column {ticker_col}: {path}")
    return {
        str(value).strip().replace(".0", "").zfill(6)
        for value in df[ticker_col].dropna().tolist()
        if str(value).strip()
    }


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_daily_metrics (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL,
            nav REAL,
            premium_discount REAL,
            premium_discount_abs REAL,
            premium_discount_quality_flag TEXT,
            aum REAL,
            aum_log REAL,
            mcap REAL,
            list_shares REAL,
            underlying_index_name TEXT,
            underlying_index_level REAL,
            underlying_index_change REAL,
            underlying_index_return_pct REAL,
            etf_return_pct REAL,
            daily_tracking_gap_pct REAL,
            daily_tracking_gap_abs_pct REAL,
            source TEXT,
            updated_at TEXT,
            PRIMARY KEY (ticker, date)
        );
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_etf_daily_metrics_date ON etf_daily_metrics(date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_etf_daily_metrics_index ON etf_daily_metrics(underlying_index_name)")
    existing = {row[1] for row in con.execute("PRAGMA table_info(etf_daily_metrics)").fetchall()}
    migrations = {
        "premium_discount_abs": "ALTER TABLE etf_daily_metrics ADD COLUMN premium_discount_abs REAL",
        "premium_discount_quality_flag": "ALTER TABLE etf_daily_metrics ADD COLUMN premium_discount_quality_flag TEXT",
        "aum_log": "ALTER TABLE etf_daily_metrics ADD COLUMN aum_log REAL",
        "daily_tracking_gap_pct": "ALTER TABLE etf_daily_metrics ADD COLUMN daily_tracking_gap_pct REAL",
        "daily_tracking_gap_abs_pct": "ALTER TABLE etf_daily_metrics ADD COLUMN daily_tracking_gap_abs_pct REAL",
    }
    for col, ddl in migrations.items():
        if col not in existing:
            con.execute(ddl)


def _normalize_frame(frame: pd.DataFrame, tickers: set[str] | None) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=METRIC_COLUMNS)
    out = frame.copy()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    if tickers is not None:
        out = out[out["ticker"].isin(tickers)].copy()
    for col in [
        "close",
        "nav",
        "premium_discount",
        "premium_discount_abs",
        "aum",
        "aum_log",
        "mcap",
        "list_shares",
        "underlying_index_level",
        "underlying_index_change",
        "underlying_index_return_pct",
        "etf_return_pct",
        "daily_tracking_gap_pct",
        "daily_tracking_gap_abs_pct",
    ]:
        if col not in out.columns:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["premium_discount_abs"] = out["premium_discount"].abs()
    out["premium_discount_quality_flag"] = np.select(
        [
            out["premium_discount"].isna(),
            out["premium_discount_abs"] >= 0.10,
            out["premium_discount_abs"] >= 0.03,
            out["premium_discount_abs"] >= 0.01,
        ],
        ["missing", "extreme", "wide", "watch"],
        default="normal",
    )
    out["aum_log"] = np.log1p(out["aum"].clip(lower=0))
    out["daily_tracking_gap_pct"] = out["etf_return_pct"] - out["underlying_index_return_pct"]
    out["daily_tracking_gap_abs_pct"] = out["daily_tracking_gap_pct"].abs()
    if "underlying_index_name" not in out.columns:
        out["underlying_index_name"] = ""
    out["underlying_index_name"] = out["underlying_index_name"].fillna("").astype(str)
    return out[METRIC_COLUMNS].drop_duplicates(["ticker", "date"])


def upsert_metrics(db_path: Path, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    now = _utcnow_iso()
    rows: list[tuple[Any, ...]] = []
    for r in frame.itertuples(index=False):
        rows.append(
            (
                str(r.ticker),
                str(r.date),
                None if pd.isna(r.close) else float(r.close),
                None if pd.isna(r.nav) else float(r.nav),
                None if pd.isna(r.premium_discount) else float(r.premium_discount),
                None if pd.isna(r.premium_discount_abs) else float(r.premium_discount_abs),
                str(r.premium_discount_quality_flag or ""),
                None if pd.isna(r.aum) else float(r.aum),
                None if pd.isna(r.aum_log) else float(r.aum_log),
                None if pd.isna(r.mcap) else float(r.mcap),
                None if pd.isna(r.list_shares) else float(r.list_shares),
                str(r.underlying_index_name or ""),
                None if pd.isna(r.underlying_index_level) else float(r.underlying_index_level),
                None if pd.isna(r.underlying_index_change) else float(r.underlying_index_change),
                None if pd.isna(r.underlying_index_return_pct) else float(r.underlying_index_return_pct),
                None if pd.isna(r.etf_return_pct) else float(r.etf_return_pct),
                None if pd.isna(r.daily_tracking_gap_pct) else float(r.daily_tracking_gap_pct),
                None if pd.isna(r.daily_tracking_gap_abs_pct) else float(r.daily_tracking_gap_abs_pct),
                "krx_openapi_etf_bydd_trd",
                now,
            )
        )
    with sqlite3.connect(str(db_path)) as con:
        _ensure_schema(con)
        con.executemany(
            """
            INSERT INTO etf_daily_metrics (
                ticker, date, close, nav, premium_discount, premium_discount_abs, premium_discount_quality_flag,
                aum, aum_log, mcap, list_shares,
                underlying_index_name, underlying_index_level, underlying_index_change,
                underlying_index_return_pct, etf_return_pct, daily_tracking_gap_pct, daily_tracking_gap_abs_pct,
                source, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                close=excluded.close,
                nav=excluded.nav,
                premium_discount=excluded.premium_discount,
                premium_discount_abs=excluded.premium_discount_abs,
                premium_discount_quality_flag=excluded.premium_discount_quality_flag,
                aum=excluded.aum,
                aum_log=excluded.aum_log,
                mcap=excluded.mcap,
                list_shares=excluded.list_shares,
                underlying_index_name=excluded.underlying_index_name,
                underlying_index_level=excluded.underlying_index_level,
                underlying_index_change=excluded.underlying_index_change,
                underlying_index_return_pct=excluded.underlying_index_return_pct,
                etf_return_pct=excluded.etf_return_pct,
                daily_tracking_gap_pct=excluded.daily_tracking_gap_pct,
                daily_tracking_gap_abs_pct=excluded.daily_tracking_gap_abs_pct,
                source=excluded.source,
                updated_at=excluded.updated_at;
            """,
            rows,
        )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch KRX ETF daily NAV/AUM/index metrics into price.db.")
    parser.add_argument("--start", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--api-key-file", default=str(ROOT / "config" / "KRX_API_Key.json"))
    parser.add_argument("--tickers-file", default="", help="Optional CSV to restrict ETF tickers")
    parser.add_argument("--ticker-col", default="ticker")
    parser.add_argument("--sleep", type=float, default=0.1)
    args = parser.parse_args()

    db_path = Path(args.db)
    api_key = load_api_key(args.api_key_file)
    tickers = _read_tickers(args.tickers_file, args.ticker_col)
    total = 0
    for bas_dd in iter_bas_dd(args.start, args.end):
        frame = fetch_etf_daily(bas_dd, api_key)
        norm = _normalize_frame(frame, tickers)
        count = upsert_metrics(db_path, norm)
        total += count
        print(f"[INFO] basDd={bas_dd} fetched={len(frame)} upserted={count}")
        if args.sleep:
            time.sleep(args.sleep)
    print(f"[DONE] upserted_rows={total} db={db_path}")


if __name__ == "__main__":
    main()
