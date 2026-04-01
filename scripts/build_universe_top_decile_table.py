from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
DETAIL_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260330\selected_vs_not_selected_3m_6m_1y_detail.csv"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
OUT_DB = PROJECT_ROOT / r"data\db\model_research.db"
TOP_PERCENTILE = 0.97
TOP_LABEL = "top_3pct"
CANDIDATE_TABLE = "universe_top_3pct_candidates"
SUMMARY_TABLE = "universe_top_3pct_summary"


def read_sql(db: Path, query: str) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con)
    finally:
        con.close()


def main() -> None:
    detail = pd.read_csv(DETAIL_CSV, parse_dates=['date', 'end_date'])
    detail['ticker'] = detail['ticker'].astype(str).str.zfill(6)
    names = read_sql(PRICE_DB, 'SELECT ticker, name, market FROM instrument_master')
    names['ticker'] = names['ticker'].astype(str).str.zfill(6)
    detail = detail.merge(names[['ticker', 'name', 'market']], on='ticker', how='left')

    detail['return_pct_rank'] = detail.groupby(['model_code', 'horizon', 'date'])['fwd_ret'].rank(pct=True, ascending=True)
    detail['mdd_pct_rank'] = detail.groupby(['model_code', 'horizon', 'date'])['path_mdd'].rank(pct=True, ascending=True)
    detail['composite_score'] = 0.7 * detail['return_pct_rank'] + 0.3 * detail['mdd_pct_rank']
    detail['top_threshold'] = detail.groupby(['model_code', 'horizon', 'date'])['composite_score'].transform(lambda s: s.quantile(TOP_PERCENTILE))
    detail['top_flag'] = (detail['composite_score'] >= detail['top_threshold']).astype(int)
    detail['top_rank'] = detail.groupby(['model_code', 'horizon', 'date'])['composite_score'].rank(method='first', ascending=False)
    detail['top_bucket_label'] = TOP_LABEL
    detail = detail.rename(columns={'date': 'signal_date'})

    summary = (
        detail[detail['top_flag'] == 1]
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
    summary['top_bucket_label'] = TOP_LABEL

    con = sqlite3.connect(str(OUT_DB))
    try:
        detail.to_sql(CANDIDATE_TABLE, con, if_exists='replace', index=False)
        summary.to_sql(SUMMARY_TABLE, con, if_exists='replace', index=False)
    finally:
        con.close()

    print(f'[ok] {TOP_LABEL} tables built')
    print(f'candidate_rows={len(detail)} top_rows={int(detail["top_flag"].sum())} summary_rows={len(summary)}')


if __name__ == '__main__':
    main()
