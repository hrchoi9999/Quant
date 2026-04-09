# T-STOCK-V01 Operational Refresh (2026-03-31)

## Purpose
- Refresh `T-STOCK-V01` operational outputs using existing local data only.
- Do not collect new market data and do not refresh upstream source DBs.
- This refresh does update `tseries_operational.db` after local outputs are rebuilt.

## Refresh Order
1. `build_t_stock_v01_theme_labels.py`
2. `build_t_stock_v01_operational_candidates.py`
3. `build_t_stock_v01_risk_filter.py`
4. `build_t_stock_v01_shadow_tracking.py`
5. `sync_tseries_operational_db.py --model stock`

## Current Operating Rules
- `stage1 >= 0.52`
- `stage2 confirmed >= 0.525`
- `stage2 near >= 0.52`
- market cap floor: `300,000,000,000 KRW`
- internal theme labels: `internal_rule_v2`

## Runner
- `D:\Quant\scripts
un_t_stock_v01_operational_refresh.py`

## Outputs
- latest watchlist
- latest watchlist summary
- risk-filtered candidate files
- historical shadow tracking summary
- synced stock rows in `D:\Quant\data\db	series_operational.db`

## Notes
- This refresh is safe to run repeatedly on the same local snapshot.
- It does not fetch new data.
- Upstream data collection and DB refresh will be attached later, together with ETF side integration.

- Refresh now also builds a rolling watchlist using the latest weekly snapshots.
  - Output: `t_stock_v01_rolling_watchlist_YYYY-MM-DD.csv`
