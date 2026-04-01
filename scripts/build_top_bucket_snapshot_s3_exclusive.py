from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\TOP_BUCKET_SNAPSHOTS_20251230_S3_EXCLUSIVE"
SIGNAL_DATE = "2025-12-30"


def read_sql(query: str) -> pd.DataFrame:
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        return pd.read_sql_query(query, con)
    finally:
        con.close()


def load_bucket(table: str, flag_col: str) -> pd.DataFrame:
    q = f"""
    SELECT model_code, horizon, signal_date, end_date, ticker, name, market,
           selected, score, fwd_ret, path_mdd, composite_score, {flag_col} AS top_flag
    FROM {table}
    WHERE model_code='S3'
      AND signal_date LIKE '{SIGNAL_DATE}%'
      AND {flag_col}=1
    ORDER BY composite_score DESC, ticker
    """
    df = read_sql(q)
    if df.empty:
        return df
    df['ticker'] = df['ticker'].astype(str).str.zfill(6)
    return df.sort_values(['composite_score', 'ticker'], ascending=[False, True]).drop_duplicates(subset=['ticker'], keep='first')


def write_snapshot(df: pd.DataFrame, path: Path) -> dict:
    df.to_csv(path, index=False, encoding='utf-8-sig')
    return {
        'n': len(df),
        'kospi': int((df['market'] == 'KOSPI').sum()) if not df.empty else 0,
        'kosdaq': int((df['market'] == 'KOSDAQ').sum()) if not df.empty else 0,
        'avg_fwd_ret': float(df['fwd_ret'].mean()) if not df.empty else float('nan'),
        'median_fwd_ret': float(df['fwd_ret'].median()) if not df.empty else float('nan'),
        'avg_mdd': float(df['path_mdd'].mean()) if not df.empty else float('nan'),
        'median_mdd': float(df['path_mdd'].median()) if not df.empty else float('nan'),
    }


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    top3 = load_bucket('universe_top_3pct_candidates', 'top_3pct_flag')
    top10 = load_bucket('universe_top_10pct_candidates', 'top_10pct_flag')
    top30 = load_bucket('universe_top_30pct_candidates', 'top_30pct_flag')
    top50 = load_bucket('universe_top_50pct_candidates', 'top_50pct_flag')

    t3_set = set(top3['ticker'])
    t10_set = set(top10['ticker'])
    t30_set = set(top30['ticker'])

    top10_ex_t3 = top10[~top10['ticker'].isin(t3_set)].copy()
    top30_ex_t10 = top30[~top30['ticker'].isin(t10_set)].copy()
    top50_ex_t30 = top50[~top50['ticker'].isin(t30_set)].copy()

    specs = [
        ('T3', top3, 's3_t3_snapshot_2025-12-30.csv'),
        ('T10_ex_T3', top10_ex_t3, 's3_t10_ex_t3_snapshot_2025-12-30.csv'),
        ('T30_ex_T10', top30_ex_t10, 's3_t30_ex_t10_snapshot_2025-12-30.csv'),
        ('T50_ex_T30', top50_ex_t30, 's3_t50_ex_t30_snapshot_2025-12-30.csv'),
    ]

    summary_rows = []
    md = ['# S3 Exclusive Top Bucket Snapshot (2025-12-30)', '', 'S3 only, deduplicated by ticker, with nested upper buckets excluded from lower buckets.', '']

    for label, df, filename in specs:
        stats = write_snapshot(df, OUTDIR / filename)
        row = {'bucket': label, **stats}
        summary_rows.append(row)
        md.append(f'## {label}')
        md.append(f'- n: `{stats["n"]}`')
        md.append(f'- KOSPI: `{stats["kospi"]}` / KOSDAQ: `{stats["kosdaq"]}`')
        md.append(f'- avg forward return: `{stats["avg_fwd_ret"]:.2%}`')
        md.append(f'- median forward return: `{stats["median_fwd_ret"]:.2%}`')
        md.append(f'- avg path MDD: `{stats["avg_mdd"]:.2%}`')
        md.append(f'- median path MDD: `{stats["median_mdd"]:.2%}`')
        md.append('')

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTDIR / 's3_exclusive_top_bucket_snapshot_summary_2025-12-30.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's3_exclusive_top_bucket_snapshot_2025-12-30.md').write_text('\n'.join(md), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
