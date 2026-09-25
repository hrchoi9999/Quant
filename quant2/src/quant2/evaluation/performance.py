from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum

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

PERFORMANCE_POLICY_VERSION = "quant2.performance_summary.v1"


class AggregationScope(str, Enum):
    OVERALL = "OVERALL"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    MARKET_STAGE = "MARKET_STAGE"


class EvidenceStatus(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class PerformanceSummaryPolicy:
    periods_per_year: int = 12
    minimum_observations: int = 12
    annual_risk_free_rate: float = 0.0
    version: str = PERFORMANCE_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.periods_per_year <= 0:
            raise ContractValidationError("periods_per_year must be positive")
        if self.minimum_observations < 2:
            raise ContractValidationError("minimum_observations must be at least 2")
        if not math.isfinite(self.annual_risk_free_rate) or self.annual_risk_free_rate <= -1.0:
            raise ContractValidationError("annual_risk_free_rate must be finite and above -100%")
        if not self.version.strip():
            raise ContractValidationError("performance policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ModelPerformanceSummary:
    model_code: str
    scope_role: EvaluationScopeRole
    ranking_eligible: bool
    cost_bps: int
    aggregation_scope: AggregationScope
    market_structure: MarketStructure | None
    market_stage: MarketStage | None
    cagr_interpretation: str
    observation_count: int
    unavailable_count: int
    availability_ratio: float
    start_date: date | None
    end_date: date | None
    total_gross_return: float | None
    total_net_return: float | None
    total_benchmark_return: float | None
    total_net_excess_return: float | None
    cagr: float | None
    annualized_volatility: float | None
    sharpe: float | None
    sortino: float | None
    mdd: float | None
    average_turnover_one_way: float | None
    total_turnover_one_way: float | None
    average_coverage_ratio: float | None
    minimum_coverage_ratio: float | None
    evidence_status: EvidenceStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PerformanceSummaryResult:
    summaries: tuple[ModelPerformanceSummary, ...]
    input_cost_result_hash: str
    input_evaluation_ready: bool
    summary_ready: bool
    policy_version: str
    policy_hash: str
    result_hash: str


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
        drawdown = equity / peak - 1.0
        maximum_drawdown = min(maximum_drawdown, drawdown)
    return maximum_drawdown


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 12)


def _validate_non_overlapping(observations: tuple[CostAdjustedObservation, ...]) -> None:
    grouped: dict[tuple[str, int], list[CostAdjustedObservation]] = {}
    for observation in observations:
        grouped.setdefault((observation.model_code, observation.cost_bps), []).append(observation)
    for key, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: item.effective_trade_date)
        for previous, current in zip(ordered, ordered[1:]):
            if current.effective_trade_date < previous.return_period_end_date:
                raise ContractValidationError(
                    f"overlapping return periods for {key[0]} at {key[1]}bp"
                )


def _summarize(
    rows: list[CostAdjustedObservation],
    *,
    aggregation_scope: AggregationScope,
    market_structure: MarketStructure | None,
    market_stage: MarketStage | None,
    policy: PerformanceSummaryPolicy,
) -> ModelPerformanceSummary:
    ordered = sorted(rows, key=lambda item: item.effective_trade_date)
    first = ordered[0]
    benchmark_codes = {row.benchmark_code for row in ordered}
    if len(benchmark_codes) != 1:
        raise ContractValidationError("a performance summary cannot mix benchmark codes")
    if any(row.scope_role is not first.scope_role for row in ordered):
        raise ContractValidationError("a performance summary cannot mix scope roles")
    available = [row for row in ordered if row.available]
    unavailable_count = len(ordered) - len(available)
    availability_ratio = len(available) / len(ordered)
    interpretation = (
        "PORTFOLIO_TIMELINE"
        if aggregation_scope is AggregationScope.OVERALL
        else "CONDITIONAL_SUBSEQUENCE"
    )
    if not available:
        return ModelPerformanceSummary(
            model_code=first.model_code,
            scope_role=first.scope_role,
            ranking_eligible=first.ranking_eligible,
            cost_bps=first.cost_bps,
            aggregation_scope=aggregation_scope,
            market_structure=market_structure,
            market_stage=market_stage,
            cagr_interpretation=interpretation,
            observation_count=0,
            unavailable_count=unavailable_count,
            availability_ratio=0.0,
            start_date=None,
            end_date=None,
            total_gross_return=None,
            total_net_return=None,
            total_benchmark_return=None,
            total_net_excess_return=None,
            cagr=None,
            annualized_volatility=None,
            sharpe=None,
            sortino=None,
            mdd=None,
            average_turnover_one_way=None,
            total_turnover_one_way=None,
            average_coverage_ratio=None,
            minimum_coverage_ratio=None,
            evidence_status=EvidenceStatus.UNAVAILABLE,
            reason_codes=("INPUT_UNAVAILABLE",),
        )

    gross_returns = [float(row.gross_return) for row in available]
    net_returns = [float(row.net_return) for row in available]
    benchmark_returns = [float(row.benchmark_return) for row in available]
    turnovers = [float(row.turnover_one_way) for row in available]
    coverages = [row.coverage_ratio for row in available]
    total_gross_return = _compound(gross_returns)
    total_net_return = _compound(net_returns)
    total_benchmark_return = _compound(benchmark_returns)
    if total_net_return < -1.0:
        raise ContractValidationError("compounded net return cannot be below -100%")
    cagr = (
        -1.0
        if math.isclose(total_net_return, -1.0, abs_tol=1e-12)
        else (1.0 + total_net_return) ** (policy.periods_per_year / len(net_returns)) - 1.0
    )
    volatility = (
        statistics.stdev(net_returns) * math.sqrt(policy.periods_per_year)
        if len(net_returns) >= 2
        else None
    )
    risk_free_per_period = (1.0 + policy.annual_risk_free_rate) ** (
        1.0 / policy.periods_per_year
    ) - 1.0
    excess_over_risk_free = [value - risk_free_per_period for value in net_returns]
    sharpe = None
    if len(net_returns) >= 2:
        period_std = statistics.stdev(excess_over_risk_free)
        if not math.isclose(period_std, 0.0, abs_tol=1e-12):
            sharpe = (
                statistics.fmean(excess_over_risk_free)
                / period_std
                * math.sqrt(policy.periods_per_year)
            )
    downside = [min(value, 0.0) for value in excess_over_risk_free]
    downside_deviation = math.sqrt(statistics.fmean(value * value for value in downside))
    sortino = None
    if not math.isclose(downside_deviation, 0.0, abs_tol=1e-12):
        sortino = (
            statistics.fmean(excess_over_risk_free)
            / downside_deviation
            * math.sqrt(policy.periods_per_year)
        )
    evidence_status = (
        EvidenceStatus.SUFFICIENT
        if len(available) >= policy.minimum_observations and unavailable_count == 0
        else EvidenceStatus.INSUFFICIENT_EVIDENCE
    )
    reasons: list[str] = []
    if len(available) < policy.minimum_observations:
        reasons.append("INSUFFICIENT_OBSERVATIONS")
    if unavailable_count:
        reasons.append("INCOMPLETE_COVERAGE")
    return ModelPerformanceSummary(
        model_code=first.model_code,
        scope_role=first.scope_role,
        ranking_eligible=first.ranking_eligible,
        cost_bps=first.cost_bps,
        aggregation_scope=aggregation_scope,
        market_structure=market_structure,
        market_stage=market_stage,
        cagr_interpretation=interpretation,
        observation_count=len(available),
        unavailable_count=unavailable_count,
        availability_ratio=_rounded(availability_ratio),
        start_date=available[0].effective_trade_date,
        end_date=available[-1].return_period_end_date,
        total_gross_return=_rounded(total_gross_return),
        total_net_return=_rounded(total_net_return),
        total_benchmark_return=_rounded(total_benchmark_return),
        total_net_excess_return=_rounded(total_net_return - total_benchmark_return),
        cagr=_rounded(cagr),
        annualized_volatility=_rounded(volatility),
        sharpe=_rounded(sharpe),
        sortino=_rounded(sortino),
        mdd=_rounded(_mdd(net_returns)),
        average_turnover_one_way=_rounded(statistics.fmean(turnovers)),
        total_turnover_one_way=_rounded(sum(turnovers)),
        average_coverage_ratio=_rounded(statistics.fmean(coverages)),
        minimum_coverage_ratio=_rounded(min(coverages)),
        evidence_status=evidence_status,
        reason_codes=tuple(reasons),
    )


def summarize_performance(
    cost_result: CostSensitivityResult,
    *,
    policy: PerformanceSummaryPolicy | None = None,
) -> PerformanceSummaryResult:
    applied_policy = policy or PerformanceSummaryPolicy()
    _validate_non_overlapping(cost_result.observations)
    grouped: dict[
        tuple[str, int, AggregationScope, MarketStructure | None, MarketStage | None],
        list[CostAdjustedObservation],
    ] = {}
    for row in cost_result.observations:
        keys = (
            (AggregationScope.OVERALL, None, None),
            (AggregationScope.MARKET_STRUCTURE, row.market_structure, None),
            (AggregationScope.MARKET_STAGE, row.market_structure, row.market_stage),
        )
        for aggregation_scope, structure, stage in keys:
            key = (row.model_code, row.cost_bps, aggregation_scope, structure, stage)
            grouped.setdefault(key, []).append(row)

    summaries = tuple(
        _summarize(
            rows,
            aggregation_scope=key[2],
            market_structure=key[3],
            market_stage=key[4],
            policy=applied_policy,
        )
        for key, rows in sorted(
            grouped.items(),
            key=lambda item: (
                item[0][0],
                item[0][1],
                item[0][2].value,
                item[0][3].value if item[0][3] else "",
                item[0][4].value if item[0][4] else "",
            ),
        )
    )
    overall_summaries = [
        summary
        for summary in summaries
        if summary.aggregation_scope is AggregationScope.OVERALL
    ]
    summary_ready = (
        cost_result.evaluation_ready
        and bool(overall_summaries)
        and all(
            summary.evidence_status is EvidenceStatus.SUFFICIENT
            for summary in overall_summaries
        )
    )
    policy_hash = applied_policy.policy_hash()
    result_hash = canonical_sha256(
        {
            "input_cost_result_hash": cost_result.result_hash,
            "policy_hash": policy_hash,
            "summaries": [asdict(summary) for summary in summaries],
        }
    )
    return PerformanceSummaryResult(
        summaries=summaries,
        input_cost_result_hash=cost_result.result_hash,
        input_evaluation_ready=cost_result.evaluation_ready,
        summary_ready=summary_ready,
        policy_version=applied_policy.version,
        policy_hash=policy_hash,
        result_hash=result_hash,
    )
