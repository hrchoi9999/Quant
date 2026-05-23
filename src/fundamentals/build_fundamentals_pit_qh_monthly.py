from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.dart_financials import extract_fs_annual_metrics  # noqa: E402
from src.fundamentals.build_fundamentals_monthly import (  # noqa: E402
    _connect,
    _fmt_ymd,
    _get_db_max_date,
    _get_month_end_dates,
    _load_universe_tickers,
    _parse_ymd,
    _table_exists,
)


TABLE_PIT = "fundamentals_pit_qh_mix400_latest"


DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_PIT} (
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    corp_name TEXT,

    annual_bsns_year INTEGER,
    annual_available_from TEXT,
    annual_report_code TEXT,
    annual_revenue_yoy REAL,
    annual_op_income_yoy REAL,

    half_bsns_year INTEGER,
    half_available_from TEXT,
    half_report_code TEXT,
    half_revenue_yoy REAL,
    half_op_income_yoy REAL,

    quarter_bsns_year INTEGER,
    quarter_available_from TEXT,
    quarter_report_code TEXT,
    quarter_label TEXT,
    q_revenue_yoy REAL,
    q_op_income_yoy REAL,
    q_revenue_yoy_delta_1q REAL,
    q_op_income_yoy_delta_1q REAL,

    has_annual INTEGER,
    has_half INTEGER,
    has_quarter INTEGER,
    coverage_score REAL,

    annual_component REAL,
    half_component REAL,
    quarter_component REAL,
    accel_component REAL,
    pit_growth_score REAL,

    PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_{TABLE_PIT}_date ON {TABLE_PIT}(date);
CREATE INDEX IF NOT EXISTS idx_{TABLE_PIT}_ticker ON {TABLE_PIT}(ticker);
"""


def _load_ticker_map(dart_db: str, tickers: list[str]) -> pd.DataFrame:
    con = _connect(dart_db)
    try:
        ph = ",".join(["?"] * len(tickers))
        df = pd.read_sql_query(
            f"""
            SELECT corp_code, corp_name, stock_code
            FROM dim_corp_listed
            WHERE stock_code IN ({ph})
            """,
            con,
            params=tickers,
        )
    finally:
        con.close()
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    return df.rename(columns={"stock_code": "ticker"})


def _load_report_accounts(dart_db: str, tickers: list[str]) -> pd.DataFrame:
    con = _connect(dart_db)
    try:
        ph = ",".join(["?"] * len(tickers))
        df = pd.read_sql_query(
            f"""
            SELECT
                d.stock_code AS ticker,
                d.corp_name,
                fr.rcept_no,
                fr.reprt_code,
                fr.bsns_year,
                fr.corp_code,
                fr.fs_div,
                ffa.sj_div,
                ffa.sj_nm,
                ffa.account_id,
                ffa.account_nm,
                ffa.account_detail,
                ffa.ord,
                ffa.currency,
                ffa.thstrm_nm,
                ffa.thstrm_amount,
                ffa.frmtrm_nm,
                ffa.frmtrm_amount
            FROM fact_report fr
            JOIN fact_fs_account ffa
              ON fr.rcept_no = ffa.rcept_no
             AND fr.fs_div = ffa.fs_div
            JOIN dim_corp_listed d
              ON fr.corp_code = d.corp_code
            WHERE d.stock_code IN ({ph})
              AND fr.reprt_code IN ('11011', '11012', '11013', '11014')
            ORDER BY d.stock_code, fr.bsns_year, fr.reprt_code, fr.rcept_no, ffa.ord
            """,
            con,
            params=tickers,
        )
    finally:
        con.close()
    if df.empty:
        return df
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["available_from"] = pd.to_datetime(df["rcept_no"].astype(str).str.slice(0, 8), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["available_from"]).copy()
    return df


def _extract_report_metrics(report_accounts: pd.DataFrame) -> pd.DataFrame:
    if report_accounts.empty:
        return pd.DataFrame(
            columns=[
                "ticker", "corp_name", "bsns_year", "reprt_code", "corp_code", "fs_div",
                "available_from", "revenue_cum", "op_income_cum",
            ]
        )

    rows: list[dict[str, object]] = []
    key_cols = ["ticker", "corp_name", "bsns_year", "reprt_code", "corp_code", "fs_div", "rcept_no", "available_from"]
    for key, grp in report_accounts.groupby(key_cols, sort=False):
        (
            ticker,
            corp_name,
            bsns_year,
            reprt_code,
            corp_code,
            fs_div,
            _rcept_no,
            available_from,
        ) = key
        metrics = extract_fs_annual_metrics(grp.copy())
        rows.append(
            {
                "ticker": str(ticker).zfill(6),
                "corp_name": corp_name,
                "bsns_year": int(bsns_year),
                "reprt_code": str(reprt_code),
                "corp_code": corp_code,
                "fs_div": fs_div,
                "available_from": pd.to_datetime(available_from),
                "revenue_cum": metrics.get("revenue"),
                "op_income_cum": metrics.get("op_income"),
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values(["ticker", "bsns_year", "reprt_code", "available_from"]).reset_index(drop=True)


def _safe_yoy(cur: object, prev: object) -> float | None:
    if pd.isna(cur) or pd.isna(prev):
        return None
    cur_v = float(cur)
    prev_v = float(prev)
    if prev_v == 0:
        return None
    return (cur_v / prev_v) - 1.0


def _quarter_idx(label: str) -> int:
    return {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(str(label), 0)


def _derive_annual_yoy(metrics: pd.DataFrame) -> pd.DataFrame:
    annual = metrics[metrics["reprt_code"] == "11011"].copy()
    if annual.empty:
        return pd.DataFrame(columns=["ticker"])
    annual = annual.sort_values(["ticker", "bsns_year", "available_from"])
    annual["annual_revenue_prev"] = annual.groupby("ticker")["revenue_cum"].shift(1)
    annual["annual_op_income_prev"] = annual.groupby("ticker")["op_income_cum"].shift(1)
    annual["annual_revenue_yoy"] = [
        _safe_yoy(c, p) for c, p in zip(annual["revenue_cum"], annual["annual_revenue_prev"])
    ]
    annual["annual_op_income_yoy"] = [
        _safe_yoy(c, p) for c, p in zip(annual["op_income_cum"], annual["annual_op_income_prev"])
    ]
    annual["annual_report_code"] = "11011"
    annual["annual_available_from"] = annual["available_from"]
    annual["annual_bsns_year"] = annual["bsns_year"]
    cols = [
        "ticker", "corp_name", "annual_bsns_year", "annual_available_from", "annual_report_code",
        "annual_revenue_yoy", "annual_op_income_yoy",
    ]
    return annual[cols].copy()


def _derive_half_yoy(metrics: pd.DataFrame) -> pd.DataFrame:
    half = metrics[metrics["reprt_code"] == "11012"].copy()
    if half.empty:
        return pd.DataFrame(columns=["ticker"])
    half = half.sort_values(["ticker", "bsns_year", "available_from"])
    half["half_revenue_prev"] = half.groupby("ticker")["revenue_cum"].shift(1)
    half["half_op_income_prev"] = half.groupby("ticker")["op_income_cum"].shift(1)
    half["half_revenue_yoy"] = [
        _safe_yoy(c, p) for c, p in zip(half["revenue_cum"], half["half_revenue_prev"])
    ]
    half["half_op_income_yoy"] = [
        _safe_yoy(c, p) for c, p in zip(half["op_income_cum"], half["half_op_income_prev"])
    ]
    half["half_report_code"] = "11012"
    half["half_available_from"] = half["available_from"]
    half["half_bsns_year"] = half["bsns_year"]
    cols = [
        "ticker", "corp_name", "half_bsns_year", "half_available_from", "half_report_code",
        "half_revenue_yoy", "half_op_income_yoy",
    ]
    return half[cols].copy()


def _derive_quarter_period(metrics: pd.DataFrame) -> pd.DataFrame:
    q1 = metrics[metrics["reprt_code"] == "11013"][
        ["ticker", "corp_name", "bsns_year", "available_from", "revenue_cum", "op_income_cum"]
    ].copy()
    h1 = metrics[metrics["reprt_code"] == "11012"][
        ["ticker", "corp_name", "bsns_year", "available_from", "revenue_cum", "op_income_cum"]
    ].copy()
    q3c = metrics[metrics["reprt_code"] == "11014"][
        ["ticker", "corp_name", "bsns_year", "available_from", "revenue_cum", "op_income_cum"]
    ].copy()
    annual = metrics[metrics["reprt_code"] == "11011"][
        ["ticker", "corp_name", "bsns_year", "available_from", "revenue_cum", "op_income_cum"]
    ].copy()

    out_frames: list[pd.DataFrame] = []

    if not q1.empty:
        q1 = q1.rename(
            columns={
                "available_from": "quarter_available_from",
                "revenue_cum": "quarter_revenue",
                "op_income_cum": "quarter_op_income",
            }
        )
        q1["quarter_label"] = "Q1"
        q1["quarter_report_code"] = "11013"
        out_frames.append(q1)

    if not h1.empty and not q1.empty:
        q2 = h1.merge(
            q1[["ticker", "bsns_year", "quarter_revenue", "quarter_op_income"]],
            on=["ticker", "bsns_year"],
            how="inner",
            suffixes=("", "_q1"),
        )
        q2["quarter_revenue"] = q2["revenue_cum"] - q2["quarter_revenue"]
        q2["quarter_op_income"] = q2["op_income_cum"] - q2["quarter_op_income"]
        q2["quarter_label"] = "Q2"
        q2["quarter_report_code"] = "11012"
        q2 = q2.rename(columns={"available_from": "quarter_available_from"})
        out_frames.append(q2[["ticker", "corp_name", "bsns_year", "quarter_available_from", "quarter_revenue", "quarter_op_income", "quarter_label", "quarter_report_code"]])

    if not q3c.empty and not h1.empty:
        q3 = q3c.merge(
            h1[["ticker", "bsns_year", "revenue_cum", "op_income_cum"]],
            on=["ticker", "bsns_year"],
            how="inner",
            suffixes=("", "_h1"),
        )
        q3["quarter_revenue"] = q3["revenue_cum"] - q3["revenue_cum_h1"]
        q3["quarter_op_income"] = q3["op_income_cum"] - q3["op_income_cum_h1"]
        q3["quarter_label"] = "Q3"
        q3["quarter_report_code"] = "11014"
        q3 = q3.rename(columns={"available_from": "quarter_available_from"})
        out_frames.append(q3[["ticker", "corp_name", "bsns_year", "quarter_available_from", "quarter_revenue", "quarter_op_income", "quarter_label", "quarter_report_code"]])

    if not annual.empty and not q3c.empty:
        q4 = annual.merge(
            q3c[["ticker", "bsns_year", "revenue_cum", "op_income_cum"]],
            on=["ticker", "bsns_year"],
            how="inner",
            suffixes=("", "_q3"),
        )
        q4["quarter_revenue"] = q4["revenue_cum"] - q4["revenue_cum_q3"]
        q4["quarter_op_income"] = q4["op_income_cum"] - q4["op_income_cum_q3"]
        q4["quarter_label"] = "Q4"
        q4["quarter_report_code"] = "11011"
        q4 = q4.rename(columns={"available_from": "quarter_available_from"})
        out_frames.append(q4[["ticker", "corp_name", "bsns_year", "quarter_available_from", "quarter_revenue", "quarter_op_income", "quarter_label", "quarter_report_code"]])

    if not out_frames:
        return pd.DataFrame(columns=["ticker"])

    quarter = pd.concat(out_frames, ignore_index=True)
    quarter = quarter.sort_values(["ticker", "bsns_year", "quarter_label", "quarter_available_from"])
    quarter["quarter_idx"] = quarter["quarter_label"].map(_quarter_idx)
    quarter["prev_key_year"] = quarter["bsns_year"] - 1

    prev = quarter[["ticker", "bsns_year", "quarter_label", "quarter_revenue", "quarter_op_income"]].rename(
        columns={
            "bsns_year": "prev_key_year",
            "quarter_revenue": "prev_quarter_revenue",
            "quarter_op_income": "prev_quarter_op_income",
        }
    )
    quarter = quarter.merge(prev, on=["ticker", "prev_key_year", "quarter_label"], how="left")
    quarter["q_revenue_yoy"] = [
        _safe_yoy(c, p) for c, p in zip(quarter["quarter_revenue"], quarter["prev_quarter_revenue"])
    ]
    quarter["q_op_income_yoy"] = [
        _safe_yoy(c, p) for c, p in zip(quarter["quarter_op_income"], quarter["prev_quarter_op_income"])
    ]

    quarter = quarter.sort_values(["ticker", "bsns_year", "quarter_idx"])
    quarter["q_revenue_yoy_delta_1q"] = quarter.groupby("ticker")["q_revenue_yoy"].diff(1)
    quarter["q_op_income_yoy_delta_1q"] = quarter.groupby("ticker")["q_op_income_yoy"].diff(1)

    quarter["quarter_bsns_year"] = quarter["bsns_year"]
    cols = [
        "ticker", "corp_name", "quarter_bsns_year", "quarter_available_from",
        "quarter_report_code", "quarter_label",
        "q_revenue_yoy", "q_op_income_yoy",
        "q_revenue_yoy_delta_1q", "q_op_income_yoy_delta_1q",
    ]
    return quarter[cols].copy()


def _merge_asof_by_ticker(base: pd.DataFrame, src: pd.DataFrame, on_col: str, out_cols: list[str]) -> pd.DataFrame:
    if src.empty:
        out = base[["date", "ticker"]].copy()
        for c in out_cols:
            out[c] = np.nan
        return out

    pieces: list[pd.DataFrame] = []
    for ticker, base_grp in base.groupby("ticker", sort=False):
        src_grp = src[src["ticker"] == ticker].sort_values(on_col)
        b = base_grp.sort_values("date")[["date", "ticker"]].copy()
        if src_grp.empty:
            for c in out_cols:
                b[c] = np.nan
            pieces.append(b)
            continue
        select_cols = ["ticker", on_col] + [c for c in out_cols if c != on_col]
        merged = pd.merge_asof(
            b,
            src_grp[select_cols].sort_values(on_col),
            left_on="date",
            right_on=on_col,
            by="ticker",
            direction="backward",
            allow_exact_matches=True,
        )
        pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


def _build_snapshot(
    month_ends: pd.Series,
    ticker_map: pd.DataFrame,
    annual_yoy: pd.DataFrame,
    half_yoy: pd.DataFrame,
    quarter_yoy: pd.DataFrame,
    annual_weight: float,
    half_weight: float,
    quarter_weight: float,
    accel_weight: float,
) -> pd.DataFrame:
    base = pd.MultiIndex.from_product(
        [pd.to_datetime(month_ends), sorted(ticker_map["ticker"].astype(str).unique())],
        names=["date", "ticker"],
    ).to_frame(index=False)
    base = base.merge(ticker_map[["ticker", "corp_name"]], on="ticker", how="left")

    annual_cols = [
        "annual_bsns_year", "annual_available_from", "annual_report_code",
        "annual_revenue_yoy", "annual_op_income_yoy",
    ]
    half_cols = [
        "half_bsns_year", "half_available_from", "half_report_code",
        "half_revenue_yoy", "half_op_income_yoy",
    ]
    quarter_cols = [
        "quarter_bsns_year", "quarter_available_from", "quarter_report_code", "quarter_label",
        "q_revenue_yoy", "q_op_income_yoy", "q_revenue_yoy_delta_1q", "q_op_income_yoy_delta_1q",
    ]

    annual_snap = _merge_asof_by_ticker(base, annual_yoy, "annual_available_from", annual_cols)
    half_snap = _merge_asof_by_ticker(base, half_yoy, "half_available_from", half_cols)
    quarter_snap = _merge_asof_by_ticker(base, quarter_yoy, "quarter_available_from", quarter_cols)

    out = base.merge(annual_snap, on=["date", "ticker"], how="left")
    out = out.merge(half_snap, on=["date", "ticker"], how="left")
    out = out.merge(quarter_snap, on=["date", "ticker"], how="left")

    out["has_annual"] = out["annual_revenue_yoy"].notna().astype(int)
    out["has_half"] = out["half_revenue_yoy"].notna().astype(int)
    out["has_quarter"] = out["q_revenue_yoy"].notna().astype(int)
    out["coverage_score"] = (
        0.4 * out["has_annual"]
        + 0.3 * out["has_half"]
        + 0.3 * out["has_quarter"]
    )

    def _rank_desc(series: pd.Series) -> pd.Series:
        return series.rank(ascending=False, method="average", na_option="bottom")

    out["annual_rev_rank"] = out.groupby("date")["annual_revenue_yoy"].transform(_rank_desc)
    out["annual_op_rank"] = out.groupby("date")["annual_op_income_yoy"].transform(_rank_desc)
    out["half_rev_rank"] = out.groupby("date")["half_revenue_yoy"].transform(_rank_desc)
    out["half_op_rank"] = out.groupby("date")["half_op_income_yoy"].transform(_rank_desc)
    out["quarter_rev_rank"] = out.groupby("date")["q_revenue_yoy"].transform(_rank_desc)
    out["quarter_op_rank"] = out.groupby("date")["q_op_income_yoy"].transform(_rank_desc)
    out["accel_rev_rank"] = out.groupby("date")["q_revenue_yoy_delta_1q"].transform(_rank_desc)
    out["accel_op_rank"] = out.groupby("date")["q_op_income_yoy_delta_1q"].transform(_rank_desc)

    out["annual_component"] = 0.7 * out["annual_rev_rank"] + 0.3 * out["annual_op_rank"]
    out["half_component"] = 0.6 * out["half_rev_rank"] + 0.4 * out["half_op_rank"]
    out["quarter_component"] = 0.6 * out["quarter_rev_rank"] + 0.4 * out["quarter_op_rank"]
    out["accel_component"] = 0.4 * out["accel_rev_rank"] + 0.6 * out["accel_op_rank"]

    out["pit_growth_score"] = (
        annual_weight * out["annual_component"]
        + half_weight * out["half_component"]
        + quarter_weight * out["quarter_component"]
        + accel_weight * out["accel_component"]
    )
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    for col in ["annual_available_from", "half_available_from", "quarter_available_from"]:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")

    keep_cols = [
        "date", "ticker", "corp_name",
        "annual_bsns_year", "annual_available_from", "annual_report_code", "annual_revenue_yoy", "annual_op_income_yoy",
        "half_bsns_year", "half_available_from", "half_report_code", "half_revenue_yoy", "half_op_income_yoy",
        "quarter_bsns_year", "quarter_available_from", "quarter_report_code", "quarter_label",
        "q_revenue_yoy", "q_op_income_yoy", "q_revenue_yoy_delta_1q", "q_op_income_yoy_delta_1q",
        "has_annual", "has_half", "has_quarter", "coverage_score",
        "annual_component", "half_component", "quarter_component", "accel_component", "pit_growth_score",
    ]
    return out[keep_cols].sort_values(["date", "pit_growth_score", "ticker"]).reset_index(drop=True)


def _ensure_table(con: sqlite3.Connection) -> None:
    con.executescript(DDL)
    con.commit()


def _upsert(df: pd.DataFrame, out_db: str) -> int:
    con = sqlite3.connect(out_db)
    try:
        _ensure_table(con)
        if df.empty:
            return 0
        cols = list(df.columns)
        rows = df[cols].where(pd.notna(df[cols]), None).values.tolist()
        placeholders = ",".join(["?"] * len(cols))
        update_cols = [c for c in cols if c not in {"date", "ticker"}]
        updates = ",".join([f"{c}=excluded.{c}" for c in update_cols])
        sql = (
            f"INSERT INTO {TABLE_PIT} ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(date, ticker) DO UPDATE SET {updates}"
        )
        con.executemany(sql, rows)
        con.commit()
        return len(rows)
    finally:
        con.close()


def _cleanup_non_month_end_rows(out_db: str, table: str, price_db: str, price_table: str) -> int:
    con = sqlite3.connect(out_db)
    try:
        cur = con.cursor()
        price_db_sql = price_db.replace("'", "''")
        cur.execute(f"ATTACH DATABASE '{price_db_sql}' AS pricedb")
        min_d, max_d = cur.execute(f"SELECT MIN(date), MAX(date) FROM {table}").fetchone()
        if min_d is None or max_d is None:
            con.commit()
            cur2 = con.cursor()
            cur2.execute("DETACH DATABASE pricedb")
            con.commit()
            return 0
        cur.execute(
            f"""
            DELETE FROM {table}
            WHERE date BETWEEN ? AND ?
              AND date NOT IN (
                    SELECT MAX(date)
                    FROM pricedb.{price_table}
                    WHERE date BETWEEN ? AND ?
                    GROUP BY substr(date,1,7)
              )
            """,
            (min_d, max_d, min_d, max_d),
        )
        n = cur.rowcount if cur.rowcount is not None else 0
        con.commit()
        cur2 = con.cursor()
        cur2.execute("DETACH DATABASE pricedb")
        con.commit()
        return int(n)
    finally:
        con.close()


def _recreate_views(out_db: str, base_table: str, min_coverage: float) -> None:
    con = sqlite3.connect(out_db)
    try:
        cur = con.cursor()
        cur.execute("DROP VIEW IF EXISTS s2_fund_scores_pit_monthly")
        cur.execute("DROP VIEW IF EXISTS vw_s2_pit_top30_monthly")
        cur.execute(
            f"""
            CREATE VIEW s2_fund_scores_pit_monthly AS
            SELECT
                date,
                ticker,
                corp_name,
                annual_revenue_yoy,
                annual_op_income_yoy,
                half_revenue_yoy,
                half_op_income_yoy,
                q_revenue_yoy,
                q_op_income_yoy,
                q_revenue_yoy_delta_1q,
                q_op_income_yoy_delta_1q,
                coverage_score,
                pit_growth_score,
                pit_growth_score AS growth_score,
                CASE
                    WHEN pit_growth_score IS NOT NULL
                     AND has_annual = 1
                     AND coverage_score >= {float(min_coverage)}
                    THEN 1 ELSE 0
                END AS valid_fund,
                ROW_NUMBER() OVER (PARTITION BY date ORDER BY pit_growth_score ASC) AS score_rank
            FROM {base_table}
            """
        )
        cur.execute(
            """
            CREATE VIEW vw_s2_pit_top30_monthly AS
            SELECT *
            FROM s2_fund_scores_pit_monthly
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
    ap.add_argument("--end", default="")
    ap.add_argument("--out-db", default=r"D:\Quant\data\db\fundamentals.db")
    ap.add_argument("--out-table", default=TABLE_PIT)
    ap.add_argument("--incremental", action="store_true", default=True)
    ap.add_argument("--annual-weight", type=float, default=0.45)
    ap.add_argument("--half-weight", type=float, default=0.15)
    ap.add_argument("--quarter-weight", type=float, default=0.25)
    ap.add_argument("--accel-weight", type=float, default=0.15)
    ap.add_argument("--min-coverage", type=float, default=0.7)
    args = ap.parse_args()

    weight_sum = args.annual_weight + args.half_weight + args.quarter_weight + args.accel_weight
    if abs(weight_sum - 1.0) > 1e-9:
        raise ValueError(f"weights must sum to 1.0, got {weight_sum}")

    tickers = _load_universe_tickers(args.universe_file, args.ticker_col)
    print(f"[INFO] tickers={len(tickers)}")

    price_db_max = _get_db_max_date(args.price_db, args.price_table, "date")
    if price_db_max is None:
        raise RuntimeError(f"[FAIL] price db has no data: {args.price_db}::{args.price_table}")

    if args.end.strip():
        req_end = _fmt_ymd(_parse_ymd(args.end))
        db_end = _fmt_ymd(_parse_ymd(price_db_max))
        end = db_end if _parse_ymd(req_end) > _parse_ymd(db_end) else req_end
    else:
        end = _fmt_ymd(_parse_ymd(price_db_max))
        print(f"[INFO] --end not provided. Using price_db_max(date)={end}")

    start = args.start.strip() or None

    if _table_exists(args.out_db, args.out_table):
        removed = _cleanup_non_month_end_rows(args.out_db, args.out_table, args.price_db, args.price_table)
        if removed > 0:
            print(f"[CLEAN] removed non-trading-month-end rows: {removed} from {args.out_table}")

    if args.incremental and _table_exists(args.out_db, args.out_table):
        existing_max = _get_db_max_date(args.out_db, args.out_table, "date")
        if existing_max:
            print(f"[INFO] out_table exists. max(date)={existing_max} (incremental enabled)")
            start = _fmt_ymd(_parse_ymd(existing_max) + pd.Timedelta(days=1))

    month_ends = _get_month_end_dates(args.price_db, args.price_table, start, end)
    if month_ends.empty:
        print("[INFO] no month_end_dates to process.")
        if _table_exists(args.out_db, args.out_table):
            _recreate_views(args.out_db, args.out_table, float(args.min_coverage))
            print(f"[DONE] refreshed PIT views on {args.out_db} (base={args.out_table})")
        return

    print(f"[INFO] month_end_dates={len(month_ends)} | {month_ends.iloc[0]}..{month_ends.iloc[-1]}")

    ticker_map = _load_ticker_map(args.dart_db, tickers)
    report_accounts = _load_report_accounts(args.dart_db, tickers)
    report_metrics = _extract_report_metrics(report_accounts)
    print(f"[INFO] report_metrics rows={len(report_metrics):,}")

    annual_yoy = _derive_annual_yoy(report_metrics)
    half_yoy = _derive_half_yoy(report_metrics)
    quarter_yoy = _derive_quarter_period(report_metrics)
    print(
        "[INFO] derived panels | "
        f"annual={len(annual_yoy):,} half={len(half_yoy):,} quarter={len(quarter_yoy):,}"
    )

    snapshot = _build_snapshot(
        month_ends=month_ends,
        ticker_map=ticker_map,
        annual_yoy=annual_yoy,
        half_yoy=half_yoy,
        quarter_yoy=quarter_yoy,
        annual_weight=float(args.annual_weight),
        half_weight=float(args.half_weight),
        quarter_weight=float(args.quarter_weight),
        accel_weight=float(args.accel_weight),
    )

    if snapshot.empty:
        print("[WARN] PIT snapshot result empty.")
        return

    print(
        f"[INFO] snapshot rows={len(snapshot):,} | "
        f"dates={snapshot['date'].min()}..{snapshot['date'].max()} | "
        f"tickers={snapshot['ticker'].nunique()}"
    )

    n = _upsert(snapshot, args.out_db)
    print(f"[DONE] upserted_rows={n:,} -> {args.out_db}::{args.out_table}")

    _recreate_views(args.out_db, args.out_table, float(args.min_coverage))
    print(f"[DONE] refreshed PIT views on {args.out_db} (base={args.out_table})")


if __name__ == "__main__":
    main()
