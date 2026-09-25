from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from itertools import combinations

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketStage,
    MarketStructure,
    canonical_sha256,
)
from src.quant2.evaluation.costs import (
    CostAdjustedObservation,
    CostSensitivityResult,
)
from src.quant2.evaluation.input_connector import EvaluationScopeRole
from src.quant2.evaluation.performance import AggregationScope, EvidenceStatus

PAIRWISE_POLICY_VERSION = "quant2.pairwise_comparison.v1"


class RedundancyLevel(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True)
class PairwiseComparisonPolicy:
    minimum_aligned_observations: int = 12
    high_correlation_threshold: float = 0.80
    high_overlap_threshold: float = 0.80
    moderate_correlation_threshold: float = 0.50
    moderate_overlap_threshold: float = 0.60
    version: str = PAIRWISE_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.minimum_aligned_observations < 2:
            raise ContractValidationError("minimum_aligned_observations must be at least 2")
        thresholds = (
            self.high_correlation_threshold,
            self.high_overlap_threshold,
            self.moderate_correlation_threshold,
            self.moderate_overlap_threshold,
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in thresholds):
            raise ContractValidationError("pairwise thresholds must be finite and between 0 and 1")
        if self.high_correlation_threshold < self.moderate_correlation_threshold:
            raise ContractValidationError("high correlation threshold cannot be below moderate")
        if self.high_overlap_threshold < self.moderate_overlap_threshold:
            raise ContractValidationError("high overlap threshold cannot be below moderate")
        if not self.version.strip():
            raise ContractValidationError("pairwise policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class PairwiseModelComparison:
    model_a: str
    model_b: str
    model_a_scope_role: EvaluationScopeRole
    model_b_scope_role: EvaluationScopeRole
    ranking_eligible: bool
    cost_bps: int
    aggregation_scope: AggregationScope
    market_structure: MarketStructure | None
    market_stage: MarketStage | None
    candidate_period_count: int
    aligned_period_count: int
    observation_count: int
    unavailable_count: int
    benchmark_mismatch_count: int
    availability_ratio: float
    start_date: date | None
    end_date: date | None
    benchmark_code: str | None
    net_return_correlation: float | None
    net_excess_return_correlation: float | None
    directional_agreement_ratio: float | None
    return_overlap_score: float | None
    redundancy_level: RedundancyLevel
    benchmark_total_return: float | None
    model_a_total_net_return: float | None
    model_b_total_net_return: float | None
    equal_weight_total_net_return: float | None
    model_a_total_net_excess_return: float | None
    model_b_total_net_excess_return: float | None
    equal_weight_total_net_excess_return: float | None
    model_a_marginal_contribution_to_b: float | None
    model_b_marginal_contribution_to_a: float | None
    model_a_mdd: float | None
    model_b_mdd: float | None
    equal_weight_mdd: float | None
    equal_weight_mdd_improvement_vs_a: float | None
    equal_weight_mdd_improvement_vs_b: float | None
    evidence_status: EvidenceStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PairwiseComparisonResult:
    comparisons: tuple[PairwiseModelComparison, ...]
    input_cost_result_hash: str
    input_evaluation_ready: bool
    comparison_ready: bool
    policy_version: str
    policy_hash: str
    result_hash: str


@dataclass(frozen=True)
class _PairPeriod:
    effective_trade_date: date
    return_period_end_date: date
    market_structure: MarketStructure
    market_stage: MarketStage
    left: CostAdjustedObservation | None
    right: CostAdjustedObservation | None


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 12)


def _compound(returns: list[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def _mdd(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity / peak - 1.0)
    return maximum_drawdown


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_centered)
        * sum(value * value for value in right_centered)
    )
    if math.isclose(denominator, 0.0, abs_tol=1e-15):
        return None
    return sum(a * b for a, b in zip(left_centered, right_centered)) / denominator


def _direction(value: float) -> int:
    if math.isclose(value, 0.0, abs_tol=1e-15):
        return 0
    return 1 if value > 0.0 else -1


def _return_overlap(left: list[float], right: list[float]) -> float:
    denominator = sum(abs(a) + abs(b) for a, b in zip(left, right))
    if math.isclose(denominator, 0.0, abs_tol=1e-15):
        return 1.0
    return max(0.0, min(1.0, 1.0 - sum(abs(a - b) for a, b in zip(left, right)) / denominator))


def _redundancy_level(
    correlation: float | None,
    overlap: float,
    policy: PairwiseComparisonPolicy,
) -> RedundancyLevel:
    if correlation is None:
        return RedundancyLevel.UNDETERMINED
    if (
        correlation >= policy.high_correlation_threshold
        and overlap >= policy.high_overlap_threshold
    ):
        return RedundancyLevel.HIGH
    if (
        correlation >= policy.moderate_correlation_threshold
        and overlap >= policy.moderate_overlap_threshold
    ):
        return RedundancyLevel.MODERATE
    return RedundancyLevel.LOW


def _validate_observations(
    observations: tuple[CostAdjustedObservation, ...],
) -> dict[tuple[str, int, date, date], CostAdjustedObservation]:
    indexed: dict[tuple[str, int, date, date], CostAdjustedObservation] = {}
    roles_by_model: dict[str, set[EvaluationScopeRole]] = {}
    ranking_by_model: dict[str, set[bool]] = {}
    periods_by_model_cost: dict[tuple[str, int], list[tuple[date, date]]] = {}
    for row in observations:
        key = (
            row.model_code,
            row.cost_bps,
            row.effective_trade_date,
            row.return_period_end_date,
        )
        if key in indexed:
            raise ContractValidationError("duplicate pairwise observation period")
        indexed[key] = row
        roles_by_model.setdefault(row.model_code, set()).add(row.scope_role)
        ranking_by_model.setdefault(row.model_code, set()).add(row.ranking_eligible)
        periods_by_model_cost.setdefault((row.model_code, row.cost_bps), []).append(
            (row.effective_trade_date, row.return_period_end_date)
        )
    if any(len(roles) != 1 for roles in roles_by_model.values()):
        raise ContractValidationError("a model cannot mix scope roles")
    if any(len(values) != 1 for values in ranking_by_model.values()):
        raise ContractValidationError("a model cannot mix ranking eligibility")
    for key, periods in periods_by_model_cost.items():
        ordered = sorted(periods)
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] < previous[1]:
                raise ContractValidationError(
                    f"overlapping return periods for {key[0]} at {key[1]}bp"
                )
    return indexed


def _pair_periods(
    indexed: dict[tuple[str, int, date, date], CostAdjustedObservation],
    *,
    model_a: str,
    model_b: str,
    cost_bps: int,
) -> list[_PairPeriod]:
    periods = sorted(
        {
            (start, end)
            for model, cost, start, end in indexed
            if cost == cost_bps and model in {model_a, model_b}
        }
    )
    result: list[_PairPeriod] = []
    for start, end in periods:
        left = indexed.get((model_a, cost_bps, start, end))
        right = indexed.get((model_b, cost_bps, start, end))
        contexts = [row for row in (left, right) if row is not None]
        context = contexts[0]
        if len(contexts) == 2:
            if (
                left.decision_date != right.decision_date
                or left.market_structure is not right.market_structure
                or left.market_stage is not right.market_stage
                or left.market_payload_hash != right.market_payload_hash
            ):
                raise ContractValidationError("paired periods must share the same market context")
        result.append(
            _PairPeriod(
                effective_trade_date=start,
                return_period_end_date=end,
                market_structure=context.market_structure,
                market_stage=context.market_stage,
                left=left,
                right=right,
            )
        )
    return result


def _summarize_pair(
    periods: list[_PairPeriod],
    *,
    model_a: str,
    model_b: str,
    model_a_role: EvaluationScopeRole,
    model_b_role: EvaluationScopeRole,
    model_a_ranking_eligible: bool,
    model_b_ranking_eligible: bool,
    cost_bps: int,
    aggregation_scope: AggregationScope,
    market_structure: MarketStructure | None,
    market_stage: MarketStage | None,
    policy: PairwiseComparisonPolicy,
) -> PairwiseModelComparison:
    aligned = [period for period in periods if period.left is not None and period.right is not None]
    benchmark_mismatch_count = sum(
        1
        for period in aligned
        if period.left.available
        and period.right.available
        and period.left.benchmark_code != period.right.benchmark_code
    )
    usable = [
        period
        for period in aligned
        if period.left.available
        and period.right.available
        and period.left.benchmark_code == period.right.benchmark_code
    ]
    candidate_count = len(periods)
    unavailable_count = candidate_count - len(usable)
    ranking_eligible = model_a_ranking_eligible and model_b_ranking_eligible
    if not usable:
        reasons = ["NO_COMPARABLE_OBSERVATIONS"]
        if benchmark_mismatch_count:
            reasons.append("BENCHMARK_MISMATCH")
        if unavailable_count:
            reasons.append("INCOMPLETE_PAIR_COVERAGE")
        return PairwiseModelComparison(
            model_a=model_a,
            model_b=model_b,
            model_a_scope_role=model_a_role,
            model_b_scope_role=model_b_role,
            ranking_eligible=ranking_eligible,
            cost_bps=cost_bps,
            aggregation_scope=aggregation_scope,
            market_structure=market_structure,
            market_stage=market_stage,
            candidate_period_count=candidate_count,
            aligned_period_count=len(aligned),
            observation_count=0,
            unavailable_count=unavailable_count,
            benchmark_mismatch_count=benchmark_mismatch_count,
            availability_ratio=0.0,
            start_date=None,
            end_date=None,
            benchmark_code=None,
            net_return_correlation=None,
            net_excess_return_correlation=None,
            directional_agreement_ratio=None,
            return_overlap_score=None,
            redundancy_level=RedundancyLevel.UNDETERMINED,
            benchmark_total_return=None,
            model_a_total_net_return=None,
            model_b_total_net_return=None,
            equal_weight_total_net_return=None,
            model_a_total_net_excess_return=None,
            model_b_total_net_excess_return=None,
            equal_weight_total_net_excess_return=None,
            model_a_marginal_contribution_to_b=None,
            model_b_marginal_contribution_to_a=None,
            model_a_mdd=None,
            model_b_mdd=None,
            equal_weight_mdd=None,
            equal_weight_mdd_improvement_vs_a=None,
            equal_weight_mdd_improvement_vs_b=None,
            evidence_status=EvidenceStatus.UNAVAILABLE,
            reason_codes=tuple(reasons),
        )

    benchmark_codes = {period.left.benchmark_code for period in usable}
    if len(benchmark_codes) != 1:
        raise ContractValidationError("a pairwise comparison cannot mix benchmark codes")
    left_returns = [float(period.left.net_return) for period in usable]
    right_returns = [float(period.right.net_return) for period in usable]
    left_excess = [float(period.left.net_excess_return) for period in usable]
    right_excess = [float(period.right.net_excess_return) for period in usable]
    benchmark_returns = [float(period.left.benchmark_return) for period in usable]
    equal_weight_returns = [(left + right) / 2.0 for left, right in zip(left_returns, right_returns)]
    left_total = _compound(left_returns)
    right_total = _compound(right_returns)
    blend_total = _compound(equal_weight_returns)
    benchmark_total = _compound(benchmark_returns)
    left_mdd = _mdd(left_returns)
    right_mdd = _mdd(right_returns)
    blend_mdd = _mdd(equal_weight_returns)
    correlation = _correlation(left_returns, right_returns)
    excess_correlation = _correlation(left_excess, right_excess)
    overlap = _return_overlap(left_returns, right_returns)
    reasons: list[str] = []
    if len(usable) < policy.minimum_aligned_observations:
        reasons.append("INSUFFICIENT_OBSERVATIONS")
    if unavailable_count:
        reasons.append("INCOMPLETE_PAIR_COVERAGE")
    if benchmark_mismatch_count:
        reasons.append("BENCHMARK_MISMATCH")
    if correlation is None:
        reasons.append("ZERO_VARIANCE_CORRELATION")
    evidence_status = (
        EvidenceStatus.SUFFICIENT
        if len(usable) >= policy.minimum_aligned_observations
        and unavailable_count == 0
        and correlation is not None
        else EvidenceStatus.INSUFFICIENT_EVIDENCE
    )
    return PairwiseModelComparison(
        model_a=model_a,
        model_b=model_b,
        model_a_scope_role=model_a_role,
        model_b_scope_role=model_b_role,
        ranking_eligible=ranking_eligible,
        cost_bps=cost_bps,
        aggregation_scope=aggregation_scope,
        market_structure=market_structure,
        market_stage=market_stage,
        candidate_period_count=candidate_count,
        aligned_period_count=len(aligned),
        observation_count=len(usable),
        unavailable_count=unavailable_count,
        benchmark_mismatch_count=benchmark_mismatch_count,
        availability_ratio=_rounded(len(usable) / candidate_count),
        start_date=usable[0].effective_trade_date,
        end_date=usable[-1].return_period_end_date,
        benchmark_code=next(iter(benchmark_codes)),
        net_return_correlation=_rounded(correlation),
        net_excess_return_correlation=_rounded(excess_correlation),
        directional_agreement_ratio=_rounded(
            statistics.fmean(
                _direction(left) == _direction(right)
                for left, right in zip(left_returns, right_returns)
            )
        ),
        return_overlap_score=_rounded(overlap),
        redundancy_level=_redundancy_level(correlation, overlap, policy),
        benchmark_total_return=_rounded(benchmark_total),
        model_a_total_net_return=_rounded(left_total),
        model_b_total_net_return=_rounded(right_total),
        equal_weight_total_net_return=_rounded(blend_total),
        model_a_total_net_excess_return=_rounded(left_total - benchmark_total),
        model_b_total_net_excess_return=_rounded(right_total - benchmark_total),
        equal_weight_total_net_excess_return=_rounded(blend_total - benchmark_total),
        model_a_marginal_contribution_to_b=_rounded(
            (blend_total - benchmark_total) - (right_total - benchmark_total)
        ),
        model_b_marginal_contribution_to_a=_rounded(
            (blend_total - benchmark_total) - (left_total - benchmark_total)
        ),
        model_a_mdd=_rounded(left_mdd),
        model_b_mdd=_rounded(right_mdd),
        equal_weight_mdd=_rounded(blend_mdd),
        equal_weight_mdd_improvement_vs_a=_rounded(blend_mdd - left_mdd),
        equal_weight_mdd_improvement_vs_b=_rounded(blend_mdd - right_mdd),
        evidence_status=evidence_status,
        reason_codes=tuple(reasons),
    )


def evaluate_pairwise_models(
    cost_result: CostSensitivityResult,
    *,
    policy: PairwiseComparisonPolicy | None = None,
) -> PairwiseComparisonResult:
    applied_policy = policy or PairwiseComparisonPolicy()
    indexed = _validate_observations(cost_result.observations)
    model_codes = sorted({row.model_code for row in cost_result.observations})
    costs = sorted({row.cost_bps for row in cost_result.observations})
    roles = {
        model_code: next(
            row.scope_role for row in cost_result.observations if row.model_code == model_code
        )
        for model_code in model_codes
    }
    ranking_eligibility = {
        model_code: next(
            row.ranking_eligible for row in cost_result.observations if row.model_code == model_code
        )
        for model_code in model_codes
    }
    comparisons: list[PairwiseModelComparison] = []
    for model_a, model_b in combinations(model_codes, 2):
        for cost_bps in costs:
            periods = _pair_periods(
                indexed,
                model_a=model_a,
                model_b=model_b,
                cost_bps=cost_bps,
            )
            if not periods:
                continue
            grouping_keys = {
                (AggregationScope.OVERALL, None, None),
                *{
                    (AggregationScope.MARKET_STRUCTURE, period.market_structure, None)
                    for period in periods
                },
                *{
                    (
                        AggregationScope.MARKET_STAGE,
                        period.market_structure,
                        period.market_stage,
                    )
                    for period in periods
                },
            }
            for aggregation_scope, structure, stage in sorted(
                grouping_keys,
                key=lambda item: (
                    item[0].value,
                    item[1].value if item[1] else "",
                    item[2].value if item[2] else "",
                ),
            ):
                selected = [
                    period
                    for period in periods
                    if (
                        aggregation_scope is AggregationScope.OVERALL
                        or (
                            period.market_structure is structure
                            and (
                                aggregation_scope is AggregationScope.MARKET_STRUCTURE
                                or period.market_stage is stage
                            )
                        )
                    )
                ]
                comparisons.append(
                    _summarize_pair(
                        selected,
                        model_a=model_a,
                        model_b=model_b,
                        model_a_role=roles[model_a],
                        model_b_role=roles[model_b],
                        model_a_ranking_eligible=ranking_eligibility[model_a],
                        model_b_ranking_eligible=ranking_eligibility[model_b],
                        cost_bps=cost_bps,
                        aggregation_scope=aggregation_scope,
                        market_structure=structure,
                        market_stage=stage,
                        policy=applied_policy,
                    )
                )
    sorted_comparisons = tuple(
        sorted(
            comparisons,
            key=lambda item: (
                item.model_a,
                item.model_b,
                item.cost_bps,
                item.aggregation_scope.value,
                item.market_structure.value if item.market_structure else "",
                item.market_stage.value if item.market_stage else "",
            ),
        )
    )
    eligible_overall = [
        item
        for item in sorted_comparisons
        if item.aggregation_scope is AggregationScope.OVERALL and item.ranking_eligible
    ]
    comparison_ready = (
        cost_result.evaluation_ready
        and bool(eligible_overall)
        and all(item.evidence_status is EvidenceStatus.SUFFICIENT for item in eligible_overall)
    )
    policy_hash = applied_policy.policy_hash()
    result_hash = canonical_sha256(
        {
            "input_cost_result_hash": cost_result.result_hash,
            "policy_hash": policy_hash,
            "comparisons": [asdict(item) for item in sorted_comparisons],
        }
    )
    return PairwiseComparisonResult(
        comparisons=sorted_comparisons,
        input_cost_result_hash=cost_result.result_hash,
        input_evaluation_ready=cost_result.evaluation_ready,
        comparison_ready=comparison_ready,
        policy_version=applied_policy.version,
        policy_hash=policy_hash,
        result_hash=result_hash,
    )
