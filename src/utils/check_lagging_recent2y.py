# check_lagging_recent2y.py ver 2026-01-27_001
import sqlite3
import pandas as pd

DB_PATH = r"D:\Quant\data\db\price.db"
TABLE = "prices_daily"
DAYS = 730  # 최근 2년(대략)

con = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(
    f"""
    SELECT ticker, MAX(date) AS max_date, COUNT(*) AS n_rows
    FROM {TABLE}
    GROUP BY ticker
    """,
    con,
)
con.close()

df["max_date"] = pd.to_datetime(df["max_date"], errors="coerce")
latest = df["max_date"].max()
cutoff = latest - pd.Timedelta(days=DAYS)

# 최신일보다 뒤처졌고, 최근 2년 구간 안에서 멈춘 종목만
lag_recent = df[(df["max_date"] < latest) & (df["max_date"] >= cutoff)].copy()
lag_recent = lag_recent.sort_values(["max_date", "n_rows"], ascending=[True, True])

print("latest:", latest.date())
print("cutoff (approx 2y):", cutoff.date())
print("count:", len(lag_recent))
print()
print(lag_recent.head(60).to_string(index=False))

# CSV 저장
out = r"D:\Quant\reports\price_db_lagging_recent2y.csv"
lag_recent.to_csv(out, index=False, encoding="utf-8-sig")
print("\nSaved:", out)
