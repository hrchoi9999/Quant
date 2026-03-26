# core/data.py ver 2026-02-24_001
"""Data access helpers for backtest engines.

Design goals:
- Pure functions: no global state.
- Explicit DB paths + table names.
- Compatibility: accept both *price_db*/*regime_db* and legacy alias *db_path*.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import sqlite3


def resolve_project_root() -> Path:
    """Resolve project root (D:\Quant) from this file location.

    Assumes structure: <root>/src/backtest/core/data.py
    """
    return Path(__file__).resolve().parents[3]


def load_universe_tickers(universe_file: str | Path, ticker_col: str = "ticker") -> List[str]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns:
        raise KeyError(f"ticker_col '{ticker_col}' not found in universe csv columns={list(df.columns)}")
    tickers = df[ticker_col].astype(str).str.zfill(6).tolist()
    # drop duplicates while preserving order
    seen = set()
    out: List[str] = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def load_universe_name_map(
    universe_file: str | Path,
    ticker_col: str = "ticker",
    name_col: str = "name",
) -> Dict[str, str]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns or name_col not in df.columns:
        return {}
    s = df[[ticker_col, name_col]].dropna()
    s[ticker_col] = s[ticker_col].astype(str).str.zfill(6)
    return dict(zip(s[ticker_col], s[name_col].astype(str)))


def load_universe_market_map(
    universe_file: str | Path,
    ticker_col: str = "ticker",
    market_col: str = "market",
) -> Dict[str, str]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns or market_col not in df.columns:
        return {}
    s = df[[ticker_col, market_col]].dropna()
    s[ticker_col] = s[ticker_col].astype(str).str.zfill(6)
    return dict(zip(s[ticker_col], s[market_col].astype(str)))


def _coalesce_table(price_table: Optional[str], table: Optional[str]) -> str:
    if price_table:
        return price_table
    if table:
        return table
    return "prices_daily"


def load_prices_wide(
    price_db: Optional[str | Path] = None,
    price_table: Optional[str] = "prices_daily",
    tickers: Optional[Sequence[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    # compatibility aliases
    db_path: Optional[str | Path] = None,
    table: Optional[str] = None,
) -> pd.DataFrame:
    """Load OHLCV close prices into wide dataframe indexed by date.

    Expected DB schema: (date TEXT, ticker TEXT, close REAL, ...)

    Parameters
    ----------
    price_db / db_path : sqlite db file path
    price_table / table : table name
    tickers : iterable of tickers (6-digit strings). If None -> load all.
    start, end : inclusive YYYY-MM-DD strings (optional)
    """
    db = Path(db_path) if db_path is not None else Path(price_db) if price_db is not None else None
    if db is None:
        raise ValueError("price_db (or db_path) is required")

    tbl = _coalesce_table(price_table, table)

    where = []
    params: List[object] = []
    if tickers:
        tlist = [str(t).zfill(6) for t in tickers]
        placeholders = ",".join(["?"] * len(tlist))
        where.append(f"ticker IN ({placeholders})")
        params.extend(tlist)
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    q = f"SELECT date, ticker, close FROM {tbl} {where_sql} ORDER BY date, ticker"

    con = sqlite3.connect(str(db))
    try:
        df = pd.read_sql_query(q, con, params=params)
    finally:
        con.close()

    if df.empty:
        return pd.DataFrame()

    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    wide.index = pd.to_datetime(wide.index)
    return wide


def compute_daily_returns(close_wide: pd.DataFrame) -> pd.DataFrame:
    if close_wide.empty:
        return close_wide
    rets = close_wide.pct_change(fill_method=None)
    return rets


def load_regime_panel(
    regime_db: Optional[str | Path] = None,
    regime_table: str = "regime_history",
    tickers: Optional[Sequence[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    horizons: Sequence[str] = ("1y", "6m", "3m"),
    # compatibility aliases
    db_path: Optional[str | Path] = None,
    table: Optional[str] = None,
) -> pd.DataFrame:
    """Load regime_history as long panel: (date, ticker, horizon, regime, score).

    Returns a DataFrame with columns: date,ticker,horizon,regime,score
    """
    db = Path(db_path) if db_path is not None else Path(regime_db) if regime_db is not None else None
    if db is None:
        raise ValueError("regime_db (or db_path) is required")
    tbl = table or regime_table

    where = []
    params: List[object] = []
    if tickers:
        tlist = [str(t).zfill(6) for t in tickers]
        placeholders = ",".join(["?"] * len(tlist))
        where.append(f"ticker IN ({placeholders})")
        params.extend(tlist)
    if horizons:
        hlist = list(horizons)
        placeholders = ",".join(["?"] * len(hlist))
        where.append(f"horizon IN ({placeholders})")
        params.extend(hlist)
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    q = f"SELECT date, ticker, horizon, regime, score FROM {tbl} {where_sql} ORDER BY date, ticker"

    con = sqlite3.connect(str(db))
    try:
        df = pd.read_sql_query(q, con, params=params)
    finally:
        con.close()

    if df.empty:
        return df

    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"])
    return df


def month_end_dates(dates: Sequence[pd.Timestamp]) -> List[pd.Timestamp]:
    # NOTE: `dates` may be a DatetimeIndex; `if not dates` is ambiguous in pandas.
    if len(dates) == 0:
        return []
    s = pd.Series(pd.to_datetime(list(dates))).sort_values().drop_duplicates()
    df = s.to_frame(name="date")
    df["ym"] = df["date"].dt.to_period("M")
    last = df.groupby("ym")["date"].max().sort_values()
    return list(last)


def week_anchor_dates(
    dates: Sequence[pd.Timestamp],
    anchor_weekday: int = 2,
    holiday_shift: str = "prev",
) -> List[pd.Timestamp]:
    """Pick weekly decision dates anchored to a weekday.

    If the anchor day is missing (holiday), shift to previous/next within that week.
    """
    # NOTE: `dates` may be a DatetimeIndex; `if not dates` is ambiguous in pandas.
    if len(dates) == 0:
        return []
    s = pd.Series(pd.to_datetime(list(dates))).sort_values().drop_duplicates()
    df = s.to_frame(name="date")
    df["week"] = df["date"].dt.to_period("W")
    by_week = df.groupby("week")["date"].apply(list)

    out: List[pd.Timestamp] = []
    for _wk, ds in by_week.items():
        ds_sorted = sorted(ds)
        candidates = [d for d in ds_sorted if d.weekday() == anchor_weekday]
        if candidates:
            out.append(candidates[0])
            continue
        if holiday_shift == "next":
            # choose first trading day after anchor weekday within week
            after = [d for d in ds_sorted if d.weekday() > anchor_weekday]
            if after:
                out.append(after[0])
                continue
        # default/prev: choose last trading day before anchor weekday within week
        before = [d for d in ds_sorted if d.weekday() < anchor_weekday]
        if before:
            out.append(before[-1])
        else:
            out.append(ds_sorted[0])
    return out


def next_trading_day(dates: Sequence[pd.Timestamp], dt: pd.Timestamp) -> Optional[pd.Timestamp]:
    # NOTE: `dates` may be a DatetimeIndex; `if not dates` is ambiguous in pandas.
    if len(dates) == 0:
        return None
    s = pd.Series(pd.to_datetime(list(dates))).sort_values().drop_duplicates()
    dt = pd.to_datetime(dt)
    # We want the *next* trading day strictly after `dt`.
    pos = s.searchsorted(dt, side="left")
    if pos < len(s) and pd.Timestamp(s.iloc[pos]) == pd.Timestamp(dt):
        pos += 1
    if pos >= len(s):
        # Clamp: if `dt` is at/after the last trading day, return the last day.
        return pd.Timestamp(s.iloc[-1])
    return pd.Timestamp(s.iloc[pos])
