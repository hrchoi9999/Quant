from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from src.backtest.configs.s6_defensive_config import S6DefensiveConfig
from src.backtest.contracts import BacktestResult
from src.backtest.core.data import next_trading_day
from src.backtest.core.etf_allocation_engine import _calc_turnover, _perf_metrics, _window_metric
from src.backtest.portfolio.s6_defensive_allocator import allocate_s6_defensive


@dataclass
class _PendingTrade:
    decision_date: pd.Timestamp
    exec_date: pd.Timestamp
    new_weights: pd.Series
    cost: float
    turnover: float
    selection_df: pd.DataFrame
    diagnostics: dict[str, object]


def run_s6_backtest(
    *,
    close_wide: pd.DataFrame,
    ret_wide: pd.DataFrame,
    core_df: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp],
    cfg: S6DefensiveConfig,
    name_map: Optional[Dict[str, str]] = None,
    market_map: Optional[Dict[str, str]] = None,
) -> BacktestResult:
    name_map = name_map or {}
    market_map = market_map or {}
    dates = pd.DatetimeIndex(pd.to_datetime(close_wide.index)).sort_values()
    price_cols = [str(c).zfill(6) for c in close_wide.columns]
    close_wide = close_wide.copy(); close_wide.columns = price_cols
    ret_wide = ret_wide.copy(); ret_wide.columns = price_cols
    rb_set = set(pd.to_datetime(rebalance_dates))

    w = pd.Series(0.0, index=price_cols, dtype=float)
    eq = 1.0
    pending: _PendingTrade | None = None
    equity_rows = []
    weights_rows = []
    trades_rows = []
    turnover_total = 0.0
    last_diag: dict[str, object] = {}

    for dt in dates:
        eq_prev = eq
        day_ret = pd.to_numeric(ret_wide.loc[dt], errors='coerce').fillna(0.0)
        eq *= 1.0 + float((day_ret * w).sum())

        if pending is not None and pd.Timestamp(dt) == pending.exec_date:
            eq *= 1.0 - pending.cost
            prev_w = w.copy()
            w = pending.new_weights.copy()
            turnover_total += float(pending.turnover)
            last_diag = dict(pending.diagnostics)
            for ticker in sorted(set(prev_w.index).union(set(w.index))):
                prev_weight = float(prev_w.get(ticker, 0.0))
                new_weight = float(w.get(ticker, 0.0))
                delta = new_weight - prev_weight
                if abs(delta) < 1e-12:
                    continue
                trades_rows.append({
                    'rebalance_date': pending.decision_date.strftime('%Y-%m-%d'),
                    'trade_date': pending.exec_date.strftime('%Y-%m-%d'),
                    'side': 'BUY' if delta > 0 else 'SELL',
                    'ticker': ticker,
                    'name': name_map.get(ticker, ticker),
                    'market': market_map.get(ticker, 'ETF'),
                    'prev_weight': prev_weight,
                    'new_weight': new_weight,
                    'delta_weight': delta,
                    'exec_price': float(close_wide.loc[dt, ticker]) if ticker in close_wide.columns else float('nan'),
                    'turnover_component': abs(delta) / 2.0,
                    **last_diag,
                })
            pending = None

        if pd.Timestamp(dt) in rb_set:
            trade_dt = next_trading_day(dates, dt) or pd.Timestamp(dt)
            available_tickers = [t for t in price_cols if pd.notna(close_wide.loc[trade_dt, t])]
            alloc = allocate_s6_defensive(core_df=core_df, close_wide=close_wide, ret_wide=ret_wide, asof=pd.Timestamp(dt), cfg=cfg, available_tickers=available_tickers)
            target = pd.Series(0.0, index=price_cols, dtype=float)
            for ticker, target_weight in alloc.weights.items():
                if ticker != 'CASH' and ticker in target.index:
                    target.loc[ticker] = float(target_weight)
            turnover = _calc_turnover(w, target)
            total_cost = turnover * ((cfg.execution.fee_bps + cfg.execution.slippage_bps) / 10000.0)
            pending = _PendingTrade(pd.Timestamp(dt), pd.Timestamp(trade_dt), target, total_cost, turnover, alloc.selection_df.copy(), dict(alloc.diagnostics))
            for row in alloc.selection_df.to_dict('records'):
                ticker = str(row.get('ticker', ''))
                weights_rows.append({
                    'rebalance_date': pd.Timestamp(dt).strftime('%Y-%m-%d'),
                    'trade_date': pd.Timestamp(trade_dt).strftime('%Y-%m-%d'),
                    'mode': 'risk_off',
                    'model': cfg.strategy_name,
                    'ticker': ticker,
                    'name': row.get('name', 'CASH' if ticker == 'CASH' else ''),
                    'market': market_map.get(ticker, 'CASH' if ticker == 'CASH' else 'ETF'),
                    'group_key': row.get('group_key', ''),
                    'target_group_weight': float(row.get('target_group_weight', 0.0) or 0.0),
                    'weight': float(row.get('assigned_weight', 0.0) or 0.0),
                    'selected': bool(row.get('selected', False)),
                    'available': bool(row.get('available', False)),
                    **alloc.diagnostics,
                })

        gross = float(w.sum())
        cash_weight = max(0.0, 1.0 - gross)
        equity_rows.append({
            'date': pd.Timestamp(dt).strftime('%Y-%m-%d'),
            'port_ret': float(eq / eq_prev - 1.0),
            'equity': float(eq),
            'mode': 'risk_off',
            'model': cfg.strategy_name,
            'n_holdings': int((w > 0).sum()),
            'gross_exposure': gross,
            'cash_weight': cash_weight,
            **last_diag,
        })

    equity_df = pd.DataFrame(equity_rows)
    perf = _perf_metrics(equity_df)
    w1 = _window_metric(equity_df, 1)
    w2 = _window_metric(equity_df, 2)
    w3 = _window_metric(equity_df, 3)
    w5 = _window_metric(equity_df, 5)
    summary_df = pd.DataFrame([{
        'strategy': cfg.strategy_name,
        'start': str(equity_df['date'].iloc[0]),
        'end': str(equity_df['date'].iloc[-1]),
        'days': int(len(equity_df)),
        'cagr': perf['cagr'], 'mdd': perf['mdd'], 'sharpe': perf['sharpe'], 'avg_daily_ret': perf['avg_daily_ret'], 'vol_daily': perf['vol_daily'],
        'turnover': float(turnover_total), 'rebalance_count': int(len(rebalance_dates)),
        'fee_bps': float(cfg.execution.fee_bps), 'slippage_bps': float(cfg.execution.slippage_bps),
        'cagr_1y': w1['cagr'], 'sharpe_1y': w1['sharpe'], 'mdd_1y': w1['mdd'],
        'cagr_2y': w2['cagr'], 'sharpe_2y': w2['sharpe'], 'mdd_2y': w2['mdd'],
        'cagr_3y': w3['cagr'], 'sharpe_3y': w3['sharpe'], 'mdd_3y': w3['mdd'],
        'cagr_5y': w5['cagr'], 'sharpe_5y': w5['sharpe'], 'mdd_5y': w5['mdd'],
    }])
    return BacktestResult(summary_df=summary_df, equity_df=equity_df, holdings_df=pd.DataFrame(weights_rows), trades_df=pd.DataFrame(trades_rows), meta={'turnover_total': float(turnover_total)})
