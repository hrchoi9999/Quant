# db_init.py ver 2025-12-11_001

import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\Quant\data\db\dart_main.db")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) 기업 마스터: corp_list.csv 기반
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dim_corp (
        corp_code    TEXT PRIMARY KEY,
        corp_name    TEXT,
        stock_code   TEXT,
        modify_date  TEXT
    );
    """)

    # 2) 보고서 메타 정보
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fact_report (
        rcept_no     TEXT PRIMARY KEY,  -- 접수번호
        reprt_code   TEXT,              -- 11014 등
        bsns_year    INTEGER,
        corp_code    TEXT,
        fs_div       TEXT,              -- CFS / SEPARATE
        created_at   TEXT
    );
    """)

    # 3) 재무제표 계정 단위 테이블
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fact_fs_account (
        rcept_no        TEXT,
        corp_code       TEXT,
        bsns_year       INTEGER,
        fs_div          TEXT,      -- CFS / SEPARATE
        sj_div          TEXT,      -- BS, IS, CI 등
        sj_nm           TEXT,      -- 재무상태표, 포괄손익계산서 등
        account_id      TEXT,
        account_nm      TEXT,
        account_detail  TEXT,
        ord             INTEGER,
        currency        TEXT,

        thstrm_nm       TEXT,
        thstrm_amount   REAL,
        frmtrm_nm       TEXT,
        frmtrm_amount   REAL,

        PRIMARY KEY (rcept_no, fs_div, account_id, sj_div, ord)
    );
    """)

    conn.commit()
    conn.close()
    print(f"[INFO] DB 초기화 완료: {DB_PATH}")


if __name__ == "__main__":
    init_db()
