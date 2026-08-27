from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("run_update_cycle_simple", HARNESS_DIR / "run_update_cycle_simple.py")
assert SPEC is not None
SIMPLE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SIMPLE)


def _args(**overrides):
    base = {
        "cycle": "weekday",
        "asof": "2026-06-27",
        "run_id": "simple_test",
        "plan": False,
        "dry_run": True,
        "execute": False,
        "approval_id": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_target_cycles_all_is_forbidden() -> None:
    try:
        SIMPLE._target_cycles("all")
    except SystemExit as exc:
        assert str(exc) == SIMPLE.FORBIDDEN_COMBINED_CYCLE_REASON
    else:
        raise AssertionError("combined weekday/weekend cycle must be forbidden")


def test_execute_requires_approval_id() -> None:
    args = _args(dry_run=False, execute=True)

    assert SIMPLE._execute_blockers(args, ["weekday"]) != []


def test_first_real_weekday_approval_bypasses_insufficient_data(monkeypatch) -> None:
    args = _args(dry_run=False, execute=True, approval_id="APPROVAL_X")
    request = {
        "approval_scope": "first_real_weekday_pilot",
        "target_cycle_type": "weekday",
        "target_stage_ids": ["WD02_MARKET_COLLECT", "WD03_MARKET_ANALYSIS", "WD05_PORTFOLIO_ANALYSIS"],
        "real_readiness_exception_approved": True,
        "external_root_execution_approved": True,
        "single_run_only": True,
        "weekday_weekend_combined_run_forbidden": True,
        "auto_repeat_allowed": False,
    }
    monkeypatch.setattr(SIMPLE, "_readiness_status", lambda: "insufficient_data")
    monkeypatch.setattr(SIMPLE, "_approval_request", lambda approval_id: request)

    assert SIMPLE._execute_blockers(args, ["weekday"]) == []


def test_weekday_specific_approval_takes_precedence() -> None:
    args = _args(approval_id="A")

    assert SIMPLE._approval_id_for(args, "weekday") == "A"


def test_dry_run_with_approval_uses_manual_cycle(monkeypatch) -> None:
    calls = {}

    def fake_run_manual_cycle(run_id, cycle, approval_file, *, execute, approval_id, asof):
        calls.update(
            {
                "run_id": run_id,
                "cycle": cycle,
                "approval_file": approval_file,
                "execute": execute,
                "approval_id": approval_id,
                "asof": asof,
            }
        )
        return {"status": "approved_for_manual_cycle", "cycle_state": "state.json"}

    monkeypatch.setattr(SIMPLE, "run_manual_cycle", fake_run_manual_cycle)
    args = _args(approval_id="APPROVAL_X")

    result = SIMPLE._run_one_cycle(args, "weekday", "run1", "dry-run")

    assert result["mode"] == "approval-gated-dry-run"
    assert calls["execute"] is False
    assert calls["approval_id"] == "APPROVAL_X"
