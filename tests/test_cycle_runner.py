from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("run_update_cycle", HARNESS_DIR / "run_update_cycle.py")
assert SPEC is not None
RUN_UPDATE_CYCLE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN_UPDATE_CYCLE)

SUMMARY_SPEC = importlib.util.spec_from_file_location("collect_cycle_summary", HARNESS_DIR / "collect_cycle_summary.py")
assert SUMMARY_SPEC is not None
SUMMARY = importlib.util.module_from_spec(SUMMARY_SPEC)
assert SUMMARY_SPEC.loader is not None
SUMMARY_SPEC.loader.exec_module(SUMMARY)


def test_mark_skipped_after_stop_only_marks_later_pending_stages() -> None:
    state = {
        "stages": [
            {"stage_id": "WD01_QUANT_FRONT", "status": "completed"},
            {"stage_id": "WD02_MARKET_COLLECT", "status": "blocked"},
            {"stage_id": "WD03_MARKET_ANALYSIS", "status": "pending"},
            {"stage_id": "WD04_QUANT_REAR", "status": "pending"},
        ]
    }

    RUN_UPDATE_CYCLE._mark_skipped_after_stop(state, "WD02_MARKET_COLLECT")

    assert state["stages"][0]["status"] == "completed"
    assert state["stages"][1]["status"] == "blocked"
    assert state["stages"][2]["status"] == "skipped"
    assert state["stages"][3]["status"] == "skipped"


def test_stage_can_continue_respects_mode() -> None:
    assert RUN_UPDATE_CYCLE._stage_can_continue("dry-run", "dry_run_completed")
    assert not RUN_UPDATE_CYCLE._stage_can_continue("dry-run", "completed")
    assert RUN_UPDATE_CYCLE._stage_can_continue("execute-safe", "completed")
    assert not RUN_UPDATE_CYCLE._stage_can_continue("execute-safe", "dry_run_completed")


def test_final_summary_includes_elapsed_time() -> None:
    state = {
        "status": "completed",
        "started_at": "2026-06-28T10:00:00",
        "completed_at": "2026-06-28T10:02:03",
        "stages": [
            {
                "order": 1,
                "stage_id": "WE01_QUANT_WEEKEND_PIPELINE",
                "status": "dry_run_completed",
                "started_at": "2026-06-28T10:00:00",
                "completed_at": "2026-06-28T10:02:00",
            },
            {
                "order": 2,
                "stage_id": "WE06_HARNESS_CLOSE",
                "status": "completed",
                "started_at": "2026-06-28T10:02:00",
                "completed_at": "2026-06-28T10:02:03",
            },
        ],
    }

    summary = SUMMARY.render_final_summary(state)

    assert "- total_elapsed: 2m 03s" in summary
    assert "- WE01_QUANT_WEEKEND_PIPELINE: 2m 00s" in summary
    assert "- WE06_HARNESS_CLOSE: 3s" in summary
