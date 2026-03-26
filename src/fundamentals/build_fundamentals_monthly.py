# build_fundamentals_monthly.py ver 2026-02-06_004
# C안 반영 요약
# (1) C안: out_table을 'fundamentals_monthly_mix{N}_latest'로 운영하도록 파이프라인에서 지정(이 파일은 테이블/뷰의 정합성 강제)
# (2) out_table 내 비-월말(date not month-end) 행이 있으면 자동 삭제하여 월말 스냅 정합성 유지
# (3) 저장(upsert) 후 s2_fund_scores_monthly / vw_s2_top30_monthly 뷰를 out_table 기반으로 재생성

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np


def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _parse_ymd(s: str) -> date:
    s = str(s).strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _fmt_ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _get_db_max_date(db_path: str, table: str, date_col: str = "date") -> str | None:
    con = _connect(db_path)
    try:
        df = pd.read_sql_query(f"SELECT MAX({date_col}) AS max_date FROM {table}", con)
        v = df.iloc[0]["max_date"]
        return str(v) if v is not None else None
    finally:
        con.close()


def _table_exists(db_path: str, table: str) -> bool:
    con = _connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            con,
            params=[table],
        )
        return not df.empty
    finally:
        con.close()


def _load_universe_tickers(universe_file: str, ticker_col: str) -> list[str]:
    df = pd.read_csv(universe_file, dtype={ticker_col: str})
    if ticker_col not in df.columns:
        raise ValueError(f"ticker_col '{ticker_col}' not found in {universe_file}. cols={list(df.columns)}")
    tickers = (
        df[ticker_col]
        .astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(6)
        .dropna()
        .unique()
        .tolist()
    )
    return sorted(tickers)


def _get_month_end_dates(price_db: str, price_table: str, start: str | None, end: str | None) -> pd.Series:
    """
    price_db의 실제 거래일 기반으로 "월말(해당 월의 마지막 거래일)" 시퀀스를 만듭니다.
    """
    con = _connect(price_db)
    try:
        q = f"SELECT DISTINCT date FROM {price_table}"
        params = []
        wh = []
        if start:
            wh.append("date >= ?")
            params.append(start)
        if end:
            wh.append("date <= ?")
            params.append(end)
        if wh:
            q += " WHERE " + " AND ".join(wh)
        q += " ORDER BY date"
        dates = pd.read_sql_query(q, con, params=params)["date"]
        if dates.empty:
            return pd.Series(dtype="object")
        dates = pd.to_datetime(dates)
        me = dates.groupby(dates.dt.to_period("M")).max().sort_values()
        return me.dt.strftime("%Y-%m-%d")
    finally:
        con.close()


def _load_annual_with_available_from(dart_db: str, tickers: list[str]) -> pd.DataFrame:
    """
    fs_annual + fact_report를 이용해서 'available_from'(공시 접수일)를 붙입니다.
    reprt_code=11011(사업보고서)만 사용.
    """
    con = _connect(dart_db)
    try:
        if not tickers:
            raise ValueError("tickers empty")

        tickers_sql = ",".join(["?"] * len(tickers))
        fs = pd.read_sql_query(
            f"""
            SELECT corp_code, bsns_year, stock_code, corp_name, revenue, op_income
            FROM fs_annual
            WHERE stock_code IN ({tickers_sql})
            """,
            con,
            params=tickers,
        )

        if fs.empty:
            raise RuntimeError("fs_annual returned 0 rows for given tickers.")

        fs["stock_code"] = fs["stock_code"].astype(str).str.zfill(6)

        rep = pd.read_sql_query(
            """
            SELECT rcept_no, reprt_code, bsns_year, corp_code, fs_div
            FROM fact_report
            WHERE reprt_code='11011'
            """,
            con,
        )

        rep["available_from"] = rep["rcept_no"].astype(str).str.slice(0, 8)
        rep = rep[rep["available_from"].str.match(r"^\d{8}$", na=False)].copy()
        rep["available_from"] = pd.to_datetime(rep["available_from"], format="%Y%m%d", errors="coerce")
        rep = rep.dropna(subset=["available_from"])

        rep = rep.groupby(["corp_code", "bsns_year"], as_index=False)["available_from"].min()

        out = fs.merge(rep, on=["corp_code", "bsns_year"], how="left")

        # available_from가 없는 경우: 다음해 03-31(보수적)로 가정
        miss = out["available_from"].isna()
        if miss.any():
            by = out.loc[miss, "bsns_year"].astype(int) + 1
            out.loc[miss, "available_from"] = pd.to_datetime(by.astype(str), format="%Y") + pd.offsets.MonthEnd(3)

        out = out.sort_values(["stock_code", "bsns_year"]).reset_index(drop=True)
        return out
    finally:
        con.close()


def _compute_yoy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["stock_code", "bsns_year"]).copy()

    df["revenue_prev"] = df.groupby("stock_code")["revenue"].shift(1)
    df["op_income_prev"] = df.groupby("stock_code")["op_income"].shift(1)

    def safe_yoy(cur, prev):
        if pd.isna(cur) or pd.isna(prev):
            return np.nan
        if prev == 0:
            return np.nan
        return (cur / prev) - 1.0

    df["revenue_yoy"] = [safe_yoy(c, p) for c, p in zip(df["revenue"], df["revenue_prev"])]
    df["op_income_yoy"] = [safe_yoy(c, p) for c, p in zip(df["op_income"], df["op_income_prev"])]

    return df


def _score_monthly(month_ends: pd.Series, annual: pd.DataFrame) -> pd.DataFrame:
    """
    월말 날짜마다 available_from <= month_end인 최신 연간 레코드를 붙여 스코어 생성.
    """
    if month_ends is None or len(month_ends) == 0:
        return pd.DataFrame(columns=["date","ticker","corp_name","bsns_year","available_from","revenue_yoy","op_income_yoy","growth_score"])

    month_ends_dt = pd.to_datetime(month_ends)
    annual = annual.copy()
    annual["available_from"] = pd.to_datetime(annual["available_from"])
    annual["bsns_year"] = annual["bsns_year"].astype(int)

    annual = annual.sort_values(["stock_code", "available_from"])

    rows = []
    for dt in month_ends_dt:
        a = annual[annual["available_from"] <= dt].copy()
        if a.empty:
            continue

        latest = a.groupby("stock_code", as_index=False).tail(1).copy()

        latest["rev_rank"] = latest["revenue_yoy"].rank(ascending=False, method="average", na_option="bottom")
        latest["op_rank"] = latest["op_income_yoy"].rank(ascending=False, method="average", na_option="bottom")
        latest["growth_score"] = 0.7 * latest["rev_rank"] + 0.3 * latest["op_rank"]

        latest["date"] = dt.strftime("%Y-%m-%d")
        rows.append(
            latest[["date", "stock_code", "corp_name", "bsns_year", "available_from", "revenue_yoy", "op_income_yoy", "growth_score"]]
        )

    if not rows:
        return pd.DataFrame(columns=["date","ticker","corp_name","bsns_year","available_from","revenue_yoy","op_income_yoy","growth_score"])

    out = pd.concat(rows, ignore_index=True)
    out = out.rename(columns={"stock_code": "ticker"})
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["available_from"] = pd.to_datetime(out["available_from"]).dt.strftime("%Y-%m-%d")
    return out.sort_values(["date", "growth_score"]).reset_index(drop=True)


def _ensure_out_table(con: sqlite3.Connection, table: str) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            corp_name TEXT,
            bsns_year INTEGER,
            available_from TEXT,
            revenue_yoy REAL,
            op_income_yoy REAL,
            growth_score REAL,
            PRIMARY KEY (date, ticker)
        )
        """
    )
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}(date)")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_ticker ON {table}(ticker)")
    con.commit()


def _upsert_sqlite(df: pd.DataFrame, out_db: str, table: str) -> int:
    Path(out_db).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out_db)
    try:
        _ensure_out_table(con, table)

        if df.empty:
            return 0

        cols = ["date","ticker","corp_name","bsns_year","available_from","revenue_yoy","op_income_yoy","growth_score"]
        rows = df[cols].where(pd.notna(df[cols]), None).values.tolist()

        sql = f"""
        INSERT INTO {table} (date, ticker, corp_name, bsns_year, available_from, revenue_yoy, op_income_yoy, growth_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, ticker) DO UPDATE SET
            corp_name=excluded.corp_name,
            bsns_year=excluded.bsns_year,
            available_from=excluded.available_from,
            revenue_yoy=excluded.revenue_yoy,
            op_income_yoy=excluded.op_income_yoy,
            growth_score=excluded.growth_score
        """
        cur = con.cursor()
        cur.executemany(sql, rows)
        con.commit()
        return len(rows)
    finally:
        con.close()


def _cleanup_non_month_end_rows(out_db: str, table: str, price_db: str, price_table: str) -> int:
    """
    C안 정합성 강제(거래월말 기준):
    - out_table에 "거래월말(trading month-end; 해당 월의 마지막 거래일)"이 아닌 date가 섞여 있으면 삭제
    - 거래월말은 price_db.price_table의 월별 max(date)로 정의
    """
    con = sqlite3.connect(out_db)
    try:
        cur = con.cursor()

        # price_db를 attach 해서 월별 마지막 거래일 집합을 만든다.
        # (주의) ATTACH 경로에 작은따옴표가 있으면 SQL 깨질 수 있어 replace 처리
        price_db_sql = price_db.replace("'", "''")
        cur.execute(f"ATTACH DATABASE '{price_db_sql}' AS pricedb")

        # fundamentals 테이블의 date 범위만 대상으로 제한(성능/안전)
        row = cur.execute(f"SELECT MIN(date), MAX(date) FROM {table}").fetchone()
        min_d, max_d = row[0], row[1]

        if min_d is None or max_d is None:
            con.commit()
            cur2 = con.cursor()
            cur2.execute("DETACH DATABASE pricedb")
            con.commit()
            return 0

        # 월별 마지막 거래일 목록(해당 기간)
        # substr(date,1,7)로 월을 그룹핑
        delete_sql = f"""
        DELETE FROM {table}
        WHERE date IS NOT NULL
          AND date BETWEEN ? AND ?
          AND date NOT IN (
                SELECT MAX(date)
                FROM pricedb.{price_table}
                WHERE date BETWEEN ? AND ?
                GROUP BY substr(date,1,7)
          )
        """
        cur.execute(delete_sql, (min_d, max_d, min_d, max_d))
        n = cur.rowcount if cur.rowcount is not None else 0
        
        # ✅ DETACH 전에 먼저 commit (트랜잭션 종료)
        con.commit()

        # ✅ 커서를 새로 만들어 DETACH (statement 정리 확실히)
        cur2 = con.cursor()
        cur2.execute("DETACH DATABASE pricedb")
        con.commit()
        return int(n)
    
    finally:
        con.close()

def _recreate_views(out_db: str, base_table: str) -> None:
    """
    백테스트 계약 안정화:
    - s2_fund_scores_monthly: (date별 growth_score 오름차순 rank) + valid_fund + score_rank
    - vw_s2_top30_monthly: valid_fund=1 & score_rank<=30

    주의: 과거에 동일 이름이 TABLE로 생성되어 있을 수 있어,
          sqlite_master를 확인해 VIEW/TABLE을 안전하게 정리한다.
    """
    def _object_type(cur: sqlite3.Cursor, name: str) -> str | None:
        row = cur.execute(
            "SELECT type FROM sqlite_master WHERE name=? AND type IN ('table','view')",
            (name,),
        ).fetchone()
        return row[0] if row else None

    def _drop_or_rename(cur: sqlite3.Cursor, name: str) -> None:
        t = _object_type(cur, name)
        if t is None:
            return
        if t == "view":
            cur.execute(f"DROP VIEW IF EXISTS {name}")
            return
        if t == "table":
            # 안전하게 백업(rename) 후 진행
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            legacy = f"{name}__legacy_{ts}"
            cur.execute(f"ALTER TABLE {name} RENAME TO {legacy}")
            print(f"[CLEAN] renamed legacy table -> {legacy}")
            return

    con = sqlite3.connect(out_db)
    try:
        cur = con.cursor()

        # 기존 오브젝트(뷰/테이블) 충돌 제거(테이블이면 rename 백업)
        _drop_or_rename(cur, "s2_fund_scores_monthly")
        _drop_or_rename(cur, "vw_s2_top30_monthly")

        # View 재생성
        cur.execute(
            f"""
            CREATE VIEW s2_fund_scores_monthly AS
            SELECT
                date,
                ticker,
                corp_name,
                revenue_yoy,
                op_income_yoy,
                growth_score,
                CASE
                    WHEN growth_score IS NOT NULL THEN 1
                    ELSE 0
                END AS valid_fund,
                ROW_NUMBER() OVER (PARTITION BY date ORDER BY growth_score ASC) AS score_rank
            FROM {base_table}
            """
        )

        cur.execute(
            """
            CREATE VIEW vw_s2_top30_monthly AS
            SELECT *
            FROM s2_fund_scores_monthly
            WHERE valid_fund = 1
              AND score_rank <= 30
            """
        )

        con.commit()
    finally:
        con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dart-db", required=True)
    ap.add_argument("--universe-file", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--price-db", required=True)
    ap.add_argument("--price-table", default="prices_daily")
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")  # optional
    ap.add_argument("--out-db", default=r"D:\Quant\data\db\fundamentals.db")
    ap.add_argument("--out-table", default="fundamentals_monthly")
    ap.add_argument("--incremental", action="store_true", default=True, help="only append/update new months after existing max(date)")
    args = ap.parse_args()

    tickers = _load_universe_tickers(args.universe_file, args.ticker_col)
    print(f"[INFO] tickers={len(tickers)}")

    # end auto/clamp by price db max(date)
    price_db_max = _get_db_max_date(args.price_db, args.price_table, "date")
    if price_db_max is None:
        raise RuntimeError(f"[FAIL] price db has no data: {args.price_db}::{args.price_table}")

    if args.end.strip():
        req_end = _fmt_ymd(_parse_ymd(args.end))
        db_end = _fmt_ymd(_parse_ymd(price_db_max))
        if _parse_ymd(req_end) > _parse_ymd(db_end):
            print(f"[WARN] end({req_end}) > price_db_max({db_end}). Using end={db_end}")
            end = db_end
        else:
            end = req_end
    else:
        end = _fmt_ymd(_parse_ymd(price_db_max))
        print(f"[INFO] --end not provided. Using price_db_max(date)={end}")

    start = args.start.strip() or None

    # C안 정합성: 기존 테이블에 비월말 date가 있으면 삭제
    if _table_exists(args.out_db, args.out_table):
        removed = _cleanup_non_month_end_rows(args.out_db, args.out_table, args.price_db, args.price_table)
        if removed > 0:
            print(f"[CLEAN] removed non-trading-month-end rows: {removed} from {args.out_table}")

    # incremental month ends
    existing_max = None
    if args.incremental and _table_exists(args.out_db, args.out_table):
        existing_max = _get_db_max_date(args.out_db, args.out_table, "date")
        if existing_max:
            print(f"[INFO] out_table exists. max(date)={existing_max} (incremental enabled)")
            # 신규 월만 만들기 위해 start를 기존 max 다음날로 설정
            d = _parse_ymd(existing_max)
            start = _fmt_ymd(d + pd.Timedelta(days=1))  # safe
        else:
            print("[INFO] out_table exists but empty. full build.")
            existing_max = None

    month_ends = _get_month_end_dates(args.price_db, args.price_table, start, end)
    if month_ends.empty:
        print("[INFO] no month_end_dates to process (already up-to-date or no price data).")
        # 그래도 뷰는 base_table 기준으로 존재/정합을 보장
        if _table_exists(args.out_db, args.out_table):
            _recreate_views(args.out_db, args.out_table)
            print(f"[DONE] refreshed views on {args.out_db} (base={args.out_table})")
        return

    print(f"[INFO] month_end_dates={len(month_ends)} | {month_ends.iloc[0]}..{month_ends.iloc[-1]}")

    annual = _load_annual_with_available_from(args.dart_db, tickers)
    annual = _compute_yoy(annual)

    print(f"[INFO] annual rows={len(annual):,} | years={annual.bsns_year.min()}..{annual.bsns_year.max()}")
    print("[INFO] build monthly fundamental features (as-of month-end, no lookahead)")

    monthly = _score_monthly(month_ends, annual)
    if monthly.empty:
        print("[WARN] monthly result empty. nothing to save.")
        # 그래도 뷰는 base_table 기준으로 존재/정합을 보장
        if _table_exists(args.out_db, args.out_table):
            _recreate_views(args.out_db, args.out_table)
            print(f"[DONE] refreshed views on {args.out_db} (base={args.out_table})")
        return

    print(f"[INFO] monthly rows={len(monthly):,} | dates={monthly['date'].min()}..{monthly['date'].max()}")

    n = _upsert_sqlite(monthly, args.out_db, args.out_table)
    print(f"[DONE] upserted_rows={n:,} -> {args.out_db}::{args.out_table}")

    # C안: latest base_table 기준으로 view를 항상 최신화
    _recreate_views(args.out_db, args.out_table)
    print(f"[DONE] refreshed views on {args.out_db} (base={args.out_table})")


if __name__ == "__main__":
    main()
