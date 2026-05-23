# AI Shadow Performance Tracker - 2026-05-04

## Purpose

Track whether AI shadow tags separate better and worse candidates.

This is still based on historical/reconstructed shadow rows and should be used as a validation layer, not a live trading claim.

## Artifacts

- Script: `D:\Quant\scripts\build_ai_shadow_performance_tracker.py`
- CSV: `D:\Quant\reports\ai_overlay_v01\ai_shadow_performance_tracker_20260504.csv`
- MD: `D:\Quant\reports\ai_overlay_v01\ai_shadow_performance_tracker_20260504.md`
- DB: `D:\Quant\data\db\ai_learning.db::ai_shadow_performance_tracker`

## Summary

- shadow rows: `2,736`
- summary rows: `315`
- horizons: `1W`, `2W`, `1M`, `2M`, `3M`

## Decision-Level Results

| decision | 1M samples | 1M avg return | 1M win rate | 2M avg return | 3M avg return |
|---|---:|---:|---:|---:|---:|
| `AI_HIGH_CONVICTION` | 9 | 12.30% | 100.00% | 38.42% | 18.71% |
| `AI_CONFIRM` | 201 | 8.51% | 73.63% | 8.97% | 14.85% |
| `AI_OBSERVE` | 2,151 | 4.26% | 51.42% | 6.80% | 10.32% |
| `AI_RISK_REVIEW` | 25 | -1.50% | 36.00% | 3.63% | 10.75% |

## Tag-Level Results

| tag | 1M samples | 1M avg return | 1M win rate | 2M avg return | 3M avg return |
|---|---:|---:|---:|---:|---:|
| `UPSIDE_STRICT` | 20 | 15.42% | 90.00% | 25.90% | 19.45% |
| `MEDIUM_QUALITY` | 59 | 21.31% | 72.88% | 22.75% | 20.63% |
| `LONG_QUALITY` | 49 | 13.00% | 75.51% | 23.46% | 25.94% |
| `SHORT_CONFIRM` | 208 | 8.58% | 74.52% | 9.30% | 14.99% |
| `OBSERVE` | 2,108 | 4.01% | 51.04% | 6.51% | 10.07% |
| `RISK_AVOID` | 25 | -1.50% | 36.00% | 3.63% | 10.75% |

## Interpretation

The AI shadow tags are directionally useful.

Strong points:

- `AI_HIGH_CONVICTION` separates a small but strong cohort.
- `UPSIDE_STRICT`, `MEDIUM_QUALITY`, and `LONG_QUALITY` have clearly higher average returns than `OBSERVE`.
- `RISK_AVOID` has negative 1M average return and low 1M win rate, so the risk tag is doing useful filtering work.

Limitations:

- `AI_HIGH_CONVICTION` sample count is only `9` for 1M.
- This tracker currently uses reconstructed/historical shadow rows as well as current shadow rows.
- Actual live AI-tag performance tracking must start from this design point forward.

Recommended next step:

- Add this tracker to the regular AI shadow batch.
- Track live-only AI tag performance separately from reconstructed history.
- Do not promote to portfolio selection until live-only samples accumulate.
