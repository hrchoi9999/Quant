from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
S3_HISTORY = PROJECT_ROOT / r"reports\backtest_s3_dev\s3_holdings_history_top20_2013-10-14_2026-03-25.csv"
DETAIL_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260330\selected_vs_not_selected_3m_6m_1y_detail.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260331_s3_backfill"
HORIZONS = [(12, '3M'), (24, '6M'), (52, '1Y')]


def read_sql(db: Path, q: str, params=None, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(q, con, params=params or (), parse_dates=parse_dates)
    finally:
        con.close()


def make_end_map(signal_dates, horizon_n):
    dts = sorted(pd.to_datetime(pd.Series(signal_dates).dropna().unique()))
    return {dts[i]: dts[i + horizon_n] for i in range(len(dts) - horizon_n)}


def compute_window_stats(cand: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    price_groups = {t: g[['date', 'close']].reset_index(drop=True) for t, g in prices.groupby('ticker')}
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
            'score': float(row.score) if pd.notna(row.score) else np.nan,
            'fwd_ret': float(rel.iloc[-1] - 1.0),
            'path_mdd': float(dd.min()),
        })
    return pd.DataFrame(rows)


def latest_fund_snapshot(fund_df, asof):
    w = fund_df[fund_df['available_from'] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(['ticker', 'available_from', 'date']).groupby('ticker', as_index=False).tail(1)


def build_s3_stats() -> pd.DataFrame:
    universe = pd.read_csv(UNIVERSE_CSV, dtype={'ticker': str})[['ticker', 'name', 'market', 'mcap']]
    universe['ticker'] = universe['ticker'].astype(str).str.zfill(6)

    selected = pd.read_csv(S3_HISTORY, dtype={'ticker': str}, parse_dates=['date'])[['date', 'ticker']]
    selected['ticker'] = selected['ticker'].astype(str).str.zfill(6)

    p = read_sql(S3_DB, 'SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope FROM s3_price_features_daily', parse_dates=['date'])
    p['ticker'] = p['ticker'].astype(str).str.zfill(6)
    f = read_sql(S3_DB, 'SELECT date, ticker, available_from, growth_score, fund_accel_score FROM s3_fund_features_monthly', parse_dates=['date', 'available_from'])
    f['ticker'] = f['ticker'].astype(str).str.zfill(6)
    prices = read_sql(PRICE_DB, 'SELECT ticker, date, close FROM prices_daily', parse_dates=['date'])
    prices['ticker'] = prices['ticker'].astype(str).str.zfill(6)
    prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
    prices = prices.dropna(subset=['close']).sort_values(['ticker', 'date'])

    out = []
    for h_n, h_label in HORIZONS:
        end_map = make_end_map(selected['date'].unique(), h_n)
        for d0, d1 in end_map.items():
            ps = p[p['date'] == d0].copy()
            fs = latest_fund_snapshot(f, d0)
            snap = universe.merge(ps, on='ticker', how='left').merge(fs[['ticker', 'growth_score', 'fund_accel_score']], on='ticker', how='left')
            snap['mom20_pct'] = snap['mom20'].rank(pct=True)
            snap['vol_ratio_pct'] = snap['vol_ratio_20'].rank(pct=True)
            snap['fund_level_pct'] = snap['growth_score'].rank(pct=True)
            snap['fund_accel_pct'] = snap['fund_accel_score'].rank(pct=True)
            trend_bonus = ((snap['ma60'] > snap['ma120']) & (snap['ma60_slope'] > 0)).astype(int)
            snap['score'] = (
                0.30 * snap['fund_level_pct'].fillna(0)
                + 0.20 * snap['fund_accel_pct'].fillna(0)
                + 0.25 * snap['mom20_pct'].fillna(0)
                + 0.10 * snap['vol_ratio_pct'].fillna(0)
                + 0.05 * snap['breakout60'].fillna(0).astype(int)
                + 0.10 * trend_bonus
            )
            sel_set = set(selected.loc[selected['date'] == d0, 'ticker'])
            snap['date'] = d0
            snap['end_date'] = d1
            snap['horizon'] = h_label
            snap['selected'] = snap['ticker'].isin(sel_set).astype(int)
            out.append(snap[['date', 'end_date', 'horizon', 'ticker', 'selected', 'score']])
    cand = pd.concat(out, ignore_index=True)
    stats = compute_window_stats(cand, prices)
    stats['model_code'] = 'S3'
    return stats[['model_code', 'horizon', 'date', 'end_date', 'ticker', 'selected', 'score', 'fwd_ret', 'path_mdd']]


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    stats = build_s3_stats()
    stats['ticker'] = stats['ticker'].astype(str).str.zfill(6)

    backup = DETAIL_CSV.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    shutil.copy2(DETAIL_CSV, backup)

    base = pd.read_csv(DETAIL_CSV, dtype={'ticker': str})
    base['ticker'] = base['ticker'].astype(str).str.zfill(6)
    merged = pd.concat([base[base['model_code'] != 'S3'], stats], ignore_index=True)
    merged = merged.sort_values(['model_code', 'horizon', 'date', 'ticker']).reset_index(drop=True)
    merged.to_csv(DETAIL_CSV, index=False, encoding='utf-8-sig')
    stats.to_csv(OUTDIR / 's3_selected_vs_not_selected_3m_6m_1y_detail_backfill.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's3_detail_backfill_summary.txt').write_text(
        f"rows={len(stats):,}\nmin_date={stats['date'].min()}\nmax_date={stats['date'].max()}\nbackup={backup}\n",
        encoding='utf-8'
    )
    print(f"[OK] rebuilt S3 detail rows={len(stats):,} range={stats['date'].min()}~{stats['date'].max()}")
    print(f"[OK] backup -> {backup}")


if __name__ == '__main__':
    main()
