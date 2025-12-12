# check_fs_data.py ver 2025-12-11_001

import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\Quant\data\db\dart_main.db")

if not DB_PATH.is_file():
    print(f"[ERROR] DB 파일을 찾을 수 없습니다: {DB_PATH}")
    raise SystemExit(1)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print(f"[INFO] DB 경로: {DB_PATH}\n")

tables = ["dim_corp", "fact_report", "fact_fs_account"]

for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"{t:20s} : {cnt:10d} rows")
    except Exception as e:
        print(f"{t:20s} : <테이블 없음 또는 오류> ({e})")

print("\n[INFO] fact_report 상위 5개 예시:")
try:
    cur.execute("""
        SELECT rcept_no, corp_code, bsns_year, fs_div, reprt_code
        FROM fact_report
        ORDER BY bsns_year DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    for r in rows:
        print("  ", r)
except Exception as e:
    print("  조회 오류:", e)

conn.close()
