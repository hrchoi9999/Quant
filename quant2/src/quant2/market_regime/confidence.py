from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from src.quant2.contracts.market_features import MarketFeatureSnapshot
from src.quant2.contracts.market_regime import (
    ConfidenceLevel,
    ContractValidationError,
    MarketAxis,
    MarketReasonCode,
    canonical_sha256,
)

CONFIDENCE_POLICY_VERSION = "quant2.market_confidence.v1"


@dataclass(frozen=True)
class ConfidencePolicy:
    stage_margin_weight: float = 0.30
    coverage_weight: float = 0.30
    signal_alignment_weight: float = 0.25
    persistence_weight: float = 0.15
    high_threshold: float = 0.75
    medium_threshold: float = 0.50
    low_coverage_threshold: float = 0.65
    signal_conflict_threshold: float = 0.40
    persistence_full_days: int = 5
    version: str = CONFIDENCE_POLICY_VERSION

    def __post_init__(self) -> None:
        weights = (
            self.stage_margin_weight,
            self.coverage_weight,
            self.signal_alignment_weight,
            self.persistence_weight,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in weights):
            raise ContractValidationError("confidence weights must be finite and non-negative")
        if not math.isclose(sum(weights), 1.0, abs_tol=1e-9):
            raise ContractValidationError("confidence weights must sum to 1")
        for field_name in (
            "high_threshold",
            "medium_threshold",
            "low_coverage_threshold",
            "signal_conflict_threshold",
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ContractValidationError(f"{field_name} must be between 0 and 1")
        if self.high_threshold <= self.medium_threshold:
            raise ContractValidationError("high_threshold must exceed medium_threshold")
        if self.persistence_full_days <= 0:
            raise ContractValidationError("persistence_full_days must be positive")
        if not self.version.strip():
            raise ContractValidationError("confidence policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ConfidenceResult:
    score: float
    level: ConfidenceLevel
    stage_margin_component: float
    coverage_component: float
    signal_alignment_component: float
    persistence_component: float
    effective_coverage_by_axis: dict[str, float]
    reason_codes: tuple[MarketReasonCode, ...]
    policy_version: str
    policy_hash: str


def _validate_unit_interval(value: float, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ContractValidationError(f"{field_name} must be between 0 and 1")
    return number


def calculate_regime_confidence(
    snapshot: MarketFeatureSnapshot,
    *,
    stage_score_margin: float,
    signal_alignment: float,
    state_persistence_days: int,
    policy: ConfidencePolicy | None = None,
) -> ConfidenceResult:
    """Combine normalized evidence without imputing unavailable axis values."""

    applied_policy = policy or ConfidencePolicy()
    margin = _validate_unit_interval(stage_score_margin, "stage_score_margin")
    alignment = _validate_unit_interval(signal_alignment, "signal_alignment")
    if state_persistence_days < 0:
        raise ContractValidationError("state_persistence_days cannot be negative")

    axis_map = snapshot.axis_map()
    effective_coverage_by_axis = {
        axis.value: axis_map[axis].effective_coverage for axis in MarketAxis
    }
    coverage = sum(effective_coverage_by_axis.values()) / len(MarketAxis)
    persistence = min(state_persistence_days / applied_policy.persistence_full_days, 1.0)
    score = (
        margin * applied_policy.stage_margin_weight
        + coverage * applied_policy.coverage_weight
        + alignment * applied_policy.signal_alignment_weight
        + persistence * applied_policy.persistence_weight
    )
    score = round(score, 12)

    if score >= applied_policy.high_threshold:
        level = ConfidenceLevel.HIGH
    elif score >= applied_policy.medium_threshold:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.LOW

    reasons: list[MarketReasonCode] = []
    for axis in MarketAxis:
        feature = axis_map[axis]
        reasons.extend(feature.reason_codes)
        if feature.available:
            if feature.freshness_ratio < 1.0:
                reasons.append(MarketReasonCode.SOURCE_STALE)
            continue
        if axis is MarketAxis.BREADTH:
            reasons.append(MarketReasonCode.BREADTH_UNAVAILABLE)
        elif axis is MarketAxis.MACRO_EARNINGS:
            reasons.append(MarketReasonCode.MACRO_EARNINGS_UNAVAILABLE)
        else:
            reasons.append(MarketReasonCode.SOURCE_UNAVAILABLE)
    if coverage < applied_policy.low_coverage_threshold:
        reasons.append(MarketReasonCode.LOW_COVERAGE)
    if alignment < applied_policy.signal_conflict_threshold:
        reasons.append(MarketReasonCode.SIGNAL_CONFLICT)

    return ConfidenceResult(
        score=score,
        level=level,
        stage_margin_component=round(margin * applied_policy.stage_margin_weight, 12),
        coverage_component=round(coverage * applied_policy.coverage_weight, 12),
        signal_alignment_component=round(alignment * applied_policy.signal_alignment_weight, 12),
        persistence_component=round(persistence * applied_policy.persistence_weight, 12),
        effective_coverage_by_axis=effective_coverage_by_axis,
        reason_codes=tuple(dict.fromkeys(reasons)),
        policy_version=applied_policy.version,
        policy_hash=applied_policy.policy_hash(),
    )
