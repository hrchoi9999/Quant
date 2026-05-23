# Redbot Data Quality Baseline

## Purpose

This document marks the starting point for redbot data-quality management after the KRX price-data rebase.

The baseline separates two checks that should not use the same comparison logic:

1. Input data quality gate
2. T-series volatility gate

The remaining controls, publish restriction, rolling watchlist continuity, and root-cause workflow automation, are intentionally deferred.

## Baseline Identity

| Field | Value |
|---|---|
| baseline_date | `2026-04-18` |
| model_data_asof | `2026-04-17` |
| run_type | `routine_refresh_after_data_rebase_baseline` |
| source event | KRX OpenAPI price-data rebase |
| policy document | `D:\Quant\docs\KRX_ROLLING_DATA_OPERATION_POLICY_20260418.md` |
| report directory | `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910` |

## 1. Input Data Quality Gate

The input gate uses the current operating data surface, not pre-rebase model outputs.

Comparison basis:

- Current KRX audit against `price.db`
- Stock/ETF row coverage
- Missing and duplicate rows
- OHLCV null/zero anomaly rate
- Universe count drift
- Feature and regime freshness

Result:

| Scope | Result |
|---|---|
| overall | `green` |
| stock KRX audit | `pass`, 2,200 compared rows, 0 missing, 0 mismatches |
| ETF KRX audit | `pass`, 9,614 compared rows, 0 missing, 0 mismatches |
| stock universe | 400 expected, 400 present |
| stock fundready universe | 200 expected, 200 present |
| ETF universe | 874 expected, 874 present |

Evidence:

- `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\input_data_quality_gate_20260417.json`
- `D:\Quant\reports\data_quality\krx_price_audit\krx_price_audit_20260418_174628\manifest.json`
- `D:\Quant\reports\data_quality\krx_price_audit\krx_price_audit_20260418_174651\manifest.json`

Interpretation:

- The KRX-based input surface is usable as the new redbot data-quality starting baseline.
- This check does not judge whether model candidates changed versus the old pykrx/FDR-derived baseline.

## 2. T-Series Volatility Gate

The T-series volatility gate uses the rebase before/after comparison as the first baseline.

The immediate comparison from `2026-04-16` to `2026-04-17` is useful, but it is not sufficient for this first post-rebase baseline because both dates are already on the reworked data surface.

Required comparison basis for this baseline:

- Pre-rebase public current object vs current public current object
- Candidate ticker-set turnover
- Bucket movement
- Candidate count change
- Explicit note that this is a `data_rebase` effect, not normal one-day instability

### T-STOCK-V01

Result:

- Status: `block_or_rebase_review`
- Reason: high candidate turnover after the KRX data rebase.

Evidence:

- `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\tseries_volatility_gate_20260417_vs_20260416.json`
- `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\quality_gate_report_20260417.md`

### T-ETF-V01

Pre-rebase public current:

- Source: `D:\Quant\_tmp_tseries_gcs_current.json`
- Wrapper as-of date: `2026-04-01`
- T-ETF model as-of date: `2026-03-31`
- Candidates:
  - `114800` KODEX 인버스, confirmed
  - `462010` TIGER 2차전지소재Fn, near
  - `305540` TIGER 2차전지테마, near

Current public current:

- Source: `D:\Quant\service_platform\web\public_data\current\quantservice_tseries_discovery.json`
- Wrapper as-of date: `2026-04-17`
- T-ETF model as-of date: `2026-04-17`
- Candidates:
  - `261220` KODEX WTI원유선물(H), observe
  - `481050` KODEX CD1년금리플러스액티브(합성), observe

Result:

| Basis | Kept | Added | Removed | Turnover | Status |
|---|---:|---:|---:|---:|---|
| all public candidates | 0 | 2 | 3 | 100.00% | `block_or_rebase_review` |
| excluding old inverse/leverage candidate | 0 | 2 | 2 | 100.00% | `block_or_rebase_review` |

Evidence:

- `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\tseries_volatility_gate_pre_rebase_vs_current_20260417.md`
- `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\tseries_volatility_gate_pre_rebase_vs_current_20260417.json`

Interpretation:

- The earlier `green` result for T-ETF-V01 was valid only for immediate post-rebase comparison from `2026-04-16` to `2026-04-17`.
- For the redbot data-quality baseline, the correct comparison is pre-rebase vs current.
- Under that basis, T-ETF-V01 materially changed and must be recorded as `block_or_rebase_review`.

## Baseline Decision

This baseline becomes the starting point for redbot data-quality management.

Operational decision:

1. Treat the current KRX-based input data surface as usable.
2. Treat T-series post-rebase candidate sets as a new baseline.
3. Do not describe T-series changes from this event as ordinary daily model volatility.
4. Future routine refreshes should compare against this baseline unless another rebase, schema change, or emergency repair occurs.

## Follow-Up

Deferred controls:

- Publish restriction automation
- Rolling watchlist continuity enforcement
- Change root-cause workflow automation

Known follow-up issue:

- T-ETF rolling watchlist continuity needs review because candidates that existed in the immediate prior post-rebase run can still be marked `new` after the rebase workflow.
