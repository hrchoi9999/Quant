PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ts_meta_models (
  model_code             TEXT PRIMARY KEY,
  display_name           TEXT NOT NULL,
  asset_scope            TEXT NOT NULL,
  stage_structure        TEXT NOT NULL,
  version_label          TEXT NOT NULL,
  status                 TEXT NOT NULL DEFAULT 'active',
  notes                  TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ts_threshold_profiles (
  profile_id             TEXT PRIMARY KEY,
  model_code             TEXT NOT NULL,
  profile_code           TEXT NOT NULL,
  asof_date              TEXT NOT NULL,
  stage1_threshold       REAL,
  stage2_confirmed_th    REAL,
  stage2_near_th         REAL,
  risk_filter_version    TEXT,
  is_current             INTEGER NOT NULL DEFAULT 0,
  notes                  TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (model_code) REFERENCES ts_meta_models(model_code)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ts_threshold_profiles_current
ON ts_threshold_profiles (model_code, profile_code, asof_date);

CREATE TABLE IF NOT EXISTS ts_runs (
  ts_run_id              TEXT PRIMARY KEY,
  model_code             TEXT NOT NULL,
  profile_id             TEXT,
  asof_date              TEXT NOT NULL,
  refresh_kind           TEXT NOT NULL,
  status                 TEXT NOT NULL,
  source_snapshot_ref    TEXT,
  started_at             TEXT,
  finished_at            TEXT,
  outdir                 TEXT,
  notes                  TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (model_code) REFERENCES ts_meta_models(model_code),
  FOREIGN KEY (profile_id) REFERENCES ts_threshold_profiles(profile_id)
);

CREATE INDEX IF NOT EXISTS idx_ts_runs_model_asof
ON ts_runs (model_code, asof_date);

CREATE TABLE IF NOT EXISTS ts_theme_labels (
  model_code             TEXT NOT NULL,
  asof_date              TEXT NOT NULL,
  ticker                 TEXT NOT NULL,
  name                   TEXT,
  market                 TEXT,
  theme_bucket           TEXT NOT NULL,
  theme_name_kr          TEXT,
  label_source           TEXT,
  label_scope            TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (model_code, asof_date, ticker),
  FOREIGN KEY (model_code) REFERENCES ts_meta_models(model_code)
);

CREATE INDEX IF NOT EXISTS idx_ts_theme_labels_model_theme
ON ts_theme_labels (model_code, theme_bucket, asof_date);

CREATE TABLE IF NOT EXISTS ts_candidates_latest (
  model_code             TEXT NOT NULL,
  asof_date              TEXT NOT NULL,
  candidate_bucket       TEXT NOT NULL,
  ticker                 TEXT NOT NULL,
  name                   TEXT,
  market                 TEXT,
  asset_class            TEXT,
  group_key              TEXT,
  theme_bucket           TEXT,
  theme_name_kr          TEXT,
  is_s2_overlap          INTEGER,
  stage1_prob            REAL,
  stage2_prob            REAL,
  mcap                   REAL,
  liquidity_20d_value    REAL,
  risk_filtered_flag     INTEGER NOT NULL DEFAULT 0,
  source_run_id          TEXT,
  details_json           TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (model_code, asof_date, ticker),
  FOREIGN KEY (model_code) REFERENCES ts_meta_models(model_code),
  FOREIGN KEY (source_run_id) REFERENCES ts_runs(ts_run_id)
);

CREATE INDEX IF NOT EXISTS idx_ts_candidates_latest_model_bucket
ON ts_candidates_latest (model_code, asof_date, candidate_bucket);

CREATE TABLE IF NOT EXISTS ts_candidates_history (
  model_code             TEXT NOT NULL,
  signal_date            TEXT NOT NULL,
  horizon                TEXT,
  candidate_bucket       TEXT NOT NULL,
  ticker                 TEXT NOT NULL,
  name                   TEXT,
  market                 TEXT,
  asset_class            TEXT,
  group_key              TEXT,
  theme_bucket           TEXT,
  theme_name_kr          TEXT,
  stage1_prob            REAL,
  stage2_prob            REAL,
  actual_t10_hit         INTEGER,
  actual_t3_hit          INTEGER,
  source_run_id          TEXT,
  details_json           TEXT,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (model_code, signal_date, horizon, ticker, candidate_bucket),
  FOREIGN KEY (model_code) REFERENCES ts_meta_models(model_code),
  FOREIGN KEY (source_run_id) REFERENCES ts_runs(ts_run_id)
);

CREATE INDEX IF NOT EXISTS idx_ts_candidates_history_model_signal
ON ts_candidates_history (model_code, signal_date, candidate_bucket);

CREATE TABLE IF NOT EXISTS ts_shadow_tracking_summary (
  model_code             TEXT NOT NULL,
  asof_date              TEXT NOT NULL,
  candidate_bucket       TEXT NOT NULL,
  horizon                TEXT,
  obs_n                  INTEGER,
  t10_hit_rate           REAL,
  t3_hit_rate            REAL,
  avg_stage1_prob        REAL,
  avg_stage2_prob        REAL,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (model_code, asof_date, candidate_bucket, horizon),
  FOREIGN KEY (model_code) REFERENCES ts_meta_models(model_code)
);

CREATE TABLE IF NOT EXISTS ts_artifacts (
  ts_run_id              TEXT NOT NULL,
  artifact_type          TEXT NOT NULL,
  artifact_path          TEXT NOT NULL,
  created_at             TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (ts_run_id, artifact_type, artifact_path),
  FOREIGN KEY (ts_run_id) REFERENCES ts_runs(ts_run_id)
);
