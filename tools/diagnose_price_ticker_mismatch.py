# diagnose_price_ticker_mismatch.py ver 2026-02-05_001
import sqlite3
import pandas as pd

PRICE_DB = r"D:\Quant\data\db\price.db"
TABLE = "prices_daily"

con = sqlite3.connect(PRICE_DB)

# 1) 테이블 존재/행 수
tables = pd.read_sql_query(
    "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type,name",
    con
)
print("[tables/views]")
print(tables.to_string(index=False))

cnt = pd.read_sql_query(f"SELECT COUNT(*) AS rows FROM {TABLE}", con)
print("\n[prices rows]")
print(cnt.to_string(index=False))

# 2) ticker 샘플/길이 분포
sample = pd.read_sql_query(f"SELECT ticker, LENGTH(ticker) AS len FROM {TABLE} GROUP BY ticker LIMIT 20", con)
print("\n[ticker sample]")
print(sample.to_string(index=False))

lens = pd.read_sql_query(f"SELECT LENGTH(ticker) AS len, COUNT(*) AS cnt FROM {TABLE} GROUP BY LENGTH(ticker) ORDER BY len", con)
print("\n[ticker length distribution]")
print(lens.to_string(index=False))

# 3) 유니버스 대표 티커가 DB에 존재하는지
probe = ["005930", "000660", "035420", "068270"]
for t in probe:
    q = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {TABLE} WHERE ticker = ?", con, params=[t])
    print(f"\n[exists ticker={t}] n={int(q.loc[0,'n'])}")

con.close()
