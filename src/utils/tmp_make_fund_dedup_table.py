# tmp_make_fund_dedup_table.py ver 2026-02-02_001
import sqlite3

DB = r"D:\Quant\data\db\fundamentals.db"
SRC = "fundamentals_monthly_mix400_20260129"
DST = "fundamentals_monthly_mix400_20260129_dedup"

con = sqlite3.connect(DB)
cur = con.cursor()

cur.execute(f"DROP TABLE IF EXISTS {DST}")

cur.execute(f"""
CREATE TABLE {DST} AS
SELECT *
FROM {SRC}
WHERE rowid IN (
  SELECT max(rowid)
  FROM {SRC}
  GROUP BY ticker, available_from
)
""")

cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{DST}_ticker_af ON {DST}(ticker, available_from)")
con.commit()

cnt_src = cur.execute(f"SELECT count(*) FROM {SRC}").fetchone()[0]
cnt_dst = cur.execute(f"SELECT count(*) FROM {DST}").fetchone()[0]
uniq_dst = cur.execute(f"SELECT count(distinct ticker || '|' || available_from) FROM {DST}").fetchone()[0]

print(f"[DONE] {SRC}: {cnt_src:,} rows")
print(f"[DONE] {DST}: {cnt_dst:,} rows | uniq_keys={uniq_dst:,}")
con.close()
