# T-series Rolling Watchlist Rules (2026-04-06)

## Purpose

T-series is better used as a rolling discovery watchlist than a full replacement portfolio.
This rule set keeps prior candidates visible for a short period instead of replacing the entire list at each refresh.

## Status Definitions

- `new`
  - Candidate appears in the current refresh and did not appear in the recent lookback window before now.
- `active`
  - Candidate appears in the current refresh and also appeared in one or more prior lookback snapshots.
- `cooling`
  - Candidate is not in the current refresh, but it appeared in the recent watchlist window and is still inside the grace period.

## Tier Definitions

- `core`
  - Best recent bucket is `confirmed` or `near`.
- `monitor`
  - Best recent bucket is `observe` only.

## T-STOCK-V01 Rule

- Refresh cadence: weekly
- Lookback window: last 4 stock watchlist snapshots
- Cooling grace: last 2 prior weekly snapshots
- Source files:
  - `t_stock_v01_latest_watchlist_YYYY-MM-DD.csv`
- Rolling outputs:
  - `t_stock_v01_rolling_watchlist_YYYY-MM-DD.csv`
  - `t_stock_v01_rolling_watchlist_summary_20260331.csv`

## T-ETF-V01 Rule

- Refresh cadence: monthly
- Lookback window: last 3 ETF watchlist snapshots
- Cooling grace: last 2 prior monthly snapshots
- Source files:
  - `etf_tseries_pit_latest_watchlist_YYYY-MM-DD.csv`
- Rolling outputs:
  - `etf_tseries_pit_rolling_watchlist_YYYY-MM-DD.csv`
  - `etf_tseries_pit_rolling_watchlist_summary_20260401.csv`

## Current Snapshot Interpretation

### T-STOCK-V01

- Current candidates remain highest priority.
- Cooling names should not be treated as immediately invalid.
- Cooling names remain part of the rolling watchlist so users can continue observing follow-through after the week they were first detected.

### T-ETF-V01

- Current candidates remain highest priority.
- Cooling names are retained for short continuity in monthly monitoring.
- Inverse and leveraged ETFs are excluded from the current operational model.

## Implementation Scripts

- `D:\Quant\scripts\build_t_stock_v01_rolling_watchlist.py`
- `D:\Quant\scripts\build_etf_tseries_pit_rolling_watchlist.py`

These scripts are now included in the normal T-series operational refresh flow.
