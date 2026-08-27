from __future__ import annotations

import importlib
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_pipeline_harness.py"
SPEC = importlib.util.spec_from_file_location("update_pipeline_harness", SCRIPT)
assert SPEC is not None
HARNESS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(HARNESS)


def test_weekday_state_advances_to_quantmarket() -> None:
    state = HARNESS.build_initial_state(
        workflow="weekday",
        asof="2026-06-26",
        batch_type="final_operational_publish",
    )

    assert state["status"] == "in_progress"
    assert state["steps"][0]["thread"] == "Quant"
    assert HARNESS.current_step(state)["id"] == "quant_data_refresh"

    advanced = HARNESS.complete_current_step(state, ["timing.json"], ["ok"])

    assert advanced["status"] == "in_progress"
    assert advanced["steps"][0]["status"] == "completed"
    assert HARNESS.current_step(advanced)["id"] == "quantmarket_handoff"
    assert HARNESS.current_step(advanced)["thread"] == "QuantMarket"


def test_weekend_prompt_contains_research_full_and_asof() -> None:
    state = HARNESS.build_initial_state(
        workflow="weekend",
        asof="2026-06-26",
        batch_type="research_full",
        include_ai_research=True,
    )

    prompt = HARNESS.render_prompt(state)

    assert len(state["steps"]) == 1
    assert state["threads"] == ["Quant"]
    assert HARNESS.current_step(state)["id"] == "quant_weekend_pipeline"
    assert "대상 thread: Quant" in prompt
    assert "research_full" in prompt
    assert "--include-ai-research" in prompt
    assert "2026-06-26" in prompt
    assert "QuantMarket" not in prompt
    assert "QuantAnalysis" not in prompt


def test_block_current_step_sets_state_blocked() -> None:
    state = HARNESS.build_initial_state(
        workflow="weekday",
        asof="2026-06-26",
        batch_type="final_operational_publish",
    )

    blocked = HARNESS.block_current_step(state, ["validation failed"])

    assert blocked["status"] == "blocked"
    assert HARNESS.current_step(blocked)["status"] == "blocked"
    assert HARNESS.current_step(blocked)["notes"] == ["validation failed"]
