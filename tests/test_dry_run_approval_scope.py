from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

BUILD_SPEC = importlib.util.spec_from_file_location("build_approval_request", HARNESS_DIR / "build_approval_request.py")
assert BUILD_SPEC is not None
BUILD = importlib.util.module_from_spec(BUILD_SPEC)
assert BUILD_SPEC.loader is not None
BUILD_SPEC.loader.exec_module(BUILD)

GATE_SPEC = importlib.util.spec_from_file_location("validate_approval_gate", HARNESS_DIR / "validate_approval_gate.py")
assert GATE_SPEC is not None
GATE = importlib.util.module_from_spec(GATE_SPEC)
assert GATE_SPEC.loader is not None
GATE_SPEC.loader.exec_module(GATE)


def test_dry_run_scope_does_not_require_real_readiness() -> None:
    path, required = BUILD._resolve_readiness_file(BUILD.DEFAULT_READINESS, "manual_operational_cycle_dry_run")

    assert path == BUILD.DEFAULT_READINESS
    assert required is False
    assert "manual_operational_cycle_dry_run" in BUILD.DRY_RUN_APPROVAL_SCOPES


def test_dry_run_scope_matches_dry_run_execution_type() -> None:
    assert GATE._scope_matches("manual_operational_cycle_dry_run", "manual_operational_cycle_dry_run")
    assert not GATE._scope_matches("manual_operational_cycle_dry_run", "manual_operational_cycle_pilot")
