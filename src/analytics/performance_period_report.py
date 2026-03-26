from __future__ import annotations

import pandas as pd

from src.analytics.model_performance_comparator import ModelSeries, perf_metrics


def build_period_table(models: dict[str, ModelSeries]) -> pd.DataFrame:
    rows = []
    for model, bundle in models.items():
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        periods = {
            '3M': eq.tail(63).copy(),
            '6M': eq.tail(126).copy(),
            '1Y': eq.tail(252).copy(),
            '2Y': eq.tail(504).copy(),
            '3Y': eq.tail(756).copy(),
            '5Y': eq.tail(1260).copy(),
            'FULL': eq.copy(),
        }
        for period, sub in periods.items():
            if sub.empty:
                continue
            m = perf_metrics(sub)
            rows.append({
                'model': model,
                'period': period,
                'start': sub['date'].min().strftime('%Y-%m-%d'),
                'end': sub['date'].max().strftime('%Y-%m-%d'),
                'days': int(len(sub)),
                'total_return': m['total_return'],
                'cagr': m['cagr'],
                'mdd': m['mdd'],
                'sharpe': m['sharpe'],
                'avg_daily_ret': m['avg_daily_ret'],
                'vol_daily': m['vol_daily'],
            })
    return pd.DataFrame(rows)


def build_yearly_table(models: dict[str, ModelSeries]) -> pd.DataFrame:
    rows = []
    for model, bundle in models.items():
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        eq['year'] = eq['date'].dt.year
        for year, sub in eq.groupby('year'):
            sub = sub.sort_values('date').copy()
            if sub.empty:
                continue
            total_return = float(sub['equity'].iloc[-1] / sub['equity'].iloc[0] - 1.0) if len(sub) > 1 else float(sub['port_ret'].sum())
            m = perf_metrics(sub)
            rows.append({
                'model': model,
                'year': int(year),
                'start': sub['date'].min().strftime('%Y-%m-%d'),
                'end': sub['date'].max().strftime('%Y-%m-%d'),
                'days': int(len(sub)),
                'total_return': total_return,
                'cagr': m['cagr'],
                'mdd': m['mdd'],
                'sharpe': m['sharpe'],
                'avg_daily_ret': m['avg_daily_ret'],
                'vol_daily': m['vol_daily'],
            })
    return pd.DataFrame(rows)
