# KRX OpenAPI Data Quality and Feature Expansion Plan

## Scope

This plan covers two operating tracks after KRX OpenAPI integration:

1. Validate existing `price.db` history against KRX OpenAPI without overwriting the production price table.
2. Identify additional KRX OpenAPI fields/services that can improve universe generation and S/T model research.

Official KRX references:

- Service list: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- Usage flow: https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp

KRX key file:

- `D:\Quant\config\KRX_API_Key.json`
- Keep local/private. Never print the key in logs or reports.

Primary audit script:

- `D:\Quant\scripts\audit_krx_price_integrity.py`

Primary backfill script:

- `D:\Quant\scripts\backfill_krx_openapi_prices.py`
- Purpose:
  - fetch KRX OpenAPI rows
  - compare with existing `price.db`
  - write old/new difference logs
  - optionally upsert KRX rows into `price.db` with `source='krx_openapi'`

Rolling operation wrapper:

- Policy: `D:\Quant\docs\KRX_ROLLING_DATA_OPERATION_POLICY_20260418.md`
- Script: `D:\Quant\scripts\run_krx_data_quality_cycle.py`
- Purpose:
  - build daily/weekly/monthly/quarterly KRX audit/backfill plans
  - run plan-only by default
  - execute audit/backfill only when `--execute` is provided
  - keep backfill as dry-run unless `--apply` is explicitly provided

Operational quality gates and management indicators:

- The canonical operating policy is `D:\Quant\docs\KRX_ROLLING_DATA_OPERATION_POLICY_20260418.md`.
- It defines the run-type classification (`routine_refresh`, `data_rebase`, `schema_or_logic_change`, `emergency_repair`), source freshness checks, T-series volatility gates, publish restriction rules, rolling watchlist continuity, and required root-cause logs.
- The 2026-04 KRX correction should be treated as a `data_rebase`, not as evidence of normal one-day T-series sensitivity.

Audit storage:

- DB: `D:\Quant\data\db\data_quality.db`
- Tables:
  - `krx_price_audit_runs`
  - `krx_price_audit_mismatch_samples`
- Reports:
  - `D:\Quant\reports\data_quality\krx_price_audit\<run_id>\summary.csv`
  - `D:\Quant\reports\data_quality\krx_price_audit\<run_id>\mismatch_detail.csv`
  - `D:\Quant\reports\data_quality\krx_price_audit\<run_id>\manifest.json`

## Current Baseline

`price.db::prices_daily` has one row per `(ticker, date)`.

This means existing pykrx/FDR rows and KRX OpenAPI rows cannot be stored side-by-side in the same table for the same ticker/date. Therefore, data quality validation must fetch KRX data into memory, compare it with the existing DB, and persist audit results separately.

Smoke test executed:

- Date: `2026-04-16`
- Markets: `KOSPI,KOSDAQ`
- Universe: `universe_mix_top400_20260416.csv`
- Result:
  - KRX rows: `399`
  - DB rows: `400`
  - Compared rows: `399`
  - Missing in DB: `0`
  - Missing in KRX: `1`
  - Mismatch rows: `0`
  - Status: `warn`
- Note:
  - The one missing-in-KRX ticker was `294400` / `KIWOOM 200TR`, which should be reviewed as a universe classification issue because it is not returned by the stock KOSPI/KOSDAQ OpenAPI endpoints.

## Audit Method

The audit compares:

- `open`
- `high`
- `low`
- `close`
- `volume`
- `value`

Default tolerances:

- Price fields: `0.0001`
- Volume: `0`
- Trading value: `1.0`

The script does not update `price.db`.

Example:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\audit_krx_price_integrity.py `
  --start 20260416 `
  --end 20260416 `
  --markets KOSPI,KOSDAQ `
  --tickers-file D:\Quant\data\universe\universe_mix_top400_20260416.csv `
  --ticker-col ticker `
  --notes smoke_test_single_day_stock
```

ETF example:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\audit_krx_price_integrity.py `
  --start 20260416 `
  --end 20260416 `
  --markets ETF `
  --tickers-file D:\Quant\data\universe\universe_etf_master_latest.csv `
  --ticker-col ticker `
  --notes smoke_test_single_day_etf
```

ETF-only audit/backfill uses a stock-market calendar check by default:

- Default `--calendar-market KOSPI`
- If KOSPI has no rows for a date, ETF rows for that date are skipped.
- This prevents KRX ETF endpoint holiday rows from being inserted or treated as missing DB rows.

## Recommended Historical Validation Plan

KRX OpenAPI daily endpoints return all market rows for one date. API pressure is mainly proportional to:

`number of trading dates * number of market endpoints`

For stock audit:

- KOSPI + KOSDAQ = 2 API calls per trading day

For ETF audit:

- ETF = 1 API call per trading day

Approximate call counts:

- 3 months: about 63 trading days
  - Stocks: about 126 calls
  - ETF: about 63 calls
  - Stocks + ETF: about 189 calls
- 6 months: about 126 trading days
  - Stocks: about 252 calls
  - ETF: about 126 calls
  - Stocks + ETF: about 378 calls
- 1 year: about 252 trading days
  - Stocks: about 504 calls
  - ETF: about 252 calls
  - Stocks + ETF: about 756 calls

Recommended block size:

- Use 3-month blocks by default.
- Use 6-month blocks only for overnight or low-traffic maintenance windows.
- Avoid 1-year blocks as a default operating unit unless we first confirm stable KRX API throughput and no service-side throttling.

Recommended rollout:

1. Phase 0: Single-day smoke tests
   - Status: started.
   - Purpose: confirm API connectivity, schema, and audit output.

2. Phase 1: Recent 3 months
   - Audit current stock model universe and ETF universe.
   - If mismatch rows are zero or explainable, mark current operating history as trusted for recent-service reporting.

3. Phase 2: Recent 12 months by 3-month blocks
   - Run four 3-month blocks.
   - Prioritize dates used by weekly/monthly rebalance and T-series refresh.

4. Phase 3: Backtest-history audit from 2026 backward
   - Continue 3-month blocks backward to the active backtest start.
   - For T-STOCK/S-series operating tests, priority target is 2017 onward.
   - For ETF models, priority target is from actual ETF data availability and model start dates.

5. Phase 4: Remediation
   - Do not auto-replace historical data from audit results.
   - If a block has material mismatches, create a dated remediation plan:
     - classify issue type: missing DB row, KRX missing row, price mismatch, volume/value mismatch, universe classification issue
     - decide whether to refill only affected ticker/date rows
     - record before/after counts and source changes

Operating cadence:

- Daily after data refresh:
  - Audit latest trading day for current stock universe and ETF universe.
- Weekly:
  - Audit one historical 3-month block.
- If API stability is excellent after two weeks:
  - Increase to two 3-month blocks per week or one 6-month block per week.

## Recommended KRX Backfill Plan

Use KRX OpenAPI as the official source for gradual historical backfill.

Recommended backfill policy:

1. Use universe-limited backfill only.
   - Never run unrestricted all-market historical backfill by default.
   - Use stock universe files for stock backfill.
   - Use ETF master universe files for ETF backfill.

2. Backfill recent years first, then move backward.
   - 2026 YTD
   - 2025
   - 2024
   - 2023
   - continue backward to 2010 if needed

3. Use 1-year blocks during evenings/weekends.
   - A stock yearly block is about `252 trading days * 2 endpoints = 504 API calls`.
   - ETF yearly block is about `252 API calls`.
   - Stocks + ETF yearly block is about `756 API calls`.
   - Use `--sleep 0.3` or slower by default.

4. Always run `--dry-run` before actual upsert for the first block of a new period.

5. Upsert KRX rows into `prices_daily` only after dry-run looks sane.
   - Existing `(ticker, date)` rows are replaced by KRX values.
   - `source` becomes `krx_openapi`.
   - Old/new differences are logged to `data_quality.db` and CSV reports.

6. KRX missing rows are not used to delete existing DB rows.
   - This matters for listing-period gaps, product classification issues, and discontinued/inactive assets.

7. Keep additional KRX metadata/features outside `prices_daily`.
   - Add new fields first to separate feature/metadata tables, not directly into `prices_daily`.

Backfill command examples:

```powershell
# Dry-run stock universe backfill for one year
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\backfill_krx_openapi_prices.py `
  --start 20250101 `
  --end 20251231 `
  --markets KOSPI,KOSDAQ `
  --tickers-file D:\Quant\data\universe\universe_mix_top400_latest.csv `
  --ticker-col ticker `
  --dry-run `
  --sleep 0.3 `
  --notes stock_2025_dry_run

# Actual stock universe backfill for one year
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\backfill_krx_openapi_prices.py `
  --start 20250101 `
  --end 20251231 `
  --markets KOSPI,KOSDAQ `
  --tickers-file D:\Quant\data\universe\universe_mix_top400_latest.csv `
  --ticker-col ticker `
  --sleep 0.3 `
  --notes stock_2025_actual

# ETF universe backfill for one year
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\backfill_krx_openapi_prices.py `
  --start 20250101 `
  --end 20251231 `
  --markets ETF `
  --tickers-file D:\Quant\data\universe\universe_etf_master_latest.csv `
  --ticker-col ticker `
  --sleep 0.3 `
  --notes etf_2025_actual
```

2010 expansion note:

- KRX OpenAPI service list indicates many daily services provide data from 2010 onward.
- Current-universe backfill to 2010 is useful for longer model research windows.
- It does not fully remove survivorship bias, because current universe files do not include all historical constituents and delisted names.
- For strict point-in-time historical research, separate historical universe reconstruction is still required.

## Additional KRX OpenAPI Data Candidates

The currently approved/tested endpoints already provide fields not fully used in the existing model stack.

### Stock daily trading information

Available fields observed from approved services:

- `ISU_CD`: ticker
- `ISU_NM`: name
- `MKT_NM`: market
- `SECT_TP_NM`: section/type
- `TDD_CLSPRC`, `TDD_OPNPRC`, `TDD_HGPRC`, `TDD_LWPRC`: OHLC
- `CMPPREVDD_PRC`: change vs previous day
- `FLUC_RT`: daily return rate
- `ACC_TRDVOL`: volume
- `ACC_TRDVAL`: trading value
- `MKTCAP`: market cap
- `LIST_SHRS`: listed shares

Immediate uses:

- Universe generation:
  - Use `MKTCAP` directly as official daily market cap.
  - Use `ACC_TRDVAL` as liquidity filter or liquidity score.
  - Use `LIST_SHRS` to detect share-count changes and corporate-action-like discontinuities.
  - Use `SECT_TP_NM` to exclude non-common-stock or non-target sections more safely than name heuristics.

- S-series:
  - Add liquidity stability filter from rolling `ACC_TRDVAL`.
  - Add market cap/liquidity percentile rank per market.
  - Add abnormal turnover/volume shock features.

- T-series:
  - Add pre-breakout accumulation features:
    - rolling trading value expansion
    - market cap rank migration
    - volume/value acceleration before T10/T3 promotion

### ETF daily trading information

Available fields observed from approved service:

- OHLC, volume, value, market cap
- `NAV`
- `INVSTASST_NETASST_TOTAMT`: net asset amount
- `LIST_SHRS`
- `IDX_IND_NM`: index industry/name
- `OBJ_STKPRC_IDX`: tracked index value
- `CMPPREVDD_IDX`, `FLUC_RT_IDX`: index move fields

Immediate uses:

- ETF universe:
  - Use `INVSTASST_NETASST_TOTAMT` as AUM-like universe quality filter.
  - Use `ACC_TRDVAL` as liquidity floor.
  - Use `NAV` and close to estimate premium/discount quality.
  - Use `IDX_IND_NM` / tracked index fields to improve ETF theme buckets.

- ETF T-series:
  - Add NAV premium/discount stability.
  - Add AUM growth and liquidity growth features.
  - Add tracked-index momentum vs ETF price momentum gap.

### Index daily information

Available/tested fields:

- Index name/class
- Close/open/high/low index values
- Volume/value
- Market cap

Immediate uses:

- S-series:
  - Improve market regime gating beyond only KOSPI price trend.
  - Add KOSDAQ regime and style/sector index signals if approved.

- T-series:
  - Normalize stock/ETF candidate strength relative to parent market or index trend.

## Additional API Services Worth Applying For

Based on KRX service list, the following are useful next candidates:

1. Stock basic information
   - `유가증권 종목기본정보`
   - `코스닥 종목기본정보`
   - Expected use:
     - more reliable instrument master
     - listing metadata
     - market/product classification

2. KONEX daily/basic information
   - Only if we decide to include or explicitly exclude KONEX.

3. ETN and ELW daily trading information
   - Not needed for current public models.
   - Useful mainly for exclusion and classification hygiene.

4. Broader index services
   - `KRX 시리즈 일별시세정보`
   - `KOSPI 시리즈 일별시세정보`
   - `KOSDAQ 시리즈 일별시세정보`
   - Expected use:
     - regime features
     - benchmark and sector/style normalization

5. ESG services
   - ESG securities, social responsibility bond info, ESG index.
   - Research-only until a strategy explicitly uses ESG constraints or themes.

## Recommendation

Use gradual KRX OpenAPI backfill with automatic diff logging instead of silent replacement.

1. Keep KRX OpenAPI as the primary source for latest daily data.
2. Backfill universe-limited historical data in 1-year evening/weekend blocks.
3. Always preserve old/new difference logs in `data_quality.db` and CSV reports.
4. Add new KRX fields first to separate feature tables or metadata tables, not directly into `prices_daily`.

Proposed future tables:

- `market_daily_krx_raw`
- `stock_liquidity_daily`
- `stock_marketcap_daily`
- `etf_nav_daily`
- `etf_aum_daily`
- `index_daily_krx`

Keep `prices_daily` stable for existing backtests.
