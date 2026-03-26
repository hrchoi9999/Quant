from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

CURRENT = Path(__file__).resolve()
ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / 'src').exists()), CURRENT.parent)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.cost_sensitivity_report import build_cost_sensitivity_table
from src.analytics.model_performance_comparator import align_model_periods, drawdown_series, load_all_model_series, perf_metrics
from src.analytics.performance_period_report import build_period_table, build_yearly_table
from src.analytics.regime_performance_report import build_regime_performance_table
from src.analytics.render_model_compare_report import render_report
from src.backtest.configs.router_config import RouterConfig, RouterRegimeConfig
from src.backtest.core.data import load_regime_panel
from src.backtest.router.multiasset_regime_router import build_regime_mode_series

PROJECT_ROOT = Path(r'D:\Quant')


def _summary_table(models):
    rows = []
    for model, bundle in models.items():
        m = perf_metrics(bundle.equity_df)
        row = {'model': model, 'start': bundle.equity_df['date'].iloc[0], 'end': bundle.equity_df['date'].iloc[-1], 'days': int(len(bundle.equity_df)), 'cagr': m['cagr'], 'mdd': m['mdd'], 'sharpe': m['sharpe'], 'avg_daily_ret': m['avg_daily_ret'], 'vol_daily': m['vol_daily']}
        if bundle.summary_df is not None and not bundle.summary_df.empty:
            src = bundle.summary_df.iloc[0].to_dict()
            row['turnover'] = float(src.get('turnover', float('nan')))
            row['rebalance_count'] = float(src.get('rebalance_count', float('nan')))
            row['fee_bps'] = float(src.get('fee_bps', 0.0) or 0.0)
            row['slippage_bps'] = float(src.get('slippage_bps', 0.0) or 0.0)
        else:
            row['turnover'] = float('nan')
            row['rebalance_count'] = float('nan')
            row['fee_bps'] = 0.0
            row['slippage_bps'] = 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def _render_charts(models: dict, outdir: Path, stamp: str) -> tuple[Path | None, Path | None]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None, None
    eq_path = outdir / f'model_compare_equity_{stamp}.png'
    dd_path = outdir / f'model_compare_drawdown_{stamp}.png'
    plt.figure(figsize=(12, 6))
    for model, bundle in models.items():
        eq = bundle.equity_df.copy()
        plt.plot(pd.to_datetime(eq['date']), eq['equity'], label=model)
    plt.legend()
    plt.title('Equity Curve Comparison')
    plt.tight_layout()
    plt.savefig(eq_path, dpi=150)
    plt.close()

    plt.figure(figsize=(12, 6))
    for model, bundle in models.items():
        dd = drawdown_series(bundle.equity_df)
        plt.plot(dd.index, dd.values, label=model)
    plt.legend()
    plt.title('Drawdown Comparison')
    plt.tight_layout()
    plt.savefig(dd_path, dpi=150)
    plt.close()
    return eq_path, dd_path


def main() -> None:
    ap = argparse.ArgumentParser(description='Run integrated model comparison framework.')
    ap.add_argument('--price-db', default=str(PROJECT_ROOT / 'data' / 'db' / 'price.db'))
    ap.add_argument('--regime-db', default=str(PROJECT_ROOT / 'data' / 'db' / 'regime.db'))
    ap.add_argument('--asof', default='2026-03-17')
    ap.add_argument('--start', default='2024-01-02')
    ap.add_argument('--end', default='2026-03-17')
    ap.add_argument('--rebalance', default='M', choices=['M','W'])
    ap.add_argument('--service-profile', default='auto', choices=['auto','stable','balanced','growth'])
    ap.add_argument('--outdir', default=str(PROJECT_ROOT / 'reports' / 'model_compare'))
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    models = load_all_model_series(price_db=Path(args.price_db), asof=str(args.asof), start=str(args.start), end=str(args.end), rebalance=str(args.rebalance), service_profile=str(args.service_profile))
    models, overlap_start, overlap_end = align_model_periods(models)
    summary_df = _summary_table(models)
    periods_df = build_period_table(models)
    yearly_df = build_yearly_table(models)
    regime_panel = load_regime_panel(regime_db=Path(args.regime_db), start=overlap_start.strftime('%Y-%m-%d'), end=overlap_end.strftime('%Y-%m-%d'), horizons=['3m'])
    regime_mode_df = build_regime_mode_series(regime_panel, RouterConfig(regime=RouterRegimeConfig(horizon='3m')))
    regime_df = build_regime_performance_table(models, regime_mode_df)
    cost_df = build_cost_sensitivity_table(models, summary_df)

    stamp = f"{str(args.asof).replace('-', '')}_{str(args.rebalance).upper()}_{overlap_start.strftime('%Y%m%d')}_{overlap_end.strftime('%Y%m%d')}_{args.service_profile}"
    summary_path = outdir / f'model_compare_summary_{stamp}.csv'
    periods_path = outdir / f'model_compare_periods_{stamp}.csv'
    yearly_path = outdir / f'model_compare_yearly_{stamp}.csv'
    regime_path = outdir / f'model_compare_regime_{stamp}.csv'
    cost_path = outdir / f'model_compare_cost_sensitivity_{stamp}.csv'
    report_path = outdir / f'model_compare_report_{stamp}.md'

    summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    periods_df.to_csv(periods_path, index=False, encoding='utf-8-sig')
    yearly_df.to_csv(yearly_path, index=False, encoding='utf-8-sig')
    regime_df.to_csv(regime_path, index=False, encoding='utf-8-sig')
    cost_df.to_csv(cost_path, index=False, encoding='utf-8-sig')
    render_report(out_path=report_path, summary_df=summary_df, periods_df=periods_df, yearly_df=yearly_df, regime_df=regime_df, cost_df=cost_df, compare_note=f'Common comparison window: {overlap_start.strftime("%Y-%m-%d")} to {overlap_end.strftime("%Y-%m-%d")}. Models: S2, S3, S4, S5, S6, Router({args.service_profile}).')
    eq_chart, dd_chart = _render_charts(models, outdir, stamp)

    print(f'[OK] summary={summary_path}')
    print(f'[OK] periods={periods_path}')
    print(f'[OK] yearly={yearly_path}')
    print(f'[OK] regime={regime_path}')
    print(f'[OK] cost={cost_path}')
    print(f'[OK] report={report_path}')
    if eq_chart:
        print(f'[OK] equity_chart={eq_chart}')
    if dd_chart:
        print(f'[OK] drawdown_chart={dd_chart}')
    print(f'[OK] overlap_start={overlap_start.strftime("%Y-%m-%d")} overlap_end={overlap_end.strftime("%Y-%m-%d")}')


if __name__ == '__main__':
    main()
