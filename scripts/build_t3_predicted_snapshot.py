from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\T3_PREDICTED_SNAPSHOT_20260326"
ASOF_DATE = pd.Timestamp("2026-03-26")
TOP_SPECS = [("top3", 0.03), ("top10", 0.10), ("top30", 0.30), ("top50", 0.50)]


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def latest_fund_snapshot(fund_df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    w = fund_df[fund_df['available_from'] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(['ticker', 'available_from']).groupby('ticker', as_index=False).tail(1)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(UNIVERSE_CSV, dtype={'ticker': str})[['ticker', 'name', 'market', 'mcap']]
    universe['ticker'] = universe['ticker'].astype(str).str.zfill(6)

    p = read_sql(S3_DB, 'SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120 FROM s3_price_features_daily', parse_dates=['date'])
    p['ticker'] = p['ticker'].astype(str).str.zfill(6)
    p['date'] = pd.to_datetime(p['date'])
    latest_price_date = pd.to_datetime(p.loc[p['date'] <= ASOF_DATE, 'date'].max())
    p_row = p[p['date'] == latest_price_date].copy()

    f = read_sql(S3_DB, 'SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly', parse_dates=['available_from'])
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)
    latest_fund = latest_fund_snapshot(f, ASOF_DATE)
    latest_fund_date = pd.to_datetime(latest_fund['available_from'].max()) if not latest_fund.empty else pd.NaT

    snap = universe.merge(p_row, on='ticker', how='left', suffixes=('', '_px')).merge(
        latest_fund[['ticker', 'available_from', 'fund_accel_score', 'gs_delta_3m', 'rev_delta_3m', 'op_delta_3m']],
        on='ticker', how='left'
    )
    snap['dist_ma60'] = snap['close'] / snap['ma60'] - 1.0
    snap['ma_stack_gap'] = snap['ma60'] / snap['ma120'] - 1.0
    for c in ['rev_delta_3m', 'op_delta_3m', 'fund_accel_score', 'ma_stack_gap', 'mom20', 'dist_ma60']:
        snap[c] = pd.to_numeric(snap[c], errors='coerce')
    snap['rev_delta_3m_pct'] = snap['rev_delta_3m'].rank(pct=True)
    snap['op_delta_3m_pct'] = snap['op_delta_3m'].rank(pct=True)
    snap['fund_accel_score_pct'] = snap['fund_accel_score'].rank(pct=True)
    snap['ma_stack_gap_pct'] = snap['ma_stack_gap'].rank(pct=True)
    snap['mom20_pct'] = snap['mom20'].rank(pct=True)
    snap['dist_ma60_pct'] = snap['dist_ma60'].rank(pct=True)
    snap['t3_positive_score'] = snap[['rev_delta_3m_pct', 'op_delta_3m_pct', 'fund_accel_score_pct', 'ma_stack_gap_pct']].mean(axis=1, skipna=True)
    snap['t3_crowded_score'] = snap[['mom20_pct', 'dist_ma60_pct']].mean(axis=1, skipna=True)
    snap['t3_model_score'] = snap['t3_positive_score'] - 0.35 * snap['t3_crowded_score'] - 0.05 * pd.to_numeric(snap['breakout60'], errors='coerce').fillna(0).astype(float)
    snap = snap.dropna(subset=['t3_model_score']).copy()
    snap['t3_model_rank'] = snap['t3_model_score'].rank(method='first', ascending=False)
    snap['t3_model_score_pct'] = snap['t3_model_score'].rank(pct=True)
    snap['asof_date'] = ASOF_DATE
    snap['price_feature_date'] = latest_price_date
    snap['fund_snapshot_date'] = latest_fund_date

    base_cols = [
        'asof_date', 'price_feature_date', 'fund_snapshot_date', 'ticker', 'name', 'market', 'mcap',
        't3_model_rank', 't3_model_score', 't3_model_score_pct', 't3_positive_score', 't3_crowded_score',
        'rev_delta_3m', 'op_delta_3m', 'fund_accel_score', 'ma_stack_gap', 'mom20', 'dist_ma60',
        'breakout60'
    ]
    snap[base_cols].sort_values(['t3_model_rank', 'ticker']).to_csv(OUTDIR / 't3_predicted_full_rank_2026-03-26.csv', index=False, encoding='utf-8-sig')

    summary_rows = []
    for label, pct in TOP_SPECS:
        n = max(1, int(round(len(snap) * pct)))
        top = snap.sort_values(['t3_model_rank', 'ticker']).head(n).copy()
        top['predicted_bucket'] = label
        top[base_cols + ['predicted_bucket']].to_csv(OUTDIR / f'{label}_predicted_snapshot_2026-03-26.csv', index=False, encoding='utf-8-sig')
        by_market = top.groupby('market').size().to_dict()
        summary_rows.append({
            'bucket': label,
            'n': len(top),
            'kospi': int(by_market.get('KOSPI', 0)),
            'kosdaq': int(by_market.get('KOSDAQ', 0)),
            'avg_t3_score': float(top['t3_model_score'].mean()),
            'min_rank': int(top['t3_model_rank'].min()),
            'max_rank': int(top['t3_model_rank'].max()),
        })

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTDIR / 't3_predicted_snapshot_summary_2026-03-26.csv', index=False, encoding='utf-8-sig')

    lines = ['# T3 Predicted Snapshot (2026-03-26)', '']
    lines.append(f'- asof_date: `{ASOF_DATE.date()}`')
    lines.append(f'- price_feature_date_used: `{latest_price_date.date()}`')
    lines.append(f'- fund_snapshot_date_used: `{latest_fund_date.date() if pd.notna(latest_fund_date) else "NA"}`')
    lines.append(f'- universe_size_scored: `{len(snap)}`')
    lines.append('')
    lines.append('| Bucket | N | KOSPI | KOSDAQ | Avg T3 Score | Rank Range |')
    lines.append('|---|---:|---:|---:|---:|---|')
    for r in summary.itertuples(index=False):
        lines.append(f'| {r.bucket} | {r.n} | {r.kospi} | {r.kosdaq} | {r.avg_t3_score:.4f} | {r.min_rank}~{r.max_rank} |')
    (OUTDIR / 't3_predicted_snapshot_2026-03-26.md').write_text('\n'.join(lines), encoding='utf-8')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
