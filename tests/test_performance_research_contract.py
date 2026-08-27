from __future__ import annotations

import json
from pathlib import Path

from scripts.harness.harness_common import read_yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "harness" / "performance_research_registry.yaml"


def _registry() -> dict:
    return read_yaml(REGISTRY)["performance_research"]


def test_performance_research_registry_allows_one_active_campaign_per_owner() -> None:
    registry = _registry()
    active_states = {"frozen_ready_to_dispatch", "in_progress", "awaiting_evidence_gate"}
    counts: dict[str, int] = {}
    for campaign in registry["campaigns"]:
        if campaign["status"] in active_states:
            owner = campaign["owner"]
            counts[owner] = counts.get(owner, 0) + 1

    assert registry["max_active_campaigns_per_owner"] == 1
    assert all(count <= 1 for count in counts.values())


def test_active_campaign_contract_is_frozen_and_safe() -> None:
    registry = _registry()
    campaign = registry["campaigns"][0]
    contract_path = ROOT / campaign["contract_file"]
    contract = read_yaml(contract_path)["performance_research_contract"]

    assert contract["campaign_id"] == campaign["campaign_id"]
    assert contract["frozen_comparison"]["baseline"] != contract["frozen_comparison"]["candidate"]
    assert contract["frozen_comparison"]["candidate_rule_change_allowed"] is False
    assert contract["frozen_comparison"]["candidate_tuning_allowed"] is False
    assert contract["frozen_comparison"]["additional_candidate_search_allowed"] is False
    assert contract["evidence_gate"]["independent_holdout_required_for_approval_eligibility"] is True
    assert contract["evidence_gate"]["approval_eligible_state_allowed"] is False
    assert campaign["policy_change_allowed"] is False
    assert campaign["public_publish_allowed"] is False


def test_contract_has_decision_ready_evidence_requirements() -> None:
    registry = _registry()
    campaign = registry["campaigns"][0]
    contract_path = ROOT / campaign["contract_file"]
    contract = read_yaml(contract_path)["performance_research_contract"]

    required = set(contract["required_report_fields"])
    assert {
        "selection_chronology",
        "untouched_holdout_inventory",
        "baseline_vs_candidate",
        "paired_uncertainty",
        "regime_robustness",
        "cost_sensitivity",
        "gain_concentration",
        "guardrail_results",
        "evidence_state",
        "recommended_next_action",
    }.issubset(required)
    assert contract["evidence_gate"]["minimum_monthly_priced_periods"] >= 24
    assert set(contract["frozen_comparison"]["cost_sensitivity_bps_one_way"]) == {20, 30}


def test_completed_campaign_has_a_non_operational_evidence_gate() -> None:
    registry = _registry()
    campaign = registry["campaigns"][0]
    gate = json.loads((ROOT / campaign["evidence_gate_file"]).read_text(encoding="utf-8"))

    assert campaign["status"] == "completed_insufficient_evidence"
    assert campaign["final_decision"] == "insufficient_evidence"
    assert gate["decision"] == "insufficient_evidence"
    assert gate["gates"]["independent_holdout"] == "fail"
    assert gate["gates"]["paired_ci_excludes_zero"] == "fail"
    assert gate["policy_change_allowed"] is False
    assert gate["public_publish_allowed"] is False


def test_relative_gate_campaign_is_frozen_shadow_only() -> None:
    registry = _registry()
    campaign = next(
        item
        for item in registry["campaigns"]
        if item["campaign_id"] == "PR_20260710_QUANTANALYSIS_RELATIVE_GATE_01"
    )
    contract_path = ROOT / campaign["contract_file"]
    contract = read_yaml(contract_path)["performance_research_contract"]
    candidate = contract["frozen_candidate"]

    assert campaign["owner"] == "QuantAnalysis"
    assert campaign["policy_change_allowed"] is False
    assert campaign["public_publish_allowed"] is False
    assert campaign["automatic_execution_allowed"] is False
    assert candidate["score_adjustments"] == {
        "rel5d_lt_0": -12,
        "rel5d_missing": -3,
        "rel5d_0_to_lt_2": 1,
        "rel5d_2_to_15": 5,
        "rel5d_gt_15_to_25": 1,
        "rel5d_gt_25": -4,
    }
    assert candidate["rule_change_allowed"] is False
    assert candidate["additional_candidate_search_allowed"] is False
    assert contract["timing_and_cost_contract"]["entry"].startswith("next trading day open")
    assert contract["initial_campaign_gate"]["performance_decision_allowed_now"] is False
    assert contract["minimum_evidence_gate"]["unique_new_entry_dates"] == 60


def test_relative_gate_shadow_initialization_has_non_operational_evidence() -> None:
    registry = _registry()
    campaign = next(
        item
        for item in registry["campaigns"]
        if item["campaign_id"] == "PR_20260710_QUANTANALYSIS_RELATIVE_GATE_01"
    )
    gate = json.loads((ROOT / campaign["evidence_gate_file"]).read_text(encoding="utf-8"))

    assert campaign["status"] == "completed_shadow_initialized_waiting_oos"
    assert campaign["final_decision"] == "shadow_initialized_waiting_oos"
    assert gate["final_decision"] == "shadow_initialized_waiting_oos"
    assert gate["performance_decision_allowed"] is False
    assert gate["canonical_signal_binding"]["bound_post_freeze_objects"] == 0
    assert gate["initial_shadow_state"]["mature_paired_outcomes"] == 0
    assert gate["operating_output_mutation_check"]["unchanged"] is True
    assert gate["verification"]["owner_tests_passed"] == 19
    assert gate["minimum_evidence_gate"]["unique_new_entry_dates"] == 60


def test_s6_s5_defensive_buffer_campaign_is_role_compatible_and_frozen() -> None:
    registry = _registry()
    campaign = next(
        item
        for item in registry["campaigns"]
        if item["campaign_id"] == "PR_20260710_S6_S5_DEFENSIVE_BUFFER_01"
    )
    contract = read_yaml(ROOT / campaign["contract_file"])["performance_research_contract"]
    candidate = contract["frozen_candidate"]

    assert campaign["owner"] == "Quant Model"
    assert campaign["policy_change_allowed"] is False
    assert campaign["public_publish_allowed"] is False
    assert contract["role_contract"]["pure_s5_replacement_allowed"] is False
    assert candidate["acute_target"] == {
        "S6_DEFENSIVE_V1": 1.0,
        "S5_NEUTRAL_V1": 0.0,
    }
    assert candidate["non_acute_risk_off_target"] == {
        "S6_DEFENSIVE_V1": 0.85,
        "S5_NEUTRAL_V1": 0.15,
    }
    assert candidate["parameter_tuning_allowed"] is False
    assert candidate["additional_candidate_search_allowed"] is False
    assert contract["evidence_chronology"]["untouched_temporal_holdout_available_now"] is False
    assert contract["minimum_post_freeze_evidence_gate"]["monthly_decision_observations"] == 24
    assert contract["initial_campaign_gate"]["performance_decision_allowed_now"] is False


def test_s6_s5_defensive_buffer_evidence_is_shadow_only() -> None:
    registry = _registry()
    campaign = next(
        item
        for item in registry["campaigns"]
        if item["campaign_id"] == "PR_20260710_S6_S5_DEFENSIVE_BUFFER_01"
    )
    gate = json.loads((ROOT / campaign["evidence_gate_file"]).read_text(encoding="utf-8"))

    assert campaign["status"] == "completed_shadow_initialized_waiting_oos"
    assert campaign["final_decision"] == "shadow_initialized_waiting_oos"
    assert gate["performance_decision_allowed"] is False
    assert gate["role_contract"]["pure_s5_replacement_allowed"] is False
    assert gate["role_contract"]["role_guard_passed"] is True
    assert gate["historical_gates"]["paired_ci_excludes_zero"] == "fail"
    assert gate["historical_gates"]["untouched_holdout"] == "fail_none"
    assert gate["post_freeze_shadow_state"]["observations"] == 0
    assert gate["qa_corrections"]["decision_date_availability_no_lookahead"] is True
    assert gate["operating_output_mutation_check"]["unchanged"] is True
