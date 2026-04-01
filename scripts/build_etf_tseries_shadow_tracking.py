from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = "20260331"
ASOF_DATE = "2026-03-31"
OUT_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "ETF_T_SERIES_OPERATIONALIZATION"
WF_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "ETF_T_SERIES_STRICT_WALKFORWARD"


def build_historical_shadow() -> pd.DataFrame:
    df = pd.read_csv(WF_DIR / "etf_tseries_strict_walkforward_top_picks.csv", dtype={"ticker": str})
    df = (
        df.groupby(["stage", "signal_date", "ticker", "name"], as_index=False)
        .agg(pred_prob=("pred_prob", "max"), target_hit=("label", "max"))
    )
    df["candidate_grade"] = df["stage"].map(
        {
            "stage1_lower_to_et10": "historical_stage1",
            "stage2_et10_to_et3": "historical_stage2",
        }
    )
    df["tracking_status"] = "resolved"
    df["source"] = "strict_walkforward"
    df["asof_date"] = pd.NA
    return df[[
        "source",
        "stage",
        "signal_date",
        "asof_date",
        "ticker",
        "name",
        "candidate_grade",
        "pred_prob",
        "target_hit",
        "tracking_status",
    ]]


def build_current_shadow() -> pd.DataFrame:
    df = pd.read_csv(OUT_DIR / f"etf_tseries_risk_filtered_candidates_{ASOF_DATE}.csv", dtype={"ticker": str})
    df["stage"] = df["candidate_grade"].map(
        {
            "confirmed": "stage2_et10_to_et3",
            "near": "stage2_et10_to_et3",
            "observe": "stage1_lower_to_et10",
        }
    )
    df["pred_prob"] = df["stage2_prob"].where(df["stage2_prob"].notna(), df["stage1_prob"])
    df["target_hit"] = pd.NA
    df["tracking_status"] = "pending"
    df["source"] = "latest_operational"
    df["asof_date"] = ASOF_DATE
    df["signal_date"] = ASOF_DATE
    return df[[
        "source",
        "stage",
        "signal_date",
        "asof_date",
        "ticker",
        "name",
        "candidate_grade",
        "pred_prob",
        "target_hit",
        "tracking_status",
    ]]


def main() -> None:
    historical = build_historical_shadow()
    current = build_current_shadow()
    combined = pd.concat([historical, current], ignore_index=True)
    combined.to_csv(OUT_DIR / f"etf_tseries_shadow_tracking_history_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    hist_summary = (
        historical.groupby(["stage", "candidate_grade"], as_index=False)
        .agg(
            candidate_count=("ticker", "count"),
            unique_tickers=("ticker", pd.Series.nunique),
            avg_pred_prob=("pred_prob", "mean"),
            hit_rate=("target_hit", "mean"),
        )
    )
    hist_summary.to_csv(OUT_DIR / f"etf_tseries_shadow_tracking_historical_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    latest_summary = (
        current.groupby(["stage", "candidate_grade"], as_index=False)
        .agg(
            candidate_count=("ticker", "count"),
            avg_pred_prob=("pred_prob", "mean"),
        )
    )
    latest_summary.to_csv(OUT_DIR / f"etf_tseries_latest_watchlist_summary_{RUN_DATE}.csv", index=False, encoding="utf-8-sig")

    latest_watch = pd.read_csv(OUT_DIR / f"etf_tseries_risk_filtered_candidates_{ASOF_DATE}.csv", dtype={"ticker": str})
    latest_watch["watch_priority"] = latest_watch["candidate_grade"].map({"confirmed": 0, "near": 1, "observe": 2})
    latest_watch = latest_watch.sort_values(["watch_priority", "stage2_prob", "stage1_prob"], ascending=[True, False, False], na_position="last")
    latest_watch.drop(columns=["watch_priority"]).to_csv(OUT_DIR / f"etf_tseries_latest_watchlist_{ASOF_DATE}.csv", index=False, encoding="utf-8-sig")

    md = f"""# ETF T-series Latest Watchlist ({ASOF_DATE})

## Current Counts
- confirmed: {int((latest_watch['candidate_grade'] == 'confirmed').sum())}
- near: {int((latest_watch['candidate_grade'] == 'near').sum())}
- observe: {int((latest_watch['candidate_grade'] == 'observe').sum())}

## Historical Shadow Tracking Reference
- stage1 historical candidates: {int((historical['stage'] == 'stage1_lower_to_et10').sum())}
- stage2 historical candidates: {int((historical['stage'] == 'stage2_et10_to_et3').sum())}
- stage1 historical hit rate: {historical.loc[historical['stage'] == 'stage1_lower_to_et10', 'target_hit'].mean():.2%}
- stage2 historical hit rate: {historical.loc[historical['stage'] == 'stage2_et10_to_et3', 'target_hit'].mean():.2%}

## Notes
- `latest_watchlist` is the operational output after candidate grading and risk filtering.
- `shadow_tracking_history` mixes resolved historical strict walk-forward picks and unresolved latest operational picks in one file.
- pending rows should be updated as future ET10 / ET3 labels become available.
"""
    (OUT_DIR / f"etf_tseries_latest_watchlist_{RUN_DATE}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
