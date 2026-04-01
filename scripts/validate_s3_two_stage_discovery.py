from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
RESEARCH_DB = PROJECT_ROOT / r"data\db\model_research.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_DISCOVERY_VALIDATION"
STAGE1_TOP_N = 40
STAGE2_TOP_N = 12
LOWER_BUCKETS = ["OUTSIDE", "T50_ex_T30", "T30_ex_T10"]


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
        SELECT model_code, horizon, signal_date, next_signal_date, ticker, name, market, bucket,
               next_bucket, entered_t10_next, entered_t3_next, score, fwd_ret, path_mdd
        FROM s3_bucket_transition_panel
        WHERE model_code='S3' AND next_bucket IS NOT NULL
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

    features = [
        "growth_score", "revenue_yoy", "op_income_yoy", "score_rank",
        "mom20", "vol_ratio_20", "fund_accel_score", "gs_delta_3m", "rev_delta_3m", "op_delta_3m",
        "dist_ma60", "dist_ma120", "ma_stack_gap",
    ]
    for feat in features:
        panel[feat] = pd.to_numeric(panel[feat], errors="coerce")
        panel[f"{feat}_pct"] = panel.groupby(["horizon", "signal_date"])[feat].transform(pct_rank)
    panel["breakout60"] = pd.to_numeric(panel["breakout60"], errors="coerce").fillna(0).astype(float)
    return panel


def add_scores(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["stage1_t10_score"] = (
        0.24 * panel["op_income_yoy_pct"].fillna(0)
        + 0.22 * panel["revenue_yoy_pct"].fillna(0)
        + 0.18 * panel["dist_ma120_pct"].fillna(0)
        + 0.18 * panel["ma_stack_gap_pct"].fillna(0)
        + 0.10 * panel["dist_ma60_pct"].fillna(0)
        + 0.08 * panel["op_delta_3m_pct"].fillna(0)
    )
    panel["stage2_t3_score"] = (
        0.24 * panel["revenue_yoy_pct"].fillna(0)
        + 0.20 * panel["dist_ma120_pct"].fillna(0)
        + 0.18 * panel["ma_stack_gap_pct"].fillna(0)
        + 0.16 * panel["dist_ma60_pct"].fillna(0)
        + 0.12 * panel["op_income_yoy_pct"].fillna(0)
        + 0.10 * panel["mom20_pct"].fillna(0)
    )
    return panel


def evaluate(panel: pd.DataFrame):
    rows = []
    selected_rows = []
    for (horizon, signal_date), g in panel.groupby(["horizon", "signal_date"]):
        lower = g[g["bucket"].isin(LOWER_BUCKETS)].copy()
        if lower.empty:
            continue
        lower = lower.sort_values(["stage1_t10_score", "ticker"], ascending=[False, True]).copy()
        stage1 = lower.head(min(STAGE1_TOP_N, len(lower))).copy()
        stage1["selected_stage"] = "stage1"
        stage1["selected_rank"] = range(1, len(stage1) + 1)
        selected_rows.append(stage1)

        pos_t10 = int(lower["entered_t10_next"].sum())
        hits_t10 = int(stage1["entered_t10_next"].sum())
        base_t10 = float(lower["entered_t10_next"].mean()) if len(lower) else 0.0
        prec_t10 = float(stage1["entered_t10_next"].mean()) if len(stage1) else 0.0
        rows.append({
            "horizon": horizon,
            "signal_date": signal_date,
            "stage": "stage1_to_t10",
            "candidate_pool_n": int(len(lower)),
            "selected_n": int(len(stage1)),
            "positive_n": pos_t10,
            "hits": hits_t10,
            "base_rate": base_t10,
            "precision": prec_t10,
            "capture_rate": float(hits_t10 / pos_t10) if pos_t10 else None,
            "lift": float(prec_t10 / base_t10) if base_t10 else None,
        })

        stage2_pool = stage1.sort_values(["stage2_t3_score", "ticker"], ascending=[False, True]).copy()
        stage2 = stage2_pool.head(min(STAGE2_TOP_N, len(stage2_pool))).copy()
        stage2["selected_stage"] = "stage2"
        stage2["selected_rank"] = range(1, len(stage2) + 1)
        selected_rows.append(stage2)

        pos_t3_pool = int(stage1["entered_t3_next"].sum())
        hits_t3 = int(stage2["entered_t3_next"].sum())
        base_t3_pool = float(stage1["entered_t3_next"].mean()) if len(stage1) else 0.0
        prec_t3 = float(stage2["entered_t3_next"].mean()) if len(stage2) else 0.0
        rows.append({
            "horizon": horizon,
            "signal_date": signal_date,
            "stage": "stage2_to_t3_within_stage1",
            "candidate_pool_n": int(len(stage1)),
            "selected_n": int(len(stage2)),
            "positive_n": pos_t3_pool,
            "hits": hits_t3,
            "base_rate": base_t3_pool,
            "precision": prec_t3,
            "capture_rate": float(hits_t3 / pos_t3_pool) if pos_t3_pool else None,
            "lift": float(prec_t3 / base_t3_pool) if base_t3_pool else None,
        })

    result = pd.DataFrame(rows)
    selected = pd.concat(selected_rows, ignore_index=True) if selected_rows else pd.DataFrame()
    overall = result.groupby("stage", dropna=False).agg(
        windows=("stage", "size"),
        avg_candidate_pool_n=("candidate_pool_n", "mean"),
        avg_selected_n=("selected_n", "mean"),
        total_positive_n=("positive_n", "sum"),
        total_hits=("hits", "sum"),
        avg_base_rate=("base_rate", "mean"),
        avg_precision=("precision", "mean"),
        avg_capture_rate=("capture_rate", "mean"),
        avg_lift=("lift", "mean"),
    ).reset_index()
    by_h = result.groupby(["horizon", "stage"], dropna=False).agg(
        windows=("stage", "size"),
        avg_candidate_pool_n=("candidate_pool_n", "mean"),
        avg_selected_n=("selected_n", "mean"),
        total_positive_n=("positive_n", "sum"),
        total_hits=("hits", "sum"),
        avg_base_rate=("base_rate", "mean"),
        avg_precision=("precision", "mean"),
        avg_capture_rate=("capture_rate", "mean"),
        avg_lift=("lift", "mean"),
    ).reset_index()
    return result, overall, by_h, selected


def save_db(result, overall, by_h, selected):
    con = sqlite3.connect(str(RESEARCH_DB))
    try:
        result.to_sql("s3_two_stage_validation_windows", con, if_exists="replace", index=False)
        overall.to_sql("s3_two_stage_validation_overall", con, if_exists="replace", index=False)
        by_h.to_sql("s3_two_stage_validation_by_horizon", con, if_exists="replace", index=False)
        selected.to_sql("s3_two_stage_validation_selected", con, if_exists="replace", index=False)
    finally:
        con.close()


def render_md(overall, by_h):
    lines = ["# S3 Two-Stage Discovery Validation", ""]
    lines.append("- evaluation method: walk-forward on historical S3 transition panel")
    lines.append(f"- stage1 target: `{LOWER_BUCKETS} -> T10_ex_T3`")
    lines.append("- stage2 target: `within stage1 top40 -> next-step T3`")
    lines.append("")
    lines.append("## Overall")
    lines.append("| Stage | Windows | Avg base rate | Avg precision | Avg capture | Avg lift | Total hits | Total positives |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in overall.itertuples(index=False):
        lines.append(f"| {r.stage} | {r.windows} | {r.avg_base_rate:.2%} | {r.avg_precision:.2%} | {r.avg_capture_rate:.2%} | {r.avg_lift:.2f}x | {int(r.total_hits)} | {int(r.total_positive_n)} |")
    lines.append("")
    lines.append("## By horizon")
    for horizon, hg in by_h.groupby("horizon"):
        lines.append(f"### {horizon}")
        lines.append("| Stage | Avg base rate | Avg precision | Avg capture | Avg lift | Total hits | Total positives |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for r in hg.itertuples(index=False):
            lines.append(f"| {r.stage} | {r.avg_base_rate:.2%} | {r.avg_precision:.2%} | {r.avg_capture_rate:.2%} | {r.avg_lift:.2f}x | {int(r.total_hits)} | {int(r.total_positive_n)} |")
        lines.append("")
    return "\n".join(lines)


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    panel = add_scores(attach_features(build_base_panel()))
    result, overall, by_h, selected = evaluate(panel)
    save_db(result, overall, by_h, selected)
    panel.to_csv(OUTDIR / 's3_two_stage_validation_panel.csv', index=False, encoding='utf-8-sig')
    result.to_csv(OUTDIR / 's3_two_stage_validation_windows.csv', index=False, encoding='utf-8-sig')
    overall.to_csv(OUTDIR / 's3_two_stage_validation_overall.csv', index=False, encoding='utf-8-sig')
    by_h.to_csv(OUTDIR / 's3_two_stage_validation_by_horizon.csv', index=False, encoding='utf-8-sig')
    selected.to_csv(OUTDIR / 's3_two_stage_validation_selected.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's3_two_stage_validation.md').write_text(render_md(overall, by_h), encoding='utf-8')
    print(overall.to_string(index=False))
    print('\nBY_H')
    print(by_h.to_string(index=False))


if __name__ == '__main__':
    main()
