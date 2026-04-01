from __future__ import annotations

from pathlib import Path

import pandas as pd


BASE_DIR = Path(r"D:\Quant")
RUN_DATE = "20260331"
ASOF_DATE = "2026-03-31"

TUNED_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "ETF_TWO_STAGE_DISCOVERY_TUNED"
OUT_DIR = BASE_DIR / "reports" / "model_upgrade_research" / RUN_DATE / "ETF_T_SERIES_OPERATIONALIZATION"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(TUNED_DIR / name, dtype={"ticker": str})


def save_csv(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT_DIR / name, index=False, encoding="utf-8-sig")


def main() -> None:
    stage1 = load_csv(f"etf_two_stage_tuned_stage1_candidates_{ASOF_DATE}.csv")
    confirmed = load_csv(f"etf_two_stage_tuned_stage2_confirmed_{ASOF_DATE}.csv")
    near = load_csv(f"etf_two_stage_tuned_stage2_near_{ASOF_DATE}.csv")

    confirmed_tickers = set(confirmed["ticker"])
    near_tickers = set(near["ticker"])

    observe = stage1[
        ~stage1["ticker"].isin(confirmed_tickers)
        & ~stage1["ticker"].isin(near_tickers)
    ].copy()

    confirmed = confirmed.copy()
    near = near.copy()
    observe = observe.copy()

    confirmed["candidate_grade"] = "confirmed"
    near["candidate_grade"] = "near"
    observe["candidate_grade"] = "observe"
    observe["stage2_prob"] = pd.NA

    keep_cols = [
        "signal_date",
        "feature_date",
        "ticker",
        "name",
        "asset_class",
        "group_key",
        "currency_exposure",
        "is_inverse",
        "is_leveraged",
        "liquidity_20d_value",
        "ret_20d",
        "ret_60d",
        "ret_120d",
        "vol_20d",
        "vol_60d",
        "dist_ma20",
        "dist_ma60",
        "dist_ma120",
        "ma20_ma60_gap",
        "ma60_ma120_gap",
        "rsi20",
        "stage1_prob",
        "stage2_prob",
        "candidate_grade",
    ]

    confirmed = confirmed[keep_cols]
    near = near[keep_cols]
    observe = observe[keep_cols]

    combined = pd.concat([confirmed, near, observe], ignore_index=True)
    combined["grade_order"] = combined["candidate_grade"].map(
        {"confirmed": 0, "near": 1, "observe": 2}
    )
    combined = combined.sort_values(
        ["grade_order", "stage2_prob", "stage1_prob", "liquidity_20d_value"],
        ascending=[True, False, False, False],
        na_position="last",
    ).drop(columns=["grade_order"])

    summary = pd.DataFrame(
        [
            {
                "grade": "confirmed",
                "count": len(confirmed),
                "avg_stage1_prob": round(confirmed["stage1_prob"].mean(), 6),
                "avg_stage2_prob": round(confirmed["stage2_prob"].mean(), 6),
            },
            {
                "grade": "near",
                "count": len(near),
                "avg_stage1_prob": round(near["stage1_prob"].mean(), 6),
                "avg_stage2_prob": round(near["stage2_prob"].mean(), 6),
            },
            {
                "grade": "observe",
                "count": len(observe),
                "avg_stage1_prob": round(observe["stage1_prob"].mean(), 6),
                "avg_stage2_prob": "",
            },
            {
                "grade": "total_stage1",
                "count": len(stage1),
                "avg_stage1_prob": round(stage1["stage1_prob"].mean(), 6),
                "avg_stage2_prob": "",
            },
        ]
    )

    save_csv(summary, f"etf_tseries_operational_candidate_summary_{RUN_DATE}.csv")
    save_csv(confirmed, f"etf_tseries_confirmed_candidates_{ASOF_DATE}.csv")
    save_csv(near, f"etf_tseries_near_candidates_{ASOF_DATE}.csv")
    save_csv(observe, f"etf_tseries_observe_candidates_{ASOF_DATE}.csv")
    save_csv(combined, f"etf_tseries_operational_candidates_{ASOF_DATE}.csv")

    baseline = pd.DataFrame(
        [
            {
                "stage": "stage1 lower->ET10",
                "validation_mode": "strict_walkforward",
                "feature_set": "baseline lower->ET10 logistic",
                "precision": 0.066872,
                "capture": 0.126035,
                "lift": 1.246353,
                "auc": 0.567083,
                "notes": "Operational baseline fixed after strict walk-forward validation.",
            },
            {
                "stage": "stage2 ET10->ET3",
                "validation_mode": "strict_walkforward_tuned",
                "feature_set": "momentum_stack top_ratio=0.03",
                "precision": 0.235294,
                "capture": 0.093697,
                "lift": 1.707703,
                "auc": 0.430541,
                "notes": "Tuned operating baseline; prioritizes precision/lift over broad capture.",
            },
        ]
    )
    save_csv(baseline, f"etf_tseries_operational_step2_tuned_baseline_{RUN_DATE}.csv")

    md = f"""# ETF T-series Operational Candidates ({ASOF_DATE})

- stage1 universe candidates: {len(stage1)}
- confirmed candidates: {len(confirmed)}
- near candidates: {len(near)}
- observe candidates: {len(observe)}

## Grade Definitions
- `confirmed`: stage1 passed and tuned stage2 confirmed bucket
- `near`: stage1 passed and tuned stage2 near bucket
- `observe`: stage1 passed but not promoted to confirmed/near

## Operating Baseline
- stage1 strict walk-forward baseline
  - precision: 6.69%
  - capture: 12.60%
  - lift: 1.25x
- stage2 tuned strict walk-forward baseline
  - precision: 23.53%
  - capture: 9.37%
  - lift: 1.71x

## Current Interpretation
- `confirmed` is the highest-conviction ETF discovery bucket
- `near` is the immediate follow-up bucket
- `observe` is the broader watchlist that still passed stage1
"""
    (OUT_DIR / f"etf_tseries_operational_candidates_{RUN_DATE}.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
