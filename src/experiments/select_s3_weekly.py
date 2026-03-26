# select_s3_weekly.py ver 2026-02-25_001

import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")

UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
FEATURES_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"

TABLE_PRICE = "s3_price_features_daily"
TABLE_FUND = "s3_fund_features_monthly"

OUTDIR = PROJECT_ROOT / r"reports\backtest_s3_dev"


def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


def _load_universe() -> pd.DataFrame:
    u = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    u["ticker"] = u["ticker"].astype(str).str.zfill(6)
    return u


def _pick_latest_fund_asof(con: sqlite3.Connection, asof: str) -> pd.DataFrame:
    """
    룩어헤드 방지:
    - available_from <= asof 조건 만족하는 것 중
    - ticker별로 available_from(또는 date) 기준 최신 1행 선택
    """
    q = f"""
    SELECT date, ticker, available_from, growth_score, gs_delta_3m, fund_accel_score
    FROM {TABLE_FUND}
    WHERE available_from <= ?
    """
    f = pd.read_sql_query(q, con, params=[asof])
    if f.empty:
        return f

    f["ticker"] = f["ticker"].astype(str).str.zfill(6)
    # 최신 선택 기준: available_from 우선, 다음 date
    f["_af"] = pd.to_datetime(f["available_from"], errors="coerce")
    f["_dt"] = pd.to_datetime(f["date"], errors="coerce")
    f = f.sort_values(["ticker", "_af", "_dt"])
    f = f.groupby("ticker", as_index=False).tail(1).drop(columns=["_af", "_dt"])
    return f


def _pick_price_asof(con: sqlite3.Connection, asof: str) -> pd.DataFrame:
    """
    asof 당일이 비거래일일 수 있으니, date <= asof 중 ticker별 최신 1행 사용
    """
    q = f"""
    SELECT ticker, date, adv20, adv60, vol_ratio_20, mom20, breakout60, value_won
    FROM {TABLE_PRICE}
    WHERE date <= ?
    """
    p = pd.read_sql_query(q, con, params=[asof])
    if p.empty:
        return p

    p["ticker"] = p["ticker"].astype(str).str.zfill(6)
    p["_dt"] = pd.to_datetime(p["date"], errors="coerce")
    p = p.sort_values(["ticker", "_dt"])
    p = p.groupby("ticker", as_index=False).tail(1).drop(columns=["_dt"])
    return p


def select(asof: str = "2026-02-23", top_n: int = 30) -> pd.DataFrame:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    u = _load_universe()[["ticker", "name", "market", "mcap", "asof"]].copy()

    con = sqlite3.connect(str(FEATURES_DB))
    try:
        f = _pick_latest_fund_asof(con, asof)
        p = _pick_price_asof(con, asof)
    finally:
        con.close()

    if p.empty:
        raise RuntimeError("No price features found for asof. Run build_s3_price_features_daily.py first.")
    if f.empty:
        raise RuntimeError("No fund features found for asof. Run build_s3_fund_features_monthly.py first.")

    df = u.merge(p, on="ticker", how="left").merge(f, on="ticker", how="left")

    # 결측 처리: PoC에서는 결측 많은 종목은 불리하게(=rank 낮게) 두는 편이 안전
    # 점수 구성(동일 유니버스에서 S2와 차이 만드는 목적)
    df["fund_level_pct"] = _pct_rank(df["growth_score"])
    df["fund_accel_pct"] = _pct_rank(df["fund_accel_score"])
    df["mom20_pct"] = _pct_rank(df["mom20"])
    df["vol_ratio_pct"] = _pct_rank(df["vol_ratio_20"])

    # breakout60은 0/1 그대로 쓰되, 보조 가점
    df["breakout60"] = df["breakout60"].fillna(0).astype(int)

    # 최종 스코어(가중치는 PoC용)
    df["s3_score"] = (
        0.35 * df["fund_level_pct"].fillna(0)
        + 0.25 * df["fund_accel_pct"].fillna(0)
        + 0.25 * df["mom20_pct"].fillna(0)
        + 0.10 * df["vol_ratio_pct"].fillna(0)
        + 0.05 * df["breakout60"]
    )

    # 정렬/선정
    sel = df.sort_values("s3_score", ascending=False).head(top_n).copy()
    sel.insert(0, "rank", range(1, len(sel) + 1))

    out_path = OUTDIR / f"s3_selection_top{top_n}_{asof}.csv"
    sel.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"[OK] wrote: {out_path}")
    print()
    print(sel[["rank","ticker","name","market","mcap","s3_score","growth_score","fund_accel_score","mom20","vol_ratio_20","breakout60"]].to_string(index=False))
    return sel


if __name__ == "__main__":
    # 기준일(asof)은 이미 확정: 2026-02-23
    select(asof="2026-02-23", top_n=30)