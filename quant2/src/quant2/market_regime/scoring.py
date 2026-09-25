from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping

from src.quant2.contracts.market_features import MarketFeatureSnapshot
from src.quant2.contracts.market_regime import (
    STAGE_STRUCTURE,
    ContractValidationError,
    MarketAxis,
    MarketReasonCode,
    MarketStage,
    MarketStructure,
    ProbabilityStatus,
    canonical_sha256,
)

SCORING_RULE_VERSION = "quant2.market_regime_scoring.v2"

AXIS_WEIGHTS: dict[MarketAxis, float] = {
    MarketAxis.TREND: 0.40,
    MarketAxis.BREADTH: 0.25,
    MarketAxis.RISK_LIQUIDITY: 0.20,
    MarketAxis.MACRO_EARNINGS: 0.15,
}

STRUCTURE_TARGETS: dict[MarketStructure, dict[MarketAxis, float]] = {
    MarketStructure.UPTREND: {
        MarketAxis.TREND: 0.75,
        MarketAxis.BREADTH: 0.45,
        MarketAxis.RISK_LIQUIDITY: 0.35,
        MarketAxis.MACRO_EARNINGS: 0.25,
    },
    MarketStructure.RANGE: {axis: 0.0 for axis in MarketAxis},
    MarketStructure.DOWNTREND: {
        MarketAxis.TREND: -0.75,
        MarketAxis.BREADTH: -0.45,
        MarketAxis.RISK_LIQUIDITY: -0.35,
        MarketAxis.MACRO_EARNINGS: -0.25,
    },
}

STAGE_TARGETS: dict[MarketStage, dict[MarketAxis, float]] = {
    MarketStage.UPTREND_INITIATION: {
        MarketAxis.TREND: 0.35,
        MarketAxis.BREADTH: 0.65,
        MarketAxis.RISK_LIQUIDITY: 0.35,
        MarketAxis.MACRO_EARNINGS: 0.20,
    },
    MarketStage.UPTREND_CONTINUATION: {
        MarketAxis.TREND: 0.90,
        MarketAxis.BREADTH: 0.75,
        MarketAxis.RISK_LIQUIDITY: 0.65,
        MarketAxis.MACRO_EARNINGS: 0.55,
    },
    MarketStage.UPTREND_EXHAUSTION: {
        MarketAxis.TREND: 0.75,
        MarketAxis.BREADTH: -0.45,
        MarketAxis.RISK_LIQUIDITY: -0.35,
        MarketAxis.MACRO_EARNINGS: -0.35,
    },
    MarketStage.RANGE_ACCUMULATION: {
        MarketAxis.TREND: 0.00,
        MarketAxis.BREADTH: 0.45,
        MarketAxis.RISK_LIQUIDITY: 0.35,
        MarketAxis.MACRO_EARNINGS: 0.30,
    },
    MarketStage.RANGE_DISTRIBUTION: {
        MarketAxis.TREND: 0.00,
        MarketAxis.BREADTH: -0.45,
        MarketAxis.RISK_LIQUIDITY: -0.35,
        MarketAxis.MACRO_EARNINGS: -0.30,
    },
    MarketStage.DOWNTREND_INITIATION: {
        MarketAxis.TREND: -0.35,
        MarketAxis.BREADTH: -0.65,
        MarketAxis.RISK_LIQUIDITY: -0.55,
        MarketAxis.MACRO_EARNINGS: -0.30,
    },
    MarketStage.DOWNTREND_CONTINUATION: {
        MarketAxis.TREND: -0.90,
        MarketAxis.BREADTH: -0.75,
        MarketAxis.RISK_LIQUIDITY: -0.65,
        MarketAxis.MACRO_EARNINGS: -0.55,
    },
    MarketStage.DOWNTREND_EXHAUSTION: {
        MarketAxis.TREND: -0.75,
        MarketAxis.BREADTH: 0.35,
        MarketAxis.RISK_LIQUIDITY: 0.25,
        MarketAxis.MACRO_EARNINGS: 0.15,
    },
}

UPWARD_TRANSITION_STAGES = frozenset(
    {
        MarketStage.DOWNTREND_EXHAUSTION,
        MarketStage.RANGE_ACCUMULATION,
        MarketStage.UPTREND_INITIATION,
    }
)
DOWNWARD_TRANSITION_STAGES = frozenset(
    {
        MarketStage.UPTREND_EXHAUSTION,
        MarketStage.RANGE_DISTRIBUTION,
        MarketStage.DOWNTREND_INITIATION,
    }
)
UPWARD_TRANSITION_OPPOSED_STAGES = frozenset(
    {
        MarketStage.DOWNTREND_INITIATION,
        MarketStage.DOWNTREND_CONTINUATION,
        MarketStage.RANGE_DISTRIBUTION,
        MarketStage.UPTREND_EXHAUSTION,
    }
)
DOWNWARD_TRANSITION_OPPOSED_STAGES = frozenset(
    {
        MarketStage.UPTREND_INITIATION,
        MarketStage.UPTREND_CONTINUATION,
        MarketStage.RANGE_ACCUMULATION,
        MarketStage.DOWNTREND_EXHAUSTION,
    }
)


@dataclass(frozen=True)
class RegimeScoringPolicy:
    zscore_clip_abs: float = 3.0
    probability_temperature: float = 0.15
    signal_direction_threshold: float = 0.10
    base_trend_weight: float = 0.60
    technical_trend_weight: float = 0.40
    transition_stage_boost: float = 0.25
    version: str = SCORING_RULE_VERSION

    def __post_init__(self) -> None:
        if not math.isfinite(self.zscore_clip_abs) or self.zscore_clip_abs <= 0.0:
            raise ContractValidationError("zscore_clip_abs must be finite and positive")
        if not math.isfinite(self.probability_temperature) or self.probability_temperature <= 0.0:
            raise ContractValidationError("probability_temperature must be finite and positive")
        if not 0.0 <= self.signal_direction_threshold <= 1.0:
            raise ContractValidationError("signal_direction_threshold must be between 0 and 1")
        if not math.isclose(
            self.base_trend_weight + self.technical_trend_weight, 1.0, abs_tol=1e-12
        ):
            raise ContractValidationError("base and technical trend weights must sum to one")
        if min(self.base_trend_weight, self.technical_trend_weight) < 0.0:
            raise ContractValidationError("trend blend weights cannot be negative")
        if not 0.0 <= self.transition_stage_boost <= 1.0:
            raise ContractValidationError("transition_stage_boost must be between 0 and 1")
        if not self.version.strip():
            raise ContractValidationError("scoring policy version is required")

    def rule_manifest(self) -> dict[str, object]:
        return {
            "version": self.version,
            "zscore_clip_abs": self.zscore_clip_abs,
            "probability_temperature": self.probability_temperature,
            "signal_direction_threshold": self.signal_direction_threshold,
            "base_trend_weight": self.base_trend_weight,
            "technical_trend_weight": self.technical_trend_weight,
            "transition_stage_boost": self.transition_stage_boost,
            "technical_transition_stage_sets": {
                "up": sorted(stage.value for stage in UPWARD_TRANSITION_STAGES),
                "down": sorted(stage.value for stage in DOWNWARD_TRANSITION_STAGES),
                "up_opposed": sorted(stage.value for stage in UPWARD_TRANSITION_OPPOSED_STAGES),
                "down_opposed": sorted(
                    stage.value for stage in DOWNWARD_TRANSITION_OPPOSED_STAGES
                ),
            },
            "axis_weights": {axis.value: AXIS_WEIGHTS[axis] for axis in MarketAxis},
            "structure_targets": {
                structure.value: {axis.value: targets[axis] for axis in MarketAxis}
                for structure, targets in STRUCTURE_TARGETS.items()
            },
            "stage_targets": {
                stage.value: {axis.value: targets[axis] for axis in MarketAxis}
                for stage, targets in STAGE_TARGETS.items()
            },
        }

    def rule_hash(self) -> str:
        return canonical_sha256(self.rule_manifest())


@dataclass(frozen=True)
class RegimeScoreResult:
    decision_date: date
    structure: MarketStructure
    stage: MarketStage
    structure_scores: Mapping[MarketStructure, float]
    stage_scores: Mapping[MarketStage, float]
    stage_probabilities: Mapping[MarketStage, float]
    probability_status: ProbabilityStatus
    stage_score_margin: float
    signal_alignment: float
    canonical_axis_values: Mapping[MarketAxis, float | None]
    reason_codes: tuple[MarketReasonCode, ...]
    rule_version: str
    rule_hash: str

    def __post_init__(self) -> None:
        if STAGE_STRUCTURE[self.stage] is not self.structure:
            raise ContractValidationError("scored stage does not belong to scored structure")
        if set(self.structure_scores) != set(MarketStructure):
            raise ContractValidationError("structure_scores must contain all market structures")
        if set(self.stage_scores) != set(MarketStage):
            raise ContractValidationError("stage_scores must contain all market stages")
        if set(self.stage_probabilities) != set(MarketStage):
            raise ContractValidationError("stage_probabilities must contain all market stages")
        if set(self.canonical_axis_values) != set(MarketAxis):
            raise ContractValidationError("canonical_axis_values must contain all market axes")
        for field_name, values in (
            ("structure_scores", self.structure_scores.values()),
            ("stage_scores", self.stage_scores.values()),
            ("stage_probabilities", self.stage_probabilities.values()),
        ):
            if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
                raise ContractValidationError(f"{field_name} values must be between 0 and 1")
        if not math.isclose(sum(self.stage_probabilities.values()), 1.0, abs_tol=1e-9):
            raise ContractValidationError("stage_probabilities must sum to 1")
        if not 0.0 <= self.stage_score_margin <= 1.0:
            raise ContractValidationError("stage_score_margin must be between 0 and 1")
        if not 0.0 <= self.signal_alignment <= 1.0:
            raise ContractValidationError("signal_alignment must be between 0 and 1")
        if self.structure_scores[self.structure] < max(self.structure_scores.values()):
            raise ContractValidationError("scored structure must have the highest structure score")
        eligible_scores = [
            self.stage_scores[item]
            for item in MarketStage
            if STAGE_STRUCTURE[item] is self.structure
        ]
        if self.stage_scores[self.stage] < max(eligible_scores):
            raise ContractValidationError("scored stage must lead within the scored structure")
        if not self.rule_version.strip():
            raise ContractValidationError("rule_version is required")
        if len(self.rule_hash) != 64 or any(character not in "0123456789ABCDEF" for character in self.rule_hash):
            raise ContractValidationError("rule_hash must be uppercase SHA-256 hex")


def _similarity(
    values: Mapping[MarketAxis, float | None],
    targets: Mapping[MarketAxis, float],
    effective_weights: Mapping[MarketAxis, float],
) -> float:
    denominator = sum(effective_weights.values())
    if denominator <= 0.0:
        raise ContractValidationError("at least one market axis must be available")
    distance = sum(
        effective_weights[axis] * abs(float(values[axis]) - targets[axis]) / 2.0
        for axis in MarketAxis
        if values[axis] is not None
    )
    return max(0.0, min(1.0, 1.0 - distance / denominator))


def _softmax(scores: Mapping[MarketStage, float], temperature: float) -> dict[MarketStage, float]:
    peak = max(scores.values())
    numerators = {
        stage: math.exp((score - peak) / temperature) for stage, score in scores.items()
    }
    denominator = sum(numerators.values())
    return {stage: value / denominator for stage, value in numerators.items()}


def _apply_transition_stage_signal(
    stage_scores: Mapping[MarketStage, float],
    transition_score: float,
    *,
    maximum_boost: float,
) -> dict[MarketStage, float]:
    if math.isclose(transition_score, 0.0, abs_tol=1e-12):
        return dict(stage_scores)
    favored = UPWARD_TRANSITION_STAGES if transition_score > 0.0 else DOWNWARD_TRANSITION_STAGES
    opposed = (
        UPWARD_TRANSITION_OPPOSED_STAGES
        if transition_score > 0.0
        else DOWNWARD_TRANSITION_OPPOSED_STAGES
    )
    boost = maximum_boost * abs(transition_score)
    adjusted = {}
    for stage, score in stage_scores.items():
        adjustment = boost if stage in favored else (-boost if stage in opposed else 0.0)
        adjusted[stage] = max(0.0, min(1.0, score + adjustment))
    return adjusted


def score_trend_components(
    *,
    decision_date: date,
    trend_score: float,
    transition_score: float,
    reason_codes: tuple[MarketReasonCode, ...],
    source_rule_hash: str,
    policy: RegimeScoringPolicy | None = None,
) -> RegimeScoreResult:
    """Score a reconstructed history row from Quant 2.0 technical components.

    This entry point deliberately avoids constructing a PIT ``MarketFeatureSnapshot``.
    It is used only when the source history is explicitly classified as reconstructed;
    unavailable breadth, risk/liquidity and macro/earnings axes remain null.
    """
    applied_policy = policy or RegimeScoringPolicy()
    if not all(math.isfinite(value) and -1.0 <= value <= 1.0 for value in (trend_score, transition_score)):
        raise ContractValidationError("technical trend components must be finite and between -1 and 1")
    if len(source_rule_hash) != 64 or any(
        character not in "0123456789ABCDEF" for character in source_rule_hash
    ):
        raise ContractValidationError("source_rule_hash must be uppercase SHA-256 hex")

    canonical_values: dict[MarketAxis, float | None] = {
        MarketAxis.TREND: float(trend_score),
        MarketAxis.BREADTH: None,
        MarketAxis.RISK_LIQUIDITY: None,
        MarketAxis.MACRO_EARNINGS: None,
    }
    effective_weights = {
        axis: AXIS_WEIGHTS[axis] if axis is MarketAxis.TREND else 0.0
        for axis in MarketAxis
    }
    structure_scores = {
        structure: _similarity(canonical_values, targets, effective_weights)
        for structure, targets in STRUCTURE_TARGETS.items()
    }
    structure = max(structure_scores, key=structure_scores.__getitem__)
    stage_scores = {
        stage: _similarity(canonical_values, targets, effective_weights)
        for stage, targets in STAGE_TARGETS.items()
    }
    stage_scores = _apply_transition_stage_signal(
        stage_scores,
        float(transition_score),
        maximum_boost=applied_policy.transition_stage_boost,
    )
    eligible = [stage for stage in MarketStage if STAGE_STRUCTURE[stage] is structure]
    ranked = sorted(eligible, key=lambda stage: stage_scores[stage], reverse=True)
    stage = ranked[0]
    stage_margin = stage_scores[ranked[0]] - stage_scores[ranked[1]]
    probabilities = _softmax(stage_scores, applied_policy.probability_temperature)
    combined_reasons = list(reason_codes)
    combined_reasons.extend(
        (
            MarketReasonCode.BREADTH_UNAVAILABLE,
            MarketReasonCode.SOURCE_UNAVAILABLE,
            MarketReasonCode.MACRO_EARNINGS_UNAVAILABLE,
        )
    )
    rule_hash = canonical_sha256(
        {
            "scoring_rule_hash": applied_policy.rule_hash(),
            "source_rule_hash": source_rule_hash,
            "mode": "RECONSTRUCTED_TECHNICAL_ONLY",
        }
    )
    return RegimeScoreResult(
        decision_date=decision_date,
        structure=structure,
        stage=stage,
        structure_scores={key: round(value, 12) for key, value in structure_scores.items()},
        stage_scores={key: round(value, 12) for key, value in stage_scores.items()},
        stage_probabilities={key: round(value, 15) for key, value in probabilities.items()},
        probability_status=ProbabilityStatus.PROVISIONAL,
        stage_score_margin=round(stage_margin, 12),
        signal_alignment=round(stage_scores[stage], 12),
        canonical_axis_values=canonical_values,
        reason_codes=tuple(dict.fromkeys(combined_reasons)),
        rule_version=f"{applied_policy.version}.technical_only",
        rule_hash=rule_hash,
    )


def score_market_regime(
    snapshot: MarketFeatureSnapshot,
    *,
    policy: RegimeScoringPolicy | None = None,
) -> RegimeScoreResult:
    applied_policy = policy or RegimeScoringPolicy()
    axis_map = snapshot.axis_map()
    canonical_values: dict[MarketAxis, float | None] = {}
    effective_weights: dict[MarketAxis, float] = {}
    for axis in MarketAxis:
        feature = axis_map[axis]
        if not feature.available:
            canonical_values[axis] = None
            effective_weights[axis] = 0.0
            continue
        zscore = max(
            -applied_policy.zscore_clip_abs,
            min(applied_policy.zscore_clip_abs, float(feature.normalized_score)),
        )
        canonical_values[axis] = zscore / applied_policy.zscore_clip_abs
        effective_weights[axis] = AXIS_WEIGHTS[axis] * feature.effective_coverage

    technical_signal = snapshot.trend_transition
    if technical_signal is not None and technical_signal.available:
        technical_trend = technical_signal.normalized_components["trend_score"]
        if technical_trend is None:
            raise ContractValidationError("available trend transition requires trend_score")
        if canonical_values[MarketAxis.TREND] is None:
            canonical_values[MarketAxis.TREND] = float(technical_trend)
            effective_weights[MarketAxis.TREND] = AXIS_WEIGHTS[MarketAxis.TREND]
        else:
            canonical_values[MarketAxis.TREND] = (
                applied_policy.base_trend_weight * float(canonical_values[MarketAxis.TREND])
                + applied_policy.technical_trend_weight * float(technical_trend)
            )

    if sum(effective_weights.values()) <= 0.0:
        raise ContractValidationError("cannot score market regime without an available axis")

    structure_scores = {
        structure: _similarity(canonical_values, targets, effective_weights)
        for structure, targets in STRUCTURE_TARGETS.items()
    }
    structure = max(structure_scores, key=structure_scores.__getitem__)
    stage_scores: dict[MarketStage, float] = {
        stage: _similarity(canonical_values, targets, effective_weights)
        for stage, targets in STAGE_TARGETS.items()
    }
    if technical_signal is not None and technical_signal.available:
        transition_score = technical_signal.normalized_components["transition_score"]
        if transition_score is None:
            raise ContractValidationError("available trend transition requires transition_score")
        stage_scores = _apply_transition_stage_signal(
            stage_scores,
            float(transition_score),
            maximum_boost=applied_policy.transition_stage_boost,
        )
    eligible_stages = [stage for stage in MarketStage if STAGE_STRUCTURE[stage] is structure]
    ranked_eligible = sorted(eligible_stages, key=lambda stage: stage_scores[stage], reverse=True)
    stage = ranked_eligible[0]
    stage_score_margin = stage_scores[ranked_eligible[0]] - stage_scores[ranked_eligible[1]]
    stage_probabilities = _softmax(stage_scores, applied_policy.probability_temperature)

    reasons: list[MarketReasonCode] = []
    trend_value = canonical_values[MarketAxis.TREND]
    if structure is MarketStructure.UPTREND:
        reasons.append(MarketReasonCode.TREND_UP_CONFIRMED)
    elif structure is MarketStructure.DOWNTREND:
        reasons.append(MarketReasonCode.TREND_DOWN_CONFIRMED)
    else:
        reasons.append(MarketReasonCode.TREND_DIRECTION_MIXED)

    for axis, positive_reason, negative_reason, unavailable_reason in (
        (
            MarketAxis.BREADTH,
            MarketReasonCode.BREADTH_IMPROVING,
            MarketReasonCode.BREADTH_WEAKENING,
            MarketReasonCode.BREADTH_UNAVAILABLE,
        ),
        (
            MarketAxis.RISK_LIQUIDITY,
            MarketReasonCode.RISK_APPETITE_IMPROVING,
            MarketReasonCode.RISK_APPETITE_WEAKENING,
            MarketReasonCode.SOURCE_UNAVAILABLE,
        ),
        (
            MarketAxis.MACRO_EARNINGS,
            MarketReasonCode.MACRO_EARNINGS_IMPROVING,
            MarketReasonCode.MACRO_EARNINGS_WEAKENING,
            MarketReasonCode.MACRO_EARNINGS_UNAVAILABLE,
        ),
    ):
        value = canonical_values[axis]
        if value is None:
            reasons.append(unavailable_reason)
        elif value > applied_policy.signal_direction_threshold:
            reasons.append(positive_reason)
        elif value < -applied_policy.signal_direction_threshold:
            reasons.append(negative_reason)

    available_values = [value for value in canonical_values.values() if value is not None]
    has_positive = any(value > applied_policy.signal_direction_threshold for value in available_values)
    has_negative = any(value < -applied_policy.signal_direction_threshold for value in available_values)
    if has_positive and has_negative:
        reasons.append(MarketReasonCode.SIGNAL_CONFLICT)
    if trend_value is None:
        reasons.append(MarketReasonCode.SOURCE_UNAVAILABLE)
    if technical_signal is not None:
        reasons.extend(technical_signal.reason_codes)

    combined_rule_hash = applied_policy.rule_hash()
    if technical_signal is not None:
        combined_rule_hash = canonical_sha256(
            {
                "scoring_rule_hash": combined_rule_hash,
                "trend_transition_rule_hash": technical_signal.rule_hash,
                "technical_indicator_rule_hash": technical_signal.technical_rule_hash,
            }
        )

    return RegimeScoreResult(
        decision_date=snapshot.decision_date,
        structure=structure,
        stage=stage,
        structure_scores={key: round(value, 12) for key, value in structure_scores.items()},
        stage_scores={key: round(value, 12) for key, value in stage_scores.items()},
        stage_probabilities={key: round(value, 12) for key, value in stage_probabilities.items()},
        probability_status=ProbabilityStatus.PROVISIONAL,
        stage_score_margin=round(stage_score_margin, 12),
        signal_alignment=round(stage_scores[stage], 12),
        canonical_axis_values=canonical_values,
        reason_codes=tuple(dict.fromkeys(reasons)),
        rule_version=applied_policy.version,
        rule_hash=combined_rule_hash,
    )
