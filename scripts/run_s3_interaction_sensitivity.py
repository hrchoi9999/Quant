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
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_INTERACTION_SENSITIVITY"
TOP_N = 20
PERF_WINDOWS = [("3M", 84), ("6M", 168), ("1Y", 365)]
BUCKET_ORDER = ["T3", "T10_ex_T3", "T30_ex_T10", "T50_ex_T30"]

BASE = {
    "fund_level": 0.30,
    "fund_accel": 0.20,
    "momentum_block": 0.40,
    "trend_block": 0.10,
}
MOMENTUM_SPLIT = {"mom20": 0.625, "vol_ratio": 0.25, "breakout": 0.125}

INTERACTION_VARIANTS = [
    {"variant_id": "baseline_s3", "fund_level": 0.30, "fund_accel": 0.20, "momentum_block": 0.40, "trend_block": 0.10},
    {"variant_id": "mom35_acc25", "fund_level": 0.35, "fund_accel": 0.25, "momentum_block": 0.35, "trend_block": 0.05},
    {"variant_id": "mom35_trend05", "fund_level": 0.40, "fund_accel": 0.20, "momentum_block": 0.35, "trend_block": 0.05},
    {"variant_id": "acc25_trend05", "fund_level": 0.35, "fund_accel": 0.25, "momentum_block": 0.35, "trend_block": 0.05},
    {"variant_id": "mom35_acc25_trend05", "fund_level": 0.35, "fund_accel": 0.25, "momentum_block": 0.35, "trend_block": 0.05},
    {"variant_id": "mom30_acc25_trend05", "fund_level": 0.40, "fund_accel": 0.25, "momentum_block": 0.30, "trend_block": 0.05},
    {"variant_id": "mom35_acc30_trend05", "fund_level": 0.30, "fund_accel": 0.30, "momentum_block": 0.35, "trend_block": 0.05},
    {"variant_id": "mom30_acc30_trend05", "fund_level": 0.35, "fund_accel": 0.30, "momentum_block": 0.30, "trend_block": 0.05},
]


def read_sql(db: Path, query: str, params=(), parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params, parse_dates=parse_dates)
    finally:
        con.close()


def latest_s3_dates() -> list[pd.Timestamp]:
    run = read_sql(QS_DB, "SELECT run_id FROM run_runs WHERE model_code='S3' ORDER BY created_at DESC LIMIT 1")
    run_id = str(run.loc[0, "run_id"])
    dates = read_sql(QS_DETAIL_DB, "SELECT DISTINCT date FROM run_signal_details_s3 WHERE run_id=? ORDER BY date", (run_id,), parse_dates=["date"])
    return sorted(pd.to_datetime(dates["date"].dropna().unique()))


def latest_fund_snapshot(fund_df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    w = fund_df[fund_df["available_from"] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(["ticker", "available_from", "date"]).groupby("ticker", as_index=False).tail(1)


def build_bucket_panel() -> pd.DataFrame:
    base = read_sql(RESEARCH_DB, "SELECT model_code, horizon, signal_date, end_date, ticker, top_50pct_flag FROM universe_top_50pct_candidates WHERE model_code='S3'", parse_dates=["signal_date", "end_date"])
    t3 = read_sql(RESEARCH_DB, "SELECT model_code, horizon, signal_date, end_date, ticker, top_3pct_flag FROM universe_top_3pct_candidates WHERE model_code='S3'", parse_dates=["signal_date", "end_date"])
    t10 = read_sql(RESEARCH_DB, "SELECT model_code, horizon, signal_date, end_date, ticker, top_10pct_flag FROM universe_top_10pct_candidates WHERE model_code='S3'", parse_dates=["signal_date", "end_date"])
    t30 = read_sql(RESEARCH_DB, "SELECT model_code, horizon, signal_date, end_date, ticker, top_30pct_flag FROM universe_top_30pct_candidates WHERE model_code='S3'", parse_dates=["signal_date", "end_date"])
    for df in (base, t3, t10, t30):
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    keys = ["model_code", "horizon", "signal_date", "end_date", "ticker"]
    panel = base.merge(t3, on=keys, how="left").merge(t10, on=keys, how="left").merge(t30, on=keys, how="left")
    for c in ["top_3pct_flag", "top_10pct_flag", "top_30pct_flag", "top_50pct_flag"]:
        panel[c] = pd.to_numeric(panel[c], errors="coerce").fillna(0).astype(int)
    panel["bucket"] = None
    panel.loc[panel["top_3pct_flag"] == 1, "bucket"] = "T3"
    panel.loc[(panel["top_10pct_flag"] == 1) & (panel["top_3pct_flag"] == 0), "bucket"] = "T10_ex_T3"
    panel.loc[(panel["top_30pct_flag"] == 1) & (panel["top_10pct_flag"] == 0), "bucket"] = "T30_ex_T10"
    panel.loc[(panel["top_50pct_flag"] == 1) & (panel["top_30pct_flag"] == 0), "bucket"] = "T50_ex_T30"
    return panel[panel["bucket"].notna()].copy()


def build_s3_score(universe: pd.DataFrame, p_row: pd.DataFrame, fund_snap: pd.DataFrame, spec: dict[str, float]) -> pd.DataFrame:
    snap = universe.merge(p_row, on="ticker", how="left").merge(fund_snap[["ticker", "growth_score", "fund_accel_score"]], on="ticker", how="left")
    snap["mom20_pct"] = snap["mom20"].rank(pct=True)
    snap["vol_ratio_pct"] = snap["vol_ratio_20"].rank(pct=True)
    snap["fund_level_pct"] = snap["growth_score"].rank(pct=True)
    snap["fund_accel_pct"] = snap["fund_accel_score"].rank(pct=True)
    trend_bonus = ((snap["ma60"] > snap["ma120"]) & (snap["ma60_slope"] > 0)).astype(float)
    snap["s3_score"] = (
        spec["fund_level"] * snap["fund_level_pct"].fillna(0)
        + spec["fund_accel"] * snap["fund_accel_pct"].fillna(0)
        + (spec["momentum_block"] * MOMENTUM_SPLIT["mom20"]) * snap["mom20_pct"].fillna(0)
        + (spec["momentum_block"] * MOMENTUM_SPLIT["vol_ratio"]) * snap["vol_ratio_pct"].fillna(0)
        + (spec["momentum_block"] * MOMENTUM_SPLIT["breakout"]) * snap["breakout60"].fillna(0).astype(float)
        + spec["trend_block"] * trend_bonus
    )
    return snap[["ticker", "s3_score"]]


def perf_windows(nav_df: pd.DataFrame) -> pd.DataFrame:
    nav_df = nav_df.sort_values("date").copy()
    last = pd.to_datetime(nav_df["date"].max())
    rows = []
    for label, days in PERF_WINDOWS:
        sub = nav_df[nav_df["date"] >= (last - pd.Timedelta(days=days))].copy()
        if len(sub) < 2:
            continue
        start = float(sub["nav"].iloc[0]); end = float(sub["nav"].iloc[-1])
        total_return = end / start - 1.0
        years = max((pd.to_datetime(sub["date"].iloc[-1]) - pd.to_datetime(sub["date"].iloc[0])).days / 365.25, 1 / 52)
        cagr = (end / start) ** (1 / years) - 1.0 if start > 0 else np.nan
        dd = sub["nav"] / sub["nav"].cummax() - 1.0
        mdd = float(dd.min())
        rows.append({"period": label, "total_return": total_return, "cagr": cagr, "mdd": mdd})
    return pd.DataFrame(rows)


def summarize_accuracy(selected_panel: pd.DataFrame, bucket_panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant_id in sorted(selected_panel["variant_id"].unique()):
        chosen = selected_panel[selected_panel["variant_id"] == variant_id][["signal_date", "ticker"]].copy()
        chosen["selected_flag"] = 1
        merged = bucket_panel.merge(chosen, on=["signal_date", "ticker"], how="left")
        merged["selected_flag"] = pd.to_numeric(merged["selected_flag"], errors="coerce").fillna(0).astype(int)
        base_rate = float(merged["selected_flag"].mean())
        row = {"variant_id": variant_id, "base_selection_rate": base_rate}
        for bucket in BUCKET_ORDER:
            bg = merged[merged["bucket"] == bucket]
            capture = float(bg["selected_flag"].mean()) if not bg.empty else np.nan
            lift = float(capture / base_rate) if base_rate > 0 and pd.notna(capture) else np.nan
            row[f"{bucket}_accuracy"] = capture
            row[f"{bucket}_lift"] = lift
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})[["ticker", "name", "market", "mcap"]]
    universe["ticker"] = universe["ticker"].astype(str).str.zfill(6)

    prices = read_sql(PRICE_DB, "SELECT ticker, date, close FROM prices_daily", parse_dates=["date"])
    prices["ticker"] = prices["ticker"].astype(str).str.zfill(6)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.dropna(subset=["close"]).sort_values(["ticker", "date"])
    price_wide = prices.pivot(index="date", columns="ticker", values="close").sort_index()

    p = read_sql(S3_DB, "SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope FROM s3_price_features_daily", parse_dates=["date"])
    p["ticker"] = p["ticker"].astype(str).str.zfill(6)
    f = read_sql(S3_DB, "SELECT date, ticker, available_from, growth_score, fund_accel_score FROM s3_fund_features_monthly", parse_dates=["date", "available_from"])
    f["ticker"] = f["ticker"].astype(str).str.zfill(6)

    signal_dates = latest_s3_dates()

    meta = pd.DataFrame(INTERACTION_VARIANTS)
    meta.to_csv(OUTDIR / 's3_interaction_variant_meta.csv', index=False, encoding='utf-8-sig')

    selected_rows = []
    for d0 in signal_dates:
        p_row = p[p['date'] == d0].copy()
        if p_row.empty:
            continue
        f_snap = latest_fund_snapshot(f, d0)
        for spec in INTERACTION_VARIANTS:
            snap = build_s3_score(universe, p_row, f_snap, spec).dropna(subset=['s3_score']).copy()
            chosen = snap.sort_values(['s3_score', 'ticker'], ascending=[False, True]).head(TOP_N).copy()
            chosen['variant_id'] = spec['variant_id']
            chosen['signal_date'] = d0
            chosen['selected'] = 1
            selected_rows.append(chosen[['variant_id', 'signal_date', 'ticker', 's3_score', 'selected']])
    selected = pd.concat(selected_rows, ignore_index=True)
    selected.to_csv(OUTDIR / 's3_interaction_selected_history.csv', index=False, encoding='utf-8-sig')

    nav_rows = []
    perf_rows = []
    for variant_id, vg in selected.groupby('variant_id'):
        lookup = {pd.Timestamp(d): list(g['ticker']) for d, g in vg.groupby('signal_date')}
        nav = 1.0
        series = []
        for i in range(1, len(signal_dates)):
            prev_d = signal_dates[i - 1]
            d = signal_dates[i]
            held = lookup.get(prev_d, [])
            if held:
                prev_px = price_wide.loc[prev_d, held] if prev_d in price_wide.index else pd.Series(dtype=float)
                curr_px = price_wide.loc[d, held] if d in price_wide.index else pd.Series(dtype=float)
                m = pd.DataFrame({'prev': prev_px, 'curr': curr_px}).dropna()
                port_ret = float((m['curr'] / m['prev'] - 1.0).mean()) if not m.empty else 0.0
            else:
                port_ret = 0.0
            nav *= (1.0 + port_ret)
            series.append({'variant_id': variant_id, 'date': d, 'nav': nav})
        nav_df = pd.DataFrame(series)
        nav_rows.append(nav_df)
        perf = perf_windows(nav_df)
        if not perf.empty:
            perf['variant_id'] = variant_id
            perf_rows.append(perf)
    nav_all = pd.concat(nav_rows, ignore_index=True)
    perf_all = pd.concat(perf_rows, ignore_index=True)
    nav_all.to_csv(OUTDIR / 's3_interaction_nav_history.csv', index=False, encoding='utf-8-sig')
    perf_all.to_csv(OUTDIR / 's3_interaction_performance_summary_long.csv', index=False, encoding='utf-8-sig')

    perf_pivot = perf_all.pivot(index='variant_id', columns='period', values=['total_return', 'mdd'])
    perf_pivot.columns = [f'{a}_{b.lower()}' for a, b in perf_pivot.columns]
    perf_pivot = perf_pivot.reset_index()

    accuracy = summarize_accuracy(selected, build_bucket_panel())
    summary = meta.merge(accuracy, on='variant_id', how='left').merge(perf_pivot, on='variant_id', how='left')
    summary = summary.rename(columns={'total_return_3m': 'ret_3m', 'total_return_6m': 'ret_6m', 'total_return_1y': 'ret_1y', 'mdd_1y': 'mdd_1y'})
    summary['rank_key'] = (
        summary['T3_accuracy'].fillna(0) * 4.0
        + summary['T10_ex_T3_accuracy'].fillna(0) * 3.0
        + summary['ret_6m'].fillna(0) * 1.5
        + summary['ret_1y'].fillna(0) * 1.5
        + summary['mdd_1y'].fillna(-1.0)
    )
    summary = summary.sort_values('rank_key', ascending=False)
    summary.to_csv(OUTDIR / 's3_interaction_sensitivity_summary.csv', index=False, encoding='utf-8-sig')

    lines = ['# S3 Interaction Sensitivity Analysis', '']
    lines.append('| Variant | Fund Level | Fund Accel | Momentum Block | Trend Block | T3 Accuracy | T10_ex_T3 Accuracy | 3M Return | 6M Return | 1Y Return | 1Y MDD |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for r in summary.itertuples(index=False):
        lines.append(f'| {r.variant_id} | {r.fund_level:.2f} | {r.fund_accel:.2f} | {r.momentum_block:.2f} | {r.trend_block:.2f} | {r.T3_accuracy:.2%} | {r.T10_ex_T3_accuracy:.2%} | {r.ret_3m:.2%} | {r.ret_6m:.2%} | {r.ret_1y:.2%} | {r.mdd_1y:.2%} |')
    (OUTDIR / 's3_interaction_sensitivity_review.md').write_text('\n'.join(lines), encoding='utf-8')
    print(summary[['variant_id', 'fund_level', 'fund_accel', 'momentum_block', 'trend_block', 'T3_accuracy', 'T10_ex_T3_accuracy', 'ret_3m', 'ret_6m', 'ret_1y', 'mdd_1y']].to_string(index=False))


if __name__ == '__main__':
    main()
