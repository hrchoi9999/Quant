from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_BUCKET_CAPTURE_ANALYSIS"


def read_sql(query: str, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        return pd.read_sql_query(query, con, parse_dates=parse_dates)
    finally:
        con.close()


def load_panel() -> pd.DataFrame:
    base = read_sql(
        """
        SELECT model_code, horizon, signal_date, end_date, ticker, name, market,
               selected, fwd_ret, path_mdd, top_50pct_flag
        FROM universe_top_50pct_candidates
        WHERE model_code='S3'
        """,
        parse_dates=['signal_date', 'end_date'],
    )
    t3 = read_sql(
        "SELECT model_code, horizon, signal_date, end_date, ticker, top_3pct_flag FROM universe_top_3pct_candidates WHERE model_code='S3'",
        parse_dates=['signal_date', 'end_date'],
    )
    t10 = read_sql(
        "SELECT model_code, horizon, signal_date, end_date, ticker, top_10pct_flag FROM universe_top_10pct_candidates WHERE model_code='S3'",
        parse_dates=['signal_date', 'end_date'],
    )
    t30 = read_sql(
        "SELECT model_code, horizon, signal_date, end_date, ticker, top_30pct_flag FROM universe_top_30pct_candidates WHERE model_code='S3'",
        parse_dates=['signal_date', 'end_date'],
    )

    for df in [base, t3, t10, t30]:
        df['ticker'] = df['ticker'].astype(str).str.zfill(6)

    keys = ['model_code', 'horizon', 'signal_date', 'end_date', 'ticker']
    panel = base.merge(t3, on=keys, how='left').merge(t10, on=keys, how='left').merge(t30, on=keys, how='left')
    for c in ['top_3pct_flag', 'top_10pct_flag', 'top_30pct_flag', 'top_50pct_flag', 'selected']:
        panel[c] = pd.to_numeric(panel[c], errors='coerce').fillna(0).astype(int)

    panel['bucket'] = None
    panel.loc[panel['top_3pct_flag'] == 1, 'bucket'] = 'T3'
    panel.loc[(panel['top_10pct_flag'] == 1) & (panel['top_3pct_flag'] == 0), 'bucket'] = 'T10_ex_T3'
    panel.loc[(panel['top_30pct_flag'] == 1) & (panel['top_10pct_flag'] == 0), 'bucket'] = 'T30_ex_T10'
    panel.loc[(panel['top_50pct_flag'] == 1) & (panel['top_30pct_flag'] == 0), 'bucket'] = 'T50_ex_T30'
    panel = panel[panel['bucket'].notna()].copy()
    return panel


def summarize(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    by_h_rows = []
    for horizon, hg in panel.groupby('horizon'):
        base_sel_rate = float(hg['selected'].mean())
        for bucket, g in hg.groupby('bucket'):
            capture_rate = float(g['selected'].mean())
            captured = g[g['selected'] == 1]
            uncaptured = g[g['selected'] == 0]
            by_h_rows.append({
                'horizon': horizon,
                'bucket': bucket,
                'obs_count': int(len(g)),
                'unique_tickers': int(g['ticker'].nunique()),
                'captured_obs': int(captured.shape[0]),
                'capture_rate': capture_rate,
                'base_selection_rate': base_sel_rate,
                'capture_lift_vs_base': float(capture_rate / base_sel_rate) if base_sel_rate > 0 else None,
                'captured_avg_fwd_ret': float(captured['fwd_ret'].mean()) if not captured.empty else None,
                'uncaptured_avg_fwd_ret': float(uncaptured['fwd_ret'].mean()) if not uncaptured.empty else None,
                'captured_avg_mdd': float(captured['path_mdd'].mean()) if not captured.empty else None,
                'uncaptured_avg_mdd': float(uncaptured['path_mdd'].mean()) if not uncaptured.empty else None,
            })

    overall_base_sel_rate = float(panel['selected'].mean())
    for bucket, g in panel.groupby('bucket'):
        captured = g[g['selected'] == 1]
        uncaptured = g[g['selected'] == 0]
        capture_rate = float(g['selected'].mean())
        rows.append({
            'bucket': bucket,
            'obs_count': int(len(g)),
            'unique_tickers': int(g['ticker'].nunique()),
            'captured_obs': int(captured.shape[0]),
            'capture_rate': capture_rate,
            'base_selection_rate': overall_base_sel_rate,
            'capture_lift_vs_base': float(capture_rate / overall_base_sel_rate) if overall_base_sel_rate > 0 else None,
            'captured_avg_fwd_ret': float(captured['fwd_ret'].mean()) if not captured.empty else None,
            'uncaptured_avg_fwd_ret': float(uncaptured['fwd_ret'].mean()) if not uncaptured.empty else None,
            'captured_avg_mdd': float(captured['path_mdd'].mean()) if not captured.empty else None,
            'uncaptured_avg_mdd': float(uncaptured['path_mdd'].mean()) if not uncaptured.empty else None,
        })
    return pd.DataFrame(rows), pd.DataFrame(by_h_rows)


def render_md(overall: pd.DataFrame, by_h: pd.DataFrame) -> str:
    order = ['T3', 'T10_ex_T3', 'T30_ex_T10', 'T50_ex_T30']
    overall['bucket'] = pd.Categorical(overall['bucket'], categories=order, ordered=True)
    by_h['bucket'] = pd.Categorical(by_h['bucket'], categories=order, ordered=True)
    lines = ['# S3 Bucket Capture Accuracy', '']
    lines.append('S3 selected-vs-bucket capture analysis using exclusive future-performance buckets.')
    lines.append('')
    lines.append('## Overall')
    lines.append('| Bucket | Obs | Unique Tickers | Captured Obs | Capture Rate | Lift vs Base | Captured Avg Return | Uncaptured Avg Return | Captured Avg MDD | Uncaptured Avg MDD |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for r in overall.sort_values('bucket').itertuples(index=False):
        lines.append(f'| {r.bucket} | {r.obs_count} | {r.unique_tickers} | {r.captured_obs} | {r.capture_rate:.2%} | {r.capture_lift_vs_base:.2f}x | {r.captured_avg_fwd_ret:.2%} | {r.uncaptured_avg_fwd_ret:.2%} | {r.captured_avg_mdd:.2%} | {r.uncaptured_avg_mdd:.2%} |')
    lines.append('')
    lines.append('## By Horizon')
    lines.append('| Horizon | Bucket | Capture Rate | Lift vs Base | Captured Avg Return | Uncaptured Avg Return | Captured Avg MDD | Uncaptured Avg MDD |')
    lines.append('|---|---|---:|---:|---:|---:|---:|---:|')
    horizon_order = {'3M': 0, '6M': 1, '1Y': 2}
    by_h['horizon_sort'] = by_h['horizon'].map(horizon_order)
    for r in by_h.sort_values(['horizon_sort', 'bucket']).itertuples(index=False):
        lines.append(f'| {r.horizon} | {r.bucket} | {r.capture_rate:.2%} | {r.capture_lift_vs_base:.2f}x | {r.captured_avg_fwd_ret:.2%} | {r.uncaptured_avg_fwd_ret:.2%} | {r.captured_avg_mdd:.2%} | {r.uncaptured_avg_mdd:.2%} |')
    lines.append('')
    return '\n'.join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    panel = load_panel()
    overall, by_h = summarize(panel)
    panel.to_csv(OUTDIR / 's3_bucket_capture_panel.csv', index=False, encoding='utf-8-sig')
    overall.to_csv(OUTDIR / 's3_bucket_capture_overall.csv', index=False, encoding='utf-8-sig')
    by_h.to_csv(OUTDIR / 's3_bucket_capture_by_horizon.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's3_bucket_capture_accuracy.md').write_text(render_md(overall, by_h), encoding='utf-8')
    print('OVERALL')
    print(overall.to_string(index=False))
    print('\nBY_HORIZON')
    print(by_h.sort_values(['horizon','bucket']).to_string(index=False))


if __name__ == '__main__':
    main()
