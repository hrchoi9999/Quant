PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS c_runs (
    run_id TEXT PRIMARY KEY,
    asof_date TEXT NOT NULL,
    model_code TEXT NOT NULL,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_price_max_date TEXT,
    stock_universe_count INTEGER,
    etf_universe_count INTEGER,
    started_at TEXT,
    finished_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS c_return_series (
    asof_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT,
    asset_type TEXT,
    market TEXT,
    theme_bucket TEXT,
    theme_name_kr TEXT,
    close REAL,
    volume REAL,
    trading_value REAL,
    daily_return REAL,
    weekly_return REAL,
    monthly_return REAL,
    vol_20d REAL,
    liquidity_20d_value REAL,
    data_quality_flag TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asof_date, ticker)
);

CREATE TABLE IF NOT EXISTS c_theme_return_series (
    asof_date TEXT NOT NULL,
    theme_bucket TEXT NOT NULL,
    member_count INTEGER,
    avg_daily_return REAL,
    avg_weekly_return REAL,
    median_weekly_return REAL,
    positive_ratio REAL,
    negative_ratio REAL,
    dispersion_score REAL,
    liquidity_sum REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asof_date, theme_bucket)
);

CREATE TABLE IF NOT EXISTS c_relationship_edges (
    asof_date TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_name TEXT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_name TEXT,
    relation_type TEXT NOT NULL,
    corr_20d REAL,
    corr_60d REAL,
    corr_120d REAL,
    corr_252d REAL,
    direction_consistency REAL,
    persistence_days INTEGER,
    persistence_ratio_120d REAL,
    break_count_120d INTEGER,
    stability_score REAL,
    relationship_strength_score REAL,
    relationship_persistence_score REAL,
    relationship_confidence_score REAL,
    liquidity_score REAL,
    rank_positive INTEGER,
    rank_negative INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asof_date, source_type, source_id, target_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_c_edges_source
ON c_relationship_edges(asof_date, source_type, source_id, relation_type, relationship_confidence_score DESC);

CREATE INDEX IF NOT EXISTS idx_c_edges_target
ON c_relationship_edges(asof_date, target_type, target_id, relation_type, relationship_confidence_score DESC);

CREATE TABLE IF NOT EXISTS c_model_overlay_scores (
    asof_date TEXT NOT NULL,
    scope TEXT NOT NULL,
    base_model_code TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT,
    base_bucket TEXT,
    base_score REAL,
    positive_relation_count INTEGER,
    negative_relation_count INTEGER,
    theme_support_score REAL,
    etf_support_score REAL,
    market_beta_support_score REAL,
    hedge_risk_score REAL,
    cluster_concentration_score REAL,
    c_overlay_score REAL,
    final_adjusted_score REAL,
    top_positive_etf TEXT,
    top_market_beta_proxy TEXT,
    top_negative_etf TEXT,
    relationship_status TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asof_date, scope, base_model_code, ticker)
);

CREATE TABLE IF NOT EXISTS c_shadow_tracking (
    asof_date TEXT NOT NULL,
    scope TEXT NOT NULL,
    base_model_code TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT,
    base_bucket TEXT,
    c_overlay_score REAL,
    relationship_status TEXT,
    top_positive_etf TEXT,
    top_market_beta_proxy TEXT,
    top_negative_etf TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asof_date, scope, base_model_code, ticker)
);
