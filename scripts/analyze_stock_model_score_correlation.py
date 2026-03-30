from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review"


def _read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def _latest_runs() -> dict[str, str]:
    df = _read_sql(
        QS_DB,
        """
        SELECT model_code, run_id
        FROM (
          SELECT model_code, run_id, created_at,
                 ROW_NUMBER() OVER (PARTITION BY model_code ORDER BY created_at DESC) AS rn
          FROM run_runs
          WHERE model_code IN ('S2','S3','S3_CORE2')
        ) WHERE rn = 1
        """,
    )
    return dict(zip(df['model_code'], df['run_id']))


def _load_prices() -> pd.DataFrame:
    px = _read_sql(PRICE_DB, "SELECT ticker, date, close FROM prices_daily", parse_dates=['date'])
    px['ticker'] = px['ticker'].astype(str).str.zfill(6)
    px['close'] = pd.to_numeric(px['close'], errors='coerce')
    return px.sort_values(['ticker', 'date'])


def _forward_return(px: pd.DataFrame, signal_dates: list[pd.Timestamp]) -> pd.DataFrame:
    dates = sorted(pd.to_datetime(pd.Series(signal_dates).dropna().unique()))
    if len(dates) < 2:
        return pd.DataFrame(columns=['date', 'next_date', 'ticker', 'fwd_ret'])
    next_map = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}
    base = pd.DataFrame({'date': list(next_map.keys()), 'next_date': list(next_map.values())})
    out = []
    px = px.copy()
    for _, r in base.iterrows():
        p0 = px[px['date'] == r['date']][['ticker', 'close']].rename(columns={'close': 'close_t'})
        p1 = px[px['date'] == r['next_date']][['ticker', 'close']].rename(columns={'close': 'close_next'})
        m = p0.merge(p1, on='ticker', how='inner')
        m['date'] = r['date']
        m['next_date'] = r['next_date']
        m['fwd_ret'] = m['close_next'] / m['close_t'] - 1.0
        out.append(m[['date', 'next_date', 'ticker', 'fwd_ret']])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=['date', 'next_date', 'ticker', 'fwd_ret'])


def _summary_table(df: pd.DataFrame, score_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df[score_col] = pd.to_numeric(df[score_col], errors='coerce')
    df['fwd_ret'] = pd.to_numeric(df['fwd_ret'], errors='coerce')
    df = df[df[score_col].notna() & df['fwd_ret'].notna()].copy()
    rows = []
    for scope, sub in [('all_candidates', df), ('selected_only', df[df['selected'] == 1]), ('not_selected', df[df['selected'] == 0])]:
        if sub.empty:
            rows.append({'scope': scope, 'n_obs': 0})
            continue
        rows.append({
            'scope': scope,
            'n_obs': int(len(sub)),
            'n_dates': int(sub['date'].nunique()),
            'pearson_corr': sub[score_col].corr(sub['fwd_ret'], method='pearson'),
            'spearman_corr': sub[score_col].corr(sub['fwd_ret'], method='spearman'),
            'avg_fwd_ret': sub['fwd_ret'].mean(),
            'median_fwd_ret': sub['fwd_ret'].median(),
        })
    bucket_src = df.copy()
    if bucket_src[score_col].nunique() > 1:
        bucket_src['score_bucket'] = pd.qcut(bucket_src[score_col], q=5, duplicates='drop')
        bucket = bucket_src.groupby(['score_bucket', 'selected'], observed=False)['fwd_ret'].agg(['count', 'mean', 'median']).reset_index()
    else:
        bucket = pd.DataFrame()
    return pd.DataFrame(rows), bucket


def _s2_candidates(signal_dates: list[pd.Timestamp], px_fwd: pd.DataFrame, selected: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    u = pd.read_csv(UNIVERSE_CSV, dtype={'ticker': str})[['ticker', 'name', 'market']]
    u['ticker'] = u['ticker'].astype(str).str.zfill(6)
    f = _read_sql(FUND_DB, 'SELECT date, ticker, growth_score, score_rank, valid_fund FROM s2_fund_scores_monthly')
    f['date'] = pd.to_datetime(f['date'])
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)
    f['growth_score'] = pd.to_numeric(f['growth_score'], errors='coerce')
    f['score_rank'] = pd.to_numeric(f['score_rank'], errors='coerce')
    f['valid_fund'] = pd.to_numeric(f['valid_fund'], errors='coerce').fillna(0).astype(int)
    out = []
    for d in sorted(signal_dates):
        fund_date = f.loc[f['date'] <= d, 'date'].max()
        if pd.isna(fund_date):
            continue
        snap = f[(f['date'] == fund_date) & (f['valid_fund'] == 1)].copy()
        snap = u.merge(snap[['ticker', 'growth_score', 'score_rank']], on='ticker', how='inner')
        snap['date'] = d
        out.append(snap)
    cand = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=['date', 'ticker', 'growth_score'])
    cand = cand.merge(px_fwd, on=['date', 'ticker'], how='left')
    sel = selected[['date', 'ticker']].copy()
    sel['selected'] = 1
    cand = cand.merge(sel, on=['date', 'ticker'], how='left')
    cand['selected'] = cand['selected'].fillna(0).astype(int)
    return cand, 'growth_score'


def _pick_latest_fund_asof(fund_df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    work = fund_df[fund_df['available_from'] <= asof].copy()
    if work.empty:
        return work
    work = work.sort_values(['ticker', 'available_from', 'date']).groupby('ticker', as_index=False).tail(1)
    return work


def _s3_base_candidates(signal_dates: list[pd.Timestamp]) -> pd.DataFrame:
    u = pd.read_csv(UNIVERSE_CSV, dtype={'ticker': str})[['ticker', 'name', 'market', 'mcap']]
    u['ticker'] = u['ticker'].astype(str).str.zfill(6)
    p = _read_sql(S3_DB, 'SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope FROM s3_price_features_daily')
    p['ticker'] = p['ticker'].astype(str).str.zfill(6)
    p['date'] = pd.to_datetime(p['date'])
    f = _read_sql(S3_DB, 'SELECT date, ticker, available_from, growth_score, fund_accel_score FROM s3_fund_features_monthly')
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)
    f['date'] = pd.to_datetime(f['date'])
    f['available_from'] = pd.to_datetime(f['available_from'])
    rows = []
    for d in sorted(signal_dates):
        ps = p[p['date'] == d].copy()
        if ps.empty:
            continue
        fs = _pick_latest_fund_asof(f, d)
        snap = u.merge(ps, on='ticker', how='left').merge(fs[['ticker', 'growth_score', 'fund_accel_score']], on='ticker', how='left')
        snap['date'] = d
        rows.append(snap)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


def _s3_candidates(signal_dates: list[pd.Timestamp], px_fwd: pd.DataFrame, selected: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    cand = _s3_base_candidates(signal_dates)
    cand['fund_level_pct'] = cand.groupby('date')['growth_score'].transform(_pct_rank)
    cand['fund_accel_pct'] = cand.groupby('date')['fund_accel_score'].transform(_pct_rank)
    cand['mom20_pct'] = cand.groupby('date')['mom20'].transform(_pct_rank)
    cand['vol_ratio_pct'] = cand.groupby('date')['vol_ratio_20'].transform(_pct_rank)
    cand['breakout60'] = cand['breakout60'].fillna(0).astype(int)
    trend_bonus = ((cand['ma60'] > cand['ma120']) & (cand['ma60_slope'] > 0)).astype(int)
    cand['s3_score'] = (
        0.30 * cand['fund_level_pct'].fillna(0)
        + 0.20 * cand['fund_accel_pct'].fillna(0)
        + 0.25 * cand['mom20_pct'].fillna(0)
        + 0.10 * cand['vol_ratio_pct'].fillna(0)
        + 0.05 * cand['breakout60']
        + 0.10 * trend_bonus
    )
    cand = cand.merge(px_fwd, on=['date', 'ticker'], how='left')
    sel = selected[['date', 'ticker']].copy()
    sel['selected'] = 1
    cand = cand.merge(sel, on=['date', 'ticker'], how='left')
    cand['selected'] = cand['selected'].fillna(0).astype(int)
    return cand, 's3_score'


def _s3_core2_candidates(signal_dates: list[pd.Timestamp], px_fwd: pd.DataFrame, selected: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    cand = _s3_base_candidates(signal_dates)
    cand['mom20_pct'] = cand.groupby('date')['mom20'].transform(_pct_rank)
    cand['vol_ratio_pct'] = cand.groupby('date')['vol_ratio_20'].transform(_pct_rank)
    cand['fund_level_pct'] = cand.groupby('date')['growth_score'].transform(_pct_rank)
    cand['fund_accel_pct'] = cand.groupby('date')['fund_accel_score'].transform(_pct_rank)
    cand['core_score'] = 0.60 * cand['mom20_pct'].fillna(0) + 0.40 * cand['vol_ratio_pct'].fillna(0)
    cand['tie_score'] = 0.002 * cand['fund_level_pct'].fillna(0.5) + 0.001 * cand['fund_accel_pct'].fillna(0.5)
    cand['s3_score'] = cand['core_score'] + cand['tie_score']
    cand = cand.merge(px_fwd, on=['date', 'ticker'], how='left')
    sel = selected[['date', 'ticker']].copy()
    sel['selected'] = 1
    cand = cand.merge(sel, on=['date', 'ticker'], how='left')
    cand['selected'] = cand['selected'].fillna(0).astype(int)
    return cand, 'core_score'


def main(asof: str = '2026-03-30') -> None:
    runs = _latest_runs()
    prices = _load_prices()
    outdir = OUTDIR / asof.replace('-', '')
    outdir.mkdir(parents=True, exist_ok=True)
    model_builders = {
        'S2': _s2_candidates,
        'S3': _s3_candidates,
        'S3_CORE2': _s3_core2_candidates,
    }
    all_summary = []
    report_lines = ['# Stock Model Score vs Forward Return', '']
    signal_table_map = {
        'S2': 'run_signal_details_s2',
        'S3': 'run_signal_details_s3',
        'S3_CORE2': 'run_signal_details_s3_core2',
    }
    for model_code, builder in model_builders.items():
        selected = _read_sql(
            QS_DETAIL_DB,
            f"SELECT date, ticker FROM {signal_table_map[model_code]} WHERE run_id=?",
            params=(runs[model_code],),
            parse_dates=['date'],
        )
        if selected.empty:
            continue
        selected['ticker'] = selected['ticker'].astype(str).str.zfill(6)
        signal_dates = sorted(selected['date'].dropna().unique())
        px_fwd = _forward_return(prices, signal_dates)
        cand, score_col = builder(signal_dates, px_fwd, selected)
        summary, bucket = _summary_table(cand, score_col)
        summary.insert(0, 'model_code', model_code)
        summary.insert(1, 'score_col', score_col)
        all_summary.append(summary)
        cand.to_csv(outdir / f'{model_code.lower()}_candidate_score_forward_returns.csv', index=False, encoding='utf-8-sig')
        bucket.to_csv(outdir / f'{model_code.lower()}_bucket_summary.csv', index=False, encoding='utf-8-sig')
        report_lines.append(f'## {model_code}')
        report_lines.append(f'- score column: `{score_col}`')
        for row in summary.to_dict('records'):
            report_lines.append(
                f"- {row['scope']}: n={row.get('n_obs', 0)}, pearson={row.get('pearson_corr')}, spearman={row.get('spearman_corr')}, avg_fwd_ret={row.get('avg_fwd_ret')}"
            )
        report_lines.append('')
    if all_summary:
        pd.concat(all_summary, ignore_index=True).to_csv(outdir / 'model_score_correlation_summary.csv', index=False, encoding='utf-8-sig')
    (outdir / 'model_score_correlation_review.md').write_text('\n'.join(report_lines), encoding='utf-8')
    print(f'[OK] wrote {outdir}')


if __name__ == '__main__':
    main()
