from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\TOP_BUCKET_SNAPSHOTS_20251230_S3_ONLY"
SIGNAL_DATE = "2025-12-30"
SPECS = [
    ("Top3%", "universe_top_3pct_candidates", "top_3pct_flag", "s3_top3_snapshot_2025-12-30.csv"),
    ("Top10%", "universe_top_10pct_candidates", "top_10pct_flag", "s3_top10_snapshot_2025-12-30.csv"),
    ("Top30%", "universe_top_30pct_candidates", "top_30pct_flag", "s3_top30_snapshot_2025-12-30.csv"),
    ("Top50%", "universe_top_50pct_candidates", "top_50pct_flag", "s3_top50_snapshot_2025-12-30.csv"),
]


def read_sql(db: Path, query: str) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con)
    finally:
        con.close()


def load_snapshot(table: str, flag_col: str) -> pd.DataFrame:
    q = f"""
    SELECT model_code, horizon, signal_date, end_date, ticker, name, market,
           selected, score, fwd_ret, path_mdd, composite_score, {flag_col} AS top_flag
    FROM {table}
    WHERE model_code='S3'
      AND signal_date LIKE '{SIGNAL_DATE}%'
      AND {flag_col}=1
    ORDER BY composite_score DESC, ticker
    """
    df = read_sql(RESEARCH_DB, q)
    if df.empty:
        return df
    df['ticker'] = df['ticker'].astype(str).str.zfill(6)
    # defensive dedupe: keep the best composite row if any duplicate ticker exists
    df = df.sort_values(['composite_score', 'ticker'], ascending=[False, True]).drop_duplicates(subset=['ticker'], keep='first')
    return df


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    md = ['# S3-only Top Bucket Snapshot (2025-12-30)', '', 'S3 only, deduplicated by ticker.']
    for label, table, flag_col, filename in SPECS:
        df = load_snapshot(table, flag_col)
        df.to_csv(OUTDIR / filename, index=False, encoding='utf-8-sig')
        n = len(df)
        kospi = int((df['market'] == 'KOSPI').sum()) if not df.empty else 0
        kosdaq = int((df['market'] == 'KOSDAQ').sum()) if not df.empty else 0
        avg_ret = float(df['fwd_ret'].mean()) if not df.empty else float('nan')
        avg_mdd = float(df['path_mdd'].mean()) if not df.empty else float('nan')
        summary_rows.append({'bucket': label, 'n': n, 'kospi': kospi, 'kosdaq': kosdaq, 'avg_fwd_ret': avg_ret, 'avg_mdd': avg_mdd})
        md.append(f'## {label}')
        md.append(f'- n: `{n}`')
        md.append(f'- KOSPI: `{kospi}` / KOSDAQ: `{kosdaq}`')
        md.append(f'- avg forward return: `{avg_ret:.2%}`')
        md.append(f'- avg path MDD: `{avg_mdd:.2%}`')
        md.append('')
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTDIR / 's3_top_bucket_snapshot_summary_2025-12-30.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's3_top_bucket_snapshot_2025-12-30.md').write_text('\n'.join(md), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
