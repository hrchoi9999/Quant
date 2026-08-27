from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("classify_harness_run_namespace", HARNESS_DIR / "classify_harness_run_namespace.py")
assert SPEC is not None
NAMESPACE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(NAMESPACE)

FILTER_SPEC = importlib.util.spec_from_file_location("filter_real_operational_runs", HARNESS_DIR / "filter_real_operational_runs.py")
assert FILTER_SPEC is not None
FILTER = importlib.util.module_from_spec(FILTER_SPEC)
assert FILTER_SPEC.loader is not None
FILTER_SPEC.loader.exec_module(FILTER)


POLICY = {
    "safe_run_indicators": {"run_id_contains": ["safe"], "command_contains": ["safe_echo.py"]},
    "test_indicators": {"run_id_contains": ["fixture", "dummy", "test", "block", "blocked"]},
    "dry_run_indicators": {"run_id_contains": ["dryrun", "dry_run"], "mode_values": ["dry-run", "plan"]},
    "real_indicators": {
        "execution_type": ["manual_operational_cycle_pilot", "approval_gated_operational_cycle_pilot"],
        "mode_values": ["execute"],
        "approval_based_execution": True,
    },
}


def test_classifies_dryrun_before_real() -> None:
    namespace, reasons = NAMESPACE.classify_metadata(
        {
            "run_id": "20260627_approval_cycle_dryrun",
            "mode": "dry-run",
            "execution_type": "manual_operational_cycle_pilot",
            "approval_based_execution": True,
            "commands": [],
        },
        POLICY,
    )

    assert namespace == "dry_run"
    assert reasons


def test_classifies_approval_gated_real_execute() -> None:
    namespace, reasons = NAMESPACE.classify_metadata(
        {
            "run_id": "20260627_weekday_execute",
            "mode": "execute",
            "execution_type": "approval_gated_operational_cycle_pilot",
            "approval_based_execution": True,
            "approval_gate_status": "passed",
            "commands": [],
        },
        POLICY,
    )

    assert namespace == "approval_gated_operational"
    assert "approval_based_execution:true" in reasons


def test_classifies_safe_echo_as_safe_run() -> None:
    namespace, _ = NAMESPACE.classify_metadata(
        {
            "run_id": "20260627_weekday",
            "mode": "execute",
            "execution_type": "manual_operational_cycle_pilot",
            "approval_based_execution": True,
            "commands": ["python scripts/harness/safe_echo.py --stage WD01"],
        },
        POLICY,
    )

    assert namespace == "safe_run"


def test_superseded_real_run_is_excluded() -> None:
    included, reason = FILTER._real_filter_decision(
        {
            "run_id": "failed_run",
            "namespace": "approval_gated_operational",
            "mode": "execute",
            "approval_based_execution": True,
        },
        {"failed_run": {"superseded_by": "retry_run", "reason": "retry completed"}},
    )

    assert not included
    assert reason == "excluded_superseded_by_retry:retry_run"
