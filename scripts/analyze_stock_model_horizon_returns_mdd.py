from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260330"
HORIZONS = [1, 4, 8, 12]


def read_sql(db, q, params=None, parse_dates=None):
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(q, con, params=params or (), parse_dates=parse_dates)
    finally:
        con.close()


def latest_runs() -> dict[str, str]:
    df = read_sql(
        QS_DB,
        """
        SELECT model_code, run_id FROM (
          SELECT model_code, run_id, created_at,
                 ROW_NUMBER() OVER (PARTITION BY model_code ORDER BY created_at DESC) rn
          FROM run_runs WHERE model_code IN ('S2','S3','S3_CORE2')
        ) WHERE rn=1
        """,
    )
    return dict(zip(df.model_code, df.run_id))


def make_end_map(signal_dates, horizon_n):
    dts = sorted(pd.to_datetime(pd.Series(signal_dates).dropna().unique()))
    return {dts[i]: dts[i + horizon_n] for i in range(len(dts) - horizon_n)}


def compute_window_stats(cand: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    price_groups = {t: g[['date', 'close']].reset_index(drop=True) for t, g in prices.groupby('ticker')}
    rows = []
    for row in cand.itertuples(index=False):
        s = price_groups.get(row.ticker)
        if s is None:
            continue
        w = s[(s['date'] >= row.date) & (s['date'] <= row.end_date)]
        if w.empty:
            continue
        entry = float(w['close'].iloc[0])
        rel = w['close'] / entry
        peak = rel.cummax()
        dd = rel / peak - 1.0
        rows.append({
            'date': row.date,
            'end_date': row.end_date,
            'horizon_weeks': int(row.horizon_weeks),
            'ticker': row.ticker,
            'selected': int(row.selected),
            'score': float(row.score) if pd.notna(row.score) else np.nan,
            'fwd_ret': float(rel.iloc[-1] - 1.0),
            'path_mdd': float(dd.min()),
        })
    return pd.DataFrame(rows)


def build_s2_candidates(runs, universe, prices):
    selected = read_sql(QS_DETAIL_DB, 'SELECT date, ticker FROM run_signal_details_s2 WHERE run_id=?', (runs['S2'],), parse_dates=['date'])
    selected['ticker'] = selected['ticker'].astype(str).str.zfill(6)
    f = read_sql(FUND_DB, 'SELECT date, ticker, growth_score, valid_fund FROM s2_fund_scores_monthly', parse_dates=['date'])
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)
    f['growth_score'] = pd.to_numeric(f['growth_score'], errors='coerce')
    f['valid_fund'] = pd.to_numeric(f['valid_fund'], errors='coerce').fillna(0).astype(int)
    out = []
    for h in HORIZONS:
        end_map = make_end_map(selected['date'].unique(), h)
        for d0, d1 in end_map.items():
            fund_date = f.loc[f['date'] <= d0, 'date'].max()
            if pd.isna(fund_date):
                continue
            snap = universe.merge(
                f[(f['date'] == fund_date) & (f['valid_fund'] == 1)][['ticker', 'growth_score']],
                on='ticker', how='inner'
            )
            sel_set = set(selected.loc[selected['date'] == d0, 'ticker'])
            snap['date'] = d0
            snap['end_date'] = d1
            snap['horizon_weeks'] = h
            snap['selected'] = snap['ticker'].isin(sel_set).astype(int)
            snap['score'] = snap['growth_score']
            out.append(snap[['date', 'end_date', 'horizon_weeks', 'ticker', 'selected', 'score']])
    cand = pd.concat(out, ignore_index=True)
    stats = compute_window_stats(cand, prices)
    stats['model_code'] = 'S2'
    return stats


def latest_fund_snapshot(fund_df, asof):
    w = fund_df[fund_df['available_from'] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(['ticker', 'available_from', 'date']).groupby('ticker', as_index=False).tail(1)


def build_s3_candidates(model_code, runs, universe, prices):
    table = 'run_signal_details_s3' if model_code == 'S3' else 'run_signal_details_s3_core2'
    selected = read_sql(QS_DETAIL_DB, f'SELECT date, ticker FROM {table} WHERE run_id=?', (runs[model_code],), parse_dates=['date'])
    selected['ticker'] = selected['ticker'].astype(str).str.zfill(6)
    p = read_sql(S3_DB, 'SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope FROM s3_price_features_daily', parse_dates=['date'])
    p['ticker'] = p['ticker'].astype(str).str.zfill(6)
    f = read_sql(S3_DB, 'SELECT date, ticker, available_from, growth_score, fund_accel_score FROM s3_fund_features_monthly', parse_dates=['date', 'available_from'])
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)
    out = []
    for h in HORIZONS:
        end_map = make_end_map(selected['date'].unique(), h)
        for d0, d1 in end_map.items():
            ps = p[p['date'] == d0].copy()
            fs = latest_fund_snapshot(f, d0)
            snap = universe.merge(ps, on='ticker', how='left').merge(fs[['ticker', 'growth_score', 'fund_accel_score']], on='ticker', how='left')
            snap['mom20_pct'] = snap['mom20'].rank(pct=True)
            snap['vol_ratio_pct'] = snap['vol_ratio_20'].rank(pct=True)
            snap['fund_level_pct'] = snap['growth_score'].rank(pct=True)
            snap['fund_accel_pct'] = snap['fund_accel_score'].rank(pct=True)
            if model_code == 'S3':
                trend_bonus = ((snap['ma60'] > snap['ma120']) & (snap['ma60_slope'] > 0)).astype(int)
                snap['score'] = (
                    0.30 * snap['fund_level_pct'].fillna(0)
                    + 0.20 * snap['fund_accel_pct'].fillna(0)
                    + 0.25 * snap['mom20_pct'].fillna(0)
                    + 0.10 * snap['vol_ratio_pct'].fillna(0)
                    + 0.05 * snap['breakout60'].fillna(0).astype(int)
                    + 0.10 * trend_bonus
                )
            else:
                snap['score'] = 0.60 * snap['mom20_pct'].fillna(0) + 0.40 * snap['vol_ratio_pct'].fillna(0)
            sel_set = set(selected.loc[selected['date'] == d0, 'ticker'])
            snap['date'] = d0
            snap['end_date'] = d1
            snap['horizon_weeks'] = h
            snap['selected'] = snap['ticker'].isin(sel_set).astype(int)
            out.append(snap[['date', 'end_date', 'horizon_weeks', 'ticker', 'selected', 'score']])
    cand = pd.concat(out, ignore_index=True)
    stats = compute_window_stats(cand, prices)
    stats['model_code'] = model_code
    return stats


def summarize(stats: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model_code, horizon_weeks, selected), g in stats.groupby(['model_code', 'horizon_weeks', 'selected']):
        rows.append({
            'model_code': model_code,
            'horizon': f'{horizon_weeks}W',
            'scope': 'selected_only' if selected == 1 else 'not_selected',
            'n_obs': int(len(g)),
            'avg_return': g['fwd_ret'].mean(),
            'median_return': g['fwd_ret'].median(),
            'avg_mdd': g['path_mdd'].mean(),
            'median_mdd': g['path_mdd'].median(),
        })
    return pd.DataFrame(rows).sort_values(['model_code', 'horizon', 'scope'])


def markdown_table(summary: pd.DataFrame) -> str:
    lines = ['# Selected vs Not Selected by Horizon', '']
    for model_code, g in summary.groupby('model_code'):
        lines.append(f'## {model_code}')
        lines.append('| Horizon | Scope | Avg Return | Avg MDD | Median Return | Median MDD | N |')
        lines.append('|---|---:|---:|---:|---:|---:|---:|')
        for r in g.itertuples(index=False):
            lines.append(f"| {r.horizon} | {r.scope} | {r.avg_return:.2%} | {r.avg_mdd:.2%} | {r.median_return:.2%} | {r.median_mdd:.2%} | {r.n_obs} |")
        lines.append('')
    return '\n'.join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    runs = latest_runs()
    universe = pd.read_csv(UNIVERSE_CSV, dtype={'ticker': str})[['ticker', 'name', 'market', 'mcap']]
    universe['ticker'] = universe['ticker'].astype(str).str.zfill(6)
    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])

    stats = pd.concat([
        build_s2_candidates(runs, universe, prices),
        build_s3_candidates('S3', runs, universe, prices),
        build_s3_candidates('S3_CORE2', runs, universe, prices),
    ], ignore_index=True)

    summary = summarize(stats)
    summary.to_csv(OUTDIR / 'selected_vs_not_selected_by_horizon_summary.csv', index=False, encoding='utf-8-sig')
    stats.to_csv(OUTDIR / 'selected_vs_not_selected_by_horizon_detail.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 'selected_vs_not_selected_by_horizon_review.md').write_text(markdown_table(summary), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
