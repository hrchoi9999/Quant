CREATE TABLE IF NOT EXISTS run_nav_daily (
  run_id                TEXT NOT NULL,
  date                  TEXT NOT NULL,
  nav                   REAL NOT NULL,
  drawdown              REAL,
  holdings_count        INTEGER,
  cash_weight           REAL,
  exposure              REAL,
  gate_open             INTEGER,
  gate_breadth          REAL,
  benchmark_nav         REAL,
  PRIMARY KEY (run_id, date)
);

CREATE INDEX IF NOT EXISTS idx_run_nav_daily_run_date
ON run_nav_daily (run_id, date);

CREATE TABLE IF NOT EXISTS run_holdings_history (
  run_id                   TEXT NOT NULL,
  date                     TEXT NOT NULL,
  ticker                   TEXT NOT NULL,
  rank_no                  INTEGER,
  weight                   REAL,
  score                    REAL,
  entry_date               TEXT,
  entry_price              REAL,
  current_price            REAL,
  cum_return_since_entry   REAL,
  reason_summary           TEXT,
  PRIMARY KEY (run_id, date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_run_holdings_history_run_date
ON run_holdings_history (run_id, date);

CREATE TABLE IF NOT EXISTS run_trades (
  run_id                TEXT NOT NULL,
  trade_id              TEXT NOT NULL,
  trade_date            TEXT NOT NULL,
  ticker                TEXT NOT NULL,
  side                  TEXT NOT NULL,
  quantity              REAL,
  weight_before         REAL,
  weight_after          REAL,
  trade_price           REAL,
  turnover_contrib      REAL,
  trade_reason          TEXT,
  PRIMARY KEY (run_id, trade_id)
);

CREATE INDEX IF NOT EXISTS idx_run_trades_run_date
ON run_trades (run_id, trade_date);

CREATE TABLE IF NOT EXISTS run_signal_details_s2 (
  run_id                TEXT NOT NULL,
  date                  TEXT NOT NULL,
  ticker                TEXT NOT NULL,
  regime_value          REAL,
  regime_label          TEXT,
  growth_score          REAL,
  sma140                REAL,
  above_sma_flag        INTEGER,
  market_gate_flag      INTEGER,
  selection_rank        INTEGER,
  PRIMARY KEY (run_id, date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_run_signal_details_s2_run_date
ON run_signal_details_s2 (run_id, date);

CREATE TABLE IF NOT EXISTS run_signal_details_s3 (
  run_id                TEXT NOT NULL,
  date                  TEXT NOT NULL,
  ticker                TEXT NOT NULL,
  s3_score              REAL,
  mom20                 REAL,
  mom20_pct             REAL,
  vol_ratio_20          REAL,
  vol_ratio_pct         REAL,
  breakout60            INTEGER,
  ma60                  REAL,
  ma120                 REAL,
  ma60_slope            REAL,
  growth_score          REAL,
  fund_accel_score      REAL,
  PRIMARY KEY (run_id, date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_run_signal_details_s3_run_date
ON run_signal_details_s3 (run_id, date);

CREATE TABLE IF NOT EXISTS run_signal_details_s3_core2 (
  run_id                TEXT NOT NULL,
  date                  TEXT NOT NULL,
  ticker                TEXT NOT NULL,
  core_score            REAL,
  tie_score             REAL,
  s3_score              REAL,
  gate_open             INTEGER,
  gate_breadth          REAL,
  mom20_pct             REAL,
  vol_ratio_pct         REAL,
  fund_level_pct        REAL,
  fund_accel_pct        REAL,
  PRIMARY KEY (run_id, date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_run_signal_details_s3_core2_run_date
ON run_signal_details_s3_core2 (run_id, date);
