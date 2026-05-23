from __future__ import annotations
import argparse
from pathlib import Path
import re
import pandas as pd

from tseries_refresh_utils import ensure_run_dir, latest_research_subdir, normalize_asof_date, normalize_run_date

PROJECT_ROOT = Path(r"D:\Quant")
MODEL_DIR = Path()
OUTDIR = Path()

CONFIGS = [
    ("operating_v2", 0.512, 0.515, 0.512),
    ("conservative", 0.525, 0.53, 0.525),
    ("precise", 0.53, 0.535, 0.53),
]


def latest_s3_current_path(max_asof: str | None = None) -> Path:
    pattern = re.compile(r"s3_holdings_last_top20_(\d{4}-\d{2}-\d{2})\.csv$")
    matches: list[tuple[str, Path]] = []
    max_key = pd.Timestamp(max_asof).strftime("%Y-%m-%d") if max_asof else None
    for p in (PROJECT_ROOT / r"reports\backtest_s3_dev").glob("s3_holdings_last_top20_*.csv"):
        m = pattern.match(p.name)
        if not m:
            continue
        key = m.group(1)
        if max_key and key > max_key:
            continue
        matches.append((key, p))
    if not matches:
        raise FileNotFoundError("No official S3 current holdings file found")
    return max(matches, key=lambda item: item[0])[1]


def latest_stage_asof(stage1: pd.DataFrame) -> str:
    if "asof_date" in stage1.columns and not stage1["asof_date"].dropna().empty:
        return str(pd.to_datetime(stage1["asof_date"].dropna().max()).date())
    return pd.Timestamp.today().strftime("%Y-%m-%d")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"ticker": str})


def load_frames(asof: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str, str]:
    s1 = read_csv(MODEL_DIR / "latest_stage1_rank.csv")
    s2 = read_csv(MODEL_DIR / "latest_stage2_rank.csv")
    s3_path = latest_s3_current_path(asof)
    s3 = read_csv(s3_path)
    for df in (s1, s2, s3):
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    stage_asof = latest_stage_asof(s1)
    current_report_asof = s3_path.stem.replace("s3_holdings_last_top20_", "")
    return s1, s2, s3, stage_asof, current_report_asof


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


def render_md(summary: pd.DataFrame, stage_asof: str, current_report_asof: str) -> str:
    lines = [
        "# S3 Two-Stage Threshold Candidates",
        "",
        "- source model: `logistic_regression` two-stage discovery",
        "- latest stage1 rank: `{stage_asof}`",
        f"- latest stage2 rank: `{stage_asof}`",
        f"- official S3 current holdings report: `{current_report_asof}`",
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
        "- `operating_v2 (0.512 / 0.515 / 0.512)` is the default profile after the April 2026 refresh recalibration to avoid an empty live candidate set.",
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
    ap = argparse.ArgumentParser(description="Build S3 two-stage threshold candidate outputs.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD output folder.")
    ap.add_argument("--asof", default=None, help="Accepted for interface consistency; latest available stage ranking is used.")
    args = ap.parse_args()

    run_date = normalize_run_date(args.run_date)
    asof = normalize_asof_date(args.asof) if args.asof else None
    run_model_dir = ensure_run_dir(run_date) / r"S3_TWO_STAGE_MODELING\logistic_regression"
    model_dir = run_model_dir if run_model_dir.exists() else latest_research_subdir(r"S3_TWO_STAGE_MODELING\logistic_regression")
    outdir = ensure_run_dir(run_date) / "S3_TWO_STAGE_THRESHOLD_CANDIDATES"
    outdir.mkdir(parents=True, exist_ok=True)

    global MODEL_DIR, OUTDIR
    MODEL_DIR = model_dir
    OUTDIR = outdir
    stage1, stage2, s3_current, stage_asof, current_report_asof = load_frames(asof)
    summary_rows = []
    for label, stage1_th, stage2_confirmed_th, stage2_near_th in CONFIGS:
        s1, s2_all, s2_confirmed, s2_near = threshold_view(stage1, stage2, stage1_th, stage2_confirmed_th, stage2_near_th)
        merge_official(s1, s2_all, s3_current, label).to_csv(OUTDIR / f"{label}_official_s3_overlap_{stage_asof}.csv", index=False, encoding="utf-8-sig")
        fusion_watchlist(s1, s2_all, s3_current, label).to_csv(OUTDIR / f"{label}_fusion_watchlist_{stage_asof}.csv", index=False, encoding="utf-8-sig")
        s1.to_csv(OUTDIR / f"{label}_stage1_candidates_{stage_asof}.csv", index=False, encoding="utf-8-sig")
        s2_all.to_csv(OUTDIR / f"{label}_stage2_candidates_{stage_asof}.csv", index=False, encoding="utf-8-sig")
        s2_confirmed.to_csv(OUTDIR / f"{label}_stage2_confirmed_candidates_{stage_asof}.csv", index=False, encoding="utf-8-sig")
        s2_near.to_csv(OUTDIR / f"{label}_stage2_near_candidates_{stage_asof}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame([
            {"grade": "confirmed", "count": len(s2_confirmed)},
            {"grade": "near", "count": len(s2_near)},
            {"grade": "total_stage2", "count": len(s2_all)},
        ]).to_csv(OUTDIR / f"{label}_stage2_candidate_buckets_summary_{stage_asof}.csv", index=False, encoding="utf-8-sig")
        summary_rows.append(summary_row(label, s1, s2_all, s2_confirmed, s2_near, s3_current, stage1_th, stage2_confirmed_th, stage2_near_th))
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTDIR / "s3_two_stage_threshold_candidate_summary.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s3_two_stage_threshold_candidates.md").write_text(render_md(summary, stage_asof, current_report_asof), encoding="utf-8")


if __name__ == "__main__":
    main()
