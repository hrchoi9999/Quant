from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\S2_OVERHEAT_PENALTY_V1"
HORIZON_MAP = {"3M": 12, "6M": 24, "1Y": 52}
VARIANTS = [
    (0.25, 0.12, 30),
    (0.30, 0.15, 30),
    (0.35, 0.18, 30),
]
MIN_SELECTED_PER_DATE = 20


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


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


def make_end_map(signal_dates: list[pd.Timestamp], horizon_weeks: int) -> dict[pd.Timestamp, pd.Timestamp]:
    dts = sorted(pd.to_datetime(pd.Series(signal_dates).dropna().unique()))
    return {dts[i]: dts[i + horizon_weeks] for i in range(len(dts) - horizon_weeks)}


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[pd.Timestamp], dict[str, pd.DataFrame]]:
    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])
    wide = prices.pivot(index='date', columns='ticker', values='close').sort_index()
    sma20 = wide.rolling(20).mean()
    sma140 = wide.rolling(140).mean()
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
    signal_dates = sorted(pd.to_datetime(fund['date'].dropna().unique()))
    return fund, wide, sma20, sma140, signal_dates, price_groups


def build_selected_for_variant(
    fund: pd.DataFrame,
    close_wide: pd.DataFrame,
    sma20: pd.DataFrame,
    sma140: pd.DataFrame,
    signal_dates: list[pd.Timestamp],
    cfg: tuple[float, float, int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cap_sma140, cap_ma20, top_n = cfg
    rows = []
    counts = []
    for d0 in signal_dates:
        if d0 not in close_wide.index or d0 not in sma20.index or d0 not in sma140.index:
            continue
        snap = fund.loc[fund['date'] == d0, ['ticker', 'growth_score', 'score_rank']].copy()
        if snap.empty:
            continue
        snap['close'] = snap['ticker'].map(close_wide.loc[d0].to_dict())
        snap['sma20'] = snap['ticker'].map(sma20.loc[d0].to_dict())
        snap['sma140'] = snap['ticker'].map(sma140.loc[d0].to_dict())
        snap = snap.dropna(subset=['close', 'sma20', 'sma140']).copy()
        if len(snap) < top_n:
            continue
        snap['dist_sma140'] = snap['close'] / snap['sma140'] - 1.0
        snap['dist_ma20'] = snap['close'] / snap['sma20'] - 1.0
        filt = snap[(snap['dist_sma140'] <= cap_sma140) & (snap['dist_ma20'] <= cap_ma20)].copy()
        filt = filt.sort_values(['growth_score', 'score_rank'], ascending=[False, True]).head(top_n)
        counts.append({'date': d0, 'candidate_count': int(len(snap)), 'selected_count': int(len(filt))})
        filt['date'] = d0
        rows.append(filt[['date', 'ticker', 'growth_score', 'score_rank', 'dist_sma140', 'dist_ma20']])
    selected = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['date', 'ticker'])
    counts_df = pd.DataFrame(counts)
    return selected, counts_df


def build_stats(selected: pd.DataFrame, signal_dates: list[pd.Timestamp], fund: pd.DataFrame, price_groups: dict[str, pd.DataFrame]) -> pd.DataFrame:
    selected_lookup = set(zip(pd.to_datetime(selected['date']), selected['ticker']))
    out = []
    for horizon, weeks in HORIZON_MAP.items():
        end_map = make_end_map(signal_dates, weeks)
        rows = []
        for d0, d1 in end_map.items():
            snap = fund.loc[fund['date'] == d0, ['ticker']].copy()
            if snap.empty:
                continue
            snap['date'] = d0
            snap['end_date'] = d1
            snap['horizon'] = horizon
            snap['selected'] = snap['ticker'].map(lambda t: 1 if (d0, t) in selected_lookup else 0)
            rows.append(snap)
        cand = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['date', 'end_date', 'horizon', 'ticker', 'selected'])
        out.append(compute_window_stats(cand, price_groups))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def summarize(stats: pd.DataFrame, variant_id: str, counts_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    avg_selected_count = float(counts_df['selected_count'].mean()) if not counts_df.empty else float('nan')
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
    score = float(by_h.loc['3M', 'return_delta']) * 1.0
    score += float(by_h.loc['6M', 'return_delta']) * 1.5
    score += float(by_h.loc['1Y', 'return_delta']) * 2.0
    for h in ['3M', '6M', '1Y']:
        mdd_delta = float(by_h.loc[h, 'mdd_delta'])
        if mdd_delta < -0.02:
            score -= abs(mdd_delta) * 0.5
    return score


def render_review(best_cfg: tuple[float, float, int], best_summary: pd.DataFrame, all_summary: pd.DataFrame) -> str:
    lines = ['# S2 Overheat Penalty V1', '']
    lines.append('## Best variant')
    lines.append(f'- distance_from_sma140_cap: `{best_cfg[0]:.2f}`')
    lines.append(f'- extension_from_ma20_cap: `{best_cfg[1]:.2f}`')
    lines.append(f'- top_n: `{best_cfg[2]}`')
    lines.append('')
    lines.append('| Horizon | Selected Avg Return | Not Selected Avg Return | Return Delta | Selected Avg MDD | Not Selected Avg MDD | MDD Delta | Avg Selected Count |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
    for r in best_summary.itertuples(index=False):
        lines.append(f'| {r.horizon} | {r.avg_selected_return:.2%} | {r.avg_not_selected_return:.2%} | {r.return_delta:.2%} | {r.avg_selected_mdd:.2%} | {r.avg_not_selected_mdd:.2%} | {r.mdd_delta:.2%} | {r.avg_selected_count:.1f} |')
    lines.append('')
    lines.append('## Top variants by experiment score')
    lines.append('| Variant | Experiment Score |')
    lines.append('|---|---:|')
    for r in all_summary[['variant_id', 'experiment_score']].drop_duplicates().sort_values('experiment_score', ascending=False).itertuples(index=False):
        lines.append(f'| {r.variant_id} | {r.experiment_score:.4f} |')
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fund, close_wide, sma20, sma140, signal_dates, price_groups = load_inputs()
    all_summary_parts = []
    best_cfg = None
    best_summary = None
    best_counts = None
    best_selected = None
    best_score = -1e9
    for cfg in VARIANTS:
        selected, counts_df = build_selected_for_variant(fund, close_wide, sma20, sma140, signal_dates, cfg)
        if selected.empty or counts_df.empty:
            continue
        if counts_df['selected_count'].min() < MIN_SELECTED_PER_DATE:
            continue
        stats = build_stats(selected, signal_dates, fund, price_groups)
        if stats.empty:
            continue
        variant_id = f"sma140cap_{cfg[0]:.2f}__ma20cap_{cfg[1]:.2f}__topn_{cfg[2]}"
        summary = summarize(stats, variant_id, counts_df)
        score = variant_score(summary)
        summary['experiment_score'] = score
        all_summary_parts.append(summary)
        if score > best_score:
            best_cfg = cfg
            best_summary = summary.copy()
            best_counts = counts_df.copy()
            best_selected = selected.copy()
            best_score = score
    if best_cfg is None or best_summary is None or best_counts is None or best_selected is None:
        raise RuntimeError('No feasible overheat-penalty variant found')
    all_summary = pd.concat(all_summary_parts, ignore_index=True).sort_values(['experiment_score', 'variant_id', 'horizon'], ascending=[False, True, True])
    best_counts.to_csv(OUTDIR / 's2_overheat_penalty_best_counts.csv', index=False, encoding='utf-8-sig')
    best_selected.to_csv(OUTDIR / 's2_overheat_penalty_best_selected.csv', index=False, encoding='utf-8-sig')
    best_summary.to_csv(OUTDIR / 's2_overheat_penalty_best_summary.csv', index=False, encoding='utf-8-sig')
    all_summary.to_csv(OUTDIR / 's2_overheat_penalty_grid_summary.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's2_overheat_penalty_review.md').write_text(render_review(best_cfg, best_summary, all_summary), encoding='utf-8')
    print('best_cfg', best_cfg)
    print(best_summary.to_string(index=False))


if __name__ == '__main__':
    main()
