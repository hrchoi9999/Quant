# src/features/init_features_db.py
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS features_daily (
  date                TEXT NOT NULL,
  ticker              TEXT NOT NULL,

  market_cap          REAL,
  adv_value_60d       REAL,

  vol_std_20          REAL,
  vol_comp_ratio      REAL,
  bb_width_20         REAL,
  vol_ratio_20        REAL,
  breakout_60         INTEGER,
  breakout_120        INTEGER,

  sales_yoy           REAL,
  sales_yoy_delta     REAL,
  opinc_yoy           REAL,
  opinc_yoy_delta     REAL,
  fund_accel_score    REAL,

  is_eligible_s3      INTEGER DEFAULT 0,
  updated_at          TEXT DEFAULT (datetime('now')),

  PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_features_daily_ticker_date
ON features_daily (ticker, date);

CREATE INDEX IF NOT EXISTS idx_features_daily_date
ON features_daily (date);
"""

def init(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(DDL)
        con.commit()
    finally:
        con.close()

if __name__ == "__main__":
    # 개발 단계: dev db 폴더에 두는 것을 권장
    db = r"D:\Quant\data\db\_dev_s3\features.db"
    init(db)
    print("[OK] initialized:", db)