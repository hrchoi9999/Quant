# build_s3_price_features_daily.py ver 2026-03-05_001
import argparse
import sqlite3
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")

PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"

S3_DB_DIR = PROJECT_ROOT / r"data\db_s3"
FEATURES_DB = S3_DB_DIR / "features_s3.db"

TABLE_PRICE = "s3_price_features_daily"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_PRICE} (
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

  updated_at TEXT DEFAULT (datetime('now')),

  PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_{TABLE_PRICE}_date
ON {TABLE_PRICE} (date);

CREATE INDEX IF NOT EXISTS idx_{TABLE_PRICE}_ticker_date
ON {TABLE_PRICE} (ticker, date);
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
    tickers = df["ticker"].astype(str).str.zfill(6).tolist()
    return tickers


def _fetch_prices(
    con: sqlite3.Connection,
    tickers: List[str],
    end_date: str,
) -> pd.DataFrame:
    placeholders = ",".join(["?"] * len(tickers))
    q = f"""
    SELECT ticker, date, close, volume
    FROM prices_daily
    WHERE ticker IN ({placeholders})
      AND date <= ?
    ORDER BY ticker, date
    """
    params = tickers + [end_date]
    df = pd.read_sql_query(q, con, params=params)
    return df


def _get_existing_max_date(con_f: sqlite3.Connection) -> Optional[str]:
    q = f"SELECT max(date) AS max_date FROM {TABLE_PRICE}"
    try:
        out = pd.read_sql_query(q, con_f)
        v = out.loc[0, "max_date"]
        return None if v is None else str(v)
    except Exception:
        return None


def _delete_range(con_f: sqlite3.Connection, start_date: str, end_date: str) -> int:
    cur = con_f.cursor()
    cur.execute(
        f"DELETE FROM {TABLE_PRICE} WHERE date >= ? AND date <= ?",
        (start_date, end_date),
    )
    return cur.rowcount if cur.rowcount is not None else 0


def build(end_date: str, lookback_days: int = 260, start_date: Optional[str] = None) -> None:
    """
    - end_date까지 가격 피처를 구축
    - start_date가 없으면: 현재 features DB의 max(date)+1 부터 증분 적재
    - 중복 방지: (start_date~end_date) 구간을 먼저 DELETE 후 INSERT
    """
    _ensure_db()

    # start_date 자동 결정 (DB max_date + 1day)
    con_f = sqlite3.connect(str(FEATURES_DB))
    try:
        max_d = _get_existing_max_date(con_f)
    finally:
        con_f.close()

    if start_date is None:
        if max_d is None:
            # 최초 적재라면, price DB가 시작되는 구간부터 충분히 쌓는 게 정석이지만
            # 여기서는 사용자가 지정하는 end_date 기준으로 lookback을 넉넉히 확보하는 방식으로 진행
            # (필요하면 start_date를 명시하세요)
            start_date = "1900-01-01"
        else:
            start_date = (pd.to_datetime(max_d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # 날짜 정규화
    end_ts = pd.to_datetime(end_date)
    start_ts = pd.to_datetime(start_date)
    if start_ts > end_ts:
        print(f"[SKIP] start_date({start_date}) > end_date({end_date})")
        return

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

    # 거래대금(원)
    px["value_won"] = px["close"] * px["volume"]

    def calc_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()

        g["adv20"] = g["value_won"].rolling(20, min_periods=10).mean()
        g["adv60"] = g["value_won"].rolling(60, min_periods=30).mean()

        g["vol_ratio_20"] = g["value_won"] / g["adv20"]

        g["mom20"] = g["close"] / g["close"].shift(20) - 1.0

        roll_max_60 = g["close"].rolling(60, min_periods=30).max()
        g["breakout60"] = (g["close"] >= roll_max_60).astype(int)

        return g

    # pandas FutureWarning은 기능상 문제 아니므로 무시해도 됩니다.
    feat = px.groupby("ticker", group_keys=False).apply(calc_group)

    feat["_dt"] = pd.to_datetime(feat["date"], errors="coerce")

    # 롤링 계산을 위해 start_date 이전 구간을 조금 포함(lookback_days*2일)
    buffer_start = start_ts - pd.Timedelta(days=lookback_days * 2)
    feat = feat[(feat["_dt"] >= buffer_start) & (feat["_dt"] <= end_ts)].copy()

    # 실제 적재는 start_date~end_date 구간만
    feat_ins = feat[(feat["_dt"] >= start_ts) & (feat["_dt"] <= end_ts)].copy()
    feat_ins.drop(columns=["_dt"], inplace=True)

    out_cols = [
        "ticker", "date", "close", "volume", "value_won",
        "adv20", "adv60", "vol_ratio_20", "mom20", "breakout60",
    ]
    feat_out = feat_ins[out_cols].copy()

    con_f = sqlite3.connect(str(FEATURES_DB))
    try:
        deleted = _delete_range(con_f, start_date=start_date, end_date=end_date)
        feat_out.to_sql(TABLE_PRICE, con_f, if_exists="append", index=False)
        con_f.commit()
    finally:
        con_f.close()

    print(
        f"[OK] price_features: deleted={deleted:,}, inserted={len(feat_out):,} "
        f"-> {FEATURES_DB}::{TABLE_PRICE} (range={start_date}~{end_date})"
    )


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", required=True, help="예: 2026-03-04")
    ap.add_argument("--start", default=None, help="미지정 시 DB max(date)+1부터 증분 적재")
    ap.add_argument("--lookback-days", type=int, default=260)
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    build(end_date=args.end, lookback_days=args.lookback_days, start_date=args.start)