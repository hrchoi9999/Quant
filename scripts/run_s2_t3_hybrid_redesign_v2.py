
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\S2_T3_HYBRID_REDESIGN_V2"
HORIZON_MAP = {"3M": 12, "6M": 24, "1Y": 52}
MIN_SELECTED_PER_DATE = 15
VARIANT_GRID = [
    (0.45, 0.45, 0.30, 0.35, 0.20, 25),
    (0.50, 0.45, 0.30, 0.35, 0.20, 25),
    (0.45, 0.50, 0.30, 0.35, 0.20, 25),
    (0.45, 0.45, 0.25, 0.40, 0.20, 25),
    (0.45, 0.45, 0.35, 0.30, 0.20, 25),
    (0.45, 0.45, 0.30, 0.35, 0.20, 30),
]


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def latest_s2_signal_dates() -> list[pd.Timestamp]:
    run = read_sql(QS_DB, "SELECT run_id FROM run_runs WHERE model_code='S2' ORDER BY created_at DESC LIMIT 1")
    run_id = str(run.loc[0, 'run_id'])
    df = read_sql(QS_DETAIL_DB, 'SELECT date FROM run_signal_details_s2 WHERE run_id=? ORDER BY date', (run_id,), parse_dates=['date'])
    return sorted(pd.to_datetime(df['date'].dropna().unique()))


def make_end_map(signal_dates: list[pd.Timestamp], horizon_weeks: int) -> dict[pd.Timestamp, pd.Timestamp]:
    dts = sorted(pd.to_datetime(pd.Series(signal_dates).dropna().unique()))
    return {dts[i]: dts[i + horizon_weeks] for i in range(len(dts) - horizon_weeks)}


def _pct_rank_high(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors='coerce')
    return s.rank(pct=True)


def _pct_rank_low(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors='coerce')
    return (-s).rank(pct=True)


def compute_window_stats(cand: pd.DataFrame, price_groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
            'horizon': row.horizon,
            'ticker': row.ticker,
            'selected': int(row.selected),
            'fwd_ret': float(rel.iloc[-1] - 1.0),
            'path_mdd': float(dd.min()),
        })
    return pd.DataFrame(rows)


def load_panel() -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[pd.Timestamp]]:
    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])
    wide = prices.pivot(index='date', columns='ticker', values='close').sort_index()
    ma60 = wide.rolling(60, min_periods=60).mean()
    ma120 = wide.rolling(120, min_periods=120).mean()
    ma140 = wide.rolling(140, min_periods=140).mean()
    ret_4w = wide / wide.shift(20) - 1.0
    ret_12w = wide / wide.shift(60) - 1.0

    fund = read_sql(FUND_DB, 'SELECT date, ticker, revenue_yoy, op_income_yoy, growth_score, valid_fund, score_rank FROM s2_fund_scores_monthly', parse_dates=['date'])
    fund['ticker'] = fund['ticker'].astype(str).str.zfill(6)
    for c in ['revenue_yoy', 'op_income_yoy', 'growth_score', 'score_rank']:
        fund[c] = pd.to_numeric(fund[c], errors='coerce')
    fund['valid_fund'] = pd.to_numeric(fund['valid_fund'], errors='coerce').fillna(0).astype(int)
    fund = fund[fund['valid_fund'] == 1].copy().sort_values(['ticker', 'date'])
    fund['rev_delta_3m'] = fund.groupby('ticker')['revenue_yoy'].diff(3)
    fund['op_delta_3m'] = fund.groupby('ticker')['op_income_yoy'].diff(3)
    fund['gs_delta_3m'] = fund.groupby('ticker')['growth_score'].diff(3)

    signal_dates = latest_s2_signal_dates()
    rows = []
    for d0 in signal_dates:
        fund_date = fund.loc[fund['date'] <= d0, 'date'].max()
        if pd.isna(fund_date) or d0 not in wide.index:
            continue
        snap = fund.loc[fund['date'] == fund_date, ['ticker', 'score_rank', 'rev_delta_3m', 'op_delta_3m', 'gs_delta_3m']].copy()
        snap['date'] = d0
        snap['close'] = snap['ticker'].map(wide.loc[d0].to_dict())
        snap['ma60'] = snap['ticker'].map(ma60.loc[d0].to_dict())
        snap['ma120'] = snap['ticker'].map(ma120.loc[d0].to_dict())
        snap['ma140'] = snap['ticker'].map(ma140.loc[d0].to_dict())
        snap['mom_4w'] = snap['ticker'].map(ret_4w.loc[d0].to_dict())
        snap['mom_12w'] = snap['ticker'].map(ret_12w.loc[d0].to_dict())
        snap['trend_ok'] = ((snap['close'] > snap['ma140']) & (snap['ma60'] > snap['ma120'])).astype(int)
        snap['ma_stack_gap'] = (snap['ma60'] / snap['ma120']) - 1.0
        snap['base_fund_pct'] = _pct_rank_low(snap['score_rank'])
        snap['fund_accel_pct'] = pd.concat([
            _pct_rank_high(snap['rev_delta_3m']).rename('r'),
            _pct_rank_high(snap['op_delta_3m']).rename('o'),
            _pct_rank_low(snap['gs_delta_3m']).rename('g')
        ], axis=1).mean(axis=1, skipna=True)
        snap['ma_stack_gap_pct'] = _pct_rank_high(snap['ma_stack_gap'])
        snap['mom_4w_pct'] = _pct_rank_high(snap['mom_4w'])
        snap['mom_12w_pct'] = _pct_rank_high(snap['mom_12w'])
        rows.append(snap)
    panel = pd.concat(rows, ignore_index=True)
    price_groups = {t: g[['date', 'close']].reset_index(drop=True) for t, g in prices.groupby('ticker')}
    return panel, price_groups, signal_dates


def build_candidates(panel: pd.DataFrame, signal_dates: list[pd.Timestamp], cfg):
    mom4_min, mom12_min, w_base, w_accel, w_trend, top_n = cfg
    rows = []
    counts = []
    for d0 in signal_dates:
        snap = panel.loc[panel['date'] == d0].copy()
        snap = snap[(snap['trend_ok'] == 1) & (snap['mom_4w_pct'] >= mom4_min) & (snap['mom_12w_pct'] >= mom12_min)].copy()
        snap = snap.dropna(subset=['base_fund_pct', 'fund_accel_pct', 'ma_stack_gap_pct'])
        if len(snap) < top_n:
            continue
        snap['hybrid_score'] = w_base*snap['base_fund_pct'] + w_accel*snap['fund_accel_pct'] + w_trend*snap['ma_stack_gap_pct']
        chosen = snap.sort_values(['hybrid_score', 'score_rank', 'ticker'], ascending=[False, True, True]).head(top_n).copy()
        counts.append({'date': d0, 'candidate_count': int(len(snap)), 'selected_count': int(len(chosen))})
        rows.append(chosen[['date', 'ticker', 'hybrid_score', 'score_rank', 'base_fund_pct', 'fund_accel_pct', 'ma_stack_gap_pct', 'mom_4w_pct', 'mom_12w_pct']])
    return (pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['date','ticker']), pd.DataFrame(counts))


def build_stats(selected_df: pd.DataFrame, signal_dates: list[pd.Timestamp], price_groups: dict[str, pd.DataFrame], panel: pd.DataFrame) -> pd.DataFrame:
    selected_lookup = set(zip(pd.to_datetime(selected_df['date']), selected_df['ticker']))
    out = []
    for horizon, weeks in HORIZON_MAP.items():
        end_map = make_end_map(signal_dates, weeks)
        rows = []
        for d0, d1 in end_map.items():
            snap = panel.loc[panel['date'] == d0].copy()
            snap = snap[snap['trend_ok'] == 1].copy()
            if snap.empty:
                continue
            snap['date'] = d0
            snap['end_date'] = d1
            snap['horizon'] = horizon
            snap['selected'] = snap['ticker'].map(lambda t: 1 if (d0, t) in selected_lookup else 0)
            rows.append(snap[['date','end_date','horizon','ticker','selected']])
        cand = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['date','end_date','horizon','ticker','selected'])
        out.append(compute_window_stats(cand, price_groups))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def summarize_variant(stats: pd.DataFrame, variant_id: str, counts_df: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    avg_selected_count=float(counts_df['selected_count'].mean()) if not counts_df.empty else np.nan
    min_selected_count=int(counts_df['selected_count'].min()) if not counts_df.empty else 0
    for horizon, g in stats.groupby('horizon'):
        sel = g[g['selected']==1]
        non = g[g['selected']==0]
        rows.append({
            'variant_id': variant_id,
            'horizon': horizon,
            'avg_selected_return': sel['fwd_ret'].mean(),
            'avg_not_selected_return': non['fwd_ret'].mean(),
            'return_delta': sel['fwd_ret'].mean() - non['fwd_ret'].mean(),
            'avg_selected_mdd': sel['path_mdd'].mean(),
            'avg_not_selected_mdd': non['path_mdd'].mean(),
            'mdd_delta': sel['path_mdd'].mean() - non['path_mdd'].mean(),
            'avg_selected_count': avg_selected_count,
            'min_selected_count': min_selected_count,
        })
    return pd.DataFrame(rows)


def variant_score(summary: pd.DataFrame) -> float:
    by_h = summary.set_index('horizon')
    score = float(by_h.loc['3M','return_delta']) + 1.5*float(by_h.loc['6M','return_delta']) + 2.0*float(by_h.loc['1Y','return_delta'])
    score += (-float(by_h.loc['3M','mdd_delta']))*0.4 + (-float(by_h.loc['6M','mdd_delta']))*0.6 + (-float(by_h.loc['1Y','mdd_delta']))*0.8
    if float(by_h.loc['1Y','return_delta']) < 0:
        score -= 0.05
    return score


def render(best_cfg, best_summary, all_summary):
    lines=['# S2 T3 Hybrid Redesign V2','']
    lines.append('Momentum confirmation is used only as an entry-quality filter, while ranking is driven by base fundamentals, fundamentals acceleration, and long-trend alignment.')
    lines.append('')
    lines.append('## Best variant')
    lines.append(f'- mom_4w_pct_min: `{best_cfg[0]:.2f}`')
    lines.append(f'- mom_12w_pct_min: `{best_cfg[1]:.2f}`')
    lines.append(f'- base_fund_weight: `{best_cfg[2]:.2f}`')
    lines.append(f'- fund_accel_weight: `{best_cfg[3]:.2f}`')
    lines.append(f'- trend_align_weight: `{best_cfg[4]:.2f}`')
    lines.append(f'- top_n: `{best_cfg[5]}`')
    lines.append('')
    lines.append('| Horizon | Selected Avg Return | Not Selected Avg Return | Return Delta | Selected Avg MDD | Not Selected Avg MDD | MDD Delta | Avg Selected Count |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
    for r in best_summary.itertuples(index=False):
        lines.append(f'| {r.horizon} | {r.avg_selected_return:.2%} | {r.avg_not_selected_return:.2%} | {r.return_delta:.2%} | {r.avg_selected_mdd:.2%} | {r.avg_not_selected_mdd:.2%} | {r.mdd_delta:.2%} | {r.avg_selected_count:.1f} |')
    lines.append('')
    lines.append('## Top variants by experiment score')
    top = all_summary[['variant_id','experiment_score']].drop_duplicates().sort_values('experiment_score', ascending=False).head(10)
    lines.append('| Variant | Experiment Score |')
    lines.append('|---|---:|')
    for r in top.itertuples(index=False):
        lines.append(f'| {r.variant_id} | {r.experiment_score:.4f} |')
    lines.append('')
    return '\n'.join(lines)


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    panel, price_groups, signal_dates = load_panel()
    best=None; best_score=-1e9; best_summary=None; best_sel=None; best_counts=None; all_summaries=[]
    for cfg in VARIANT_GRID:
        sel, counts = build_candidates(panel, signal_dates, cfg)
        if sel.empty or counts.empty or counts['selected_count'].min() < MIN_SELECTED_PER_DATE:
            continue
        stats = build_stats(sel, signal_dates, price_groups, panel)
        if stats.empty:
            continue
        variant_id = f'm4_{cfg[0]:.2f}__m12_{cfg[1]:.2f}__base_{cfg[2]:.2f}__accel_{cfg[3]:.2f}__trend_{cfg[4]:.2f}__topn_{cfg[5]}'
        summary = summarize_variant(stats, variant_id, counts)
        score = variant_score(summary)
        summary['experiment_score'] = score
        all_summaries.append(summary)
        if score > best_score:
            best=cfg; best_score=score; best_summary=summary.copy(); best_sel=sel.copy(); best_counts=counts.copy()
    if best is None:
        raise RuntimeError('No feasible variant found')
    all_summary = pd.concat(all_summaries, ignore_index=True).sort_values(['experiment_score','variant_id','horizon'], ascending=[False,True,True])
    best_sel.to_csv(OUTDIR / 's2_t3_hybrid_redesign_best_selected.csv', index=False, encoding='utf-8-sig')
    best_counts.to_csv(OUTDIR / 's2_t3_hybrid_redesign_best_counts.csv', index=False, encoding='utf-8-sig')
    best_summary.to_csv(OUTDIR / 's2_t3_hybrid_redesign_best_summary.csv', index=False, encoding='utf-8-sig')
    all_summary.to_csv(OUTDIR / 's2_t3_hybrid_redesign_grid_summary.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's2_t3_hybrid_redesign_review.md').write_text(render(best, best_summary, all_summary), encoding='utf-8')
    print('best_cfg', best)
    print(best_summary.to_string(index=False))

if __name__ == '__main__':
    main()
