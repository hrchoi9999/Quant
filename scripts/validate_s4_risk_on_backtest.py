from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")


def main() -> None:
    ap = argparse.ArgumentParser(description='Smoke validate S4 risk-on backtest.')
    ap.add_argument('--asof', default='2026-03-17')
    ap.add_argument('--start', default='2024-01-02')
    ap.add_argument('--end', default='2026-03-17')
    ap.add_argument('--rebalance', default='M', choices=['M','W'])
    ap.add_argument('--outdir', default=str(PROJECT_ROOT / 'reports' / 'backtest_etf_allocation'))
    args = ap.parse_args()

    cmd = [
        str(PROJECT_ROOT / 'venv64' / 'Scripts' / 'python.exe'),
        str(PROJECT_ROOT / 'src' / 'backtest' / 'run_backtest_s4_risk_on_allocation.py'),
        '--asof', str(args.asof), '--start', str(args.start), '--end', str(args.end), '--rebalance', str(args.rebalance).upper(), '--outdir', str(args.outdir)
    ]
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))

    outdir = Path(args.outdir)
    stamp = f"{str(args.asof).replace('-', '')}_{str(args.rebalance).upper()}_{str(args.start).replace('-', '')}_{str(args.end).replace('-', '')}"
    summary = outdir / f's4_alloc_summary_{stamp}.csv'
    equity = outdir / f's4_alloc_equity_{stamp}.csv'
    weights = outdir / f's4_alloc_weights_{stamp}.csv'
    trades = outdir / f's4_alloc_trades_{stamp}.csv'
    compare = outdir / f's4_vs_task04_riskon_{stamp}.csv'
    for p in [summary, equity, weights, trades, compare]:
        if not p.exists():
            raise AssertionError(f'Missing output file: {p}')

    summary_df = pd.read_csv(summary)
    equity_df = pd.read_csv(equity)
    weights_df = pd.read_csv(weights)
    compare_df = pd.read_csv(compare)
    if summary_df.empty or equity_df.empty or weights_df.empty or compare_df.empty:
        raise AssertionError('One or more S4 outputs are empty')
    if not {'strategy','cagr','mdd','sharpe','turnover','rebalance_count'}.issubset(summary_df.columns):
        raise AssertionError('summary columns missing')
    if not {'strong_trend','rs_growth','sector_hot','growth_participation','weakening','overheating'}.issubset(weights_df.columns):
        raise AssertionError('weights diagnostics missing')
    if set(compare_df['model']) != {'TASK04_RISK_ON','S4_RISK_ON_V1'}:
        raise AssertionError('comparison file missing expected models')

    print(f'[OK] summary={summary}')
    print(f'[OK] equity_rows={len(equity_df)} weights_rows={len(weights_df)} compare_rows={len(compare_df)}')
    print(f'[OK] compare_models={sorted(compare_df["model"].tolist())}')


if __name__ == '__main__':
    main()
