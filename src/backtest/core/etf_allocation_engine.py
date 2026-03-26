from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.backtest.configs.etf_allocation_config import EtfAllocationConfig
from src.backtest.contracts import BacktestResult
from src.backtest.core.data import next_trading_day
from src.backtest.portfolio.etf_regime_allocator import allocate_group_representatives, resolve_mode_for_date


def _calc_turnover(prev_w: pd.Series, new_w: pd.Series) -> float:
    prev_w = prev_w.fillna(0.0)
    new_w = new_w.fillna(0.0)
    return float(new_w.sub(prev_w, fill_value=0.0).abs().sum() / 2.0)


def _perf_metrics(equity_df: pd.DataFrame) -> dict[str, float]:
    if equity_df is None or equity_df.empty:
        return {
            "cagr": float("nan"),
            "mdd": float("nan"),
            "sharpe": float("nan"),
            "avg_daily_ret": float("nan"),
            "vol_daily": float("nan"),
        }
    rets = pd.to_numeric(equity_df["port_ret"], errors="coerce").fillna(0.0)
    eq = pd.to_numeric(equity_df["equity"], errors="coerce").dropna()
    n = int(len(eq))
    years = max(n / 252.0, 1.0 / 252.0)
    cagr = float(eq.iloc[-1] ** (1.0 / years) - 1.0) if n > 0 and eq.iloc[-1] > 0 else float("nan")
    dd = eq / eq.cummax() - 1.0
    mdd = float(dd.min()) if len(dd) else float("nan")
    vol = float(rets.std(ddof=0))
    sharpe = float((rets.mean() / vol) * np.sqrt(252.0)) if vol > 0 else float("nan")
    return {
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": sharpe,
        "avg_daily_ret": float(rets.mean()),
        "vol_daily": vol,
    }


def _window_metric(equity_df: pd.DataFrame, years: int) -> dict[str, float]:
    if equity_df is None or equity_df.empty:
        return {"cagr": float("nan"), "mdd": float("nan"), "sharpe": float("nan")}
    window = equity_df.tail(252 * years).copy()
    return _perf_metrics(window)


@dataclass
class _PendingTrade:
    decision_date: pd.Timestamp
    exec_date: pd.Timestamp
    mode: str
    regime_value: float | None
    new_weights: pd.Series
    cost: float
    turnover: float
    selection_df: pd.DataFrame


def run_etf_allocation_backtest(
    *,
    close_wide: pd.DataFrame,
    ret_wide: pd.DataFrame,
    core_df: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    regime_mode_df: pd.DataFrame,
    cfg: EtfAllocationConfig,
    name_map: Optional[Dict[str, str]] = None,
    market_map: Optional[Dict[str, str]] = None,
) -> BacktestResult:
    if close_wide is None or close_wide.empty:
        raise RuntimeError("close_wide is empty")
    if ret_wide is None or ret_wide.empty:
        raise RuntimeError("ret_wide is empty")
    if core_df is None or core_df.empty:
        raise RuntimeError("core_df is empty")
    if not rebalance_dates:
        raise RuntimeError("rebalance_dates is empty")

    name_map = name_map or {}
    market_map = market_map or {}
    dates = pd.DatetimeIndex(pd.to_datetime(close_wide.index)).sort_values()
    rb_set = set(pd.to_datetime(rebalance_dates))
    price_cols = [str(c).zfill(6) for c in close_wide.columns]

    w = pd.Series(0.0, index=price_cols, dtype=float)
    eq = 1.0
    pending: Optional[_PendingTrade] = None
    last_mode = cfg.regime.fallback_mode
    last_regime_value: float | None = None

    equity_rows: list[dict[str, object]] = []
    weights_rows: list[dict[str, object]] = []
    trades_rows: list[dict[str, object]] = []
    turnover_total = 0.0

    close_wide = close_wide.copy()
    close_wide.columns = price_cols
    ret_wide = ret_wide.copy()
    ret_wide.columns = price_cols

    for dt in dates:
        eq_prev = eq
        day_ret = pd.to_numeric(ret_wide.loc[dt], errors="coerce").fillna(0.0)
        eq *= 1.0 + float((day_ret * w).sum())

        if pending is not None and pd.Timestamp(dt) == pending.exec_date:
            eq *= 1.0 - pending.cost
            prev_w = w.copy()
            w = pending.new_weights.copy()
            turnover_total += float(pending.turnover)

            union = sorted(set(prev_w.index).union(set(w.index)))
            for ticker in union:
                prev_weight = float(prev_w.get(ticker, 0.0))
                new_weight = float(w.get(ticker, 0.0))
                delta = new_weight - prev_weight
                if abs(delta) < 1e-12:
                    continue
                side = "BUY" if delta > 0 else "SELL"
                exec_price = float(close_wide.loc[dt, ticker]) if ticker in close_wide.columns else float("nan")
                trades_rows.append(
                    {
                        "rebalance_date": pending.decision_date.strftime("%Y-%m-%d"),
                        "trade_date": pending.exec_date.strftime("%Y-%m-%d"),
                        "mode": pending.mode,
                        "regime_value": pending.regime_value,
                        "side": side,
                        "ticker": ticker,
                        "name": name_map.get(ticker, ticker),
                        "market": market_map.get(ticker, "ETF"),
                        "prev_weight": prev_weight,
                        "new_weight": new_weight,
                        "delta_weight": delta,
                        "exec_price": exec_price,
                        "turnover_component": abs(delta) / 2.0,
                    }
                )
            pending = None

        if pd.Timestamp(dt) in rb_set:
            trade_dt = next_trading_day(dates, dt)
            if trade_dt is None:
                trade_dt = pd.Timestamp(dt)

            last_mode, last_regime_value = resolve_mode_for_date(regime_mode_df, dt, cfg.regime.fallback_mode)
            available_tickers = [
                t for t in price_cols if t in close_wide.columns and pd.notna(close_wide.loc[trade_dt, t])
            ]
            selection = allocate_group_representatives(
                core_df=core_df,
                mode=last_mode,
                cfg=cfg,
                available_tickers=available_tickers,
            )

            target = pd.Series(0.0, index=price_cols, dtype=float)
            for ticker, target_weight in selection.weights.items():
                if ticker == "CASH":
                    continue
                if ticker in target.index:
                    target.loc[ticker] = float(target_weight)
            turnover = _calc_turnover(w, target)
            total_cost = turnover * ((cfg.execution.fee_bps + cfg.execution.slippage_bps) / 10000.0)
            pending = _PendingTrade(
                decision_date=pd.Timestamp(dt),
                exec_date=pd.Timestamp(trade_dt),
                mode=last_mode,
                regime_value=last_regime_value,
                new_weights=target,
                cost=total_cost,
                turnover=turnover,
                selection_df=selection.selection_df.copy(),
            )

            sel_df = selection.selection_df.copy()
            if not sel_df.empty:
                for row in sel_df.to_dict("records"):
                    ticker = str(row.get("ticker", ""))
                    weights_rows.append(
                        {
                            "rebalance_date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                            "trade_date": pd.Timestamp(trade_dt).strftime("%Y-%m-%d"),
                            "mode": last_mode,
                            "regime_value": last_regime_value,
                            "group_key": row.get("group_key", ""),
                            "ticker": ticker,
                            "name": row.get("name", "CASH" if ticker == "CASH" else ""),
                            "market": market_map.get(ticker, "CASH" if ticker == "CASH" else "ETF"),
                            "target_group_weight": float(row.get("target_group_weight", 0.0) or 0.0),
                            "weight": float(row.get("assigned_weight", 0.0) or 0.0),
                            "selected": bool(row.get("selected", False)),
                            "available": bool(row.get("available", False)),
                            "liquidity_20d_value": float(row.get("liquidity_20d_value", 0.0) or 0.0),
                        }
                    )

        gross = float(w.sum())
        cash_weight = max(0.0, 1.0 - gross)
        n_holdings = int((w > 0).sum())
        equity_rows.append(
            {
                "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                "port_ret": float(eq / eq_prev - 1.0),
                "equity": float(eq),
                "mode": last_mode,
                "regime_value": last_regime_value,
                "n_holdings": n_holdings,
                "gross_exposure": gross,
                "cash_weight": cash_weight,
            }
        )

    equity_df = pd.DataFrame(equity_rows)
    summary_metrics = _perf_metrics(equity_df)
    one_year = _window_metric(equity_df, 1)
    two_year = _window_metric(equity_df, 2)
    three_year = _window_metric(equity_df, 3)
    five_year = _window_metric(equity_df, 5)
    summary_df = pd.DataFrame(
        [
            {
                "strategy": cfg.strategy_name,
                "start": str(equity_df["date"].iloc[0]),
                "end": str(equity_df["date"].iloc[-1]),
                "days": int(len(equity_df)),
                "cagr": summary_metrics["cagr"],
                "mdd": summary_metrics["mdd"],
                "sharpe": summary_metrics["sharpe"],
                "avg_daily_ret": summary_metrics["avg_daily_ret"],
                "vol_daily": summary_metrics["vol_daily"],
                "turnover": float(turnover_total),
                "rebalance_count": int(len(rebalance_dates)),
                "fee_bps": float(cfg.execution.fee_bps),
                "slippage_bps": float(cfg.execution.slippage_bps),
                "cagr_1y": one_year["cagr"],
                "sharpe_1y": one_year["sharpe"],
                "mdd_1y": one_year["mdd"],
                "cagr_2y": two_year["cagr"],
                "sharpe_2y": two_year["sharpe"],
                "mdd_2y": two_year["mdd"],
                "cagr_3y": three_year["cagr"],
                "sharpe_3y": three_year["sharpe"],
                "mdd_3y": three_year["mdd"],
                "cagr_5y": five_year["cagr"],
                "sharpe_5y": five_year["sharpe"],
                "mdd_5y": five_year["mdd"],
            }
        ]
    )

    return BacktestResult(
        summary_df=summary_df,
        equity_df=equity_df,
        holdings_df=pd.DataFrame(weights_rows),
        trades_df=pd.DataFrame(trades_rows),
        meta={"turnover_total": float(turnover_total)},
    )
