# inspect_strategy_dbs.py
# 실행: python inspect_strategy_dbs.py

import sqlite3
import pandas as pd
from pathlib import Path

DBS = {
    "regime": r"D:\Quant\data\db\regime.db",   # 경로는 실제 위치로 수정
    "features": r"D:\Quant\data\db\features.db",
    "market": r"D:\Quant\data\db\market.db",
}

def q(conn, sql, params=None):
    return pd.read_sql_query(sql, conn, params=params or [])

def list_tables(conn):
    return q(conn, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")["name"].tolist()

def table_info(conn, table):
    return q(conn, f"PRAGMA table_info({table})")[["cid","name","type","notnull","dflt_value","pk"]]

def minmax(conn, table):
    cols = q(conn, f"PRAGMA table_info({table})")["name"].tolist()
    if "date" in cols:
        return q(conn, f"SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as n FROM {table}")
    return None

def sample(conn, table):
    return q(conn, f"SELECT * FROM {table} LIMIT 5")

def main():
    for name, path in DBS.items():
        p = Path(path)
        print("\n" + "="*80)
        print(f"[{name}] {p}")
        if not p.exists():
            print("!! 파일이 없습니다. 경로 확인 필요")
            continue

        conn = sqlite3.connect(str(p))
        try:
            tables = list_tables(conn)
            print(f"tables({len(tables)}): {tables}")

            for t in tables:
                print("\n" + "-"*60)
                print(f"table: {t}")
                print(table_info(conn, t).to_string(index=False))

                mm = minmax(conn, t)
                if mm is not None:
                    print(mm.to_string(index=False))

                print("sample:")
                print(sample(conn, t).to_string(index=False))
        finally:
            conn.close()

if __name__ == "__main__":
    main()
