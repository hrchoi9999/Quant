from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\LOWER_TO_T10_TRANSITION_ANALYSIS"

FEATURES = [
    "growth_score",
    "revenue_yoy",
    "op_income_yoy",
    "score_rank",
    "mom20",
    "vol_ratio_20",
    "fund_accel_score",
    "gs_delta_3m",
    "rev_delta_3m",
    "op_delta_3m",
    "dist_ma60",
    "dist_ma120",
    "ma_stack_gap",
]


def read_sql(db: Path, query: str, parse_dates=None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, parse_dates=parse_dates)
    finally:
        con.close()


def pct_rank(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True)


def build_base_panel() -> pd.DataFrame:
    panel = read_sql(
        RESEARCH_DB,
        """
        SELECT horizon, signal_date, next_signal_date, ticker, name, market, bucket,
               next_bucket, entered_t10_next, entered_t3_next, score, fwd_ret, path_mdd
        FROM s3_bucket_transition_panel
        WHERE model_code='S3'
          AND bucket IN ('OUTSIDE', 'T50_ex_T30', 'T30_ex_T10')
          AND next_bucket IS NOT NULL
        """,
        parse_dates=["signal_date", "next_signal_date"],
    )
    panel["ticker"] = panel["ticker"].astype(str).str.zfill(6)
    return panel


def attach_features(panel: pd.DataFrame) -> pd.DataFrame:
    s2 = read_sql(
        FUND_DB,
        "SELECT date, ticker, growth_score, revenue_yoy, op_income_yoy, score_rank FROM s2_fund_scores_monthly",
        parse_dates=["date"],
    )
    s2["ticker"] = s2["ticker"].astype(str).str.zfill(6)
    s3p = read_sql(
        S3_DB,
        "SELECT ticker, date, close, mom20, vol_ratio_20, breakout60, ma60, ma120, ma60_slope, ma120_slope FROM s3_price_features_daily",
        parse_dates=["date"],
    )
    s3p["ticker"] = s3p["ticker"].astype(str).str.zfill(6)
    s3f = read_sql(
        S3_DB,
        "SELECT ticker, available_from, fund_accel_score, gs_delta_3m, rev_delta_3m, op_delta_3m FROM s3_fund_features_monthly",
        parse_dates=["available_from"],
    )
    s3f["ticker"] = s3f["ticker"].astype(str).str.zfill(6)

    panel = panel.merge(
        s3p,
        left_on=["ticker", "signal_date"],
        right_on=["ticker", "date"],
        how="left",
    ).drop(columns=["date"])

    out = []
    for d0, g in panel.groupby("signal_date"):
        left = g.sort_values("ticker").copy()
        right_s2 = (
            s2[s2["date"] <= d0]
            .sort_values(["ticker", "date"])
            .groupby("ticker", as_index=False)
            .tail(1)
        )
        left = left.merge(
            right_s2[["ticker", "growth_score", "revenue_yoy", "op_income_yoy", "score_rank"]],
            on="ticker",
            how="left",
        )

        right_s3f = (
            s3f[s3f["available_from"] <= d0]
            .sort_values(["ticker", "available_from"])
            .groupby("ticker", as_index=False)
            .tail(1)
        )
        left = left.merge(
            right_s3f[["ticker", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m"]],
            on="ticker",
            how="left",
        )
        out.append(left)
    panel = pd.concat(out, ignore_index=True)

    panel["dist_ma60"] = panel["close"] / panel["ma60"] - 1.0
    panel["dist_ma120"] = panel["close"] / panel["ma120"] - 1.0
    panel["ma_stack_gap"] = panel["ma60"] / panel["ma120"] - 1.0

    for feat in FEATURES:
        panel[f"{feat}_pct"] = panel.groupby(["horizon", "signal_date"])[feat].transform(pct_rank)
    panel["breakout60"] = pd.to_numeric(panel["breakout60"], errors="coerce").fillna(0).astype(int)
    return panel


def summarize(panel: pd.DataFrame):
    work = panel.copy()
    work["label"] = pd.to_numeric(work["entered_t10_next"], errors="coerce").fillna(0).astype(int)
    feat_cols = [f"{f}_pct" for f in FEATURES if f"{f}_pct" in work.columns] + ["breakout60"]

    def summarize_group(df: pd.DataFrame, extra: dict):
        rows = []
        for feat in feat_cols:
            s = pd.to_numeric(df[feat], errors="coerce")
            y = df["label"]
            mask = s.notna() & y.notna()
            if mask.sum() < 30:
                continue
            q_hi = s[mask].quantile(0.8)
            q_lo = s[mask].quantile(0.2)
            rows.append(
                {
                    **extra,
                    "feature": feat,
                    "corr_next_t10": float(s[mask].corr(y[mask])),
                    "mean_pos": float(s[mask & (y == 1)].mean()),
                    "mean_neg": float(s[mask & (y == 0)].mean()),
                    "mean_diff": float(s[mask & (y == 1)].mean() - s[mask & (y == 0)].mean()),
                    "top20_next_t10_rate": float(y[mask & (s >= q_hi)].mean()),
                    "bottom20_next_t10_rate": float(y[mask & (s <= q_lo)].mean()),
                    "lift": float(y[mask & (s >= q_hi)].mean() - y[mask & (s <= q_lo)].mean()),
                    "n": int(mask.sum()),
                }
            )
        return rows

    overall_rows = summarize_group(work, {})
    by_h_rows = []
    by_bucket_rows = []
    for horizon, hg in work.groupby("horizon"):
        by_h_rows.extend(summarize_group(hg, {"horizon": horizon}))
    for (horizon, bucket), bg in work.groupby(["horizon", "bucket"]):
        by_bucket_rows.extend(summarize_group(bg, {"horizon": horizon, "bucket": bucket}))

    overall = pd.DataFrame(overall_rows).sort_values(["corr_next_t10", "lift"], ascending=[False, False]).reset_index(drop=True)
    by_h = pd.DataFrame(by_h_rows).sort_values(["horizon", "corr_next_t10", "lift"], ascending=[True, False, False]).reset_index(drop=True)
    by_bucket = pd.DataFrame(by_bucket_rows).sort_values(["horizon", "bucket", "corr_next_t10", "lift"], ascending=[True, True, False, False]).reset_index(drop=True)
    return overall, by_h, by_bucket


def save_db(panel: pd.DataFrame, overall: pd.DataFrame, by_h: pd.DataFrame, by_bucket: pd.DataFrame) -> None:
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        panel.to_sql("s3_lower_to_t10_feature_panel", con, if_exists="replace", index=False)
        overall.to_sql("s3_lower_to_t10_feature_summary", con, if_exists="replace", index=False)
        by_h.to_sql("s3_lower_to_t10_feature_summary_by_horizon", con, if_exists="replace", index=False)
        by_bucket.to_sql("s3_lower_to_t10_feature_summary_by_bucket", con, if_exists="replace", index=False)
    finally:
        con.close()


def render_md(panel: pd.DataFrame, overall: pd.DataFrame, by_h: pd.DataFrame, by_bucket: pd.DataFrame) -> str:
    pos_rate = float(panel["entered_t10_next"].mean())
    lines = ["# Lower Buckets To T10_ex_T3 Transition Feature Analysis", ""]
    lines.append(f"- panel rows: `{len(panel):,}`")
    lines.append(f"- unique tickers: `{panel['ticker'].nunique():,}`")
    lines.append(f"- next-step T10_ex_T3 transition rate: `{pos_rate:.2%}`")
    lines.append("")
    lines.append("## Overall top features")
    lines.append("| Feature | Corr(next T10) | Mean diff | Top20 next T10 rate | Bottom20 next T10 rate | Lift | N |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in overall.head(12).itertuples(index=False):
        lines.append(
            f"| {r.feature} | {r.corr_next_t10:.4f} | {r.mean_diff:.4f} | {r.top20_next_t10_rate:.2%} | {r.bottom20_next_t10_rate:.2%} | {r.lift:.2%} | {r.n} |"
        )
    lines.append("")
    lines.append("## By horizon top signals")
    for horizon, hg in by_h.groupby("horizon"):
        lines.append(f"### {horizon}")
        lines.append("| Feature | Corr(next T10) | Lift | N |")
        lines.append("|---|---:|---:|---:|")
        for r in hg.head(8).itertuples(index=False):
            lines.append(f"| {r.feature} | {r.corr_next_t10:.4f} | {r.lift:.2%} | {r.n} |")
        lines.append("")
    lines.append("## By horizon and source bucket")
    for (horizon, bucket), bg in by_bucket.groupby(["horizon", "bucket"]):
        lines.append(f"### {horizon} / {bucket}")
        lines.append("| Feature | Corr(next T10) | Lift | N |")
        lines.append("|---|---:|---:|---:|")
        for r in bg.head(6).itertuples(index=False):
            lines.append(f"| {r.feature} | {r.corr_next_t10:.4f} | {r.lift:.2%} | {r.n} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    panel = attach_features(build_base_panel())
    overall, by_h, by_bucket = summarize(panel)
    save_db(panel, overall, by_h, by_bucket)
    panel.to_csv(OUTDIR / "lower_to_t10_feature_panel.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(OUTDIR / "lower_to_t10_feature_summary.csv", index=False, encoding="utf-8-sig")
    by_h.to_csv(OUTDIR / "lower_to_t10_feature_summary_by_horizon.csv", index=False, encoding="utf-8-sig")
    by_bucket.to_csv(OUTDIR / "lower_to_t10_feature_summary_by_bucket.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "lower_to_t10_feature_analysis.md").write_text(render_md(panel, overall, by_h, by_bucket), encoding="utf-8")
    print(overall.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
