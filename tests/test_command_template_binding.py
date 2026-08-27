from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

COMMON_SPEC = importlib.util.spec_from_file_location("harness_common", HARNESS_DIR / "harness_common.py")
assert COMMON_SPEC is not None
COMMON = importlib.util.module_from_spec(COMMON_SPEC)
assert COMMON_SPEC.loader is not None
COMMON_SPEC.loader.exec_module(COMMON)

RUN_STAGE_SPEC = importlib.util.spec_from_file_location("run_stage", HARNESS_DIR / "run_stage.py")
assert RUN_STAGE_SPEC is not None
RUN_STAGE = importlib.util.module_from_spec(RUN_STAGE_SPEC)
assert RUN_STAGE_SPEC.loader is not None
RUN_STAGE_SPEC.loader.exec_module(RUN_STAGE)


def test_bind_command_template_reports_unresolved_asof() -> None:
    result = COMMON.bind_command_template("python run.py --asof {asof}", {})

    assert result["resolved"] is False
    assert result["unresolved_variables"] == ["asof"]


def test_bind_command_template_replaces_asof() -> None:
    result = COMMON.bind_command_template("python run.py --asof {asof}", {"asof": "2026-06-27"})

    assert result["resolved"] is True
    assert result["command"] == "python run.py --asof 2026-06-27"


def test_run_stage_blocks_unresolved_operational_template() -> None:
    result = RUN_STAGE.run_stage(
        "test_asof_missing",
        "WD01_QUANT_FRONT",
        execute=False,
        config_path=COMMON.OPERATIONAL_COMMANDS_PATH,
    )

    assert result["status"] == "blocked"
    assert result["unresolved_command_variables"] == ["asof"]


def test_run_stage_binds_operational_template_for_dry_run() -> None:
    result = RUN_STAGE.run_stage(
        "test_asof_bound",
        "WD01_QUANT_FRONT",
        execute=False,
        config_path=COMMON.OPERATIONAL_COMMANDS_PATH,
        asof="2026-06-27",
    )

    assert result["status"] == "dry_run_completed"
    assert "--asof 2026-06-27" in result["command"]
