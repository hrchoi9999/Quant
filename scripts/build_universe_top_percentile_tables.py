
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
DETAIL_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260330\selected_vs_not_selected_3m_6m_1y_detail.csv"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
OUT_DB = PROJECT_ROOT / r"data\db\model_research.db"

SPECS = [
    (0.97, 'top_3pct', 'universe_top_3pct_candidates', 'universe_top_3pct_summary'),
    (0.90, 'top_10pct', 'universe_top_10pct_candidates', 'universe_top_10pct_summary'),
    (0.70, 'top_30pct', 'universe_top_30pct_candidates', 'universe_top_30pct_summary'),
    (0.50, 'top_50pct', 'universe_top_50pct_candidates', 'universe_top_50pct_summary'),
]

BAND_SPECS = [
    ('top_0_10pct', 0.90, None, 'universe_top_0_10pct_candidates', 'universe_top_0_10pct_summary'),
    ('top_10_30pct', 0.70, 0.90, 'universe_top_10_30pct_candidates', 'universe_top_10_30pct_summary'),
    ('top_30_50pct', 0.50, 0.70, 'universe_top_30_50pct_candidates', 'universe_top_30_50pct_summary'),
    ('top_50_100pct', None, 0.50, 'universe_top_50_100pct_candidates', 'universe_top_50_100pct_summary'),
]


def read_sql(db: Path, query: str) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con)
    finally:
        con.close()


def build_bucket(detail: pd.DataFrame, q: float, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = detail.copy()
    threshold_col = f'{label}_threshold'
    flag_col = f'{label}_flag'
    rank_col = f'{label}_rank'
    work[threshold_col] = work.groupby(['model_code', 'horizon', 'signal_date'])['composite_score'].transform(lambda s: s.quantile(q))
    work[flag_col] = (work['composite_score'] >= work[threshold_col]).astype(int)
    work[rank_col] = work.groupby(['model_code', 'horizon', 'signal_date'])['composite_score'].rank(method='first', ascending=False)
    work['top_bucket_label'] = label
    summary = (
        work[work[flag_col] == 1]
        .groupby(['model_code', 'horizon', 'ticker', 'name', 'market'], as_index=False)
        .agg(
            top_observations=('ticker', 'size'),
            avg_fwd_ret=('fwd_ret', 'mean'),
            avg_path_mdd=('path_mdd', 'mean'),
            selected_hit_rate=('selected', 'mean'),
            avg_composite_score=('composite_score', 'mean'),
        )
        .sort_values(['model_code', 'horizon', 'top_observations', 'avg_composite_score'], ascending=[True, True, False, False])
    )
    summary['top_bucket_label'] = label
    return work, summary


def build_band(detail: pd.DataFrame, label: str, lower_q: float | None, upper_q: float | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = detail.copy()
    grp = ['model_code', 'horizon', 'signal_date']
    rank_col = f'{label}_rank'
    flag_col = f'{label}_flag'

    if upper_q is not None:
        upper_col = f'{label}_upper_threshold'
        work[upper_col] = work.groupby(grp)['composite_score'].transform(lambda s: s.quantile(upper_q))
    else:
        upper_col = None

    if lower_q is not None:
        lower_col = f'{label}_lower_threshold'
        work[lower_col] = work.groupby(grp)['composite_score'].transform(lambda s: s.quantile(lower_q))
    else:
        lower_col = None

    flag = pd.Series(True, index=work.index)
    if lower_col is not None:
        flag &= work['composite_score'] >= work[lower_col]
    if upper_col is not None:
        flag &= work['composite_score'] < work[upper_col]

    work[flag_col] = flag.astype(int)
    work[rank_col] = work.groupby(grp)['composite_score'].rank(method='first', ascending=False)
    work['top_bucket_label'] = label

    summary = (
        work[work[flag_col] == 1]
        .groupby(['model_code', 'horizon', 'ticker', 'name', 'market'], as_index=False)
        .agg(
            top_observations=('ticker', 'size'),
            avg_fwd_ret=('fwd_ret', 'mean'),
            avg_path_mdd=('path_mdd', 'mean'),
            selected_hit_rate=('selected', 'mean'),
            avg_composite_score=('composite_score', 'mean'),
        )
        .sort_values(['model_code', 'horizon', 'top_observations', 'avg_composite_score'], ascending=[True, True, False, False])
    )
    summary['top_bucket_label'] = label
    return work, summary


def main() -> None:
    detail = pd.read_csv(DETAIL_CSV, parse_dates=['date', 'end_date'])
    detail = detail.rename(columns={'date': 'signal_date'})
    detail['ticker'] = detail['ticker'].astype(str).str.zfill(6)
    names = read_sql(PRICE_DB, 'SELECT ticker, name, market FROM instrument_master')
    names['ticker'] = names['ticker'].astype(str).str.zfill(6)
    detail = detail.merge(names[['ticker', 'name', 'market']], on='ticker', how='left', suffixes=('', '_master'))
    if 'name_master' in detail.columns:
        detail['name'] = detail['name'].fillna(detail['name_master'])
        detail = detail.drop(columns=['name_master'])
    if 'market_master' in detail.columns:
        detail['market'] = detail['market'].fillna(detail['market_master'])
        detail = detail.drop(columns=['market_master'])

    detail['return_pct_rank'] = detail.groupby(['model_code', 'horizon', 'signal_date'])['fwd_ret'].rank(pct=True, ascending=True)
    detail['mdd_pct_rank'] = detail.groupby(['model_code', 'horizon', 'signal_date'])['path_mdd'].rank(pct=True, ascending=True)
    detail['composite_score'] = 0.7 * detail['return_pct_rank'] + 0.3 * detail['mdd_pct_rank']

    con = sqlite3.connect(str(OUT_DB))
    try:
        for q, label, cand_tbl, sum_tbl in SPECS:
            cand, summ = build_bucket(detail, q, label)
            cand.to_sql(cand_tbl, con, if_exists='replace', index=False)
            summ.to_sql(sum_tbl, con, if_exists='replace', index=False)
            top_rows = int(cand.filter(like=f'{label}_flag').iloc[:, 0].sum())
            print(f'[ok] {label}: candidate_rows={len(cand)} top_rows={top_rows} summary_rows={len(summ)}')
        for label, lower_q, upper_q, cand_tbl, sum_tbl in BAND_SPECS:
            cand, summ = build_band(detail, label, lower_q, upper_q)
            cand.to_sql(cand_tbl, con, if_exists='replace', index=False)
            summ.to_sql(sum_tbl, con, if_exists='replace', index=False)
            band_rows = int(cand.filter(like=f'{label}_flag').iloc[:, 0].sum())
            print(f'[ok] {label}: candidate_rows={len(cand)} band_rows={band_rows} summary_rows={len(summ)}')
    finally:
        con.close()


if __name__ == '__main__':
    main()
