# T-series Operational DB Design (2026-03-31)

## Why
- `T-STOCK-V01` and `T-ETF-V01` are no longer pure research prototypes.
- They now have operational watchlists, risk filters, and shadow tracking.
- Continuing to manage them only with `model_research.db + CSV` is workable for research, but weak for sustained operations.

## Separation Principle
- Keep `model_research.db` as the research / experiment DB.
- Add a separate operational DB for `T-series`.
- Do not mix `T-series` shadow outputs into existing `S-series` publish tables yet.

## Recommended DB
- DB file: `D:\Quant\data\db\tseries_operational.db`
- schema file: `D:\Quant\src\quant_service\schema_tseries_operational.sql`
- init script: `D:\Quant\src\quant_service\init_tseries_operational_db.py`

## Core Tables
- `ts_meta_models`
  - model metadata for `T-STOCK-V01`, `T-ETF-V01`
- `ts_threshold_profiles`
  - stage1/stage2 threshold profiles and risk filter versions
- `ts_runs`
  - each shadow refresh run
- `ts_theme_labels`
  - internal stock theme labels and future ETF labeling if needed
- `ts_candidates_latest`
  - latest watchlist snapshot (`confirmed / near / observe`)
- `ts_candidates_history`
  - historical candidate rows by signal date / horizon
- `ts_shadow_tracking_summary`
  - summarized historical hit rates
- `ts_artifacts`
  - output file paths for run-level traceability

## Why a Separate DB
- avoids touching current `quant_service.db` and `quant_service_detail.db`
- allows `T-series` to remain shadow-mode while still being queryable
- cleanly separates discovery / promotion models from current published ranking models
- makes later service/QS integration easier without polluting existing `S-series` schema

## Migration Strategy
1. keep current CSV/report outputs unchanged
2. create `tseries_operational.db`
3. add insert/upsert scripts for stock and ETF operational refresh outputs
4. run both file output and DB upsert in parallel for a stabilization period
5. only after stabilization decide whether service-facing tables should read from `tseries_operational.db`

## Current Recommendation
- yes, now is the right time to create the formal operational DB structure
- no, we do not need to merge into existing publish DBs yet
- next practical step is to initialize the DB and then add upsert loaders for stock/ETF shadow refresh results
