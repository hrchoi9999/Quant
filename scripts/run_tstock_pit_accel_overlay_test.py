from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")
TS_DB = PROJECT_ROOT / r"data\db\tseries_operational.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_tstock_pit_accel_overlay"


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def load_tstock_history() -> pd.DataFrame:
    hist = read_sql(
        TS_DB,
        """
        SELECT model_code, signal_date, horizon, candidate_bucket, ticker, name, stage1_prob, stage2_prob,
               actual_t10_hit, actual_t3_hit
        FROM ts_candidates_history
        WHERE model_code='T-STOCK-V01'
        """,
        parse_dates=["signal_date"],
    )
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    hist["stage1_prob"] = pd.to_numeric(hist["stage1_prob"], errors="coerce")
    hist["stage2_prob"] = pd.to_numeric(hist["stage2_prob"], errors="coerce")
    hist["actual_t10_hit"] = pd.to_numeric(hist["actual_t10_hit"], errors="coerce")
    hist["actual_t3_hit"] = pd.to_numeric(hist["actual_t3_hit"], errors="coerce")
    bucket_rank = {"confirmed": 0, "near": 1, "observe": 2}
    hist["bucket_rank"] = hist["candidate_bucket"].map(bucket_rank).fillna(9).astype(int)
    hist = hist.sort_values(
        ["signal_date", "horizon", "ticker", "bucket_rank", "stage2_prob", "stage1_prob"],
        ascending=[True, True, True, True, False, False],
        na_position="last",
    ).drop_duplicates(["signal_date", "horizon", "ticker"], keep="first")
    hist["base_score"] = hist["stage2_prob"].where(hist["stage2_prob"].notna(), hist["stage1_prob"])
    return hist


def load_pit() -> pd.DataFrame:
    pit = read_sql(
        FUND_DB,
        """
        SELECT date, ticker, coverage_score, pit_growth_score,
               q_revenue_yoy, q_op_income_yoy,
               q_revenue_yoy_delta_1q, q_op_income_yoy_delta_1q
        FROM fundamentals_pit_qh_mix400_latest
        """,
        parse_dates=["date"],
    )
    pit["ticker"] = pit["ticker"].astype(str).str.zfill(6)
    for col in [
        "coverage_score", "pit_growth_score", "q_revenue_yoy", "q_op_income_yoy",
        "q_revenue_yoy_delta_1q", "q_op_income_yoy_delta_1q",
    ]:
        pit[col] = pd.to_numeric(pit[col], errors="coerce")
    return pit


def attach_pit(hist: pd.DataFrame, pit: pd.DataFrame) -> pd.DataFrame:
    left = hist.sort_values(["ticker", "signal_date"]).reset_index(drop=True).copy()
    right = pit.sort_values(["ticker", "date"]).reset_index(drop=True).copy()
    parts: list[pd.DataFrame] = []
    for ticker, sub_left in left.groupby("ticker", sort=False):
        sub_right = right[right["ticker"] == ticker].copy()
        if sub_right.empty:
            merged_sub = sub_left.copy()
            for col in right.columns:
                if col not in merged_sub.columns:
                    merged_sub[col] = np.nan
        else:
            merged_sub = pd.merge_asof(
                sub_left.sort_values("signal_date").reset_index(drop=True),
                sub_right.sort_values("date").reset_index(drop=True),
                left_on="signal_date",
                right_on="date",
                direction="backward",
            )
            if "ticker_x" in merged_sub.columns:
                merged_sub["ticker"] = merged_sub["ticker_x"]
                merged_sub = merged_sub.drop(columns=[c for c in ["ticker_x", "ticker_y"] if c in merged_sub.columns])
        parts.append(merged_sub)
    merged = pd.concat(parts, ignore_index=True) if parts else left.copy()
    merged["pit_level_pct"] = merged.groupby(["signal_date", "horizon"])["pit_growth_score"].transform(
        lambda s: 1.0 - s.rank(pct=True)
    )
    merged["pit_quarter_pct"] = merged.groupby(["signal_date", "horizon"])["q_op_income_yoy"].transform(
        lambda s: s.rank(pct=True)
    )
    merged["pit_accel_pct"] = merged.groupby(["signal_date", "horizon"])["q_op_income_yoy_delta_1q"].transform(
        lambda s: s.rank(pct=True)
    )
    merged["pit_overlay"] = (
        0.60 * merged["pit_accel_pct"].fillna(0)
        + 0.25 * merged["pit_quarter_pct"].fillna(0)
        + 0.15 * merged["pit_level_pct"].fillna(0)
    )
    merged["pit_confirmed"] = (merged["coverage_score"].fillna(0) >= 0.7).astype(int)
    merged["overlay_light"] = merged["base_score"].fillna(0) + 0.10 * merged["pit_overlay"] * merged["pit_confirmed"]
    merged["overlay_medium"] = merged["base_score"].fillna(0) + 0.20 * merged["pit_overlay"] * merged["pit_confirmed"]
    return merged


def rank_variant(df: pd.DataFrame, variant: str) -> pd.DataFrame:
    if variant == "baseline":
        score_col = "base_score"
    elif variant == "accel_light":
        score_col = "overlay_light"
    else:
        score_col = "overlay_medium"
    ranked_frames = []
    for (dt, horizon), sub in df.groupby(["signal_date", "horizon"], sort=True):
        ranked = sub.sort_values(
            ["bucket_rank", score_col, "stage2_prob", "stage1_prob", "ticker"],
            ascending=[True, False, False, False, True],
            na_position="last",
        ).copy()
        ranked["variant"] = variant
        ranked["rank_no"] = np.arange(1, len(ranked) + 1)
        ranked["variant_score"] = ranked[score_col]
        ranked_frames.append(ranked)
    return pd.concat(ranked_frames, ignore_index=True) if ranked_frames else pd.DataFrame()


def safe_corr(df: pd.DataFrame, xcol: str, ycol: str) -> float | None:
    tmp = df[[xcol, ycol]].copy()
    tmp[xcol] = pd.to_numeric(tmp[xcol], errors="coerce")
    tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
    tmp = tmp.dropna()
    if len(tmp) < 3 or tmp[xcol].nunique() < 2 or tmp[ycol].nunique() < 2:
        return None
    return float(tmp[xcol].corr(tmp[ycol], method="spearman"))


def summarize(detail: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    topk_rows = []
    date_ic_rows = []
    for (variant, horizon), sub in detail.groupby(["variant", "horizon"], dropna=False):
        rank_alpha = -pd.to_numeric(sub["rank_no"], errors="coerce")
        tmp = sub.copy()
        tmp["rank_alpha"] = rank_alpha
        ic_t10 = safe_corr(tmp, "rank_alpha", "actual_t10_hit")
        ic_t3 = safe_corr(tmp, "rank_alpha", "actual_t3_hit")
        rows.append(
            {
                "variant": variant,
                "horizon": horizon,
                "n_rows": len(tmp),
                "spearman_rank_vs_t10": ic_t10,
                "spearman_rank_vs_t3": ic_t3,
                "avg_actual_t10_hit": float(tmp["actual_t10_hit"].mean()),
                "avg_actual_t3_hit": float(tmp["actual_t3_hit"].mean()),
                "avg_bucket_rank": float(tmp["bucket_rank"].mean()),
            }
        )
        for k in (5, 10, 20):
            top = tmp[tmp["rank_no"] <= k].copy()
            if top.empty:
                continue
            topk_rows.append(
                {
                    "variant": variant,
                    "horizon": horizon,
                    "top_k": k,
                    "n_rows": len(top),
                    "avg_actual_t10_hit": float(top["actual_t10_hit"].mean()),
                    "avg_actual_t3_hit": float(top["actual_t3_hit"].mean()),
                    "avg_pit_overlay": float(top["pit_overlay"].mean()),
                    "avg_stage_prob": float(top["base_score"].mean()),
                }
            )
        for dt, dt_sub in tmp.groupby("signal_date", sort=True):
            date_ic_rows.append(
                {
                    "variant": variant,
                    "horizon": horizon,
                    "signal_date": dt,
                    "spearman_rank_vs_t10": safe_corr(dt_sub.assign(rank_alpha=-dt_sub["rank_no"]), "rank_alpha", "actual_t10_hit"),
                    "spearman_rank_vs_t3": safe_corr(dt_sub.assign(rank_alpha=-dt_sub["rank_no"]), "rank_alpha", "actual_t3_hit"),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(topk_rows), pd.DataFrame(date_ic_rows)


def bucket_summary(detail: pd.DataFrame) -> pd.DataFrame:
    return (
        detail.groupby(["variant", "horizon", "candidate_bucket"], dropna=False)
        .agg(
            n_rows=("ticker", "size"),
            avg_actual_t10_hit=("actual_t10_hit", "mean"),
            avg_actual_t3_hit=("actual_t3_hit", "mean"),
            avg_rank_no=("rank_no", "mean"),
            avg_overlay=("pit_overlay", "mean"),
        )
        .reset_index()
    )


def overlap_summary(base: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (dt, horizon), sub in base.groupby(["signal_date", "horizon"], sort=True):
        target = other[(other["signal_date"] == dt) & (other["horizon"] == horizon)]
        if target.empty:
            continue
        for k in (5, 10, 20):
            b = set(sub.loc[sub["rank_no"] <= k, "ticker"])
            o = set(target.loc[target["rank_no"] <= k, "ticker"])
            rows.append(
                {
                    "variant": target["variant"].iloc[0],
                    "horizon": horizon,
                    "signal_date": dt,
                    "top_k": k,
                    "overlap_ratio": len(b & o) / max(len(b | o), 1),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby(["variant", "horizon", "top_k"], dropna=False).agg(
        avg_overlap_ratio=("overlap_ratio", "mean"),
        min_overlap_ratio=("overlap_ratio", "min"),
    ).reset_index()


def to_markdown(summary: pd.DataFrame, topk: pd.DataFrame, overlap: pd.DataFrame) -> str:
    lines = [
        "# T-STOCK PIT Accel Overlay Test",
        "",
        "## Scope",
        "- model: `T-STOCK-V01`",
        "- overlay policy: keep original buckets, only reorder inside the bucket with PIT accel overlay",
        "- variants:",
        "  - `baseline`",
        "  - `accel_light` = base_prob + 0.10 * PIT accel overlay",
        "  - `accel_medium` = base_prob + 0.20 * PIT accel overlay",
        "",
        "## Summary",
        "| Variant | Horizon | Spearman Rank vs T10 | Spearman Rank vs T3 | Avg T10 Hit | Avg T3 Hit | Avg Bucket Rank |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.sort_values(["variant", "horizon"]).itertuples(index=False):
        lines.append(
            f"| {row.variant} | {row.horizon} | {('-' if pd.isna(row.spearman_rank_vs_t10) else f'{row.spearman_rank_vs_t10:.4f}')} | "
            f"{('-' if pd.isna(row.spearman_rank_vs_t3) else f'{row.spearman_rank_vs_t3:.4f}')} | {row.avg_actual_t10_hit:.2%} | {row.avg_actual_t3_hit:.2%} | {row.avg_bucket_rank:.2f} |"
        )
    lines.append("")
    if not topk.empty:
        lines.extend([
            "## Top-K Quality",
            "| Variant | Horizon | Top K | Avg T10 Hit | Avg T3 Hit | Avg PIT Overlay | Avg Stage Prob |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        for row in topk.sort_values(["variant", "horizon", "top_k"]).itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.horizon} | {row.top_k} | {row.avg_actual_t10_hit:.2%} | {row.avg_actual_t3_hit:.2%} | {row.avg_pit_overlay:.4f} | {row.avg_stage_prob:.4f} |"
            )
        lines.append("")
    if not overlap.empty:
        lines.extend([
            "## Baseline Overlap",
            "| Variant | Horizon | Top K | Avg Overlap | Min Overlap |",
            "|---|---|---:|---:|---:|",
        ])
        for row in overlap.sort_values(["variant", "horizon", "top_k"]).itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.horizon} | {row.top_k} | {row.avg_overlap_ratio:.2%} | {row.min_overlap_ratio:.2%} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    hist = load_tstock_history()
    pit = load_pit()
    merged = attach_pit(hist, pit)
    baseline = rank_variant(merged, "baseline")
    accel_light = rank_variant(merged, "accel_light")
    accel_medium = rank_variant(merged, "accel_medium")
    all_ranked = pd.concat([baseline, accel_light, accel_medium], ignore_index=True)

    summary, topk, date_ic = summarize(all_ranked)
    bucket = bucket_summary(all_ranked)
    overlap = pd.concat(
        [
            overlap_summary(baseline, accel_light),
            overlap_summary(baseline, accel_medium),
        ],
        ignore_index=True,
    )

    merged.to_csv(OUTDIR / "tstock_pit_accel_merged.csv", index=False, encoding="utf-8-sig")
    all_ranked.to_csv(OUTDIR / "tstock_pit_accel_ranked.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTDIR / "tstock_pit_accel_summary.csv", index=False, encoding="utf-8-sig")
    topk.to_csv(OUTDIR / "tstock_pit_accel_topk.csv", index=False, encoding="utf-8-sig")
    date_ic.to_csv(OUTDIR / "tstock_pit_accel_date_ic.csv", index=False, encoding="utf-8-sig")
    bucket.to_csv(OUTDIR / "tstock_pit_accel_bucket_summary.csv", index=False, encoding="utf-8-sig")
    overlap.to_csv(OUTDIR / "tstock_pit_accel_overlap.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "tstock_pit_accel_overlay_test.md").write_text(to_markdown(summary, topk, overlap), encoding="utf-8")
    print(f"[OK] wrote {OUTDIR}")


if __name__ == "__main__":
    main()
