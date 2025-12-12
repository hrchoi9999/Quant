# build_fs_annual_table.py ver 2025-12-11_001

import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\Quant\data\db\dart_main.db")


def create_view_vw_fs_annual_cfs(con: sqlite3.Connection) -> None:
    """
    연간 연결재무제표(CFS)만 모아두는 뷰.
    - reprt_code 컬럼이 없으므로 bsns_year + fs_div='CFS' 기준만 사용
    - thstrm_amount를 REAL로 캐스팅
    """
    sql = """
    CREATE VIEW IF NOT EXISTS vw_fs_annual_cfs AS
    SELECT
        f.corp_code,
        f.bsns_year,
        f.fs_div,
        f.sj_div,
        f.account_id,
        f.account_nm,
        f.account_detail,
        CAST(
            REPLACE(
                NULLIF(f.thstrm_amount, ''),
                ',',
                ''
            ) AS REAL
        ) AS amount
    FROM fact_fs_account AS f
    WHERE f.fs_div = 'CFS';
    """
    con.execute(sql)


def create_table_fs_annual(con: sqlite3.Connection) -> None:
    """
    분석용 연간 재무 테이블.
    - 한 회사 + 한 연도당 한 줄
    - 주요 계정만 피벗해서 컬럼으로 만든다.
    """
    sql = """
    CREATE TABLE IF NOT EXISTS fs_annual (
        corp_code   TEXT NOT NULL,
        bsns_year   INTEGER NOT NULL,
        stock_code  TEXT,
        corp_name   TEXT,
        revenue     REAL,   -- 매출액 / 수익(매출액)
        op_income   REAL,   -- 영업이익
        net_income  REAL,   -- 당기순이익
        assets      REAL,   -- 자산총계
        liab        REAL,   -- 부채총계
        equity      REAL,   -- 자본총계
        op_cf       REAL,   -- 영업활동현금흐름
        PRIMARY KEY (corp_code, bsns_year)
    );
    """
    con.execute(sql)


def rebuild_fs_annual(con: sqlite3.Connection) -> None:
    """
    fs_annual 내용을 vw_fs_annual_cfs + dim_corp_listed 에서 다시 채운다.
    - dim_corp_listed: 상장사만
    - account_id / account_nm 기반으로 주요 계정 하나씩 뽑아서 MAX()로 집계
    """
    # 기존 데이터 삭제
    con.execute("DELETE FROM fs_annual;")

    sql = """
    INSERT INTO fs_annual (
        corp_code, bsns_year, stock_code, corp_name,
        revenue, op_income, net_income,
        assets, liab, equity, op_cf
    )
    SELECT
        c.corp_code,
        v.bsns_year,
        c.stock_code,
        c.corp_name,

        -- 매출액 / 수익(매출액)
        MAX(CASE
                WHEN v.account_id IN ('ifrs-full_Revenue', 'dart_OperatingRevenue')
                     OR v.account_nm LIKE '%매출액%'
                     OR v.account_nm LIKE '%수익(매출액)%'
                THEN v.amount END) AS revenue,

        -- 영업이익
        MAX(CASE
                WHEN v.account_id IN ('ifrs-full_OperatingIncomeLoss', 'dart_OperatingIncomeLoss')
                     OR v.account_nm LIKE '%영업이익%'
                THEN v.amount END) AS op_income,

        -- 당기순이익
        MAX(CASE
                WHEN v.account_id IN ('ifrs-full_ProfitLoss', 'dart_ProfitLoss')
                     OR v.account_nm LIKE '%당기순이익%'
                THEN v.amount END) AS net_income,

        -- 자산총계
        MAX(CASE
                WHEN v.account_id IN ('ifrs-full_Assets', 'dart_TotalAssets')
                     OR v.account_nm LIKE '%자산총계%'
                THEN v.amount END) AS assets,

        -- 부채총계
        MAX(CASE
                WHEN v.account_id IN ('ifrs-full_Liabilities', 'dart_TotalLiabilities')
                     OR v.account_nm LIKE '%부채총계%'
                THEN v.amount END) AS liab,

        -- 자본총계
        MAX(CASE
                WHEN v.account_id IN ('ifrs-full_Equity')
                     OR v.account_nm LIKE '%자본총계%'
                THEN v.amount END) AS equity,

        -- 영업활동현금흐름
        MAX(CASE
                WHEN v.account_id IN (
                        'ifrs-full_CashFlowsFromUsedInOperatingActivities'
                    )
                     OR (v.account_nm LIKE '%영업활동%' AND v.account_nm LIKE '%현금흐름%')
                THEN v.amount END) AS op_cf

    FROM vw_fs_annual_cfs AS v
    JOIN dim_corp_listed AS c
      ON v.corp_code = c.corp_code
    GROUP BY
        c.corp_code,
        v.bsns_year,
        c.stock_code,
        c.corp_name
    ORDER BY
        c.corp_code,
        v.bsns_year;
    """
    con.execute(sql)


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    try:
        print("[1] 뷰(vw_fs_annual_cfs) 생성")
        create_view_vw_fs_annual_cfs(con)

        print("[2] fs_annual 테이블 생성")
        create_table_fs_annual(con)

        print("[3] fs_annual 데이터 재구축 (상장사만 대상)")
        rebuild_fs_annual(con)

        con.commit()
        print("[완료] fs_annual 테이블 재생성 완료")
    finally:
        con.close()


if __name__ == "__main__":
    main()
