# check_sample.py ver 2025-12-11_001

import sqlite3
import pandas as pd

DB = r"D:\Quant\data\db\dart_main.db"

def check_company(corp_code, year):
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
    print(f"\n=== 검증: corp_code={corp_code}, year={year} ===")
    print(df)
    return df


# 예시 5개 기업 (원하시면 변경 가능)
samples = [
    ('00126380', 2023),  # 삼성전자
    ('00164779', 2023),  # 현대자동차
    ('00247079', 2023),  # 카카오
    ('00138789', 2023),  # LG화학
    ('00323821', 2023),  # 종근당
]

for corp_code, year in samples:
    check_company(corp_code, year)
