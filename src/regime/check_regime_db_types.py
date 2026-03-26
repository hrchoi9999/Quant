# check_regime_db_types.py
import sqlite3

DB = r"D:\Quant\data\db\regime.db"

con = sqlite3.connect(DB)
cur = con.cursor()

print("[db]", DB)
print("[typeof(regime)]", cur.execute(
    "select typeof(regime), count(*) from regime_history group by typeof(regime)"
).fetchall())

print("[distinct regime by horizon]", cur.execute(
    "select horizon, count(distinct regime) from regime_history group by horizon"
).fetchall())

print("[sample rows]", cur.execute(
    "select date, ticker, horizon, score, regime from regime_history order by date desc limit 5"
).fetchall())

con.close()
