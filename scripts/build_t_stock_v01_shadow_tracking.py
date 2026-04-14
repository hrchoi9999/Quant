from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from tseries_refresh_utils import ensure_run_dir, latest_asof_from_dir, normalize_run_date

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = ""
OP_DIR = Path()
HIST_DIR = Path()
ASOF_DATE = ""

CONF_STAGE2 = 0.515
NEAR_STAGE2 = 0.512
OBS_STAGE1 = 0.512


def build_latest_watchlist() -> tuple[pd.DataFrame, pd.DataFrame]:
    latest = pd.read_csv(OP_DIR / f"t_stock_v01_risk_filtered_candidates_{ASOF_DATE}.csv", dtype={"ticker": str})
    latest = latest.rename(columns={"candidate_grade": "candidate_bucket"})
    latest["model_code"] = "T-STOCK-V01"
    latest["asof_date"] = ASOF_DATE
    latest = latest[[
        "model_code", "asof_date", "candidate_bucket", "ticker", "name", "market", "theme_bucket", "theme_name_kr",
        "is_s2_overlap", "stage1_prob", "stage2_prob", "mcap"
    ]].sort_values(["candidate_bucket", "stage2_prob", "stage1_prob", "mcap"], ascending=[True, False, False, False], na_position="last")

    summary = latest.groupby(["candidate_bucket", "market", "theme_bucket", "theme_name_kr"], as_index=False).size().rename(columns={"size": "count"})
    return latest, summary


def build_history() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stage1 = pd.read_csv(HIST_DIR / "operating_v2_stage1_tracking_history.csv", dtype={"ticker": str})
    stage2 = pd.read_csv(HIST_DIR / "operating_v2_stage2_only_tracking_history.csv", dtype={"ticker": str})
    labels = pd.read_csv(BASE_DIR / "data" / "labels" / f"t_stock_v01_theme_labels_{RUN_DATE}.csv", dtype={"ticker": str})[["ticker", "theme_bucket", "theme_name_kr"]].drop_duplicates("ticker")

    s2 = stage2.copy()
    s2["candidate_bucket"] = s2["pred_prob"].apply(lambda x: "confirmed" if float(x) >= CONF_STAGE2 else ("near" if float(x) >= NEAR_STAGE2 else None))
    s2 = s2[s2["candidate_bucket"].notna()].copy()
    s2["stage1_prob"] = pd.NA
    s2["stage2_prob"] = s2["pred_prob"]

    stage2_keys = set(zip(s2["horizon"], s2["signal_date"], s2["ticker"]))
    s1 = stage1.copy()
    s1 = s1[s1["pred_prob"] >= OBS_STAGE1].copy()
    s1 = s1[[tuple(x) not in stage2_keys for x in zip(s1["horizon"], s1["signal_date"], s1["ticker"])]]
    s1["candidate_bucket"] = "observe"
    s1["stage1_prob"] = s1["pred_prob"]
    s1["stage2_prob"] = pd.NA

    cols = [
        "horizon", "signal_date", "ticker", "name", "market", "bucket", "candidate_bucket",
        "stage1_prob", "stage2_prob", "actual_t10_or_better_2to4", "actual_t3_2to4"
    ]
    hist = pd.concat([s2[cols], s1[cols]], ignore_index=True)
    hist = hist.merge(labels, on="ticker", how="left")
    hist["model_code"] = "T-STOCK-V01"
    hist = hist[[
        "model_code", "horizon", "signal_date", "candidate_bucket", "ticker", "name", "market", "bucket",
        "theme_bucket", "theme_name_kr", "stage1_prob", "stage2_prob", "actual_t10_or_better_2to4", "actual_t3_2to4"
    ]].sort_values(["signal_date", "candidate_bucket", "ticker"])

    overall = hist.groupby("candidate_bucket", as_index=False).agg(
        obs_n=("ticker", "size"),
        t10_hit_rate=("actual_t10_or_better_2to4", "mean"),
        t3_hit_rate=("actual_t3_2to4", "mean"),
    )
    overall["t10_hit_rate"] = overall["t10_hit_rate"] * 100.0
    overall["t3_hit_rate"] = overall["t3_hit_rate"] * 100.0

    by_horizon = hist.groupby(["candidate_bucket", "horizon"], as_index=False).agg(
        obs_n=("ticker", "size"),
        t10_hit_rate=("actual_t10_or_better_2to4", "mean"),
        t3_hit_rate=("actual_t3_2to4", "mean"),
    )
    by_horizon["t10_hit_rate"] = by_horizon["t10_hit_rate"] * 100.0
    by_horizon["t3_hit_rate"] = by_horizon["t3_hit_rate"] * 100.0

    return hist, overall, by_horizon


def main() -> None:
    ap = argparse.ArgumentParser(description="Build T-STOCK-V01 shadow tracking outputs.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD run folder.")
    ap.add_argument("--asof", default=None, help="Accepted for interface consistency; latest risk-filtered asof is used.")
    args = ap.parse_args()

    global RUN_DATE, OP_DIR, HIST_DIR, ASOF_DATE
    RUN_DATE = normalize_run_date(args.run_date)
    run_root = ensure_run_dir(RUN_DATE)
    OP_DIR = run_root / "T_STOCK_V01_OPERATIONALIZATION"
    HIST_DIR = run_root / "S3_OPERATING_V2_TRACKING"
    ASOF_DATE = latest_asof_from_dir(OP_DIR, r"t_stock_v01_risk_filtered_candidates_(\d{4}-\d{2}-\d{2})\.csv")

    latest, latest_summary = build_latest_watchlist()
    hist, overall, by_horizon = build_history()

    latest.to_csv(OP_DIR / f"t_stock_v01_latest_watchlist_{ASOF_DATE}.csv", index=False, encoding="utf-8-sig")
    latest_summary.to_csv(OP_DIR / f"t_stock_v01_latest_watchlist_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")
    hist.to_csv(OP_DIR / f"t_stock_v01_shadow_tracking_history_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(OP_DIR / f"t_stock_v01_shadow_tracking_historical_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")
    by_horizon.to_csv(OP_DIR / f"t_stock_v01_shadow_tracking_historical_summary_by_horizon_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    md = f"""# T-STOCK-V01 Shadow Tracking ({RUN_DATE})

## Latest Watchlist
- confirmed: {int((latest['candidate_bucket'] == 'confirmed').sum())}
- near: {int((latest['candidate_bucket'] == 'near').sum())}
- observe: {int((latest['candidate_bucket'] == 'observe').sum())}
- total: {len(latest)}

## Historical Tracking Rule
- confirmed: `stage2_prob >= {CONF_STAGE2}`
- near: `{NEAR_STAGE2} <= stage2_prob < {CONF_STAGE2}`
- observe: `stage1_prob >= {OBS_STAGE1}` and not already in confirmed/near on the same date

## Historical Summary
"""
    for _, row in overall.iterrows():
        md += f"- {row['candidate_bucket']}: obs `{int(row['obs_n'])}`, T10 hit `{row['t10_hit_rate']:.2f}%`, T3 hit `{row['t3_hit_rate']:.2f}%`\n"

    (OP_DIR / f"t_stock_v01_shadow_tracking_{RUN_DATE}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
