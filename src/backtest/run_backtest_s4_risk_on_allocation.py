from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

try:
    from src.backtest.configs.s4_risk_on_config import S4RiskOnConfig, S4ExecutionConfig
    from src.backtest.core.data import compute_daily_returns, load_prices_wide, month_end_dates, week_anchor_dates
    from src.backtest.core.s4_backtest_runner import run_s4_backtest
    from src.repositories.instrument_repository import InstrumentRepository
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / 'src').exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.backtest.configs.s4_risk_on_config import S4RiskOnConfig, S4ExecutionConfig
    from src.backtest.core.data import compute_daily_returns, load_prices_wide, month_end_dates, week_anchor_dates
    from src.backtest.core.s4_backtest_runner import run_s4_backtest
    from src.repositories.instrument_repository import InstrumentRepository

PROJECT_ROOT = Path(r"D:\Quant")


def _today() -> str:
    return date.today().isoformat()


def _normalize_date(s: str) -> str:
    return str(s).strip().replace('/', '-')


def _load_core_universe(price_db: Path, asof: str) -> pd.DataFrame:
    repo = InstrumentRepository(price_db)
    core_df = repo.get_etf_core_universe(asof=asof)
    if core_df.empty:
        csv_path = PROJECT_ROOT / 'data' / 'universe' / f'universe_etf_core_{asof.replace("-", "")}.csv'
        if not csv_path.exists():
            raise FileNotFoundError(csv_path)
        core_df = pd.read_csv(csv_path, dtype={'ticker': 'string'})
        if 'market' not in core_df.columns:
            core_df['market'] = 'ETF'
    core_df['ticker'] = core_df['ticker'].astype(str).str.zfill(6)
    return core_df


def _build_rebalance_dates(price_index: pd.DatetimeIndex, rebalance: str, anchor_weekday: int, holiday_shift: str) -> list[pd.Timestamp]:
    if str(rebalance).upper() == 'W':
        return week_anchor_dates(price_index, anchor_weekday=anchor_weekday, holiday_shift=holiday_shift)
    return month_end_dates(price_index)


def _load_value_wide(price_db: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    where = []
    params = []
    if tickers:
        where.append('ticker IN (' + ','.join(['?'] * len(tickers)) + ')')
        params.extend([str(t).zfill(6) for t in tickers])
    where.append('date >= ?'); params.append(start)
    where.append('date <= ?'); params.append(end)
    q = 'SELECT date, ticker, value FROM prices_daily WHERE ' + ' AND '.join(where) + ' ORDER BY date, ticker'
    with sqlite3.connect(str(price_db)) as con:
        df = pd.read_sql_query(q, con, params=params)
    if df.empty:
        return pd.DataFrame()
    df['ticker'] = df['ticker'].astype(str).str.zfill(6)
    wide = df.pivot(index='date', columns='ticker', values='value').sort_index()
    wide.index = pd.to_datetime(wide.index)
    return wide


def _ensure_task04_baseline(asof: str, start: str, end: str, rebalance: str, outdir: Path) -> Path:
    baseline = outdir / f'etf_alloc_summary_{asof.replace("-", "")}_{rebalance}_{start.replace("-", "")}_{end.replace("-", "")}_risk_on.csv'
    if baseline.exists():
        return baseline
    cmd = [
        str(PROJECT_ROOT / 'venv64' / 'Scripts' / 'python.exe'),
        str(PROJECT_ROOT / 'src' / 'backtest' / 'run_backtest_etf_allocation.py'),
        '--asof', asof, '--start', start, '--end', end, '--rebalance', rebalance, '--force-mode', 'risk_on', '--outdir', str(outdir)
    ]
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
    return baseline


def main() -> None:
    ap = argparse.ArgumentParser(description='Run S4 risk-on offensive allocation backtest.')
    ap.add_argument('--price-db', default=str(PROJECT_ROOT / 'data' / 'db' / 'price.db'))
    ap.add_argument('--start', default='2024-01-02')
    ap.add_argument('--end', default=_today())
    ap.add_argument('--asof', default=_today())
    ap.add_argument('--rebalance', default='M', choices=['M','W'])
    ap.add_argument('--weekly-anchor-weekday', type=int, default=2)
    ap.add_argument('--weekly-holiday-shift', default='prev', choices=['prev','next'])
    ap.add_argument('--fee-bps', type=float, default=5.0)
    ap.add_argument('--slippage-bps', type=float, default=5.0)
    ap.add_argument('--outdir', default=str(PROJECT_ROOT / 'reports' / 'backtest_etf_allocation'))
    args = ap.parse_args()

    price_db = Path(args.price_db)
    start = _normalize_date(args.start)
    end = _normalize_date(args.end)
    asof = _normalize_date(args.asof)
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    cfg = S4RiskOnConfig(execution=S4ExecutionConfig(
        fee_bps=float(args.fee_bps), slippage_bps=float(args.slippage_bps), rebalance=str(args.rebalance).upper(), weekly_anchor_weekday=int(args.weekly_anchor_weekday), weekly_holiday_shift=str(args.weekly_holiday_shift)
    ))
    core_df = _load_core_universe(price_db, asof)
    tickers = core_df['ticker'].astype(str).str.zfill(6).drop_duplicates().tolist()
    close_wide = load_prices_wide(price_db=price_db, tickers=tickers, start=start, end=end)
    if close_wide.empty:
        raise RuntimeError('No ETF prices loaded for S4 run.')
    value_wide = _load_value_wide(price_db, tickers, start, end)
    ret_wide = compute_daily_returns(close_wide).fillna(0.0)
    rebalance_dates = _build_rebalance_dates(close_wide.index, str(args.rebalance).upper(), int(args.weekly_anchor_weekday), str(args.weekly_holiday_shift))
    name_map = {str(r['ticker']).zfill(6): str(r.get('name', '')) for r in core_df.to_dict('records')}
    market_map = {str(r['ticker']).zfill(6): str(r.get('market', 'ETF')) for r in core_df.to_dict('records')}
    result = run_s4_backtest(close_wide=close_wide, value_wide=value_wide, ret_wide=ret_wide, core_df=core_df, rebalance_dates=rebalance_dates, cfg=cfg, name_map=name_map, market_map=market_map)

    stamp = f"{asof.replace('-', '')}_{str(args.rebalance).upper()}_{start.replace('-', '')}_{end.replace('-', '')}"
    summary_path = outdir / f's4_alloc_summary_{stamp}.csv'
    equity_path = outdir / f's4_alloc_equity_{stamp}.csv'
    weights_path = outdir / f's4_alloc_weights_{stamp}.csv'
    trades_path = outdir / f's4_alloc_trades_{stamp}.csv'
    compare_path = outdir / f's4_vs_task04_riskon_{stamp}.csv'
    result.summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    result.equity_df.to_csv(equity_path, index=False, encoding='utf-8-sig')
    result.holdings_df.to_csv(weights_path, index=False, encoding='utf-8-sig')
    result.trades_df.to_csv(trades_path, index=False, encoding='utf-8-sig')

    baseline_path = _ensure_task04_baseline(asof, start, end, str(args.rebalance).upper(), outdir)
    base = pd.read_csv(baseline_path)
    s4 = pd.read_csv(summary_path)
    compare = pd.DataFrame([
        {'model': 'TASK04_RISK_ON', **base.iloc[0].to_dict()},
        {'model': 'S4_RISK_ON_V1', **s4.iloc[0].to_dict()},
    ])
    compare.to_csv(compare_path, index=False, encoding='utf-8-sig')

    print(f'[OK] summary={summary_path}')
    print(f'[OK] equity={equity_path}')
    print(f'[OK] weights={weights_path}')
    print(f'[OK] trades={trades_path}')
    print(f'[OK] compare={compare_path}')
    print(f'[OK] rebalance_dates={len(rebalance_dates)} core_tickers={len(tickers)}')


if __name__ == '__main__':
    main()
