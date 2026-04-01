from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_DISCOVERY_PROTOTYPE"
ASOF_DATE = pd.Timestamp("2026-03-26")
STAGE1_TOP_N = 40
STAGE2_TOP_N = 12
WATCHLIST_TOP_N = 20


def read_sql(db: Path, query: str, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, parse_dates=parse_dates)
    finally:
        con.close()


def latest_snapshot(df: pd.DataFrame, date_col: str, asof: pd.Timestamp) -> pd.DataFrame:
    w = df[df[date_col] <= asof].copy()
    if w.empty:
        return w
    return w.sort_values(["ticker", date_col]).groupby("ticker", as_index=False).tail(1)


def pct_rank(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True)


def build_panel() -> pd.DataFrame:
    universe = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})[["ticker", "name", "market", "mcap"]]
    universe["ticker"] = universe["ticker"].astype(str).str.zfill(6)

    p = read_sql(
        S3_DB,
        "SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120, ma60_slope, ma120_slope FROM s3_price_features_daily",
        parse_dates=["date"],
    )
    p["ticker"] = p["ticker"].astype(str).str.zfill(6)
    latest_price_date = pd.to_datetime(p.loc[p["date"] <= ASOF_DATE, "date"].max())
    p_row = p[p["date"] == latest_price_date].copy()

    s2 = read_sql(
        FUND_DB,
        "SELECT date, ticker, growth_score, revenue_yoy, op_income_yoy, score_rank FROM s2_fund_scores_monthly",
        parse_dates=["date"],
    )
    s2["ticker"] = s2["ticker"].astype(str).str.zfill(6)
    s2_row = latest_snapshot(s2, "date", ASOF_DATE)
    latest_s2_date = pd.to_datetime(s2_row["date"].max()) if not s2_row.empty else pd.NaT

    s3f = read_sql(
        S3_DB,
        "SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly",
        parse_dates=["available_from"],
    )
    s3f["ticker"] = s3f["ticker"].astype(str).str.zfill(6)
    s3f_row = latest_snapshot(s3f, "available_from", ASOF_DATE)
    latest_fund_date = pd.to_datetime(s3f_row["available_from"].max()) if not s3f_row.empty else pd.NaT

    snap = universe.merge(p_row, on="ticker", how="left").merge(
        s2_row[["ticker", "date", "growth_score", "revenue_yoy", "op_income_yoy", "score_rank"]],
        on="ticker", how="left"
    ).merge(
        s3f_row[["ticker", "available_from", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m"]],
        on="ticker", how="left"
    )

    snap["dist_ma60"] = snap["close"] / snap["ma60"] - 1.0
    snap["dist_ma120"] = snap["close"] / snap["ma120"] - 1.0
    snap["ma_stack_gap"] = snap["ma60"] / snap["ma120"] - 1.0

    feature_cols = [
        "growth_score", "revenue_yoy", "op_income_yoy", "score_rank",
        "mom20", "vol_ratio_20", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m",
        "dist_ma60", "dist_ma120", "ma_stack_gap",
    ]
    for c in feature_cols:
        snap[c] = pd.to_numeric(snap[c], errors="coerce")
        snap[f"{c}_pct"] = pct_rank(snap[c])

    snap["breakout60"] = pd.to_numeric(snap["breakout60"], errors="coerce").fillna(0).astype(float)

    # Stage 1: lower buckets -> T10_ex_T3
    snap["stage1_t10_score"] = (
        0.24 * snap["op_income_yoy_pct"].fillna(0)
        + 0.22 * snap["revenue_yoy_pct"].fillna(0)
        + 0.18 * snap["dist_ma120_pct"].fillna(0)
        + 0.18 * snap["ma_stack_gap_pct"].fillna(0)
        + 0.10 * snap["dist_ma60_pct"].fillna(0)
        + 0.08 * snap["op_delta_3m_pct"].fillna(0)
    )

    # Stage 2: T10_ex_T3 -> T3
    snap["stage2_t3_score"] = (
        0.24 * snap["revenue_yoy_pct"].fillna(0)
        + 0.20 * snap["dist_ma120_pct"].fillna(0)
        + 0.18 * snap["ma_stack_gap_pct"].fillna(0)
        + 0.16 * snap["dist_ma60_pct"].fillna(0)
        + 0.12 * snap["op_income_yoy_pct"].fillna(0)
        + 0.10 * snap["mom20_pct"].fillna(0)
    )

    snap["stage1_t10_rank"] = snap["stage1_t10_score"].rank(method="first", ascending=False)
    snap["stage2_t3_rank_all"] = snap["stage2_t3_score"].rank(method="first", ascending=False)
    snap["asof_date"] = ASOF_DATE
    snap["price_feature_date"] = latest_price_date
    snap["s2_snapshot_date"] = latest_s2_date
    snap["fund_snapshot_date"] = latest_fund_date
    return snap


def save_db(panel: pd.DataFrame) -> None:
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        panel.to_sql("s3_two_stage_discovery_snapshot", con, if_exists="replace", index=False)
    finally:
        con.close()


def render_md(summary: dict, stage1_top: pd.DataFrame, stage2_top: pd.DataFrame, overlap: pd.DataFrame) -> str:
    lines = ["# S3 Two-Stage Discovery Prototype", ""]
    lines.append(f"- asof_date: `{summary['asof_date']}`")
    lines.append(f"- price_feature_date: `{summary['price_feature_date']}`")
    lines.append(f"- s2_snapshot_date: `{summary['s2_snapshot_date']}`")
    lines.append(f"- fund_snapshot_date: `{summary['fund_snapshot_date']}`")
    lines.append(f"- universe_size: `{summary['universe_size']}`")
    lines.append(f"- stage1_top_n: `{summary['stage1_top_n']}`")
    lines.append(f"- stage2_top_n: `{summary['stage2_top_n']}`")
    lines.append("")
    lines.append("## Stage 1 score idea")
    lines.append("- target: `T30_ex_T10 -> T10_ex_T3`")
    lines.append("- emphasis: `op_income_yoy`, `revenue_yoy`, `dist_ma120`, `ma_stack_gap`, `dist_ma60`, `op_delta_3m`")
    lines.append("")
    lines.append("## Stage 2 score idea")
    lines.append("- target: `T10_ex_T3 -> T3`")
    lines.append("- emphasis: `revenue_yoy`, `dist_ma120`, `ma_stack_gap`, `dist_ma60`, `op_income_yoy`, `mom20`")
    lines.append("")
    lines.append("## Overlap summary")
    lines.append(f"- stage1 top40 vs stage2 top12 overlap: `{len(overlap)}`")
    lines.append("")
    lines.append("## Stage 1 top 10")
    lines.append("| Rank | Ticker | Name | Market | Stage1 | Stage2 |")
    lines.append("|---:|---|---|---|---:|---:|")
    for r in stage1_top.head(10).itertuples(index=False):
        lines.append(f"| {int(r.stage1_t10_rank)} | {r.ticker} | {r.name} | {r.market} | {r.stage1_t10_score:.4f} | {r.stage2_t3_score:.4f} |")
    lines.append("")
    lines.append("## Stage 2 top 12")
    lines.append("| Rank | Ticker | Name | Market | Stage1 Rank | Stage2 |")
    lines.append("|---:|---|---|---|---:|---:|")
    for i, r in enumerate(stage2_top.itertuples(index=False), start=1):
        lines.append(f"| {i} | {r.ticker} | {r.name} | {r.market} | {int(r.stage1_t10_rank)} | {r.stage2_t3_score:.4f} |")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    snap = build_panel().dropna(subset=["stage1_t10_score", "stage2_t3_score"]).copy()
    save_db(snap)

    base_cols = [
        "asof_date", "price_feature_date", "s2_snapshot_date", "fund_snapshot_date",
        "ticker", "name", "market", "mcap",
        "stage1_t10_rank", "stage1_t10_score", "stage2_t3_rank_all", "stage2_t3_score",
        "revenue_yoy", "op_income_yoy", "fund_accel_score", "rev_delta_3m", "op_delta_3m",
        "mom20", "dist_ma60", "dist_ma120", "ma_stack_gap", "breakout60"
    ]
    snap[base_cols].sort_values(["stage1_t10_rank", "ticker"]).to_csv(OUTDIR / "s3_two_stage_full_rank_2026-03-26.csv", index=False, encoding="utf-8-sig")

    stage1_top = snap.sort_values(["stage1_t10_rank", "ticker"]).head(STAGE1_TOP_N).copy()
    stage1_top[base_cols].to_csv(OUTDIR / "s3_stage1_t10_candidates_2026-03-26.csv", index=False, encoding="utf-8-sig")

    stage2_pool = stage1_top.sort_values(["stage2_t3_score", "ticker"], ascending=[False, True]).copy()
    stage2_top = stage2_pool.head(STAGE2_TOP_N).copy()
    stage2_top[base_cols].to_csv(OUTDIR / "s3_stage2_t3_candidates_2026-03-26.csv", index=False, encoding="utf-8-sig")

    watch = snap.sort_values(["stage2_t3_score", "ticker"], ascending=[False, True]).head(WATCHLIST_TOP_N).copy()
    watch[base_cols].to_csv(OUTDIR / "s3_stage2_watchlist_top20_2026-03-26.csv", index=False, encoding="utf-8-sig")

    overlap = stage1_top.merge(stage2_top[["ticker"]], on="ticker", how="inner")
    overlap[base_cols].to_csv(OUTDIR / "s3_two_stage_overlap_2026-03-26.csv", index=False, encoding="utf-8-sig")

    summary = {
        "asof_date": str(ASOF_DATE.date()),
        "price_feature_date": str(pd.to_datetime(snap["price_feature_date"].iloc[0]).date()),
        "s2_snapshot_date": str(pd.to_datetime(snap["s2_snapshot_date"].iloc[0]).date()) if pd.notna(snap["s2_snapshot_date"].iloc[0]) else "NA",
        "fund_snapshot_date": str(pd.to_datetime(snap["fund_snapshot_date"].iloc[0]).date()) if pd.notna(snap["fund_snapshot_date"].iloc[0]) else "NA",
        "universe_size": int(len(snap)),
        "stage1_top_n": STAGE1_TOP_N,
        "stage2_top_n": STAGE2_TOP_N,
        "stage1_kospi": int((stage1_top["market"] == "KOSPI").sum()),
        "stage1_kosdaq": int((stage1_top["market"] == "KOSDAQ").sum()),
        "stage2_kospi": int((stage2_top["market"] == "KOSPI").sum()),
        "stage2_kosdaq": int((stage2_top["market"] == "KOSDAQ").sum()),
    }
    pd.DataFrame([summary]).to_csv(OUTDIR / "s3_two_stage_summary_2026-03-26.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s3_two_stage_discovery_prototype_2026-03-26.md").write_text(
        render_md(summary, stage1_top, stage2_top, overlap), encoding="utf-8"
    )
    print(pd.DataFrame([summary]).to_string(index=False))


if __name__ == "__main__":
    main()
