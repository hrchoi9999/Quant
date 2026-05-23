# S-Series Challenger Filter Design

## Purpose

This document defines the first challenger filter design for:

- `S2`: initial reversal pocket
- `S3`: second-stage loser rejection
- `S3_CORE2`: second-stage loser rejection

The baseline model logic is preserved. The challenger logic is evaluated in parallel and should not replace the baseline until backtest and shadow comparison are complete.

## Versioning Principle

- Keep stable model codes:
  - `S2`
  - `S3`
  - `S3_CORE2`
- Register challenger logic as a new `model_version_id` under the same `model_code`
- Do not create parallel public model codes such as `S2_v2`
- Recommended management mode:
  - baseline = current internal version
  - challenger = new filter-enhanced version
  - promote only after comparison

## Why S2 Needs a Different Fix

`S2` missed many strong future winners not because their growth score was weak, but because they were early reversal names:

- high growth score
- high fund acceleration
- weak or not-yet-confirmed trend
- small or slightly negative distance vs `MA60`

This means `S2` should not simply loosen the main trend filter.
Instead, it should add a small separate reversal pocket.

## S2 Challenger Pocket

### Rule

- baseline selected set remains unchanged
- add a small candidate sleeve from the not-selected universe if:
  - `score_value >= 200`
  - `fund_accel_score >= 0.60`
  - `trend_up == 0`
  - `-0.12 <= ma_gap_60 <= 0.08`
  - `-0.15 <= mom20 <= 0.10`
- then keep only top `5` names per date by `score_value`

### Intended Effect

- capture earlier reversal / re-rating names
- avoid destroying the main S2 trend-confirmation logic
- keep portfolio turnover and noise contained by using a small sleeve

## Why S3 / S3_CORE2 Need a Different Fix

For `S3` and `S3_CORE2`, the bigger issue is not missing winners.
The main issue is that some already-selected names are too overheated and then reverse down.

The gap study suggests a second-stage rejection filter is more useful than a broader inclusion filter.

## S3 Challenger Reject Filter

### Rule

Reject a selected name when all of the following are true:

- `ma_gap_60 >= 0.60`
- `vol_ratio_20 >= 2.30`
- `mcap <= 5e12`
- `fund_accel_score >= 0.55`
- `mom20 >= 0.10`

### Interpretation

This targets small/mid-cap, high-acceleration, highly extended momentum names that are more likely to reverse after selection.

## S3_CORE2 Challenger Reject Filter

### Rule

Reject a selected name when all of the following are true:

- `ma_gap_60 >= 0.45`
- `vol_ratio_20 >= 2.00`
- `mcap <= 3e12`
- `fund_accel_score >= 0.55`
- `mom20 >= 0.10`

### Interpretation

`S3_CORE2` is already tighter than `S3`, so the reject rule should also be tighter and more selective.

## Operational Guidance

- `S2` challenger:
  - treat as `add_reversal_pocket`
  - test first as internal challenger only
- `S3` / `S3_CORE2` challenger:
  - treat as `reject_overheat`
  - apply to challenger backtest and compare against baseline

## Required Next Step

Before operational promotion:

1. run challenger backtests against baseline
2. compare:
   - 1M / 3M forward return
   - loser rate
   - winner retention
   - turnover
   - recent live-like shadow behavior
3. only then decide whether to promote challenger into current internal version
