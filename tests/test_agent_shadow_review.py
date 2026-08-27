from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("agent_shadow_review_cycle", HARNESS_DIR / "agent_shadow_review_cycle.py")
assert SPEC is not None
SHADOW = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SHADOW)


def test_scan_text_is_case_insensitive() -> None:
    patterns = {"critical": ["permission denied"], "error": ["Traceback"], "warning": ["missing"]}

    issues = SHADOW._scan_text("S1", "stderr.log", "Permission Denied\ntraceback\nMISSING file", patterns)

    assert {issue["severity"] for issue in issues} == {"critical", "error", "warning"}


def test_required_skipped_is_error() -> None:
    assert SHADOW._status_severity("skipped", required=True) == "error"


def test_optional_skipped_deferred_is_info() -> None:
    assert SHADOW._status_severity("skipped_deferred", required=False) == "info"


def test_stage_recommendation_for_blocked() -> None:
    assert SHADOW._recommend_for_stage("blocked", "error", False) == "resolve_blocked_stage"
