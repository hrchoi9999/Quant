from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("prepare_execute_pilot_readiness", HARNESS_DIR / "prepare_execute_pilot_readiness.py")
assert SPEC is not None
READINESS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(READINESS)


def test_outside_workspace_detects_external_root() -> None:
    assert READINESS._outside_workspace("D:/QuantMarket")
    assert not READINESS._outside_workspace("D:/Quant")


def test_weekday_candidates_follow_scoped_operational_commands() -> None:
    summary = READINESS._cycle_summary("weekday")

    stage_ids = {row["stage_id"] for row in summary["stage_rows"]}
    assert "WD01_QUANT_FRONT" in stage_ids
    assert set(summary["deferred_stages"]) == {
        "WD02_MARKET_COLLECT",
        "WD03_MARKET_ANALYSIS",
        "WD04_QUANT_REAR",
        "WD05_PORTFOLIO_ANALYSIS",
        "WD06_PRE_GCS_PUBLISH",
    }


def test_weekend_candidates_follow_scoped_operational_commands() -> None:
    summary = READINESS._cycle_summary("weekend")

    stage_ids = {row["stage_id"] for row in summary["stage_rows"]}
    assert stage_ids == {"WE01_QUANT_WEEKEND_PIPELINE"}
    assert set(summary["deferred_stages"]) == {"WE01_QUANT_WEEKEND_PIPELINE"}
    assert {row["thread"] for row in summary["stage_rows"]} == {"Quant"}
