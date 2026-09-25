from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketStage,
    MarketStructure,
    canonical_sha256,
)
from src.quant2.evaluation.input_connector import EvaluationScopeRole
from src.quant2.evaluation.pairwise import (
    PairwiseComparisonResult,
    PairwiseModelComparison,
    RedundancyLevel,
)
from src.quant2.evaluation.performance import (
    AggregationScope,
    EvidenceStatus,
    ModelPerformanceSummary,
    PerformanceSummaryResult,
)

CLASSIFICATION_POLICY_VERSION = "quant2.research_classification.v1"


class ModelResearchClass(str, Enum):
    CORE = "CORE"
    REGIME_SPECIALIST = "REGIME_SPECIALIST"
    CHALLENGER = "CHALLENGER"
    REFERENCE_VALIDATION = "REFERENCE_VALIDATION"
    RETIRE_CANDIDATE = "RETIRE_CANDIDATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ClassificationPolicy:
    primary_cost_bps: int = 10
    stress_cost_bps: int = 30
    minimum_overall_sharpe: float = 0.50
    minimum_overall_net_excess_return: float = 0.0
    minimum_stress_net_excess_return: float = 0.0
    minimum_mdd: float = -0.30
    minimum_specialist_sharpe: float = 0.50
    minimum_specialist_net_excess_return: float = 0.03
    minimum_marginal_contribution: float = 0.0
    minimum_sufficient_pairwise_comparisons: int = 1
    version: str = CLASSIFICATION_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.primary_cost_bps <= 0 or self.stress_cost_bps <= 0:
            raise ContractValidationError("classification cost scenarios must be positive")
        if self.primary_cost_bps >= self.stress_cost_bps:
            raise ContractValidationError("stress_cost_bps must exceed primary_cost_bps")
        numeric_values = (
            self.minimum_overall_sharpe,
            self.minimum_overall_net_excess_return,
            self.minimum_stress_net_excess_return,
            self.minimum_mdd,
            self.minimum_specialist_sharpe,
            self.minimum_specialist_net_excess_return,
            self.minimum_marginal_contribution,
        )
        if any(not math.isfinite(value) for value in numeric_values):
            raise ContractValidationError("classification thresholds must be finite")
        if not -1.0 <= self.minimum_mdd <= 0.0:
            raise ContractValidationError("minimum_mdd must be between -100% and 0%")
        if self.minimum_sufficient_pairwise_comparisons < 1:
            raise ContractValidationError(
                "minimum_sufficient_pairwise_comparisons must be positive"
            )
        if not self.version.strip():
            raise ContractValidationError("classification policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ModelClassificationCandidate:
    model_code: str
    scope_role: EvaluationScopeRole
    ranking_eligible: bool
    proposed_classification: ModelResearchClass
    evidence_status: EvidenceStatus
    operationally_actionable: bool
    primary_cost_bps: int
    stress_cost_bps: int
    primary_total_net_excess_return: float | None
    stress_total_net_excess_return: float | None
    primary_sharpe: float | None
    primary_mdd: float | None
    strongest_regime_structure: MarketStructure | None
    strongest_regime_stage: MarketStage | None
    strongest_regime_total_net_excess_return: float | None
    strongest_regime_sharpe: float | None
    sufficient_overall_pairwise_count: int
    high_redundancy_pair_count: int
    positive_overall_marginal_count: int
    maximum_overall_marginal_contribution: float | None
    strongest_regime_marginal_contribution: float | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.operationally_actionable:
            raise ContractValidationError(
                "research classification candidates cannot be operationally actionable"
            )
        expected_ranking = self.scope_role is EvaluationScopeRole.EVALUATION_CANDIDATE
        if self.ranking_eligible is not expected_ranking:
            raise ContractValidationError("ranking_eligible conflicts with scope role")


@dataclass(frozen=True)
class ClassificationResult:
    candidates: tuple[ModelClassificationCandidate, ...]
    input_performance_result_hash: str
    input_pairwise_result_hash: str
    input_cost_result_hash: str
    input_performance_ready: bool
    input_pairwise_ready: bool
    research_gate_ready: bool
    operational_authorization: bool
    policy_version: str
    policy_hash: str
    result_hash: str

    def __post_init__(self) -> None:
        if self.operational_authorization:
            raise ContractValidationError(
                "classification evidence gate cannot grant operational authorization"
            )


def _index_performance(
    result: PerformanceSummaryResult,
) -> dict[tuple[str, int, AggregationScope, MarketStructure | None, MarketStage | None], ModelPerformanceSummary]:
    indexed: dict[
        tuple[str, int, AggregationScope, MarketStructure | None, MarketStage | None],
        ModelPerformanceSummary,
    ] = {}
    roles: dict[str, set[EvaluationScopeRole]] = {}
    ranking: dict[str, set[bool]] = {}
    for summary in result.summaries:
        key = (
            summary.model_code,
            summary.cost_bps,
            summary.aggregation_scope,
            summary.market_structure,
            summary.market_stage,
        )
        if key in indexed:
            raise ContractValidationError("duplicate performance summary for classification")
        indexed[key] = summary
        roles.setdefault(summary.model_code, set()).add(summary.scope_role)
        ranking.setdefault(summary.model_code, set()).add(summary.ranking_eligible)
    if any(len(values) != 1 for values in roles.values()):
        raise ContractValidationError("a model cannot mix scope roles in classification")
    if any(len(values) != 1 for values in ranking.values()):
        raise ContractValidationError("a model cannot mix ranking eligibility in classification")
    return indexed


def _marginal_contribution(
    comparison: PairwiseModelComparison,
    model_code: str,
) -> float | None:
    if comparison.model_a == model_code:
        return comparison.model_a_marginal_contribution_to_b
    if comparison.model_b == model_code:
        return comparison.model_b_marginal_contribution_to_a
    raise ContractValidationError("model is not part of pairwise comparison")


def _validate_pairwise_against_performance(
    comparisons: tuple[PairwiseModelComparison, ...],
    indexed_performance: dict[
        tuple[str, int, AggregationScope, MarketStructure | None, MarketStage | None],
        ModelPerformanceSummary,
    ],
) -> None:
    performance_roles: dict[str, EvaluationScopeRole] = {}
    performance_ranking: dict[str, bool] = {}
    for summary in indexed_performance.values():
        performance_roles[summary.model_code] = summary.scope_role
        performance_ranking[summary.model_code] = summary.ranking_eligible
    seen: set[
        tuple[
            str,
            str,
            int,
            AggregationScope,
            MarketStructure | None,
            MarketStage | None,
        ]
    ] = set()
    for comparison in comparisons:
        key = (
            comparison.model_a,
            comparison.model_b,
            comparison.cost_bps,
            comparison.aggregation_scope,
            comparison.market_structure,
            comparison.market_stage,
        )
        if key in seen:
            raise ContractValidationError("duplicate pairwise comparison for classification")
        seen.add(key)
        if comparison.model_a not in performance_roles or comparison.model_b not in performance_roles:
            raise ContractValidationError("pairwise model is missing from performance summaries")
        if (
            comparison.model_a_scope_role is not performance_roles[comparison.model_a]
            or comparison.model_b_scope_role is not performance_roles[comparison.model_b]
        ):
            raise ContractValidationError("pairwise scope role conflicts with performance summary")
        expected_pair_ranking = (
            performance_ranking[comparison.model_a]
            and performance_ranking[comparison.model_b]
        )
        if comparison.ranking_eligible is not expected_pair_ranking:
            raise ContractValidationError(
                "pairwise ranking eligibility conflicts with performance summary"
            )


def _strongest_regime(
    summaries: list[ModelPerformanceSummary],
) -> ModelPerformanceSummary | None:
    eligible = [
        summary
        for summary in summaries
        if summary.aggregation_scope is AggregationScope.MARKET_STAGE
        and summary.evidence_status is EvidenceStatus.SUFFICIENT
        and summary.total_net_excess_return is not None
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda item: (
            float(item.total_net_excess_return),
            float(item.sharpe) if item.sharpe is not None else float("-inf"),
            item.market_structure.value if item.market_structure else "",
            item.market_stage.value if item.market_stage else "",
        ),
    )


def _matching_regime_marginal(
    comparisons: list[PairwiseModelComparison],
    model_code: str,
    strongest_regime: ModelPerformanceSummary | None,
) -> float | None:
    if strongest_regime is None:
        return None
    values = [
        value
        for comparison in comparisons
        if comparison.aggregation_scope is AggregationScope.MARKET_STAGE
        and comparison.market_structure is strongest_regime.market_structure
        and comparison.market_stage is strongest_regime.market_stage
        and comparison.evidence_status is EvidenceStatus.SUFFICIENT
        and comparison.ranking_eligible
        and model_code in {comparison.model_a, comparison.model_b}
        for value in [_marginal_contribution(comparison, model_code)]
        if value is not None
    ]
    return max(values) if values else None


def _scope_limited_classification(
    role: EvaluationScopeRole,
) -> tuple[ModelResearchClass, str] | None:
    if role is EvaluationScopeRole.REFERENCE_VALIDATION_ONLY:
        return ModelResearchClass.REFERENCE_VALIDATION, "SCOPE_REFERENCE_VALIDATION_ONLY"
    if role is EvaluationScopeRole.ALPHA_VALIDATION:
        return ModelResearchClass.REFERENCE_VALIDATION, "SCOPE_ALPHA_VALIDATION_ONLY"
    if role is EvaluationScopeRole.GUARDED_CHALLENGER:
        return ModelResearchClass.CHALLENGER, "SCOPE_GUARDED_CHALLENGER"
    return None


def _candidate_for_model(
    model_code: str,
    summaries: list[ModelPerformanceSummary],
    comparisons: list[PairwiseModelComparison],
    *,
    policy: ClassificationPolicy,
) -> ModelClassificationCandidate:
    first = summaries[0]
    primary = next(
        (
            summary
            for summary in summaries
            if summary.cost_bps == policy.primary_cost_bps
            and summary.aggregation_scope is AggregationScope.OVERALL
        ),
        None,
    )
    stress = next(
        (
            summary
            for summary in summaries
            if summary.cost_bps == policy.stress_cost_bps
            and summary.aggregation_scope is AggregationScope.OVERALL
        ),
        None,
    )
    primary_regime_summaries = [
        summary for summary in summaries if summary.cost_bps == policy.primary_cost_bps
    ]
    strongest_regime = _strongest_regime(primary_regime_summaries)
    primary_pairwise = [
        comparison
        for comparison in comparisons
        if comparison.cost_bps == policy.primary_cost_bps
        and model_code in {comparison.model_a, comparison.model_b}
        and comparison.ranking_eligible
    ]
    sufficient_overall = [
        comparison
        for comparison in primary_pairwise
        if comparison.aggregation_scope is AggregationScope.OVERALL
        and comparison.evidence_status is EvidenceStatus.SUFFICIENT
    ]
    marginal_values = [
        value
        for comparison in sufficient_overall
        for value in [_marginal_contribution(comparison, model_code)]
        if value is not None
    ]
    maximum_marginal = max(marginal_values) if marginal_values else None
    positive_marginal_count = sum(
        value > policy.minimum_marginal_contribution for value in marginal_values
    )
    high_redundancy_count = sum(
        comparison.redundancy_level is RedundancyLevel.HIGH
        for comparison in sufficient_overall
    )
    regime_marginal = _matching_regime_marginal(
        primary_pairwise,
        model_code,
        strongest_regime,
    )
    scope_limited = _scope_limited_classification(first.scope_role)
    evidence_status = (
        primary.evidence_status if primary is not None else EvidenceStatus.UNAVAILABLE
    )
    reasons: list[str] = []

    if scope_limited is not None:
        classification, reason = scope_limited
        reasons.append(reason)
    else:
        missing_evidence = False
        if primary is None or primary.evidence_status is not EvidenceStatus.SUFFICIENT:
            reasons.append("PRIMARY_PERFORMANCE_INSUFFICIENT")
            missing_evidence = True
        if stress is None or stress.evidence_status is not EvidenceStatus.SUFFICIENT:
            reasons.append("STRESS_PERFORMANCE_INSUFFICIENT")
            missing_evidence = True
        if len(sufficient_overall) < policy.minimum_sufficient_pairwise_comparisons:
            reasons.append("PAIRWISE_EVIDENCE_INSUFFICIENT")
            missing_evidence = True
        if missing_evidence:
            classification = ModelResearchClass.INSUFFICIENT_EVIDENCE
            evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE
        else:
            evidence_status = EvidenceStatus.SUFFICIENT
            primary_excess = float(primary.total_net_excess_return)
            stress_excess = float(stress.total_net_excess_return)
            primary_sharpe = primary.sharpe
            primary_mdd = float(primary.mdd)
            core_metrics_pass = (
                primary_excess > policy.minimum_overall_net_excess_return
                and stress_excess > policy.minimum_stress_net_excess_return
                and primary_sharpe is not None
                and primary_sharpe >= policy.minimum_overall_sharpe
                and primary_mdd >= policy.minimum_mdd
            )
            marginal_pass = (
                maximum_marginal is not None
                and maximum_marginal > policy.minimum_marginal_contribution
            )
            high_redundancy_without_gain = (
                high_redundancy_count > 0 and not marginal_pass
            )
            specialist_pass = (
                strongest_regime is not None
                and float(strongest_regime.total_net_excess_return)
                > policy.minimum_specialist_net_excess_return
                and strongest_regime.sharpe is not None
                and strongest_regime.sharpe >= policy.minimum_specialist_sharpe
                and regime_marginal is not None
                and regime_marginal > policy.minimum_marginal_contribution
            )
            retire_evidence = (
                primary_excess <= policy.minimum_overall_net_excess_return
                and stress_excess <= policy.minimum_stress_net_excess_return
                and (primary_sharpe is None or primary_sharpe <= 0.0)
                and not specialist_pass
                and (maximum_marginal is None or maximum_marginal <= policy.minimum_marginal_contribution)
            )
            if core_metrics_pass and marginal_pass and not high_redundancy_without_gain:
                classification = ModelResearchClass.CORE
                reasons.extend(
                    (
                        "OVERALL_PERFORMANCE_GATE_PASS",
                        "STRESS_COST_GATE_PASS",
                        "MARGINAL_CONTRIBUTION_GATE_PASS",
                    )
                )
            elif specialist_pass:
                classification = ModelResearchClass.REGIME_SPECIALIST
                reasons.append("REGIME_SPECIALIST_GATE_PASS")
            elif retire_evidence:
                classification = ModelResearchClass.RETIRE_CANDIDATE
                reasons.append("CONSISTENT_NEGATIVE_EVIDENCE")
            else:
                classification = ModelResearchClass.CHALLENGER
                reasons.append("RESEARCH_CHALLENGER_PENDING_MORE_EVIDENCE")
                if high_redundancy_without_gain:
                    reasons.append("HIGH_REDUNDANCY_WITHOUT_MARGINAL_GAIN")

    return ModelClassificationCandidate(
        model_code=model_code,
        scope_role=first.scope_role,
        ranking_eligible=first.ranking_eligible,
        proposed_classification=classification,
        evidence_status=evidence_status,
        operationally_actionable=False,
        primary_cost_bps=policy.primary_cost_bps,
        stress_cost_bps=policy.stress_cost_bps,
        primary_total_net_excess_return=(
            primary.total_net_excess_return if primary is not None else None
        ),
        stress_total_net_excess_return=(
            stress.total_net_excess_return if stress is not None else None
        ),
        primary_sharpe=primary.sharpe if primary is not None else None,
        primary_mdd=primary.mdd if primary is not None else None,
        strongest_regime_structure=(
            strongest_regime.market_structure if strongest_regime is not None else None
        ),
        strongest_regime_stage=(
            strongest_regime.market_stage if strongest_regime is not None else None
        ),
        strongest_regime_total_net_excess_return=(
            strongest_regime.total_net_excess_return
            if strongest_regime is not None
            else None
        ),
        strongest_regime_sharpe=(
            strongest_regime.sharpe if strongest_regime is not None else None
        ),
        sufficient_overall_pairwise_count=len(sufficient_overall),
        high_redundancy_pair_count=high_redundancy_count,
        positive_overall_marginal_count=positive_marginal_count,
        maximum_overall_marginal_contribution=maximum_marginal,
        strongest_regime_marginal_contribution=regime_marginal,
        reason_codes=tuple(reasons),
    )


def classify_model_research_candidates(
    performance_result: PerformanceSummaryResult,
    pairwise_result: PairwiseComparisonResult,
    *,
    policy: ClassificationPolicy | None = None,
) -> ClassificationResult:
    applied_policy = policy or ClassificationPolicy()
    if performance_result.input_cost_result_hash != pairwise_result.input_cost_result_hash:
        raise ContractValidationError(
            "performance and pairwise results must share the same cost input hash"
        )
    indexed = _index_performance(performance_result)
    _validate_pairwise_against_performance(pairwise_result.comparisons, indexed)
    model_codes = sorted({key[0] for key in indexed})
    summaries_by_model = {
        model_code: [
            summary for key, summary in indexed.items() if key[0] == model_code
        ]
        for model_code in model_codes
    }
    candidates = tuple(
        _candidate_for_model(
            model_code,
            summaries_by_model[model_code],
            list(pairwise_result.comparisons),
            policy=applied_policy,
        )
        for model_code in model_codes
    )
    evaluation_candidates = [
        candidate
        for candidate in candidates
        if candidate.scope_role is EvaluationScopeRole.EVALUATION_CANDIDATE
    ]
    research_gate_ready = (
        performance_result.summary_ready
        and pairwise_result.comparison_ready
        and bool(evaluation_candidates)
        and all(
            candidate.proposed_classification
            is not ModelResearchClass.INSUFFICIENT_EVIDENCE
            for candidate in evaluation_candidates
        )
    )
    policy_hash = applied_policy.policy_hash()
    result_hash = canonical_sha256(
        {
            "input_performance_result_hash": performance_result.result_hash,
            "input_pairwise_result_hash": pairwise_result.result_hash,
            "input_cost_result_hash": performance_result.input_cost_result_hash,
            "policy_hash": policy_hash,
            "candidates": [asdict(candidate) for candidate in candidates],
            "operational_authorization": False,
        }
    )
    return ClassificationResult(
        candidates=candidates,
        input_performance_result_hash=performance_result.result_hash,
        input_pairwise_result_hash=pairwise_result.result_hash,
        input_cost_result_hash=performance_result.input_cost_result_hash,
        input_performance_ready=performance_result.summary_ready,
        input_pairwise_ready=pairwise_result.comparison_ready,
        research_gate_ready=research_gate_ready,
        operational_authorization=False,
        policy_version=applied_policy.version,
        policy_hash=policy_hash,
        result_hash=result_hash,
    )
