# build_regime_history.py ver 2026-01-27_002
"""유니버스 종목의 레짐(5단계) 히스토리를 생성하여 SQLite DB에 저장합니다.

권장 실행(패키지 모드)
  (venv64) PS D:/Quant> python -m src.regime.build_regime_history \
      --universe-file "D:/Quant/data/universe/universe_top200_kospi_20260127.csv" \
      --ticker-col ticker \
      --price-db "D:/Quant/data/db/price.db" \
      --price-table prices_daily \
      --years 5

- `python src/regime/build_regime_history.py ...` 로 실행해도 되도록 sys.path 보정 포함.
- 기존 `src.regime.regime_score.compute_regime_scores()`가 2D 입력에서 실패하는 사례가 있어
  (pd.cut: "Input array must be 1 dimensional"), 여기서는 2D(wide) 기준으로 안전하게 계산합니다.

산출 정의(현 시점의 최소 규격)
- HORIZONS: 1y/6m/3m = 252/126/63 거래일
- ret_h: horizon 수익률 (close/shift - 1)
- score_h: 동일 일자에 TopN 종목의 ret_h를 cross-sectional percentile(0~1)로 변환
- regime_h: score_h를 5단계로 구간화(1~5)
  * 1=강하락, 2=하락, 3=보합, 4=상승, 5=강상승
- dd_h: 해당 horizon 내 rolling max 대비 drawdown (close/rolling_max - 1)
- vol: 20일 변동성(연율화) = std(daily_ret, 20) * sqrt(252)

저장 테이블(기본: regime_history)
- trade_date TEXT (YYYY-MM-DD)
- ticker TEXT (6자리)
- horizon TEXT (1y/6m/3m)
- ret REAL
- score REAL
- regime INTEGER
- dd REAL
- vol REAL
- created_at TEXT

주의
- universe 티커가 숫자로 읽혀 0이 사라지는 경우가 있어 zfill(6) 보정합니다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


# ------------------------------
# Path/bootstrap
# ------------------------------
# D:\Quant\src\regime\build_regime_history.py 기준
#   __file__ -> ...\src\regime\
#   .. -> ...\src\
#   .. -> ...\(project root)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ------------------------------
# Regime spec
# ------------------------------
HORIZONS: Dict[str, int] = {
    "1y": 252,
    "6m": 126,
    "3m": 63,
}

REGIME_LABELS: Dict[int, str] = {
    1: "StrongDown",
    2: "Down",
    3: "Flat",
    4: "Up",
    5: "StrongUp",
}


# ------------------------------
# Utils
# ------------------------------

def _log(msg: str) -> None:
    print(msg, flush=True)


def _zfill6(x: object) -> str:
    s = str(x).strip()
    # pandas가 float로 읽는 경우 "5930.0" 형태 방지
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6)


def _parse_yyyymmdd(s: str) -> dt.date:
    s = str(s)
    if "-" in s:
        return dt.date.fromisoformat(s)
    return dt.datetime.strptime(s, "%Y%m%d").date()


def _date_to_str(d: dt.date) -> str:
    return d.isoformat()


def _chunked(seq: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# ------------------------------
# DB / data loading
# ------------------------------

def load_universe(universe_file: str, ticker_col: str) -> List[str]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns:
        raise ValueError(f"ticker_col not found: {ticker_col}. columns={list(df.columns)}")
    tickers = df[ticker_col].dropna().map(_zfill6).unique().tolist()
    tickers = [t for t in tickers if len(t) == 6]
    return tickers


def load_prices_wide(
    db_path: str,
    table: str,
    tickers: List[str],
    start_date: dt.date,
    end_date: dt.date | None = None,
    date_col: str = "trade_date",
    ticker_col: str = "ticker",
    close_col: str = "close",
) -> pd.DataFrame:
    """DB에서 close 시계열을 wide(date x ticker)로 로딩."""

    if end_date is None:
        end_date = dt.date.today()

    start_s = _date_to_str(start_date)
    end_s = _date_to_str(end_date)

    if len(tickers) == 0:
        raise ValueError("tickers is empty")

    con = sqlite3.connect(db_path)
    try:
        # IN 절 파라미터 개수 제한 대비: chunk로 쿼리
        frames: List[pd.DataFrame] = []
        for chunk in _chunked(tickers, 400):
            placeholders = ",".join(["?"] * len(chunk))
            sql = f"""
                SELECT {date_col} AS trade_date, {ticker_col} AS ticker, {close_col} AS close
                FROM {table}
                WHERE {date_col} >= ? AND {date_col} <= ?
                  AND {ticker_col} IN ({placeholders})
                ORDER BY {date_col} ASC
            """.strip()
            params: List[object] = [start_s, end_s] + chunk
            part = pd.read_sql_query(sql, con, params=params)
            frames.append(part)

        if not frames:
            raise RuntimeError("No data frames returned from DB query")

        df = pd.concat(frames, ignore_index=True)
        if df.empty:
            raise RuntimeError(
                f"prices query returned empty. table={table}, start={start_s}, end={end_s}, tickers={len(tickers)}"
            )

        df["ticker"] = df["ticker"].map(_zfill6)
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df = df.dropna(subset=["trade_date", "ticker", "close"])

        wide = df.pivot_table(index="trade_date", columns="ticker", values="close", aggfunc="last")
        wide = wide.sort_index()
        # 유니버스 순서/컬럼 보정 (없는 티커는 NaN)
        wide = wide.reindex(columns=tickers)
        return wide
    finally:
        con.close()


# ------------------------------
# Regime computation (safe for 2D)
# ------------------------------

def compute_regime_wide(
    close_wide: pd.DataFrame,
    horizons: Dict[str, int] = HORIZONS,
    vol_window: int = 20,
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """wide close를 받아 horizon별 ret/score/regime/dd 및 공통 vol을 산출."""

    close = close_wide.astype(float)

    daily_ret = close.pct_change()
    vol = daily_ret.rolling(vol_window).std() * np.sqrt(252.0)

    out: Dict[str, Dict[str, pd.DataFrame]] = {}

    for h_name, h_days in horizons.items():
        ret_h = close / close.shift(h_days) - 1.0

        # cross-sectional percentile (행 단위)
        score_h = ret_h.rank(axis=1, pct=True)

        # 5단계 구간화 (1~5). NaN 유지
        score_arr = score_h.to_numpy(dtype=float)
        regime_arr = np.ceil(score_arr * 5.0)
        regime_arr = np.clip(regime_arr, 1.0, 5.0)
        regime_arr[np.isnan(score_arr)] = np.nan
        regime_h = pd.DataFrame(regime_arr, index=score_h.index, columns=score_h.columns).astype("Float64")
        # 저장 시 Int64로 변환 (NaN 허용)
        regime_h = regime_h.round(0).astype("Int64")

        # horizon 내 rolling max 대비 drawdown
        roll_max = close.rolling(h_days, min_periods=1).max()
        dd_h = close / roll_max - 1.0

        out[h_name] = {
            "ret": ret_h,
            "score": score_h,
            "regime": regime_h,
            "dd": dd_h,
            "vol": vol,
        }

    return out


def to_long(reg: Dict[str, Dict[str, pd.DataFrame]]) -> pd.DataFrame:
    """horizon dict -> long DataFrame."""

    longs: List[pd.DataFrame] = []
    for h, mats in reg.items():
        ret_s = mats["ret"].stack(dropna=False).rename("ret")
        score_s = mats["score"].stack(dropna=False).rename("score")
        regime_s = mats["regime"].stack(dropna=False).rename("regime")
        dd_s = mats["dd"].stack(dropna=False).rename("dd")
        vol_s = mats["vol"].stack(dropna=False).rename("vol")

        df = pd.concat([ret_s, score_s, regime_s, dd_s, vol_s], axis=1).reset_index()
        df = df.rename(columns={"level_0": "trade_date", "level_1": "ticker"})
        df["horizon"] = h

        # ret가 NaN이면 score/regime도 의미 없음: 제거
        df = df.dropna(subset=["ret"])  # early 기간 제거

        # dtype 정리
        df["trade_date"] = df["trade_date"].astype(str)  # YYYY-MM-DD
        df["ticker"] = df["ticker"].map(_zfill6)
        df["regime"] = df["regime"].astype("Int64")
        df["created_at"] = dt.datetime.now().isoformat(timespec="seconds")

        longs.append(df)

    if not longs:
        return pd.DataFrame(columns=["trade_date", "ticker", "horizon", "ret", "score", "regime", "dd", "vol", "created_at"])

    all_long = pd.concat(longs, ignore_index=True)
    return all_long


# ------------------------------
# DB write
# ------------------------------

def ensure_table(con: sqlite3.Connection, table: str) -> None:
    cur = con.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            trade_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            horizon TEXT NOT NULL,
            ret REAL,
            score REAL,
            regime INTEGER,
            dd REAL,
            vol REAL,
            created_at TEXT,
            PRIMARY KEY (trade_date, ticker, horizon)
        )
        """.strip()
    )
    con.commit()


def delete_existing(
    con: sqlite3.Connection,
    table: str,
    tickers: List[str],
    date_min: str,
    date_max: str,
) -> None:
    if not tickers:
        return

    cur = con.cursor()
    # SQLite IN 절 최대 파라미터 고려
    for chunk in _chunked(tickers, 800):
        placeholders = ",".join(["?"] * len(chunk))
        sql = f"""
            DELETE FROM {table}
            WHERE trade_date >= ? AND trade_date <= ?
              AND ticker IN ({placeholders})
        """.strip()
        params: List[object] = [date_min, date_max] + chunk
        cur.execute(sql, params)
    con.commit()


def insert_rows(con: sqlite3.Connection, table: str, df_long: pd.DataFrame, chunk_size: int = 50000) -> int:
    if df_long.empty:
        return 0

    cols = ["trade_date", "ticker", "horizon", "ret", "score", "regime", "dd", "vol", "created_at"]
    df = df_long[cols].copy()

    cur = con.cursor()
    sql = f"""
        INSERT OR REPLACE INTO {table}
        (trade_date, ticker, horizon, ret, score, regime, dd, vol, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """.strip()

    total = 0
    rows = df.itertuples(index=False, name=None)

    batch: List[Tuple[object, ...]] = []
    for r in rows:
        batch.append(r)
        if len(batch) >= chunk_size:
            cur.executemany(sql, batch)
            con.commit()
            total += len(batch)
            batch = []

    if batch:
        cur.executemany(sql, batch)
        con.commit()
        total += len(batch)

    return total


# ------------------------------
# CLI
# ------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--universe-file", required=True)
    p.add_argument("--ticker-col", default="ticker")

    p.add_argument("--price-db", required=True)
    p.add_argument("--price-table", default="prices_daily")
    p.add_argument("--years", type=int, default=5)

    p.add_argument("--out-table", default="regime_history")
    p.add_argument("--vol-window", type=int, default=20)

    # date range override (옵션)
    p.add_argument("--end", default=None, help="YYYY-MM-DD or YYYYMMDD. default=today")

    return p


def main() -> None:
    args = build_parser().parse_args()

    project_root = PROJECT_ROOT
    _log(f"[INFO] project_root={project_root}")

    tickers = load_universe(args.universe_file, args.ticker_col)
    _log(f"[INFO] universe={args.universe_file}")
    _log(f"[INFO] tickers={len(tickers)}")

    end_date = _parse_yyyymmdd(args.end) if args.end else dt.date.today()
    start_date = end_date - dt.timedelta(days=365 * int(args.years))
    # years를 day로 잡되, 실제는 DB의 거래일만 사용
    _log(f"[INFO] load start_date>={start_date.isoformat()} (years={args.years})")

    close_wide = load_prices_wide(
        db_path=args.price_db,
        table=args.price_table,
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
    )
    _log(f"[INFO] prices loaded: dates={len(close_wide.index)}, tickers_in_wide={close_wide.shape[1]}")

    reg = compute_regime_wide(close_wide, horizons=HORIZONS, vol_window=args.vol_window)
    df_long = to_long(reg)

    if df_long.empty:
        _log("[WARN] regime history is empty (insufficient data?)")
        return

    date_min = df_long["trade_date"].min()
    date_max = df_long["trade_date"].max()
    _log(f"[INFO] output rows={len(df_long):,} (date_range={date_min}~{date_max}, horizons={list(HORIZONS.keys())})")

    con = sqlite3.connect(args.price_db)
    try:
        ensure_table(con, args.out_table)
        delete_existing(con, args.out_table, tickers, date_min, date_max)
        inserted = insert_rows(con, args.out_table, df_long)
    finally:
        con.close()

    _log(f"[DONE] inserted_or_replaced={inserted:,} -> table={args.out_table} in {args.price_db}")


if __name__ == "__main__":
    main()
