# check_fs_samsung_clean.py ver 2025-12-11_001

import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path(r"D:\Quant\data\db\dart_main.db")


def main():
    con = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT
            corp_code, stock_code, corp_name,
            bsns_year, revenue, op_income, net_income,
            assets, liab, equity, op_cf
        FROM fs_annual
        WHERE stock_code = '005930'
        ORDER BY bsns_year DESC;
    """, con)

    print(df)

    con.close()


if __name__ == "__main__":
    main()
