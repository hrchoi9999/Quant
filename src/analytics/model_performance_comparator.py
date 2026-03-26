from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src.backtest.core.data import compute_daily_returns, load_prices_wide

PROJECT_ROOT = Path(r'D:\Quant')


@dataclass(frozen=True)
class ModelSeries:
    model: str
    equity_df: pd.DataFrame
    holdings_df: pd.DataFrame | None = None
    summary_df: pd.DataFrame | None = None
    source: str = ''


def _latest_glob(folder: Path, pattern: str) -> Path:
    files = sorted(folder.glob(pattern), key=lambda p: (p.stat().st_mtime, p.name))
    if not files:
        raise FileNotFoundError(f'{folder} / {pattern}')
    return files[-1]


def perf_metrics(equity_df: pd.DataFrame) -> dict[str, float]:
    if equity_df is None or equity_df.empty:
        return {'cagr': float('nan'), 'mdd': float('nan'), 'sharpe': float('nan'), 'avg_daily_ret': float('nan'), 'vol_daily': float('nan'), 'total_return': float('nan')}
    work = equity_df.copy()
    rets = pd.to_numeric(work['port_ret'], errors='coerce').fillna(0.0)
    eq = pd.to_numeric(work['equity'], errors='coerce').dropna()
    n = int(len(eq))
    if n == 0:
        return {'cagr': float('nan'), 'mdd': float('nan'), 'sharpe': float('nan'), 'avg_daily_ret': float('nan'), 'vol_daily': float('nan'), 'total_return': float('nan')}
    start_eq = float(eq.iloc[0])
    end_eq = float(eq.iloc[-1])
    years = max(n / 252.0, 1.0 / 252.0)
    total_return = float(end_eq / start_eq - 1.0) if start_eq > 0 else float('nan')
    cagr = float((end_eq / start_eq) ** (1.0 / years) - 1.0) if start_eq > 0 and end_eq > 0 else float('nan')
    dd = eq / eq.cummax() - 1.0
    mdd = float(dd.min()) if len(dd) else float('nan')
    vol = float(rets.std(ddof=0))
    sharpe = float((rets.mean() / vol) * np.sqrt(252.0)) if vol > 0 else float('nan')
    return {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'avg_daily_ret': float(rets.mean()), 'vol_daily': vol, 'total_return': total_return}


def align_model_periods(models: dict[str, ModelSeries]) -> tuple[dict[str, ModelSeries], pd.Timestamp, pd.Timestamp]:
    overlap_start = max(pd.to_datetime(m.equity_df['date']).min() for m in models.values())
    overlap_end = min(pd.to_datetime(m.equity_df['date']).max() for m in models.values())
    aligned = {}
    for name, bundle in models.items():
        eq = bundle.equity_df.copy()
        eq['date'] = pd.to_datetime(eq['date'])
        eq = eq.loc[(eq['date'] >= overlap_start) & (eq['date'] <= overlap_end)].copy()
        eq['date'] = eq['date'].dt.strftime('%Y-%m-%d')
        hold = bundle.holdings_df.copy() if bundle.holdings_df is not None else None
        if hold is not None and not hold.empty and 'trade_date' in hold.columns:
            hold['trade_date'] = pd.to_datetime(hold['trade_date'])
            hold = hold.loc[(hold['trade_date'] >= overlap_start) & (hold['trade_date'] <= overlap_end)].copy()
            hold['trade_date'] = hold['trade_date'].dt.strftime('%Y-%m-%d')
        aligned[name] = ModelSeries(model=bundle.model, equity_df=eq, holdings_df=hold, summary_df=bundle.summary_df, source=bundle.source)
    return aligned, pd.Timestamp(overlap_start), pd.Timestamp(overlap_end)


def load_s2_series(start: str, end: str) -> ModelSeries:
    folder = PROJECT_ROOT / 'reports' / 'backtest_regime_refactor'
    eq_path = _latest_glob(folder, 'regime_bt_equity_3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_*.csv')
    hold_path = _latest_glob(folder, 'regime_bt_holdings_3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_*.csv')
    summary_path = _latest_glob(folder, 'regime_bt_summary_3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_*.csv')
    eq = pd.read_csv(eq_path)
    eq['date'] = pd.to_datetime(eq['date'])
    eq = eq.loc[(eq['date'] >= pd.Timestamp(start)) & (eq['date'] <= pd.Timestamp(end)), ['date', 'port_ret', 'equity']].copy()
    eq['date'] = eq['date'].dt.strftime('%Y-%m-%d')
    hold = pd.read_csv(hold_path, dtype={'ticker': 'string'})
    hold['ticker'] = hold['ticker'].astype(str).str.zfill(6)
    hold['trade_date'] = pd.to_datetime(hold['trade_date'])
    hold = hold.loc[(hold['trade_date'] >= pd.Timestamp(start)) & (hold['trade_date'] <= pd.Timestamp(end)), ['trade_date', 'ticker', 'name', 'market', 'weight']].copy()
    hold['trade_date'] = hold['trade_date'].dt.strftime('%Y-%m-%d')
    return ModelSeries(model='S2', equity_df=eq, holdings_df=hold, summary_df=pd.read_csv(summary_path), source=str(eq_path))


def load_s3_series(price_db: Path, start: str, end: str, model_name: str = 'S3') -> ModelSeries:
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
    sched = sorted(pd.to_datetime(hist['date'].drop_duplicates()).tolist())
    weight_map = {}
    hold_rows = []
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
            hold_rows.append({'trade_date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'ticker': ticker, 'name': row.get('name', ''), 'market': row.get('market', 'STOCK'), 'weight': per_weight})
        if len(sub) == 0:
            hold_rows.append({'trade_date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'ticker': 'CASH', 'name': 'CASH', 'market': 'CASH', 'weight': 1.0})
        elif cash_weight > 0:
            hold_rows.append({'trade_date': pd.Timestamp(dt).strftime('%Y-%m-%d'), 'ticker': 'CASH', 'name': 'CASH', 'market': 'CASH', 'weight': cash_weight})
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
    return ModelSeries(model=model_name, equity_df=pd.DataFrame(eq_rows), holdings_df=pd.DataFrame(hold_rows), summary_df=None, source=str(nav_path))


def load_etf_series(model: str, asof: str, start: str, end: str, rebalance: str = 'M') -> ModelSeries:
    folder = PROJECT_ROOT / 'reports' / 'backtest_etf_allocation'
    prefix = {'S4': 's4', 'S5': 's5', 'S6': 's6'}[model]
    eq_path = folder / f"{prefix}_alloc_equity_{asof.replace('-', '')}_{rebalance}_{start.replace('-', '')}_{end.replace('-', '')}.csv"
    wt_path = folder / f"{prefix}_alloc_weights_{asof.replace('-', '')}_{rebalance}_{start.replace('-', '')}_{end.replace('-', '')}.csv"
    summary_path = folder / f"{prefix}_alloc_summary_{asof.replace('-', '')}_{rebalance}_{start.replace('-', '')}_{end.replace('-', '')}.csv"
    eq = pd.read_csv(eq_path)[['date', 'port_ret', 'equity']].copy()
    hold = pd.read_csv(wt_path, dtype={'ticker': 'string'})
    hold = hold.loc[hold['selected'].astype(bool)].copy() if 'selected' in hold.columns else hold.copy()
    hold['ticker'] = hold['ticker'].fillna('').astype(str).str.zfill(6)
    hold = hold[['trade_date', 'ticker', 'name', 'market', 'weight']].copy()
    return ModelSeries(model=model, equity_df=eq, holdings_df=hold, summary_df=pd.read_csv(summary_path), source=str(eq_path))


def load_router_series(asof: str, service_profile: str = 'auto', rebalance: str = 'M') -> ModelSeries:
    folder = PROJECT_ROOT / 'reports' / 'backtest_router'
    summary_path = _latest_glob(folder, f'router_summary_{asof.replace("-","")}_{rebalance}_*_{service_profile}.csv')
    suffix = summary_path.stem.replace('router_summary_', '')
    equity_path = folder / f'router_equity_{suffix}.csv'
    weights_path = folder / f'router_weights_{suffix}.csv'
    eq = pd.read_csv(equity_path)[['date', 'port_ret', 'equity']].copy()
    hold = pd.read_csv(weights_path, dtype={'ticker': 'string'})[['trade_date', 'ticker', 'name', 'market', 'weight']].copy()
    return ModelSeries(model='Router', equity_df=eq, holdings_df=hold, summary_df=pd.read_csv(summary_path), source=str(summary_path))


def load_all_model_series(*, price_db: Path, asof: str, start: str, end: str, rebalance: str = 'M', service_profile: str = 'auto') -> dict[str, ModelSeries]:
    models = {
        'S2': load_s2_series(start, end),
        'S3': load_s3_series(price_db, start, end, 'S3'),
        'S3_CORE2': load_s3_series(price_db, start, end, 'S3_CORE2'),
        'S4': load_etf_series('S4', asof, start, end, rebalance),
        'S5': load_etf_series('S5', asof, start, end, rebalance),
        'S6': load_etf_series('S6', asof, start, end, rebalance),
        'Router': load_router_series(asof, service_profile, rebalance),
    }
    return models


def drawdown_series(equity_df: pd.DataFrame) -> pd.Series:
    eq = pd.to_numeric(equity_df['equity'], errors='coerce').dropna()
    dd = eq / eq.cummax() - 1.0
    return pd.Series(dd.values, index=pd.to_datetime(equity_df['date']))
