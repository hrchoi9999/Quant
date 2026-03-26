from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Quant")
CORE_DB_PATH = PROJECT_ROOT / r"data\db\quant_service.db"
DETAIL_DB_PATH = PROJECT_ROOT / r"data\db\quant_service_detail.db"
CORE_SCHEMA_PATH = PROJECT_ROOT / r"src\quant_service\schema_quant_service.sql"
DETAIL_SCHEMA_PATH = PROJECT_ROOT / r"src\quant_service\schema_quant_service_detail.sql"

SEED_MODELS = [
    ("S2", "Quant S2", "Regime-aware weekly top-N model with fundamentals and market gate.", "KR_EQUITY", "W", "KRX_BENCHMARK", "MEDIUM", "active", 1),
    ("S3", "Quant S3", "Trend-hold top 20 model using price and fundamental acceleration features.", "KR_EQUITY", "W", "KRX_BENCHMARK", "MEDIUM_HIGH", "active", 1),
    ("S3_CORE2", "Quant S3 core2", "Trend-hold top 20 core model with market breadth gate and tie-break logic.", "KR_EQUITY", "W", "KRX_BENCHMARK", "HIGH", "active", 1),
]

SEED_MODEL_VERSIONS = [
    ("S2__2026_03_12_001", "S2", "2026.03.12.001", "src.backtest.run_backtest_s2_refactor_v1", "Current S2 refactor runner baseline.", None, 1),
    ("S3__2026_03_12_001", "S3", "2026.03.12.001", "src.experiments.run_s3_trend_hold_top20", "Current S3 base runner with CLI date support.", None, 1),
    ("S3_CORE2__2026_03_12_001", "S3_CORE2", "2026.03.12.001", "src.experiments.run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP", "Current S3 core2 runner with breadth gate.", None, 1),
]

SEED_BENCHMARKS = [
    ("KRX_BENCHMARK", "KR equity benchmark", "Placeholder benchmark record for QuantService model comparisons."),
]

LEGACY_DETAIL_TABLES = [
    "run_nav_daily",
    "run_holdings_history",
    "run_trades",
    "run_signal_details_s2",
    "run_signal_details_s3",
    "run_signal_details_s3_core2",
]


def _init_core(db_path: Path, schema_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(schema_sql)
        for table in LEGACY_DETAIL_TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        con.executemany(
            """
            INSERT INTO meta_benchmarks (benchmark_code, display_name, description)
            VALUES (?, ?, ?)
            ON CONFLICT(benchmark_code) DO UPDATE SET
              display_name=excluded.display_name,
              description=excluded.description
            """,
            SEED_BENCHMARKS,
        )
        con.executemany(
            """
            INSERT INTO meta_models (
              model_code, display_name, description, asset_class, rebalance_frequency,
              benchmark_code, risk_grade, status, service_enabled
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_code) DO UPDATE SET
              display_name=excluded.display_name,
              description=excluded.description,
              asset_class=excluded.asset_class,
              rebalance_frequency=excluded.rebalance_frequency,
              benchmark_code=excluded.benchmark_code,
              risk_grade=excluded.risk_grade,
              status=excluded.status,
              service_enabled=excluded.service_enabled,
              updated_at=datetime('now')
            """,
            SEED_MODELS,
        )
        con.executemany(
            """
            INSERT INTO meta_model_versions (
              model_version_id, model_code, version_label, code_ref,
              logic_summary, parameter_schema_json, is_current_internal
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_version_id) DO UPDATE SET
              model_code=excluded.model_code,
              version_label=excluded.version_label,
              code_ref=excluded.code_ref,
              logic_summary=excluded.logic_summary,
              parameter_schema_json=excluded.parameter_schema_json,
              is_current_internal=excluded.is_current_internal
            """,
            SEED_MODEL_VERSIONS,
        )
        con.commit()
    finally:
        con.close()


def _init_detail(db_path: Path, schema_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")
    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(schema_sql)
        con.commit()
    finally:
        con.close()


def init(core_db_path: Path = CORE_DB_PATH, detail_db_path: Path = DETAIL_DB_PATH) -> None:
    _init_core(core_db_path, CORE_SCHEMA_PATH)
    _init_detail(detail_db_path, DETAIL_SCHEMA_PATH)


if __name__ == "__main__":
    init()
    print(f"[OK] initialized core: {CORE_DB_PATH}")
    print(f"[OK] initialized detail: {DETAIL_DB_PATH}")
