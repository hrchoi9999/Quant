from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r'D:\Quant')


def main() -> None:
    ap = argparse.ArgumentParser(description='Validate model comparison outputs.')
    ap.add_argument('--asof', default='2026-03-17')
    ap.add_argument('--rebalance', default='M', choices=['M','W'])
    ap.add_argument('--service-profile', default='auto', choices=['auto','stable','balanced','growth'])
    args = ap.parse_args()

    outdir = PROJECT_ROOT / 'reports' / 'model_compare'
    prefix = f"{str(args.asof).replace('-', '')}_{str(args.rebalance).upper()}_"
    summary = sorted(outdir.glob(f'model_compare_summary_{prefix}*_{args.service_profile}.csv'))[-1]
    periods = sorted(outdir.glob(f'model_compare_periods_{prefix}*_{args.service_profile}.csv'))[-1]
    yearly = sorted(outdir.glob(f'model_compare_yearly_{prefix}*_{args.service_profile}.csv'))[-1]
    regime = sorted(outdir.glob(f'model_compare_regime_{prefix}*_{args.service_profile}.csv'))[-1]
    cost = sorted(outdir.glob(f'model_compare_cost_sensitivity_{prefix}*_{args.service_profile}.csv'))[-1]
    report_candidates = sorted(outdir.glob(f'model_compare_report_{prefix}*.md'))
    if not report_candidates:
        raise AssertionError('Missing markdown report output')
    report = report_candidates[-1]

    s = pd.read_csv(summary)
    p = pd.read_csv(periods)
    y = pd.read_csv(yearly)
    r = pd.read_csv(regime)
    c = pd.read_csv(cost)

    expected_models = {'S2','S3','S4','S5','S6','Router'}
    expected_periods = {'FULL','1Y','2Y','3Y','5Y'}
    if not expected_models.issubset(set(s['model'].astype(str))):
        raise AssertionError(f'Summary models mismatch: {sorted(set(s["model"].astype(str)))}')
    if not expected_models.issubset(set(p['model'].astype(str))):
        raise AssertionError('Period models mismatch')
    if not expected_periods.issubset(set(p['period'].astype(str))):
        raise AssertionError('Missing comparison periods')
    if not expected_models.issubset(set(y['model'].astype(str))):
        raise AssertionError('Yearly models mismatch')
    if not expected_models.issubset(set(r['model'].astype(str))):
        raise AssertionError('Regime models mismatch')
    if not expected_models.issubset(set(c['model'].astype(str))):
        raise AssertionError('Cost models mismatch')
    print(f'[OK] summary={summary}')
    print(f'[OK] periods={periods}')
    print(f'[OK] yearly={yearly}')
    print(f'[OK] regime={regime}')
    print(f'[OK] cost={cost}')
    print(f'[OK] report={report}')
    print(f'[OK] summary_rows={len(s)} period_rows={len(p)} yearly_rows={len(y)} regime_rows={len(r)} cost_rows={len(c)}')


if __name__ == '__main__':
    main()
