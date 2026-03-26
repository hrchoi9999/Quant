# run_backtest_s2_v5.py ver 2026-02-23_001
"""
Regime portfolio backtest (R2, S1, S2) - refactored for maintainability.

This v4 focuses on:

This v4 applies decisions agreed in chat (strategy preset defaults):
- Market gate (시장 게이트) is enabled by default and uses the universe-based market proxy.
    * market_sma_window (msma) = 60
    * entry_mult = 1.00  (invest when proxy > SMA60)
    * exit_mult  = 1.00  (risk-off when proxy < SMA60)
    * NOTE/TODO: Replace proxy with official KOSPI index series when available.
- Stock-level defense rule (P2-2, 2-week confirmation) is enabled by default:
    * If a held stock closes below its SMA for N consecutive rebalances (default N=2),
      it is removed at the rebalance.
- Stock SMA filter is enabled by default:
    * stock_sma_window = 140 and require close > SMA to be eligible.
- S2 fundamentals view default is set to: s2_fund_scores_monthly
- Rebalance default is weekly (W) to match the research workflow.

- Clear separation of concerns (6 sections)
- Fixing S2 fundamentals selection by using the prebuilt DB view:
    vw_s2_top30_monthly  (date별 valid_fund=1 TOP30을 이미 보장)
- Defaults updated per user request:
    * S2 portfolio size: TOP30 (default --top-n 30)
    * SMA filter window: 60 (default --sma-window 60)
    * Market gate SMA window: 60 (default --market-sma-window 60)

Data sources
- regime.db   : regime_history(date, ticker, horizon, score, regime)
- price.db    : prices_daily(date, ticker, close, ...)
- fundamentals.db (or fundamentals table DB):
    vw_s2_top30_monthly(date, ticker, corp_name, revenue_yoy, op_income_yoy, growth_score, valid_fund, score_rank)

Notes
- S2 in v1 used 'as-of' available_from updating logic. That is intentionally removed here.
  We rely on the monthly snapshot table/view that you already validated.
"""


from __future__ import annotations

import argparse
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bisect
import math
import datetime

import numpy as np
import pandas as pd
def _sort_snapshot_by_return(df: pd.DataFrame, return_col: str = "return") -> pd.DataFrame:
    """Sort snapshot rows by per-ticker return descending while preserving column order.
    - Keeps CASH row (name == 'CASH' or ticker == 'CASH') at the bottom.
    - Coerces return to numeric safely (handles strings like '2.3%', '0.023', etc.).
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    cols = list(df.columns)

    work = df.copy()

    # Identify CASH rows
    name_upper = work["name"].astype(str).str.upper() if "name" in work.columns else pd.Series([""] * len(work))
    ticker_upper = work["ticker"].astype(str).str.upper() if "ticker" in work.columns else pd.Series([""] * len(work))
    is_cash = (name_upper == "CASH") | (ticker_upper == "CASH")

    # Parse return column
    if return_col in work.columns:
        r = work[return_col]
        # remove % if present and coerce
        r_num = pd.to_numeric(r.astype(str).str.replace("%", "", regex=False), errors="coerce")
        # Heuristic: if values look like decimals (e.g., 0.02) treat as already ratio; else might be percent points.
        # We do NOT rescale; we only sort, so magnitude scaling doesn't matter.
        work["_return_num__"] = r_num
    else:
        work["_return_num__"] = float("nan")

    # Sort non-cash by return desc; stable for ties
    non_cash = work.loc[~is_cash].sort_values(by="_return_num__", ascending=False, kind="mergesort")
    cash_part = work.loc[is_cash]
    out = pd.concat([non_cash, cash_part], axis=0)

    # Restore columns
    out = out[cols]
    return out

def _attach_market_col(df: pd.DataFrame, market_map: dict, ticker_col: str = "ticker", out_col: str = "market") -> pd.DataFrame:
    """Attach market column (KOSPI/KOSDAQ) next to name (if exists) or next to ticker."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df
    if not market_map:
        # still ensure column exists for schema stability
        if out_col not in df.columns:
            df[out_col] = ""
    else:
        if out_col not in df.columns:
            df[out_col] = df[ticker_col].astype(str).map(lambda t: str(market_map.get(str(t), "")).strip())
        else:
            df[out_col] = df[out_col].astype(str).where(df[out_col].astype(str).str.len() > 0,
                                                       df[ticker_col].astype(str).map(lambda t: str(market_map.get(str(t), "")).strip()))
    # reorder columns: ticker, name, market, ...
    cols = list(df.columns)
    if "name" in cols and out_col in cols and ticker_col in cols:
        # place market right after name
        cols.remove(out_col)
        name_idx = cols.index("name")
        cols.insert(name_idx + 1, out_col)
        df = df[cols]
    elif out_col in cols and ticker_col in cols:
        cols.remove(out_col)
        t_idx = cols.index(ticker_col)
        cols.insert(t_idx + 1, out_col)
        df = df[cols]
    return df

from datetime import datetime, time

import sys


__VERSION__ = '2026-02-23_001'

# Google Sheets defaults (user-specific). You can override via CLI args if desired.
DEFAULT_GSHEET_CRED = r"D:\Quant\config\quant-485814-0df3dc750a8d.json"
DEFAULT_GSHEET_ID   = "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs"


# [협의 반영 요약]
# 1) Market gate: 상승장 진입 + 위험회피 역할을 동시에 수행하도록 entry_mult 기본값을 1.02로 완화 (exit_mult=1.00 유지)
# 2) 게이트 OFF 즉시 강제청산은 적용하지 않음
# 3) 종목 레벨 방어(P2-2): 보유 종목이 SMA 아래로 N회(기본 2회) 연속 마감하면 리밸런스 시점에 제외
# 4) 성과 리포트(perf_windows) ALL 구간 CAGR 계산을 equity 기반(end/start)으로 수정
# 5) equity_df 진단 컬럼 저장 버그(미정의 변수 참조) 제거 및 안정화
#


# =============================================================================
# 1) 공통 유틸 / 로깅 / 문자열 정규화
# =============================================================================



def _build_rebalance_ledger(
    holdings_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    name_map: dict,
    market_map: dict,
    qty_default: int = 1,
    ticker_col: str = "ticker",
) -> pd.DataFrame:
    """Build rebalance-event based ledger.

    For each rebalance_date, detect:
      - BUY: tickers newly added vs previous rebalance
      - SELL: tickers removed vs previous rebalance

    FIFO lot tracking is used to derive first_buy_date/buy_price for SELL rows.
    Quantity is fixed (default=1) for now but the structure supports future extension.
    """
    if holdings_df is None or holdings_df.empty:
        return pd.DataFrame()

    # Normalize expected columns
    if "rebalance_date" not in holdings_df.columns:
        raise ValueError("holdings_df must contain 'rebalance_date' column")

    # holdings_df may contain rows with NaN ticker when market_gate blocks; treat as empty holdings for that date
    tmp = holdings_df.copy()
    tmp["rebalance_date"] = pd.to_datetime(tmp["rebalance_date"])
    if ticker_col not in tmp.columns:
        # some versions may use 'ticker' fixed
        ticker_col = "ticker"

    tmp[ticker_col] = tmp[ticker_col].astype(str)
    # convert 'nan' literal (from astype) back to missing
    tmp.loc[tmp[ticker_col].str.lower().isin(["nan", "none", ""]), ticker_col] = np.nan

    # group holdings by date
    dates = sorted(tmp["rebalance_date"].dropna().unique())
    holdings_by_date = {}
    for d in dates:
        s = tmp.loc[tmp["rebalance_date"] == d, ticker_col].dropna().unique().tolist()
        holdings_by_date[pd.Timestamp(d).normalize()] = set(s)

    # Helper to get price; fallback NaN if missing
    def _px(dt: pd.Timestamp, t: str):
        # CASH is a pseudo-ticker: treat as 1.0 price for ledger bookkeeping
        if str(t).upper() == "CASH":
            return 1.0
        try:
            return float(close_wide.loc[dt, t])
        except Exception:
            return np.nan

    # FIFO lots: ticker -> list of dicts
    lots = {}
    rows = []

    prev_hold = set()
    for dt in dates:
        dt = pd.Timestamp(dt).normalize()
        cur_hold = holdings_by_date.get(dt, set())

        buys = sorted(list(cur_hold - prev_hold))
        sells = sorted(list(prev_hold - cur_hold))

        # BUY rows
        for t in buys:
            px = _px(dt, t)
            qty = qty_default
            amt = (px * qty) if pd.notnull(px) else np.nan
            lots.setdefault(t, []).append({"buy_date": dt, "buy_price": px, "qty": qty})

            rows.append({
                "rebalance_date": dt.date().isoformat(),
                "side": "BUY",
                "buy_date": dt.date().isoformat(),
                "ticker": t,
                "name": name_map.get(t, ""),
                "market": ("CASH" if str(t).upper()=="CASH" else market_map.get(t, "")),
                "price": px,
                "qty": qty,
                "amount": amt,
                # For BUY rows, first_buy_date should equal buy_date (ledger usability)
                "first_buy_date": dt.date().isoformat(),
                "sell_price": "",
                "pnl": "",
            })

        # SELL rows
        for t in sells:
            px_sell = _px(dt, t)
            qty = qty_default
            # FIFO: use earliest lot
            first_buy = ""
            buy_px = np.nan
            if t in lots and len(lots[t]) > 0:
                lot = lots[t].pop(0)
                first_buy = lot["buy_date"].date().isoformat() if isinstance(lot.get("buy_date"), pd.Timestamp) else str(lot.get("buy_date",""))
                buy_px = lot.get("buy_price", np.nan)

            pnl = (px_sell - buy_px) * qty if (pd.notnull(px_sell) and pd.notnull(buy_px)) else np.nan

            rows.append({
                "rebalance_date": dt.date().isoformat(),
                "side": "SELL",
                "buy_date": "",
                "ticker": t,
                "name": name_map.get(t, ""),
                "market": market_map.get(t, ""),
                "price": "",
                "qty": qty,
                "amount": "",
                "first_buy_date": first_buy,
                "sell_price": px_sell,
                "pnl": pnl,
            })

        prev_hold = cur_hold

    df = pd.DataFrame(rows)
    # Sort by rebalance_date then side (SELL after BUY for readability)
    if not df.empty:
        df["rebalance_date"] = pd.to_datetime(df["rebalance_date"])
        df["side_ord"] = df["side"].map({"BUY": 0, "SELL": 1}).fillna(9).astype(int)
        df = df.sort_values(["rebalance_date", "side_ord", "ticker"], ascending=[True, True, True]).drop(columns=["side_ord"])
        # convert dates back to iso for csv/google
        for col in ["rebalance_date", "buy_date", "first_buy_date"]:
            if col in df.columns:
                df[col] = df[col].astype(str)
    return df

def _try_import_gsheet_uploader(project_root: Path):
    """Import gsheet uploader from src/utils.

    Canonical run mode is `python -m src.backtest.run_backtest_s2_v5` (package execution).
    This avoids sys.path mutation and keeps imports consistent with the refactor runner.

    Returns (upload_snapshot_bundle, GSheetConfig) or (None, None).
    """
    try:
        from src.utils.gsheet_uploader import upload_snapshot_bundle, GSheetConfig  # type: ignore
        return upload_snapshot_bundle, GSheetConfig
    except Exception:
        return None, None

def _log(msg: str) -> None:
    print(msg, flush=True)


def resolve_project_root(start: Path) -> Path:
    """Walk up to find project root containing 'src' directory."""
    p = start.resolve()
    if p.is_file():
        p = p.parent
    for _ in range(12):
        if (p / "src").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return start.resolve()


def _ensure_ticker6(x: str) -> str:
    s = str(x).strip()
    if s.isdigit() and len(s) < 6:
        s = s.zfill(6)
    return s


def normalize_ticker(x) -> str:
    """Normalize ticker to 6-digit string used across this project."""
    if x is None:
        return ""
    s = str(x).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return ""
    return _ensure_ticker6(s)


# =============================================================================
# 2) 데이터 로더 (SQLite/CSV) + 리밸런싱 캘린더
# =============================================================================
def load_universe_tickers(universe_file: str, ticker_col: str) -> List[str]:
    df = pd.read_csv(universe_file, dtype={ticker_col: str})
    if ticker_col not in df.columns:
        raise RuntimeError(f"ticker_col not found: {ticker_col}. cols={list(df.columns)}")
    tickers = sorted({_ensure_ticker6(x) for x in df[ticker_col].dropna().astype(str).tolist()})
    return tickers


def load_universe_name_map(universe_file: str, ticker_col: str, name_col: str = "") -> Tuple[Dict[str, str], str]:
    """Load optional ticker->name mapping from universe csv."""
    df = pd.read_csv(universe_file, dtype={ticker_col: str})
    if ticker_col not in df.columns:
        raise RuntimeError(f"ticker_col not found: {ticker_col}. cols={list(df.columns)}")

    resolved = name_col.strip()
    if not resolved:
        for c in ["name", "corp_name", "company_name", "기업명", "종목명", "종목명(한글)", "종목명_한글"]:
            if c in df.columns:
                resolved = c
                break

    if not resolved or resolved not in df.columns:
        return {}, ""

    name_map: Dict[str, str] = {}
    for _, r in df[[ticker_col, resolved]].dropna().iterrows():
        t = _ensure_ticker6(r[ticker_col])
        nm = str(r[resolved]).strip()
        if t and nm:
            name_map[t] = nm
    return name_map, resolved


def _chunked_in_query(
    cur: sqlite3.Cursor,
    base_sql: str,
    params_head: List,
    tickers: List[str],
) -> List[Tuple]:
    """Chunked IN query helper to avoid SQLite variable limits."""
    out: List[Tuple] = []
    chunk = 900
    for i in range(0, len(tickers), chunk):
        ct = tickers[i : i + chunk]
        ph = ",".join(["?"] * len(ct))
        sql = base_sql.format(placeholders=ph)
        params = params_head + ct
        out.extend(cur.execute(sql, params).fetchall())
    return out


def load_regime_panel(
    regime_db: str,
    regime_table: str,
    horizon: str,
    tickers: List[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    con = sqlite3.connect(regime_db)
    try:
        cur = con.cursor()
        where = "WHERE horizon = ?"
        params: List = [str(horizon)]
        if start:
            where += " AND date >= ?"
            params.append(str(start))
        if end:
            where += " AND date <= ?"
            params.append(str(end))

        base_sql = f"""
            SELECT date, ticker, score, regime
            FROM {regime_table}
            {where}
              AND ticker IN ({{placeholders}})
        """
        rows = _chunked_in_query(cur, base_sql, params, tickers)
        df = pd.DataFrame(rows, columns=["date", "ticker", "score", "regime"])
    finally:
        con.close()

    if df.empty:
        raise RuntimeError(f"regime panel empty for horizon={horizon}. check db/table/date range/universe.")

    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].map(_ensure_ticker6)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["regime"] = pd.to_numeric(df["regime"], errors="coerce").astype("Int64")
    df = df[df["regime"].notna()].copy()
    df["regime"] = df["regime"].astype(int)
    df = df[df["score"].notna()].copy()
    return df


def load_prices_wide(
    price_db: str,
    price_table: str,
    tickers: List[str],
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    con = sqlite3.connect(price_db)
    try:
        cur = con.cursor()
        where = "WHERE 1=1"
        params: List = []
        if start:
            where += " AND date >= ?"
            params.append(str(start))
        if end:
            where += " AND date <= ?"
            params.append(str(end))

        base_sql = f"""
            SELECT date, ticker, close
            FROM {price_table}
            {where}
              AND ticker IN ({{placeholders}})
            ORDER BY date ASC
        """
        rows = _chunked_in_query(cur, base_sql, params, tickers)
        df = pd.DataFrame(rows, columns=["date", "ticker", "close"])
    finally:
        con.close()

    if df.empty:
        raise RuntimeError("price data empty. check price db/table/date range/universe.")

    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].map(_ensure_ticker6)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[df["close"].notna()].copy()

    wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    wide = wide.ffill().bfill()  # halted/suspension -> 0 return approximation
    return wide


def compute_daily_returns(close_wide: pd.DataFrame) -> pd.DataFrame:
    return close_wide.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)


def month_end_dates(dates: pd.DatetimeIndex) -> List[pd.Timestamp]:
    s = pd.Series(dates, index=dates)
    return s.groupby([s.index.year, s.index.month]).last().tolist()


def week_end_dates(dates: pd.DatetimeIndex) -> List[pd.Timestamp]:
    s = pd.Series(dates, index=dates)
    iso = s.index.isocalendar()
    return s.groupby([iso.year, iso.week]).last().tolist()



def week_anchor_dates(dates: pd.DatetimeIndex, anchor_weekday: int = 2, holiday_shift: str = 'prev') -> List[pd.Timestamp]:
    """Return one rebalance decision date per ISO week, anchored to a weekday.

    - anchor_weekday: 0=Mon .. 2=Wed .. 4=Fri
    - holiday_shift: 'prev' (default) or 'next' if the anchor day is missing in that week.

    The returned dates are *decision* dates. Portfolio changes are applied from the next trading day.
    """
    if len(dates) == 0:
        return []
    if anchor_weekday < 0 or anchor_weekday > 6:
        raise ValueError("anchor_weekday must be in 0..6")
    holiday_shift = str(holiday_shift).lower().strip()
    if holiday_shift not in ('prev', 'next'):
        raise ValueError("holiday_shift must be 'prev' or 'next'")

    s = pd.Series(index=dates, data=1)  # marker series
    # group by ISO week (year, week)
    keys = [(d.isocalendar().year, d.isocalendar().week) for d in dates]
    out: List[pd.Timestamp] = []
    start = 0
    for k in range(1, len(keys) + 1):
        if k == len(keys) or keys[k] != keys[start]:
            week_dates = dates[start:k]
            # try exact weekday
            target = [d for d in week_dates if d.weekday() == anchor_weekday]
            if target:
                out.append(pd.Timestamp(target[0]))
            else:
                out.append(pd.Timestamp(week_dates[-1] if holiday_shift == 'prev' else week_dates[0]))
            start = k
    return out
def load_s2_topn_candidates(
    fundamentals_db: str,
    fundamentals_view: str,
    date: pd.Timestamp,
    universe_tickers: List[str],
    top_n: int,
    max_rank: Optional[int] = None,
) -> pd.DataFrame:
    """
    Fetch S2 candidates for a rebalance date from the prebuilt monthly view.

    Expected view columns (at least):
      date, ticker, growth_score, score_rank, valid_fund (optional)
    """
    dt = pd.to_datetime(date).strftime("%Y-%m-%d")

    con = sqlite3.connect(fundamentals_db)
    try:
        cur = con.cursor()
        rank_cap = int(max_rank) if (max_rank is not None) else int(top_n)

        def _query(view_or_table: str) -> pd.DataFrame:
            sql = f"""
                SELECT date, ticker, growth_score, score_rank
                FROM {view_or_table}
                WHERE date = ?
                  AND score_rank <= ?
                  AND ticker IN ({{placeholders}})
                ORDER BY score_rank ASC
            """
            rows_ = _chunked_in_query(cur, sql, [dt, rank_cap], universe_tickers)
            return pd.DataFrame(rows_, columns=["date", "ticker", "growth_score", "score_rank"])

        # 1) primary: user-specified view
        df = _query(fundamentals_view)

        # 2) fallback: if view is too narrow (e.g., top30 view) try base table if present
        if len(df) < min(int(top_n), rank_cap):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='s2_fund_scores_monthly'")
            if cur.fetchone() is not None:
                df2 = _query("s2_fund_scores_monthly")
                if len(df2) > len(df):
                    df = df2
    finally:
        con.close()

    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].astype(str).map(_ensure_ticker6)
    df["growth_score"] = pd.to_numeric(df["growth_score"], errors="coerce")
    df["score_rank"] = pd.to_numeric(df["score_rank"], errors="coerce").astype(int)
    return df



def _load_fund_available_dates(fundamentals_db: str, fundamentals_view: str) -> List[pd.Timestamp]:
    """Return sorted unique dates available in the monthly fundamentals view (or fallback table)."""
    con = sqlite3.connect(fundamentals_db)
    try:
        cur = con.cursor()
        rows = []
        # prefer view
        try:
            cur.execute(f"SELECT DISTINCT date FROM {fundamentals_view} ORDER BY date")
            rows = cur.fetchall()
        except Exception:
            rows = []
        # fallback table if view fails/empty
        if not rows:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='s2_fund_scores_monthly'")
            if cur.fetchone() is not None:
                cur.execute("SELECT DISTINCT date FROM s2_fund_scores_monthly ORDER BY date")
                rows = cur.fetchall()
        dates = [pd.to_datetime(r[0]) for r in rows if r and r[0] is not None]
        dates = sorted(set(dates))
        return dates
    finally:
        con.close()


def _asof_fund_date(rb_date: pd.Timestamp, available: List[pd.Timestamp]) -> Optional[pd.Timestamp]:
    """Pick latest fundamentals date <= rb_date. Returns None if not available."""
    if not available:
        return None
    d = pd.to_datetime(rb_date)
    pos = bisect.bisect_right(available, d) - 1
    if pos < 0:
        return None
    return available[pos]


# =============================================================================
# 3) 전략 의사결정 (R2/S1/S2) - S2를 TOP30 뷰 기반으로 단순화
# =============================================================================
@dataclass
class RebalanceDecision:
    date: pd.Timestamp
    risk_on: bool
    spread: float
    n_assets: int
    weights: Dict[str, float]  # ticker -> weight


def _parse_good_regimes(s: str) -> List[int]:
    items: List[int] = []
    for x in (s or "").split(","):
        x = x.strip()
        if not x:
            continue
        try:
            items.append(int(x))
        except ValueError:
            continue
    return items or [4, 3]


def decide_weights_s2_v2(
    *,
    date: pd.Timestamp,
    reg_day: pd.DataFrame,
    fund_top_df: pd.DataFrame,
    close_row: pd.Series,
    sma_row: Optional[pd.Series],
    top_n: int,
    min_holdings: int,
    good_regimes: List[int],
    require_above_sma: bool,
) -> RebalanceDecision:
    """
    S2 v2 selection with a minimum-holdings safeguard.

    Base idea:
      fundamentals (score_rank asc) ∩ regime(good_regimes) ∩ (optionally close > SMA)

    Practical issue observed:
      too-strict filters can collapse holdings to near-zero, making the strategy effectively "all cash".

    Resolution:
      apply a relaxation cascade until we secure at least `min_holdings` (or we run out of candidates).
        0) regime + SMA (if enabled)
        1) regime only (drop SMA)
        2) SMA only (drop regime)
        3) no filters (fundamentals order only)

    Returns equal-weight among selected tickers.
    """
    if reg_day is None or reg_day.empty:
        return RebalanceDecision(date=date, risk_on=False, spread=float("nan"), n_assets=0, weights={})
    if fund_top_df is None or fund_top_df.empty:
        return RebalanceDecision(date=date, risk_on=False, spread=float("nan"), n_assets=0, weights={})

    reg = reg_day.copy()
    reg["ticker"] = reg["ticker"].astype(str).map(_ensure_ticker6)

    f = fund_top_df.copy()
    f["ticker"] = f["ticker"].astype(str).map(_ensure_ticker6)

    merged = reg.merge(f[["ticker", "growth_score", "score_rank"]], on="ticker", how="inner")
    if merged.empty:
        return RebalanceDecision(date=date, risk_on=False, spread=float("nan"), n_assets=0, weights={})

    # Prepare px/sma vectors once
    px_all = close_row.reindex(merged["ticker"]).astype(float)
    sm_all = sma_row.reindex(merged["ticker"]).astype(float) if (sma_row is not None) else None

    def _filtered(use_regime: bool, use_sma: bool) -> pd.DataFrame:
        out = merged
        if use_regime:
            out = out[out["regime"].isin([int(x) for x in good_regimes])]
        if use_sma and require_above_sma and (sm_all is not None):
            px = px_all.reindex(out["ticker"]).astype(float)
            sm = sm_all.reindex(out["ticker"]).astype(float)
            ok = (px > sm) & px.notna() & sm.notna()
            out = out.loc[ok.values]
        return out.copy()

    # relaxation cascade
    steps = [
        (True, True),   # regime + SMA
        (True, False),  # regime only
        (False, True),  # SMA only
        (False, False), # no filters
    ]

    chosen: Optional[pd.DataFrame] = None
    for use_regime, use_sma in steps:
        cand = _filtered(use_regime, use_sma)
        if len(cand) >= int(min_holdings):
            chosen = cand
            break
        # keep the best we have so far (in case none reaches min_holdings)
        if chosen is None or len(cand) > len(chosen):
            chosen = cand

    if chosen is None or chosen.empty:
        return RebalanceDecision(date=date, risk_on=False, spread=float("nan"), n_assets=0, weights={})

    chosen = chosen.sort_values(["score_rank"], ascending=True)
    picks = chosen["ticker"].head(int(top_n)).tolist()
    if not picks:
        return RebalanceDecision(date=date, risk_on=False, spread=float("nan"), n_assets=0, weights={})

    w = 1.0 / len(picks)
    return RebalanceDecision(date=date, risk_on=True, spread=float("nan"), n_assets=len(picks), weights={t: w for t in picks})


# =============================================================================
# 4) 백테스트 엔진 (공통) + S2 전용 엔진 (v2)
# =============================================================================
def turnover(old_w: Dict[str, float], new_w: Dict[str, float]) -> float:
    keys = set(old_w.keys()) | set(new_w.keys())
    s = 0.0
    for k in keys:
        s += abs(old_w.get(k, 0.0) - new_w.get(k, 0.0))
    return 0.5 * s


def calc_cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return float("nan")
    start_val = float(equity.iloc[0])
    end_val = float(equity.iloc[-1])
    if start_val <= 0:
        return float("nan")
    days = (equity.index[-1] - equity.index[0]).days
    if days <= 0:
        return float("nan")
    years = days / 365.25
    return (end_val / start_val) ** (1.0 / years) - 1.0


def calc_mdd(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity / peak) - 1.0
    return float(dd.min())


def calc_sharpe(daily_ret: pd.Series) -> float:
    mu = float(daily_ret.mean())
    sd = float(daily_ret.std(ddof=1))
    if sd == 0:
        return float("nan")
    return (mu / sd) * np.sqrt(252.0)


def backtest_s2_v2(
    *,
    close_wide: pd.DataFrame,
    ret_wide: pd.DataFrame,
    regime_primary: pd.DataFrame,
    fundamentals_db: str,
    fundamentals_view: str,
    fundamentals_asof: bool,
    rebalance_dates: List[pd.Timestamp],
    fee_bps: float,
    slippage_bps: float,
    top_n: int,
    min_holdings: int,
    good_regimes: List[int],
    sma_window: int,
    require_above_sma: bool,
    market_gate: bool,
    market_scope_tickers: List[str],
    market_sma_window: int,
    market_sma_mult: float,
    market_entry_mult: float,
    market_exit_mult: float,
    exit_below_sma_weeks: int,
    enable_exit_below_sma: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    S2 backtest (v2):
    - Fundamentals candidates: query monthly view by date; if fundamentals_asof=True, weekly rebalances use latest month-end (as-of)
    - Optional market gate: synthetic market proxy from price panel (scope average return), with hysteresis (entry/exit multipliers)
    """
    dates = close_wide.index
    rebalance_dates = [d for d in rebalance_dates if d in dates]
    if not rebalance_dates:
        raise RuntimeError("no rebalance dates available in price data.")

    cost_per_turnover = (fee_bps + slippage_bps) / 10000.0
    port_ret = pd.Series(0.0, index=dates)
    holdings_rows: List[Dict] = []
    old_w: Dict[str, float] = {}
    below_sma_streak: Dict[str, int] = {}  # ticker -> consecutive rebalance streak of close<SMA

    # SMA for per-ticker filter
    sma = close_wide.rolling(int(sma_window), min_periods=int(sma_window)).mean()

    # Market gate (optional): build synthetic proxy price series
    market_ok_series: Optional[pd.Series] = None
    market_price: Optional[pd.Series] = None
    market_sma: Optional[pd.Series] = None

    if market_gate:
        scope_cols = [t for t in market_scope_tickers if t in close_wide.columns]
        if not scope_cols:
            scope_cols = list(close_wide.columns)

        mret = close_wide[scope_cols].pct_change().mean(axis=1, skipna=True).fillna(0.0)
        market_price = (1.0 + mret).cumprod()
        market_sma = market_price.rolling(int(market_sma_window), min_periods=int(market_sma_window)).mean()
        # Hysteresis gate:
        # - enter risk_on when price > sma * entry_mult
        # - exit  risk_on when price < sma * exit_mult
        entry_mult = float(market_entry_mult)
        exit_mult = float(market_exit_mult)
        if exit_mult > entry_mult:
            # keep sane ordering
            exit_mult, entry_mult = entry_mult, exit_mult

        market_ok_series = pd.Series(False, index=market_price.index, dtype=bool)
        state = False
        for dt_ in market_price.index:
            s = market_sma.loc[dt_]
            p = market_price.loc[dt_]
            if pd.isna(s):
                market_ok_series.loc[dt_] = False
                continue
            if not state:
                if p > (s * entry_mult):
                    state = True
            else:
                if p < (s * exit_mult):
                    state = False
            market_ok_series.loc[dt_] = bool(state)


        last_dt = market_price.index[-1]
        _log(
            f"[INFO] market_gate=ON | scope_tickers={len(scope_cols):,} | "
            f"win={int(market_sma_window)} | entry={float(market_entry_mult):.3f} | exit={float(market_exit_mult):.3f} | "
            f"last_price={float(market_price.loc[last_dt]):.4f} | "
            f"last_sma={float(market_sma.loc[last_dt]) if pd.notna(market_sma.loc[last_dt]) else float('nan'):.4f} | "
            f"last_ok={bool(market_ok_series.loc[last_dt])}"
        )

    universe_tickers = list(close_wide.columns)

    fund_dates = _load_fund_available_dates(fundamentals_db, fundamentals_view)

    for i, rb_date in enumerate(rebalance_dates):
        next_rb = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else None

        # Market gate on rebalance date
        market_ok = True
        m_price = np.nan
        m_sma = np.nan
        if market_ok_series is not None:
            market_ok = bool(market_ok_series.get(rb_date, False))
            if market_price is not None and rb_date in market_price.index:
                m_price = float(market_price.loc[rb_date])
            if market_sma is not None and rb_date in market_sma.index:
                m_sma = float(market_sma.loc[rb_date])

        # Strategy decision
        reg_day = regime_primary[regime_primary["date"] == rb_date].copy()
        close_row = close_wide.loc[rb_date]
        sma_row = sma.loc[rb_date] if rb_date in sma.index else None

        fund_asof = None
        if fundamentals_asof:
            fund_asof = _asof_fund_date(rb_date, fund_dates)
        use_fund_date = fund_asof if fund_asof is not None else rb_date

        fund_top = load_s2_topn_candidates(
            fundamentals_db=fundamentals_db,
            fundamentals_view=fundamentals_view,
            date=use_fund_date,
            universe_tickers=universe_tickers,
            top_n=int(top_n),
            max_rank=max(200, int(top_n) * 2),
        )

        if (not market_ok) or reg_day.empty or fund_top.empty or (fundamentals_asof and fund_asof is None):
            decision = RebalanceDecision(date=rb_date, risk_on=False, spread=float("nan"), n_assets=0, weights={})
        else:
            decision = decide_weights_s2_v2(
                date=rb_date,
                reg_day=reg_day,
                fund_top_df=fund_top,
                close_row=close_row,
                sma_row=sma_row,
                top_n=int(top_n),
                min_holdings=int(min_holdings),
                good_regimes=good_regimes,
                require_above_sma=bool(require_above_sma),
            )

        new_w = decision.weights

        # ---------------------------------------------------------------------
        # P2-2 stock-level defense (2-week confirmation exit)
        # - Only applies to tickers currently held (old_w) that remain in new_w.
        # - If close < SMA for N consecutive rebalances, force exit at this rebalance.
        # ---------------------------------------------------------------------
        if enable_exit_below_sma and int(exit_below_sma_weeks) > 0 and (sma_row is not None):
            force_exit = set()
            held_prev = set(old_w.keys())
            held_now = set(new_w.keys())
            # Update streaks for tickers we are carrying forward
            for t in (held_prev & held_now):
                try:
                    px = float(close_row.get(t, np.nan))
                    sm = float(sma_row.get(t, np.nan))
                except Exception:
                    px, sm = np.nan, np.nan
                if (pd.notna(px) and pd.notna(sm) and (px < sm)):
                    below_sma_streak[t] = int(below_sma_streak.get(t, 0)) + 1
                    if below_sma_streak[t] >= int(exit_below_sma_weeks):
                        force_exit.add(t)
                else:
                    below_sma_streak[t] = 0

            # Reset streak for new entries (not previously held)
            for t in (held_now - held_prev):
                below_sma_streak[t] = 0

            # Remove streak records for tickers no longer held
            for t in list(below_sma_streak.keys()):
                if t not in held_now:
                    below_sma_streak.pop(t, None)

            # Force exits: drop from portfolio now (rebalance executed at rb_date close)
            if force_exit:
                for t in force_exit:
                    new_w.pop(t, None)

                # Re-normalize remaining weights equally (keep equal-weight convention)
                if new_w:
                    k = len(new_w)
                    w = 1.0 / k
                    new_w = {t: w for t in new_w.keys()}
                    decision = RebalanceDecision(date=rb_date, risk_on=True, spread=decision.spread, n_assets=k, weights=new_w)
                else:
                    decision = RebalanceDecision(date=rb_date, risk_on=False, spread=float("nan"), n_assets=0, weights={})
        
        # Transaction cost on rebalance date
        tv = turnover(old_w, new_w)
        cost = tv * cost_per_turnover
        if cost > 0:
            port_ret.loc[rb_date] -= cost

        # Holdings record
        if decision.risk_on:
            sub = reg_day[reg_day["ticker"].isin(new_w.keys())][["ticker", "regime", "score"]].copy()
            sub = sub.merge(fund_top[["ticker", "growth_score", "score_rank"]], on="ticker", how="left")
            for _, r in sub.iterrows():
                t = str(r["ticker"])
                holdings_rows.append(
                    {
                        "strategy": "S2",
                        "rebalance_date": rb_date.strftime("%Y-%m-%d"),
                        "fund_asof_date": (fund_asof.strftime("%Y-%m-%d") if fund_asof is not None else ""),
                        "ticker": t,
                        "weight": float(new_w.get(t, 0.0)),
                        "regime": int(r["regime"]) if pd.notna(r["regime"]) else np.nan,
                        "regime_score": float(r["score"]) if pd.notna(r["score"]) else np.nan,
                        "growth_score": float(r["growth_score"]) if pd.notna(r["growth_score"]) else np.nan,
                        "score_rank": int(r["score_rank"]) if pd.notna(r["score_rank"]) else np.nan,
                        "top_n": int(top_n),
                        "good_regimes": ",".join([str(x) for x in good_regimes]),
                        "sma_window": int(sma_window),
                        "require_above_sma": bool(require_above_sma),
                        "market_gate": bool(market_gate),
                        "market_ok": bool(market_ok),
                        "market_price": m_price,
                        "market_sma": m_sma,
                        "market_sma_window": int(market_sma_window),
                        "market_sma_mult": float(market_sma_mult),
                        "market_entry_mult": float(market_entry_mult),
                        "market_exit_mult": float(market_exit_mult),
                    }
                )
            # CASH residual row (standardized) for this rebalance_date
            try:
                sum_w = float(sum([float(new_w.get(t, 0.0)) for t in new_w.keys()])) if new_w else 0.0
            except Exception:
                sum_w = 0.0
            cash_w = max(0.0, 1.0 - sum_w)
            if abs(cash_w) < 1e-10:
                cash_w = 0.0
            holdings_rows.append(
                {
                    "strategy": "S2",
                    "rebalance_date": rb_date.strftime("%Y-%m-%d"),
                    "fund_asof_date": (fund_asof.strftime("%Y-%m-%d") if fund_asof is not None else ""),
                    "ticker": "CASH",
                    "weight": float(cash_w),
                    "regime": np.nan,
                    "regime_score": np.nan,
                    "growth_score": np.nan,
                    "score_rank": np.nan,
                    "top_n": int(top_n),
                    "good_regimes": ",".join([str(x) for x in good_regimes]),
                    "sma_window": int(sma_window),
                    "require_above_sma": bool(require_above_sma),
                    "market_gate": bool(market_gate),
                    "market_ok": bool(market_ok),
                    "market_price": m_price,
                    "market_sma": m_sma,
                    "market_sma_window": int(market_sma_window),
                    "market_sma_mult": float(market_sma_mult),
                    "market_entry_mult": float(market_entry_mult),
                    "market_exit_mult": float(market_exit_mult),
                }
            )

        else:
            # Risk-off or no candidates -> fully in CASH
            holdings_rows.append(
                {
                    "strategy": "S2",
                    "rebalance_date": rb_date.strftime("%Y-%m-%d"),
                    "fund_asof_date": (fund_asof.strftime("%Y-%m-%d") if fund_asof is not None else ""),
                    "ticker": "CASH",
                    "weight": 1.0,
                    "regime": np.nan,
                    "regime_score": np.nan,
                    "growth_score": np.nan,
                    "score_rank": np.nan,
                    "top_n": int(top_n),
                    "good_regimes": ",".join([str(x) for x in good_regimes]),
                    "sma_window": int(sma_window),
                    "require_above_sma": bool(require_above_sma),
                    "market_gate": bool(market_gate),
                    "market_ok": bool(market_ok),
                    "market_price": m_price,
                    "market_sma": m_sma,
                    "market_sma_window": int(market_sma_window),
                    "market_sma_mult": float(market_sma_mult),
                    "market_entry_mult": float(market_entry_mult),
                    "market_exit_mult": float(market_exit_mult),
                }
            )

        # Apply weights for (rb_date, next_rb] window
        start_idx = dates.get_loc(rb_date)
        if next_rb is not None:
            end_idx = dates.get_loc(next_rb)
            window = dates[(start_idx + 1) : end_idx + 1]
        else:
            window = dates[(start_idx + 1) :]

        if decision.risk_on and window.size > 0:
            cols = [c for c in new_w.keys() if c in ret_wide.columns]
            if cols:
                w_vec = pd.Series(new_w).reindex(cols).fillna(0.0)
                rr = (ret_wide.loc[window, cols] * w_vec.values).sum(axis=1)
                port_ret.loc[window] += rr.values

        old_w = new_w

    equity = (1.0 + port_ret).cumprod()
    equity_df = pd.DataFrame({"date": equity.index.strftime("%Y-%m-%d"), "port_ret": port_ret.values, "equity": equity.values})
    holdings_df = pd.DataFrame(holdings_rows)

    # --- enrich equity with diagnostics (daily market gate, exposure, holdings) ---
    # Daily market gate diagnostics
    if market_ok_series is not None:
        equity_df["market_ok"] = market_ok_series.reindex(dates).fillna(False).astype(int).values
    else:
        equity_df["market_ok"] = 1

    if market_price is not None:
        equity_df["market_price"] = market_price.reindex(dates).astype(float).values
    if market_sma is not None:
        equity_df["market_sma"] = market_sma.reindex(dates).astype(float).values
        # Reference thresholds (entry/exit)
        equity_df["market_entry_th"] = (market_sma.reindex(dates).astype(float) * float(market_entry_mult)).values
        equity_df["market_exit_th"] = (market_sma.reindex(dates).astype(float) * float(market_exit_mult)).values

    # rebalance-level exposure / holdings (forward-filled to daily)
    try:
        tmp_h = holdings_df.copy()
        # normalize date types
        tmp_h["rebalance_date"] = pd.to_datetime(tmp_h["rebalance_date"])
        def _is_risk_ticker(x: str) -> bool:
            s = str(x).strip().upper()
            return (s != "") and (s != "CASH") and (s.lower() not in ("nan", "none"))

        tmp_h["is_risk_ticker"] = tmp_h["ticker"].apply(_is_risk_ticker)

        rb_grp = tmp_h.groupby("rebalance_date", sort=True)
        _rb_func = lambda g: pd.Series({
            "n_holdings": int(g.loc[g["is_risk_ticker"], "ticker"].shape[0]),
            "gross_exposure": float(pd.to_numeric(g.loc[g["is_risk_ticker"], "weight"], errors="coerce").fillna(0.0).sum()),
        })
        try:
            # pandas >= 2.2: grouping columns excluded when include_groups=False
            rb_stats = rb_grp.apply(_rb_func, include_groups=False)
        except TypeError:
            # older pandas
            rb_stats = rb_grp.apply(_rb_func)
        rb_stats["cash_weight"] = 1.0 - rb_stats["gross_exposure"].astype(float)
        rb_stats["risk_on_portfolio"] = (rb_stats["gross_exposure"].astype(float) > 0).astype(int)

        # forward-fill to daily index
        rb_stats = rb_stats.reindex(dates, method="ffill")
        rb_stats = rb_stats.fillna({"n_holdings": 0, "gross_exposure": 0.0, "cash_weight": 1.0, "risk_on_portfolio": 0})
        equity_df["n_holdings"] = rb_stats["n_holdings"].astype(int).values
        equity_df["gross_exposure"] = rb_stats["gross_exposure"].astype(float).values
        equity_df["cash_weight"] = rb_stats["cash_weight"].astype(float).values
        equity_df["risk_on_portfolio"] = rb_stats["risk_on_portfolio"].astype(int).values
    except Exception:
        pass


    daily_ret = pd.Series(port_ret.values, index=dates)
    summary = {
        "strategy": "S2",
        "start": equity.index[0].strftime("%Y-%m-%d"),
        "end": equity.index[-1].strftime("%Y-%m-%d"),
        "cagr": calc_cagr(pd.Series(equity.values, index=dates)),
        "sharpe": calc_sharpe(daily_ret),
        "mdd": calc_mdd(pd.Series(equity.values, index=dates)),
        "avg_daily_ret": float(daily_ret.mean()),
        "vol_daily": float(daily_ret.std(ddof=1)),
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "rebalance_count": int(len(rebalance_dates)),
        "top_n": int(top_n),
        "good_regimes": ",".join([str(x) for x in good_regimes]),
        "sma_window": int(sma_window),
        "require_above_sma": bool(require_above_sma),
        "fundamentals_view": str(fundamentals_view),
        "fundamentals_asof": bool(fundamentals_asof),
        "market_gate": bool(market_gate),
        "market_sma_window": int(market_sma_window),
        "market_sma_mult": float(market_sma_mult),
    }
    summary_df = pd.DataFrame([summary])
    return equity_df, summary_df, holdings_df


# =============================================================================
# 5) 리포팅/스냅샷/저장 태그
# =============================================================================
def build_snapshot_last_portfolio(
    *,
    holdings_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    name_map: Dict[str, str],
    snapshot_date: Optional[pd.Timestamp] = None,
    cash_label: str = "CASH",
) -> pd.DataFrame:
    if holdings_df is None or holdings_df.empty:
        raise RuntimeError("holdings_df is empty; cannot build snapshot.")

    h = holdings_df.copy()
    h["rebalance_date"] = pd.to_datetime(h["rebalance_date"])
    all_reb_dates = sorted(h["rebalance_date"].dropna().unique().tolist())
    if not all_reb_dates:
        raise RuntimeError("no rebalance_date rows in holdings_df.")

    snap_dt = snapshot_date if snapshot_date is not None else all_reb_dates[-1]
    snap_dt = pd.to_datetime(snap_dt)

    h_last = h[h["rebalance_date"] == snap_dt].copy()
    # Exclude CASH pseudo-ticker from 'held' rows (CASH is handled separately)
    held = h_last[
        (h_last["ticker"].astype(str).str.len() > 0) &
        (h_last["ticker"].astype(str).str.upper() != "CASH")
    ].copy()
    held["ticker"] = held["ticker"].astype(str)

    rows: List[Dict] = []

    # build ticker -> set(rebalance_dates held)
    ticker_dates_map: Dict[str, set] = {}
    for t, g in h[h["ticker"].astype(str).str.len() > 0].groupby("ticker"):
        ticker_dates_map[str(t)] = set(pd.to_datetime(g["rebalance_date"]).tolist())

    px_dates = close_wide.index
    if snap_dt not in px_dates:
        raise RuntimeError(f"snapshot_date {snap_dt.date()} not in price index.")

    for _, r in held.iterrows():
        t = str(r["ticker"])
        w = float(r["weight"]) if pd.notna(r.get("weight", np.nan)) else 0.0

        t_dates = ticker_dates_map.get(t, set())
        if snap_dt not in t_dates:
            buy_dt = snap_dt
        else:
            idx = all_reb_dates.index(snap_dt)
            buy_dt = snap_dt
            while idx > 0:
                prev = all_reb_dates[idx - 1]
                if prev in t_dates:
                    buy_dt = prev
                    idx -= 1
                    continue
                break

        entry_px = float(close_wide.loc[buy_dt, t])
        last_px = float(close_wide.loc[snap_dt, t])
        ret = (last_px / entry_px - 1.0) if entry_px != 0 else float("nan")

        i0 = px_dates.get_loc(buy_dt)
        i1 = px_dates.get_loc(snap_dt)
        holding_days = int(i1 - i0)

        rows.append(
            {
                "snapshot_date": snap_dt.strftime("%Y-%m-%d"),
                "ticker": t,
                "name": name_map.get(t, ""),
                "weight": w,
                "buy_date": pd.to_datetime(buy_dt).strftime("%Y-%m-%d"),
                "holding_days": holding_days,
                "entry_price": entry_px,
                "last_price": last_px,
                "return": ret,
            }
        )

    # CASH weight: prefer explicit CASH row in holdings_df (standardized), else compute residual.
    try:
        cash_rows = h_last[h_last["ticker"].astype(str).str.upper() == "CASH"]
        if len(cash_rows) > 0:
            cash_w = float(pd.to_numeric(cash_rows["weight"], errors="coerce").fillna(0.0).sum())
        else:
            sum_w = float(sum([float(r["weight"]) for r in rows])) if rows else 0.0
            cash_w = max(0.0, 1.0 - sum_w)
    except Exception:
        sum_w = float(sum([float(r["weight"]) for r in rows])) if rows else 0.0
        cash_w = max(0.0, 1.0 - sum_w)

    # clamp tiny float noise
    if abs(cash_w) < 1e-10:
        cash_w = 0.0

    rows.append(
        {
            "snapshot_date": snap_dt.strftime("%Y-%m-%d"),
            "ticker": "CASH",
            "name": cash_label,
            "weight": cash_w,
            "buy_date": "",
            "holding_days": 0,
            # Standardize CASH row to avoid NaNs propagating into downstream checks
            "entry_price": 1.0,
            "last_price": 1.0,
            "return": 0.0,
        }
    )

    out = pd.DataFrame(rows).sort_values(["ticker"]).reset_index(drop=True)
    return out



def build_trade_snapshot_history(holdings_df: pd.DataFrame, close_wide: pd.DataFrame, names_map: dict, end_date: str) -> pd.DataFrame:
    """Build per-ticker holding-period return rows for BOTH closed and open positions.

    - Entry/Exit are assumed to occur at the rebalance_date close.
    - If a position is still open at the end, exit_date=end_date and exit_price=last close.
    """
    if holdings_df is None or len(holdings_df) == 0:
        return pd.DataFrame()

    h = holdings_df.copy()
    h = h[h["ticker"].notna()].copy()
    if len(h) == 0:
        return pd.DataFrame()

    h["rebalance_date"] = pd.to_datetime(h["rebalance_date"])
    h["ticker"] = h["ticker"].astype(str)

    # weights per rebalance_date
    by_date = {}
    for d, g in h.groupby("rebalance_date", sort=True):
        w = {t: float(wt) for t, wt in zip(g["ticker"], g["weight"]) if pd.notna(t) and float(wt) > 0}
        by_date[pd.Timestamp(d)] = w

    rb_dates = sorted(by_date.keys())
    if len(rb_dates) == 0:
        return pd.DataFrame()

    end_ts = pd.to_datetime(end_date)
    if end_ts not in close_wide.index:
        # use last available date in close_wide
        end_ts = close_wide.index.max()

    def _px(ts: pd.Timestamp, t: str) -> float:
        try:
            v = close_wide.at[ts, t]
            return float(v) if pd.notna(v) else np.nan
        except Exception:
            return np.nan

    open_pos = {}  # ticker -> dict(entry_date, entry_price)
    trades = []
    trade_id = 0

    prev_w = {}
    for d in rb_dates:
        w = by_date.get(d, {})
        prev_set = set(prev_w.keys())
        curr_set = set(w.keys())

        # exits
        for t in sorted(prev_set - curr_set):
            entry = open_pos.get(t)
            if entry is None:
                continue
            exit_price = _px(d, t)
            trade_id += 1
            trades.append(
                {
                    "trade_id": trade_id,
                    "ticker": t,
                    "name": names_map.get(t, ""),
                    "entry_date": entry["entry_date"].strftime("%Y-%m-%d"),
                    "entry_price": entry["entry_price"],
                    "exit_date": d.strftime("%Y-%m-%d"),
                    "exit_price": exit_price,
                    "holding_days": int((d - entry["entry_date"]).days),
                    "return": (exit_price / entry["entry_price"] - 1.0) if (pd.notna(exit_price) and entry["entry_price"] > 0) else np.nan,
                    "status": "CLOSED",
                }
            )
            open_pos.pop(t, None)

        # entries
        for t in sorted(curr_set - prev_set):
            entry_price = _px(d, t)
            open_pos[t] = {"entry_date": d, "entry_price": entry_price}

        prev_w = w

    # still open -> close at end_ts
    for t, entry in open_pos.items():
        exit_price = _px(end_ts, t)
        trade_id += 1
        trades.append(
            {
                "trade_id": trade_id,
                "ticker": t,
                "name": names_map.get(t, ""),
                "entry_date": entry["entry_date"].strftime("%Y-%m-%d"),
                "entry_price": entry["entry_price"],
                "exit_date": end_ts.strftime("%Y-%m-%d"),
                "exit_price": exit_price,
                "holding_days": int((end_ts - entry["entry_date"]).days),
                "return": (exit_price / entry["entry_price"] - 1.0) if (pd.notna(exit_price) and entry["entry_price"] > 0) else np.nan,
                "status": "OPEN",
            }
        )

    df = pd.DataFrame(trades)

    # C안: 매수/매도 컬럼(결정일=체결일=리밸런싱일 종가 기준), 수익률/수익률(%)
    if len(df) > 0:
        df["buy_date"] = df["entry_date"]
        df["buy_price"] = df["entry_price"]
        df["sell_date"] = df["exit_date"]
        df["sell_price"] = df["exit_price"]
        df["return_pct"] = df["return"] * 100.0
        # 컬럼 순서 정리(가독성)
        cols = [
            "trade_id","ticker","name",
            "buy_date","buy_price","sell_date","sell_price",
            "entry_date","entry_price","exit_date","exit_price",
            "holding_days","return","return_pct","status",
        ]
        cols = [c for c in cols if c in df.columns]
        df = df[cols]
    return df


def _perf_from_equity_and_ret(dates: pd.DatetimeIndex, equity: pd.Series, port_ret: pd.Series) -> dict:
    """Compute CAGR/MDD/Sharpe from daily equity curve and daily returns."""
    if len(equity) == 0:
        return {"cagr": np.nan, "mdd": np.nan, "sharpe": np.nan, "avg_daily_ret": np.nan, "vol_daily": np.nan}

    # CAGR
    days = int((dates[-1] - dates[0]).days)
    years = days / 365.25 if days > 0 else np.nan
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0) if (years and years > 0 and equity.iloc[-1] > 0) else np.nan

    # MDD
    eq = equity.astype(float).values
    running_max = np.maximum.accumulate(eq)
    dd = (eq / running_max) - 1.0
    mdd = float(np.nanmin(dd)) if len(dd) else np.nan

    # Sharpe (daily)
    r = port_ret.astype(float).values
    mu = np.nanmean(r)
    sig = np.nanstd(r, ddof=0)
    sharpe = float((mu / sig) * math.sqrt(252)) if sig and sig > 0 else np.nan

    return {
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "avg_daily_ret": float(mu),
        "vol_daily": float(sig),
    }


def build_perf_windows_report(equity_df: pd.DataFrame, windows_years=(1, 2, 3, 5)) -> pd.DataFrame:
    """Return a tidy report with 1/2/3/5y metrics, and gate ON/OFF splits.

    - Overall metrics use the equity curve within the window.
    - Gate ON/OFF splits provide:
      (a) fullcurve metrics on the sliced equity (start/end within subset),
      (b) chain metrics from compounding returns only on subset days.
    """
    if equity_df is None or len(equity_df) == 0:
        return pd.DataFrame()

    df = equity_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if "market_ok" not in df.columns:
        df["market_ok"] = 1  # treat as always on

    end = df["date"].iloc[-1]
    out = []

    for y in windows_years:
        start = end - pd.DateOffset(years=int(y))
        w = df[df["date"] >= start].copy()
        if len(w) < 10:
            continue

        dates = pd.DatetimeIndex(w["date"])
        equity = w["equity"].astype(float)
        pret = w["port_ret"].astype(float)
        base = _perf_from_equity_and_ret(dates, equity, pret)
        out.append({"window": f"{y}y", "segment": "ALL", "mode": "fullcurve", **base, "days": len(w), "start": dates[0].strftime("%Y-%m-%d"), "end": dates[-1].strftime("%Y-%m-%d")})

        for seg_name, mask in [("GATE_ON", w["market_ok"].astype(int) == 1), ("GATE_OFF", w["market_ok"].astype(int) == 0)]:
            s = w[mask].copy()
            if len(s) < 10:
                continue

            d2 = pd.DatetimeIndex(s["date"])
            eq2 = s["equity"].astype(float)
            r2 = s["port_ret"].astype(float)

            # fullcurve on sliced equity (not isolated)
            m_full = _perf_from_equity_and_ret(d2, eq2 / eq2.iloc[0], r2)  # normalize to start=1
            out.append({"window": f"{y}y", "segment": seg_name, "mode": "fullcurve", **m_full, "days": len(s), "start": d2[0].strftime("%Y-%m-%d"), "end": d2[-1].strftime("%Y-%m-%d")})

            # chain-only metrics
            chain_eq = (1.0 + r2.fillna(0.0)).cumprod()
            m_chain = _perf_from_equity_and_ret(d2, chain_eq, r2)
            out.append({"window": f"{y}y", "segment": seg_name, "mode": "chain", **m_chain, "days": len(s), "start": d2[0].strftime("%Y-%m-%d"), "end": d2[-1].strftime("%Y-%m-%d")})

    return pd.DataFrame(out)



def _stamp_s2(args: argparse.Namespace, start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> str:
    gr_tag = (args.good_regimes or "4,3").replace(",", "")
    sma_tag = f"SMA{int(args.sma_window)}" + ("_NOSMA" if args.no_sma_filter else "")
    mg_tag = "MG1" if args.market_gate else "MG0"

    ex_tag = "EX0"
    try:
        if (not bool(getattr(args, "no_exit_below_sma", False))) and int(getattr(args, "exit_below_sma_weeks", 0)) > 0:
            ex_tag = f"EX{int(getattr(args, 'exit_below_sma_weeks', 0))}"
    except Exception:
        ex_tag = "EX0"

    rb_tag = "W" if (args.rebalance or "M").upper() == "W" else "M"
    stamp = (
        f"{args.horizon}_S2_RB{rb_tag}_top{int(args.top_n)}_GR{gr_tag}_{sma_tag}_{mg_tag}_{ex_tag}"
        f"_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}"
    )
    return stamp


# =============================================================================
# 6) CLI main: 실행 파라미터 / 흐름 제어 / 저장
# =============================================================================
def main() -> None:
    _log(f"[INFO] script_version={__VERSION__}")
    ap = argparse.ArgumentParser()

    ap.add_argument("--regime-db", required=True)
    ap.add_argument("--regime-table", default="regime_history")

    ap.add_argument("--price-db", required=True)
    ap.add_argument("--price-table", default="prices_daily")

    ap.add_argument("--universe-file", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--name-col", default="", help="optional name column in universe csv (auto-detect if empty)")

    ap.add_argument("--horizon", "--primary-horizon", dest="horizon", default="3m", help="primary horizon (e.g., 1y, 6m, 3m)")

    ap.add_argument("--strategy", default="S2", choices=["R2", "S1", "S2"], help="R2=spread Long/Cash, S1=market+regime+features, S2=regime+fundamentals+SMA")
    ap.add_argument("--good-regimes", default="4,3", help="comma-separated regime priority order (default: 4,3)")

    # Defaults updated per request: TOP50
    ap.add_argument("--top-n", type=int, default=50, help="portfolio size (default: 50)")
    ap.add_argument("--min-holdings", type=int, default=15, help="minimum holdings when risk-on (default: 15)")

    ap.add_argument("--start", default="", help="YYYY-MM-DD (optional)")
    ap.add_argument("--end", default="", help="YYYY-MM-DD (optional)")
    ap.add_argument("--rebalance", default="M", choices=["M", "W"], help="M=month-end, W=weekly anchored decision day (default Wed) with holiday shift")
    ap.add_argument("--weekly-anchor-weekday", type=int, default=2, help="Weekly decision anchor weekday for --rebalance W: 0=Mon..2=Wed..4=Fri. If holiday, apply --weekly-holiday-shift.")
    ap.add_argument("--weekly-holiday-shift", choices=["prev", "next"], default="prev", help="If anchor weekday is a holiday/missing, choose previous or next trading day within that week.")
    ap.add_argument("--safe-intraday", dest="safe_intraday", action="store_true", default=True, help="If --end is today and local time is before market close, snap end to previous trading day to avoid intraday prices.")
    ap.add_argument("--no-safe-intraday", dest="safe_intraday", action="store_false", help="Disable intraday safety snapping.")

    # S2 fundamentals: use view
    ap.add_argument("--fundamentals-db", default="", help="fundamentals db path (required for S2)")
    ap.add_argument("--fundamentals-view", default="s2_fund_scores_monthly", help="view name used for S2 candidates (default: vw_s2_top30_monthly)")
    ap.add_argument("--no-fundamentals-asof", action="store_true", help="S2: disable monthly as-of mapping for weekly rebalancing (default: as-of enabled when rebalance=W)")

    # Defaults updated per request: SMA60
    ap.add_argument("--sma-window", type=int, default=140, help="S2 stock price filter SMA window (default: 140)")
    ap.add_argument("--no-sma-filter", action="store_true", help="if set, S2 does NOT require close > SMA")
    ap.add_argument("--require-above-sma", dest="no_sma_filter", action="store_false", help="Alias (default): require close > SMA (i.e., do NOT set --no-sma-filter).")

    # P2-2 stock-level defense: exit after N consecutive rebalance closes below SMA
    ap.add_argument("--exit-below-sma-weeks", type=int, default=2, help="S2: exit rule (P2-2). If held close < SMA for N consecutive rebalances, exit (default: 2). Set 0 to disable.")
    ap.add_argument("--no-exit-below-sma", action="store_true", help="Disable P2-2 exit rule even if exit-below-sma-weeks > 0")


    # S2 market gate
    ap.add_argument("--market-gate", dest="market_gate", action="store_true", default=True,
                    help="S2: enable market gate with hysteresis (default: enabled). Entry if price > SMA*entry_mult; exit if price < SMA*exit_mult")
    ap.add_argument("--no-market-gate", dest="market_gate", action="store_false",
                    help="Disable market gate (override default enabled)")
    ap.add_argument("--market-scope", default="KOSPI", choices=["KOSPI", "ALL"], help="S2: proxy scope. Uses universe column `market` if present; otherwise falls back to ALL")
    ap.add_argument("--market-sma-window", type=int, default=60, help="S2 market gate SMA window (default: 60)")
    ap.add_argument("--market-sma-mult", type=float, default=1.00, help="S2 market gate ENTRY multiplier (default: 1.00)")
    ap.add_argument("--market-exit-mult", type=float, default=1.00, help="S2 market gate EXIT multiplier (default: 1.00). Should be <= entry_mult")

    ap.add_argument("--fee-bps", type=float, default=10.0)
    ap.add_argument("--slippage-bps", type=float, default=10.0)

    ap.add_argument("--snapshot-date", default="", help="snapshot portfolio date YYYY-MM-DD (default: end)")
    ap.add_argument("--no-snapshot", action="store_true", help="if set, do not save snapshot csv")

    
    # Google Sheets upload (optional)
    ap.add_argument("--gsheet-enable", action=argparse.BooleanOptionalAction, default=True,
                    help="Upload snapshot/trades/windows to Google Sheets (default: enabled). Use --no-gsheet-enable to disable.")
    ap.add_argument("--gsheet-prefix", default="S2", help="Google Sheets: sheet name prefix (default: S2). New sheets will be created as <prefix>_YYYYMMDD_SEQ_kind")
    ap.add_argument("--gsheet-cred", default=DEFAULT_GSHEET_CRED, help="service account credentials json path")
    ap.add_argument("--gsheet-id", default=DEFAULT_GSHEET_ID, help="Google Spreadsheet ID (the /d/<ID>/ part)")
    ap.add_argument("--gsheet-tab", default="", help="Base tab name (e.g., 'S2_snapshot'). Suffixes _trades/_windows are used for additional tables.")
    ap.add_argument("--gsheet-mode", default="overwrite", choices=["new_sheet","overwrite","append"], help="overwrite clears tab; append adds rows")
    ap.add_argument("--gsheet-ledger", action="store_true", default=True, help="generate/upload rebalance ledger sheet")
    ap.add_argument("--gsheet-start-cell", default="A1", help="start cell for writing (default: A1)")
    
    # Trades CSV: keep only recent N years (default: 6). Set 0 to keep all.
    ap.add_argument("--trades-lookback-years", type=int, default=6, help="Save trades limited to last N years by exit_date (default: 6). Set 0 to keep all.")

    ap.add_argument("--outdir", default=r".\reports\backtest_regime")
    args = ap.parse_args()

    orig_cwd = Path.cwd()
    project_root = resolve_project_root(orig_cwd)

    def _abs_path(p: str) -> str:
        """Resolve a possibly-relative path against the ORIGINAL working directory."""
        pp = Path(p)
        if pp.is_absolute():
            return str(pp)
        return str((orig_cwd / pp).resolve())

    # IMPORTANT: we may chdir() to project_root for imports / relative resources,
    # so make all user-supplied paths absolute first.
    args.regime_db = _abs_path(args.regime_db)
    args.price_db = _abs_path(args.price_db)
    if getattr(args, "fundamentals_db", None):
        args.fundamentals_db = _abs_path(args.fundamentals_db)
    args.universe_file = _abs_path(args.universe_file)
    if getattr(args, "outdir", None):
        args.outdir = _abs_path(args.outdir)

    os.chdir(project_root)

    # Universe
    univ_df = pd.read_csv(args.universe_file, dtype={args.ticker_col: str})
    univ_df[args.ticker_col] = univ_df[args.ticker_col].apply(normalize_ticker)

    # ---------------------------------------------------------------------
    # Market mapping (KOSPI/KOSDAQ) for outputs (snapshot/trades/holdings)
    # Source priority: 'market' -> 'mkt' -> '시장'
    # ---------------------------------------------------------------------
    market_map: dict[str, str] = {}
    try:
        if "market" in univ_df.columns:
            market_map = dict(zip(univ_df[args.ticker_col].astype(str), univ_df["market"].astype(str)))
        elif "mkt" in univ_df.columns:
            market_map = dict(zip(univ_df[args.ticker_col].astype(str), univ_df["mkt"].astype(str)))
        elif "시장" in univ_df.columns:
            market_map = dict(zip(univ_df[args.ticker_col].astype(str), univ_df["시장"].astype(str)))
        else:
            market_map = {}
    except Exception:
        market_map = {}
    if market_map:
        market_map = {str(k): str(v).strip().upper() for k, v in market_map.items()}
    market_map["CASH"] = "CASH"


    tickers = load_universe_tickers(args.universe_file, args.ticker_col)
    name_map, resolved_name_col = load_universe_name_map(args.universe_file, args.ticker_col, args.name_col)
    if resolved_name_col:
        _log(f"[INFO] universe name_col={resolved_name_col} | names={len(name_map):,}")
    _log(f"[INFO] tickers={len(tickers):,}")

    # Prices
    close_wide = load_prices_wide(
        price_db=str(Path(args.price_db).resolve()),
        price_table=args.price_table,
        tickers=tickers,
        start=args.start or None,
        end=args.end or None,
    )

    start_dt = close_wide.index.min()
    end_dt = close_wide.index.max()
    # Intraday safety: if --end is today and local time is before market close,
    # snap end to previous trading day to avoid using partial/intraday prices.
    if getattr(args, "safe_intraday", True) and getattr(args, "end", None):
        try:
            requested_end = pd.Timestamp(args.end).normalize()
            now = datetime.now()
            today_local = pd.Timestamp(now.date()).normalize()
            if requested_end == today_local and end_dt.normalize() == requested_end:
                if (now.hour, now.minute) < (15, 30) and len(close_wide.index) >= 2:
                    prev_dt = pd.Timestamp(close_wide.index[-2]).normalize()
                    _log(f"[INFO] safe_intraday: end={requested_end.date()} but now={now.strftime('%H:%M')} < 15:30 -> snapping end to prev trading day {prev_dt.date()}")
                    close_wide = close_wide.loc[:prev_dt].copy()
                    start_dt = close_wide.index.min()
                    end_dt = close_wide.index.max()
        except Exception as e:
            _log(f"[WARN] safe_intraday: failed to apply intraday safety ({e}). Continuing without snap.")

    ret_wide = compute_daily_returns(close_wide)
    _log(f"[INFO] price dates={len(close_wide):,} | {start_dt.date()}..{end_dt.date()}")

    # Regime
    reg_primary = load_regime_panel(
        regime_db=str(Path(args.regime_db).resolve()),
        regime_table=args.regime_table,
        horizon=args.horizon,
        tickers=tickers,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
    )
    _log(f"[INFO] regime(primary) rows={len(reg_primary):,} | horizon={args.horizon}")

    # Universe hygiene: keep tickers with price+regime on end date
    def _tickers_with_regime_on_date(reg_df: pd.DataFrame, dt: pd.Timestamp) -> set:
        if reg_df is None or reg_df.empty:
            return set()
        return set(reg_df.loc[reg_df["date"] == dt, "ticker"].astype(str).map(_ensure_ticker6))

    elig = set(close_wide.columns)
    if end_dt in close_wide.index:
        elig &= set(close_wide.loc[end_dt].dropna().index)
    elig &= _tickers_with_regime_on_date(reg_primary, end_dt)

    dropped = sorted(set(close_wide.columns) - elig)
    if dropped:
        head = ", ".join(dropped[:20])
        tail = " ..." if len(dropped) > 20 else ""
        _log(f"[INFO] excluded tickers (missing price/regime at end): n={len(dropped)} | {head}{tail}")

    tickers = [t for t in tickers if t in elig]
    close_wide = close_wide[tickers]
    ret_wide = ret_wide[tickers]
    reg_primary = reg_primary[reg_primary["ticker"].isin(tickers)].copy()

    # Rebalance calendar
    if (args.rebalance or "M").upper() == "W":
        rb_dates = week_anchor_dates(close_wide.index, anchor_weekday=int(args.weekly_anchor_weekday), holiday_shift=str(args.weekly_holiday_shift))
        _log(f"[INFO] rebalance dates={len(rb_dates):,} (week-anchor: weekday={int(args.weekly_anchor_weekday)}, holiday_shift={str(args.weekly_holiday_shift)})")
    else:
        rb_dates = month_end_dates(close_wide.index)
        _log(f"[INFO] rebalance dates={len(rb_dates):,} (month-end)")

    # Strategy dispatch (v2 currently implements S2 fully)
    strategy = (args.strategy or "S2").upper()
    if strategy != "S2":
        raise RuntimeError("This v2 refactor currently supports S2 execution path only. Use v1 for R2/S1 or extend here.")

    if not args.fundamentals_db:
        raise RuntimeError("S2 requires --fundamentals-db (view is inside that db).")

    good_regimes = _parse_good_regimes(args.good_regimes)
    require_above_sma = (not bool(args.no_sma_filter))

    fundamentals_asof = (str(args.strategy).upper() == 'S2') and (str(args.rebalance).upper() == 'W') and (not bool(args.no_fundamentals_asof))

    # Market scope tickers
    scope = (getattr(args, "market_scope", "KOSPI") or "KOSPI").upper()
    scope_tickers = tickers
    if scope == "KOSPI":
        if "market" in univ_df.columns:
            mcol = univ_df["market"].astype(str).str.upper()
            scope_tickers = univ_df[mcol.str.contains("KOSPI")][args.ticker_col].tolist()
        else:
            _log("[WARN] universe has no 'market' column; market_scope=KOSPI falls back to ALL.")
            scope_tickers = tickers

    _log(
        "[INFO] strategy=S2(v2) | "
        f"good_regimes={good_regimes} | top_n={int(args.top_n)} | "
        f"sma_window={int(args.sma_window)} | require_above_sma={require_above_sma} | "
        f"fund_view={args.fundamentals_view} | "
        f"market_gate={bool(args.market_gate)} | market_sma_window={int(args.market_sma_window)} | "
        f"exit_below_sma_weeks={int(args.exit_below_sma_weeks)} | enable_exit_below_sma={not bool(args.no_exit_below_sma)}"
    )

    equity_df, summary_df, holdings_df = backtest_s2_v2(
        close_wide=close_wide,
        ret_wide=ret_wide,
        regime_primary=reg_primary,
        fundamentals_db=str(Path(args.fundamentals_db).resolve()),
        fundamentals_view=str(args.fundamentals_view).strip(),
        fundamentals_asof=bool(fundamentals_asof),
        rebalance_dates=rb_dates,
        fee_bps=float(args.fee_bps),
        slippage_bps=float(args.slippage_bps),
        top_n=int(args.top_n),
        min_holdings=int(args.min_holdings),
        good_regimes=good_regimes,
        sma_window=int(args.sma_window),
        require_above_sma=bool(require_above_sma),
        market_gate=bool(args.market_gate),
        market_scope_tickers=scope_tickers,
        market_sma_window=int(args.market_sma_window),
        market_sma_mult=float(args.market_sma_mult),
        market_entry_mult=float(args.market_sma_mult),
        market_exit_mult=float(args.market_exit_mult),
        exit_below_sma_weeks=int(args.exit_below_sma_weeks),
        enable_exit_below_sma=(not bool(args.no_exit_below_sma)) and int(args.exit_below_sma_weeks) > 0,
    )

    # Save
    outdir = (Path(project_root) / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    stamp = _stamp_s2(args, start_dt, end_dt)
    p_equity = outdir / f"regime_bt_equity_{stamp}.csv"
    p_sum = outdir / f"regime_bt_summary_{stamp}.csv"
    p_hold = outdir / f"regime_bt_holdings_{stamp}.csv"

    equity_df.to_csv(p_equity, index=False, encoding="utf-8-sig")
    summary_df.to_csv(p_sum, index=False, encoding="utf-8-sig")
    holdings_df.to_csv(p_hold, index=False, encoding="utf-8-sig")

    # Rebalance ledger (order book style)
    ledger_df = pd.DataFrame()
    p_ledger = outdir / f"regime_bt_ledger_{stamp}.csv"
    if getattr(args, "gsheet_ledger", False):
        try:
            ledger_df = _build_rebalance_ledger(
                holdings_df=holdings_df,
                close_wide=close_wide,
                name_map=name_map,
                market_map=market_map if isinstance(market_map, dict) else {},
                qty_default=1,
                ticker_col="ticker",
            )
            if not ledger_df.empty:
                ledger_df.to_csv(p_ledger, index=False, encoding="utf-8-sig")
                print(f"[SAVE] {p_ledger}")
        except Exception as e:
            print(f"[WARN] ledger build failed: {e}")

    # Snapshot
    if not args.no_snapshot:
        snap_dt = pd.to_datetime(args.snapshot_date) if args.snapshot_date else None
        snap_df = build_snapshot_last_portfolio(
            holdings_df=holdings_df,
            close_wide=close_wide,
            name_map=name_map,
            snapshot_date=snap_dt,
            cash_label="CASH",
        )
        p_snap = outdir / f"regime_bt_snapshot_{stamp}.csv"
        snap_df = _attach_market_col(snap_df, market_map, ticker_col="ticker", out_col="market")
        snap_df = _sort_snapshot_by_return(snap_df, return_col="return")
        snap_df.to_csv(p_snap, index=False, encoding="utf-8-sig")
        _log(f"[SAVE] {p_snap}")
        _log(f"[INFO] outdir={outdir} | stamp={stamp}")

        # [ADD] trade snapshot (closed + open) and performance windows report (1/2/3/5y, gate on/off)
        try:
            trade_df = build_trade_snapshot_history(holdings_df, close_wide, names_map=name_map, end_date=pd.to_datetime(equity_df["date"]).max().strftime("%Y-%m-%d"))
            # Limit trades CSV to recent N years (default 6) to keep reports concise
            if getattr(args, "trades_lookback_years", 6) and "exit_date" in trade_df.columns:
                try:
                    _end_dt = pd.to_datetime(equity_df["date"]).max()
                    _cutoff = _end_dt - pd.DateOffset(years=int(args.trades_lookback_years))
                    trade_df["exit_date"] = pd.to_datetime(trade_df["exit_date"], errors="coerce")
                    # keep recent closed trades + all open trades (exit_date is NaT)
                    trade_df = trade_df[(trade_df["exit_date"].isna()) | (trade_df["exit_date"] >= _cutoff)].copy()
                except Exception as _e:
                    _log(f"[WARN] trades lookback filter skipped: {_e}")
            if len(trade_df) > 0:
                p_trades = outdir / f"regime_bt_snapshot_{stamp}__trades.csv"
                trade_df = _attach_market_col(trade_df, market_map, ticker_col="ticker", out_col="market")
                trade_df.to_csv(p_trades, index=False, encoding="utf-8-sig")
                _log(f"[SAVE] {p_trades}")
                # C안: 라운드트립(CLOSED)만 저장
                try:
                    trade_c = trade_df[trade_df["status"].astype(str).str.upper() == "CLOSED"].copy() if "status" in trade_df.columns else trade_df.copy()
                    keep_cols = ["trade_id","ticker","name","buy_date","buy_price","sell_date","sell_price","holding_days","return","return_pct","status"]
                    keep_cols = [c for c in keep_cols if c in trade_c.columns]
                    if keep_cols:
                        trade_c = trade_c[keep_cols]
                except Exception:
                    trade_c = trade_df.copy()

                p_trades_c = outdir / f"regime_bt_trades_C_{stamp}.csv"
                trade_c.to_csv(p_trades_c, index=False, encoding="utf-8-sig")
                _log(f"[SAVE] {p_trades_c}")
        except Exception as e:
            _log(f"[WARN] trade snapshot build failed: {e}")

        try:
            win_df = build_perf_windows_report(equity_df, windows_years=(1, 2, 3, 5))
            if len(win_df) > 0:
                p_win = outdir / f"regime_bt_perf_windows_{stamp}.csv"
                win_df.to_csv(p_win, index=False, encoding="utf-8-sig")
                _log(f"[SAVE] {p_win}")
        except Exception as e:
            _log(f"[WARN] perf windows report failed: {e}")


    
        # --- Google Sheets upload (snapshot/trades/windows) ---
        if args.gsheet_enable:
            upload_snapshot_bundle, GSheetConfig = _try_import_gsheet_uploader(project_root)
            if upload_snapshot_bundle is None:
                expected = (project_root / "src" / "utils" / "gsheet_uploader.py")
                _log(f"[GSHEET][ERROR] uploader import failed. Expected: {expected}")
            else:
                try:
                    # sheet name prefix (default: S2) -> creates NEW sheets every run:
                    #   <prefix>_<YYYYMMDD>_<SEQ3>_snapshot|trades|windows
                    prefix = str(getattr(args, "gsheet_prefix", "S2")).strip() or "S2"

                    # Use snapshot_date (if provided) else end date for naming YYYYMMDD
                    snap_date = args.snapshot_date or args.end
                    yyyymmdd = str(snap_date).replace("-", "") if snap_date else None

                    tdf = trade_df if ("trade_df" in locals() and isinstance(trade_df, pd.DataFrame) and len(trade_df) > 0) else None
                    wdf = win_df if ("win_df" in locals() and isinstance(win_df, pd.DataFrame) and len(win_df) > 0) else None

                    # trades_C: round-trip only (CLOSED) with buy/sell + return_pct
                    tdf_c = None
                    if tdf is not None and "status" in tdf.columns:
                        tdf_c = tdf[tdf["status"].astype(str).str.upper() == "CLOSED"].copy()
                        keep_cols = ["trade_id","ticker","name","buy_date","buy_price","sell_date","sell_price","holding_days","return","return_pct","status"]
                        keep_cols = [c for c in keep_cols if c in tdf_c.columns]
                        if keep_cols:
                            tdf_c = tdf_c[keep_cols]
                    if tdf is not None:
                        tdf = _attach_market_col(tdf, market_map, ticker_col="ticker", out_col="market")
                    if wdf is not None:
                        wdf = wdf  # no market needed
                    if snap_df is not None:
                        snap_df = _attach_market_col(snap_df, market_map, ticker_col="ticker", out_col="market")
                    if tdf_c is not None:
                        tdf_c = _attach_market_col(tdf_c, market_map, ticker_col="ticker", out_col="market")

                    snap_df = _sort_snapshot_by_return(snap_df, return_col="return")

                    # stamp: prefix_YYYYMMDD (overwrite 모드면 동일명 시트에 덮어쓰기)
                    stamp = f"{prefix}_{yyyymmdd}"
                    cfg = GSheetConfig(
                        cred_path=(args.gsheet_cred or DEFAULT_GSHEET_CRED),
                        spreadsheet_id=(args.gsheet_id or DEFAULT_GSHEET_ID),
                        mode=str(getattr(args, "gsheet_mode", "new_sheet")),
                        start_cell=str(getattr(args, "gsheet_start_cell", "A1")),
                    )
                    # gsheet sheet-name components (prefix/date/seq).
                    # For overwrite mode, use a fixed seq=1 to avoid sheet count growth.
                    date_yyyymmdd = yyyymmdd
                    seq = 1 if str(args.gsheet_mode).lower() == "overwrite" else (int(datetime.datetime.now().strftime("%H%M%S")) % 1000)
                    
                    created = upload_snapshot_bundle(
                        cfg,
                        prefix=prefix,
                        date_yyyymmdd=date_yyyymmdd,
                        seq=seq,
                        snapshot_df=snap_df,
                        trades_df=tdf,
                        windows_df=wdf,
                        trades_c_df=tdf_c,
                        ledger_df=ledger_df,
                        mode=args.gsheet_mode,
                    )
                    _log(f"[GSHEET] created sheets: {created}")
                except Exception as e:
                    _log(f"[GSHEET][ERROR] upload failed: {e}")
    _log("[SUMMARY]")
    _log("=" * 80)
    _log(summary_df.to_string(index=False))
    _log("")
    _log(f"[SAVE] {p_sum}")
    _log(f"[SAVE] {p_equity}")
    _log(f"[SAVE] {p_hold}")
    _log("[INFO] done.")


if __name__ == "__main__":
    main()