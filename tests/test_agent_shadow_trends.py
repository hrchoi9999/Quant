from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("analyze_shadow_review_trends", HARNESS_DIR / "analyze_shadow_review_trends.py")
assert SPEC is not None
TRENDS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TRENDS)


def test_issue_key_groups_repeated_issue() -> None:
    issue = {"severity": "warning", "stage_id": "WD02", "source": "stderr.log", "message": "missing"}

    assert TRENDS._issue_key(issue) == ("warning", "WD02", "stderr.log", "missing")


def test_stability_blocked_for_failure() -> None:
    row = {
        "critical_count": 0,
        "failed_count": 1,
        "blocked_count": 0,
        "error_count": 0,
        "artifact_missing_count": 0,
        "warning_count": 0,
        "skipped_count": 0,
    }

    assert TRENDS._stability(row, 2) == "blocked"


def test_stability_watch_for_warning() -> None:
    row = {
        "critical_count": 0,
        "failed_count": 0,
        "blocked_count": 0,
        "error_count": 0,
        "artifact_missing_count": 0,
        "warning_count": 1,
        "skipped_count": 0,
    }

    assert TRENDS._stability(row, 2) == "watch"
