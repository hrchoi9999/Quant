from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r'D:\Quant')


def main() -> None:
    ap = argparse.ArgumentParser(description='Validate multi-asset router smoke run.')
    ap.add_argument('--asof', default='2026-03-17')
    ap.add_argument('--start', default='2024-01-02')
    ap.add_argument('--end', default='2026-03-17')
    ap.add_argument('--rebalance', default='M', choices=['M', 'W'])
    ap.add_argument('--service-profile', default='auto', choices=['auto', 'stable', 'balanced', 'growth'])
    args = ap.parse_args()

    cmd = [str(PROJECT_ROOT / 'venv64' / 'Scripts' / 'python.exe'), str(PROJECT_ROOT / 'src' / 'backtest' / 'run_backtest_multiasset_router.py'), '--asof', str(args.asof), '--start', str(args.start), '--end', str(args.end), '--rebalance', str(args.rebalance), '--service-profile', str(args.service_profile)]
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))

    stamp_prefix = f"{str(args.asof).replace('-', '')}_{str(args.rebalance).upper()}_"
    outdir = PROJECT_ROOT / 'reports' / 'backtest_router'
    summary = sorted(outdir.glob(f'router_summary_{stamp_prefix}*_{args.service_profile}.csv'))[-1]
    equity = sorted(outdir.glob(f'router_equity_{stamp_prefix}*_{args.service_profile}.csv'))[-1]
    weights = sorted(outdir.glob(f'router_weights_{stamp_prefix}*_{args.service_profile}.csv'))[-1]
    trades = sorted(outdir.glob(f'router_trades_{stamp_prefix}*_{args.service_profile}.csv'))[-1]
    decisions = sorted(outdir.glob(f'router_decisions_{stamp_prefix}*_{args.service_profile}.csv'))[-1]
    compare = sorted(outdir.glob(f'router_compare_{stamp_prefix}*_{args.service_profile}.csv'))[-1]

    summary_df = pd.read_csv(summary)
    equity_df = pd.read_csv(equity)
    weights_df = pd.read_csv(weights)
    decisions_df = pd.read_csv(decisions)
    compare_df = pd.read_csv(compare)

    req_sum = {'strategy', 'cagr', 'mdd', 'sharpe', 'turnover', 'rebalance_count', 'service_profile'}
    req_dec = {'date', 'detected_regime', 'selected_models', 'stock_sleeve_weight', 'etf_sleeve_weight', 'service_profile', 'fallback_used', 'note'}
    req_cmp = {'S2', 'S3', 'S4', 'S5', 'S6', 'ROUTER'}
    if summary_df.empty or equity_df.empty or weights_df.empty or decisions_df.empty or compare_df.empty:
        raise AssertionError('One or more router outputs are empty')
    if not req_sum.issubset(summary_df.columns):
        raise AssertionError(f'Missing summary cols: {sorted(req_sum - set(summary_df.columns))}')
    if not req_dec.issubset(decisions_df.columns):
        raise AssertionError(f'Missing decision cols: {sorted(req_dec - set(decisions_df.columns))}')
    if not req_cmp.issubset(set(compare_df['model'].astype(str).tolist())):
        raise AssertionError(f'Compare models mismatch: {sorted(set(compare_df["model"].astype(str).tolist()))}')

    print(f'[OK] summary={summary}')
    print(f'[OK] equity={equity}')
    print(f'[OK] weights={weights}')
    print(f'[OK] trades={trades}')
    print(f'[OK] decisions={decisions}')
    print(f'[OK] compare={compare}')
    print(f'[OK] decision_rows={len(decisions_df)} weight_rows={len(weights_df)} compare_models={sorted(compare_df["model"].astype(str).tolist())}')


if __name__ == '__main__':
    main()
