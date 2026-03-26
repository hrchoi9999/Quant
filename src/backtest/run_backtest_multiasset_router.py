from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

try:
    from src.backtest.configs.router_config import RouterConfig, RouterExecutionConfig, RouterRegimeConfig
    from src.backtest.core.data import compute_daily_returns, load_prices_wide, load_regime_panel, month_end_dates, week_anchor_dates
    from src.backtest.core.router_backtest_runner import ModelBundle, _perf_metrics, run_router_backtest
    from src.backtest.router.multiasset_regime_router import build_regime_mode_series
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / 'src').exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.backtest.configs.router_config import RouterConfig, RouterExecutionConfig, RouterRegimeConfig
    from src.backtest.core.data import compute_daily_returns, load_prices_wide, load_regime_panel, month_end_dates, week_anchor_dates
    from src.backtest.core.router_backtest_runner import ModelBundle, _perf_metrics, run_router_backtest
    from src.backtest.router.multiasset_regime_router import build_regime_mode_series

PROJECT_ROOT = Path(r'D:\Quant')


def _today() -> str:
    return date.today().isoformat()


def _normalize_date(s: str) -> str:
    return str(s).strip().replace('/', '-')


def _latest_glob(folder: Path, pattern: str) -> Path:
    files = sorted(folder.glob(pattern), key=lambda p: (p.stat().st_mtime, p.name))
    if not files:
        raise FileNotFoundError(f'{folder} / {pattern}')
    return files[-1]


def _ensure_etf_model_outputs(model: str, asof: str, start: str, end: str, rebalance: str, outdir: Path) -> tuple[Path, Path]:
    prefix = {'S4': 's4', 'S5': 's5', 'S6': 's6'}[model]
    eq = outdir / f'{prefix}_alloc_equity_{asof.replace("-","")}_{rebalance}_{start.replace("-","")}_{end.replace("-","")}.csv'
    wt = outdir / f'{prefix}_alloc_weights_{asof.replace("-","")}_{rebalance}_{start.replace("-","")}_{end.replace("-","")}.csv'
    if eq.exists() and wt.exists():
        return eq, wt
    script = {'S4': 'run_backtest_s4_risk_on_allocation.py', 'S5': 'run_backtest_s5_neutral_allocation.py', 'S6': 'run_backtest_s6_defensive_allocation.py'}[model]
    cmd = [str(PROJECT_ROOT / 'venv64' / 'Scripts' / 'python.exe'), str(PROJECT_ROOT / 'src' / 'backtest' / script), '--asof', asof, '--start', start, '--end', end, '--rebalance', rebalance, '--outdir', str(outdir)]
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
    return eq, wt


def _standardize_s2_holdings(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={'ticker': 'string'}).copy()
    df['ticker'] = df['ticker'].astype(str).str.zfill(6)
    if 'name' not in df.columns:
        df['name'] = df['ticker']
    if 'market' not in df.columns:
        df['market'] = 'STOCK'
    return df[['trade_date', 'ticker', 'name', 'market', 'weight']].copy()


def _standardize_etf_weights(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={'ticker': 'string'}).copy()
    df = df.loc[df['selected'].astype(bool)].copy() if 'selected' in df.columns else df.copy()
    df['ticker'] = df['ticker'].fillna('').astype(str).str.zfill(6)
    return df[['trade_date', 'ticker', 'name', 'market', 'weight']].copy()


def _load_s2_bundle(start: str, end: str) -> ModelBundle:
    folder = PROJECT_ROOT / 'reports' / 'backtest_regime_refactor'
    eq_path = _latest_glob(folder, 'regime_bt_equity_3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_*.csv')
    hold_path = _latest_glob(folder, 'regime_bt_holdings_3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_*.csv')
    eq = pd.read_csv(eq_path)
    eq['date'] = pd.to_datetime(eq['date'])
    eq = eq.loc[(eq['date'] >= pd.Timestamp(start)) & (eq['date'] <= pd.Timestamp(end)), ['date', 'port_ret', 'equity']].copy()
    eq['date'] = eq['date'].dt.strftime('%Y-%m-%d')
    holdings = _standardize_s2_holdings(hold_path)
    holdings['trade_date'] = pd.to_datetime(holdings['trade_date'])
    holdings = holdings.loc[(holdings['trade_date'] >= pd.Timestamp(start)) & (holdings['trade_date'] <= pd.Timestamp(end))].copy()
    holdings['trade_date'] = holdings['trade_date'].dt.strftime('%Y-%m-%d')
    return ModelBundle(model='S2', equity_df=eq, holdings_df=holdings)


def _reconstruct_s3_daily(price_db: Path, start: str, end: str, model_name: str = 'S3') -> ModelBundle:
    folder = PROJECT_ROOT / 'reports' / 'backtest_s3_dev'
    if model_name == 'S3_CORE2':
        hist_path = _latest_glob(folder, 's3_holdings_history_top20_daily_*_2013-10-14_*.csv')
        nav_path = _latest_glob(folder, 's3_nav_hold_top20_daily_*_2013-10-14_*.csv')
    else:
        hist_path = _latest_glob(folder, 's3_holdings_history_top20_2013-10-14_*.csv')
        nav_path = _latest_glob(folder, 's3_nav_hold_top20_2013-10-14_*.csv')
    hist = pd.read_csv(hist_path, dtype={'ticker': 'string'})
    nav = pd.read_csv(nav_path)
    hist['date'] = pd.to_datetime(hist['date'])
    nav['date'] = pd.to_datetime(nav['date'])
    hist = hist.loc[(hist['date'] >= pd.Timestamp(start)) & (hist['date'] <= pd.Timestamp(end))].copy()
    nav = nav.loc[(nav['date'] >= pd.Timestamp(start)) & (nav['date'] <= pd.Timestamp(end))].copy()
    tickers = sorted(hist['ticker'].astype(str).str.zfill(6).unique().tolist())
    close_wide = load_prices_wide(price_db=price_db, tickers=tickers, start=start, end=end)
    ret_wide = compute_daily_returns(close_wide).fillna(0.0)
    dates = pd.DatetimeIndex(close_wide.index)
    if len(dates) == 0:
        raise RuntimeError('No S3 prices to reconstruct daily series')
    sched = sorted(pd.to_datetime(hist['date'].drop_duplicates()).tolist())
    weight_map = {}
    holdings_rows = []
    for dt in sched:
        sub = hist.loc[hist['date'] == pd.Timestamp(dt)].copy()
        sub['ticker'] = sub['ticker'].astype(str).str.zfill(6)
        cash_row = nav.loc[nav['date'] == pd.Timestamp(dt)]
        cash_weight = float(cash_row['cash_weight'].iloc[0]) if not cash_row.empty else 0.0
        invest_weight = max(0.0, 1.0 - cash_weight)
        per_weight = invest_weight / len(sub) if len(sub) else 0.0
        w = {'CASH': cash_weight}
        for _, row in sub.iterrows():
            ticker = str(row['ticker']).zfill(6)
            w[ticker] = per_weight
            holdings_rows.append({'trade_date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'ticker': ticker, 'name': row.get('name', ''), 'market': row.get('market', 'STOCK'), 'weight': per_weight})
        if len(sub) == 0:
            holdings_rows.append({'trade_date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'ticker': 'CASH', 'name': 'CASH', 'market': 'CASH', 'weight': 1.0})
        elif cash_weight > 0:
            holdings_rows.append({'trade_date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'ticker': 'CASH', 'name': 'CASH', 'market': 'CASH', 'weight': cash_weight})
        weight_map[pd.Timestamp(dt)] = w
    current = {'CASH': 1.0}
    eq = 1.0
    eq_rows = []
    for dt in dates:
        prior_sched = [d for d in sched if d <= pd.Timestamp(dt)]
        if prior_sched:
            current = weight_map[prior_sched[-1]]
        eq_prev = eq
        day_ret = 0.0
        for ticker, weight in current.items():
            if ticker == 'CASH':
                continue
            if ticker in ret_wide.columns:
                day_ret += float(weight) * float(ret_wide.loc[dt, ticker])
        eq *= 1.0 + day_ret
        eq_rows.append({'date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'port_ret': float(eq / eq_prev - 1.0), 'equity': float(eq)})
    return ModelBundle(model=model_name, equity_df=pd.DataFrame(eq_rows), holdings_df=pd.DataFrame(holdings_rows))


def _load_etf_bundle(model: str, asof: str, start: str, end: str, rebalance: str, outdir: Path) -> ModelBundle:
    eq_path, wt_path = _ensure_etf_model_outputs(model, asof, start, end, rebalance, outdir)
    eq = pd.read_csv(eq_path)[['date', 'port_ret', 'equity']].copy()
    holdings = _standardize_etf_weights(wt_path)
    return ModelBundle(model=model, equity_df=eq, holdings_df=holdings)


def _build_rebalance_dates(dates: pd.DatetimeIndex, rebalance: str, anchor_weekday: int, holiday_shift: str) -> list[pd.Timestamp]:
    if rebalance.upper() == 'W':
        return week_anchor_dates(dates, anchor_weekday=anchor_weekday, holiday_shift=holiday_shift)
    return month_end_dates(dates)


def _compare_rows(router_summary: pd.DataFrame, bundles: dict[str, ModelBundle], start: str, end: str) -> pd.DataFrame:
    rows = []
    for model, bundle in bundles.items():
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        eq = eq.loc[(eq['date'] >= pd.Timestamp(start)) & (eq['date'] <= pd.Timestamp(end))].copy()
        m = _perf_metrics(eq)
        rows.append({'model': model, 'start': start, 'end': end, 'days': int(len(eq)), 'cagr': m['cagr'], 'mdd': m['mdd'], 'sharpe': m['sharpe'], 'avg_daily_ret': m['avg_daily_ret'], 'vol_daily': m['vol_daily']})
    router_row = {'model': 'ROUTER'}
    router_row.update(router_summary.iloc[0].to_dict())
    rows.append(router_row)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description='Run multi-asset regime router backtest.')
    ap.add_argument('--price-db', default=str(PROJECT_ROOT / 'data' / 'db' / 'price.db'))
    ap.add_argument('--regime-db', default=str(PROJECT_ROOT / 'data' / 'db' / 'regime.db'))
    ap.add_argument('--start', default='2024-01-02')
    ap.add_argument('--end', default='2026-03-17')
    ap.add_argument('--asof', default=_today())
    ap.add_argument('--rebalance', default='M', choices=['M', 'W'])
    ap.add_argument('--weekly-anchor-weekday', type=int, default=2)
    ap.add_argument('--weekly-holiday-shift', default='prev', choices=['prev', 'next'])
    ap.add_argument('--regime-horizon', default='3m')
    ap.add_argument('--service-profile', default='auto', choices=['auto', 'stable', 'balanced', 'growth'])
    ap.add_argument('--fee-bps', type=float, default=0.0)
    ap.add_argument('--slippage-bps', type=float, default=0.0)
    ap.add_argument('--outdir', default=str(PROJECT_ROOT / 'reports' / 'backtest_router'))
    args = ap.parse_args()

    price_db = Path(args.price_db)
    regime_db = Path(args.regime_db)
    start = _normalize_date(args.start)
    end = _normalize_date(args.end)
    asof = _normalize_date(args.asof)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    cfg = RouterConfig(regime=RouterRegimeConfig(horizon=str(args.regime_horizon)), execution=RouterExecutionConfig(rebalance=str(args.rebalance).upper(), weekly_anchor_weekday=int(args.weekly_anchor_weekday), weekly_holiday_shift=str(args.weekly_holiday_shift), fee_bps=float(args.fee_bps), slippage_bps=float(args.slippage_bps)))

    bundles = {
        'S2': _load_s2_bundle(start, end),
        'S3': _reconstruct_s3_daily(price_db, start, end, 'S3'),
        'S3_CORE2': _reconstruct_s3_daily(price_db, start, end, 'S3_CORE2'),
        'S4': _load_etf_bundle('S4', asof, start, end, str(args.rebalance).upper(), PROJECT_ROOT / 'reports' / 'backtest_etf_allocation'),
        'S5': _load_etf_bundle('S5', asof, start, end, str(args.rebalance).upper(), PROJECT_ROOT / 'reports' / 'backtest_etf_allocation'),
        'S6': _load_etf_bundle('S6', asof, start, end, str(args.rebalance).upper(), PROJECT_ROOT / 'reports' / 'backtest_etf_allocation'),
    }

    overlap_start = max(pd.to_datetime(bundle.equity_df['date']).min() for bundle in bundles.values())
    overlap_end = min(pd.to_datetime(bundle.equity_df['date']).max() for bundle in bundles.values())
    for model, bundle in list(bundles.items()):
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        eq = eq.loc[(eq['date'] >= overlap_start) & (eq['date'] <= overlap_end)].copy()
        eq['date'] = eq['date'].dt.strftime('%Y-%m-%d')
        hold = bundle.holdings_df.copy()
        if not hold.empty:
            hold['trade_date'] = pd.to_datetime(hold['trade_date'])
            hold = hold.loc[(hold['trade_date'] >= overlap_start) & (hold['trade_date'] <= overlap_end)].copy()
            hold['trade_date'] = hold['trade_date'].dt.strftime('%Y-%m-%d')
        bundles[model] = ModelBundle(model=model, equity_df=eq, holdings_df=hold)

    regime_panel = load_regime_panel(regime_db=regime_db, start=overlap_start.strftime('%Y-%m-%d'), end=overlap_end.strftime('%Y-%m-%d'), horizons=[str(args.regime_horizon)])
    regime_mode_df = build_regime_mode_series(regime_panel, cfg)
    base_dates = pd.DatetimeIndex(pd.to_datetime(bundles['S4'].equity_df['date']))
    rebalance_dates = _build_rebalance_dates(base_dates, str(args.rebalance).upper(), int(args.weekly_anchor_weekday), str(args.weekly_holiday_shift))

    result = run_router_backtest(model_bundles=bundles, regime_mode_df=regime_mode_df, rebalance_dates=rebalance_dates, cfg=cfg, service_profile=str(args.service_profile))
    decisions_df = result.meta['decisions_df']
    compare_df = _compare_rows(result.summary_df, bundles, overlap_start.strftime('%Y-%m-%d'), overlap_end.strftime('%Y-%m-%d'))

    stamp = f"{asof.replace('-', '')}_{str(args.rebalance).upper()}_{overlap_start.strftime('%Y%m%d')}_{overlap_end.strftime('%Y%m%d')}_{args.service_profile}"
    summary_path = outdir / f'router_summary_{stamp}.csv'
    equity_path = outdir / f'router_equity_{stamp}.csv'
    weights_path = outdir / f'router_weights_{stamp}.csv'
    trades_path = outdir / f'router_trades_{stamp}.csv'
    decisions_path = outdir / f'router_decisions_{stamp}.csv'
    compare_path = outdir / f'router_compare_{stamp}.csv'

    result.summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    result.equity_df.to_csv(equity_path, index=False, encoding='utf-8-sig')
    result.holdings_df.to_csv(weights_path, index=False, encoding='utf-8-sig')
    result.trades_df.to_csv(trades_path, index=False, encoding='utf-8-sig')
    decisions_df.to_csv(decisions_path, index=False, encoding='utf-8-sig')
    compare_df.to_csv(compare_path, index=False, encoding='utf-8-sig')

    print(f'[OK] overlap_start={overlap_start.strftime("%Y-%m-%d")} overlap_end={overlap_end.strftime("%Y-%m-%d")}')
    print(f'[OK] summary={summary_path}')
    print(f'[OK] equity={equity_path}')
    print(f'[OK] weights={weights_path}')
    print(f'[OK] trades={trades_path}')
    print(f'[OK] decisions={decisions_path}')
    print(f'[OK] compare={compare_path}')


if __name__ == '__main__':
    main()
