# Daily Batch Operation Policy

## Purpose

Define a stable daily operating rule for Quant when stock same-day data and ETF same-day data become available at different times.

The key principle is simple:

- internal review may use provisional evening results,
- public publish must use only the final batch based on a complete common date.

## Why This Policy Exists

Observed operating pattern:

- stock daily data is often available on the evening of the trading day,
- ETF daily data is often delayed until later or the next morning,
- publishing the evening result and then republishing again the next morning causes unnecessary churn in holdings, change history, and trading-sign outputs.

Therefore, Quant should not let incomplete ETF availability create two different public truths within the same overnight cycle.

## Two-Step Daily Structure

### 1. Evening Provisional Internal Batch

Purpose:

- internal-only check after market close,
- confirm stock data ingestion, S-series state, and T-STOCK status,
- detect operational failures early.

Allowed interpretation scope:

- `S2`
- `S3`
- `S3_CORE2`
- `T-STOCK-V01`

Restrictions:

- do not treat as final user-facing output,
- do not overwrite canonical GCS current,
- do not refresh public website state,
- do not describe the result as the final daily model state unless stock and ETF completeness both pass.

### 2. Next-Morning Final Operational Batch

Purpose:

- run after confirming that stock and ETF data are both complete for the previous trading date,
- regenerate the full model stack on one common operating `asof`,
- publish one stable public result.

Required scope:

- `S2`
- `S3`
- `S3_CORE2`
- `S4`
- `S5`
- `S6`
- `T-STOCK-V01`
- `T-ETF-V01`
- user models `stable / balanced / growth`
- `trading_sign`
- public/admin current payloads

This final batch is the only batch that may update canonical current used by `redbot.co.kr`.

## Operating `asof` Rule

Use the latest date where all required operating inputs are complete enough for contract validation.

In practice:

- if stock has same-day rows but ETF does not, do not promote same-day `asof` to public current,
- keep the public operating `asof` on the last complete common date,
- rerun the final batch after ETF coverage is available.

## Publish Rule

Canonical publish is allowed only when all of the following are true:

- stock universe coverage passes,
- ETF universe coverage passes,
- model/current validators pass,
- admin tracker validator passes,
- trading-sign validator passes,
- daily pipeline contract validator passes.

If same-day ETF coverage fails, the evening run remains provisional and non-public.

## Interpretation Rule

When reviewing daily changes, classify the run before explaining model behavior:

- `provisional_evening_internal`
- `final_operational_publish`

Do not compare a provisional evening result with a final next-morning publish result as if they were two equivalent operating snapshots.

## Recommended Daily Workflow

1. Evening:
   - collect same-day stock data,
   - attempt ETF collection,
   - run internal checks if needed,
   - review provisional outputs only.

2. Next morning:
   - retry ETF collection,
   - confirm common-date completeness,
   - run the full final daily pipeline,
   - publish once to canonical current.

## Reference Documents

- [DAILY_QUANT_BATCH_CHECKLIST_20260320.md](D:/Quant/docs/DAILY_QUANT_BATCH_CHECKLIST_20260320.md)
- [KRX_ROLLING_DATA_OPERATION_POLICY_20260418.md](D:/Quant/docs/KRX_ROLLING_DATA_OPERATION_POLICY_20260418.md)
