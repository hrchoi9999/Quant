# inspect_corp_tables.py ver 2025-12-11_001

import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\Quant\data\db\dart_main")

def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    print("=== 전체 테이블 목록 ===")
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cur.fetchall()]
    for name in tables:
        print("-", name)

    print("\n=== 'corp' 글자가 들어가는 테이블의 컬럼 구조 ===")
    for name in tables:
        if "corp" in name.lower():
            print(f"\n[테이블] {name}")
            cur.execute(f"PRAGMA table_info({name});")
            cols = cur.fetchall()
            for cid, col_name, col_type, notnull, dflt, pk in cols:
                print(f"  - {col_name} ({col_type})")

    con.close()

if __name__ == "__main__":
    main()
