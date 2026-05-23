from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
INPUT_DETAIL = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_selection_gap\s_series_selection_gap_detail.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger"

S2_RULE = {
    "score_min": 200.0,
    "fund_accel_min": 0.60,
    "trend_up": 0,
    "ma_gap_low": -0.12,
    "ma_gap_high": 0.08,
    "mom20_low": -0.15,
    "mom20_high": 0.10,
    "top_n_per_date": 5,
}

S3_RULE = {
    "ma_gap_min": 0.60,
    "vol_ratio_min": 2.30,
    "mcap_max": 5_000_000_000_000.0,
    "fund_accel_min": 0.55,
    "mom20_min": 0.10,
}

S3_CORE2_RULE = {
    "ma_gap_min": 0.45,
    "vol_ratio_min": 2.00,
    "mcap_max": 3_000_000_000_000.0,
    "fund_accel_min": 0.55,
    "mom20_min": 0.10,
}


def load_detail() -> pd.DataFrame:
    if not INPUT_DETAIL.exists():
        raise FileNotFoundError(f"missing input detail: {INPUT_DETAIL}")
    df = pd.read_csv(INPUT_DETAIL, parse_dates=["date", "end_date"])
    for col in [
        "score_value",
        "fund_accel_score",
        "mom20",
        "ma_gap_60",
        "vol_ratio_20",
        "mcap",
        "forward_return",
        "selected",
        "trend_up",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_s2_reversal_pocket(df: pd.DataFrame) -> pd.DataFrame:
    rule = S2_RULE
    pocket = df[
        (df["model_code"] == "S2")
        & (df["selected"] == 0)
        & (df["score_value"] >= rule["score_min"])
        & (df["fund_accel_score"] >= rule["fund_accel_min"])
        & (df["trend_up"] == rule["trend_up"])
        & (df["ma_gap_60"].between(rule["ma_gap_low"], rule["ma_gap_high"]))
        & (df["mom20"].between(rule["mom20_low"], rule["mom20_high"]))
    ].copy()
    pocket["reversal_rank"] = pocket.groupby(["horizon", "date"])["score_value"].rank(method="first", ascending=False)
    pocket = pocket[pocket["reversal_rank"] <= rule["top_n_per_date"]].copy()
    pocket["challenger_action"] = "add_reversal_pocket"
    return pocket


def apply_reject_rule(df: pd.DataFrame, model_code: str, rule: dict[str, float]) -> pd.DataFrame:
    out = df[(df["model_code"] == model_code) & (df["selected"] == 1)].copy()
    flag = (
        (out["ma_gap_60"] >= rule["ma_gap_min"])
        & (out["vol_ratio_20"] >= rule["vol_ratio_min"])
        & (out["mcap"] <= rule["mcap_max"])
        & (out["fund_accel_score"] >= rule["fund_accel_min"])
        & (out["mom20"] >= rule["mom20_min"])
    )
    out["challenger_reject_flag"] = flag.astype(int)
    out["challenger_action"] = out["challenger_reject_flag"].map({1: "reject_overheat", 0: "keep"})
    return out


def summarize_s2_pocket(pocket: pd.DataFrame) -> pd.DataFrame:
    if pocket.empty:
        return pd.DataFrame()
    return (
        pocket.groupby("horizon", dropna=False)
        .agg(
            n_obs=("ticker", "size"),
            n_dates=("date", "nunique"),
            avg_per_date=("date", lambda s: len(s) / s.nunique()),
            avg_forward_return=("forward_return", "mean"),
            median_forward_return=("forward_return", "median"),
            avg_score=("score_value", "mean"),
            avg_fund_accel=("fund_accel_score", "mean"),
        )
        .reset_index()
    )


def summarize_rejects(flagged: pd.DataFrame, window_label: str) -> pd.DataFrame:
    rows = []
    if flagged.empty:
        return pd.DataFrame()
    for horizon, horizon_df in flagged.groupby("horizon", dropna=False):
        base = horizon_df.copy()
        reject = base[base["challenger_reject_flag"] == 1].copy()
        keep = base[base["challenger_reject_flag"] == 0].copy()
        if reject.empty:
            continue
        total_winners = int((base["forward_return"] > 0).sum())
        kept_winner_share = None
        if total_winners > 0:
            kept_winner_share = float((keep["forward_return"] > 0).sum() / total_winners)
        rows.append(
            {
                "window": window_label,
                "model_code": str(base["model_code"].iloc[0]),
                "horizon": horizon,
                "n_total": int(len(base)),
                "n_reject": int(len(reject)),
                "reject_rate": float(len(reject) / len(base)),
                "base_avg_return": float(base["forward_return"].mean()),
                "reject_avg_return": float(reject["forward_return"].mean()),
                "keep_avg_return": float(keep["forward_return"].mean()) if not keep.empty else None,
                "base_loser_rate": float((base["forward_return"] <= 0).mean()),
                "reject_loser_rate": float((reject["forward_return"] <= 0).mean()),
                "keep_loser_rate": float((keep["forward_return"] <= 0).mean()) if not keep.empty else None,
                "kept_winner_share": kept_winner_share,
            }
        )
    return pd.DataFrame(rows)


def to_markdown(s2_summary: pd.DataFrame, reject_summary: pd.DataFrame) -> str:
    lines = [
        "# S-Series Challenger Filter Prototype",
        "",
        "## Principle",
        "- baseline `S2 / S3 / S3_CORE2` is preserved as-is",
        "- challenger logic is defined as an add-on pocket for `S2` and a second-stage reject filter for `S3 / S3_CORE2`",
        "",
        "## Challenger Rules",
        "",
        "### S2 Reversal Pocket",
        f"- `score_value >= {S2_RULE['score_min']}`",
        f"- `fund_accel_score >= {S2_RULE['fund_accel_min']}`",
        f"- `trend_up == {S2_RULE['trend_up']}`",
        f"- `ma_gap_60 in [{S2_RULE['ma_gap_low']}, {S2_RULE['ma_gap_high']}]`",
        f"- `mom20 in [{S2_RULE['mom20_low']}, {S2_RULE['mom20_high']}]`",
        f"- take top `{S2_RULE['top_n_per_date']}` by score for each date/horizon",
        "",
        "### S3 Overheat Reject",
        f"- `ma_gap_60 >= {S3_RULE['ma_gap_min']}`",
        f"- `vol_ratio_20 >= {S3_RULE['vol_ratio_min']}`",
        f"- `mcap <= {S3_RULE['mcap_max']:.0f}`",
        f"- `fund_accel_score >= {S3_RULE['fund_accel_min']}`",
        f"- `mom20 >= {S3_RULE['mom20_min']}`",
        "",
        "### S3_CORE2 Overheat Reject",
        f"- `ma_gap_60 >= {S3_CORE2_RULE['ma_gap_min']}`",
        f"- `vol_ratio_20 >= {S3_CORE2_RULE['vol_ratio_min']}`",
        f"- `mcap <= {S3_CORE2_RULE['mcap_max']:.0f}`",
        f"- `fund_accel_score >= {S3_CORE2_RULE['fund_accel_min']}`",
        f"- `mom20 >= {S3_CORE2_RULE['mom20_min']}`",
        "",
    ]

    if not s2_summary.empty:
        lines.append("## S2 Reversal Pocket Summary")
        lines.append("| Horizon | N | Dates | Avg per Date | Avg Return | Median Return | Avg Score | Avg Fund Accel |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for row in s2_summary.itertuples(index=False):
            lines.append(
                f"| {row.horizon} | {row.n_obs} | {row.n_dates} | {row.avg_per_date:.2f} | {row.avg_forward_return:.2%} | "
                f"{row.median_forward_return:.2%} | {row.avg_score:.3f} | {row.avg_fund_accel:.3f} |"
            )
        lines.append("")

    if not reject_summary.empty:
        lines.append("## Reject Filter Summary")
        lines.append("| Window | Model | Horizon | Reject Rate | Reject Avg Return | Reject Loser Rate | Keep Avg Return | Keep Loser Rate | Kept Winner Share |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for row in reject_summary.itertuples(index=False):
            keep_winner = "-" if pd.isna(row.kept_winner_share) else f"{row.kept_winner_share:.2%}"
            lines.append(
                f"| {row.window} | {row.model_code} | {row.horizon} | {row.reject_rate:.2%} | {row.reject_avg_return:.2%} | "
                f"{row.reject_loser_rate:.2%} | {row.keep_avg_return:.2%} | {row.keep_loser_rate:.2%} | {keep_winner} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df = load_detail()

    s2_pocket = build_s2_reversal_pocket(df)
    s2_summary = summarize_s2_pocket(s2_pocket)

    s3_flagged = apply_reject_rule(df, "S3", S3_RULE)
    s3_core2_flagged = apply_reject_rule(df, "S3_CORE2", S3_CORE2_RULE)

    recent_cutoff = pd.Timestamp("2024-01-01")
    reject_summary = pd.concat(
        [
            summarize_rejects(s3_flagged[s3_flagged["date"] >= recent_cutoff], "recent_2024plus"),
            summarize_rejects(s3_core2_flagged[s3_core2_flagged["date"] >= recent_cutoff], "recent_2024plus"),
            summarize_rejects(s3_flagged, "full_history"),
            summarize_rejects(s3_core2_flagged, "full_history"),
        ],
        ignore_index=True,
    )

    s2_pocket.to_csv(OUTDIR / "s2_reversal_pocket_candidates.csv", index=False, encoding="utf-8-sig")
    s2_summary.to_csv(OUTDIR / "s2_reversal_pocket_summary.csv", index=False, encoding="utf-8-sig")
    s3_flagged.to_csv(OUTDIR / "s3_reject_filter_flags.csv", index=False, encoding="utf-8-sig")
    s3_core2_flagged.to_csv(OUTDIR / "s3_core2_reject_filter_flags.csv", index=False, encoding="utf-8-sig")
    reject_summary.to_csv(OUTDIR / "s3_family_reject_filter_summary.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s_series_challenger_filter_prototype.md").write_text(
        to_markdown(s2_summary, reject_summary),
        encoding="utf-8",
    )
    print(f"[OK] wrote {OUTDIR}")


if __name__ == "__main__":
    main()
