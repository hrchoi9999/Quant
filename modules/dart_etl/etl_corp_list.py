# etl_corp_list.py ver 2025-12-11_001

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(r"D:\Quant\data\db\dart_main.db")
CORP_LIST_CSV = Path(r"D:\Quant\data\raw\dart\corp_list.csv")


def load_corp_list():
    if not CORP_LIST_CSV.is_file():
        raise FileNotFoundError(f"corp_list.csv를 찾을 수 없습니다: {CORP_LIST_CSV}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    df = pd.read_csv(CORP_LIST_CSV, dtype={"corp_code": str, "stock_code": str, "modify_date": str})

    # 중복 대비: 같은 corp_code는 덮어쓰기(Upsert)
    for row in df.itertuples(index=False):
        cur.execute("""
            INSERT INTO dim_corp (corp_code, corp_name, stock_code, modify_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(corp_code) DO UPDATE SET
                corp_name   = excluded.corp_name,
                stock_code  = excluded.stock_code,
                modify_date = excluded.modify_date;
        """, (
            str(row.corp_code),
            str(row.corp_name),
            str(row.stock_code) if not pd.isna(row.stock_code) else None,
            str(row.modify_date),
        ))

    conn.commit()
    conn.close()
    print(f"[INFO] dim_corp 적재 완료: {len(df)} rows")


if __name__ == "__main__":
    load_corp_list()
