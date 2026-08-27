from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("run_manual_approved_stage", HARNESS_DIR / "run_manual_approved_stage.py")
assert SPEC is not None
MANUAL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MANUAL)


def _passed_preflight(stage_id: str) -> dict[str, object]:
    return {
        "stage_id": stage_id,
        "status": "passed",
        "thread_root_match": True,
        "entrypoint_exists": True,
    }


def test_manual_validation_requires_approval() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message ok",
        "working_dir": str(Path(__file__).resolve().parents[1]),
        "risk_level": "low",
    }

    reason = MANUAL._validate_execution_allowed("WD03_MARKET_ANALYSIS", config, None)

    assert "approval" in reason


def test_manual_validation_blocks_rejected_status() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message ok",
        "working_dir": str(Path(__file__).resolve().parents[1]),
        "risk_level": "low",
    }
    approval = {"approval_status": "candidate_found", "approval_scope": "single_stage_manual_pilot"}

    reason = MANUAL._validate_execution_allowed("WD03_MARKET_ANALYSIS", config, approval)

    assert reason == "approval rejected: candidate_found"


def test_manual_validation_allows_high_risk_after_approval_and_preflight(monkeypatch) -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message ok",
        "working_dir": str(Path(__file__).resolve().parents[1]),
        "risk_level": "high",
    }
    approval = {"approval_status": "approved_for_manual_execute", "approval_scope": "single_stage_manual_pilot"}
    monkeypatch.setattr(MANUAL, "_preflight", _passed_preflight)

    reason = MANUAL._validate_execution_allowed("WD04_QUANT_REAR", config, approval)

    assert reason is None


def test_manual_validation_blocks_missing_preflight_after_approval() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message ok",
        "working_dir": str(Path(__file__).resolve().parents[1]),
        "risk_level": "high",
    }
    approval = {"approval_status": "approved_for_manual_execute", "approval_scope": "single_stage_manual_pilot"}

    reason = MANUAL._validate_execution_allowed("WD04_QUANT_REAR", config, approval)

    assert reason == "preflight not passed: missing"


def test_manual_validation_blocks_critical_risk_after_approval() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message ok",
        "working_dir": str(Path(__file__).resolve().parents[1]),
        "risk_level": "critical",
    }
    approval = {"approval_status": "approved_for_manual_execute", "approval_scope": "single_stage_manual_pilot"}

    reason = MANUAL._validate_execution_allowed("WD04_QUANT_REAR", config, approval)

    assert reason == "risk_level is not allowed for manual pilot: critical"


def test_manual_validation_blocks_blocked_pattern() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message buy",
        "working_dir": str(Path(__file__).resolve().parents[1]),
        "risk_level": "low",
    }
    approval = {"approval_status": "approved_for_manual_execute", "approval_scope": "single_stage_manual_pilot"}

    reason = MANUAL._validate_execution_allowed("WD03_MARKET_ANALYSIS", config, approval)

    assert reason == "blocked pattern matched: buy"
