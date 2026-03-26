# outputs/legacy_reports.py ver 2026-02-23_001
"""Legacy-compatible report builders.

Purpose (P1-1):
  - Keep "report/output" logic (snapshot, trades, ledger, perf windows) OUT of the backtest engine.
  - Reuse the *exact* legacy calculations/columns so both legacy runner and refactor engine can
    produce identical CSV outputs.

Inputs:
  - holdings_df: columns [rebalance_date, ticker, weight] (+ optional others)
  - close_wide:  wide close price (index=date, columns=ticker)
  - equity_df:   columns [date, equity, port_ret] (+ optional market_ok)
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.backtest.core.tickers import normalize_ticker, normalize_ticker_series, normalize_columns_to_tickers


def sort_snapshot_by_return(df: pd.DataFrame, return_col: str = "return") -> pd.DataFrame:
    """Sort snapshot rows by per-ticker return descending while preserving column order.
    - Keeps CASH row (name == 'CASH' or ticker == 'CASH') at the bottom.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    cols = list(df.columns)
    work = df.copy()

    name_upper = work["name"].astype(str).str.upper() if "name" in work.columns else pd.Series([""] * len(work))
    ticker_upper = work["ticker"].astype(str).str.upper() if "ticker" in work.columns else pd.Series([""] * len(work))
    is_cash = (name_upper == "CASH") | (ticker_upper == "CASH")

    if return_col in work.columns:
        r = work[return_col]
        r_num = pd.to_numeric(r.astype(str).str.replace("%", "", regex=False), errors="coerce")
        work["_return_num__"] = r_num
    else:
        work["_return_num__"] = float("nan")

    non_cash = work.loc[~is_cash].sort_values(by="_return_num__", ascending=False, kind="mergesort")
    cash_part = work.loc[is_cash]
    out = pd.concat([non_cash, cash_part], axis=0)
    return out[cols]


def attach_market_col(
    df: pd.DataFrame,
    market_map: Dict[str, str],
    ticker_col: str = "ticker",
    out_col: str = "market",
) -> pd.DataFrame:
    """Attach market column (KOSPI/KOSDAQ) next to name (if exists) or next to ticker."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    market_map = market_map or {}
    out = df.copy()

    if out_col not in out.columns:
        out[out_col] = out[ticker_col].astype(str).map(lambda t: str(market_map.get(str(t), "")).strip())
    else:
        # fill blanks only
        blank = out[out_col].astype(str).str.len() == 0
        out.loc[blank, out_col] = out.loc[blank, ticker_col].astype(str).map(lambda t: str(market_map.get(str(t), "")).strip())

    cols = list(out.columns)
    if "name" in cols and out_col in cols and ticker_col in cols:
        cols.remove(out_col)
        name_idx = cols.index("name")
        cols.insert(name_idx + 1, out_col)
        out = out[cols]
    elif out_col in cols and ticker_col in cols:
        cols.remove(out_col)
        t_idx = cols.index(ticker_col)
        cols.insert(t_idx + 1, out_col)
        out = out[cols]
    return out


def build_snapshot_last_portfolio(
    *,
    holdings_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    name_map: Dict[str, str],
    snapshot_date: Optional[pd.Timestamp] = None,
    cash_label: str = "CASH",
) -> pd.DataFrame:
    """Build legacy-style snapshot (last portfolio as-of snapshot_date).

    Key semantics (legacy):
    - holdings_df.rebalance_date is the *decision* date (weekly anchor, holiday-shifted).
    - actual execution (buy/sell) is on the next available trading day.
    - snapshot_date is an *as-of* date (typically end date), not necessarily a rebalance date.
    """

    if holdings_df is None or holdings_df.empty:
        raise RuntimeError("holdings_df is empty; cannot build snapshot.")

    if "rebalance_date" not in holdings_df.columns:
        raise ValueError("holdings_df must contain 'rebalance_date' column")

    # --- Normalize dates (avoid time-component mismatches) --------------------
    h = holdings_df.copy()
    # Normalize ticker labels (project-wide invariant)
    if "ticker" in h.columns:
        h["ticker"] = normalize_ticker_series(h["ticker"], cash_label=cash_label)

    h["rebalance_date"] = pd.to_datetime(h["rebalance_date"]).dt.normalize()

    # Trading calendar index (must be DatetimeIndex)
    close_wide = close_wide.copy()
    if not isinstance(close_wide.index, pd.DatetimeIndex):
        close_wide.index = pd.to_datetime(close_wide.index)
    # DatetimeIndex has .normalize(); .dt is for Series
    close_wide.index = close_wide.index.normalize()
    trading_idx = close_wide.index

    # Normalize price columns to canonical ticker strings
    close_wide.columns = normalize_columns_to_tickers(close_wide.columns, cash_label=cash_label)
    # If normalization introduces duplicate columns, deterministically coalesce
    if close_wide.columns.has_duplicates:
        close_wide = close_wide.groupby(level=0, axis=1).first()

    # As-of date
    if snapshot_date is None:
        asof = trading_idx.max()
    else:
        asof = pd.to_datetime(snapshot_date).normalize()
        # if asof is not a trading day, roll back to last available trading day
        if asof not in trading_idx:
            pos = trading_idx.searchsorted(asof, side="right") - 1
            if pos < 0:
                raise RuntimeError(f"snapshot_date {asof.date()} is before available price history")
            asof = trading_idx[pos]

    # Latest decision date <= asof
    all_reb = pd.Index(sorted(h["rebalance_date"].unique()))
    pos = all_reb.searchsorted(asof, side="right") - 1
    if pos < 0:
        # no rebalance yet -> all cash
        rows = [{
            "snapshot_date": asof.strftime("%Y-%m-%d"),
            "ticker": cash_label,
            "name": cash_label,
            "market": cash_label,
            "weight": 1.0,
            "buy_date": "",
            "holding_days": 0,
            "entry_price": 1.0,
            "last_price": 1.0,
            "return": 0.0,
        }]
        return pd.DataFrame(rows)

    decision_dt = pd.to_datetime(all_reb[pos]).normalize()

    # Execution date = next trading day after decision_dt (if possible)
    def _next_trading_day(dt: pd.Timestamp) -> pd.Timestamp:
        dt = pd.to_datetime(dt).normalize()
        i = trading_idx.searchsorted(dt)
        # if decision is a trading day, move to next trading day; else first trading day after it
        if i < len(trading_idx) and trading_idx[i] == dt:
            i += 1
        if i >= len(trading_idx):
            return dt  # fallback (should not happen for typical end dates)
        return trading_idx[i]

    exec_dt = _next_trading_day(decision_dt)
    # But if exec_dt is after asof, clamp (edge case at dataset end)
    if exec_dt > asof:
        exec_dt = asof

    # Holdings at decision date
    h_last = h[h["rebalance_date"] == decision_dt].copy()
    # Keep only investable tickers (exclude CASH / blanks)
    held = h_last[
        h_last["ticker"].astype(str).str.len().gt(0)
        & (h_last["ticker"].astype(str) != cash_label)
    ].copy()

    # If nothing to hold, snapshot is cash
    if held.empty:
        rows = [{
            "snapshot_date": asof.strftime("%Y-%m-%d"),
            "ticker": cash_label,
            "name": cash_label,
            "market": cash_label,
            "weight": 1.0,
            "buy_date": "",
            "holding_days": 0,
            "entry_price": 1.0,
            "last_price": 1.0,
            "return": 0.0,
        }]
        return pd.DataFrame(rows)

    # Find entry decision date for each ticker as the earliest date in the current continuous holding streak.
    # (Walk backward across rebalance dates while ticker remains present.)
    reb_dates = list(pd.to_datetime(all_reb).normalize())
    reb_pos = {d: i for i, d in enumerate(reb_dates)}
    cur_i = reb_pos[decision_dt]

    rows = []
    total_w = 0.0

    for _, row in held.iterrows():
        t = normalize_ticker(row["ticker"], cash_label=cash_label)
        w = float(row.get("weight", 0.0) or 0.0)
        total_w += w

        # Walk back to find streak start
        entry_i = cur_i
        while entry_i - 1 >= 0:
            prev_dt = reb_dates[entry_i - 1]
            prev_slice = h[h["rebalance_date"] == prev_dt]
            if (prev_slice["ticker"].astype(str) == t).any():
                entry_i -= 1
            else:
                break
        entry_decision_dt = reb_dates[entry_i]
        entry_exec_dt = _next_trading_day(entry_decision_dt)
        if entry_exec_dt > asof:
            entry_exec_dt = asof

        # Prices
        try:
            entry_px = float(close_wide.loc[entry_exec_dt, t])
            last_px = float(close_wide.loc[asof, t])
        except Exception:
            # if price missing for any reason, skip the asset (keeps legacy robustness)
            continue

        # Trading-day holding length (exclusive of buy day like legacy UIs usually do)
        try:
            hd = int(trading_idx.get_indexer([asof])[0] - trading_idx.get_indexer([entry_exec_dt])[0])
            hd = max(hd, 0)
        except Exception:
            hd = max(int((asof - entry_exec_dt).days), 0)

        ret = (last_px / entry_px - 1.0) if entry_px else 0.0

        rows.append({
            "snapshot_date": asof.strftime("%Y-%m-%d"),
            "ticker": t,
            "name": name_map.get(t, row.get("name", t)),
            "market": row.get("market", ""),
            "weight": w,
            "buy_date": entry_exec_dt.strftime("%Y-%m-%d"),
            "holding_days": hd,
            "entry_price": entry_px,
            "last_price": last_px,
            "return": ret,
        })

    # Cash residual
    cash_w = max(0.0, 1.0 - total_w)
    rows.append({
        "snapshot_date": asof.strftime("%Y-%m-%d"),
        "ticker": cash_label,
        "name": cash_label,
        "market": cash_label,
        "weight": cash_w,
        "buy_date": "",
        "holding_days": 0,
        "entry_price": 1.0,
        "last_price": 1.0,
        "return": 0.0,
    })

    # Sort: non-cash first, then cash
    df = pd.DataFrame(rows)
    df["_is_cash"] = (df["ticker"] == cash_label).astype(int)
    df = df.sort_values(["_is_cash", "weight", "ticker"], ascending=[True, False, True]).drop(columns=["_is_cash"])
    return df

def build_trade_snapshot_history(
    holdings_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    names_map: Dict[str, str],
    end_date: str,
    *,
    cash_label: str = "CASH",
) -> pd.DataFrame:
    """Build per-ticker holding-period return rows for BOTH closed and open positions."""
    if holdings_df is None or len(holdings_df) == 0:
        return pd.DataFrame()

    h = holdings_df.copy()
    # Normalize ticker labels (project-wide invariant)
    if "ticker" in h.columns:
        h["ticker"] = normalize_ticker_series(h["ticker"], cash_label=cash_label)

    # Normalize price panel (dates + tickers)
    close_wide = close_wide.copy()
    if not isinstance(close_wide.index, pd.DatetimeIndex):
        close_wide.index = pd.to_datetime(close_wide.index)
    close_wide.index = pd.to_datetime(close_wide.index).normalize()
    close_wide.columns = normalize_columns_to_tickers(close_wide.columns, cash_label=cash_label)
    if close_wide.columns.has_duplicates:
        close_wide = close_wide.groupby(level=0, axis=1).first()

    h = h[h["ticker"].notna()].copy()
    if len(h) == 0:
        return pd.DataFrame()

    h["rebalance_date"] = pd.to_datetime(h["rebalance_date"], errors="coerce").dt.normalize()
    h["ticker"] = h["ticker"].astype(str)

    by_date = {}
    for d, g in h.groupby("rebalance_date", sort=True):
        w = {t: float(wt) for t, wt in zip(g["ticker"], g["weight"]) if pd.notna(t) and float(wt) > 0 and str(t).upper() != "CASH"}
        by_date[pd.Timestamp(d).normalize()] = w

    rb_dates = sorted(by_date.keys())
    if len(rb_dates) == 0:
        return pd.DataFrame()

    end_ts = pd.to_datetime(end_date).normalize()
    if end_ts not in close_wide.index:
        end_ts = close_wide.index.max()

    def _px(ts: pd.Timestamp, t: str) -> float:
        try:
            v = close_wide.at[ts, t]
            return float(v) if pd.notna(v) else np.nan
        except Exception:
            return np.nan

    def _next_trading_day(dt_: pd.Timestamp) -> pd.Timestamp:
        dt_ = pd.to_datetime(dt_).normalize()
        i = close_wide.index.searchsorted(dt_, side="left")
        if i < len(close_wide.index) and close_wide.index[i] == dt_:
            i += 1
        if i >= len(close_wide.index):
            return dt_
        return pd.Timestamp(close_wide.index[i]).normalize()

    open_pos = {}
    trades = []
    trade_id = 0

    prev_w = {}
    for d in rb_dates:
        w = by_date.get(d, {})
        prev_set = set(prev_w.keys())
        curr_set = set(w.keys())

        for t in sorted(prev_set - curr_set):
            entry = open_pos.get(t)
            if entry is None:
                continue
            exec_d = _next_trading_day(d)
            exit_price = _px(exec_d, t)
            trade_id += 1
            trades.append(
                {
                    "trade_id": trade_id,
                    "ticker": t,
                    "name": names_map.get(t, ""),
                    "entry_date": entry["entry_date"].strftime("%Y-%m-%d"),
                    "entry_price": entry["entry_price"],
                    "exit_date": exec_d.strftime("%Y-%m-%d"),
                    "exit_price": exit_price,
                    "holding_days": int((exec_d - entry["entry_date"]).days),
                    "return": (exit_price / entry["entry_price"] - 1.0) if (pd.notna(exit_price) and entry["entry_price"] > 0) else np.nan,
                    "status": "CLOSED",
                }
            )
            open_pos.pop(t, None)

        for t in sorted(curr_set - prev_set):
            exec_d = _next_trading_day(d)
            entry_price = _px(exec_d, t)
            open_pos[t] = {"entry_date": exec_d, "entry_price": entry_price}

        prev_w = w

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

    if not trades:
        return pd.DataFrame()

    return pd.DataFrame(trades)


def build_rebalance_ledger(
    *,
    holdings_df: pd.DataFrame,
    close_wide: pd.DataFrame,
    name_map: Dict[str, str],
    market_map: Dict[str, str],
    qty_default: int = 1,
    ticker_col: str = "ticker",
) -> pd.DataFrame:
    """Build rebalance-event ledger (BUY/SELL by rebalance_date; execution on trade_date=T+1)."""
    if holdings_df is None or holdings_df.empty:
        return pd.DataFrame()

    # Legacy CSV schema uses 'rebalance_date'.
    # Refactor-engine holdings sometimes emit 'date' instead.
    # Accept both to keep reporting robust during refactor.
    if "rebalance_date" not in holdings_df.columns:
        if "date" in holdings_df.columns:
            holdings_df = holdings_df.copy()
            holdings_df["rebalance_date"] = holdings_df["date"]
        else:
            raise ValueError("holdings_df must contain 'rebalance_date' (or 'date') column")

    tmp = holdings_df.copy()
    tmp["rebalance_date"] = pd.to_datetime(tmp["rebalance_date"], errors="coerce").dt.normalize()

    close_wide = close_wide.copy()
    if not isinstance(close_wide.index, pd.DatetimeIndex):
        close_wide.index = pd.to_datetime(close_wide.index)
    close_wide.index = pd.to_datetime(close_wide.index).normalize()
    close_wide.columns = normalize_columns_to_tickers(close_wide.columns, cash_label="CASH")
    if close_wide.columns.has_duplicates:
        close_wide = close_wide.groupby(level=0, axis=1).first()

    if ticker_col not in tmp.columns:
        ticker_col = "ticker"

    tmp[ticker_col] = tmp[ticker_col].astype(str)
    tmp.loc[tmp[ticker_col].str.lower().isin(["nan", "none", ""]), ticker_col] = np.nan

    dates = sorted(tmp["rebalance_date"].dropna().unique())
    holdings_by_date = {}
    for d in dates:
        s = tmp.loc[tmp["rebalance_date"] == d, ticker_col].dropna().unique().tolist()
        s = [t for t in s if str(t).upper() != "CASH"]
        holdings_by_date[pd.Timestamp(d).normalize()] = set(s)

    def _px(dt: pd.Timestamp, t: str):
        if str(t).upper() == "CASH":
            return 1.0
        try:
            return float(close_wide.loc[dt, t])
        except Exception:
            return np.nan

    def _next_trading_day(dt_: pd.Timestamp) -> pd.Timestamp:
        dt_ = pd.to_datetime(dt_).normalize()
        i = close_wide.index.searchsorted(dt_, side="left")
        if i < len(close_wide.index) and close_wide.index[i] == dt_:
            i += 1
        if i >= len(close_wide.index):
            return dt_
        return pd.Timestamp(close_wide.index[i]).normalize()

    lots = {}
    rows = []
    prev_hold = set()

    for dt in dates:
        dt = pd.Timestamp(dt).normalize()  # decision date (rebalance_date)
        exec_dt = _next_trading_day(dt)    # execution date (trade_date)
        cur_hold = holdings_by_date.get(dt, set())

        buys = sorted(list(cur_hold - prev_hold))
        sells = sorted(list(prev_hold - cur_hold))

        for t in buys:
            px = _px(exec_dt, t)
            qty = qty_default
            amt = (px * qty) if pd.notnull(px) else np.nan
            lots.setdefault(t, []).append({"buy_date": exec_dt, "buy_price": px, "qty": qty})

            rows.append({
                "rebalance_date": dt.strftime("%Y-%m-%d"),
                "trade_date": exec_dt.strftime("%Y-%m-%d"),
                "action": "BUY",
                "ticker": t,
                "name": name_map.get(t, ""),
                "market": str(market_map.get(t, "")).strip().upper() if market_map else "",
                "qty": qty,
                "price": px,
                "amount": amt,
                "first_buy_date": exec_dt.strftime("%Y-%m-%d"),
                "first_buy_price": px,
            })

        for t in sells:
            px = _px(exec_dt, t)
            qty = qty_default
            amt = (px * qty) if pd.notnull(px) else np.nan

            lot_list = lots.get(t, [])
            if lot_list:
                first = lot_list[0]
                first_buy_date = first.get("buy_date", np.nan)
                first_buy_price = first.get("buy_price", np.nan)
                lot_list.pop(0)
                lots[t] = lot_list
            else:
                first_buy_date = np.nan
                first_buy_price = np.nan

            rows.append({
                "rebalance_date": dt.strftime("%Y-%m-%d"),
                "trade_date": exec_dt.strftime("%Y-%m-%d"),
                "action": "SELL",
                "ticker": t,
                "name": name_map.get(t, ""),
                "market": str(market_map.get(t, "")).strip().upper() if market_map else "",
                "qty": qty,
                "price": px,
                "amount": amt,
                "first_buy_date": first_buy_date.strftime("%Y-%m-%d") if isinstance(first_buy_date, pd.Timestamp) else ("" if pd.isna(first_buy_date) else str(first_buy_date)),
                "first_buy_price": first_buy_price,
            })

        prev_hold = cur_hold

    return pd.DataFrame(rows)


def _perf_from_equity_and_ret(dates: pd.DatetimeIndex, equity: pd.Series, pret: pd.Series) -> Dict[str, float]:
    eq = equity.astype(float)
    r = pret.astype(float)
    total_days = int((dates[-1] - dates[0]).days)
    years = total_days / 365.25 if total_days > 0 else 0.0
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    peak = eq.cummax()
    dd = (eq / peak) - 1.0
    mdd = float(dd.min()) if len(dd) else 0.0

    avg_daily_ret = float(r.mean()) if len(r) else 0.0
    vol_daily = float(r.std(ddof=0)) if len(r) else 0.0
    sharpe = float((avg_daily_ret / vol_daily) * np.sqrt(252.0)) if vol_daily > 0 else 0.0

    return {
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "avg_daily_ret": avg_daily_ret,
        "vol_daily": vol_daily,
    }


def build_perf_windows_report(equity_df: pd.DataFrame, windows_years=(1, 2, 3, 5)) -> pd.DataFrame:
    if equity_df is None or len(equity_df) == 0:
        return pd.DataFrame()

    df = equity_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if "market_ok" not in df.columns:
        df["market_ok"] = 1
    if "port_ret" not in df.columns:
        # fallback to equity pct_change
        df["port_ret"] = df["equity"].astype(float).pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)

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

            m_full = _perf_from_equity_and_ret(d2, eq2 / eq2.iloc[0], r2)
            out.append({"window": f"{y}y", "segment": seg_name, "mode": "fullcurve", **m_full, "days": len(s), "start": d2[0].strftime("%Y-%m-%d"), "end": d2[-1].strftime("%Y-%m-%d")})

            chain_eq = (1.0 + r2.fillna(0.0)).cumprod()
            m_chain = _perf_from_equity_and_ret(d2, chain_eq, r2)
            out.append({"window": f"{y}y", "segment": seg_name, "mode": "chain", **m_chain, "days": len(s), "start": d2[0].strftime("%Y-%m-%d"), "end": d2[-1].strftime("%Y-%m-%d")})

    return pd.DataFrame(out)
