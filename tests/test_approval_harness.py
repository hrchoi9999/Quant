from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("validate_approval_gate", HARNESS_DIR / "validate_approval_gate.py")
assert SPEC is not None
GATE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GATE)


def test_gate_status_passed() -> None:
    checks = {
        "request_exists": True,
        "decision_exists": True,
        "decision_approved": True,
        "not_expired": True,
        "scope_match": True,
        "target_run_match": True,
        "risk_allowed": True,
        "blocked_pattern": False,
        "auto_execute_allowed": False,
        "publish_allowed": False,
        "db_sync_allowed": False,
        "trading_sign_allowed": False,
        "trading_order_allowed": False,
    }
    assert GATE._gate_status(checks) == "passed"


def test_gate_status_blocks_pattern() -> None:
    checks = {
        "request_exists": True,
        "decision_exists": True,
        "decision_approved": True,
        "not_expired": True,
        "scope_match": True,
        "target_run_match": True,
        "risk_allowed": True,
        "blocked_pattern": True,
        "auto_execute_allowed": True,
        "publish_allowed": True,
        "db_sync_allowed": True,
        "trading_sign_allowed": True,
        "trading_order_allowed": True,
    }

    assert GATE._gate_status(checks) == "blocked"


def test_scope_match_for_stage_execution() -> None:
    assert GATE._scope_matches("single_stage_manual_pilot", "manual_operational_stage_pilot")
    assert not GATE._scope_matches("manual_operational_cycle_pilot", "manual_operational_stage_pilot")


def test_first_real_scope_matches_cycle_execution() -> None:
    assert GATE._scope_matches("first_real_weekday_pilot", "manual_operational_cycle_pilot")


def test_first_real_controls_require_exact_weekday_scope() -> None:
    request = {
        "approval_scope": "first_real_weekday_pilot",
        "target_cycle_type": "weekday",
        "target_stage_ids": ["WD02_MARKET_COLLECT", "WD03_MARKET_ANALYSIS", "WD05_PORTFOLIO_ANALYSIS"],
        "first_real_pilot": True,
        "real_readiness_exception_approved": True,
        "readiness_status": "insufficient_data",
        "external_root_execution_approved": True,
        "single_run_only": True,
        "weekday_weekend_combined_run_forbidden": True,
        "auto_repeat_allowed": False,
    }
    decision = {
        "execution_constraints": {
            "first_real_weekday_pilot_allowed": True,
            "single_run_only": True,
            "auto_repeat_allowed": False,
        }
    }

    assert GATE._first_real_controls_pass(request, decision, "weekday")

    request["target_stage_ids"] = ["WD02_MARKET_COLLECT", "WD03_MARKET_ANALYSIS", "WD04_QUANT_REAR"]
    assert not GATE._first_real_controls_pass(request, decision, "weekday")
