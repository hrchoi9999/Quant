from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketStage,
    canonical_sha256,
)
from src.quant2.evaluation.classification import (
    ClassificationResult,
    ModelClassificationCandidate,
    ModelResearchClass,
)
from src.quant2.evaluation.input_connector import EvaluationScopeRole
from src.quant2.evaluation.performance import EvidenceStatus

ROUTER_CANDIDATE_CODE = "ROUTER_REGIME_HIERARCHICAL_V1_SHADOW"
ROUTER_MANIFEST_POLICY_VERSION = "quant2.router_candidate_manifest.v1"
ROUTER_REQUIRED_INPUT_FIELDS = (
    "base_user_profile_weights",
    "market_structure",
    "market_stage",
    "market_confidence",
    "transition_flag",
    "shock_overlay",
    "low_confidence_overlay",
    "risk_appetite",
    "model_research_classification",
    "model_performance_guardrail",
    "model_rule_hash",
)
ROUTER_CALCULATION_LAYERS = (
    "BASE_USER_PROFILE_WEIGHTS",
    "REGIME_MODEL_FITNESS",
    "REGIME_CONFIDENCE",
    "RISK_OVERLAY",
    "MODEL_PERFORMANCE_GUARDRAIL",
    "TURNOVER_AND_WEIGHT_CHANGE_CAP",
)


class RouterCandidateStatus(str, Enum):
    PROVISIONAL_NOT_ELIGIBLE_FOR_SHADOW = "PROVISIONAL_NOT_ELIGIBLE_FOR_SHADOW"


class RouterHypothesisScope(str, Enum):
    ALL_MARKET_STAGES = "ALL_MARKET_STAGES"
    SINGLE_MARKET_STAGE = "SINGLE_MARKET_STAGE"
    RESEARCH_OBSERVATION_ONLY = "RESEARCH_OBSERVATION_ONLY"
    REFERENCE_VALIDATION_ONLY = "REFERENCE_VALIDATION_ONLY"
    EXCLUDED_PENDING_REVIEW = "EXCLUDED_PENDING_REVIEW"
    BLOCKED_INSUFFICIENT_EVIDENCE = "BLOCKED_INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class RouterManifestPolicy:
    router_code: str = ROUTER_CANDIDATE_CODE
    schema_version: str = "quant2.router_candidate_manifest.v1"
    performance_grid: str = "MONTH_END"
    execution_contract: str = "D_CLOSE_DECISION_NEXT_TRADABLE_SESSION"
    fallback_contract: str = "CASH_OR_CONTRACTED_FALLBACK_ONLY"
    forecast_contract: str = "TRANSITION_BUDGET_ONLY_NO_STATE_OVERRIDE"
    required_input_fields: tuple[str, ...] = ROUTER_REQUIRED_INPUT_FIELDS
    calculation_layers: tuple[str, ...] = ROUTER_CALCULATION_LAYERS
    maximum_router_candidates: int = 1
    version: str = ROUTER_MANIFEST_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.router_code != ROUTER_CANDIDATE_CODE:
            raise ContractValidationError("only the frozen Quant 2.0 Router candidate is allowed")
        if self.maximum_router_candidates != 1:
            raise ContractValidationError("exactly one Router candidate must be frozen")
        fixed_contracts = {
            "schema_version": "quant2.router_candidate_manifest.v1",
            "performance_grid": "MONTH_END",
            "execution_contract": "D_CLOSE_DECISION_NEXT_TRADABLE_SESSION",
            "fallback_contract": "CASH_OR_CONTRACTED_FALLBACK_ONLY",
            "forecast_contract": "TRANSITION_BUDGET_ONLY_NO_STATE_OVERRIDE",
            "version": ROUTER_MANIFEST_POLICY_VERSION,
        }
        for field_name, expected in fixed_contracts.items():
            if getattr(self, field_name) != expected:
                raise ContractValidationError(f"{field_name} is frozen by Router manifest v1")
        for field_name in (
            "schema_version",
            "performance_grid",
            "execution_contract",
            "fallback_contract",
            "forecast_contract",
            "version",
        ):
            if not getattr(self, field_name).strip():
                raise ContractValidationError(f"{field_name} is required")
        if not self.required_input_fields or len(self.required_input_fields) != len(
            set(self.required_input_fields)
        ):
            raise ContractValidationError("required_input_fields must be non-empty and unique")
        if not self.calculation_layers or len(self.calculation_layers) != len(
            set(self.calculation_layers)
        ):
            raise ContractValidationError("calculation_layers must be non-empty and unique")
        if self.required_input_fields != ROUTER_REQUIRED_INPUT_FIELDS:
            raise ContractValidationError("required_input_fields are frozen by Router manifest v1")
        if self.calculation_layers != ROUTER_CALCULATION_LAYERS:
            raise ContractValidationError("calculation_layers are frozen by Router manifest v1")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ModelRoutingHypothesis:
    model_code: str
    research_classification: ModelResearchClass
    evidence_status: EvidenceStatus
    scope_role: EvaluationScopeRole
    hypothesis_scope: RouterHypothesisScope
    market_stages: tuple[MarketStage, ...]
    included_in_routing_hypothesis: bool
    shadow_eligible: bool
    operationally_actionable: bool
    source_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.model_code.strip():
            raise ContractValidationError("model_code is required")
        if self.shadow_eligible or self.operationally_actionable:
            raise ContractValidationError("pre-frozen model hypotheses cannot be actionable")
        if len(self.market_stages) != len(set(self.market_stages)):
            raise ContractValidationError("model hypothesis market stages must be unique")
        if self.included_in_routing_hypothesis:
            if self.scope_role is not EvaluationScopeRole.EVALUATION_CANDIDATE:
                raise ContractValidationError("scope-limited models cannot enter routing hypothesis")
            if self.evidence_status is not EvidenceStatus.SUFFICIENT:
                raise ContractValidationError("routing hypothesis requires sufficient evidence")
            if self.research_classification not in {
                ModelResearchClass.CORE,
                ModelResearchClass.REGIME_SPECIALIST,
            }:
                raise ContractValidationError("only core or specialist models may enter hypothesis")
            if not self.market_stages:
                raise ContractValidationError("included model hypothesis requires market stages")
        elif self.market_stages:
            raise ContractValidationError("excluded model hypothesis cannot carry market stages")
        if (
            self.hypothesis_scope is RouterHypothesisScope.ALL_MARKET_STAGES
            and self.market_stages != tuple(MarketStage)
        ):
            raise ContractValidationError("all-stage hypothesis must include every market stage")
        if (
            self.hypothesis_scope is RouterHypothesisScope.SINGLE_MARKET_STAGE
            and len(self.market_stages) != 1
        ):
            raise ContractValidationError("single-stage hypothesis must include exactly one stage")


@dataclass(frozen=True)
class StageRoutingHypothesis:
    market_stage: MarketStage
    hypothesis_model_codes: tuple[str, ...]
    allocation_weights_defined: bool

    def __post_init__(self) -> None:
        if self.hypothesis_model_codes != tuple(sorted(set(self.hypothesis_model_codes))):
            raise ContractValidationError("stage hypothesis model codes must be sorted and unique")
        if self.allocation_weights_defined:
            raise ContractValidationError("pre-freeze manifest cannot define allocation weights")


@dataclass(frozen=True)
class RouterCandidateManifest:
    router_code: str
    schema_version: str
    status: RouterCandidateStatus
    input_classification_result_hash: str
    input_classification_policy_version: str
    input_performance_result_hash: str
    input_pairwise_result_hash: str
    input_cost_result_hash: str
    research_gate_ready: bool
    research_manifest_ready: bool
    candidate_identity_frozen: bool
    hypothesis_snapshot_frozen: bool
    routing_weights_defined: bool
    real_data_classification_validated: bool
    paired_bootstrap_validated: bool
    classification_confirmed: bool
    shadow_target_generation_allowed: bool
    eligible_for_p3_validation: bool
    operational_authorization: bool
    performance_grid: str
    execution_contract: str
    fallback_contract: str
    forecast_contract: str
    required_input_fields: tuple[str, ...]
    calculation_layers: tuple[str, ...]
    model_hypotheses: tuple[ModelRoutingHypothesis, ...]
    stage_hypotheses: tuple[StageRoutingHypothesis, ...]
    blocked_reason_codes: tuple[str, ...]
    policy_version: str
    policy_hash: str
    manifest_hash: str

    def __post_init__(self) -> None:
        if self.router_code != ROUTER_CANDIDATE_CODE:
            raise ContractValidationError("Router candidate identity changed after pre-freeze")
        if self.schema_version != "quant2.router_candidate_manifest.v1":
            raise ContractValidationError("Router candidate schema changed after pre-freeze")
        if self.status is not RouterCandidateStatus.PROVISIONAL_NOT_ELIGIBLE_FOR_SHADOW:
            raise ContractValidationError("pre-freeze manifest must remain provisional")
        if not self.candidate_identity_frozen or not self.hypothesis_snapshot_frozen:
            raise ContractValidationError("candidate identity and hypothesis snapshot must be frozen")
        if (
            self.routing_weights_defined
            or self.real_data_classification_validated
            or self.paired_bootstrap_validated
            or self.classification_confirmed
            or self.shadow_target_generation_allowed
            or self.eligible_for_p3_validation
            or self.operational_authorization
        ):
            raise ContractValidationError("pre-freeze manifest cannot grant validation or operation")
        if not self.blocked_reason_codes:
            raise ContractValidationError("provisional manifest requires blocked reasons")
        if len(self.blocked_reason_codes) != len(set(self.blocked_reason_codes)):
            raise ContractValidationError("blocked_reason_codes must be unique")
        if len(self.model_hypotheses) != len(
            {item.model_code for item in self.model_hypotheses}
        ):
            raise ContractValidationError("model hypotheses must have unique model codes")
        if tuple(item.model_code for item in self.model_hypotheses) != tuple(
            sorted(item.model_code for item in self.model_hypotheses)
        ):
            raise ContractValidationError("model hypotheses must be sorted")
        if tuple(item.market_stage for item in self.stage_hypotheses) != tuple(MarketStage):
            raise ContractValidationError("stage hypotheses must cover every market stage in order")
        expected_by_stage = {
            stage: tuple(
                sorted(
                    item.model_code
                    for item in self.model_hypotheses
                    if item.included_in_routing_hypothesis and stage in item.market_stages
                )
            )
            for stage in MarketStage
        }
        for stage_hypothesis in self.stage_hypotheses:
            if stage_hypothesis.hypothesis_model_codes != expected_by_stage[
                stage_hypothesis.market_stage
            ]:
                raise ContractValidationError("stage and model hypotheses are inconsistent")
        included_models = [
            item for item in self.model_hypotheses if item.included_in_routing_hypothesis
        ]
        if self.research_manifest_ready is not (
            self.research_gate_ready and bool(included_models)
        ):
            raise ContractValidationError("research_manifest_ready conflicts with evidence state")
        fixed_policy = RouterManifestPolicy()
        if (
            self.performance_grid != fixed_policy.performance_grid
            or self.execution_contract != fixed_policy.execution_contract
            or self.fallback_contract != fixed_policy.fallback_contract
            or self.forecast_contract != fixed_policy.forecast_contract
            or self.required_input_fields != fixed_policy.required_input_fields
            or self.calculation_layers != fixed_policy.calculation_layers
            or self.policy_version != fixed_policy.version
        ):
            raise ContractValidationError("manifest contents conflict with frozen Router policy")
        if self.policy_hash != fixed_policy.policy_hash():
            raise ContractValidationError("policy_hash does not match frozen Router policy")
        for field_name in (
            "input_classification_result_hash",
            "input_performance_result_hash",
            "input_pairwise_result_hash",
            "input_cost_result_hash",
            "policy_hash",
            "manifest_hash",
        ):
            value = getattr(self, field_name)
            if len(value) != 64 or any(
                character not in "0123456789ABCDEF" for character in value
            ):
                raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")
        payload = asdict(self)
        payload.pop("manifest_hash")
        if self.manifest_hash != canonical_sha256(payload):
            raise ContractValidationError("manifest_hash does not match manifest contents")


def _model_hypothesis(candidate: ModelClassificationCandidate) -> ModelRoutingHypothesis:
    classification = candidate.proposed_classification
    if classification is ModelResearchClass.CORE:
        if (
            candidate.scope_role is not EvaluationScopeRole.EVALUATION_CANDIDATE
            or candidate.evidence_status is not EvidenceStatus.SUFFICIENT
        ):
            raise ContractValidationError("core hypothesis conflicts with scope or evidence")
        scope = RouterHypothesisScope.ALL_MARKET_STAGES
        stages = tuple(MarketStage)
        included = True
    elif classification is ModelResearchClass.REGIME_SPECIALIST:
        if (
            candidate.scope_role is not EvaluationScopeRole.EVALUATION_CANDIDATE
            or candidate.evidence_status is not EvidenceStatus.SUFFICIENT
            or candidate.strongest_regime_stage is None
        ):
            raise ContractValidationError("specialist hypothesis requires a supported market stage")
        scope = RouterHypothesisScope.SINGLE_MARKET_STAGE
        stages = (candidate.strongest_regime_stage,)
        included = True
    elif classification is ModelResearchClass.CHALLENGER:
        scope = RouterHypothesisScope.RESEARCH_OBSERVATION_ONLY
        stages = ()
        included = False
    elif classification is ModelResearchClass.REFERENCE_VALIDATION:
        scope = RouterHypothesisScope.REFERENCE_VALIDATION_ONLY
        stages = ()
        included = False
    elif classification is ModelResearchClass.RETIRE_CANDIDATE:
        scope = RouterHypothesisScope.EXCLUDED_PENDING_REVIEW
        stages = ()
        included = False
    else:
        scope = RouterHypothesisScope.BLOCKED_INSUFFICIENT_EVIDENCE
        stages = ()
        included = False
    return ModelRoutingHypothesis(
        model_code=candidate.model_code,
        research_classification=classification,
        evidence_status=candidate.evidence_status,
        scope_role=candidate.scope_role,
        hypothesis_scope=scope,
        market_stages=stages,
        included_in_routing_hypothesis=included,
        shadow_eligible=False,
        operationally_actionable=False,
        source_reason_codes=candidate.reason_codes,
    )


def pre_freeze_router_candidate(
    classification_result: ClassificationResult,
    *,
    policy: RouterManifestPolicy | None = None,
) -> RouterCandidateManifest:
    applied_policy = policy or RouterManifestPolicy()
    if classification_result.operational_authorization:
        raise ContractValidationError("operational classification cannot enter pre-freeze")
    if not classification_result.candidates:
        raise ContractValidationError("classification result requires model candidates")
    for field_name in (
        "result_hash",
        "input_performance_result_hash",
        "input_pairwise_result_hash",
        "input_cost_result_hash",
    ):
        value = getattr(classification_result, field_name)
        if len(value) != 64 or any(
            character not in "0123456789ABCDEF" for character in value
        ):
            raise ContractValidationError(f"classification {field_name} must be SHA-256 hex")
    model_codes = [candidate.model_code for candidate in classification_result.candidates]
    if len(model_codes) != len(set(model_codes)):
        raise ContractValidationError("classification candidates must have unique model codes")
    model_hypotheses = tuple(
        sorted(
            (_model_hypothesis(candidate) for candidate in classification_result.candidates),
            key=lambda item: item.model_code,
        )
    )
    stage_hypotheses = tuple(
        StageRoutingHypothesis(
            market_stage=stage,
            hypothesis_model_codes=tuple(
                sorted(
                    item.model_code
                    for item in model_hypotheses
                    if item.included_in_routing_hypothesis and stage in item.market_stages
                )
            ),
            allocation_weights_defined=False,
        )
        for stage in MarketStage
    )
    included_models = [
        item for item in model_hypotheses if item.included_in_routing_hypothesis
    ]
    insufficient_models = [
        item
        for item in model_hypotheses
        if item.evidence_status is not EvidenceStatus.SUFFICIENT
    ]
    blocked_reasons = [
        "REAL_DATA_CLASSIFICATION_NOT_VALIDATED",
        "PAIRED_BOOTSTRAP_NOT_VALIDATED",
        "CLASSIFICATION_NOT_CONFIRMED",
        "SHADOW_POLICY_NOT_AUTHORIZED",
    ]
    if not classification_result.research_gate_ready:
        blocked_reasons.append("RESEARCH_GATE_NOT_READY")
    if not included_models:
        blocked_reasons.append("NO_CORE_OR_SPECIALIST_HYPOTHESIS")
    if insufficient_models:
        blocked_reasons.append("INSUFFICIENT_MODEL_EVIDENCE")
    policy_hash = applied_policy.policy_hash()
    payload = {
        "router_code": applied_policy.router_code,
        "schema_version": applied_policy.schema_version,
        "status": RouterCandidateStatus.PROVISIONAL_NOT_ELIGIBLE_FOR_SHADOW,
        "input_classification_result_hash": classification_result.result_hash,
        "input_classification_policy_version": classification_result.policy_version,
        "input_performance_result_hash": classification_result.input_performance_result_hash,
        "input_pairwise_result_hash": classification_result.input_pairwise_result_hash,
        "input_cost_result_hash": classification_result.input_cost_result_hash,
        "research_gate_ready": classification_result.research_gate_ready,
        "research_manifest_ready": (
            classification_result.research_gate_ready and bool(included_models)
        ),
        "candidate_identity_frozen": True,
        "hypothesis_snapshot_frozen": True,
        "routing_weights_defined": False,
        "real_data_classification_validated": False,
        "paired_bootstrap_validated": False,
        "classification_confirmed": False,
        "shadow_target_generation_allowed": False,
        "eligible_for_p3_validation": False,
        "operational_authorization": False,
        "performance_grid": applied_policy.performance_grid,
        "execution_contract": applied_policy.execution_contract,
        "fallback_contract": applied_policy.fallback_contract,
        "forecast_contract": applied_policy.forecast_contract,
        "required_input_fields": applied_policy.required_input_fields,
        "calculation_layers": applied_policy.calculation_layers,
        "model_hypotheses": model_hypotheses,
        "stage_hypotheses": stage_hypotheses,
        "blocked_reason_codes": tuple(blocked_reasons),
        "policy_version": applied_policy.version,
        "policy_hash": policy_hash,
    }
    return RouterCandidateManifest(
        **payload,
        manifest_hash=canonical_sha256(payload),
    )
