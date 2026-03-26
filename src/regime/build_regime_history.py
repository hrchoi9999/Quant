# build_regime_history.py ver 2026-02-05_003
# - Patch(1) pd.NA -> np.nan (dtype 안정화)
# - Patch(2) stack(future_stack=True) 호환성 fallback
# - Patch(3) --end 미지정/미래 지정 시 price.db max(date) 기반 자동 보정

from __future__ import annotations

import argparse
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


# -----------------------------
# Helpers
# -----------------------------
def zfill6(x: str) -> str:
    return str(x).strip().zfill(6)


def parse_ymd(s: str) -> date:
    s = str(s).strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def fmt_ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def get_db_max_date(db_path: Path, table: str, date_col: str = "date") -> Optional[str]:
    con = sqlite3.connect(str(db_path))
    try:
        q = f"select max({date_col}) as max_date from {table}"
        df = pd.read_sql_query(q, con)
        v = df.iloc[0]["max_date"]
        return str(v) if v is not None else None
    finally:
        con.close()


def stack_compat(df: pd.DataFrame) -> pd.Series:
    """pandas 버전 호환을 위한 stack wrapper (future_stack 지원/미지원 모두 대응)."""
    try:
        return df.stack(future_stack=True)
    except TypeError:
        return df.stack()


# -----------------------------
# SQLite adapter: numpy -> python primitives
# -----------------------------
def register_sqlite_adapters() -> None:
    # numpy scalar들이 sqlite에 BLOB로 들어가는 걸 방지
    sqlite3.register_adapter(np.int8, int)
    sqlite3.register_adapter(np.int16, int)
    sqlite3.register_adapter(np.int32, int)
    sqlite3.register_adapter(np.int64, int)
    sqlite3.register_adapter(np.uint8, int)
    sqlite3.register_adapter(np.uint16, int)
    sqlite3.register_adapter(np.uint32, int)
    sqlite3.register_adapter(np.uint64, int)
    sqlite3.register_adapter(np.float32, float)
    sqlite3.register_adapter(np.float64, float)


# -----------------------------
# Core
# -----------------------------
def read_universe_tickers(universe_file: Optional[Path], ticker_col: str) -> Optional[List[str]]:
    if not universe_file:
        return None
    df = pd.read_csv(universe_file, dtype={ticker_col: str})
    if ticker_col not in df.columns:
        raise KeyError(f"Universe file missing column '{ticker_col}': {universe_file}")
    ticks = df[ticker_col].astype(str).map(zfill6).dropna().unique().tolist()
    return sorted(ticks)


def load_prices_wide(
    price_db: Path,
    price_table: str,
    tickers: Optional[List[str]],
    start: str,
    end: str,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    prices_daily schema 가정: date(TEXT), ticker(TEXT), open/high/low/close/volume/value 등
    반환: index=date, columns=ticker, values=close(float)
    """
    con = sqlite3.connect(str(price_db))
    try:
        params = [start, end]
        where = "where date>=? and date<=?"
        if tickers:
            # chunk IN
            chunk = 900
            frames = []
            for i in range(0, len(tickers), chunk):
                part = tickers[i : i + chunk]
                qmarks = ",".join(["?"] * len(part))
                q = f"""
                    select date, ticker, {price_col} as px
                    from {price_table}
                    {where} and ticker in ({qmarks})
                    order by date, ticker
                """
                df = pd.read_sql_query(q, con, params=params + part)
                frames.append(df)
            raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "ticker", "px"])
        else:
            q = f"""
                select date, ticker, {price_col} as px
                from {price_table}
                {where}
                order by date, ticker
            """
            raw = pd.read_sql_query(q, con, params=params)

    finally:
        con.close()

    if raw.empty:
        return pd.DataFrame()

    raw["ticker"] = raw["ticker"].astype(str).map(zfill6)
    raw["date"] = raw["date"].astype(str)

    wide = raw.pivot(index="date", columns="ticker", values="px").sort_index()
    # Patch(1): 없는 티커 컬럼은 np.nan으로(절대 pd.NA 쓰지 않기)
    if tickers:
        for t in tickers:
            if t not in wide.columns:
                wide[t] = np.nan
        wide = wide[tickers]  # 컬럼 순서 고정
    # float 유지
    wide = wide.astype("float64")
    return wide


def compute_regime_for_horizon(wide: pd.DataFrame, horizon_days: int) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    간단한 레짐 산출:
    - ret: horizon 수익률 (px/px.shift(h)-1)
    - vol: 21일 수익률 표준편차 연환산
    - dd: horizon window 내 max 대비 낙폭의 최솟값(대략 MDD proxy)
    - score: ret를 cross-sectional percentile (0~1)
    """
    px = wide

    ret = px / px.shift(horizon_days) - 1.0

    r1 = px.pct_change()
    vol = r1.rolling(21, min_periods=10).std() * math.sqrt(252)

    roll_max = px.rolling(horizon_days, min_periods=10).max()
    dd = (px / roll_max - 1.0).rolling(horizon_days, min_periods=10).min()

    # score: cross-sectional percentile each date
    score = ret.rank(axis=1, pct=True)

    return ret, score, dd, vol


def score_to_regime(score: pd.DataFrame) -> pd.DataFrame:
    """
    score(0~1)를 5분위 레짐(0~4)으로 변환.
    """
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0000001]
    labels = [0, 1, 2, 3, 4]
    # vectorized apply per row is expensive; use numpy digitize on values
    arr = score.to_numpy(dtype="float64")
    # digitize returns 1..len(bins)-1
    idx = np.digitize(arr, bins, right=False) - 1
    # NaN은 -1로 들어올 수 있으니 NaN mask 적용
    nan_mask = np.isnan(arr)
    idx = idx.astype("int64")
    idx[nan_mask] = -1
    out = pd.DataFrame(idx, index=score.index, columns=score.columns)
    return out


def to_long(
    ret: pd.DataFrame,
    score: pd.DataFrame,
    regime: pd.DataFrame,
    dd: pd.DataFrame,
    vol: pd.DataFrame,
    horizon_label: str,
) -> pd.DataFrame:
    # Patch(2): stack future_stack fallback
    s_ret = stack_compat(ret).rename("ret")
    s_score = stack_compat(score).rename("score")
    s_reg = stack_compat(regime).rename("regime")
    s_dd = stack_compat(dd).rename("dd")
    s_vol = stack_compat(vol).rename("vol")

    df = pd.concat([s_ret, s_score, s_reg, s_dd, s_vol], axis=1).reset_index()
    df.columns = ["date", "ticker", "ret", "score", "regime", "dd", "vol"]
    df["date"] = df["date"].astype(str)
    df["ticker"] = df["ticker"].astype(str).map(zfill6)
    df["horizon"] = str(horizon_label)

    # sqlite 안전: numpy scalar를 python primitive로
    df["regime"] = df["regime"].astype("int64").map(int)
    df["ret"] = df["ret"].astype("float64").map(lambda x: float(x) if pd.notna(x) else None)
    df["score"] = df["score"].astype("float64").map(lambda x: float(x) if pd.notna(x) else None)
    df["dd"] = df["dd"].astype("float64").map(lambda x: float(x) if pd.notna(x) else None)
    df["vol"] = df["vol"].astype("float64").map(lambda x: float(x) if pd.notna(x) else None)

    return df


def ensure_regime_table(con: sqlite3.Connection, table: str) -> None:
    con.execute(
        f"""
        create table if not exists {table} (
            date    TEXT not null,
            ticker  TEXT not null,
            horizon TEXT not null,
            ret     REAL,
            score   REAL,
            regime  INTEGER,
            dd      REAL,
            vol     REAL,
            primary key (date, ticker, horizon)
        )
        """
    )
    con.commit()


def upsert_regime_history(regime_db: Path, table: str, df_long: pd.DataFrame, chunksize: int = 20000) -> int:
    if df_long.empty:
        return 0

    con = sqlite3.connect(str(regime_db))
    try:
        ensure_regime_table(con, table)

        rows = df_long[["date", "ticker", "horizon", "ret", "score", "regime", "dd", "vol"]].values.tolist()
        sql = f"""
            insert into {table} (date, ticker, horizon, ret, score, regime, dd, vol)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(date, ticker, horizon) do update set
                ret=excluded.ret,
                score=excluded.score,
                regime=excluded.regime,
                dd=excluded.dd,
                vol=excluded.vol
        """
        cur = con.cursor()
        total = 0
        for i in range(0, len(rows), chunksize):
            cur.executemany(sql, rows[i : i + chunksize])
            total += cur.rowcount if cur.rowcount != -1 else len(rows[i : i + chunksize])
            con.commit()

        return total
    finally:
        con.close()


def verify_no_blob(regime_db: Path, table: str) -> None:
    con = sqlite3.connect(str(regime_db))
    try:
        df = pd.read_sql_query(
            f"""
            select count(*) as blob_cnt
            from {table}
            where typeof(regime)='blob'
            """,
            con,
        )
        blob_cnt = int(df.iloc[0]["blob_cnt"])
        if blob_cnt > 0:
            raise RuntimeError(f"[FAIL] regime stored as BLOB rows={blob_cnt}. Please check adapters/casting.")
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()

    p.add_argument("--price-db", required=True)
    p.add_argument("--price-table", default="prices_daily")
    p.add_argument("--price-col", default="close")

    p.add_argument("--regime-db", required=True)
    p.add_argument("--regime-table", default="regime_history")

    p.add_argument("--universe-file", default="")
    p.add_argument("--ticker-col", default="ticker")

    p.add_argument("--years", type=int, default=10)
    # Patch(3): end 미지정 시 DB max(date)로 자동
    p.add_argument("--end", default="", help="YYYY-MM-DD or YYYYMMDD (optional). If empty, use price DB max(date).")

    # horizons (일수 기준) + label
    p.add_argument("--h1", type=int, default=252, help="1y horizon days")
    p.add_argument("--h2", type=int, default=126, help="6m horizon days")
    p.add_argument("--h3", type=int, default=63, help="3m horizon days")

    p.add_argument("--verify-no-blob", action="store_true", default=True)
    return p.parse_args()


def main() -> None:
    register_sqlite_adapters()
    args = parse_args()

    price_db = Path(args.price_db)
    regime_db = Path(args.regime_db)

    # Patch(3): end 자동 보정
    db_max = get_db_max_date(price_db, args.price_table, "date")
    if db_max is None:
        raise RuntimeError(f"price db has no data: {price_db}::{args.price_table}")

    if args.end:
        req_end = fmt_ymd(parse_ymd(args.end))
        db_end = fmt_ymd(parse_ymd(db_max))
        if parse_ymd(req_end) > parse_ymd(db_end):
            print(f"[WARN] end({req_end}) > price_db_max({db_end}). Using end={db_end}")
            end = db_end
        else:
            end = req_end
    else:
        end = fmt_ymd(parse_ymd(db_max))
        print(f"[INFO] --end not provided. Using price_db_max(date)={end}")

    end_d = parse_ymd(end)
    start_d = end_d - timedelta(days=int(args.years * 365.25))
    start = fmt_ymd(start_d)

    universe_file = Path(args.universe_file) if args.universe_file else None
    tickers = read_universe_tickers(universe_file, args.ticker_col)

    print("================================================================================")
    print("[REGIME BUILD CONFIG]")
    print("--------------------------------------------------------------------------------")
    print(f"price_db      : {price_db} :: {args.price_table}")
    print(f"regime_db     : {regime_db} :: {args.regime_table}")
    print(f"universe_file : {universe_file if universe_file else '(ALL in price_db)'}")
    print(f"range         : {start} ~ {end} (years={args.years})")
    print(f"horizons      : 1y={args.h1}, 6m={args.h2}, 3m={args.h3}")
    print("================================================================================")

    wide = load_prices_wide(price_db, args.price_table, tickers, start, end, price_col=args.price_col)
    if wide.empty:
        raise RuntimeError("No price data loaded. Check date range/table/column.")

    # drop all-NaN columns just in case (should not happen with tickers fixed, but safe)
    wide = wide.dropna(axis=1, how="all")

    horizon_map = [
        ("1y", int(args.h1)),
        ("6m", int(args.h2)),
        ("3m", int(args.h3)),
    ]

    total_upsert = 0
    ensure_parent(regime_db)

    for label, h in horizon_map:
        ret, score, dd, vol = compute_regime_for_horizon(wide, h)
        reg = score_to_regime(score)

        df_long = to_long(ret, score, reg, dd, vol, horizon_label=label)
        # 레짐이 -1(NaN)인 행은 저장 의미가 없으니 제거
        df_long = df_long[df_long["regime"] >= 0].copy()

        n = upsert_regime_history(regime_db, args.regime_table, df_long)
        total_upsert += n
        print(f"[DONE] horizon={label} upsert_rows~={n:,}")

    if args.verify_no_blob:
        verify_no_blob(regime_db, args.regime_table)
        print("[OK] verify_no_blob: PASSED")

    print(f"[DONE] total upsert ~ {total_upsert:,} rows")
    print("================================================================================")


if __name__ == "__main__":
    main()
