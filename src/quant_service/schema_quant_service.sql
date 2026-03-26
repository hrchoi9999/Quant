PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta_models (
  model_code            TEXT PRIMARY KEY,
  display_name          TEXT NOT NULL,
  description           TEXT,
  asset_class           TEXT,
  rebalance_frequency   TEXT,
  benchmark_code        TEXT,
  risk_grade            TEXT,
  status                TEXT NOT NULL DEFAULT 'active',
  service_enabled       INTEGER NOT NULL DEFAULT 1,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta_model_versions (
  model_version_id      TEXT PRIMARY KEY,
  model_code            TEXT NOT NULL,
  version_label         TEXT NOT NULL,
  code_ref              TEXT,
  logic_summary         TEXT,
  parameter_schema_json TEXT,
  is_current_internal   INTEGER NOT NULL DEFAULT 0,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS meta_benchmarks (
  benchmark_code        TEXT PRIMARY KEY,
  display_name          TEXT NOT NULL,
  description           TEXT
);

CREATE TABLE IF NOT EXISTS run_batches (
  batch_id              TEXT PRIMARY KEY,
  batch_type            TEXT NOT NULL,
  asof_date             TEXT NOT NULL,
  status                TEXT NOT NULL,
  started_at            TEXT,
  finished_at           TEXT,
  triggered_by          TEXT,
  notes                 TEXT
);

CREATE TABLE IF NOT EXISTS run_data_snapshots (
  snapshot_id             TEXT PRIMARY KEY,
  batch_id                TEXT NOT NULL,
  price_asof              TEXT,
  regime_asof             TEXT,
  fundamentals_asof       TEXT,
  s3_price_features_asof  TEXT,
  s3_fund_features_asof   TEXT,
  universe_asof           TEXT,
  universe_name           TEXT,
  created_at              TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id)
);

CREATE TABLE IF NOT EXISTS run_runs (
  run_id                TEXT PRIMARY KEY,
  batch_id              TEXT NOT NULL,
  snapshot_id           TEXT,
  model_code            TEXT NOT NULL,
  model_version_id      TEXT NOT NULL,
  run_kind              TEXT NOT NULL DEFAULT 'backtest',
  start_date            TEXT NOT NULL,
  end_date              TEXT NOT NULL,
  asof_date             TEXT NOT NULL,
  status                TEXT NOT NULL,
  exit_code             INTEGER,
  started_at            TEXT,
  finished_at           TEXT,
  runtime_seconds       REAL,
  outdir                TEXT,
  error_message         TEXT,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id),
  FOREIGN KEY (snapshot_id) REFERENCES run_data_snapshots(snapshot_id),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code),
  FOREIGN KEY (model_version_id) REFERENCES meta_model_versions(model_version_id)
);

CREATE INDEX IF NOT EXISTS idx_run_runs_model_asof
ON run_runs (model_code, asof_date);

CREATE TABLE IF NOT EXISTS run_params (
  run_id                TEXT NOT NULL,
  param_key             TEXT NOT NULL,
  param_value           TEXT,
  PRIMARY KEY (run_id, param_key),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS run_summary (
  run_id                  TEXT PRIMARY KEY,
  cagr                    REAL,
  sharpe                  REAL,
  sortino                 REAL,
  mdd                     REAL,
  calmar                  REAL,
  total_return            REAL,
  avg_daily_ret           REAL,
  vol_daily               REAL,
  win_rate                REAL,
  rebalance_count         INTEGER,
  trade_count             INTEGER,
  turnover                REAL,
  avg_holding_count       REAL,
  final_nav               REAL,
  benchmark_total_return  REAL,
  benchmark_cagr          REAL,
  benchmark_mdd           REAL,
  created_at              TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
  run_id                TEXT NOT NULL,
  artifact_type         TEXT NOT NULL,
  artifact_path         TEXT NOT NULL,
  file_format           TEXT,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (run_id, artifact_type, artifact_path),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS pub_model_current (
  model_code             TEXT PRIMARY KEY,
  published_run_id       TEXT NOT NULL,
  published_at           TEXT NOT NULL,
  display_name           TEXT NOT NULL,
  short_description      TEXT,
  long_description       TEXT,
  benchmark_code         TEXT,
  data_asof              TEXT NOT NULL,
  signal_asof            TEXT,
  latest_nav             REAL,
  latest_drawdown        REAL,
  latest_holdings_count  INTEGER,
  latest_rebalance_date  TEXT,
  risk_grade             TEXT,
  disclaimer_text        TEXT,
  FOREIGN KEY (published_run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS pub_model_performance (
  model_code             TEXT NOT NULL,
  period_code            TEXT NOT NULL,
  asof_date              TEXT NOT NULL,
  return_pct             REAL,
  benchmark_return_pct   REAL,
  excess_return_pct      REAL,
  mdd                    REAL,
  sharpe                 REAL,
  PRIMARY KEY (model_code, period_code, asof_date),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS pub_model_nav_history (
  model_code             TEXT NOT NULL,
  date                   TEXT NOT NULL,
  nav                    REAL NOT NULL,
  benchmark_nav          REAL,
  drawdown               REAL,
  PRIMARY KEY (model_code, date),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS pub_model_current_holdings (
  model_code             TEXT NOT NULL,
  asof_date              TEXT NOT NULL,
  ticker                 TEXT NOT NULL,
  rank_no                INTEGER,
  weight                 REAL,
  score                  REAL,
  rationale_title        TEXT,
  rationale_detail       TEXT,
  PRIMARY KEY (model_code, asof_date, ticker),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS pub_model_rebalance_events (
  model_code             TEXT NOT NULL,
  event_date             TEXT NOT NULL,
  ticker                 TEXT NOT NULL,
  event_type             TEXT NOT NULL,
  detail_text            TEXT,
  PRIMARY KEY (model_code, event_date, ticker, event_type),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS ops_quality_checks (
  check_id              TEXT PRIMARY KEY,
  batch_id              TEXT,
  run_id                TEXT,
  check_type            TEXT NOT NULL,
  status                TEXT NOT NULL,
  detail_json           TEXT,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id),
  FOREIGN KEY (run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS ops_publish_history (
  publish_id            TEXT PRIMARY KEY,
  model_code            TEXT NOT NULL,
  previous_run_id       TEXT,
  new_run_id            TEXT NOT NULL,
  published_at          TEXT NOT NULL,
  published_by          TEXT,
  note_text             TEXT,
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code),
  FOREIGN KEY (new_run_id) REFERENCES run_runs(run_id)
);

CREATE TABLE IF NOT EXISTS ops_gsheet_sync_log (
  sync_id               TEXT PRIMARY KEY,
  batch_id              TEXT,
  model_code            TEXT,
  sync_target           TEXT NOT NULL,
  status                TEXT NOT NULL,
  started_at            TEXT,
  finished_at           TEXT,
  detail_text           TEXT,
  FOREIGN KEY (batch_id) REFERENCES run_batches(batch_id),
  FOREIGN KEY (model_code) REFERENCES meta_models(model_code)
);
