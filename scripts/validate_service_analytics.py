from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.service_analytics_builder import SERVICE_ANALYTICS_DB, persist_service_analytics

REQUIRED_TABLES = [
    "analytics_model_run_overview",
    "analytics_model_weekly_snapshot",
    "analytics_model_asset_mix_weekly",
    "analytics_model_change_log",
    "analytics_model_change_activity_weekly",
    "analytics_holding_lifecycle",
    "analytics_model_change_impact_weekly",
    "analytics_model_quality_weekly",
    "analytics_model_asset_detail_weekly",
    "analytics_data_quality_checks",
]


def _read_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def main() -> None:
    persist_service_analytics()

    conn = sqlite3.connect(SERVICE_ANALYTICS_DB)
    try:
        existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [table for table in REQUIRED_TABLES if table not in existing]
        if missing:
            raise SystemExit("Missing analytics tables: " + ", ".join(missing))

        overview = _read_table(conn, "analytics_model_run_overview")
        weekly = _read_table(conn, "analytics_model_weekly_snapshot")
        asset_mix = _read_table(conn, "analytics_model_asset_mix_weekly")
        asset_detail = _read_table(conn, "analytics_model_asset_detail_weekly")
        changes = _read_table(conn, "analytics_model_change_log")
        change_activity = _read_table(conn, "analytics_model_change_activity_weekly")
        lifecycle = _read_table(conn, "analytics_holding_lifecycle")
        change_impact = _read_table(conn, "analytics_model_change_impact_weekly")
        quality = _read_table(conn, "analytics_model_quality_weekly")
        quality_checks = _read_table(conn, "analytics_data_quality_checks")
    finally:
        conn.close()

    if overview.empty or weekly.empty or asset_mix.empty or asset_detail.empty or changes.empty or change_activity.empty or lifecycle.empty or change_impact.empty or quality.empty or quality_checks.empty:
        raise SystemExit("Core analytics tables must not be empty")

    required_models = {"S2", "S3", "S3_CORE2", "S4", "S5", "S6"}
    overview_models = set(overview["model_code"].dropna().astype(str))
    missing_models = sorted(required_models - overview_models)
    if missing_models:
        raise SystemExit("Missing models in analytics_model_run_overview: " + ", ".join(missing_models))

    if (asset_mix["gross_weight_check"] < -1e-9).any() or (asset_mix["gross_weight_check"] > 1.10).any():
        raise SystemExit("gross_weight_check out of range in asset mix")

    if not set(changes["change_type"].dropna().astype(str)).issubset({"new", "exit", "increase", "decrease"}):
        raise SystemExit("Unexpected change_type in analytics_model_change_log")

    if (weekly["nav"] <= 0).any():
        raise SystemExit("Invalid nav in weekly snapshot")

    required_quality_cols = {"relative_strength_vs_benchmark_12w", "relative_strength_vs_benchmark_52w", "turnover_1w", "turnover_avg_4w", "top5_weight", "holdings_hhi"}
    missing_quality_cols = sorted(required_quality_cols - set(quality.columns))
    if missing_quality_cols:
        raise SystemExit("Missing quality columns: " + ", ".join(missing_quality_cols))

    print(f"validated_tables={len(REQUIRED_TABLES)}")
    print(f"validated_models={len(overview_models)}")
    print(f"run_overview_rows={len(overview)}")
    print(f"weekly_snapshot_rows={len(weekly)}")
    print(f"asset_mix_rows={len(asset_mix)}")
    print(f"asset_detail_rows={len(asset_detail)}")
    print(f"change_log_rows={len(changes)}")
    print(f"change_activity_rows={len(change_activity)}")
    print(f"holding_lifecycle_rows={len(lifecycle)}")
    print(f"change_impact_rows={len(change_impact)}")
    if not set(quality_checks["status"].dropna().astype(str)).issubset({"ok", "warn", "error"}):
        raise SystemExit("Unexpected status in analytics_data_quality_checks")

    print(f"quality_rows={len(quality)}")
    print(f"quality_check_rows={len(quality_checks)}")
    print("validated_service_analytics=ok")


if __name__ == "__main__":
    main()
