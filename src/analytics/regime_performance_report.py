from __future__ import annotations

import pandas as pd

from src.analytics.model_performance_comparator import ModelSeries, perf_metrics


def build_regime_performance_table(models: dict[str, ModelSeries], regime_mode_df: pd.DataFrame) -> pd.DataFrame:
    if regime_mode_df is None or regime_mode_df.empty:
        return pd.DataFrame(columns=['model','regime','days','cagr','mdd','sharpe','avg_daily_ret','vol_daily'])
    mode_map = regime_mode_df.copy()
    mode_map['date'] = pd.to_datetime(mode_map['date'])
    rows = []
    for model, bundle in models.items():
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        merged = eq.merge(mode_map[['date', 'mode']], on='date', how='left').rename(columns={'mode': 'regime'})
        merged['regime'] = merged['regime'].fillna('unknown')
        for regime, sub in merged.groupby('regime'):
            if sub.empty:
                continue
            m = perf_metrics(sub[['date','port_ret','equity']].copy())
            rows.append({
                'model': model,
                'regime': regime,
                'days': int(len(sub)),
                'cagr': m['cagr'],
                'mdd': m['mdd'],
                'sharpe': m['sharpe'],
                'avg_daily_ret': m['avg_daily_ret'],
                'vol_daily': m['vol_daily'],
            })
    return pd.DataFrame(rows)
