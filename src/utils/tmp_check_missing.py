# tmp_check_missing.py
import pandas as pd
import sqlite3

end = "2026-01-29"
uni_path = r"D:\Quant\data\universe\universe_top200_kospi_20260127.csv"
db_path = r"D:\Quant\data\db\regime.db"

uni = pd.read_csv(uni_path)
U = set(uni["ticker"].astype(str).str.zfill(6))

con = sqlite3.connect(db_path)
df = pd.read_sql_query(
    "select horizon, ticker from regime_history where date=?",
    con,
    params=(end,),
)
con.close()

df["ticker"] = df["ticker"].astype(str).str.zfill(6)

for h in ["1y", "6m", "3m"]:
    S = set(df.loc[df["horizon"] == h, "ticker"])
    miss = sorted(U - S)
    print(h, "missing", len(miss))
    if miss:
        print(" ", miss)
