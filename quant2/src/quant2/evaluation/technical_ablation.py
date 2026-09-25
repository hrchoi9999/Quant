from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum

from src.quant2.contracts.market_features import MarketFeatureSnapshot
from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketAxis,
    MarketReasonCode,
    MarketScope,
    MarketStage,
    MarketStructure,
    canonical_sha256,
)
from src.quant2.contracts.trend_transition import (
    TechnicalTransitionDirection,
    TrendTransitionSignal,
)
from src.quant2.market_regime.scoring import (
    RegimeScoreResult,
    RegimeScoringPolicy,
    score_market_regime,
)

TECHNICAL_ABLATION_POLICY_VERSION = "quant2.technical_ablation.v1"


class TechnicalAblationVariant(str, Enum):
    Q2_MARKET_BASE = "Q2_MARKET_BASE"
    Q2_MA_GAP = "Q2_MA_GAP"
    Q2_RSI = "Q2_RSI"
    Q2_MACD = "Q2_MACD"
    Q2_COMBINED = "Q2_COMBINED"


TECHNICAL_ABLATION_VARIANTS = tuple(TechnicalAblationVariant)


@dataclass(frozen=True)
class TechnicalAblationSpecification:
    variant: TechnicalAblationVariant
    enabled_feature_groups: tuple[str, ...]
    technical_trend_weight: float
    transition_component: str | None
    version: str = TECHNICAL_ABLATION_POLICY_VERSION

    def specification_hash(self) -> str:
        return canonical_sha256(
            {
                "variant": self.variant.value,
                "enabled_feature_groups": self.enabled_feature_groups,
                "technical_trend_weight": self.technical_trend_weight,
                "transition_component": self.transition_component,
                "version": self.version,
            }
        )


TECHNICAL_ABLATION_SPECIFICATIONS = {
    TechnicalAblationVariant.Q2_MARKET_BASE: TechnicalAblationSpecification(
        variant=TechnicalAblationVariant.Q2_MARKET_BASE,
        enabled_feature_groups=("MARKET_BASE",),
        technical_trend_weight=0.0,
        transition_component=None,
    ),
    TechnicalAblationVariant.Q2_MA_GAP: TechnicalAblationSpecification(
        variant=TechnicalAblationVariant.Q2_MA_GAP,
        enabled_feature_groups=("MARKET_BASE", "MA_GAP"),
        technical_trend_weight=0.40,
        transition_component="fast_gap_momentum",
    ),
    TechnicalAblationVariant.Q2_RSI: TechnicalAblationSpecification(
        variant=TechnicalAblationVariant.Q2_RSI,
        enabled_feature_groups=("MARKET_BASE", "RSI"),
        technical_trend_weight=0.0,
        transition_component="rsi_confirmation",
    ),
    TechnicalAblationVariant.Q2_MACD: TechnicalAblationSpecification(
        variant=TechnicalAblationVariant.Q2_MACD,
        enabled_feature_groups=("MARKET_BASE", "MACD"),
        technical_trend_weight=0.0,
        transition_component="macd_confirmation",
    ),
    TechnicalAblationVariant.Q2_COMBINED: TechnicalAblationSpecification(
        variant=TechnicalAblationVariant.Q2_COMBINED,
        enabled_feature_groups=("MARKET_BASE", "MA_GAP", "RSI", "MACD"),
        technical_trend_weight=0.40,
        transition_component="transition_score",
    ),
}


@dataclass(frozen=True)
class TechnicalAblationOutcome:
    variant: TechnicalAblationVariant
    market_scope: MarketScope
    decision_date: date
    enabled_feature_groups: tuple[str, ...]
    feature_snapshot_hash: str
    projected_signal_hash: str | None
    specification_hash: str
    scoring_rule_hash: str
    structure: MarketStructure
    stage: MarketStage
    canonical_trend_value: float | None
    technical_trend_score: float | None
    transition_score: float | None
    transition_direction: TechnicalTransitionDirection | None
    candidate_score: RegimeScoreResult
    outcome_hash: str


@dataclass(frozen=True)
class TechnicalAblationResult:
    outcomes: tuple[TechnicalAblationOutcome, ...]
    input_snapshot_set_hash: str
    variant_order: tuple[TechnicalAblationVariant, ...]
    policy_version: str
    result_hash: str


def _project_components(
    signal: TrendTransitionSignal,
    variant: TechnicalAblationVariant,
) -> dict[str, float | None]:
    values = dict(signal.normalized_components)
    if not signal.available:
        return values
    zeroed = {name: 0.0 for name in values}
    if variant is TechnicalAblationVariant.Q2_MA_GAP:
        for name in (
            "slow_gap_level",
            "slow_gap_momentum",
            "fast_gap_level",
            "fast_gap_momentum",
            "trend_score",
        ):
            zeroed[name] = values[name]
        zeroed["transition_score"] = values["fast_gap_momentum"]
        return zeroed
    if variant is TechnicalAblationVariant.Q2_RSI:
        zeroed["rsi_confirmation"] = values["rsi_confirmation"]
        zeroed["confirmation_score"] = values["rsi_confirmation"]
        zeroed["transition_score"] = values["rsi_confirmation"]
        return zeroed
    if variant is TechnicalAblationVariant.Q2_MACD:
        zeroed["macd_confirmation"] = values["macd_confirmation"]
        zeroed["confirmation_score"] = values["macd_confirmation"]
        zeroed["transition_score"] = values["macd_confirmation"]
        return zeroed
    if variant is TechnicalAblationVariant.Q2_COMBINED:
        return values
    raise ContractValidationError("market base does not project a technical signal")


def _project_reason_codes(
    components: dict[str, float | None],
    specification: TechnicalAblationSpecification,
    *,
    threshold: float,
) -> tuple[MarketReasonCode, ...]:
    transition = float(components["transition_score"])
    trend = float(components["trend_score"])
    reasons: list[MarketReasonCode] = []
    if "MA_GAP" in specification.enabled_feature_groups:
        if trend >= threshold:
            reasons.append(MarketReasonCode.TREND_UP_CONFIRMED)
        elif trend <= -threshold:
            reasons.append(MarketReasonCode.TREND_DOWN_CONFIRMED)
        else:
            reasons.append(MarketReasonCode.TREND_DIRECTION_MIXED)
    if transition >= threshold:
        reasons.append(MarketReasonCode.FAST_UPWARD_TRANSITION)
    elif transition <= -threshold:
        reasons.append(MarketReasonCode.FAST_DOWNWARD_TRANSITION)
    if "RSI" in specification.enabled_feature_groups:
        rsi = float(components["rsi_confirmation"])
        if rsi >= threshold:
            reasons.append(MarketReasonCode.RSI_RECOVERY_CONFIRMATION)
        elif rsi <= -threshold:
            reasons.append(MarketReasonCode.RSI_WEAKENING_CONFIRMATION)
    if "MACD" in specification.enabled_feature_groups:
        macd = float(components["macd_confirmation"])
        if macd >= threshold:
            reasons.append(MarketReasonCode.MACD_UP_CONFIRMATION)
        elif macd <= -threshold:
            reasons.append(MarketReasonCode.MACD_DOWN_CONFIRMATION)
    if "MA_GAP" in specification.enabled_feature_groups and trend * transition < 0.0:
        reasons.append(MarketReasonCode.TECHNICAL_SIGNAL_CONFLICT)
    return tuple(dict.fromkeys(reasons or [MarketReasonCode.TREND_DIRECTION_MIXED]))


def project_technical_signal(
    signal: TrendTransitionSignal,
    *,
    variant: TechnicalAblationVariant,
    direction_threshold: float = 0.20,
) -> TrendTransitionSignal | None:
    if variant is TechnicalAblationVariant.Q2_MARKET_BASE:
        return None
    if not 0.0 < direction_threshold < 1.0:
        raise ContractValidationError("ablation direction threshold must be between zero and one")
    specification = TECHNICAL_ABLATION_SPECIFICATIONS[variant]
    components = _project_components(signal, variant)
    rule_hash = canonical_sha256(
        {
            "base_rule_hash": signal.rule_hash,
            "specification_hash": specification.specification_hash(),
            "direction_threshold": direction_threshold,
        }
    )
    if not signal.available:
        return replace(
            signal,
            normalized_components=components,
            rule_version=f"{TECHNICAL_ABLATION_POLICY_VERSION}:{variant.value}",
            rule_hash=rule_hash,
        )
    transition_score = float(components["transition_score"])
    if transition_score >= direction_threshold:
        direction = TechnicalTransitionDirection.UP
    elif transition_score <= -direction_threshold:
        direction = TechnicalTransitionDirection.DOWN
    else:
        direction = TechnicalTransitionDirection.NEUTRAL
    return replace(
        signal,
        normalized_components=components,
        direction=direction,
        strength=min(1.0, abs(transition_score)),
        reason_codes=_project_reason_codes(
            components,
            specification,
            threshold=direction_threshold,
        ),
        rule_version=f"{TECHNICAL_ABLATION_POLICY_VERSION}:{variant.value}",
        rule_hash=rule_hash,
    )


def _outcome_payload(outcome: TechnicalAblationOutcome) -> dict[str, object]:
    score = outcome.candidate_score
    return {
        "variant": outcome.variant.value,
        "market_scope": outcome.market_scope.value,
        "decision_date": outcome.decision_date,
        "enabled_feature_groups": outcome.enabled_feature_groups,
        "feature_snapshot_hash": outcome.feature_snapshot_hash,
        "projected_signal_hash": outcome.projected_signal_hash,
        "specification_hash": outcome.specification_hash,
        "scoring_rule_hash": outcome.scoring_rule_hash,
        "structure": outcome.structure.value,
        "stage": outcome.stage.value,
        "canonical_trend_value": outcome.canonical_trend_value,
        "technical_trend_score": outcome.technical_trend_score,
        "transition_score": outcome.transition_score,
        "transition_direction": (
            outcome.transition_direction.value if outcome.transition_direction else None
        ),
        "candidate_score": {
            "decision_date": score.decision_date,
            "structure": score.structure.value,
            "stage": score.stage.value,
            "structure_scores": {
                key.value: value for key, value in score.structure_scores.items()
            },
            "stage_scores": {
                key.value: value for key, value in score.stage_scores.items()
            },
            "stage_probabilities": {
                key.value: value for key, value in score.stage_probabilities.items()
            },
            "probability_status": score.probability_status.value,
            "stage_score_margin": score.stage_score_margin,
            "signal_alignment": score.signal_alignment,
            "canonical_axis_values": {
                key.value: value for key, value in score.canonical_axis_values.items()
            },
            "reason_codes": [item.value for item in score.reason_codes],
            "rule_version": score.rule_version,
            "rule_hash": score.rule_hash,
        },
    }


def evaluate_technical_ablation(
    snapshots: tuple[MarketFeatureSnapshot, ...],
) -> TechnicalAblationResult:
    if not snapshots:
        raise ContractValidationError("technical ablation requires feature snapshots")
    keys = [(item.market_scope.value, item.decision_date) for item in snapshots]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise ContractValidationError("technical ablation snapshots must be unique and ordered")
    if any(item.trend_transition is None for item in snapshots):
        raise ContractValidationError("all ablation inputs require a technical signal contract")

    outcomes: list[TechnicalAblationOutcome] = []
    for snapshot in snapshots:
        for variant in TECHNICAL_ABLATION_VARIANTS:
            specification = TECHNICAL_ABLATION_SPECIFICATIONS[variant]
            projected_signal = project_technical_signal(
                snapshot.trend_transition,
                variant=variant,
            )
            projected_snapshot = replace(snapshot, trend_transition=projected_signal)
            scoring_policy = RegimeScoringPolicy(
                base_trend_weight=1.0 - specification.technical_trend_weight,
                technical_trend_weight=specification.technical_trend_weight,
            )
            score = score_market_regime(projected_snapshot, policy=scoring_policy)
            transition_score = (
                float(projected_signal.normalized_components["transition_score"])
                if projected_signal is not None and projected_signal.available
                else None
            )
            technical_trend_score = (
                float(projected_signal.normalized_components["trend_score"])
                if projected_signal is not None
                and projected_signal.available
                and specification.technical_trend_weight > 0.0
                else None
            )
            base_fields = {
                "variant": variant,
                "market_scope": snapshot.market_scope,
                "decision_date": snapshot.decision_date,
                "enabled_feature_groups": specification.enabled_feature_groups,
                "feature_snapshot_hash": projected_snapshot.payload_hash(),
                "projected_signal_hash": (
                    projected_signal.payload_hash() if projected_signal is not None else None
                ),
                "specification_hash": specification.specification_hash(),
                "scoring_rule_hash": score.rule_hash,
                "structure": score.structure,
                "stage": score.stage,
                "canonical_trend_value": score.canonical_axis_values[MarketAxis.TREND],
                "technical_trend_score": technical_trend_score,
                "transition_score": transition_score,
                "transition_direction": (
                    projected_signal.direction if projected_signal is not None else None
                ),
                "candidate_score": score,
            }
            provisional = TechnicalAblationOutcome(**base_fields, outcome_hash="")
            outcomes.append(
                replace(provisional, outcome_hash=canonical_sha256(_outcome_payload(provisional)))
            )

    input_hash = canonical_sha256([item.payload_hash() for item in snapshots])
    result_payload = {
        "input_snapshot_set_hash": input_hash,
        "variant_order": [variant.value for variant in TECHNICAL_ABLATION_VARIANTS],
        "policy_version": TECHNICAL_ABLATION_POLICY_VERSION,
        "outcomes": [_outcome_payload(item) | {"outcome_hash": item.outcome_hash} for item in outcomes],
    }
    return TechnicalAblationResult(
        outcomes=tuple(outcomes),
        input_snapshot_set_hash=input_hash,
        variant_order=TECHNICAL_ABLATION_VARIANTS,
        policy_version=TECHNICAL_ABLATION_POLICY_VERSION,
        result_hash=canonical_sha256(result_payload),
    )
