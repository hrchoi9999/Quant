from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
FEATURES_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
TABLE_PRICE = "s3_price_features_daily"

DDL = f"""
DROP TABLE IF EXISTS {TABLE_PRICE};
CREATE TABLE {TABLE_PRICE} (
  ticker TEXT NOT NULL,
  date   TEXT NOT NULL,
  close REAL,
  volume REAL,
  value_won REAL,
  adv20 REAL,
  adv60 REAL,
  vol_ratio_20 REAL,
  mom20 REAL,
  breakout60 INTEGER,
  ma60 REAL,
  ma120 REAL,
  ma60_slope REAL,
  ma120_slope REAL,
  updated_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_s3_price_features_daily_date ON s3_price_features_daily (date);
CREATE INDEX IF NOT EXISTS idx_s3_price_features_daily_ticker_date ON s3_price_features_daily (ticker, date);
"""


def read_universe_tickers() -> list[str]:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    return df["ticker"].astype(str).str.zfill(6).tolist()


def fetch_prices(tickers: list[str], end_date: str) -> pd.DataFrame:
    con = sqlite3.connect(str(PRICE_DB))
    try:
        placeholders = ",".join(["?"] * len(tickers))
        q = f"""
        SELECT ticker, date, close, volume
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date <= ?
        ORDER BY ticker, date
        """
        return pd.read_sql_query(q, con, params=tickers + [end_date])
    finally:
        con.close()


def build(start_date: str, end_date: str) -> None:
    tickers = read_universe_tickers()
    px = fetch_prices(tickers, end_date)
    if px.empty:
        raise RuntimeError("No price rows fetched")

    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["date"] = pd.to_datetime(px["date"], errors="coerce")
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px["volume"] = pd.to_numeric(px["volume"], errors="coerce")
    px = px.dropna(subset=["date", "close"]).copy()
    px["value_won"] = px["close"] * px["volume"]

    def calc_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()
        g["adv20"] = g["value_won"].rolling(20, min_periods=10).mean()
        g["adv60"] = g["value_won"].rolling(60, min_periods=30).mean()
        g["vol_ratio_20"] = g["value_won"] / g["adv20"]
        g["mom20"] = g["close"] / g["close"].shift(20) - 1.0
        g["breakout60"] = (g["close"] >= g["close"].rolling(60, min_periods=30).max()).astype(int)
        g["ma60"] = g["close"].rolling(60, min_periods=30).mean()
        g["ma120"] = g["close"].rolling(120, min_periods=60).mean()
        g["ma60_slope"] = (g["ma60"] - g["ma60"].shift(5)) / 5.0
        g["ma120_slope"] = (g["ma120"] - g["ma120"].shift(5)) / 5.0
        return g

    feat = px.groupby("ticker", group_keys=False).apply(calc_group)
    feat = feat[(feat["date"] >= pd.Timestamp(start_date)) & (feat["date"] <= pd.Timestamp(end_date))].copy()
    feat["date"] = feat["date"].dt.strftime("%Y-%m-%d")

    out_cols = [
        "ticker", "date", "close", "volume", "value_won", "adv20", "adv60",
        "vol_ratio_20", "mom20", "breakout60", "ma60", "ma120", "ma60_slope", "ma120_slope"
    ]
    out = feat[out_cols].copy()

    con = sqlite3.connect(str(FEATURES_DB))
    try:
        con.executescript(DDL)
        out.to_sql(TABLE_PRICE, con, if_exists="append", index=False)
        con.commit()
    finally:
        con.close()

    print(f"[OK] rebuilt {TABLE_PRICE}: rows={len(out):,}, range={start_date}~{end_date}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()
    build(args.start, args.end)


if __name__ == "__main__":
    main()
