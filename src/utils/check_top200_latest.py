# check_top200_latest.py ver 2026-01-27_001
import sqlite3
import pandas as pd

db = r"D:\Quant\data\db\price.db"
univ = r"D:\Quant\data\universe\universe_top200_kospi_20251230_clean.csv"
tcol = "ticker"
table = "prices_daily"

u = pd.read_csv(univ, dtype={tcol: "string"})
tickers = (
    u[tcol]
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
    .map(lambda x: x.zfill(6))
    .tolist()
)

con = sqlite3.connect(db)
q = f"""
SELECT ticker, MAX(date) AS max_date, COUNT(*) AS n_rows
FROM {table}
WHERE ticker IN ({",".join(["?"] * len(tickers))})
GROUP BY ticker
"""
df = pd.read_sql_query(q, con, params=tickers)
con.close()

df["max_date"] = pd.to_datetime(df["max_date"], errors="coerce")
latest = df["max_date"].max()

print("Top200 tickers in DB:", df["ticker"].nunique())
print("latest:", latest.date())
print("at latest:", int((df["max_date"] == latest).sum()))
print("lagging:", int((df["max_date"] < latest).sum()))
print("\n[Lagging sample]")
print(df[df["max_date"] < latest].sort_values("max_date").head(20).to_string(index=False))
