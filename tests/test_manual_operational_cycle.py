from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("validate_cycle_approval", HARNESS_DIR / "validate_cycle_approval.py")
assert SPEC is not None
CYCLE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CYCLE)


def test_single_stage_scope_is_not_cycle_scoped() -> None:
    approval = {
        "approval_status": "approved_for_manual_execute",
        "approval_scope": "single_stage_manual_pilot",
    }

    assert not CYCLE.approval_is_cycle_scoped(approval)


def test_cycle_scope_is_accepted() -> None:
    approval = {
        "approval_status": "approved_for_manual_execute",
        "approval_scope": "manual_operational_cycle_pilot",
    }

    assert CYCLE.approval_is_cycle_scoped(approval)


def test_partial_approval_when_required_stage_missing() -> None:
    rows = [
        {"stage_id": "WD02_MARKET_COLLECT", "required": True, "validation_status": "approved"},
        {"stage_id": "WD03_MARKET_ANALYSIS", "required": True, "validation_status": "not_approved"},
        {"stage_id": "WD05_PORTFOLIO_ANALYSIS", "required": True, "validation_status": "approved"},
    ]

    assert CYCLE.overall_status("weekday", rows) == "partial_approval_only"


def test_blocked_when_required_high_risk() -> None:
    rows = [
        {"stage_id": "WD02_MARKET_COLLECT", "required": True, "validation_status": "approved"},
        {"stage_id": "WD03_MARKET_ANALYSIS", "required": True, "validation_status": "approved"},
        {"stage_id": "WD05_PORTFOLIO_ANALYSIS", "required": True, "validation_status": "blocked"},
    ]

    assert CYCLE.overall_status("weekday", rows) == "blocked"


def test_stage_validation_blocks_blocked_pattern(tmp_path: Path) -> None:
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        """
{
  "approvals": [
    {
      "stage_id": "WD02_MARKET_COLLECT",
      "approval_status": "approved_for_manual_execute",
      "approval_scope": "manual_operational_cycle_pilot"
    }
  ]
}
""",
        encoding="utf-8",
    )
    row = {
        "order": 1,
        "stage_id": "WD02_MARKET_COLLECT",
        "thread": "QuantMarket",
        "action": "blocked pattern test",
        "command": "python D:/Quant/scripts/harness/safe_echo.py --message buy",
        "working_dir": "D:/Quant",
        "risk_level": "medium",
        "command_status": "candidate_found",
        "close_stage": False,
    }

    result = CYCLE.validate_stage_for_cycle("unit", "weekday", row, approval_file)

    assert result["validation_status"] == "blocked"
    assert "blocked_pattern:buy" in result["issues"]
