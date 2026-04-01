
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\T3_MODEL_FILTER_ANALYSIS"
BASE_DETAIL_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260330\selected_vs_not_selected_3m_6m_1y_detail.csv"

TARGET_SPECS = [
    ('top_10pct', 'universe_top_10pct_candidates', 'top_10pct_flag'),
    ('top_30pct', 'universe_top_30pct_candidates', 'top_30pct_flag'),
    ('top_50pct', 'universe_top_50pct_candidates', 'top_50pct_flag'),
]
FILTER_SPECS = [('t3_top_10pct', 0.90), ('t3_top_30pct', 0.70), ('t3_top_50pct', 0.50)]


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def latest_fund_snapshot(fund_df: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    out = []
    for ticker, g in panel[['ticker', 'signal_date']].drop_duplicates().sort_values(['ticker', 'signal_date']).groupby('ticker'):
        left = g.sort_values('signal_date')
        right = fund_df[fund_df['ticker'] == ticker].sort_values('available_from')
        if right.empty:
            left = left.copy()
            left['fund_accel_score'] = np.nan
            left['gs_delta_3m'] = np.nan
            left['rev_delta_3m'] = np.nan
            left['op_delta_3m'] = np.nan
            out.append(left)
            continue
        merged = pd.merge_asof(
            left,
            right[['available_from', 'fund_accel_score', 'gs_delta_3m', 'rev_delta_3m', 'op_delta_3m']].rename(columns={'available_from': 'asof_fund_date'}),
            left_on='signal_date',
            right_on='asof_fund_date',
            direction='backward',
            allow_exact_matches=True,
        )
        out.append(merged)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=['ticker', 'signal_date'])


def add_pct_ranks(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    grp = ['model_code', 'horizon', 'signal_date']
    pct_cols = [
        'revenue_yoy', 'op_income_yoy', 'fund_accel_score', 'rev_delta_3m', 'op_delta_3m', 'ma_stack_gap',
        'mom20', 'dist_ma60'
    ]
    for feat in pct_cols:
        if feat in panel.columns:
            panel[f'{feat}_pct'] = panel.groupby(grp)[feat].rank(pct=True)
    return panel


def build_panel() -> pd.DataFrame:
    base = pd.read_csv(BASE_DETAIL_CSV, parse_dates=['date', 'end_date'])
    base = base.rename(columns={'date': 'signal_date'})
    base['ticker'] = base['ticker'].astype(str).str.zfill(6)
    names = read_sql(PRICE_DB, 'SELECT ticker, name, market FROM instrument_master')
    names['ticker'] = names['ticker'].astype(str).str.zfill(6)
    base = base.merge(names[['ticker','name','market']], on='ticker', how='left')

    s2 = read_sql(FUND_DB, 'SELECT date, ticker, growth_score, revenue_yoy, op_income_yoy, score_rank FROM s2_fund_scores_monthly', parse_dates=['date'])
    s2['ticker'] = s2['ticker'].astype(str).str.zfill(6)
    s3p = read_sql(S3_DB, 'SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120 FROM s3_price_features_daily', parse_dates=['date'])
    s3p['ticker'] = s3p['ticker'].astype(str).str.zfill(6)
    s3f = read_sql(S3_DB, 'SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly', parse_dates=['available_from'])
    s3f['ticker'] = s3f['ticker'].astype(str).str.zfill(6)

    panel = base.merge(s2, left_on=['signal_date', 'ticker'], right_on=['date', 'ticker'], how='left').drop(columns=['date'])
    panel = panel.merge(s3p, left_on=['signal_date', 'ticker'], right_on=['date', 'ticker'], how='left').drop(columns=['date'])
    latest_fund = latest_fund_snapshot(s3f, panel)
    panel = panel.merge(latest_fund, on=['ticker', 'signal_date'], how='left')
    panel['dist_ma60'] = panel['close'] / panel['ma60'] - 1.0
    panel['ma_stack_gap'] = panel['ma60'] / panel['ma120'] - 1.0
    panel = add_pct_ranks(panel)

    pos = panel[[
        'revenue_yoy_pct', 'op_income_yoy_pct', 'fund_accel_score_pct', 'rev_delta_3m_pct', 'op_delta_3m_pct', 'ma_stack_gap_pct'
    ]].mean(axis=1, skipna=True)
    neg = panel[['mom20_pct', 'dist_ma60_pct']].mean(axis=1, skipna=True)
    breakout_penalty = pd.to_numeric(panel['breakout60'], errors='coerce').fillna(0).astype(float)
    panel['t3_positive_score'] = pos
    panel['t3_crowded_score'] = neg
    panel['t3_model_score'] = pos - 0.35 * neg - 0.05 * breakout_penalty
    panel['t3_model_score_pct'] = panel.groupby(['model_code', 'horizon', 'signal_date'])['t3_model_score'].rank(pct=True)
    return panel


def load_target_flags(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel[['model_code', 'horizon', 'signal_date', 'end_date', 'ticker']].copy()
    for label, table, flag_col in TARGET_SPECS:
        df = read_sql(RESEARCH_DB, f'SELECT model_code, horizon, signal_date, end_date, ticker, {flag_col} FROM {table}', parse_dates=['signal_date', 'end_date'])
        df['ticker'] = df['ticker'].astype(str).str.zfill(6)
        out = out.merge(df, on=['model_code', 'horizon', 'signal_date', 'end_date', 'ticker'], how='left')
        out[flag_col] = pd.to_numeric(out[flag_col], errors='coerce').fillna(0).astype(int)
    return out


def summarize_capture(panel: pd.DataFrame, flags: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = panel.merge(flags, on=['model_code', 'horizon', 'signal_date', 'end_date', 'ticker'], how='left')
    summary_rows = []
    hit_rows = []
    for filt_label, filt in FILTER_SPECS:
        work[f'{filt_label}_flag'] = (work['t3_model_score_pct'] >= filt).astype(int)
        for target_label, _table, target_flag_col in TARGET_SPECS:
            for (model_code, horizon), g in work.groupby(['model_code', 'horizon']):
                pred = g[f'{filt_label}_flag']
                truth = g[target_flag_col]
                tp = int(((pred == 1) & (truth == 1)).sum())
                pred_pos = int((pred == 1).sum())
                actual_pos = int((truth == 1).sum())
                precision = float(tp / pred_pos) if pred_pos else np.nan
                recall = float(tp / actual_pos) if actual_pos else np.nan
                lift = float(precision / (actual_pos / len(g))) if pred_pos and actual_pos else np.nan
                summary_rows.append({
                    'filter_label': filt_label,
                    'target_label': target_label,
                    'model_code': model_code,
                    'horizon': horizon,
                    'n_obs': int(len(g)),
                    'predicted_count': pred_pos,
                    'target_count': actual_pos,
                    'true_positive_count': tp,
                    'precision': precision,
                    'recall': recall,
                    'precision_lift_vs_base': lift,
                    'avg_t3_score_predicted': float(g.loc[pred == 1, 't3_model_score'].mean()) if pred_pos else np.nan,
                    'avg_fwd_ret_predicted': float(g.loc[pred == 1, 'fwd_ret'].mean()) if pred_pos else np.nan,
                    'avg_path_mdd_predicted': float(g.loc[pred == 1, 'path_mdd'].mean()) if pred_pos else np.nan,
                })
                hits = g[(pred == 1) & (truth == 1)].copy()
                if not hits.empty:
                    sample = (
                        hits.groupby(['ticker', 'name', 'market'], as_index=False)
                        .agg(hit_count=('ticker', 'size'), avg_t3_score=('t3_model_score', 'mean'), avg_fwd_ret=('fwd_ret', 'mean'), avg_path_mdd=('path_mdd', 'mean'))
                        .sort_values(['hit_count', 'avg_t3_score'], ascending=[False, False])
                        .head(20)
                    )
                    sample['filter_label'] = filt_label
                    sample['target_label'] = target_label
                    sample['model_code'] = model_code
                    sample['horizon'] = horizon
                    hit_rows.append(sample)
    summary = pd.DataFrame(summary_rows)
    hits = pd.concat(hit_rows, ignore_index=True) if hit_rows else pd.DataFrame()
    return summary, hits


def render_md(overall: pd.DataFrame, hits: pd.DataFrame) -> str:
    lines = ['# T3 Model Filter Analysis', '']
    lines.append('T3 model score is defined from Top3-entry characteristics: fundamentals growth/acceleration and long-trend alignment, with crowded short-term momentum penalties.')
    lines.append('')
    lines.append('## Overall summary by filter and target')
    lines.append('| Filter | Target | Precision | Recall | Lift vs Base | Avg Pred Return | Avg Pred MDD |')
    lines.append('|---|---|---:|---:|---:|---:|---:|')
    agg = overall.groupby(['filter_label', 'target_label'], as_index=False).agg(
        precision=('precision', 'mean'),
        recall=('recall', 'mean'),
        precision_lift_vs_base=('precision_lift_vs_base', 'mean'),
        avg_fwd_ret_predicted=('avg_fwd_ret_predicted', 'mean'),
        avg_path_mdd_predicted=('avg_path_mdd_predicted', 'mean'),
    )
    for r in agg.itertuples(index=False):
        lines.append(f'| {r.filter_label} | {r.target_label} | {r.precision:.2%} | {r.recall:.2%} | {r.precision_lift_vs_base:.2f}x | {r.avg_fwd_ret_predicted:.2%} | {r.avg_path_mdd_predicted:.2%} |')
    lines.append('')
    lines.append('## Best model/horizon cases')
    top = overall.sort_values(['precision_lift_vs_base', 'precision'], ascending=[False, False]).head(15)
    lines.append('| Filter | Target | Model | Horizon | Precision | Recall | Lift | TP | Pred | Target |')
    lines.append('|---|---|---|---|---:|---:|---:|---:|---:|---:|')
    for r in top.itertuples(index=False):
        lines.append(f'| {r.filter_label} | {r.target_label} | {r.model_code} | {r.horizon} | {r.precision:.2%} | {r.recall:.2%} | {r.precision_lift_vs_base:.2f}x | {r.true_positive_count} | {r.predicted_count} | {r.target_count} |')
    if not hits.empty:
        lines.append('')
        lines.append('## Example captured names')
        lines.append('| Filter | Target | Model | Horizon | Ticker | Name | Market | Hit Count | Avg T3 Score | Avg Return | Avg MDD |')
        lines.append('|---|---|---|---|---|---|---|---:|---:|---:|---:|')
        for r in hits.sort_values(['hit_count', 'avg_t3_score'], ascending=[False, False]).head(30).itertuples(index=False):
            lines.append(f'| {r.filter_label} | {r.target_label} | {r.model_code} | {r.horizon} | {r.ticker} | {r.name} | {r.market} | {r.hit_count} | {r.avg_t3_score:.4f} | {r.avg_fwd_ret:.2%} | {r.avg_path_mdd:.2%} |')
    lines.append('')
    return '\n'.join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    panel = build_panel()
    flags = load_target_flags(panel)
    summary, hits = summarize_capture(panel, flags)

    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        panel.to_sql('t3_model_filter_panel', con, if_exists='replace', index=False)
        summary.to_sql('t3_model_filter_capture_summary', con, if_exists='replace', index=False)
        hits.to_sql('t3_model_filter_capture_examples', con, if_exists='replace', index=False)
    finally:
        con.close()

    panel.to_csv(OUTDIR / 't3_model_filter_panel_sample.csv', index=False, encoding='utf-8-sig')
    summary.to_csv(OUTDIR / 't3_model_filter_capture_summary.csv', index=False, encoding='utf-8-sig')
    hits.to_csv(OUTDIR / 't3_model_filter_capture_examples.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 't3_model_filter_analysis.md').write_text(render_md(summary, hits), encoding='utf-8')
    print('[ok] T3 model filter analysis built')
    print(summary.sort_values(['precision_lift_vs_base', 'precision'], ascending=[False, False]).head(12).to_string(index=False))


if __name__ == '__main__':
    main()
