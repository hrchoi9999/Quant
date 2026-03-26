# build_s3_price_features_daily_v2.py ver 2026-03-05_001
import argparse
import sqlite3
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")

PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"

S3_DB_DIR = PROJECT_ROOT / r"data\db_s3"
FEATURES_DB = S3_DB_DIR / "features_s3.db"

TABLE_PRICE = "s3_price_features_daily"  # S3 전용

DDL = f"""
DROP TABLE IF EXISTS {TABLE_PRICE};

CREATE TABLE {TABLE_PRICE} (
  ticker TEXT NOT NULL,
  date   TEXT NOT NULL,

  close      REAL,
  volume     REAL,
  value_won  REAL,

  adv20      REAL,
  adv60      REAL,
  vol_ratio_20 REAL,

  mom20      REAL,
  breakout60 INTEGER,

  ma60       REAL,
  ma120      REAL,
  ma60_slope REAL,
  ma120_slope REAL,

  updated_at TEXT DEFAULT (datetime('now')),

  PRIMARY KEY (ticker, date)
);

CREATE INDEX idx_{TABLE_PRICE}_date ON {TABLE_PRICE} (date);
CREATE INDEX idx_{TABLE_PRICE}_ticker_date ON {TABLE_PRICE} (ticker, date);
"""


def _ensure_db() -> None:
    S3_DB_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(FEATURES_DB))
    try:
        con.executescript(DDL)
        con.commit()
    finally:
        con.close()


def _read_universe_tickers() -> List[str]:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    return df["ticker"].astype(str).str.zfill(6).tolist()


def _fetch_prices(con: sqlite3.Connection, tickers: List[str], end_date: str) -> pd.DataFrame:
    placeholders = ",".join(["?"] * len(tickers))
    q = f"""
    SELECT ticker, date, close, volume
    FROM prices_daily
    WHERE ticker IN ({placeholders})
      AND date <= ?
    ORDER BY ticker, date
    """
    params = tickers + [end_date]
    return pd.read_sql_query(q, con, params=params)


def build(end_date: str, lookback_days: int = 260) -> None:
    _ensure_db()

    tickers = _read_universe_tickers()

    con_p = sqlite3.connect(str(PRICE_DB))
    try:
        px = _fetch_prices(con_p, tickers, end_date=end_date)
    finally:
        con_p.close()

    if px.empty:
        raise RuntimeError("No price rows fetched. Check price.db and end_date.")

    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["date"] = px["date"].astype(str)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px["volume"] = pd.to_numeric(px["volume"], errors="coerce")
    px["value_won"] = px["close"] * px["volume"]

    def calc_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()

        g["adv20"] = g["value_won"].rolling(20, min_periods=10).mean()
        g["adv60"] = g["value_won"].rolling(60, min_periods=30).mean()
        g["vol_ratio_20"] = g["value_won"] / g["adv20"]

        g["mom20"] = g["close"] / g["close"].shift(20) - 1.0
        roll_max_60 = g["close"].rolling(60, min_periods=30).max()
        g["breakout60"] = (g["close"] >= roll_max_60).astype(int)

        g["ma60"] = g["close"].rolling(60, min_periods=30).mean()
        g["ma120"] = g["close"].rolling(120, min_periods=60).mean()
        g["ma60_slope"] = (g["ma60"] - g["ma60"].shift(5)) / 5.0
        g["ma120_slope"] = (g["ma120"] - g["ma120"].shift(5)) / 5.0

        return g

    feat = px.groupby("ticker", group_keys=False).apply(calc_group)

    end_ts = pd.to_datetime(end_date)
    feat["_dt"] = pd.to_datetime(feat["date"], errors="coerce")
    feat = feat[feat["_dt"] >= (end_ts - pd.Timedelta(days=lookback_days * 2))].copy()
    feat.drop(columns=["_dt"], inplace=True)

    out_cols = [
        "ticker", "date", "close", "volume", "value_won",
        "adv20", "adv60", "vol_ratio_20", "mom20", "breakout60",
        "ma60", "ma120", "ma60_slope", "ma120_slope",
    ]
    feat_out = feat[out_cols].copy()

    con_f = sqlite3.connect(str(FEATURES_DB))
    try:
        feat_out.to_sql(TABLE_PRICE, con_f, if_exists="append", index=False)
        con_f.commit()
    finally:
        con_f.close()

    print(f"[OK] price_features_v2: inserted={len(feat_out):,} -> {FEATURES_DB}::{TABLE_PRICE} (end={end_date})")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", required=True)
    ap.add_argument("--lookback-days", type=int, default=260)
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    build(end_date=args.end, lookback_days=args.lookback_days)