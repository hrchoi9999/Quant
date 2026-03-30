from __future__ import annotations

import itertools
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\S2_MOMENTUM_CONFIRMATION_V1"
HORIZON_MAP = {"3M": 12, "6M": 24, "1Y": 52}
VARIANT_GRID = [(0.55, 0.50, 25)]
MIN_SELECTED_PER_DATE = 15


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def latest_s2_run() -> str:
    df = read_sql(
        QS_DB,
        """
        SELECT run_id FROM run_runs
        WHERE model_code='S2'
        ORDER BY created_at DESC
        LIMIT 1
        """,
    )
    if df.empty:
        raise RuntimeError("No S2 run found")
    return str(df.loc[0, 'run_id'])


def make_end_map(signal_dates: list[pd.Timestamp], horizon_weeks: int) -> dict[pd.Timestamp, pd.Timestamp]:
    dts = sorted(pd.to_datetime(pd.Series(signal_dates).dropna().unique()))
    return {dts[i]: dts[i + horizon_weeks] for i in range(len(dts) - horizon_weeks)}


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


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[pd.Timestamp]]:
    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])
    price_groups = {t: g[['date', 'close']].reset_index(drop=True) for t, g in prices.groupby('ticker')}

    fund = read_sql(
        FUND_DB,
        'SELECT date, ticker, growth_score, valid_fund, score_rank FROM s2_fund_scores_monthly',
        parse_dates=['date'],
    )
    fund['ticker'] = fund['ticker'].astype(str).str.zfill(6)
    fund['growth_score'] = pd.to_numeric(fund['growth_score'], errors='coerce')
    fund['score_rank'] = pd.to_numeric(fund['score_rank'], errors='coerce')
    fund['valid_fund'] = pd.to_numeric(fund['valid_fund'], errors='coerce').fillna(0).astype(int)
    fund = fund[fund['valid_fund'] == 1].copy()

    run_id = latest_s2_run()
    selected = read_sql(
        QS_DETAIL_DB,
        'SELECT date, ticker FROM run_signal_details_s2 WHERE run_id=?',
        params=(run_id,),
        parse_dates=['date'],
    )
    selected['ticker'] = selected['ticker'].astype(str).str.zfill(6)
    signal_dates = sorted(pd.to_datetime(selected['date'].dropna().unique()))

    wide = prices.pivot(index='date', columns='ticker', values='close').sort_index()
    ret_4w = wide / wide.shift(20) - 1.0
    ret_12w = wide / wide.shift(60) - 1.0

    return fund, ret_4w, ret_12w, signal_dates


def build_candidates_for_variant(
    fund: pd.DataFrame,
    ret_4w: pd.DataFrame,
    ret_12w: pd.DataFrame,
    signal_dates: list[pd.Timestamp],
    thresholds: tuple[float, float, int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mom4_min, mom12_min, top_n = thresholds
    rows = []
    counts = []
    for d0 in signal_dates:
        fund_date = fund.loc[fund['date'] <= d0, 'date'].max()
        if pd.isna(fund_date):
            continue
        snap = fund.loc[fund['date'] == fund_date, ['ticker', 'growth_score', 'score_rank']].copy()
        if snap.empty:
            continue
        if d0 not in ret_4w.index or d0 not in ret_12w.index:
            continue
        snap['mom_4w'] = snap['ticker'].map(ret_4w.loc[d0].to_dict())
        snap['mom_12w'] = snap['ticker'].map(ret_12w.loc[d0].to_dict())
        snap = snap.dropna(subset=['mom_4w', 'mom_12w']).copy()
        if len(snap) < top_n:
            continue
        snap['mom_4w_pct'] = snap['mom_4w'].rank(pct=True)
        snap['mom_12w_pct'] = snap['mom_12w'].rank(pct=True)
        filt = snap[(snap['mom_4w_pct'] >= mom4_min) & (snap['mom_12w_pct'] >= mom12_min)].copy()
        filt = filt.sort_values(['growth_score', 'score_rank'], ascending=[False, True]).head(top_n)
        filt['date'] = d0
        counts.append({'date': d0, 'candidate_count': int(len(snap)), 'selected_count': int(len(filt))})
        rows.append(filt[['date', 'ticker', 'growth_score', 'score_rank', 'mom_4w', 'mom_12w', 'mom_4w_pct', 'mom_12w_pct']])
    cand = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['date', 'ticker'])
    counts_df = pd.DataFrame(counts)
    return cand, counts_df


def build_stats_for_variant(
    variant_selected: pd.DataFrame,
    signal_dates: list[pd.Timestamp],
    price_groups: dict[str, pd.DataFrame],
    fund: pd.DataFrame,
) -> pd.DataFrame:
    out = []
    selected_lookup = set(zip(pd.to_datetime(variant_selected['date']), variant_selected['ticker']))
    for horizon, weeks in HORIZON_MAP.items():
        end_map = make_end_map(signal_dates, weeks)
        rows = []
        for d0, d1 in end_map.items():
            fund_date = fund.loc[fund['date'] <= d0, 'date'].max()
            if pd.isna(fund_date):
                continue
            snap = fund.loc[fund['date'] == fund_date, ['ticker']].copy()
            if snap.empty:
                continue
            snap['date'] = d0
            snap['end_date'] = d1
            snap['horizon'] = horizon
            snap['selected'] = snap['ticker'].map(lambda t: 1 if (d0, t) in selected_lookup else 0)
            rows.append(snap)
        cand = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['date', 'end_date', 'horizon', 'ticker', 'selected'])
        stats = compute_window_stats(cand, price_groups)
        out.append(stats)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def summarize_variant(stats: pd.DataFrame, variant_id: str, counts_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    avg_selected_count = float(counts_df['selected_count'].mean()) if not counts_df.empty else np.nan
    min_selected_count = int(counts_df['selected_count'].min()) if not counts_df.empty else 0
    for horizon, g in stats.groupby('horizon'):
        sel = g[g['selected'] == 1]
        non = g[g['selected'] == 0]
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
            'n_selected_obs': int(len(sel)),
            'n_not_selected_obs': int(len(non)),
        })
    return pd.DataFrame(rows)


def variant_score(summary: pd.DataFrame) -> float:
    by_h = summary.set_index('horizon')
    score = 0.0
    score += float(by_h.loc['3M', 'return_delta']) * 1.0
    score += float(by_h.loc['6M', 'return_delta']) * 1.5
    score += float(by_h.loc['1Y', 'return_delta']) * 2.0
    mdd_penalty = 0.0
    for h in ['3M', '6M', '1Y']:
        mdd_delta = float(by_h.loc[h, 'mdd_delta'])
        if mdd_delta < -0.03:
            mdd_penalty += abs(mdd_delta) * 0.5
    count_penalty = 0.0
    if float(by_h['avg_selected_count'].mean()) < 18:
        count_penalty = 0.02
    return score - mdd_penalty - count_penalty


def render_markdown(best_cfg: tuple[float, float, int], best_summary: pd.DataFrame, all_summary: pd.DataFrame) -> str:
    lines = ['# S2 Momentum Confirmation V1', '']
    lines.append('## Best variant')
    lines.append(f'- mom_4w_pct_min: `{best_cfg[0]:.2f}`')
    lines.append(f'- mom_12w_pct_min: `{best_cfg[1]:.2f}`')
    lines.append(f'- top_n: `{best_cfg[2]}`')
    lines.append('')
    lines.append('| Horizon | Selected Avg Return | Not Selected Avg Return | Return Delta | Selected Avg MDD | Not Selected Avg MDD | MDD Delta | Avg Selected Count |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
    for r in best_summary.itertuples(index=False):
        lines.append(
            f'| {r.horizon} | {r.avg_selected_return:.2%} | {r.avg_not_selected_return:.2%} | {r.return_delta:.2%} | {r.avg_selected_mdd:.2%} | {r.avg_not_selected_mdd:.2%} | {r.mdd_delta:.2%} | {r.avg_selected_count:.1f} |'
        )
    lines.append('')
    lines.append('## Top variants by experiment score')
    top = all_summary[['variant_id', 'experiment_score']].drop_duplicates().sort_values('experiment_score', ascending=False).head(10)
    lines.append('| Variant | Experiment Score |')
    lines.append('|---|---:|')
    for r in top.itertuples(index=False):
        lines.append(f'| {r.variant_id} | {r.experiment_score:.4f} |')
    lines.append('')
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fund, ret_4w, ret_12w, signal_dates = load_inputs()
    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])
    price_groups = {t: g[['date', 'close']].reset_index(drop=True) for t, g in prices.groupby('ticker')}

    all_summaries = []
    best = None
    best_score = -1e9
    best_summary = None
    best_selected = None
    best_counts = None

    for cfg in VARIANT_GRID:
        selected, counts_df = build_candidates_for_variant(fund, ret_4w, ret_12w, signal_dates, cfg)
        if selected.empty or counts_df.empty:
            continue
        if counts_df['selected_count'].min() < MIN_SELECTED_PER_DATE:
            continue
        stats = build_stats_for_variant(selected, signal_dates, price_groups, fund)
        if stats.empty:
            continue
        variant_id = f"mom4_{cfg[0]:.2f}__mom12_{cfg[1]:.2f}__topn_{cfg[2]}"
        summary = summarize_variant(stats, variant_id, counts_df)
        score = variant_score(summary)
        summary['experiment_score'] = score
        all_summaries.append(summary)
        if score > best_score:
            best = cfg
            best_score = score
            best_summary = summary.copy()
            best_selected = selected.copy()
            best_counts = counts_df.copy()

    if best is None or best_summary is None or best_selected is None or best_counts is None:
        raise RuntimeError('No feasible variant found')

    all_summary = pd.concat(all_summaries, ignore_index=True).sort_values(['experiment_score', 'variant_id', 'horizon'], ascending=[False, True, True])
    best_selected.to_csv(OUTDIR / 's2_momentum_confirmation_best_selected.csv', index=False, encoding='utf-8-sig')
    best_counts.to_csv(OUTDIR / 's2_momentum_confirmation_best_counts.csv', index=False, encoding='utf-8-sig')
    best_summary.to_csv(OUTDIR / 's2_momentum_confirmation_best_summary.csv', index=False, encoding='utf-8-sig')
    all_summary.to_csv(OUTDIR / 's2_momentum_confirmation_grid_summary.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's2_momentum_confirmation_review.md').write_text(render_markdown(best, best_summary, all_summary), encoding='utf-8')
    print('best_cfg', best)
    print(best_summary.to_string(index=False))


if __name__ == '__main__':
    main()
