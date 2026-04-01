
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\S3_T3_PREFILTER_BACKTEST"
HORIZON_MAP = {'3M': 12, '6M': 24, '1Y': 52, '2Y': 104, '3Y': 156}
TOP_N = 20
FILTER_SPECS = [
    ('baseline_s3', None),
    ('t3_top_50pct_prefilter', 0.50),
    ('t3_top_30pct_prefilter', 0.70),
]


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def latest_s3_run_and_dates() -> tuple[str, list[pd.Timestamp]]:
    run = read_sql(QS_DB, "SELECT run_id FROM run_runs WHERE model_code='S3' ORDER BY created_at DESC LIMIT 1")
    run_id = str(run.loc[0, 'run_id'])
    dates = read_sql(QS_DETAIL_DB, 'SELECT DISTINCT date FROM run_signal_details_s3 WHERE run_id=? ORDER BY date', (run_id,), parse_dates=['date'])
    signal_dates = sorted(pd.to_datetime(dates['date'].dropna().unique()))
    return run_id, signal_dates


def latest_fund_snapshot(fund_df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    w = fund_df[fund_df['available_from'] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(['ticker', 'available_from', 'date']).groupby('ticker', as_index=False).tail(1)


def build_t3_score(universe: pd.DataFrame, p_row: pd.DataFrame, fund_snap: pd.DataFrame, signal_date: pd.Timestamp) -> pd.DataFrame:
    snap = universe.merge(p_row, on='ticker', how='left').merge(fund_snap[['ticker', 'fund_accel_score', 'rev_delta_3m', 'op_delta_3m']], on='ticker', how='left')
    snap['dist_ma60'] = snap['close'] / snap['ma60'] - 1.0
    snap['ma_stack_gap'] = snap['ma60'] / snap['ma120'] - 1.0
    grp_cols = ['rev_delta_3m', 'op_delta_3m', 'fund_accel_score', 'ma_stack_gap', 'mom20', 'dist_ma60']
    for c in grp_cols:
        snap[c] = pd.to_numeric(snap[c], errors='coerce')
    snap['rev_delta_3m_pct'] = snap['rev_delta_3m'].rank(pct=True)
    snap['op_delta_3m_pct'] = snap['op_delta_3m'].rank(pct=True)
    snap['fund_accel_score_pct'] = snap['fund_accel_score'].rank(pct=True)
    snap['ma_stack_gap_pct'] = snap['ma_stack_gap'].rank(pct=True)
    snap['mom20_pct'] = snap['mom20'].rank(pct=True)
    snap['dist_ma60_pct'] = snap['dist_ma60'].rank(pct=True)
    snap['t3_positive_score'] = snap[['rev_delta_3m_pct', 'op_delta_3m_pct', 'fund_accel_score_pct', 'ma_stack_gap_pct']].mean(axis=1, skipna=True)
    snap['t3_crowded_score'] = snap[['mom20_pct', 'dist_ma60_pct']].mean(axis=1, skipna=True)
    snap['t3_model_score'] = snap['t3_positive_score'] - 0.35 * snap['t3_crowded_score'] - 0.05 * snap['breakout60'].fillna(0).astype(float)
    snap['t3_model_score_pct'] = snap['t3_model_score'].rank(pct=True)
    snap['signal_date'] = signal_date
    return snap


def build_s3_score(universe: pd.DataFrame, p_row: pd.DataFrame, fund_snap: pd.DataFrame, signal_date: pd.Timestamp) -> pd.DataFrame:
    snap = universe.merge(p_row, on='ticker', how='left').merge(fund_snap[['ticker', 'growth_score', 'fund_accel_score']], on='ticker', how='left')
    snap['mom20_pct'] = snap['mom20'].rank(pct=True)
    snap['vol_ratio_pct'] = snap['vol_ratio_20'].rank(pct=True)
    snap['fund_level_pct'] = snap['growth_score'].rank(pct=True)
    snap['fund_accel_pct'] = snap['fund_accel_score'].rank(pct=True)
    trend_bonus = ((snap['ma60'] > snap['ma120']) & (snap['ma60_slope'] > 0)).astype(int)
    snap['s3_score'] = (
        0.30 * snap['fund_level_pct'].fillna(0)
        + 0.20 * snap['fund_accel_pct'].fillna(0)
        + 0.25 * snap['mom20_pct'].fillna(0)
        + 0.10 * snap['vol_ratio_pct'].fillna(0)
        + 0.05 * snap['breakout60'].fillna(0).astype(int)
        + 0.10 * trend_bonus
    )
    snap['signal_date'] = signal_date
    return snap


def make_end_map(signal_dates: list[pd.Timestamp], horizon_weeks: int) -> dict[pd.Timestamp, pd.Timestamp]:
    dts = sorted(pd.to_datetime(pd.Series(signal_dates).dropna().unique()))
    return {dts[i]: dts[i + horizon_weeks] for i in range(len(dts) - horizon_weeks)}


def compute_window_stats(cand: pd.DataFrame, price_groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for row in cand.itertuples(index=False):
        s = price_groups.get(row.ticker)
        if s is None:
            continue
        w = s[(s['date'] >= row.signal_date) & (s['date'] <= row.end_date)]
        if w.empty:
            continue
        entry = float(w['close'].iloc[0])
        rel = w['close'] / entry
        peak = rel.cummax()
        dd = rel / peak - 1.0
        rows.append({
            'variant': row.variant,
            'signal_date': row.signal_date,
            'end_date': row.end_date,
            'horizon': row.horizon,
            'ticker': row.ticker,
            'selected': int(row.selected),
            'fwd_ret': float(rel.iloc[-1] - 1.0),
            'path_mdd': float(dd.min()),
        })
    return pd.DataFrame(rows)


def compute_portfolio_nav(selected_df: pd.DataFrame, price_wide: pd.DataFrame, signal_dates: list[pd.Timestamp], variant: str) -> pd.DataFrame:
    if selected_df.empty:
        return pd.DataFrame()
    lookup = {pd.Timestamp(d): list(g['ticker']) for d, g in selected_df.groupby('signal_date')}
    nav = 1.0
    rows = []
    for i in range(1, len(signal_dates)):
        prev_d = signal_dates[i - 1]
        d = signal_dates[i]
        held = lookup.get(prev_d, [])
        if held:
            prev_px = price_wide.loc[prev_d, held] if prev_d in price_wide.index else pd.Series(dtype=float)
            curr_px = price_wide.loc[d, held] if d in price_wide.index else pd.Series(dtype=float)
            m = pd.DataFrame({'prev': prev_px, 'curr': curr_px}).dropna()
            port_ret = float((m['curr'] / m['prev'] - 1.0).mean()) if not m.empty else 0.0
        else:
            port_ret = 0.0
        nav *= (1.0 + port_ret)
        rows.append({'variant': variant, 'date': d, 'nav': nav, 'holdings_count': len(held)})
    return pd.DataFrame(rows)


def perf_windows(nav_df: pd.DataFrame) -> pd.DataFrame:
    if nav_df.empty:
        return pd.DataFrame()
    nav_df = nav_df.sort_values('date').copy()
    last = pd.to_datetime(nav_df['date'].max())
    windows = [('3M', 84), ('6M', 168), ('1Y', 365), ('2Y', 730), ('3Y', 1095)]
    out = []
    for label, days in windows:
        sub = nav_df[nav_df['date'] >= (last - pd.Timedelta(days=days))].copy()
        if len(sub) < 2:
            continue
        start = float(sub['nav'].iloc[0])
        end = float(sub['nav'].iloc[-1])
        total_return = end / start - 1.0
        years = max((pd.to_datetime(sub['date'].iloc[-1]) - pd.to_datetime(sub['date'].iloc[0])).days / 365.25, 1/52)
        cagr = (end / start) ** (1 / years) - 1.0 if start > 0 else np.nan
        dd = sub['nav'] / sub['nav'].cummax() - 1.0
        mdd = float(dd.min())
        rets = sub['nav'].pct_change().dropna()
        sharpe = float((rets.mean() / rets.std()) * np.sqrt(52)) if len(rets) > 1 and rets.std() > 0 else np.nan
        out.append({'period': label, 'total_return': total_return, 'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe})
    return pd.DataFrame(out)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(UNIVERSE_CSV, dtype={'ticker': str})[['ticker', 'name', 'market', 'mcap']]
    universe['ticker'] = universe['ticker'].astype(str).str.zfill(6)

    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])
    price_groups = {t: g[['date', 'close']].reset_index(drop=True) for t, g in prices.groupby('ticker')}
    price_wide = prices.pivot(index='date', columns='ticker', values='close').sort_index()

    p = read_sql(S3_DB, 'SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope FROM s3_price_features_daily', parse_dates=['date'])
    p['ticker'] = p['ticker'].astype(str).str.zfill(6)
    f = read_sql(S3_DB, 'SELECT date, ticker, available_from, growth_score, fund_accel_score, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly', parse_dates=['date', 'available_from'])
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)

    _run_id, signal_dates = latest_s3_run_and_dates()
    selected_rows = []
    for d0 in signal_dates:
        p_row = p[p['date'] == d0].copy()
        if p_row.empty:
            continue
        f_snap = latest_fund_snapshot(f, d0)
        t3_snap = build_t3_score(universe, p_row, f_snap, d0)
        s3_snap = build_s3_score(universe, p_row, f_snap, d0)
        base = s3_snap.copy()
        for variant, cutoff in FILTER_SPECS:
            snap = base.merge(t3_snap[['ticker', 't3_model_score_pct']], on='ticker', how='left')
            if cutoff is not None:
                snap = snap[snap['t3_model_score_pct'] >= cutoff].copy()
            snap = snap.dropna(subset=['s3_score']).copy()
            chosen = snap.sort_values(['s3_score', 'ticker'], ascending=[False, True]).head(TOP_N).copy()
            chosen['variant'] = variant
            selected_rows.append(chosen[['variant', 'signal_date', 'ticker', 's3_score', 't3_model_score_pct']])
    selected_df = pd.concat(selected_rows, ignore_index=True)
    selected_df.to_csv(OUTDIR / 's3_t3_prefilter_selected_history.csv', index=False, encoding='utf-8-sig')

    # selected vs not selected within the same variant's investable set
    all_stats = []
    for variant, cutoff in FILTER_SPECS:
        selected_lookup = set(zip(selected_df.loc[selected_df['variant'] == variant, 'signal_date'].map(pd.Timestamp), selected_df.loc[selected_df['variant'] == variant, 'ticker']))
        variant_rows = []
        for horizon, weeks in HORIZON_MAP.items():
            end_map = make_end_map(signal_dates, weeks)
            for d0, d1 in end_map.items():
                p_row = p[p['date'] == d0].copy()
                if p_row.empty:
                    continue
                f_snap = latest_fund_snapshot(f, d0)
                t3_snap = build_t3_score(universe, p_row, f_snap, d0)
                s3_snap = build_s3_score(universe, p_row, f_snap, d0)
                snap = s3_snap.merge(t3_snap[['ticker', 't3_model_score_pct']], on='ticker', how='left')
                if cutoff is not None:
                    snap = snap[snap['t3_model_score_pct'] >= cutoff].copy()
                snap = snap.dropna(subset=['s3_score']).copy()
                snap['variant'] = variant
                snap['signal_date'] = d0
                snap['end_date'] = d1
                snap['horizon'] = horizon
                snap['selected'] = snap['ticker'].map(lambda t: 1 if (d0, t) in selected_lookup else 0)
                variant_rows.append(snap[['variant','signal_date','end_date','horizon','ticker','selected']])
        cand = pd.concat(variant_rows, ignore_index=True)
        all_stats.append(compute_window_stats(cand, price_groups))
    stats = pd.concat(all_stats, ignore_index=True)
    stats.to_csv(OUTDIR / 's3_t3_prefilter_window_stats.csv', index=False, encoding='utf-8-sig')

    summary_rows = []
    for (variant, horizon, selected), g in stats.groupby(['variant', 'horizon', 'selected']):
        summary_rows.append({
            'variant': variant,
            'horizon': horizon,
            'scope': 'selected' if selected == 1 else 'not_selected',
            'avg_return': g['fwd_ret'].mean(),
            'avg_mdd': g['path_mdd'].mean(),
            'n_obs': len(g),
        })
    summary = pd.DataFrame(summary_rows).sort_values(['variant','horizon','scope'])
    summary.to_csv(OUTDIR / 's3_t3_prefilter_selected_vs_not_selected_summary.csv', index=False, encoding='utf-8-sig')

    nav_frames = []
    perf_frames = []
    for variant, _cutoff in FILTER_SPECS:
        nav = compute_portfolio_nav(selected_df[selected_df['variant'] == variant], price_wide, signal_dates, variant)
        nav_frames.append(nav)
        perf = perf_windows(nav)
        if not perf.empty:
            perf['variant'] = variant
            perf_frames.append(perf)
    nav_all = pd.concat(nav_frames, ignore_index=True)
    perf_all = pd.concat(perf_frames, ignore_index=True)
    nav_all.to_csv(OUTDIR / 's3_t3_prefilter_nav_history.csv', index=False, encoding='utf-8-sig')
    perf_all.to_csv(OUTDIR / 's3_t3_prefilter_performance_summary.csv', index=False, encoding='utf-8-sig')

    lines = ['# S3 T3 Prefilter Backtest', '']
    lines.append('## Portfolio performance summary')
    lines.append('| Variant | Period | Total Return | CAGR | MDD | Sharpe |')
    lines.append('|---|---|---:|---:|---:|---:|')
    for r in perf_all.sort_values(['variant','period']).itertuples(index=False):
        lines.append(f'| {r.variant} | {r.period} | {r.total_return:.2%} | {r.cagr:.2%} | {r.mdd:.2%} | {r.sharpe:.2f} |')
    lines.append('')
    lines.append('## Selected vs not-selected summary')
    lines.append('| Variant | Horizon | Scope | Avg Return | Avg MDD | N |')
    lines.append('|---|---|---|---:|---:|---:|')
    for r in summary.itertuples(index=False):
        lines.append(f'| {r.variant} | {r.horizon} | {r.scope} | {r.avg_return:.2%} | {r.avg_mdd:.2%} | {r.n_obs} |')
    (OUTDIR / 's3_t3_prefilter_backtest_review.md').write_text('\n'.join(lines), encoding='utf-8')
    print(perf_all.to_string(index=False))


if __name__ == '__main__':
    main()
