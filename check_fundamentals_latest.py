# check_fundamentals_latest.py ver 2026-02-06_002
# 목적:
# 1) fundamentals_monthly_mix400_latest 기본 통계
# 2) s2_fund_scores_monthly / vw_s2_top30_monthly가 VIEW인지 확인
# 3) "달력 월말" 기준 비월말 행 수(참고용)
# 4) "거래월말(월 마지막 거래일)" 기준 비월말 행 수(핵심)  -> 이 값이 0이면 C안 정합성 OK

import sqlite3
import pandas as pd


FUND_DB = r"D:\Quant\data\db\fundamentals.db"
PRICE_DB = r"D:\Quant\data\db\price.db"

FUND_TABLE = "fundamentals_monthly_mix400_latest"
PRICE_TABLE = "prices_daily"


def main() -> None:
    fund_con = sqlite3.connect(FUND_DB)
    price_con = sqlite3.connect(PRICE_DB)

    try:
        # 1) 기본 통계
        q1 = f"""
        select
            min(date) as min_d,
            max(date) as max_d,
            count(*) as rows,
            count(distinct ticker) as tickers
        from {FUND_TABLE}
        """
        print(pd.read_sql_query(q1, fund_con).to_string(index=False))

        # 2) 최근 월별 row 수
        q2 = f"""
        select substr(date,1,7) as ym, count(*) as rows
        from {FUND_TABLE}
        group by ym
        order by ym desc
        limit 12
        """
        print("---")
        print(pd.read_sql_query(q2, fund_con).to_string(index=False))

        # 3) VIEW 존재 확인
        q3 = """
        select name, type
        from sqlite_master
        where name in ('s2_fund_scores_monthly','vw_s2_top30_monthly')
        """
        print("---")
        print(pd.read_sql_query(q3, fund_con).to_string(index=False))

        # 4) 달력 월말 기준(참고용) - 휴장월이면 값이 생길 수 있음
        q4 = f"""
        select count(*) as non_calendar_month_end_rows
        from {FUND_TABLE}
        where date <> date(date, 'start of month', '+1 month', '-1 day')
        """
        print("---")
        print(pd.read_sql_query(q4, fund_con).to_string(index=False))

        # 5) 거래월말(핵심) 검증: fundamentals.date 가 price 월별 마지막 거래일에 포함되는가?
        # - price_table에서 월별 마지막 거래일 집합(trading month-end) 생성
        p = pd.read_sql_query(
            f"""
            select max(date) as tme
            from {PRICE_TABLE}
            group by substr(date,1,7)
            """,
            price_con,
        )
        tme_set = set(pd.to_datetime(p["tme"], errors="coerce").dropna().dt.strftime("%Y-%m-%d").tolist())

        f_dates = pd.read_sql_query(f"select distinct date from {FUND_TABLE}", fund_con)
        f_dates["date"] = pd.to_datetime(f_dates["date"], errors="coerce")
        f_dates = f_dates.dropna(subset=["date"])
        f_dates["date"] = f_dates["date"].dt.strftime("%Y-%m-%d")

        bad = f_dates[~f_dates["date"].isin(tme_set)].sort_values("date")

        print("---")
        print(f"non_trading_month_end_dates = {len(bad)}")
        if len(bad) > 0:
            print("[BAD SAMPLE] fundamentals dates not in trading month-end set (show up to 20):")
            print(bad.head(20).to_string(index=False))
        else:
            print("[OK] All fundamentals dates are trading month-end dates.")

    finally:
        fund_con.close()
        price_con.close()


if __name__ == "__main__":
    main()
