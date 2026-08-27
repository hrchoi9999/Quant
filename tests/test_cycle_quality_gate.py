from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("validate_cycle_outputs", HARNESS_DIR / "validate_cycle_outputs.py")
assert SPEC is not None
QUALITY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(QUALITY)


def test_render_quality_gate_lists_no_issues() -> None:
    result = {
        "run_id": "r1",
        "status": "passed",
        "cycle_status": "completed",
        "mode": "dry-run",
        "issues": [],
        "checks": [],
        "summary": {"issue_count": 0},
    }

    text = QUALITY.render_quality_gate(result)

    assert "- none" in text
    assert "status: passed" in text


def test_render_quality_gate_lists_issues() -> None:
    result = {
        "run_id": "r1",
        "status": "failed",
        "cycle_status": "blocked",
        "mode": "execute-safe",
        "issues": ["stage:blocked"],
        "checks": [{"check": "required_run_file", "target": "x", "ok": False}],
        "summary": {"issue_count": 1},
    }

    text = QUALITY.render_quality_gate(result)

    assert "stage:blocked" in text
    assert "ok=False" in text
