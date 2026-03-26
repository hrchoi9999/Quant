from __future__ import annotations

import pandas as pd

from src.analytics.model_performance_comparator import ModelSeries


def build_cost_sensitivity_table(models: dict[str, ModelSeries], summary_df: pd.DataFrame, scenario_cost_bps: tuple[float, ...] = (0.0, 10.0, 20.0, 30.0)) -> pd.DataFrame:
    rows = []
    for _, row in summary_df.iterrows():
        model = str(row['model'])
        days = float(row.get('days', 0.0) or 0.0)
        years = max(days / 252.0, 1.0 / 252.0)
        turnover = float(row.get('turnover', 0.0) or 0.0)
        base_cagr = float(row.get('cagr', float('nan')))
        current_fee_bps = float(row.get('fee_bps', 0.0) or 0.0) + float(row.get('slippage_bps', 0.0) or 0.0)
        for cost_bps in scenario_cost_bps:
            annual_drag = (turnover * (cost_bps / 10000.0)) / years
            rows.append({
                'model': model,
                'scenario_cost_bps': float(cost_bps),
                'current_cost_bps': current_fee_bps,
                'turnover': turnover,
                'years': years,
                'base_cagr': base_cagr,
                'approx_net_cagr': base_cagr - annual_drag,
                'approx_cost_drag': annual_drag,
            })
    return pd.DataFrame(rows)
