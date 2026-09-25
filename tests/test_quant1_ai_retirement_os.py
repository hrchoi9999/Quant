"""The retired Quant 1.0 AI paths cannot resume through OS entrypoints."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts import build_admin_new_entry_tracker as tracker
from scripts import build_c_series_v01 as c_series
from scripts import publish_public_current_to_gcs as publisher
from src.analytics import service_analytics_builder as analytics
from src.analytics import service_analytics_bundle_common as analytics_bundle
from src.quant_service import run_daily_quant_pipeline as daily

ROOT = Path(__file__).resolve().parents[1]


def test_research_full_cannot_schedule_retired_models_or_cleanup() -> None:
    commands = daily.build_commands(
        asof="2026-09-23", python_exe=sys.executable, core_db="core.db", detail_db="detail.db",
        core2_tag="test", include_etf=True, etf_start="2026-09-23",
        include_service_analytics=True, include_tseries_shadow=True,
        include_iseries_shadow=True, include_ai_overlay=True, include_ai_research=True,
        include_remote_current_publish=False, include_generated_cleanup=True,
        full_regime_rebuild=False, full_validation=False, pipeline_mode="research_full",
    )
    assert commands[4] == []  # T refresh
    assert commands[10] == []  # AI training, inference, and research
    assert commands[13]  # independent opt-in service analytics remains available
    assert all("tseries" not in " ".join(cmd).lower() and "ai_overlay" not in " ".join(cmd).lower()
               for cmd in commands[13])
    assert commands[14] == []  # generated-history cleanup
    assert "--exclude-tseries" in commands[11][0]
    assert any("run_backtest_s4_risk_on_allocation.py" in " ".join(cmd) for cmd in commands[2])


def test_service_analytics_opt_in_and_retired_model_filter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run_rows = pd.DataFrame([
        {"model_code": code, "published_at": None, "asof_date": "2026-09-23",
         "start_date": "2026-09-01", "end_date": "2026-09-23"}
        for code in ("S2", "T-STOCK-V01", "T-ETF-V01", "S6")
    ])
    monkeypatch.setattr(analytics, "_current_runs", lambda _db: run_rows.copy())
    result = analytics.build_model_run_overview(analytics.SourceDbs(quant_service=tmp_path / "missing.db"))
    assert result["model_code"].tolist() == ["S2"]


def test_old_analytics_db_cannot_feed_direct_preview_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "old_service_analytics.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE analytics_model_run_overview (model_code TEXT)")
        con.executemany("INSERT INTO analytics_model_run_overview VALUES (?)", [("S2",), ("T-STOCK-V01",)])
    monkeypatch.setattr(analytics_bundle, "ANALYTICS_DB", db)
    with pytest.raises(ValueError, match="T-STOCK-V01"):
        analytics_bundle.build_common_meta("2026-09-23", "p1", ["today_model_info"])


def test_c_and_admin_builders_do_not_read_retired_t_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "absent_tseries.db"
    monkeypatch.setattr(c_series, "TS_DB", missing)
    monkeypatch.setattr(tracker, "TSERIES_DB", missing)
    assert c_series._latest_t_candidates("2026-09-23").empty
    assert tracker.build_tseries_weekly_rank_rows("2026-09-23") == []
    assert tracker.build_tseries_rows("2026-09-23") == []
    assert tracker.build_tseries_model_performance_summary("2026-09-23", []) == []
    assert not missing.exists()


def test_publisher_plan_omits_retired_current_objects() -> None:
    args = SimpleNamespace(admin_strategy_research_observation_only=False)
    for flag in (
        "skip_user_current", "skip_user_history", "skip_tseries_current", "skip_tseries_history",
        "skip_admin_current", "skip_admin_history", "skip_trading_sign_current",
    ):
        setattr(args, flag, False)
    selected = publisher.selected_legacy_objects(args)
    assert "publish_manifest.json" in selected
    assert not any("tseries_discovery" in name or "ai_learning" in name for name in selected)


@pytest.mark.parametrize("script", [
    "run_t_stock_v01_operational_refresh.py",
    "run_t_etf_v01_operational_refresh.py",
    "build_ai_overlay_v01.py",
])
def test_direct_retired_cli_rejects_before_work(script: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--asof", "2026-09-23"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode != 0
    assert "Quant 1.0 AI retired" in completed.stderr
