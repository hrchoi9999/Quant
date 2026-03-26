# build_s3_fund_features_monthly.py ver 2026-03-05_001
import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")

FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB_DIR = PROJECT_ROOT / r"data\db_s3"
FEATURES_DB = S3_DB_DIR / "features_s3.db"

TABLE_FUND = "s3_fund_features_monthly"
SRC_TABLE = "fundamentals_monthly_mix400_latest"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_FUND} (
  date           TEXT NOT NULL,
  ticker         TEXT NOT NULL,

  available_from TEXT,
  growth_score   REAL,
  revenue_yoy    REAL,
  op_income_yoy  REAL,

  gs_delta_3m    REAL,
  rev_delta_3m   REAL,
  op_delta_3m    REAL,

  fund_accel_score REAL,

  updated_at TEXT DEFAULT (datetime('now')),

  PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_{TABLE_FUND}_ticker_date
ON {TABLE_FUND} (ticker, date);

CREATE INDEX IF NOT EXISTS idx_{TABLE_FUND}_date
ON {TABLE_FUND} (date);
"""


def _ensure_db() -> None:
    S3_DB_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(FEATURES_DB))
    try:
        con.executescript(DDL)
        con.commit()
    finally:
        con.close()


def build(mode: str = "rebuild") -> None:
    """
    mode:
      - rebuild: TABLE_FUND 전체 삭제 후 재생성(중복/PK 문제 없음, 월간이라 비용 낮음)
      - append : 그냥 append (비권장; PK 충돌 가능)
    """
    _ensure_db()

    con = sqlite3.connect(str(FUND_DB))
    try:
        q = f"""
        SELECT date, ticker, available_from, revenue_yoy, op_income_yoy, growth_score
        FROM {SRC_TABLE}
        ORDER BY ticker, date
        """
        df = pd.read_sql_query(q, con)
    finally:
        con.close()

    if df.empty:
        raise RuntimeError("No fundamentals rows fetched. Check fundamentals.db and SRC_TABLE.")

    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = df["date"].astype(str)
    df["available_from"] = df["available_from"].astype(str)

    for c in ["revenue_yoy", "op_income_yoy", "growth_score"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_values(["ticker", "date"]).copy()
    df["gs_delta_3m"] = df.groupby("ticker")["growth_score"].diff(3)
    df["rev_delta_3m"] = df.groupby("ticker")["revenue_yoy"].diff(3)
    df["op_delta_3m"] = df.groupby("ticker")["op_income_yoy"].diff(3)

    def pct_rank(s: pd.Series) -> pd.Series:
        return s.rank(pct=True)

    df["gs_level_pct"] = df.groupby("date")["growth_score"].transform(pct_rank)
    df["gs_delta_pct"] = df.groupby("date")["gs_delta_3m"].transform(pct_rank)

    df["fund_accel_score"] = (
        0.7 * df["gs_level_pct"].fillna(0)
        + 0.3 * df["gs_delta_pct"].fillna(0)
    )

    out_cols = [
        "date", "ticker", "available_from",
        "growth_score", "revenue_yoy", "op_income_yoy",
        "gs_delta_3m", "rev_delta_3m", "op_delta_3m",
        "fund_accel_score",
    ]
    out = df[out_cols].copy()

    con_f = sqlite3.connect(str(FEATURES_DB))
    try:
        if mode.lower() == "rebuild":
            con_f.execute(f"DELETE FROM {TABLE_FUND}")
            con_f.commit()

        out.to_sql(TABLE_FUND, con_f, if_exists="append", index=False)
        con_f.commit()
    finally:
        con_f.close()

    print(f"[OK] fund_features: mode={mode} rows={len(out):,} -> {FEATURES_DB}::{TABLE_FUND}")


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="rebuild", choices=["rebuild", "append"])
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    build(mode=args.mode)