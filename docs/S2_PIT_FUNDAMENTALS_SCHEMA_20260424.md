# S2 PIT Fundamentals Schema

## Purpose

`S2` challenger research uses a point-in-time fundamentals layer that blends:

- annual growth stability
- half-year freshness
- quarterly growth
- quarterly acceleration

The baseline `S2` model remains unchanged. This PIT layer is an additional research / challenger input.

## Base Table

Table:
- `fundamentals_pit_qh_mix400_latest`

Primary key:
- `(date, ticker)`

Main columns:

- `date`
- `ticker`
- `corp_name`

- `annual_bsns_year`
- `annual_available_from`
- `annual_report_code`
- `annual_revenue_yoy`
- `annual_op_income_yoy`

- `half_bsns_year`
- `half_available_from`
- `half_report_code`
- `half_revenue_yoy`
- `half_op_income_yoy`

- `quarter_bsns_year`
- `quarter_available_from`
- `quarter_report_code`
- `quarter_label`
- `q_revenue_yoy`
- `q_op_income_yoy`
- `q_revenue_yoy_delta_1q`
- `q_op_income_yoy_delta_1q`

- `has_annual`
- `has_half`
- `has_quarter`
- `coverage_score`

- `annual_component`
- `half_component`
- `quarter_component`
- `accel_component`
- `pit_growth_score`

## PIT Rules

- Only reports with `available_from <= month_end` are used.
- Future reports are never used.
- Source tables:
  - `dart_main.db::fact_report`
  - `dart_main.db::fact_fs_account`
  - `dart_main.db::dim_corp_listed`

## Report Interpretation

- `11011`: annual cumulative
- `11012`: half-year cumulative
- `11013`: Q1 cumulative
- `11014`: Q3 cumulative

Derived quarter values:

- `Q1 = 11013`
- `Q2 = 11012 - 11013`
- `Q3 = 11014 - 11012`
- `Q4 = 11011 - 11014`

## YoY Definitions

- `annual_revenue_yoy = annual_revenue / prev_annual_revenue - 1`
- `annual_op_income_yoy = annual_op_income / prev_annual_op_income - 1`

- `half_revenue_yoy = half_revenue / prev_half_revenue - 1`
- `half_op_income_yoy = half_op_income / prev_half_op_income - 1`

- `q_revenue_yoy = quarter_revenue / prev_same_quarter_revenue - 1`
- `q_op_income_yoy = quarter_op_income / prev_same_quarter_op_income - 1`

Quarterly acceleration:

- `q_revenue_yoy_delta_1q = current_q_revenue_yoy - previous_q_revenue_yoy`
- `q_op_income_yoy_delta_1q = current_q_op_income_yoy - previous_q_op_income_yoy`

## Coverage Score

- annual present: `+0.4`
- half present: `+0.3`
- quarter present: `+0.3`

Formula:

- `coverage_score = 0.4*has_annual + 0.3*has_half + 0.3*has_quarter`

## S2 Challenger Formula

Component formulas:

- `annual_component = 0.7 * annual_rev_rank + 0.3 * annual_op_rank`
- `half_component = 0.6 * half_rev_rank + 0.4 * half_op_rank`
- `quarter_component = 0.6 * quarter_rev_rank + 0.4 * quarter_op_rank`
- `accel_component = 0.4 * accel_rev_rank + 0.6 * accel_op_rank`

Default blend:

- `pit_growth_score = 0.45*annual_component + 0.15*half_component + 0.25*quarter_component + 0.15*accel_component`

Interpretation:

- lower `pit_growth_score` is better
- ranks are computed cross-sectionally by date

## Views

- `s2_fund_scores_pit_monthly`
- `vw_s2_pit_top30_monthly`

Current `valid_fund` rule:

- `has_annual = 1`
- `coverage_score >= 0.7`
- `pit_growth_score IS NOT NULL`

## Current Caveat

At dates before many annual filings are released, PIT coverage can be intentionally thin.
This is expected behavior, not a bug, because the design avoids lookahead.
