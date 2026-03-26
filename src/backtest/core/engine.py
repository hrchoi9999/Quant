# src/backtest/core/engine.py ver 2026-02-23_001
"""Backtest engine (refactor path)

Key compatibility goals (golden regression):
- Weekly rebalance decision dates are *decision* dates; portfolio changes apply from NEXT trading day.
- Snapshot schema matches legacy:
  snapshot_date,ticker,name,market,weight,buy_date,holding_days,entry_price,last_price,return
- Holding_days uses trading-day count based on close_wide index (KRX holidays excluded).
- Summary metrics match legacy (CAGR/MDD/Sharpe/avg_daily_ret/vol_daily, fee/slippage, rebalance_count).

This engine remains strategy-agnostic, but supports "decision-date" semantics via
Strategy.decide() being called on decision dates, then applied from the next trading day.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple

import numpy as np
import pandas as pd

from src.backtest.core.tickers import normalize_ticker
from src.backtest.core.data import next_trading_day
from src.backtest.strategies.base import Strategy, RebalanceDecision
from src.backtest.contracts import BacktestResult

def _calc_turnover(prev_w: pd.Series, new_w: pd.Series) -> float:
    """Approx turnover = sum(|w_new - w_old|)/2"""
    prev_w = prev_w.fillna(0.0)
    new_w = new_w.fillna(0.0)
    return float(new_w.sub(prev_w, fill_value=0.0).abs().sum() / 2.0)


def _asof_slice(df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    if asof in df.index:
        return df.loc[:asof]
    return df.loc[df.index <= asof]


def _safe_name(name_map: Dict[str, str], ticker: str) -> str:
    try:
        return str(name_map.get(ticker, ""))
    except Exception:
        return ""


def _safe_market(market_map: Dict[str, str], ticker: str) -> str:
    try:
        return str(market_map.get(ticker, ""))
    except Exception:
        return ""


def _count_trading_days(dates: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Count trading days in (start, end] based on available price dates."""
    if start is None or end is None:
        return 0
    if end <= start:
        return 0
    # dates is sorted DatetimeIndex
    mask = (dates > start) & (dates <= end)
    return int(mask.sum())


@dataclass
class _PendingRebalance:
    decision_date: pd.Timestamp
    exec_date: pd.Timestamp
    new_weights: pd.Series
    turnover: float
    cost: float


def run_backtest(
    strategy: Strategy,
    close_wide: pd.DataFrame,
    ret_wide: pd.DataFrame,
    regime_panel: pd.DataFrame,
    rebalance_dates: List[pd.Timestamp],
    fee_bps: float,
    slippage_bps: float,
    name_map: Optional[Dict[str, str]] = None,
    market_map: Optional[Dict[str, str]] = None,
) -> BacktestResult:
    """Run a backtest and return a standardized BacktestResult bundle."""

    name_map = name_map or {}
    market_map = market_map or {}

    dates = close_wide.index
    rb_set = set(pd.to_datetime(rebalance_dates))

    # portfolio state
    w = pd.Series(0.0, index=ret_wide.columns)
    eq = 1.0

    # track entry info (decision-date based)
    entry_date: Dict[str, pd.Timestamp] = {}
    entry_price: Dict[str, float] = {}

    # for snapshot we need last decision weights/date
    last_decision_date: Optional[pd.Timestamp] = None
    last_decision_weights: Optional[pd.Series] = None

    pending: Optional[_PendingRebalance] = None

    equity_vals: List[Tuple[pd.Timestamp, float, float]] = []  # (date, equity, port_ret)
    holdings_rows: List[Dict[str, object]] = []
    # Candidate/selection diagnostics per rebalance (for divergence root-cause).
    selection_rows: List[Dict[str, object]] = []

    # portfolio state
    w = pd.Series(0.0, index=ret_wide.columns)
    eq = 1.0

    # track entry info (execution-date based for snapshot)
    entry_date: Dict[str, pd.Timestamp] = {}
    entry_price: Dict[str, float] = {}

    # for snapshot we need last decision weights/date
    last_decision_date: Optional[pd.Timestamp] = None
    last_decision_weights: Optional[pd.Series] = None

    pending: Optional[_PendingRebalance] = None

    # --- main loop ---
    for dt in dates:
        dt = pd.Timestamp(dt)
        eq_prev = eq

        # 1) Daily mark-to-market using CURRENT effective weights.
        #    (New portfolio decided on rebalance_date is NOT effective until after trade_date.)
        r_price = float((ret_wide.loc[dt] * w).sum())
        eq *= (1.0 + r_price)

        # 2) Execute pending rebalance on its trade_date (T+1) at END of day:
        #    - Apply transaction costs on trade_date
        #    - Update holdings/weights for subsequent days (returns start next trading day)
        if pending is not None and dt == pending.exec_date:
            # Apply cost on execution day (trade_date)
            eq *= (1.0 - pending.cost)

            prev_w = w
            w = pending.new_weights

            # Track entry based on execution date (trade_date)
            trade_dt = pd.Timestamp(dt)

            prev_set = set(prev_w[prev_w.abs() > 0].index.astype(str))
            new_set = set(w[w.abs() > 0].index.astype(str))

            exited = prev_set - new_set
            entered = new_set - prev_set

            for t in exited:
                entry_date.pop(t, None)
                entry_price.pop(t, None)

            for t in entered:
                t = str(t)
                if t in close_wide.columns and trade_dt in close_wide.index:
                    px = float(close_wide.loc[trade_dt, t])
                else:
                    px = float('nan')
                entry_date[t] = trade_dt
                entry_price[t] = px

            pending = None

        # 3) On decision dates, compute next weights (but do not execute same day)
        if dt in rb_set:
            decision: RebalanceDecision = strategy.decide(
                asof=dt,
                close_wide=_asof_slice(close_wide, dt),
                ret_wide=_asof_slice(ret_wide, dt),
                regime_panel=_asof_slice(regime_panel, dt),
            )
            new_w = decision.weights.reindex(ret_wide.columns).fillna(0.0)

            turnover = _calc_turnover(w, new_w)
            cost = turnover * ((fee_bps + slippage_bps) / 10000.0)

            pending = _PendingRebalance(
                decision_date=pd.Timestamp(dt),
                exec_date=next_trading_day(dates, pd.Timestamp(dt)),
                new_weights=new_w,
                turnover=turnover,
                cost=cost,
            )

            last_decision_date = pd.Timestamp(dt)
            last_decision_weights = new_w.copy()

            # --- holdings snapshot at decision date (CONVENTIONS semantics) ---
            # Save weights > 0 plus CASH residual. If all weights are 0, store CASH=1.
            try:
                w_pos = new_w.copy().fillna(0.0)
                w_pos = w_pos[w_pos > 0].sort_values(ascending=False)
                sum_w = float(w_pos.sum()) if len(w_pos) else 0.0
                cash_w = max(0.0, 1.0 - sum_w)
                if sum_w <= 0:
                    cash_w = 1.0

                trade_dt = next_trading_day(dates, pd.Timestamp(dt))

                # --- selection log (top candidates + filter flags) ---
                # StrategyS2 provides cand_table in decision.meta (DataFrame).
                # We persist it as rows to diagnose first divergence date.
                try:
                    meta = getattr(decision, "meta", None) or {}
                    cand_df = meta.get("cand_table")
                    if isinstance(cand_df, pd.DataFrame) and not cand_df.empty:
                        tmp = cand_df.copy()
                        tmp["rebalance_date"] = pd.Timestamp(dt).strftime("%Y-%m-%d")
                        tmp["trade_date"] = pd.Timestamp(trade_dt).strftime("%Y-%m-%d")
                        selection_rows.extend(tmp.to_dict("records"))
                except Exception:
                    pass

                for t, wt in w_pos.items():
                    holdings_rows.append({
                        'rebalance_date': pd.Timestamp(dt).strftime('%Y-%m-%d'),
                        'trade_date': trade_dt.strftime('%Y-%m-%d'),
                        'ticker': normalize_ticker(t),
                        'weight': float(wt),
                    })
                holdings_rows.append({
                    'rebalance_date': pd.Timestamp(dt).strftime('%Y-%m-%d'),
                    'trade_date': trade_dt.strftime('%Y-%m-%d'),
                    'ticker': 'CASH',
                    'weight': float(cash_w),
                })
            except Exception:
                # Do not fail the backtest due to reporting-only artifacts.
                pass

        port_ret_total = float(eq / eq_prev - 1.0)
        equity_vals.append((dt, eq, port_ret_total))

    equity_df = pd.DataFrame(equity_vals, columns=['date', 'equity', 'port_ret']).set_index('date')

    # --- snapshot (legacy schema) ---
    if last_decision_date is None:
        snapshot_df = pd.DataFrame(columns=[
            "snapshot_date","ticker","name","market","weight","buy_date","holding_days","entry_price","last_price","return"
        ])
        snapshot_date_str = ""
        w_snap = pd.Series(dtype=float)
    else:
        snapshot_date = last_decision_date
        snapshot_date_str = snapshot_date.date().isoformat()
        # snapshot weights (avoid ambiguous truth value for pandas Series)
        if last_decision_weights is None:
            w_snap = pd.Series(0.0, index=ret_wide.columns)
        else:
            if isinstance(last_decision_weights, dict):
                w_snap = pd.Series(last_decision_weights)
            else:
                w_snap = last_decision_weights
            w_snap = w_snap.reindex(ret_wide.columns).copy()
        w_snap = w_snap.fillna(0.0)
        w_snap = w_snap[w_snap.abs() > 0].sort_values(ascending=False)

        rows = []
        for ticker, weight in w_snap.items():
            t = normalize_ticker(ticker)
            last_px = float(close_wide.loc[snapshot_date, t]) if (t in close_wide.columns and snapshot_date in close_wide.index) else np.nan
            bdt = entry_date.get(t, np.nan)
            epx = entry_price.get(t, np.nan)
            hdays = _count_trading_days(close_wide.index, pd.to_datetime(bdt) if bdt is not np.nan else snapshot_date, snapshot_date) if (bdt is not np.nan) else 0
            ret_ = (last_px / epx - 1.0) if (np.isfinite(last_px) and np.isfinite(epx) and epx != 0) else 0.0
            rows.append({
                "snapshot_date": snapshot_date_str,
                "ticker": t,
                "name": _safe_name(name_map, t),
                "market": _safe_market(market_map, t),
                "weight": float(weight),
                "buy_date": pd.to_datetime(bdt).date().isoformat() if bdt is not np.nan else np.nan,
                "holding_days": int(hdays) if bdt is not np.nan else 0,
                "entry_price": float(epx) if np.isfinite(epx) else np.nan,
                "last_price": float(last_px) if np.isfinite(last_px) else np.nan,
                "return": float(ret_),
            })

        cash_w = float(max(0.0, 1.0 - float(w_snap.sum())))
        rows.append({
            "snapshot_date": snapshot_date_str,
            "ticker": "CASH",
            "name": "CASH",
            "market": "CASH",
            "weight": cash_w if cash_w > 0 else 0.0,
            "buy_date": np.nan,
            "holding_days": 0,
            "entry_price": 1.0,
            "last_price": 1.0,
            "return": 0.0,
        })
        snapshot_df = pd.DataFrame(rows)

    # --- summary (legacy schema) ---
    eq_series = equity_df["equity"]
    eq_ret = eq_series.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # Legacy parity: vol_daily uses sample std (ddof=1).
    avg_daily_ret = float(eq_ret.mean()) if len(eq_ret) else 0.0
    vol_daily = float(eq_ret.std(ddof=1)) if len(eq_ret) else 0.0
    sharpe = float((avg_daily_ret / vol_daily) * np.sqrt(252.0)) if vol_daily > 0 else 0.0

    # CAGR
    if len(eq_series) >= 2:
        total_days = int((equity_df.index[-1] - equity_df.index[0]).days)
        years = total_days / 365.25 if total_days > 0 else 0.0
        cagr = float((eq_series.iloc[-1] / eq_series.iloc[0]) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    else:
        cagr = 0.0

    # MDD
    peak = eq_series.cummax()
    dd = (eq_series / peak) - 1.0
    mdd = float(dd.min()) if len(dd) else 0.0

    # robust rebalance_count: compare on normalized Timestamps
    rb_count = int(len(set(pd.to_datetime(rebalance_dates)).intersection(set(dates))))

    summary_df = pd.DataFrame([{
        "strategy": getattr(strategy, "name", "NA"),
        "start": equity_df.index.min().date().isoformat() if len(equity_df) else "",
        "end": equity_df.index.max().date().isoformat() if len(equity_df) else "",
        "cagr": cagr,
        "sharpe": sharpe,
        "mdd": mdd,
        "avg_daily_ret": avg_daily_ret,
        "vol_daily": vol_daily,
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "rebalance_count": rb_count,
    }])

    holdings_df = pd.DataFrame(holdings_rows) if holdings_rows else pd.DataFrame(columns=["rebalance_date","ticker","weight"])
    selection_df = pd.DataFrame(selection_rows) if selection_rows else pd.DataFrame()

    equity_out = equity_df.reset_index()
    # Legacy files store date as YYYY-MM-DD strings.
    equity_out["date"] = pd.to_datetime(equity_out["date"]).dt.strftime("%Y-%m-%d")

    return BacktestResult(
        summary_df=summary_df,
        snapshot_df=snapshot_df,
        equity_df=equity_out,
        ledger_df=None,
        trades_df=None,
        trades_c_df=None,
        windows_df=None,
        holdings_df=holdings_df,
        meta={
            "snapshot_date": snapshot_date_str,
            # Optional diagnostic table (not part of legacy bundle unless caller saves it)
            "selection_df": selection_df,
        },
    )