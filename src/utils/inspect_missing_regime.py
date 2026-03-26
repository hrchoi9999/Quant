# inspect_missing_regime.py ver 2026-01-29_001
import sqlite3
import pandas as pd

END = "2026-01-29"
TICKERS = ["031210", "064400", "439260", "483650"]

PRICE_DB = r"D:\Quant\data\db\price.db"
PRICE_TABLE = "prices_daily"

def q(con, sql, params=()):
    return pd.read_sql_query(sql, con, params=params)

def main():
    con = sqlite3.connect(PRICE_DB)

    print(f"[CHECK] end={END} | table={PRICE_TABLE}")
    for t in TICKERS:
        # 전체 기간 커버리지
        df0 = q(
            con,
            f"""
            select
                min(date) as min_date,
                max(date) as max_date,
                count(*) as rows,
                sum(case when close is not null then 1 else 0 end) as nonnull_close
            from {PRICE_TABLE}
            where ticker = ?
            """,
            (t,),
        )

        # end 이전 1y/6m/3m 유효 close 개수(룩백 가능성 확인)
        df1 = q(
            con,
            f"""
            with x as (
              select date, close
              from {PRICE_TABLE}
              where ticker=? and date<=?
              order by date desc
              limit 400
            )
            select
              sum(case when close is not null then 1 else 0 end) as nonnull_close_last400,
              sum(case when close is not null then 1 else 0 end) >= 252 as has_1y,
              sum(case when close is not null then 1 else 0 end) >= 126 as has_6m,
              sum(case when close is not null then 1 else 0 end) >= 63  as has_3m
            from x
            """,
            (t, END),
        )

        print("\n" + "=" * 90)
        print(f"ticker={t}")
        print(df0.to_string(index=False))
        print(df1.to_string(index=False))

        # end 이전 close가 NULL인 날짜가 있는지(최근 결측)
        df2 = q(
            con,
            f"""
            select date, close
            from {PRICE_TABLE}
            where ticker=? and date<=?
            order by date desc
            limit 10
            """,
            (t, END),
        )
        print("[last 10 rows]")
        print(df2.to_string(index=False))

    con.close()
    print("\n[DONE]")

if __name__ == "__main__":
    main()
