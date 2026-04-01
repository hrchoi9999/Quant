from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE_DIR = Path(r"D:\Quant")
RUN_DATE = "20260331"
ASOF_DATE = "2026-03-26"
SRC_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "S3_TWO_STAGE_THRESHOLD_CANDIDATES"
OUT_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "T_STOCK_V01_OPERATIONALIZATION"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(SRC_DIR / name, dtype={"ticker": str})


def save_csv(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT_DIR / name, index=False, encoding="utf-8-sig")


def main() -> None:
    stage1 = load_csv(f"operating_v2_stage1_candidates_{ASOF_DATE}.csv")
    confirmed = load_csv(f"operating_v2_stage2_confirmed_candidates_{ASOF_DATE}.csv")
    near = load_csv(f"operating_v2_stage2_near_candidates_{ASOF_DATE}.csv")

    stage1_prob_map = stage1[["ticker", "pred_prob"]].rename(columns={"pred_prob": "stage1_prob"})

    confirmed = confirmed.merge(stage1_prob_map, on="ticker", how="left")
    near = near.merge(stage1_prob_map, on="ticker", how="left")
    stage1 = stage1.rename(columns={"pred_prob": "stage1_prob"})

    confirmed["stage2_prob"] = confirmed["pred_prob"]
    near["stage2_prob"] = near["pred_prob"]
    confirmed = confirmed.drop(columns=["pred_prob"])
    near = near.drop(columns=["pred_prob"])

    confirmed_tickers = set(confirmed["ticker"])
    near_tickers = set(near["ticker"])

    observe = stage1[
        ~stage1["ticker"].isin(confirmed_tickers)
        & ~stage1["ticker"].isin(near_tickers)
    ].copy()
    observe["stage2_prob"] = pd.NA

    confirmed["candidate_grade"] = "confirmed"
    near["candidate_grade"] = "near"
    observe["candidate_grade"] = "observe"

    keep_cols = [
        "asof_date",
        "ticker",
        "name",
        "market",
        "mcap",
        "revenue_yoy_pct",
        "op_income_yoy_pct",
        "op_delta_3m_pct",
        "mom20_pct",
        "vol_ratio_20_pct",
        "stage1_prob",
        "stage2_prob",
        "candidate_grade",
    ]

    confirmed = confirmed[keep_cols]
    near = near[keep_cols]
    observe = observe[keep_cols]

    combined = pd.concat([confirmed, near, observe], ignore_index=True)
    combined["grade_order"] = combined["candidate_grade"].map({"confirmed": 0, "near": 1, "observe": 2})
    combined = combined.sort_values(
        ["grade_order", "stage2_prob", "stage1_prob", "mcap"],
        ascending=[True, False, False, False],
        na_position="last",
    ).drop(columns=["grade_order"])

    summary = pd.DataFrame(
        [
            {"grade": "confirmed", "count": len(confirmed), "avg_stage1_prob": round(pd.to_numeric(confirmed["stage1_prob"], errors="coerce").mean(), 6), "avg_stage2_prob": round(pd.to_numeric(confirmed["stage2_prob"], errors="coerce").mean(), 6)},
            {"grade": "near", "count": len(near), "avg_stage1_prob": round(pd.to_numeric(near["stage1_prob"], errors="coerce").mean(), 6), "avg_stage2_prob": round(pd.to_numeric(near["stage2_prob"], errors="coerce").mean(), 6)},
            {"grade": "observe", "count": len(observe), "avg_stage1_prob": round(pd.to_numeric(observe["stage1_prob"], errors="coerce").mean(), 6), "avg_stage2_prob": ""},
            {"grade": "total_stage1", "count": len(stage1), "avg_stage1_prob": round(pd.to_numeric(stage1["stage1_prob"], errors="coerce").mean(), 6), "avg_stage2_prob": ""},
        ]
    )

    save_csv(summary, f"t_stock_v01_operational_candidate_summary_{RUN_DATE}.csv")
    save_csv(confirmed, f"t_stock_v01_confirmed_candidates_{ASOF_DATE}.csv")
    save_csv(near, f"t_stock_v01_near_candidates_{ASOF_DATE}.csv")
    save_csv(observe, f"t_stock_v01_observe_candidates_{ASOF_DATE}.csv")
    save_csv(combined, f"t_stock_v01_operational_candidates_{ASOF_DATE}.csv")

    md = f"""# T-STOCK-V01 Operational Candidates ({ASOF_DATE})

- stage1 candidates: {len(stage1)}
- confirmed candidates: {len(confirmed)}
- near candidates: {len(near)}
- observe candidates: {len(observe)}

## Grade Definitions
- `confirmed`: operating_v2 stage2 confirmed bucket
- `near`: operating_v2 stage2 near bucket
- `observe`: stage1 passed but not promoted to confirmed/near

## Current Interpretation
- `confirmed` is the highest-conviction discovery bucket
- `near` is the immediate follow-up bucket
- `observe` is the broader watchlist that still passed stage1
"""
    (OUT_DIR / f"t_stock_v01_operational_candidates_{RUN_DATE}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
