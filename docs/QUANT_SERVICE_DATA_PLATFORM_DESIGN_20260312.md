# QuantService Data Platform Design

## Purpose

This document defines the target data platform for:

- up to 12 quant models
- backtest result storage
- detailed output storage
- QuantService frontend/API delivery
- post-development Google Sheet management sync

The design principle is:

1. DB is the system of record.
2. CSV is an optional export artifact.
3. Google Sheets is a management view generated from DB after DB development is complete.
4. QuantService frontend must consume data only through API, never by directly reading files or SQLite tables.

## Scope

This design covers three deliverables:

1. `quant_service.db` SQLite schema draft
2. mapping of current S2, S3, S3 core2 outputs into the schema
3. API-oriented integration design for QuantService frontend

## High-Level Architecture

```text
price.db / regime.db / fundamentals.db / features_s3.db
    -> daily batch runners
    -> backtest execution
    -> quant_service.db (official result store)
    -> API layer
    -> QuantService frontend

quant_service.db
    -> optional CSV export
    -> optional Google Sheet sync (management only)
```

## Design Principles

- Separate source data from result data.
- Separate internal run data from published service data.
- Treat each backtest run as immutable.
- Promote a completed run into published service data through a controlled publish step.
- Keep model-common tables generic.
- Keep model-specific logic details in extension tables.
- Support up to 12 models without changing service contracts.

## DB Choice

Phase 1 should use SQLite because the current system already uses SQLite and local batch execution.

Recommended file:

- `D:\Quant\data\db\quant_service.db`

Phase 2 can migrate the same schema to PostgreSQL when QuantService becomes multi-user or requires concurrent writes.

## Schema Overview

Table groups:

- `meta_*`: model catalog and version catalog
- `run_*`: raw backtest execution records
- `pub_*`: published service-facing tables
- `ops_*`: quality, lineage, promotion, and sync logs

## Core IDs

### `model_code`

Stable model identifier.

Examples:

- `S2`
- `S3`
- `S3_CORE2`
- future: `S4`, `ALPHA_ROTATION`, `DIV_GROWTH`

### `model_version_id`

Immutable logic version for one model.

Examples:

- `S2__2026_03_12_001`
- `S3__2026_03_12_001`
- `S3_CORE2__2026_03_12_001`

### `batch_id`

One integrated daily execution batch.

Example:

- `BATCH__2026_03_12__DAILY`

### `run_id`

One actual model run.

Example:

- `RUN__S2__2026_03_12__2013_10_14__2026_03_12__001`

## Schema Draft

### 1. Metadata

```sql
CREATE TABLE IF NOT EXISTS meta_models (
  model_code           TEXT PRIMARY KEY,
  display_name         TEXT NOT NULL,
  description          TEXT,
  asset_class          TEXT,
  rebalance_frequency  TEXT,
  benchmark_code       TEXT,
  risk_grade           TEXT,
  status               TEXT NOT NULL DEFAULT 'active',
  service_enabled      INTEGER NOT NULL DEFAULT 1,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta_model_versions (
  model_version_id     TEXT PRIMARY KEY,
  model_code           TEXT NOT NULL,
  version_label        TEXT NOT NULL,
  code_ref             TEXT,
  logic_summary        TEXT,
  parameter_schema_json TEXT,
  is_current_internal  INTEGER NOT NULL DEFAULT 0,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS meta_benchmarks (
  benchmark_code       TEXT PRIMARY KEY,
  display_name         TEXT NOT NULL,
  description          TEXT
);
```

### 2. Batch and Run Ledger

```sql
CREATE TABLE IF NOT EXISTS run_batches (
  batch_id             TEXT PRIMARY KEY,
  batch_type           TEXT NOT NULL,
  asof_date            TEXT NOT NULL,
  status               TEXT NOT NULL,
  started_at           TEXT,
  finished_at          TEXT,
  triggered_by         TEXT,
  notes                TEXT
);

CREATE TABLE IF NOT EXISTS run_data_snapshots (
  snapshot_id          TEXT PRIMARY KEY,
  batch_id             TEXT NOT NULL,
  price_asof           TEXT,
  regime_asof          TEXT,
  fundamentals_asof    TEXT,
  s3_price_features_asof TEXT,
  s3_fund_features_asof  TEXT,
  universe_asof        TEXT,
  universe_name        TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id)
);

CREATE TABLE IF NOT EXISTS run_runs (
  run_id               TEXT PRIMARY KEY,
  batch_id             TEXT NOT NULL,
  snapshot_id          TEXT,
  model_code           TEXT NOT NULL,
  model_version_id     TEXT NOT NULL,
  run_kind             TEXT NOT NULL DEFAULT 'backtest',
  start_date           TEXT NOT NULL,
  end_date             TEXT NOT NULL,
  asof_date            TEXT NOT NULL,
  status               TEXT NOT NULL,
  exit_code            INTEGER,
  started_at           TEXT,
  finished_at          TEXT,
  runtime_seconds      REAL,
  outdir               TEXT,
  error_message        TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id),
  FOREIGN KEY (snapshot_id) REFERENCES run_data_snapshots(snapshot_id),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code),
  FOREIGN KEY (model_version_id) REFERENCES meta_model_versions(model_version_id)
);

CREATE INDEX IF NOT EXISTS idx_run_runs_model_asof
ON run_runs (model_code, asof_date);
```

### 3. Run Parameters and Summary

```sql
CREATE TABLE IF NOT EXISTS run_params (
  run_id               TEXT NOT NULL,
  param_key            TEXT NOT NULL,
  param_value          TEXT,
  PRIMARY KEY (run_id, param_key),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS run_summary (
  run_id               TEXT PRIMARY KEY,
  cagr                 REAL,
  sharpe               REAL,
  sortino              REAL,
  mdd                  REAL,
  calmar               REAL,
  total_return         REAL,
  avg_daily_ret        REAL,
  vol_daily            REAL,
  win_rate             REAL,
  rebalance_count      INTEGER,
  trade_count          INTEGER,
  turnover             REAL,
  avg_holding_count    REAL,
  final_nav            REAL,
  benchmark_total_return REAL,
  benchmark_cagr       REAL,
  benchmark_mdd        REAL,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);
```

### 4. Time Series and Detailed Output

```sql
CREATE TABLE IF NOT EXISTS run_nav_daily (
  run_id               TEXT NOT NULL,
  date                 TEXT NOT NULL,
  nav                  REAL NOT NULL,
  drawdown             REAL,
  holdings_count       INTEGER,
  cash_weight          REAL,
  exposure             REAL,
  gate_open            INTEGER,
  gate_breadth         REAL,
  benchmark_nav        REAL,
  PRIMARY KEY (run_id, date),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_run_nav_daily_date
ON run_nav_daily (date);

CREATE TABLE IF NOT EXISTS run_holdings_history (
  run_id               TEXT NOT NULL,
  date                 TEXT NOT NULL,
  ticker               TEXT NOT NULL,
  rank_no              INTEGER,
  weight               REAL,
  score                REAL,
  entry_date           TEXT,
  entry_price          REAL,
  current_price        REAL,
  cum_return_since_entry REAL,
  reason_summary       TEXT,
  PRIMARY KEY (run_id, date, ticker),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_run_holdings_history_date
ON run_holdings_history (date);

CREATE TABLE IF NOT EXISTS run_trades (
  run_id               TEXT NOT NULL,
  trade_id             TEXT NOT NULL,
  trade_date           TEXT NOT NULL,
  ticker               TEXT NOT NULL,
  side                 TEXT NOT NULL,
  quantity             REAL,
  weight_before        REAL,
  weight_after         REAL,
  trade_price          REAL,
  turnover_contrib     REAL,
  trade_reason         TEXT,
  PRIMARY KEY (run_id, trade_id),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_run_trades_date
ON run_trades (trade_date);

CREATE TABLE IF NOT EXISTS run_artifacts (
  run_id               TEXT NOT NULL,
  artifact_type        TEXT NOT NULL,
  artifact_path        TEXT NOT NULL,
  file_format          TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (run_id, artifact_type, artifact_path),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);
```

### 5. Model-Specific Signal Extension Tables

Common tables should remain generic. Model-specific internals should be separated.

```sql
CREATE TABLE IF NOT EXISTS run_signal_details_s2 (
  run_id               TEXT NOT NULL,
  date                 TEXT NOT NULL,
  ticker               TEXT NOT NULL,
  regime_value         REAL,
  regime_label         TEXT,
  growth_score         REAL,
  sma140               REAL,
  above_sma_flag       INTEGER,
  market_gate_flag     INTEGER,
  selection_rank       INTEGER,
  PRIMARY KEY (run_id, date, ticker),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS run_signal_details_s3 (
  run_id               TEXT NOT NULL,
  date                 TEXT NOT NULL,
  ticker               TEXT NOT NULL,
  s3_score             REAL,
  mom20                REAL,
  mom20_pct            REAL,
  vol_ratio_20         REAL,
  vol_ratio_pct        REAL,
  breakout60           INTEGER,
  ma60                 REAL,
  ma120                REAL,
  ma60_slope           REAL,
  growth_score         REAL,
  fund_accel_score     REAL,
  PRIMARY KEY (run_id, date, ticker),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS run_signal_details_s3_core2 (
  run_id               TEXT NOT NULL,
  date                 TEXT NOT NULL,
  ticker               TEXT NOT NULL,
  core_score           REAL,
  tie_score            REAL,
  s3_score             REAL,
  gate_open            INTEGER,
  gate_breadth         REAL,
  mom20_pct            REAL,
  vol_ratio_pct        REAL,
  fund_level_pct       REAL,
  fund_accel_pct       REAL,
  PRIMARY KEY (run_id, date, ticker),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);
```

### 6. Published Service Tables

These are the tables the API should read first for frontend delivery.

```sql
CREATE TABLE IF NOT EXISTS pub_model_current (
  model_code           TEXT PRIMARY KEY,
  published_run_id     TEXT NOT NULL,
  published_at         TEXT NOT NULL,
  display_name         TEXT NOT NULL,
  short_description    TEXT,
  long_description     TEXT,
  benchmark_code       TEXT,
  data_asof            TEXT NOT NULL,
  signal_asof          TEXT,
  latest_nav           REAL,
  latest_drawdown      REAL,
  latest_holdings_count INTEGER,
  latest_rebalance_date TEXT,
  risk_grade           TEXT,
  disclaimer_text      TEXT,
  FOREIGN KEY (published_run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS pub_model_performance (
  model_code           TEXT NOT NULL,
  period_code          TEXT NOT NULL,
  asof_date            TEXT NOT NULL,
  return_pct           REAL,
  benchmark_return_pct REAL,
  excess_return_pct    REAL,
  mdd                  REAL,
  sharpe               REAL,
  PRIMARY KEY (model_code, period_code, asof_date),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS pub_model_nav_history (
  model_code           TEXT NOT NULL,
  date                 TEXT NOT NULL,
  nav                  REAL NOT NULL,
  benchmark_nav        REAL,
  drawdown             REAL,
  PRIMARY KEY (model_code, date),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS pub_model_current_holdings (
  model_code           TEXT NOT NULL,
  asof_date            TEXT NOT NULL,
  ticker               TEXT NOT NULL,
  rank_no              INTEGER,
  weight               REAL,
  score                REAL,
  rationale_title      TEXT,
  rationale_detail     TEXT,
  PRIMARY KEY (model_code, asof_date, ticker),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS pub_model_rebalance_events (
  model_code           TEXT NOT NULL,
  event_date           TEXT NOT NULL,
  ticker               TEXT NOT NULL,
  event_type           TEXT NOT NULL,
  detail_text          TEXT,
  PRIMARY KEY (model_code, event_date, ticker, event_type),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);
```

### 7. Operational and Audit Tables

```sql
CREATE TABLE IF NOT EXISTS ops_quality_checks (
  check_id             TEXT PRIMARY KEY,
  batch_id             TEXT,
  run_id               TEXT,
  check_type           TEXT NOT NULL,
  status               TEXT NOT NULL,
  detail_json          TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS ops_publish_history (
  publish_id           TEXT PRIMARY KEY,
  model_code           TEXT NOT NULL,
  previous_run_id      TEXT,
  new_run_id           TEXT NOT NULL,
  published_at         TEXT NOT NULL,
  published_by         TEXT,
  note_text            TEXT,
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code),
  FOREIGN KEY (new_run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS ops_gsheet_sync_log (
  sync_id              TEXT PRIMARY KEY,
  batch_id             TEXT,
  model_code           TEXT,
  sync_target          TEXT NOT NULL,
  status               TEXT NOT NULL,
  started_at           TEXT,
  finished_at          TEXT,
  detail_text          TEXT,
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);
```

## Mapping Current Models Into the Schema

### S2

Current sources:

- runner: `src/backtest/run_backtest_v5.py`
- delegated runner: `src/backtest/run_backtest_s2_refactor_v1.py`
- outputs: summary, equity, holdings, ledger, snapshot, trades, windows

Mapping:

- `run_runs`: one S2 execution row
- `run_params`: all CLI flags
- `run_summary`: summary CSV values
- `run_nav_daily`: equity curve
- `run_holdings_history`: holdings CSV and snapshot history
- `run_trades`: trades CSV
- `run_signal_details_s2`: regime, SMA, market gate, rank data when available
- `run_artifacts`: all saved CSV file paths

### S3

Current sources:

- runner: `src/experiments/run_s3_trend_hold_top20.py`
- outputs: nav, holdings history, last holdings

Mapping:

- `run_runs`
- `run_params`
- `run_summary`: derived summary metrics should be calculated after run
- `run_nav_daily`
- `run_holdings_history`
- `run_signal_details_s3`
- `run_artifacts`

### S3 core2

Current sources:

- runner: `src/experiments/run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py`
- outputs: nav, holdings history, last holdings with gate data

Mapping:

- `run_runs`
- `run_params`
- `run_summary`
- `run_nav_daily`
- `run_holdings_history`
- `run_signal_details_s3_core2`
- `run_artifacts`

### Future Models up to 12

For future models:

- register the model in `meta_models`
- register logic versions in `meta_model_versions`
- reuse `run_runs`, `run_params`, `run_summary`, `run_nav_daily`, `run_holdings_history`, `run_trades`, `run_artifacts`
- create a new `run_signal_details_<model>` table only if the model has unique internal signals that should be preserved

This prevents schema explosion in common service tables.

## Publish Workflow

Publishing must be an explicit step after validation.

### Internal flow

1. Daily batch creates `run_batches`
2. Data snapshot row is recorded in `run_data_snapshots`
3. Each model writes one row into `run_runs`
4. Detailed outputs are inserted into `run_*`
5. Quality checks are inserted into `ops_quality_checks`
6. Approved run is promoted into `pub_*`
7. Optional management sync pushes selected published data to Google Sheets

### Why publish separation is required

- a run may succeed but not be approved for user exposure
- multiple experimental runs may exist for the same day
- QuantService should only read officially published data

## API Integration Design

Frontend must not read CSV files or SQLite directly.

### Required API rule

QuantService frontend consumes only API responses.

Recommended backend structure:

- Batch layer writes to `quant_service.db`
- API service reads from `pub_*` and selected `meta_*`
- Admin API can read `run_*` for internal monitoring

### Public API examples

- `GET /api/v1/models`
  - list active published models
- `GET /api/v1/models/{model_code}`
  - model overview and latest snapshot
- `GET /api/v1/models/{model_code}/performance`
  - period return cards and benchmark comparison
- `GET /api/v1/models/{model_code}/nav?from=...&to=...`
  - chart data
- `GET /api/v1/models/{model_code}/holdings/current`
  - current holdings
- `GET /api/v1/models/{model_code}/rebalance-events`
  - recent inclusion and exclusion history

### Internal/admin API examples

- `GET /api/v1/admin/batches/{batch_id}`
- `GET /api/v1/admin/runs/{run_id}`
- `GET /api/v1/admin/runs/{run_id}/signals`
- `POST /api/v1/admin/publish/{run_id}`
- `POST /api/v1/admin/gsheet-sync/{batch_id}`

### API response contract rule

The API should never expose internal raw schema directly.

Instead:

- backend transforms DB rows into stable API DTOs
- frontend depends on DTO contracts, not table names
- DB can evolve without breaking frontend

## Google Sheets Design

Google Sheets should be treated as a management destination only after DB development is complete.

### Rule

- source of truth: `quant_service.db`
- Google Sheets: secondary sync target

### Recommended sync contents

Only publish management summaries:

- latest published model snapshot
- latest holdings summary
- latest performance summary
- batch execution status

Do not push all detailed holdings history or all raw signal rows to Google Sheets.

That data belongs in DB and API.

## CSV Design After DB Adoption

CSV should become optional export only.

Recommended outputs:

- keep `summary.csv` for manual sharing
- keep `current_holdings.csv` for quick review
- keep full detailed CSV only on demand or debug mode

All CSV paths should be recorded in `run_artifacts`.

## Ingestion Design From Existing Code

Current code writes CSV directly.

Recommended migration path:

### Phase 1

- keep current CSV generation
- add DB writer after each model run
- insert `run_runs`, `run_summary`, `run_nav_daily`, `run_holdings_history`, `run_trades`, `run_artifacts`

### Phase 2

- move published data generation to DB-driven promotion job
- frontend reads only API over `pub_*`

### Phase 3

- make CSV optional
- Google Sheet sync reads from `pub_*` and `ops_*`

## Suggested Initial API DTOs

### Model list item

```json
{
  "modelCode": "S2",
  "displayName": "Quant S2",
  "dataAsOf": "2026-03-12",
  "latestNav": 2.84,
  "periodReturns": {
    "m1": 0.031,
    "m3": 0.087,
    "ytd": 0.124,
    "itd": 1.841
  },
  "riskGrade": "MEDIUM"
}
```

### Current holdings item

```json
{
  "ticker": "005930",
  "name": "Samsung Electronics",
  "weight": 0.051,
  "rank": 3,
  "score": 0.912,
  "rationaleTitle": "Trend and regime aligned",
  "rationaleDetail": "Selected by active regime and above SMA filter."
}
```

## Recommended First Development Order

1. Create `quant_service.db`
2. Create `meta_*`, `run_*`, `ops_*` tables
3. Add DB writer modules for S2, S3, S3 core2
4. Backfill recent historical runs into DB
5. Add publish promotion job into `pub_*`
6. Build API on top of `pub_*`
7. After DB and API are stable, add Google Sheet sync from DB

## Immediate Implementation Target

The first implementation target should cover:

- `meta_models`
- `meta_model_versions`
- `run_batches`
- `run_data_snapshots`
- `run_runs`
- `run_params`
- `run_summary`
- `run_nav_daily`
- `run_holdings_history`
- `run_trades`
- `run_artifacts`
- `ops_quality_checks`
- `ops_publish_history`

Then add:

- `pub_model_current`
- `pub_model_performance`
- `pub_model_nav_history`
- `pub_model_current_holdings`
- `pub_model_rebalance_events`

## Final Recommendation

The project should move from:

- source DBs + CSV + Google Sheets

to:

- source DBs + `quant_service.db` + API + optional CSV + optional management Sheets

This is the most scalable path for:

- 12-model expansion
- historical auditability
- service-grade frontend delivery
- later migration to server DB infrastructure
