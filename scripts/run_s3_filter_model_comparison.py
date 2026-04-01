
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330\S3_FILTER_MODEL_COMPARISON"
DETAIL_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260330\selected_vs_not_selected_3m_6m_1y_detail.csv"
WINDOWS = [('3M', 84), ('6M', 168), ('1Y', 365), ('2Y', 730), ('3Y', 1095)]
TOP_N = 20
T3_CUTOFF = 0.50
VARIANTS = [
    ('baseline_s3', 'full_universe'),
    ('t3_filter_s3', 'dynamic_t3_top50pct'),
    ('top0_10_bucket_s3', 'static_band_top0_10pct_universe'),
    ('top10_30_bucket_s3', 'static_band_top10_30pct_universe'),
    ('top30_50_bucket_s3', 'static_band_top30_50pct_universe'),
]


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def latest_s3_dates() -> list[pd.Timestamp]:
    run = read_sql(QS_DB, "SELECT run_id FROM run_runs WHERE model_code='S3' ORDER BY created_at DESC LIMIT 1")
    run_id = str(run.loc[0, 'run_id'])
    dates = read_sql(QS_DETAIL_DB, 'SELECT DISTINCT date FROM run_signal_details_s3 WHERE run_id=? ORDER BY date', (run_id,), parse_dates=['date'])
    return sorted(pd.to_datetime(dates['date'].dropna().unique()))


def latest_fund_snapshot(fund_df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    w = fund_df[fund_df['available_from'] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(['ticker', 'available_from', 'date']).groupby('ticker', as_index=False).tail(1)


def build_t3_score(universe: pd.DataFrame, p_row: pd.DataFrame, fund_snap: pd.DataFrame) -> pd.DataFrame:
    snap = universe.merge(p_row, on='ticker', how='left').merge(fund_snap[['ticker', 'fund_accel_score', 'rev_delta_3m', 'op_delta_3m']], on='ticker', how='left')
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
    snap['t3_model_score'] = snap['t3_positive_score'] - 0.35 * snap['t3_crowded_score'] - 0.05 * snap['breakout60'].fillna(0).astype(float)
    snap['t3_model_score_pct'] = snap['t3_model_score'].rank(pct=True)
    return snap[['ticker', 't3_model_score', 't3_model_score_pct']]


def build_s3_score(universe: pd.DataFrame, p_row: pd.DataFrame, fund_snap: pd.DataFrame) -> pd.DataFrame:
    snap = universe.merge(p_row, on='ticker', how='left').merge(fund_snap[['ticker', 'growth_score', 'fund_accel_score']], on='ticker', how='left')
    snap['mom20_pct'] = snap['mom20'].rank(pct=True)
    snap['vol_ratio_pct'] = snap['vol_ratio_20'].rank(pct=True)
    snap['fund_level_pct'] = snap['growth_score'].rank(pct=True)
    snap['fund_accel_pct'] = snap['fund_accel_score'].rank(pct=True)
    trend_bonus = ((snap['ma60'] > snap['ma120']) & (snap['ma60_slope'] > 0)).astype(int)
    snap['s3_score'] = (
        0.30 * snap['fund_level_pct'].fillna(0)
        + 0.20 * snap['fund_accel_pct'].fillna(0)
        + 0.25 * snap['mom20_pct'].fillna(0)
        + 0.10 * snap['vol_ratio_pct'].fillna(0)
        + 0.05 * snap['breakout60'].fillna(0).astype(int)
        + 0.10 * trend_bonus
    )
    return snap[['ticker', 's3_score']]


def perf_windows(nav_df: pd.DataFrame, end_date: pd.Timestamp | None = None) -> pd.DataFrame:
    nav_df = nav_df.sort_values('date').copy()
    if end_date is not None:
        nav_df = nav_df[nav_df['date'] <= end_date].copy()
    last = pd.to_datetime(nav_df['date'].max())
    rows = []
    for label, days in WINDOWS:
        sub = nav_df[nav_df['date'] >= (last - pd.Timedelta(days=days))].copy()
        if len(sub) < 2:
            continue
        start = float(sub['nav'].iloc[0])
        end = float(sub['nav'].iloc[-1])
        total_return = end / start - 1.0
        years = max((pd.to_datetime(sub['date'].iloc[-1]) - pd.to_datetime(sub['date'].iloc[0])).days / 365.25, 1/52)
        cagr = (end / start) ** (1 / years) - 1.0 if start > 0 else np.nan
        dd = sub['nav'] / sub['nav'].cummax() - 1.0
        mdd = float(dd.min())
        rets = sub['nav'].pct_change().dropna()
        sharpe = float((rets.mean() / rets.std()) * np.sqrt(52)) if len(rets) > 1 and rets.std() > 0 else np.nan
        rows.append({'period': label, 'total_return': total_return, 'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe})
    return pd.DataFrame(rows)


def build_dynamic_band_lookup(detail_csv: Path, model_code: str = "S3") -> tuple[dict[pd.Timestamp, set[str]], dict[pd.Timestamp, set[str]], dict[pd.Timestamp, set[str]]]:
    df = pd.read_csv(detail_csv, parse_dates=["date", "end_date"])
    df = df.rename(columns={"date": "signal_date"})
    df = df[df["model_code"] == model_code].copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["return_pct_rank"] = df.groupby(["model_code", "horizon", "signal_date"])["fwd_ret"].rank(pct=True, ascending=True)
    df["mdd_pct_rank"] = df.groupby(["model_code", "horizon", "signal_date"])["path_mdd"].rank(pct=True, ascending=True)
    df["composite_score"] = 0.7 * df["return_pct_rank"] + 0.3 * df["mdd_pct_rank"]
    agg = (
        df[df["horizon"].isin(["3M", "6M", "1Y"])]
        .groupby(["signal_date", "ticker"], as_index=False)
        .agg(
            composite_score=("composite_score", "mean"),
            horizons_available=("horizon", "nunique"),
        )
    )
    out_0_10, out_10_30, out_30_50 = {}, {}, {}
    for d, g in agg.groupby("signal_date"):
        g = g.copy()
        if g.empty:
            continue
        q90 = g["composite_score"].quantile(0.90)
        q70 = g["composite_score"].quantile(0.70)
        q50 = g["composite_score"].quantile(0.50)
        out_0_10[pd.Timestamp(d)] = set(g.loc[g["composite_score"] >= q90, "ticker"])
        out_10_30[pd.Timestamp(d)] = set(g.loc[(g["composite_score"] >= q70) & (g["composite_score"] < q90), "ticker"])
        out_30_50[pd.Timestamp(d)] = set(g.loc[(g["composite_score"] >= q50) & (g["composite_score"] < q70), "ticker"])
    return out_0_10, out_10_30, out_30_50


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(UNIVERSE_CSV, dtype={'ticker': str})[['ticker', 'name', 'market', 'mcap']]
    universe['ticker'] = universe['ticker'].astype(str).str.zfill(6)

    bucket0_10, bucket10_30, bucket30_50 = build_dynamic_band_lookup(DETAIL_CSV, model_code='S3')

    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])
    price_wide = prices.pivot(index='date', columns='ticker', values='close').sort_index()

    p = read_sql(S3_DB, 'SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope FROM s3_price_features_daily', parse_dates=['date'])
    p['ticker'] = p['ticker'].astype(str).str.zfill(6)
    f = read_sql(S3_DB, 'SELECT date, ticker, available_from, growth_score, fund_accel_score, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly', parse_dates=['date', 'available_from'])
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)

    signal_dates = latest_s3_dates()
    selected_rows = []
    for d0 in signal_dates:
        p_row = p[p['date'] == d0].copy()
        if p_row.empty:
            continue
        f_snap = latest_fund_snapshot(f, d0)
        t3 = build_t3_score(universe, p_row, f_snap)
        s3 = build_s3_score(universe, p_row, f_snap)
        base = universe[['ticker']].merge(s3, on='ticker', how='left').merge(t3, on='ticker', how='left')
        variants = {
            'baseline_s3': base.copy(),
            't3_filter_s3': base[base['t3_model_score_pct'] >= T3_CUTOFF].copy(),
            'top0_10_bucket_s3': base[base['ticker'].isin(bucket0_10.get(pd.Timestamp(d0), set()))].copy(),
            'top10_30_bucket_s3': base[base['ticker'].isin(bucket10_30.get(pd.Timestamp(d0), set()))].copy(),
            'top30_50_bucket_s3': base[base['ticker'].isin(bucket30_50.get(pd.Timestamp(d0), set()))].copy(),
        }
        for variant, snap in variants.items():
            snap = snap.dropna(subset=['s3_score']).copy()
            chosen = snap.sort_values(['s3_score','ticker'], ascending=[False, True]).head(TOP_N).copy()
            chosen['variant'] = variant
            chosen['signal_date'] = d0
            selected_rows.append(chosen[['variant','signal_date','ticker','s3_score','t3_model_score_pct']])
    selected = pd.concat(selected_rows, ignore_index=True)
    selected.to_csv(OUTDIR / 's3_filter_model_selected_history.csv', index=False, encoding='utf-8-sig')

    nav_rows = []
    perf_rows = []
    variant_last_signal = selected.groupby('variant')['signal_date'].max().to_dict()
    common_end_date = min(pd.Timestamp(v) for v in variant_last_signal.values())
    for variant, _desc in VARIANTS:
        lookup = {pd.Timestamp(d): list(g['ticker']) for d, g in selected[selected['variant'] == variant].groupby('signal_date')}
        nav = 1.0
        series = []
        for i in range(1, len(signal_dates)):
            prev_d = signal_dates[i-1]
            d = signal_dates[i]
            held = lookup.get(prev_d, [])
            if held:
                prev_px = price_wide.loc[prev_d, held] if prev_d in price_wide.index else pd.Series(dtype=float)
                curr_px = price_wide.loc[d, held] if d in price_wide.index else pd.Series(dtype=float)
                m = pd.DataFrame({'prev': prev_px, 'curr': curr_px}).dropna()
                port_ret = float((m['curr']/m['prev'] - 1.0).mean()) if not m.empty else 0.0
            else:
                port_ret = 0.0
            nav *= (1.0 + port_ret)
            series.append({'variant': variant, 'date': d, 'nav': nav, 'holdings_count': len(held)})
        nav_df = pd.DataFrame(series)
        nav_rows.append(nav_df)
        perf = perf_windows(nav_df, end_date=common_end_date)
        if not perf.empty:
            perf['variant'] = variant
            perf_rows.append(perf)
    nav_all = pd.concat(nav_rows, ignore_index=True)
    perf_all = pd.concat(perf_rows, ignore_index=True)
    nav_all.to_csv(OUTDIR / 's3_filter_model_nav_history.csv', index=False, encoding='utf-8-sig')
    perf_all.to_csv(OUTDIR / 's3_filter_model_performance_summary.csv', index=False, encoding='utf-8-sig')

    lines = ['# S3 Filter Model Comparison', '']
    lines.append('Research-only comparison. Band bucket variants use non-overlap dynamic bucket membership by signal date built from combined future `3M/6M/1Y` S3 composite scores for analysis, not deployable live models.')
    lines.append('')
    lines.append(f'Common comparison end date: {common_end_date.date()}')
    lines.append('')
    lines.append('| Variant | Period | Total Return | CAGR | MDD | Sharpe |')
    lines.append('|---|---|---:|---:|---:|---:|')
    order = ['baseline_s3','t3_filter_s3','top0_10_bucket_s3','top10_30_bucket_s3','top30_50_bucket_s3']
    perf_all['variant'] = pd.Categorical(perf_all['variant'], categories=order, ordered=True)
    period_order = {'3M':0,'6M':1,'1Y':2,'2Y':3,'3Y':4}
    perf_all['period_sort'] = perf_all['period'].map(period_order)
    for r in perf_all.sort_values(['variant','period_sort']).itertuples(index=False):
        lines.append(f'| {r.variant} | {r.period} | {r.total_return:.2%} | {r.cagr:.2%} | {r.mdd:.2%} | {r.sharpe:.2f} |')
    (OUTDIR / 's3_filter_model_comparison_review.md').write_text('\n'.join(lines), encoding='utf-8')
    print(perf_all.sort_values(['variant','period_sort']).drop(columns=['period_sort']).to_string(index=False))


if __name__ == '__main__':
    main()
