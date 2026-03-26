# inspect_regime_db.py
import sqlite3
from pathlib import Path

DB = Path(r"D:\Quant\data\db\regime.db")

print("[INFO] db_path =", DB)
print("[INFO] exists  =", DB.exists())
if DB.exists():
    print("[INFO] size   =", DB.stat().st_size, "bytes")

con = sqlite3.connect(DB)
cur = con.cursor()

print("[INFO] PRAGMA database_list =", cur.execute("PRAGMA database_list").fetchall())

tables = cur.execute(
    "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
).fetchall()

print("[INFO] sqlite_master objects =", [(t[0], t[1]) for t in tables])

for name, typ, sql in tables:
    if name.lower().startswith("regime"):
        print("\n=== OBJECT:", name, typ, "===")
        print(sql)
        print("PRAGMA table_info =", cur.execute(f"PRAGMA table_info('{name}')").fetchall())

# 명시적으로 regime_history도 찍기
print("\n=== CHECK: regime_history ===")
print("PRAGMA table_info(regime_history) =", cur.execute("PRAGMA table_info('regime_history')").fetchall())

con.close()
