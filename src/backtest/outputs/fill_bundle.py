# src/backtest/outputs/fill_bundle.py ver 2026-02-23_002
"""Populate missing legacy CSV tables from a refactor-engine BacktestResult.

P1-1 scope:
  - Given engine outputs (equity/summary/snapshot maybe/holdings), build the remaining
    legacy CSVs: ledger, trades, trades_C, perf_windows, and ensure market col / sorting.

This keeps the engine lean and makes output parity testable in isolation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Optional, Tuple, Any

import pandas as pd

# NOTE: This module sits on the boundary between refactor engine outputs and the
# legacy CSV schemas. Keep imports explicit to avoid NameError cascades.
from src.backtest.contracts import BacktestResult
from src.backtest.core.tickers import normalize_ticker_series
from src.backtest.schemas import attach_market_col, sort_snapshot_by_return, make_trades_c
from src.backtest.outputs.legacy_reports import (
    build_snapshot_last_portfolio,
    build_rebalance_ledger,
    build_trade_snapshot_history,
    build_perf_windows_report,
)
def _apply_trades_lookback(trades_df: pd.DataFrame, end_dt: pd.Timestamp, years: int) -> pd.DataFrame:
    if trades_df is None or trades_df.empty:
        return trades_df
    if years is None or int(years) <= 0:
        return trades_df
    if "exit_date" not in trades_df.columns:
        return trades_df
    out = trades_df.copy()
    out["exit_date"] = pd.to_datetime(out["exit_date"], errors="coerce")
    cutoff = end_dt - pd.DateOffset(years=int(years))
    # keep: recent closed + all open (exit_date NaT)
    return out[(out["exit_date"].isna()) | (out["exit_date"] >= cutoff)].copy()


def fill_legacy_outputs(
    result: BacktestResult,
    *,
    close_wide: pd.DataFrame,
    name_map: Dict[str, str],
    market_map: Optional[Dict[str, str]] = None,
    # --- strategy/config fields needed for legacy schema parity ---
    top_n: Optional[int] = None,
    good_regimes: Optional[str] = None,
    sma_window: Optional[int] = None,
    require_above_sma: Optional[bool] = None,
    fundamentals_view: Optional[str] = None,
    fundamentals_asof: Optional[bool] = None,
    market_gate: Optional[bool] = None,
    market_scope: str = "KOSPI",
    market_sma_window: int = 60,
    market_entry_mult: float = 1.02,
    market_exit_mult: float = 1.00,
    snapshot_date: Optional[pd.Timestamp] = None,
    trades_lookback_years: int = 6,
    windows_years: Tuple[int, ...] = (1, 2, 3, 5),
    qty_default: int = 1,
) -> BacktestResult:
    """Return a NEW BacktestResult with legacy tables filled in."""

    market_map = market_map or {}

    if result.holdings_df is None or result.holdings_df.empty:
        raise RuntimeError("fill_legacy_outputs requires holdings_df")

    # Work on a local copy and normalize for legacy semantics.
    # Legacy canonical meaning:
    #   - holdings_df.rebalance_date is the *decision* date (weekly anchor; holiday-shifted).
    #   - snapshot_date is an *as-of* date and must NOT create an extra rebalance decision row.
    holdings_df = result.holdings_df.copy()

    # Accept both schemas during refactor:
    #   - engine/legacy: rebalance_date
    #   - transitional:  date
    if "rebalance_date" not in holdings_df.columns:
        if "date" in holdings_df.columns:
            holdings_df = holdings_df.copy()
            holdings_df["rebalance_date"] = holdings_df["date"]
        else:
            raise ValueError("holdings_df must contain 'rebalance_date' (or 'date') column")

    # Keep a string column for CSV friendliness, but do NOT treat it as a rebalance driver.
    holdings_df["rebalance_date"] = pd.to_datetime(holdings_df["rebalance_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # ---------------------------------------------------------------------
    # 0) Enrich equity/summary/holdings to match legacy schemas
    # ---------------------------------------------------------------------

    def _legacy_market_series() -> Dict[str, pd.Series]:
        """Rebuild the legacy market gate diagnostics series (daily)."""
        dates = close_wide.index
        cols = list(close_wide.columns)

        mg = bool(market_gate) if market_gate is not None else False
        if not mg:
            return {
                "market_ok": pd.Series(1, index=dates, dtype=int),
                "market_price": pd.Series(float("nan"), index=dates, dtype=float),
                "market_sma": pd.Series(float("nan"), index=dates, dtype=float),
                "market_entry_th": pd.Series(float("nan"), index=dates, dtype=float),
                "market_exit_th": pd.Series(float("nan"), index=dates, dtype=float),
            }

        mm = market_map or {}
        scope = (market_scope or "KOSPI").upper()
        if scope == "KOSPI":
            # Keep parity with StrategyS2: treat values like "KOSPI200"/"KOSPI" as KOSPI scope (contains match).
            scope_cols = [t for t in cols if "KOSPI" in str(mm.get(str(t), "")).upper()]
        else:
            scope_cols = cols
        scope_cols = [t for t in scope_cols if t in close_wide.columns]
        if not scope_cols:
            scope_cols = cols

        mret = close_wide[scope_cols].pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)
        mprice = (1.0 + mret).cumprod()
        msma = mprice.rolling(int(market_sma_window), min_periods=int(market_sma_window)).mean()

        entry_mult = float(market_entry_mult)
        exit_mult = float(market_exit_mult)
        if exit_mult > entry_mult:
            exit_mult, entry_mult = entry_mult, exit_mult

        ok = pd.Series(False, index=dates, dtype=bool)
        state = False
        for dt_ in dates:
            s = msma.loc[dt_]
            p = mprice.loc[dt_]
            if pd.isna(s):
                ok.loc[dt_] = False
                continue
            if not state:
                if p > (s * entry_mult):
                    state = True
            else:
                if p < (s * exit_mult):
                    state = False
            ok.loc[dt_] = bool(state)

        entry_th = (msma * entry_mult).astype(float)
        exit_th = (msma * exit_mult).astype(float)

        return {
            "market_ok": ok.astype(int),
            "market_price": mprice.astype(float),
            "market_sma": msma.astype(float),
            "market_entry_th": entry_th.astype(float),
            "market_exit_th": exit_th.astype(float),
        }

    mkt = _legacy_market_series()

    # Equity: add legacy diagnostic columns (market gate + exposure)
    eq_df = (result.equity_df.copy() if result.equity_df is not None else pd.DataFrame())
    if not eq_df.empty and "date" in eq_df.columns:
        dates = pd.to_datetime(eq_df["date"], errors="coerce")
        # market gate daily diagnostics
        eq_df["market_ok"] = mkt["market_ok"].reindex(dates).fillna(0).astype(int).values
        eq_df["market_price"] = mkt["market_price"].reindex(dates).astype(float).values
        eq_df["market_sma"] = mkt["market_sma"].reindex(dates).astype(float).values
        eq_df["market_entry_th"] = mkt["market_entry_th"].reindex(dates).astype(float).values
        eq_df["market_exit_th"] = mkt["market_exit_th"].reindex(dates).astype(float).values

        # rebalance-level exposure / holdings (forward-filled to daily)
        try:
            tmp_h = holdings_df.copy()
            tmp_h["rebalance_date"] = pd.to_datetime(tmp_h.get("rebalance_date"), errors="coerce")
            tmp_h["ticker"] = tmp_h["ticker"].astype(str)

            def _is_risk_ticker(x: Any) -> bool:
                s = str(x).strip().upper()
                return (s != "") and (s != "CASH") and (s.lower() not in ("nan", "none"))

            tmp_h["is_risk_ticker"] = tmp_h["ticker"].apply(_is_risk_ticker)
            rb_grp = tmp_h.groupby("rebalance_date", sort=True)
            _rb_func = lambda g: pd.Series({
                "n_holdings": int(g.loc[g["is_risk_ticker"], "ticker"].shape[0]),
                "gross_exposure": float(pd.to_numeric(g.loc[g["is_risk_ticker"], "weight"], errors="coerce").fillna(0.0).sum()),
            })
            try:
                rb_stats = rb_grp.apply(_rb_func, include_groups=False)
            except TypeError:
                rb_stats = rb_grp.apply(_rb_func)

            rb_stats["cash_weight"] = 1.0 - rb_stats["gross_exposure"].astype(float)
            rb_stats["risk_on_portfolio"] = (rb_stats["gross_exposure"].astype(float) > 0).astype(int)
            rb_stats = rb_stats.reindex(dates, method="ffill")
            rb_stats = rb_stats.fillna({"n_holdings": 0, "gross_exposure": 0.0, "cash_weight": 1.0, "risk_on_portfolio": 0})

            eq_df["n_holdings"] = rb_stats["n_holdings"].astype(int).values
            eq_df["gross_exposure"] = rb_stats["gross_exposure"].astype(float).values
            eq_df["cash_weight"] = rb_stats["cash_weight"].astype(float).values
            eq_df["risk_on_portfolio"] = rb_stats["risk_on_portfolio"].astype(int).values
        except Exception:
            # reporting-only; do not break refactor path
            pass

    # Summary: add legacy config fields (keep existing perf metrics)
    sum_df = (result.summary_df.copy() if result.summary_df is not None else pd.DataFrame())
    if not sum_df.empty:
        if top_n is not None:
            sum_df["top_n"] = int(top_n)
        if good_regimes is not None:
            sum_df["good_regimes"] = str(good_regimes)
        if sma_window is not None:
            sum_df["sma_window"] = int(sma_window)
        if require_above_sma is not None:
            sum_df["require_above_sma"] = bool(require_above_sma)
        if fundamentals_view is not None:
            sum_df["fundamentals_view"] = str(fundamentals_view)
        if fundamentals_asof is not None:
            sum_df["fundamentals_asof"] = bool(fundamentals_asof)
        if market_gate is not None:
            sum_df["market_gate"] = bool(market_gate)
        sum_df["market_sma_window"] = int(market_sma_window)
        # legacy uses market_sma_mult name, even though it's effectively entry_mult
        sum_df["market_sma_mult"] = float(market_entry_mult)

    # Holdings: upcast to legacy holdings schema (create columns even if NaN)
    # Legacy report builders require 'rebalance_date'. Refactor engine may emit 'date'.
    holdings_df_norm = holdings_df.copy()
    if "rebalance_date" not in holdings_df_norm.columns:
        if "date" in holdings_df_norm.columns:
            holdings_df_norm["rebalance_date"] = holdings_df_norm["date"]
        else:
            raise ValueError("holdings_df must contain 'rebalance_date' or 'date' column")

    # Canonicalize types
    holdings_df_norm["rebalance_date"] = pd.to_datetime(holdings_df_norm["rebalance_date"], errors="coerce").dt.normalize()
    holdings_df_norm["ticker"] = normalize_ticker_series(holdings_df_norm["ticker"])

    hold_df = holdings_df.copy()
    hold_df["rebalance_date"] = pd.to_datetime(hold_df.get("rebalance_date"), errors="coerce").dt.strftime("%Y-%m-%d")
    hold_df["ticker"] = normalize_ticker_series(hold_df["ticker"])

    # attach name/market/price
    def _px(row) -> float:
        try:
            t = str(row["ticker"]).strip()
            if t.upper() == "CASH":
                return 1.0
            dt = pd.to_datetime(row["rebalance_date"])
            if dt in close_wide.index and t in close_wide.columns:
                return float(close_wide.loc[dt, t])
        except Exception:
            pass
        return float("nan")

    hold_df["name"] = hold_df["ticker"].map(lambda t: str(name_map.get(str(t), "")))
    hold_df["market"] = hold_df["ticker"].map(lambda t: str((market_map or {}).get(str(t), "")))
    hold_df["price"] = hold_df.apply(_px, axis=1)

    # add legacy decision/diagnostic columns (mostly NA, but must exist)
    na_cols = {
        "risk_on": float("nan"),
        "spread": float("nan"),
        "n_assets": float("nan"),
        "regime": float("nan"),
        "regime_score": float("nan"),
        "growth_score": float("nan"),
        "score_rank": float("nan"),
    }
    for c, v in na_cols.items():
        if c not in hold_df.columns:
            hold_df[c] = v

    # config columns (repeat per row)
    if top_n is not None:
        hold_df["top_n"] = int(top_n)
    if good_regimes is not None:
        hold_df["good_regimes"] = str(good_regimes)
    if sma_window is not None:
        hold_df["sma_window"] = int(sma_window)
    if require_above_sma is not None:
        hold_df["require_above_sma"] = bool(require_above_sma)
    if market_gate is not None:
        hold_df["market_gate"] = bool(market_gate)

    # market diagnostics on rebalance dates
    try:
        rb_dt = pd.to_datetime(hold_df["rebalance_date"], errors="coerce")
        hold_df["market_ok"] = mkt["market_ok"].reindex(rb_dt).fillna(0).astype(int).values
        hold_df["market_price"] = mkt["market_price"].reindex(rb_dt).astype(float).values
        hold_df["market_sma"] = mkt["market_sma"].reindex(rb_dt).astype(float).values
        hold_df["market_sma_window"] = int(market_sma_window)
        hold_df["market_sma_mult"] = float(market_entry_mult)
        hold_df["market_entry_mult"] = float(market_entry_mult)
        hold_df["market_exit_mult"] = float(market_exit_mult)
    except Exception:
        pass

    # ---------------------------------------------------------------------
    # 1) Snapshot/Ledger/Trades/Windows (existing behavior)
    # ---------------------------------------------------------------------

    # Snapshot (rebuild to guarantee schema)
    snap_df = build_snapshot_last_portfolio(
        holdings_df=holdings_df_norm,
        close_wide=close_wide,
        name_map=name_map,
        snapshot_date=snapshot_date,
        cash_label="CASH",
    )
    snap_df = attach_market_col(snap_df, market_map, ticker_col="ticker", out_col="market")
    snap_df = sort_snapshot_by_return(snap_df, return_col="return")

    # Ledger
    ledger_df = build_rebalance_ledger(
        holdings_df=holdings_df_norm,
        close_wide=close_wide,
        name_map=name_map,
        market_map=market_map,
        qty_default=int(qty_default),
        ticker_col="ticker",
    )

    # Trades (snapshot)
    end_dt = pd.to_datetime(eq_df["date"]).max() if (eq_df is not None and not eq_df.empty and "date" in eq_df.columns) else close_wide.index.max()
    trades_df = build_trade_snapshot_history(holdings_df_norm, close_wide, names_map=name_map, end_date=end_dt.strftime("%Y-%m-%d"))
    trades_df = _apply_trades_lookback(trades_df, end_dt, int(trades_lookback_years))
    trades_df = attach_market_col(trades_df, market_map, ticker_col="ticker", out_col="market") if (trades_df is not None and not trades_df.empty) else trades_df

    # Trades C (round-trip)
    trades_c_df = make_trades_c(trades_df) if (trades_df is not None and not trades_df.empty) else pd.DataFrame()
    trades_c_df = attach_market_col(trades_c_df, market_map, ticker_col="ticker", out_col="market") if (trades_c_df is not None and not trades_c_df.empty) else trades_c_df

    # Perf windows
    windows_df = build_perf_windows_report(eq_df, windows_years=windows_years)

    return replace(
        result,
        summary_df=sum_df,
        equity_df=eq_df,
        holdings_df=hold_df,
        snapshot_df=snap_df,
        ledger_df=ledger_df,
        trades_df=trades_df,
        trades_c_df=trades_c_df,
        windows_df=windows_df,
    )
