from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

RUN_STAGE_SPEC = importlib.util.spec_from_file_location("run_stage", HARNESS_DIR / "run_stage.py")
assert RUN_STAGE_SPEC is not None
RUN_STAGE = importlib.util.module_from_spec(RUN_STAGE_SPEC)
assert RUN_STAGE_SPEC.loader is not None
RUN_STAGE_SPEC.loader.exec_module(RUN_STAGE)


def test_execute_blocks_high_risk_command() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message SHOULD_NOT_RUN",
        "safe_run": True,
        "risk_level": "high",
    }

    assert RUN_STAGE.execution_block_reason(config) == "risk_level is blocked: high"


def test_execute_blocks_unsafe_command() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message SHOULD_NOT_RUN",
        "safe_run": False,
        "risk_level": "low",
    }

    assert RUN_STAGE.execution_block_reason(config) == "safe_run is false"


def test_execute_allows_low_risk_safe_command() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message OK",
        "safe_run": True,
        "risk_level": "low",
    }

    assert RUN_STAGE.execution_block_reason(config) is None


def test_execute_blocks_unapproved_operational_status() -> None:
    config = {
        "command": "python scripts/harness/safe_echo.py --message OK",
        "safe_run": True,
        "risk_level": "low",
        "command_status": "preflight_passed",
    }

    assert RUN_STAGE.execution_block_reason(config) == "command_status is not approved for harness execute: preflight_passed"


def test_execute_blocks_policy_pattern() -> None:
    config = {
        "command": "python scripts/publish_public_current_to_gcs.py",
        "safe_run": True,
        "risk_level": "low",
        "command_status": "approved_for_harness_execute",
    }

    assert RUN_STAGE.execution_block_reason(config) == "blocked pattern matched: publish_public_current_to_gcs"


def test_execute_blocks_manual_prompt_only_stage() -> None:
    config = {
        "command": None,
        "safe_run": False,
        "risk_level": "medium",
        "command_status": "manual_prompt_only",
    }

    assert RUN_STAGE.execution_block_reason(config) == "stage is manual_prompt_only"


def test_operational_commands_follow_prompt_scope() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "harness" / "stage_commands_operational.yaml"
    stages = yaml.safe_load(path.read_text(encoding="utf-8"))["stages"]

    assert stages["WD02_MARKET_COLLECT"]["thread"] == "QuantMarketData"
    assert "WE02_MARKET_COLLECT" not in stages
    assert "WE03_MARKET_ANALYSIS" not in stages
    assert "WE05_PORTFOLIO_ANALYSIS" not in stages

    prompt_only = [
        "WD02_MARKET_COLLECT",
        "WD03_MARKET_ANALYSIS",
        "WD04_QUANT_REAR",
        "WD05_PORTFOLIO_ANALYSIS",
        "WD06_PRE_GCS_PUBLISH",
        "WE01_QUANT_WEEKEND_PIPELINE",
    ]
    for stage_id in prompt_only:
        assert stages[stage_id]["command"] is None
        assert stages[stage_id]["command_status"] == "manual_prompt_only"

    all_commands = "\n".join(str(row.get("command") or "") for row in stages.values())
    assert "research_full" not in all_commands
    assert "run_market_analysis_pipeline.py" not in all_commands
    assert "run_daily_investment_portfolio.ps1" not in all_commands
