from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\TOP3_ENTRY_FEATURE_ANALYSIS"

BASE_TABLE = 'universe_top_3pct_candidates'
PANEL_TABLE = 'top3_entry_feature_panel'
SUMMARY_TABLE = 'top3_entry_feature_summary'
SUMMARY_BY_MODEL_TABLE = 'top3_entry_feature_summary_by_model'

FEATURES = [
    'growth_score', 'revenue_yoy', 'op_income_yoy', 'score_rank',
    'close', 'mom20', 'vol_ratio_20', 'breakout60', 'ma60', 'ma120', 'ma60_slope', 'ma120_slope',
    'fund_accel_score', 'gs_delta_3m', 'rev_delta_3m', 'op_delta_3m',
    'dist_ma60', 'dist_ma120', 'ma_stack_gap'
]
PCT_FEATURES = [
    'growth_score', 'revenue_yoy', 'op_income_yoy', 'score_rank',
    'mom20', 'vol_ratio_20', 'fund_accel_score', 'gs_delta_3m', 'rev_delta_3m', 'op_delta_3m',
    'dist_ma60', 'dist_ma120', 'ma_stack_gap'
]


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def add_entry_flags(base: pd.DataFrame) -> pd.DataFrame:
    base = base.sort_values(['model_code', 'horizon', 'ticker', 'signal_date']).copy()
    base['prev_top_flag'] = base.groupby(['model_code', 'horizon', 'ticker'])['top_flag'].shift(1).fillna(0).astype(int)
    base['entry_start_flag'] = ((base['top_flag'] == 1) & (base['prev_top_flag'] == 0)).astype(int)
    return base


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
    for feat in PCT_FEATURES:
        if feat in panel.columns:
            panel[f'{feat}_pct'] = panel.groupby(grp)[feat].rank(pct=True)
    return panel


def summarize_features(panel: pd.DataFrame, group_cols: list[str] | None = None) -> pd.DataFrame:
    rows = []
    keys = [()] if not group_cols else panel[group_cols].drop_duplicates().itertuples(index=False, name=None)
    for key in keys:
        if not group_cols:
            sub = panel
            key_map = {}
        else:
            key_map = dict(zip(group_cols, key))
            mask = pd.Series(True, index=panel.index)
            for col, val in key_map.items():
                mask &= panel[col].eq(val)
            sub = panel[mask]
        y = sub['entry_start_flag']
        for feat in [f'{x}_pct' for x in PCT_FEATURES if f'{x}_pct' in sub.columns] + ['breakout60']:
            x = pd.to_numeric(sub[feat], errors='coerce')
            use = pd.DataFrame({'x': x, 'y': y}).dropna()
            if len(use) < 50 or use['y'].nunique() < 2 or use['x'].nunique() < 2:
                continue
            entry = use.loc[use['y'] == 1, 'x']
            non = use.loc[use['y'] == 0, 'x']
            q80 = use['x'].quantile(0.8)
            q20 = use['x'].quantile(0.2)
            top_rate = float(use.loc[use['x'] >= q80, 'y'].mean()) if pd.notna(q80) else np.nan
            bot_rate = float(use.loc[use['x'] <= q20, 'y'].mean()) if pd.notna(q20) else np.nan
            row = {
                'feature': feat,
                'n': int(len(use)),
                'entry_count': int((use['y'] == 1).sum()),
                'corr_entry': float(use['x'].corr(use['y'])),
                'mean_entry': float(entry.mean()),
                'mean_non_entry': float(non.mean()),
                'mean_diff': float(entry.mean() - non.mean()),
                'top20_entry_rate': top_rate,
                'bottom20_entry_rate': bot_rate,
                'entry_rate_lift_top_vs_bottom': float(top_rate - bot_rate) if pd.notna(top_rate) and pd.notna(bot_rate) else np.nan,
            }
            row.update(key_map)
            rows.append(row)
    return pd.DataFrame(rows)


def render_markdown(overall: pd.DataFrame, by_model: pd.DataFrame, panel: pd.DataFrame) -> str:
    lines = ['# Top3 Entry Feature Analysis', '']
    lines.append('## Dataset')
    lines.append(f'- panel rows: `{len(panel):,}`')
    lines.append(f'- entry starts: `{int(panel["entry_start_flag"].sum()):,}`')
    lines.append('')
    lines.append('## Overall top features')
    lines.append('| Feature | Corr(entry) | Mean diff | Top20 entry rate | Bottom20 entry rate | Lift | N |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for r in overall.sort_values('corr_entry', ascending=False).head(12).itertuples(index=False):
        lines.append(f'| {r.feature} | {r.corr_entry:.4f} | {r.mean_diff:.4f} | {r.top20_entry_rate:.4%} | {r.bottom20_entry_rate:.4%} | {r.entry_rate_lift_top_vs_bottom:.4%} | {r.n} |')
    lines.append('')
    lines.append('## Overall bottom features')
    lines.append('| Feature | Corr(entry) | Mean diff | Top20 entry rate | Bottom20 entry rate | Lift | N |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for r in overall.sort_values('corr_entry', ascending=True).head(12).itertuples(index=False):
        lines.append(f'| {r.feature} | {r.corr_entry:.4f} | {r.mean_diff:.4f} | {r.top20_entry_rate:.4%} | {r.bottom20_entry_rate:.4%} | {r.entry_rate_lift_top_vs_bottom:.4%} | {r.n} |')
    lines.append('')
    lines.append('## By model top signals')
    for model_code, g in by_model.groupby('model_code'):
        lines.append(f'### {model_code}')
        lines.append('| Feature | Corr(entry) | Lift | N |')
        lines.append('|---|---:|---:|---:|')
        for r in g.sort_values('corr_entry', ascending=False).head(8).itertuples(index=False):
            lines.append(f'| {r.feature} | {r.corr_entry:.4f} | {r.entry_rate_lift_top_vs_bottom:.4%} | {r.n} |')
        lines.append('')
    return '\n'.join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    base = read_sql(RESEARCH_DB, f'SELECT * FROM {BASE_TABLE}', parse_dates=['signal_date', 'end_date'])
    base['ticker'] = base['ticker'].astype(str).str.zfill(6)
    base = add_entry_flags(base)
    panel = base[(base['top_flag'] == 0) | (base['entry_start_flag'] == 1)].copy()

    s2 = read_sql(FUND_DB, 'SELECT date, ticker, growth_score, revenue_yoy, op_income_yoy, score_rank FROM s2_fund_scores_monthly', parse_dates=['date'])
    s2['ticker'] = s2['ticker'].astype(str).str.zfill(6)
    s3p = read_sql(S3_DB, 'SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120, ma60_slope, ma120_slope FROM s3_price_features_daily', parse_dates=['date'])
    s3p['ticker'] = s3p['ticker'].astype(str).str.zfill(6)
    s3f = read_sql(S3_DB, 'SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly', parse_dates=['available_from'])
    s3f['ticker'] = s3f['ticker'].astype(str).str.zfill(6)

    panel = panel.merge(s2, left_on=['signal_date', 'ticker'], right_on=['date', 'ticker'], how='left')
    panel = panel.drop(columns=['date'])
    panel = panel.merge(s3p, left_on=['signal_date', 'ticker'], right_on=['date', 'ticker'], how='left')
    panel = panel.drop(columns=['date'])
    latest_fund = latest_fund_snapshot(s3f, panel)
    panel = panel.merge(latest_fund, on=['ticker', 'signal_date'], how='left')

    panel['dist_ma60'] = panel['close'] / panel['ma60'] - 1.0
    panel['dist_ma120'] = panel['close'] / panel['ma120'] - 1.0
    panel['ma_stack_gap'] = panel['ma60'] / panel['ma120'] - 1.0
    panel = add_pct_ranks(panel)

    overall = summarize_features(panel)
    by_model = summarize_features(panel, ['model_code'])

    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        panel.to_sql(PANEL_TABLE, con, if_exists='replace', index=False)
        overall.to_sql(SUMMARY_TABLE, con, if_exists='replace', index=False)
        by_model.to_sql(SUMMARY_BY_MODEL_TABLE, con, if_exists='replace', index=False)
    finally:
        con.close()

    panel.to_csv(OUTDIR / 'top3_entry_feature_panel_sample.csv', index=False, encoding='utf-8-sig')
    overall.to_csv(OUTDIR / 'top3_entry_feature_summary.csv', index=False, encoding='utf-8-sig')
    by_model.to_csv(OUTDIR / 'top3_entry_feature_summary_by_model.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 'top3_entry_feature_analysis.md').write_text(render_markdown(overall, by_model, panel), encoding='utf-8')
    print('[ok] top3 entry feature analysis built')
    print(f'panel_rows={len(panel)} entry_starts={int(panel["entry_start_flag"].sum())}')


if __name__ == '__main__':
    main()
