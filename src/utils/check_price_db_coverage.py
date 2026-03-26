# check_price_db_coverage.py
import sqlite3
import pandas as pd

DB_PATH = r"D:\Quant\data\db\price.db"
TABLE = "prices_daily"   # 다르면 수정

con = sqlite3.connect(DB_PATH)

# 1) 테이블 존재 확인
tables = pd.read_sql_query(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;", con
)
print("Tables:", tables["name"].tolist())

# 2) 종목별 min/max/count
q = f"""
SELECT
  ticker,
  MIN(date) AS min_date,
  MAX(date) AS max_date,
  COUNT(*)  AS n_rows
FROM {TABLE}
GROUP BY ticker
ORDER BY max_date DESC, n_rows DESC
"""
df = pd.read_sql_query(q, con)
con.close()

# 날짜 파싱
df["min_date"] = pd.to_datetime(df["min_date"], errors="coerce")
df["max_date"] = pd.to_datetime(df["max_date"], errors="coerce")

print("\n[Summary]")
print("tickers:", len(df))
print("rows:", int(df["n_rows"].sum()))
latest = df["max_date"].max()
earliest = df["min_date"].min()
print("global earliest:", earliest.date() if pd.notna(earliest) else None)
print("global latest  :", latest.date() if pd.notna(latest) else None)

# 3) 최신일 기준으로 뒤처진 종목 상위
lagging = df[df["max_date"] < latest].sort_values("max_date")
print("\n[Lagging tickers (top 30)]")
print(lagging[["ticker", "max_date", "n_rows"]].head(30).to_string(index=False))

# 4) 히스토리 길이(행수) 부족 종목: 레짐 계산 최소 252일 기준
short = df[df["n_rows"] < 252].sort_values("n_rows")
print("\n[Short history (<252 rows) tickers (top 30)]")
print(short[["ticker", "min_date", "max_date", "n_rows"]].head(30).to_string(index=False))

# 5) 분포 요약(최종일, 히스토리 길이)
print("\n[Max_date distribution (top 15)]")
print(df["max_date"].dt.date.value_counts().head(15).to_string())

bins = [0, 50, 100, 252, 500, 1000, 2000, 5000, 10**9]
labels = ["<50", "50-99", "100-251", "252-499", "500-999", "1000-1999", "2000-4999", ">=5000"]
df["len_bucket"] = pd.cut(df["n_rows"], bins=bins, labels=labels, right=False)
print("\n[History length buckets]")
print(df["len_bucket"].value_counts().sort_index().to_string())

# 6) CSV로 저장(원하면)
out = r"D:\Quant\reports\price_db_coverage.csv"
try:
    df.sort_values(["max_date", "n_rows"], ascending=[False, False]).to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {out}")
except Exception as e:
    print(f"\nCould not save CSV to {out}: {e}")
