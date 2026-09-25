from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    canonical_sha256,
)
from src.quant2.evaluation.classification import (
    ClassificationResult,
    ModelResearchClass,
)
from src.quant2.evaluation.costs import CostSensitivityResult
from src.quant2.evaluation.diagnostics import FailureConcentrationDiagnosticsResult
from src.quant2.evaluation.input_connector import (
    P2_REQUIRED_MODEL_CODES,
    EvaluationScopeRole,
)
from src.quant2.evaluation.pairwise import PairwiseComparisonResult
from src.quant2.evaluation.performance import (
    AggregationScope,
    EvidenceStatus,
    PerformanceSummaryResult,
)
from src.quant2.router.manifest import (
    ROUTER_CANDIDATE_CODE,
    RouterCandidateManifest,
    RouterCandidateStatus,
)

P2_GATE_POLICY_VERSION = "quant2.p2_synthetic_completion_gate.v1"


class P2GateComponent(str, Enum):
    CONTRACT_COVERAGE = "CONTRACT_COVERAGE"
    COST_EVALUATION = "COST_EVALUATION"
    PERFORMANCE_SUMMARY = "PERFORMANCE_SUMMARY"
    PAIRWISE_COMPARISON = "PAIRWISE_COMPARISON"
    RESEARCH_CLASSIFICATION = "RESEARCH_CLASSIFICATION"
    FAILURE_CONCENTRATION_DIAGNOSTICS = "FAILURE_CONCENTRATION_DIAGNOSTICS"
    ROUTER_CANDIDATE_MANIFEST = "ROUTER_CANDIDATE_MANIFEST"
    SAFETY_LOCKS = "SAFETY_LOCKS"


class P2GateCheckStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class P2SyntheticCompletionStatus(str, Enum):
    PASS = "PASS"
    INCOMPLETE = "INCOMPLETE"


class P2RealDataStatus(str, Enum):
    NOT_RUN = "NOT_RUN"


class P2PhaseStatus(str, Enum):
    SYNTHETIC_COMPLETE_REAL_DATA_BLOCKED = "SYNTHETIC_COMPLETE_REAL_DATA_BLOCKED"
    SYNTHETIC_INCOMPLETE = "SYNTHETIC_INCOMPLETE"


@dataclass(frozen=True)
class P2SyntheticGatePolicy:
    required_model_codes: tuple[str, ...] = P2_REQUIRED_MODEL_CODES
    optional_model_codes: tuple[str, ...] = ("SAI_GUARDED",)
    required_cost_bps: tuple[int, ...] = (10, 20, 30)
    required_router_code: str = ROUTER_CANDIDATE_CODE
    version: str = P2_GATE_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.required_model_codes != P2_REQUIRED_MODEL_CODES:
            raise ContractValidationError("P2 required model coverage is frozen")
        if self.optional_model_codes != ("SAI_GUARDED",):
            raise ContractValidationError("P2 optional model coverage is frozen")
        if self.required_cost_bps != (10, 20, 30):
            raise ContractValidationError("P2 cost scenarios are frozen")
        if self.required_router_code != ROUTER_CANDIDATE_CODE:
            raise ContractValidationError("P2 Router candidate identity is frozen")
        if self.version != P2_GATE_POLICY_VERSION:
            raise ContractValidationError("P2 gate policy version is frozen")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class P2GateComponentCheck:
    component: P2GateComponent
    status: P2GateCheckStatus
    source_hash: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.source_hash) != 64 or any(
            character not in "0123456789ABCDEF" for character in self.source_hash
        ):
            raise ContractValidationError("gate component source_hash must be SHA-256 hex")
        if self.status is P2GateCheckStatus.PASS and self.reason_codes:
            raise ContractValidationError("passing gate component cannot have reason codes")
        if self.status is P2GateCheckStatus.BLOCKED and not self.reason_codes:
            raise ContractValidationError("blocked gate component requires reason codes")


@dataclass(frozen=True)
class P2SyntheticCompletionReport:
    component_checks: tuple[P2GateComponentCheck, ...]
    observed_model_codes: tuple[str, ...]
    observed_cost_bps: tuple[int, ...]
    input_cost_result_hash: str
    input_performance_result_hash: str
    input_pairwise_result_hash: str
    input_classification_result_hash: str
    input_diagnostics_result_hash: str
    input_router_manifest_hash: str
    synthetic_completion_status: P2SyntheticCompletionStatus
    real_data_status: P2RealDataStatus
    phase_status: P2PhaseStatus
    synthetic_contract_complete: bool
    real_data_evaluation_complete: bool
    paired_bootstrap_complete: bool
    classification_confirmed: bool
    actual_router_manifest_frozen: bool
    p2_complete: bool
    eligible_for_p3_validation: bool
    eligible_for_shadow: bool
    operational_authorization: bool
    blocked_reason_codes: tuple[str, ...]
    policy_version: str
    policy_hash: str
    report_hash: str

    def __post_init__(self) -> None:
        if (
            self.real_data_evaluation_complete
            or self.paired_bootstrap_complete
            or self.classification_confirmed
            or self.actual_router_manifest_frozen
            or self.p2_complete
            or self.eligible_for_p3_validation
            or self.eligible_for_shadow
            or self.operational_authorization
        ):
            raise ContractValidationError("synthetic P2 gate cannot grant downstream authority")
        if self.real_data_status is not P2RealDataStatus.NOT_RUN:
            raise ContractValidationError("synthetic P2 gate must keep real data status NOT_RUN")
        expected_components = tuple(P2GateComponent)
        if tuple(item.component for item in self.component_checks) != expected_components:
            raise ContractValidationError(
                "P2 gate component checks must be complete, unique, and ordered"
            )
        expected_source_hashes = {
            P2GateComponent.CONTRACT_COVERAGE: self.input_cost_result_hash,
            P2GateComponent.COST_EVALUATION: self.input_cost_result_hash,
            P2GateComponent.PERFORMANCE_SUMMARY: self.input_performance_result_hash,
            P2GateComponent.PAIRWISE_COMPARISON: self.input_pairwise_result_hash,
            P2GateComponent.RESEARCH_CLASSIFICATION: (
                self.input_classification_result_hash
            ),
            P2GateComponent.FAILURE_CONCENTRATION_DIAGNOSTICS: (
                self.input_diagnostics_result_hash
            ),
            P2GateComponent.ROUTER_CANDIDATE_MANIFEST: self.input_router_manifest_hash,
            P2GateComponent.SAFETY_LOCKS: self.input_router_manifest_hash,
        }
        if any(
            item.source_hash != expected_source_hashes[item.component]
            for item in self.component_checks
        ):
            raise ContractValidationError("P2 gate component source hash binding is invalid")
        expected_complete = all(
            item.status is P2GateCheckStatus.PASS for item in self.component_checks
        )
        if self.synthetic_contract_complete is not expected_complete:
            raise ContractValidationError("synthetic completion conflicts with component checks")
        expected_status = (
            P2SyntheticCompletionStatus.PASS
            if expected_complete
            else P2SyntheticCompletionStatus.INCOMPLETE
        )
        if self.synthetic_completion_status is not expected_status:
            raise ContractValidationError("synthetic completion status is inconsistent")
        expected_phase = (
            P2PhaseStatus.SYNTHETIC_COMPLETE_REAL_DATA_BLOCKED
            if expected_complete
            else P2PhaseStatus.SYNTHETIC_INCOMPLETE
        )
        if self.phase_status is not expected_phase:
            raise ContractValidationError("P2 phase status is inconsistent")
        if not self.blocked_reason_codes or len(self.blocked_reason_codes) != len(
            set(self.blocked_reason_codes)
        ):
            raise ContractValidationError("P2 gate blocked reasons must be non-empty and unique")
        fixed_blockers = {
            "REAL_DATA_EVALUATION_NOT_RUN",
            "PAIRED_BOOTSTRAP_NOT_RUN",
            "CLASSIFICATION_NOT_CONFIRMED",
            "ACTUAL_ROUTER_MANIFEST_NOT_FROZEN",
            "P3_VALIDATION_NOT_AUTHORIZED",
            "SHADOW_NOT_AUTHORIZED",
            "OPERATIONAL_POLICY_NOT_AUTHORIZED",
        }
        component_blockers = {
            f"SYNTHETIC_{item.component.value}_BLOCKED"
            for item in self.component_checks
            if item.status is P2GateCheckStatus.BLOCKED
        }
        if not (fixed_blockers | component_blockers).issubset(
            self.blocked_reason_codes
        ):
            raise ContractValidationError("P2 gate required blocked reasons are missing")
        expected_policy_hash = P2SyntheticGatePolicy().policy_hash()
        if self.policy_version != P2_GATE_POLICY_VERSION or self.policy_hash != expected_policy_hash:
            raise ContractValidationError("P2 gate policy metadata is invalid")
        for field_name in (
            "input_cost_result_hash",
            "input_performance_result_hash",
            "input_pairwise_result_hash",
            "input_classification_result_hash",
            "input_diagnostics_result_hash",
            "input_router_manifest_hash",
            "policy_hash",
            "report_hash",
        ):
            value = getattr(self, field_name)
            if len(value) != 64 or any(
                character not in "0123456789ABCDEF" for character in value
            ):
                raise ContractValidationError(f"{field_name} must be SHA-256 hex")
        payload = asdict(self)
        payload.pop("report_hash")
        if self.report_hash != canonical_sha256(payload):
            raise ContractValidationError("report_hash does not match P2 gate contents")


def _assert_artifact_hashes(
    cost_result: CostSensitivityResult,
    performance_result: PerformanceSummaryResult,
    pairwise_result: PairwiseComparisonResult,
    classification_result: ClassificationResult,
    diagnostics_result: FailureConcentrationDiagnosticsResult,
) -> None:
    expected_cost_hash = canonical_sha256(
        {
            "input_panel_hash": cost_result.input_panel_hash,
            "policy_hash": cost_result.policy_hash,
            "observations": [asdict(item) for item in cost_result.observations],
        }
    )
    if cost_result.result_hash != expected_cost_hash:
        raise ContractValidationError("cost result hash integrity failed")
    expected_performance_hash = canonical_sha256(
        {
            "input_cost_result_hash": performance_result.input_cost_result_hash,
            "policy_hash": performance_result.policy_hash,
            "summaries": [asdict(item) for item in performance_result.summaries],
        }
    )
    if performance_result.result_hash != expected_performance_hash:
        raise ContractValidationError("performance result hash integrity failed")
    expected_pairwise_hash = canonical_sha256(
        {
            "input_cost_result_hash": pairwise_result.input_cost_result_hash,
            "policy_hash": pairwise_result.policy_hash,
            "comparisons": [asdict(item) for item in pairwise_result.comparisons],
        }
    )
    if pairwise_result.result_hash != expected_pairwise_hash:
        raise ContractValidationError("pairwise result hash integrity failed")
    expected_classification_hash = canonical_sha256(
        {
            "input_performance_result_hash": (
                classification_result.input_performance_result_hash
            ),
            "input_pairwise_result_hash": classification_result.input_pairwise_result_hash,
            "input_cost_result_hash": classification_result.input_cost_result_hash,
            "policy_hash": classification_result.policy_hash,
            "candidates": [asdict(item) for item in classification_result.candidates],
            "operational_authorization": False,
        }
    )
    if classification_result.result_hash != expected_classification_hash:
        raise ContractValidationError("classification result hash integrity failed")
    expected_diagnostics_hash = canonical_sha256(
        {
            "input_cost_result_hash": diagnostics_result.input_cost_result_hash,
            "policy_hash": diagnostics_result.policy_hash,
            "model_diagnostics": [
                asdict(item) for item in diagnostics_result.model_diagnostics
            ],
            "cross_model_periods": [
                asdict(item) for item in diagnostics_result.cross_model_periods
            ],
            "operationally_actionable": False,
        }
    )
    if diagnostics_result.result_hash != expected_diagnostics_hash:
        raise ContractValidationError("diagnostics result hash integrity failed")


def _assert_hash_chain(
    cost_result: CostSensitivityResult,
    performance_result: PerformanceSummaryResult,
    pairwise_result: PairwiseComparisonResult,
    classification_result: ClassificationResult,
    diagnostics_result: FailureConcentrationDiagnosticsResult,
    router_manifest: RouterCandidateManifest,
) -> None:
    cost_hash = cost_result.result_hash
    if any(
        input_hash != cost_hash
        for input_hash in (
            performance_result.input_cost_result_hash,
            pairwise_result.input_cost_result_hash,
            classification_result.input_cost_result_hash,
            diagnostics_result.input_cost_result_hash,
            router_manifest.input_cost_result_hash,
        )
    ):
        raise ContractValidationError("P2 artifacts do not share the same cost result hash")
    if (
        classification_result.input_performance_result_hash
        != performance_result.result_hash
        or router_manifest.input_performance_result_hash != performance_result.result_hash
    ):
        raise ContractValidationError("P2 performance hash chain is invalid")
    if (
        classification_result.input_pairwise_result_hash != pairwise_result.result_hash
        or router_manifest.input_pairwise_result_hash != pairwise_result.result_hash
    ):
        raise ContractValidationError("P2 pairwise hash chain is invalid")
    if router_manifest.input_classification_result_hash != classification_result.result_hash:
        raise ContractValidationError("P2 classification hash chain is invalid")


def _assert_readiness_integrity(
    cost_result: CostSensitivityResult,
    performance_result: PerformanceSummaryResult,
    pairwise_result: PairwiseComparisonResult,
    classification_result: ClassificationResult,
    diagnostics_result: FailureConcentrationDiagnosticsResult,
) -> None:
    expected_cost_ready = (
        cost_result.input_panel_ready
        and bool(cost_result.observations)
        and all(item.available for item in cost_result.observations)
    )
    if cost_result.evaluation_ready is not expected_cost_ready:
        raise ContractValidationError("cost evaluation readiness integrity failed")
    if (
        performance_result.input_evaluation_ready is not cost_result.evaluation_ready
        or pairwise_result.input_evaluation_ready is not cost_result.evaluation_ready
        or diagnostics_result.input_evaluation_ready is not cost_result.evaluation_ready
    ):
        raise ContractValidationError("downstream cost readiness binding failed")
    overall_summaries = [
        item
        for item in performance_result.summaries
        if item.aggregation_scope is AggregationScope.OVERALL
    ]
    expected_performance_ready = (
        cost_result.evaluation_ready
        and bool(overall_summaries)
        and all(item.evidence_status is EvidenceStatus.SUFFICIENT for item in overall_summaries)
    )
    if performance_result.summary_ready is not expected_performance_ready:
        raise ContractValidationError("performance readiness integrity failed")
    eligible_overall_pairs = [
        item
        for item in pairwise_result.comparisons
        if item.aggregation_scope is AggregationScope.OVERALL and item.ranking_eligible
    ]
    expected_pairwise_ready = (
        cost_result.evaluation_ready
        and bool(eligible_overall_pairs)
        and all(
            item.evidence_status is EvidenceStatus.SUFFICIENT
            for item in eligible_overall_pairs
        )
    )
    if pairwise_result.comparison_ready is not expected_pairwise_ready:
        raise ContractValidationError("pairwise readiness integrity failed")
    evaluation_candidates = [
        item
        for item in classification_result.candidates
        if item.scope_role is EvaluationScopeRole.EVALUATION_CANDIDATE
    ]
    expected_classification_ready = (
        performance_result.summary_ready
        and pairwise_result.comparison_ready
        and bool(evaluation_candidates)
        and all(
            item.proposed_classification is not ModelResearchClass.INSUFFICIENT_EVIDENCE
            for item in evaluation_candidates
        )
    )
    if (
        classification_result.input_performance_ready
        is not performance_result.summary_ready
        or classification_result.input_pairwise_ready
        is not pairwise_result.comparison_ready
        or classification_result.research_gate_ready
        is not expected_classification_ready
    ):
        raise ContractValidationError("classification readiness integrity failed")
    eligible_cross_periods = [
        item
        for item in diagnostics_result.cross_model_periods
        if item.candidate_model_count > 0
    ]
    expected_diagnostics_ready = (
        cost_result.evaluation_ready
        and bool(diagnostics_result.model_diagnostics)
        and all(
            item.evidence_status is EvidenceStatus.SUFFICIENT
            for item in diagnostics_result.model_diagnostics
        )
        and bool(eligible_cross_periods)
        and all(
            item.evidence_status is EvidenceStatus.SUFFICIENT
            for item in eligible_cross_periods
        )
    )
    if diagnostics_result.diagnostics_ready is not expected_diagnostics_ready:
        raise ContractValidationError("diagnostics readiness integrity failed")


def _check(
    component: P2GateComponent,
    passed: bool,
    source_hash: str,
    reason_code: str,
) -> P2GateComponentCheck:
    return P2GateComponentCheck(
        component=component,
        status=P2GateCheckStatus.PASS if passed else P2GateCheckStatus.BLOCKED,
        source_hash=source_hash,
        reason_codes=() if passed else (reason_code,),
    )


def build_p2_synthetic_completion_gate(
    cost_result: CostSensitivityResult,
    performance_result: PerformanceSummaryResult,
    pairwise_result: PairwiseComparisonResult,
    classification_result: ClassificationResult,
    diagnostics_result: FailureConcentrationDiagnosticsResult,
    router_manifest: RouterCandidateManifest,
    *,
    policy: P2SyntheticGatePolicy | None = None,
) -> P2SyntheticCompletionReport:
    applied_policy = policy or P2SyntheticGatePolicy()
    _assert_artifact_hashes(
        cost_result,
        performance_result,
        pairwise_result,
        classification_result,
        diagnostics_result,
    )
    _assert_hash_chain(
        cost_result,
        performance_result,
        pairwise_result,
        classification_result,
        diagnostics_result,
        router_manifest,
    )
    _assert_readiness_integrity(
        cost_result,
        performance_result,
        pairwise_result,
        classification_result,
        diagnostics_result,
    )
    observed_models = tuple(
        sorted({item.model_code for item in cost_result.observations})
    )
    observed_costs = tuple(sorted({item.cost_bps for item in cost_result.observations}))
    missing_models = set(applied_policy.required_model_codes) - set(observed_models)
    unsupported_models = set(observed_models) - set(applied_policy.required_model_codes) - set(
        applied_policy.optional_model_codes
    )
    model_cost_groups = {
        (item.model_code, item.cost_bps) for item in cost_result.observations
    }
    missing_model_cost_groups = {
        (model_code, cost_bps)
        for model_code in observed_models
        for cost_bps in applied_policy.required_cost_bps
        if (model_code, cost_bps) not in model_cost_groups
    }
    coverage_ready = (
        not missing_models
        and not unsupported_models
        and observed_costs == applied_policy.required_cost_bps
        and not missing_model_cost_groups
    )
    required_manifest_blockers = {
        "REAL_DATA_CLASSIFICATION_NOT_VALIDATED",
        "PAIRED_BOOTSTRAP_NOT_VALIDATED",
        "CLASSIFICATION_NOT_CONFIRMED",
        "SHADOW_POLICY_NOT_AUTHORIZED",
    }
    manifest_ready = (
        router_manifest.router_code == applied_policy.required_router_code
        and router_manifest.status
        is RouterCandidateStatus.PROVISIONAL_NOT_ELIGIBLE_FOR_SHADOW
        and router_manifest.research_gate_ready
        is classification_result.research_gate_ready
        and router_manifest.research_manifest_ready
        and router_manifest.candidate_identity_frozen
        and router_manifest.hypothesis_snapshot_frozen
    )
    safety_ready = (
        not classification_result.operational_authorization
        and not diagnostics_result.operationally_actionable
        and not router_manifest.routing_weights_defined
        and not router_manifest.real_data_classification_validated
        and not router_manifest.paired_bootstrap_validated
        and not router_manifest.classification_confirmed
        and not router_manifest.shadow_target_generation_allowed
        and not router_manifest.eligible_for_p3_validation
        and not router_manifest.operational_authorization
        and required_manifest_blockers.issubset(router_manifest.blocked_reason_codes)
    )
    checks = (
        _check(
            P2GateComponent.CONTRACT_COVERAGE,
            coverage_ready,
            cost_result.result_hash,
            "REQUIRED_MODEL_OR_COST_COVERAGE_INCOMPLETE",
        ),
        _check(
            P2GateComponent.COST_EVALUATION,
            cost_result.evaluation_ready,
            cost_result.result_hash,
            "COST_EVALUATION_NOT_READY",
        ),
        _check(
            P2GateComponent.PERFORMANCE_SUMMARY,
            performance_result.summary_ready,
            performance_result.result_hash,
            "PERFORMANCE_SUMMARY_NOT_READY",
        ),
        _check(
            P2GateComponent.PAIRWISE_COMPARISON,
            pairwise_result.comparison_ready,
            pairwise_result.result_hash,
            "PAIRWISE_COMPARISON_NOT_READY",
        ),
        _check(
            P2GateComponent.RESEARCH_CLASSIFICATION,
            classification_result.research_gate_ready,
            classification_result.result_hash,
            "RESEARCH_CLASSIFICATION_NOT_READY",
        ),
        _check(
            P2GateComponent.FAILURE_CONCENTRATION_DIAGNOSTICS,
            diagnostics_result.diagnostics_ready,
            diagnostics_result.result_hash,
            "FAILURE_CONCENTRATION_DIAGNOSTICS_NOT_READY",
        ),
        _check(
            P2GateComponent.ROUTER_CANDIDATE_MANIFEST,
            manifest_ready,
            router_manifest.manifest_hash,
            "ROUTER_CANDIDATE_MANIFEST_NOT_READY",
        ),
        _check(
            P2GateComponent.SAFETY_LOCKS,
            safety_ready,
            router_manifest.manifest_hash,
            "P2_SAFETY_LOCKS_INVALID",
        ),
    )
    synthetic_complete = all(
        item.status is P2GateCheckStatus.PASS for item in checks
    )
    blocked_reasons = [
        "REAL_DATA_EVALUATION_NOT_RUN",
        "PAIRED_BOOTSTRAP_NOT_RUN",
        "CLASSIFICATION_NOT_CONFIRMED",
        "ACTUAL_ROUTER_MANIFEST_NOT_FROZEN",
        "P3_VALIDATION_NOT_AUTHORIZED",
        "SHADOW_NOT_AUTHORIZED",
        "OPERATIONAL_POLICY_NOT_AUTHORIZED",
    ]
    blocked_reasons.extend(
        f"SYNTHETIC_{item.component.value}_BLOCKED"
        for item in checks
        if item.status is P2GateCheckStatus.BLOCKED
    )
    policy_hash = applied_policy.policy_hash()
    payload = {
        "component_checks": checks,
        "observed_model_codes": observed_models,
        "observed_cost_bps": observed_costs,
        "input_cost_result_hash": cost_result.result_hash,
        "input_performance_result_hash": performance_result.result_hash,
        "input_pairwise_result_hash": pairwise_result.result_hash,
        "input_classification_result_hash": classification_result.result_hash,
        "input_diagnostics_result_hash": diagnostics_result.result_hash,
        "input_router_manifest_hash": router_manifest.manifest_hash,
        "synthetic_completion_status": (
            P2SyntheticCompletionStatus.PASS
            if synthetic_complete
            else P2SyntheticCompletionStatus.INCOMPLETE
        ),
        "real_data_status": P2RealDataStatus.NOT_RUN,
        "phase_status": (
            P2PhaseStatus.SYNTHETIC_COMPLETE_REAL_DATA_BLOCKED
            if synthetic_complete
            else P2PhaseStatus.SYNTHETIC_INCOMPLETE
        ),
        "synthetic_contract_complete": synthetic_complete,
        "real_data_evaluation_complete": False,
        "paired_bootstrap_complete": False,
        "classification_confirmed": False,
        "actual_router_manifest_frozen": False,
        "p2_complete": False,
        "eligible_for_p3_validation": False,
        "eligible_for_shadow": False,
        "operational_authorization": False,
        "blocked_reason_codes": tuple(blocked_reasons),
        "policy_version": applied_policy.version,
        "policy_hash": policy_hash,
    }
    return P2SyntheticCompletionReport(
        **payload,
        report_hash=canonical_sha256(payload),
    )
