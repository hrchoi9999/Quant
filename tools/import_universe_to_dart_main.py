# import_universe_to_dart_main.py ver 2026-02-05_001
import sqlite3
import pandas as pd

CSV_PATH = r"D:\Quant\data\universe\universe_top400_fundready.csv"
DB_PATH  = r"D:\Quant\data\db\dart_main.db"
TABLE    = "universe_top400_fundready"

df = pd.read_csv(CSV_PATH, dtype={"ticker": str})
df["ticker"] = df["ticker"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
cur.execute(f"""
CREATE TABLE {TABLE} (
  ticker TEXT NOT NULL,
  name   TEXT,
  market TEXT,
  mcap   INTEGER,
  asof   TEXT
)
""")
con.commit()

df.to_sql(TABLE, con, if_exists="append", index=False)

cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_ticker ON {TABLE}(ticker)")
cur.execute(f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_market ON {TABLE}(market)")
con.commit()
con.close()

print(f"OK: inserted {len(df)} rows into {DB_PATH}::{TABLE}")
