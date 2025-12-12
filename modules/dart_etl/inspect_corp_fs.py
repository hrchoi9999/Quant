# inspect_corp_fs.py ver 2025-12-11_002

import sqlite3
import pandas as pd

DB = r"D:\Quant\data\db\dart_main.db"


def find_corp(name_keyword: str):
    conn = sqlite3.connect(DB)
    query = f"""
    SELECT corp_code, corp_name, stock_code
    FROM dim_corp
    WHERE corp_name LIKE '%{name_keyword}%'
    ORDER BY corp_name
    """
    df = pd.read_sql(query, conn)
    conn.close()
    print(f"\n[1] dim_corp 검색: '{name_keyword}'")
    print(df)
    return df


def show_fs_years(corp_code: str):
    conn = sqlite3.connect(DB)
    query = f"""
    SELECT bsns_year, fs_div, COUNT(*) AS cnt
    FROM fact_fs_account
    WHERE corp_code = '{corp_code}'
    GROUP BY bsns_year, fs_div
    ORDER BY bsns_year, fs_div;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    print(f"\n[2] fact_fs_account 연도별 데이터: corp_code={corp_code}")
    print(df)
    return df


def sample_main_accounts(corp_code: str, year: int):
    conn = sqlite3.connect(DB)
    query = f"""
    SELECT account_nm, thstrm_amount, frmtrm_amount
    FROM fact_fs_account
    WHERE corp_code = '{corp_code}'
      AND bsns_year = {year}
      AND account_nm IN (
        '매출액', '영업이익', '당기순이익',
        '자산총계', '부채총계', '자본총계'
      )
    ORDER BY account_nm;
    """
    df = pd.read_sql(query, conn)
    conn.close()
    print(f"\n[3] 핵심 계정 값 확인: corp_code={corp_code}, year={year}")
    print(df)
    return df


if __name__ == "__main__":
    # 1) 삼성전자
    samsung = find_corp("삼성전자")
    if not samsung.empty:
        samsung_code = samsung.iloc[0]["corp_code"]
        years = show_fs_years(samsung_code)
        if not years.empty:
            latest_year = int(years["bsns_year"].max())
            sample_main_accounts(samsung_code, latest_year)

    # 2) 현대자동차
    hyundai = find_corp("현대자동차")
    if not hyundai.empty:
        hyundai_code = hyundai.iloc[0]["corp_code"]
        years = show_fs_years(hyundai_code)
        if not years.empty:
            latest_year = int(years["bsns_year"].max())
            sample_main_accounts(hyundai_code, latest_year)
