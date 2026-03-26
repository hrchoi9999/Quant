# build_features_db.py ver 2026-01-29_001
"""
Create features.db (technical indicators / factors) from price.db.

Input:
  - price.db with table prices_daily
    (ticker TEXT, date TEXT, open/high/low/close REAL, volume INTEGER, ...)

Output:
  - features.db with table features_daily (one row per ticker-date)

Computed features (daily):
  - ret_1d, ret_21d, ret_63d, ret_126d, ret_252d
  - sma_20, sma_60, sma_120, sma_200
  - rsi_14 (Wilder)
  - macd, macd_signal, macd_hist (EMA12-EMA26, signal EMA9)
  - vol_21, vol_63 (rolling std of ret_1d)
  - atr_14 (Wilder)
  - gap_sma200 (close/sma_200 - 1)

Notes:
  - Processes tickers one-by-one to keep memory bounded.
  - date is assumed ISO 'YYYY-MM-DD' (TEXT) and sortable.
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import List, Optional, Tuple

import pandas as pd
import numpy as np


# -----------------------------
# Indicator helpers
# -----------------------------
def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI using EMA smoothing (alpha=1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    m = ema_fast - ema_slow
    s = m.ewm(span=signal, adjust=False, min_periods=signal).mean()
    h = m - s
    return m, s, h


def atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


# -----------------------------
# DB helpers
# -----------------------------
def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA cache_size=-200000;")  # ~200MB cache (negative=KB)
    return con


def ensure_out_table(con: sqlite3.Connection, table: str) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
          ticker TEXT NOT NULL,
          date   TEXT NOT NULL,

          close REAL,

          ret_1d   REAL,
          ret_21d  REAL,
          ret_63d  REAL,
          ret_126d REAL,
          ret_252d REAL,

          sma_20  REAL,
          sma_60  REAL,
          sma_120 REAL,
          sma_200 REAL,

          rsi_14 REAL,

          macd        REAL,
          macd_signal REAL,
          macd_hist   REAL,

          vol_21 REAL,
          vol_63 REAL,

          atr_14 REAL,
          gap_sma200 REAL,

          PRIMARY KEY (ticker, date)
        ) WITHOUT ROWID;
        """
    )
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}(date);")
    con.commit()


def load_universe_tickers(universe_file: str, ticker_col: str) -> List[str]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns:
        raise ValueError(f"ticker_col='{ticker_col}' not found. columns={list(df.columns)}")
    tickers = df[ticker_col].astype(str).str.strip().unique().tolist()
    # 6자리 숫자코드 정규화
    tickers = [t.zfill(6) if t.isdigit() else t for t in tickers]
    return sorted(tickers)


def fetch_tickers(con: sqlite3.Connection, table: str, tickers: Optional[List[str]]) -> List[str]:
    if tickers:
        return tickers
    rows = con.execute(f"SELECT DISTINCT ticker FROM {table} ORDER BY ticker;").fetchall()
    return [r[0] for r in rows]


def read_prices_for_ticker(
    con: sqlite3.Connection,
    table: str,
    ticker: str,
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    where = ["ticker = ?"]
    params: List[str] = [ticker]
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)

    q = f"""
    SELECT date, open, high, low, close, volume, value
    FROM {table}
    WHERE {" AND ".join(where)}
    ORDER BY date;
    """
    df = pd.read_sql_query(q, con, params=params)
    for c in ["open", "high", "low", "close", "volume", "value"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]

    ret_1d = close.pct_change()
    df["ret_1d"] = ret_1d
    for k, col in [(21, "ret_21d"), (63, "ret_63d"), (126, "ret_126d"), (252, "ret_252d")]:
        df[col] = close / close.shift(k) - 1.0

    for w, col in [(20, "sma_20"), (60, "sma_60"), (120, "sma_120"), (200, "sma_200")]:
        df[col] = close.rolling(window=w, min_periods=w).mean()

    df["rsi_14"] = rsi_wilder(close, 14)

    m, s, h = macd(close, 12, 26, 9)
    df["macd"] = m
    df["macd_signal"] = s
    df["macd_hist"] = h

    df["vol_21"] = ret_1d.rolling(window=21, min_periods=21).std()
    df["vol_63"] = ret_1d.rolling(window=63, min_periods=63).std()

    df["atr_14"] = atr_wilder(df["high"], df["low"], close, 14)
    df["gap_sma200"] = (close / df["sma_200"]) - 1.0

    return df


def to_rows(ticker: str, df: pd.DataFrame) -> List[Tuple]:
    cols = [
        "date", "close",
        "ret_1d", "ret_21d", "ret_63d", "ret_126d", "ret_252d",
        "sma_20", "sma_60", "sma_120", "sma_200",
        "rsi_14",
        "macd", "macd_signal", "macd_hist",
        "vol_21", "vol_63",
        "atr_14",
        "gap_sma200",
    ]
    out = df[cols].copy().replace({np.nan: None})
    return [(ticker, *r) for r in out.itertuples(index=False, name=None)]


def upsert_rows(con: sqlite3.Connection, table: str, rows: List[Tuple], batch_size: int) -> int:
    if not rows:
        return 0

    cols = [
        "ticker", "date",
        "close",
        "ret_1d", "ret_21d", "ret_63d", "ret_126d", "ret_252d",
        "sma_20", "sma_60", "sma_120", "sma_200",
        "rsi_14",
        "macd", "macd_signal", "macd_hist",
        "vol_21", "vol_63",
        "atr_14",
        "gap_sma200",
    ]
    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join(cols)
    update_cols = [c for c in cols if c not in ("ticker", "date")]
    update_set = ",".join([f"{c}=excluded.{c}" for c in update_cols])

    sql = f"""
    INSERT INTO {table} ({col_list})
    VALUES ({placeholders})
    ON CONFLICT(ticker, date) DO UPDATE SET
      {update_set};
    """

    cur = con.cursor()
    n = 0
    for i in range(0, len(rows), batch_size):
        cur.executemany(sql, rows[i : i + batch_size])
        con.commit()
        n += min(batch_size, len(rows) - i)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--price-db", required=True)
    ap.add_argument("--price-table", default="prices_daily")
    ap.add_argument("--out-db", required=True)
    ap.add_argument("--out-table", default="features_daily")
    ap.add_argument("--universe-file", default=None)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--progress-every", type=int, default=20)
    args = ap.parse_args()

    in_con = connect(args.price_db)
    out_con = connect(args.out_db)
    ensure_out_table(out_con, args.out_table)

    tickers = load_universe_tickers(args.universe_file, args.ticker_col) if args.universe_file else None
    ticker_list = fetch_tickers(in_con, args.price_table, tickers)

    print(f"[INFO] tickers={len(ticker_list)} | start={args.start} | end={args.end}")
    total = 0

    for idx, tk in enumerate(ticker_list, 1):
        dfp = read_prices_for_ticker(in_con, args.price_table, tk, args.start, args.end)
        if dfp.empty:
            continue
        dfp = dfp.dropna(subset=["close"]).copy()
        if dfp.empty:
            continue

        df_feat = compute_features(dfp)
        rows = to_rows(tk, df_feat)
        total += upsert_rows(out_con, args.out_table, rows, args.batch_size)

        if idx % args.progress_every == 0:
            print(f"[PROGRESS] {idx}/{len(ticker_list)} tickers | rows_written={total:,}")

    cnt = out_con.execute(f"SELECT COUNT(*) FROM {args.out_table};").fetchone()[0]
    print(f"[DONE] features rows={cnt:,} -> {args.out_db}::{args.out_table}")

    in_con.close()
    out_con.close()


if __name__ == "__main__":
    main()
