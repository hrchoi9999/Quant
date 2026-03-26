# tmp_check_fund_duplicates.py ver 2026-02-02_001
import sqlite3
import pandas as pd

DB = r"D:\Quant\data\db\fundamentals.db"
TABLE = "fundamentals_monthly_mix400_20260129"

con = sqlite3.connect(DB)

q1 = f"""
select
  count(*) as rows,
  count(distinct ticker) as tickers,
  count(distinct ticker || '|' || available_from) as uniq_keys
from {TABLE}
"""
print("\n[OVERALL]")
print(pd.read_sql_query(q1, con).to_string(index=False))

q2 = f"""
select available_from, count(*) as rows, count(distinct ticker) as tickers
from {TABLE}
group by available_from
order by rows desc
limit 20
"""
print("\n[TOP 20 available_from by rows]")
print(pd.read_sql_query(q2, con).to_string(index=False))

q3 = f"""
select ticker, available_from, count(*) as n
from {TABLE}
group by ticker, available_from
having n > 1
order by n desc
limit 50
"""
print("\n[DUPLICATE (ticker, available_from) TOP 50]")
print(pd.read_sql_query(q3, con).to_string(index=False))

con.close()
print("\n[DONE]")
