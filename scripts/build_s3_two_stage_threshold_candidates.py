from __future__ import annotations
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
MODEL_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_MODELING\logistic_regression"
S3_CURRENT = PROJECT_ROOT / r"reports\backtest_s3_dev\s3_holdings_last_top20_2026-03-25.csv"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_THRESHOLD_CANDIDATES"

CONFIGS = [
    ("operating_v2", 0.52, 0.525, 0.52),
    ("conservative", 0.525, 0.53, 0.525),
    ("precise", 0.53, 0.535, 0.53),
]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"ticker": str})


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s1 = read_csv(MODEL_DIR / "latest_stage1_rank.csv")
    s2 = read_csv(MODEL_DIR / "latest_stage2_rank.csv")
    s3 = read_csv(S3_CURRENT)
    for df in (s1, s2, s3):
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return s1, s2, s3


def threshold_view(
    stage1: pd.DataFrame,
    stage2: pd.DataFrame,
    stage1_th: float,
    stage2_confirmed_th: float,
    stage2_near_th: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s1 = stage1[pd.to_numeric(stage1["pred_prob"], errors="coerce") >= stage1_th].copy()
    allowed = set(s1["ticker"])
    near_mask = (
        (pd.to_numeric(stage2["pred_prob"], errors="coerce") >= stage2_near_th)
        & (stage2["ticker"].isin(allowed))
    )
    confirmed_mask = (
        (pd.to_numeric(stage2["pred_prob"], errors="coerce") >= stage2_confirmed_th)
        & (stage2["ticker"].isin(allowed))
    )
    s2_all = stage2[near_mask].copy()
    s2_confirmed = stage2[confirmed_mask].copy()
    s2_near = s2_all[
        pd.to_numeric(s2_all["pred_prob"], errors="coerce") < stage2_confirmed_th
    ].copy()
    return s1, s2_all, s2_confirmed, s2_near


def merge_official(stage1_df: pd.DataFrame, stage2_df: pd.DataFrame, s3_current: pd.DataFrame, label: str) -> pd.DataFrame:
    current = s3_current.copy()
    current["official_s3_rank"] = current.index + 1
    current["in_official_s3"] = True
    current["stage1_pass"] = current["ticker"].isin(stage1_df["ticker"])
    current["stage2_pass"] = current["ticker"].isin(stage2_df["ticker"])
    current["threshold_profile"] = label
    stage1_map = stage1_df.set_index("ticker")[["pred_prob", "rank"]].rename(columns={"pred_prob": "stage1_pred_prob", "rank": "stage1_rank"})
    stage2_map = stage2_df.set_index("ticker")[["pred_prob", "rank"]].rename(columns={"pred_prob": "stage2_pred_prob", "rank": "stage2_rank"})
    current = current.join(stage1_map, on="ticker")
    current = current.join(stage2_map, on="ticker")
    return current


def fusion_watchlist(stage1_df: pd.DataFrame, stage2_df: pd.DataFrame, s3_current: pd.DataFrame, label: str) -> pd.DataFrame:
    current = s3_current[["ticker", "name", "market", "s3_score"]].copy()
    current["in_official_s3"] = True
    current["official_s3_rank"] = current["s3_score"].rank(method="first", ascending=False)
    stage1 = stage1_df[["ticker", "name", "market", "pred_prob", "rank"]].copy().rename(columns={"pred_prob": "stage1_pred_prob", "rank": "stage1_rank"})
    stage1["stage1_pass"] = True
    stage2 = stage2_df[["ticker", "name", "market", "pred_prob", "rank"]].copy().rename(columns={"pred_prob": "stage2_pred_prob", "rank": "stage2_rank"})
    stage2["stage2_pass"] = True
    merged = current.merge(stage1, on=["ticker", "name", "market"], how="outer").merge(stage2, on=["ticker", "name", "market"], how="outer")
    merged["in_official_s3"] = merged["in_official_s3"].fillna(False)
    merged["stage1_pass"] = merged["stage1_pass"].fillna(False)
    merged["stage2_pass"] = merged["stage2_pass"].fillna(False)
    merged["threshold_profile"] = label

    def tier(row: pd.Series) -> str:
        if row["stage2_pass"] and row["in_official_s3"]:
            return "A_intersection_stage2_and_s3"
        if row["stage2_pass"]:
            return "B_stage2_only"
        if row["stage1_pass"] and row["in_official_s3"]:
            return "C_stage1_and_s3"
        if row["stage1_pass"]:
            return "D_stage1_only"
        if row["in_official_s3"]:
            return "E_official_s3_only"
        return "Z_other"

    tier_order = {
        "A_intersection_stage2_and_s3": 1,
        "B_stage2_only": 2,
        "C_stage1_and_s3": 3,
        "D_stage1_only": 4,
        "E_official_s3_only": 5,
        "Z_other": 99,
    }
    merged["fusion_tier"] = merged.apply(tier, axis=1)
    merged["fusion_tier_order"] = merged["fusion_tier"].map(tier_order).fillna(99)
    for col in ["stage2_rank", "stage1_rank", "official_s3_rank"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    return merged.sort_values(
        ["fusion_tier_order", "stage2_rank", "stage1_rank", "official_s3_rank", "ticker"],
        ascending=[True, True, True, True, True],
    ).reset_index(drop=True)


def summary_row(
    label: str,
    stage1_df: pd.DataFrame,
    stage2_df: pd.DataFrame,
    stage2_confirmed_df: pd.DataFrame,
    stage2_near_df: pd.DataFrame,
    s3_current: pd.DataFrame,
    stage1_th: float,
    stage2_confirmed_th: float,
    stage2_near_th: float,
) -> dict:
    stage1_overlap = int(stage1_df["ticker"].isin(s3_current["ticker"]).sum())
    stage2_overlap = int(stage2_df["ticker"].isin(s3_current["ticker"]).sum())
    return {
        "threshold_profile": label,
        "stage1_threshold": stage1_th,
        "stage2_confirmed_threshold": stage2_confirmed_th,
        "stage2_near_threshold": stage2_near_th,
        "stage1_candidate_n": int(len(stage1_df)),
        "stage2_candidate_n": int(len(stage2_df)),
        "stage2_confirmed_n": int(len(stage2_confirmed_df)),
        "stage2_near_n": int(len(stage2_near_df)),
        "official_s3_current_n": int(len(s3_current)),
        "stage1_overlap_with_official_s3_n": stage1_overlap,
        "stage2_overlap_with_official_s3_n": stage2_overlap,
        "stage1_overlap_with_official_s3_pct": float(stage1_overlap / len(stage1_df)) if len(stage1_df) else 0.0,
        "stage2_overlap_with_official_s3_pct": float(stage2_overlap / len(stage2_df)) if len(stage2_df) else 0.0,
    }


def render_md(summary: pd.DataFrame) -> str:
    lines = [
        "# S3 Two-Stage Threshold Candidates",
        "",
        "- source model: `logistic_regression` two-stage discovery",
        "- latest stage1 rank: `2026-03-26`",
        "- latest stage2 rank: `2026-03-26`",
        "- official S3 current holdings: `2026-03-25`",
        "",
        "## Summary",
        "",
        "| Profile | Stage1 TH | Stage2 Confirmed TH | Stage2 Near TH | Stage1 N | Stage2 N | Confirmed N | Near N | Official S3 N | Stage1∩S3 | Stage2∩S3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['threshold_profile']} | {row['stage1_threshold']:.3f} | {row['stage2_confirmed_threshold']:.3f} | {row['stage2_near_threshold']:.3f} | "
            f"{int(row['stage1_candidate_n'])} | {int(row['stage2_candidate_n'])} | {int(row['stage2_confirmed_n'])} | {int(row['stage2_near_n'])} | "
            f"{int(row['official_s3_current_n'])} | {int(row['stage1_overlap_with_official_s3_n'])} | {int(row['stage2_overlap_with_official_s3_n'])} |"
        )
    lines.extend([
        "",
        "## Operating Decision",
        "",
        "- `operating_v2 (0.520 / 0.525 / 0.520)` is the default profile after 2017 backfill recalibration.",
        "- `conservative (0.525 / 0.530 / 0.525)` remains as a tighter reference profile.",
        "- `precise (0.530 / 0.535 / 0.530)` remains as a high-conviction reference profile.",
        "",
        "## Fusion Rule",
        "",
        "1. `A_intersection_stage2_and_s3`: highest conviction.",
        "2. `B_stage2_only`: discovery names promoted by two-stage model but not yet in official S3.",
        "3. `C_stage1_and_s3`: official S3 names that also pass the broad stage1 filter.",
        "4. `D_stage1_only`: broad discovery candidates not yet validated by official S3.",
        "5. `E_official_s3_only`: official S3 names not supported by the two-stage filter.",
        "",
        "Current snapshot note: overlap is still zero, so the operational use is a parallel discovery watchlist.",
    ])
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    stage1, stage2, s3_current = load_frames()
    summary_rows = []
    for label, stage1_th, stage2_confirmed_th, stage2_near_th in CONFIGS:
        s1, s2_all, s2_confirmed, s2_near = threshold_view(stage1, stage2, stage1_th, stage2_confirmed_th, stage2_near_th)
        merge_official(s1, s2_all, s3_current, label).to_csv(OUTDIR / f"{label}_official_s3_overlap_2026-03-26.csv", index=False, encoding="utf-8-sig")
        fusion_watchlist(s1, s2_all, s3_current, label).to_csv(OUTDIR / f"{label}_fusion_watchlist_2026-03-26.csv", index=False, encoding="utf-8-sig")
        s1.to_csv(OUTDIR / f"{label}_stage1_candidates_2026-03-26.csv", index=False, encoding="utf-8-sig")
        s2_all.to_csv(OUTDIR / f"{label}_stage2_candidates_2026-03-26.csv", index=False, encoding="utf-8-sig")
        s2_confirmed.to_csv(OUTDIR / f"{label}_stage2_confirmed_candidates_2026-03-26.csv", index=False, encoding="utf-8-sig")
        s2_near.to_csv(OUTDIR / f"{label}_stage2_near_candidates_2026-03-26.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame([
            {"grade": "confirmed", "count": len(s2_confirmed)},
            {"grade": "near", "count": len(s2_near)},
            {"grade": "total_stage2", "count": len(s2_all)},
        ]).to_csv(OUTDIR / f"{label}_stage2_candidate_buckets_summary_2026-03-26.csv", index=False, encoding="utf-8-sig")
        summary_rows.append(summary_row(label, s1, s2_all, s2_confirmed, s2_near, s3_current, stage1_th, stage2_confirmed_th, stage2_near_th))
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTDIR / "s3_two_stage_threshold_candidate_summary.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s3_two_stage_threshold_candidates.md").write_text(render_md(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
