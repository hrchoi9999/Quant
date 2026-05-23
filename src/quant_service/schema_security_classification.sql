PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS security_classification_master (
    asof_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT,
    asset_type TEXT,
    market TEXT,
    sector_raw TEXT,
    industry_raw TEXT,
    asset_class TEXT,
    group_key TEXT,
    sector_bucket TEXT,
    theme_bucket TEXT,
    theme_name_kr TEXT,
    source TEXT,
    source_quality TEXT,
    confidence_score REAL,
    is_active INTEGER,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asof_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_sec_class_bucket
ON security_classification_master(asof_date, asset_type, theme_bucket, sector_bucket);

CREATE TABLE IF NOT EXISTS security_classification_runs (
    run_id TEXT PRIMARY KEY,
    asof_date TEXT NOT NULL,
    status TEXT NOT NULL,
    stock_universe_count INTEGER,
    etf_universe_count INTEGER,
    classified_count INTEGER,
    missing_sector_count INTEGER,
    source_summary_json TEXT,
    started_at TEXT,
    finished_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
