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
from src.quant2.evaluation.performance import EvidenceStatus

DIAGNOSTICS_POLICY_VERSION = "quant2.failure_concentration_diagnostics.v1"


class DiagnosticFlag(str, Enum):
    TOP_POSITIVE_PERIOD_CONCENTRATION = "TOP_POSITIVE_PERIOD_CONCENTRATION"
    POSITIVE_CONTRIBUTION_HHI_HIGH = "POSITIVE_CONTRIBUTION_HHI_HIGH"
    NEGATIVE_CONTRIBUTION_HHI_HIGH = "NEGATIVE_CONTRIBUTION_HHI_HIGH"
    DOMINANT_STAGE_CONCENTRATION = "DOMINANT_STAGE_CONCENTRATION"
    HIGH_FAILURE_PERIOD_RATIO = "HIGH_FAILURE_PERIOD_RATIO"
    LONG_FAILURE_STREAK = "LONG_FAILURE_STREAK"
    CROSS_MODEL_CONTRIBUTION_CONCENTRATION = "CROSS_MODEL_CONTRIBUTION_CONCENTRATION"


@dataclass(frozen=True)
class DiagnosticsPolicy:
    minimum_observations: int = 12
    minimum_cross_model_count: int = 2
    top_period_count: int = 3
    rolling_window_sizes: tuple[int, ...] = (3, 6)
    top_positive_period_share_threshold: float = 0.60
    contribution_hhi_threshold: float = 0.25
    dominant_stage_share_threshold: float = 0.70
    failure_period_ratio_threshold: float = 0.50
    longest_failure_streak_threshold: int = 3
    cross_model_top_share_threshold: float = 0.60
    cross_model_hhi_threshold: float = 0.50
    version: str = DIAGNOSTICS_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.minimum_observations < 2:
            raise ContractValidationError("minimum_observations must be at least 2")
        if self.minimum_cross_model_count < 2:
            raise ContractValidationError("minimum_cross_model_count must be at least 2")
        if self.top_period_count < 1:
            raise ContractValidationError("top_period_count must be positive")
        if (
            not self.rolling_window_sizes
            or tuple(sorted(set(self.rolling_window_sizes))) != self.rolling_window_sizes
            or any(value < 2 for value in self.rolling_window_sizes)
        ):
            raise ContractValidationError(
                "rolling_window_sizes must be sorted, unique, and at least 2"
            )
        thresholds = (
            self.top_positive_period_share_threshold,
            self.contribution_hhi_threshold,
            self.dominant_stage_share_threshold,
            self.failure_period_ratio_threshold,
            self.cross_model_top_share_threshold,
            self.cross_model_hhi_threshold,
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in thresholds):
            raise ContractValidationError("diagnostic ratio thresholds must be between 0 and 1")
        if self.longest_failure_streak_threshold < 1:
            raise ContractValidationError("longest_failure_streak_threshold must be positive")
        if not self.version.strip():
            raise ContractValidationError("diagnostics policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class FailureEpisode:
    start_date: date
    end_date: date
    failure_period_count: int
    compounded_net_return: float
    compounded_benchmark_return: float
    compounded_net_excess_return: float
    worst_period_net_excess_return: float
    market_structures: tuple[MarketStructure, ...]
    market_stages: tuple[MarketStage, ...]


@dataclass(frozen=True)
class RollingFailureWindow:
    window_size: int
    start_date: date
    end_date: date
    compounded_net_return: float
    compounded_benchmark_return: float
    compounded_net_excess_return: float


@dataclass(frozen=True)
class ModelFailureConcentrationDiagnostic:
    model_code: str
    scope_role: EvaluationScopeRole
    ranking_eligible: bool
    cost_bps: int
    candidate_period_count: int
    observation_count: int
    unavailable_count: int
    availability_ratio: float
    start_date: date | None
    end_date: date | None
    benchmark_code: str | None
    positive_excess_period_count: int
    failure_period_count: int
    failure_period_ratio: float | None
    failure_episode_count: int
    longest_failure_streak: int
    failure_episodes: tuple[FailureEpisode, ...]
    worst_rolling_windows: tuple[RollingFailureWindow, ...]
    top_positive_period_share: float | None
    positive_contribution_hhi: float | None
    top_negative_period_share: float | None
    negative_contribution_hhi: float | None
    dominant_positive_structure: MarketStructure | None
    dominant_positive_stage: MarketStage | None
    dominant_positive_stage_share: float | None
    diagnostic_flags: tuple[DiagnosticFlag, ...]
    evidence_status: EvidenceStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CrossModelPeriodConcentration:
    cost_bps: int
    effective_trade_date: date
    return_period_end_date: date
    market_structure: MarketStructure
    market_stage: MarketStage
    candidate_model_count: int
    available_model_count: int
    unavailable_model_count: int
    benchmark_code: str | None
    equal_weight_net_return: float | None
    equal_weight_net_excess_return: float | None
    top_positive_model_code: str | None
    top_positive_model_share: float | None
    positive_model_contribution_hhi: float | None
    diagnostic_flags: tuple[DiagnosticFlag, ...]
    evidence_status: EvidenceStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class FailureConcentrationDiagnosticsResult:
    model_diagnostics: tuple[ModelFailureConcentrationDiagnostic, ...]
    cross_model_periods: tuple[CrossModelPeriodConcentration, ...]
    input_cost_result_hash: str
    input_evaluation_ready: bool
    diagnostics_ready: bool
    operationally_actionable: bool
    policy_version: str
    policy_hash: str
    result_hash: str

    def __post_init__(self) -> None:
        if self.operationally_actionable:
            raise ContractValidationError("research diagnostics cannot be operationally actionable")


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 12)


def _compound(returns: list[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def _share_hhi(values: list[float], *, top_count: int) -> tuple[float | None, float | None]:
    positive = [value for value in values if value > 0.0]
    total = sum(positive)
    if not positive or math.isclose(total, 0.0, abs_tol=1e-15):
        return None, None
    ordered = sorted(positive, reverse=True)
    top_share = sum(ordered[:top_count]) / total
    hhi = sum((value / total) ** 2 for value in positive)
    return top_share, hhi


def _available_segments(
    rows: list[CostAdjustedObservation],
) -> list[list[CostAdjustedObservation]]:
    segments: list[list[CostAdjustedObservation]] = []
    current: list[CostAdjustedObservation] = []
    for row in rows:
        contiguous = not current or row.effective_trade_date == current[-1].return_period_end_date
        if not row.available or not contiguous:
            if current:
                segments.append(current)
            current = []
        if row.available:
            current.append(row)
    if current:
        segments.append(current)
    return segments


def _failure_episode(rows: list[CostAdjustedObservation]) -> FailureEpisode:
    net_returns = [float(row.net_return) for row in rows]
    benchmark_returns = [float(row.benchmark_return) for row in rows]
    net_total = _compound(net_returns)
    benchmark_total = _compound(benchmark_returns)
    return FailureEpisode(
        start_date=rows[0].effective_trade_date,
        end_date=rows[-1].return_period_end_date,
        failure_period_count=len(rows),
        compounded_net_return=_rounded(net_total),
        compounded_benchmark_return=_rounded(benchmark_total),
        compounded_net_excess_return=_rounded(net_total - benchmark_total),
        worst_period_net_excess_return=_rounded(
            min(float(row.net_excess_return) for row in rows)
        ),
        market_structures=tuple(dict.fromkeys(row.market_structure for row in rows)),
        market_stages=tuple(dict.fromkeys(row.market_stage for row in rows)),
    )


def _failure_episodes(
    rows: list[CostAdjustedObservation],
) -> tuple[FailureEpisode, ...]:
    episodes: list[FailureEpisode] = []
    current: list[CostAdjustedObservation] = []
    for row in rows:
        contiguous = not current or row.effective_trade_date == current[-1].return_period_end_date
        failed = row.available and float(row.net_excess_return) < 0.0
        if not failed or not contiguous:
            if current:
                episodes.append(_failure_episode(current))
            current = []
        if failed:
            current.append(row)
    if current:
        episodes.append(_failure_episode(current))
    return tuple(episodes)


def _worst_rolling_windows(
    rows: list[CostAdjustedObservation],
    window_sizes: tuple[int, ...],
) -> tuple[RollingFailureWindow, ...]:
    windows: list[RollingFailureWindow] = []
    segments = _available_segments(rows)
    for window_size in window_sizes:
        candidates: list[RollingFailureWindow] = []
        for segment in segments:
            for start in range(len(segment) - window_size + 1):
                selected = segment[start : start + window_size]
                net_total = _compound([float(row.net_return) for row in selected])
                benchmark_total = _compound(
                    [float(row.benchmark_return) for row in selected]
                )
                candidates.append(
                    RollingFailureWindow(
                        window_size=window_size,
                        start_date=selected[0].effective_trade_date,
                        end_date=selected[-1].return_period_end_date,
                        compounded_net_return=_rounded(net_total),
                        compounded_benchmark_return=_rounded(benchmark_total),
                        compounded_net_excess_return=_rounded(
                            net_total - benchmark_total
                        ),
                    )
                )
        if candidates:
            windows.append(
                min(
                    candidates,
                    key=lambda item: (
                        item.compounded_net_excess_return,
                        item.start_date,
                    ),
                )
            )
    return tuple(windows)


def _validate_and_group(
    observations: tuple[CostAdjustedObservation, ...],
) -> dict[tuple[str, int], list[CostAdjustedObservation]]:
    grouped: dict[tuple[str, int], list[CostAdjustedObservation]] = {}
    seen: set[tuple[str, int, date, date]] = set()
    roles: dict[str, set[EvaluationScopeRole]] = {}
    ranking: dict[str, set[bool]] = {}
    model_codes = {row.model_code for row in observations}
    costs = {row.cost_bps for row in observations}
    for row in observations:
        key = (
            row.model_code,
            row.cost_bps,
            row.effective_trade_date,
            row.return_period_end_date,
        )
        if key in seen:
            raise ContractValidationError("duplicate diagnostic observation period")
        seen.add(key)
        grouped.setdefault((row.model_code, row.cost_bps), []).append(row)
        roles.setdefault(row.model_code, set()).add(row.scope_role)
        ranking.setdefault(row.model_code, set()).add(row.ranking_eligible)
    if any(len(values) != 1 for values in roles.values()):
        raise ContractValidationError("a diagnostic model cannot mix scope roles")
    if any(len(values) != 1 for values in ranking.values()):
        raise ContractValidationError("a diagnostic model cannot mix ranking eligibility")
    missing_groups = {
        (model_code, cost_bps)
        for model_code in model_codes
        for cost_bps in costs
        if (model_code, cost_bps) not in grouped
    }
    if missing_groups:
        raise ContractValidationError("every diagnostic model must cover every cost scenario")
    for key, rows in grouped.items():
        rows.sort(key=lambda item: item.effective_trade_date)
        benchmark_codes = {row.benchmark_code for row in rows}
        if len(benchmark_codes) != 1:
            raise ContractValidationError("a diagnostic model cannot mix benchmark codes")
        for previous, current in zip(rows, rows[1:]):
            if current.effective_trade_date < previous.return_period_end_date:
                raise ContractValidationError(
                    f"overlapping diagnostic periods for {key[0]} at {key[1]}bp"
                )
    return grouped


def _model_diagnostic(
    rows: list[CostAdjustedObservation],
    *,
    policy: DiagnosticsPolicy,
) -> ModelFailureConcentrationDiagnostic:
    first = rows[0]
    available = [row for row in rows if row.available]
    unavailable_count = len(rows) - len(available)
    if not available:
        return ModelFailureConcentrationDiagnostic(
            model_code=first.model_code,
            scope_role=first.scope_role,
            ranking_eligible=first.ranking_eligible,
            cost_bps=first.cost_bps,
            candidate_period_count=len(rows),
            observation_count=0,
            unavailable_count=unavailable_count,
            availability_ratio=0.0,
            start_date=None,
            end_date=None,
            benchmark_code=first.benchmark_code,
            positive_excess_period_count=0,
            failure_period_count=0,
            failure_period_ratio=None,
            failure_episode_count=0,
            longest_failure_streak=0,
            failure_episodes=(),
            worst_rolling_windows=(),
            top_positive_period_share=None,
            positive_contribution_hhi=None,
            top_negative_period_share=None,
            negative_contribution_hhi=None,
            dominant_positive_structure=None,
            dominant_positive_stage=None,
            dominant_positive_stage_share=None,
            diagnostic_flags=(),
            evidence_status=EvidenceStatus.UNAVAILABLE,
            reason_codes=("INPUT_UNAVAILABLE",),
        )

    excess_returns = [float(row.net_excess_return) for row in available]
    positive = [value for value in excess_returns if value > 0.0]
    negative_magnitudes = [-value for value in excess_returns if value < 0.0]
    top_positive_share, positive_hhi = _share_hhi(
        positive,
        top_count=policy.top_period_count,
    )
    top_negative_share, negative_hhi = _share_hhi(
        negative_magnitudes,
        top_count=policy.top_period_count,
    )
    stage_positive: dict[tuple[MarketStructure, MarketStage], float] = {}
    for row in available:
        contribution = max(float(row.net_excess_return), 0.0)
        stage_positive[(row.market_structure, row.market_stage)] = (
            stage_positive.get((row.market_structure, row.market_stage), 0.0)
            + contribution
        )
    positive_total = sum(stage_positive.values())
    dominant_key: tuple[MarketStructure, MarketStage] | None = None
    dominant_share = None
    if positive_total > 0.0:
        dominant_key, dominant_value = max(
            stage_positive.items(),
            key=lambda item: (item[1], item[0][0].value, item[0][1].value),
        )
        dominant_share = dominant_value / positive_total
    episodes = _failure_episodes(rows)
    failure_count = len(negative_magnitudes)
    failure_ratio = failure_count / len(available)
    longest_streak = max(
        (episode.failure_period_count for episode in episodes),
        default=0,
    )
    flags: list[DiagnosticFlag] = []
    if (
        top_positive_share is not None
        and top_positive_share >= policy.top_positive_period_share_threshold
    ):
        flags.append(DiagnosticFlag.TOP_POSITIVE_PERIOD_CONCENTRATION)
    if positive_hhi is not None and positive_hhi >= policy.contribution_hhi_threshold:
        flags.append(DiagnosticFlag.POSITIVE_CONTRIBUTION_HHI_HIGH)
    if negative_hhi is not None and negative_hhi >= policy.contribution_hhi_threshold:
        flags.append(DiagnosticFlag.NEGATIVE_CONTRIBUTION_HHI_HIGH)
    if dominant_share is not None and dominant_share >= policy.dominant_stage_share_threshold:
        flags.append(DiagnosticFlag.DOMINANT_STAGE_CONCENTRATION)
    if failure_ratio >= policy.failure_period_ratio_threshold:
        flags.append(DiagnosticFlag.HIGH_FAILURE_PERIOD_RATIO)
    if longest_streak >= policy.longest_failure_streak_threshold:
        flags.append(DiagnosticFlag.LONG_FAILURE_STREAK)
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
    return ModelFailureConcentrationDiagnostic(
        model_code=first.model_code,
        scope_role=first.scope_role,
        ranking_eligible=first.ranking_eligible,
        cost_bps=first.cost_bps,
        candidate_period_count=len(rows),
        observation_count=len(available),
        unavailable_count=unavailable_count,
        availability_ratio=_rounded(len(available) / len(rows)),
        start_date=available[0].effective_trade_date,
        end_date=available[-1].return_period_end_date,
        benchmark_code=first.benchmark_code,
        positive_excess_period_count=len(positive),
        failure_period_count=failure_count,
        failure_period_ratio=_rounded(failure_ratio),
        failure_episode_count=len(episodes),
        longest_failure_streak=longest_streak,
        failure_episodes=episodes,
        worst_rolling_windows=_worst_rolling_windows(rows, policy.rolling_window_sizes),
        top_positive_period_share=_rounded(top_positive_share),
        positive_contribution_hhi=_rounded(positive_hhi),
        top_negative_period_share=_rounded(top_negative_share),
        negative_contribution_hhi=_rounded(negative_hhi),
        dominant_positive_structure=dominant_key[0] if dominant_key else None,
        dominant_positive_stage=dominant_key[1] if dominant_key else None,
        dominant_positive_stage_share=_rounded(dominant_share),
        diagnostic_flags=tuple(flags),
        evidence_status=evidence_status,
        reason_codes=tuple(reasons),
    )


def _cross_model_diagnostics(
    observations: tuple[CostAdjustedObservation, ...],
    *,
    policy: DiagnosticsPolicy,
) -> tuple[CrossModelPeriodConcentration, ...]:
    ranking_rows = [row for row in observations if row.ranking_eligible]
    expected_models = sorted({row.model_code for row in ranking_rows})
    costs = sorted({row.cost_bps for row in observations})
    output: list[CrossModelPeriodConcentration] = []
    for cost_bps in costs:
        cost_rows = [row for row in ranking_rows if row.cost_bps == cost_bps]
        period_keys = sorted(
            {(row.effective_trade_date, row.return_period_end_date) for row in cost_rows}
        )
        for start, end in period_keys:
            period_rows = [
                row
                for row in cost_rows
                if row.effective_trade_date == start and row.return_period_end_date == end
            ]
            contexts = {
                (
                    row.decision_date,
                    row.market_structure,
                    row.market_stage,
                    row.market_payload_hash,
                )
                for row in period_rows
            }
            if len(contexts) != 1:
                raise ContractValidationError(
                    "cross-model diagnostic periods must share market context"
                )
            available = [row for row in period_rows if row.available]
            unavailable_count = len(expected_models) - len(available)
            context = period_rows[0]
            benchmark_codes = {row.benchmark_code for row in available}
            reasons: list[str] = []
            if len(available) < policy.minimum_cross_model_count:
                reasons.append("INSUFFICIENT_MODEL_COUNT")
            if unavailable_count:
                reasons.append("INCOMPLETE_MODEL_COVERAGE")
            if len(benchmark_codes) > 1:
                reasons.append("BENCHMARK_MISMATCH")
            comparable = (
                len(available) >= policy.minimum_cross_model_count
                and len(benchmark_codes) == 1
            )
            top_code = None
            top_share = None
            hhi = None
            equal_weight_net = None
            equal_weight_excess = None
            flags: list[DiagnosticFlag] = []
            if comparable:
                equal_weight_net = statistics.fmean(float(row.net_return) for row in available)
                equal_weight_excess = statistics.fmean(
                    float(row.net_excess_return) for row in available
                )
                positive_rows = [
                    row for row in available if float(row.net_excess_return) > 0.0
                ]
                positive_total = sum(float(row.net_excess_return) for row in positive_rows)
                if positive_rows and positive_total > 0.0:
                    top_row = max(
                        positive_rows,
                        key=lambda row: (float(row.net_excess_return), row.model_code),
                    )
                    top_code = top_row.model_code
                    top_share = float(top_row.net_excess_return) / positive_total
                    hhi = sum(
                        (float(row.net_excess_return) / positive_total) ** 2
                        for row in positive_rows
                    )
                    if (
                        top_share >= policy.cross_model_top_share_threshold
                        or hhi >= policy.cross_model_hhi_threshold
                    ):
                        flags.append(
                            DiagnosticFlag.CROSS_MODEL_CONTRIBUTION_CONCENTRATION
                        )
            if not available:
                evidence_status = EvidenceStatus.UNAVAILABLE
            elif comparable and unavailable_count == 0:
                evidence_status = EvidenceStatus.SUFFICIENT
            else:
                evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE
            output.append(
                CrossModelPeriodConcentration(
                    cost_bps=cost_bps,
                    effective_trade_date=start,
                    return_period_end_date=end,
                    market_structure=context.market_structure,
                    market_stage=context.market_stage,
                    candidate_model_count=len(expected_models),
                    available_model_count=len(available),
                    unavailable_model_count=unavailable_count,
                    benchmark_code=(next(iter(benchmark_codes)) if len(benchmark_codes) == 1 else None),
                    equal_weight_net_return=_rounded(equal_weight_net),
                    equal_weight_net_excess_return=_rounded(equal_weight_excess),
                    top_positive_model_code=top_code,
                    top_positive_model_share=_rounded(top_share),
                    positive_model_contribution_hhi=_rounded(hhi),
                    diagnostic_flags=tuple(flags),
                    evidence_status=evidence_status,
                    reason_codes=tuple(reasons),
                )
            )
    return tuple(output)


def diagnose_failure_concentration(
    cost_result: CostSensitivityResult,
    *,
    policy: DiagnosticsPolicy | None = None,
) -> FailureConcentrationDiagnosticsResult:
    applied_policy = policy or DiagnosticsPolicy()
    grouped = _validate_and_group(cost_result.observations)
    model_diagnostics = tuple(
        _model_diagnostic(rows, policy=applied_policy)
        for _, rows in sorted(grouped.items())
    )
    cross_model_periods = _cross_model_diagnostics(
        cost_result.observations,
        policy=applied_policy,
    )
    eligible_cross_periods = [
        item for item in cross_model_periods if item.candidate_model_count > 0
    ]
    diagnostics_ready = (
        cost_result.evaluation_ready
        and bool(model_diagnostics)
        and all(
            item.evidence_status is EvidenceStatus.SUFFICIENT
            for item in model_diagnostics
        )
        and bool(eligible_cross_periods)
        and all(
            item.evidence_status is EvidenceStatus.SUFFICIENT
            for item in eligible_cross_periods
        )
    )
    policy_hash = applied_policy.policy_hash()
    result_hash = canonical_sha256(
        {
            "input_cost_result_hash": cost_result.result_hash,
            "policy_hash": policy_hash,
            "model_diagnostics": [asdict(item) for item in model_diagnostics],
            "cross_model_periods": [asdict(item) for item in cross_model_periods],
            "operationally_actionable": False,
        }
    )
    return FailureConcentrationDiagnosticsResult(
        model_diagnostics=model_diagnostics,
        cross_model_periods=cross_model_periods,
        input_cost_result_hash=cost_result.result_hash,
        input_evaluation_ready=cost_result.evaluation_ready,
        diagnostics_ready=diagnostics_ready,
        operationally_actionable=False,
        policy_version=applied_policy.version,
        policy_hash=policy_hash,
        result_hash=result_hash,
    )
