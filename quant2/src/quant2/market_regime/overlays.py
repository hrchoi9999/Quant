from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from src.quant2.contracts.market_features import MarketFeatureSnapshot
from src.quant2.contracts.market_overlays import OverlayInputs
from src.quant2.contracts.market_regime import (
    EXPECTED_PRIMARY_LABEL,
    ContractValidationError,
    MarketAxis,
    MarketReasonCode,
    MarketStage,
    MarketStructure,
    ObservedMarketState,
    PrimaryTransitionLabel,
    RiskAppetite,
    ShortTermPriceShock,
    TransitionState,
    VolatilityState,
    canonical_sha256,
)
from src.quant2.market_regime.confidence import ConfidenceResult
from src.quant2.market_regime.scoring import RegimeScoreResult
from src.quant2.market_regime.short_term_shock import (
    ShortTermShockPolicy,
    calculate_short_term_shock,
)
from src.quant2.market_regime.transition import TransitionDecision

OVERLAY_POLICY_VERSION = "quant2.market_overlays.v2"
OBSERVED_ASSEMBLY_VERSION = "quant2.observed_market_assembly.v1"

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
CONTINUATION_STAGES = frozenset(
    {
        MarketStage.UPTREND_CONTINUATION,
        MarketStage.DOWNTREND_CONTINUATION,
    }
)


@dataclass(frozen=True)
class OverlayPolicy:
    risk_on_strong_threshold: float = 0.65
    risk_on_threshold: float = 0.20
    risk_off_threshold: float = -0.20
    risk_off_strong_threshold: float = -0.65
    volatility_calm_threshold: float = -0.75
    volatility_elevated_threshold: float = 0.75
    volatility_stress_threshold: float = 1.75
    transition_probability_threshold: float = 0.55
    transition_probability_gap: float = 0.10
    short_term_shock: ShortTermShockPolicy = field(default_factory=ShortTermShockPolicy)
    version: str = OVERLAY_POLICY_VERSION

    def __post_init__(self) -> None:
        if not (
            1.0 >= self.risk_on_strong_threshold > self.risk_on_threshold > self.risk_off_threshold
            > self.risk_off_strong_threshold >= -1.0
        ):
            raise ContractValidationError("risk appetite thresholds must be strictly descending")
        if not (
            self.volatility_calm_threshold
            < self.volatility_elevated_threshold
            < self.volatility_stress_threshold
        ):
            raise ContractValidationError("volatility thresholds must be strictly increasing")
        for field_name in ("transition_probability_threshold", "transition_probability_gap"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ContractValidationError(f"{field_name} must be between 0 and 1")
        if not self.version.strip():
            raise ContractValidationError("overlay policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class MarketOverlayResult:
    risk_appetite: RiskAppetite
    volatility_state: VolatilityState
    transition: TransitionState
    short_term_price_shock: ShortTermPriceShock
    shock_flag: bool
    shock_reason_codes: tuple[MarketReasonCode, ...]
    upward_transition_probability: float
    downward_transition_probability: float
    continuation_probability: float
    primary_transition_label: PrimaryTransitionLabel
    primary_transition_probability: float
    transition_confidence: float
    reason_codes: tuple[MarketReasonCode, ...]
    policy_version: str
    policy_hash: str

    def __post_init__(self) -> None:
        probabilities = (
            self.upward_transition_probability,
            self.downward_transition_probability,
            self.continuation_probability,
            self.primary_transition_probability,
            self.transition_confidence,
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities):
            raise ContractValidationError("overlay probabilities and confidence must be between 0 and 1")
        if not math.isclose(sum(probabilities[:3]), 1.0, abs_tol=1e-9):
            raise ContractValidationError("overlay transition probabilities must sum to 1")
        if self.shock_flag != bool(self.shock_reason_codes):
            raise ContractValidationError("shock flag and shock reason codes must agree")
        if not self.policy_version.strip():
            raise ContractValidationError("overlay policy version is required")
        if len(self.policy_hash) != 64 or any(character not in "0123456789ABCDEF" for character in self.policy_hash):
            raise ContractValidationError("overlay policy hash must be uppercase SHA-256 hex")


@dataclass(frozen=True)
class ObservedAssemblyResult:
    observed: ObservedMarketState
    rule_version: str
    rule_hash: str
    overlay: MarketOverlayResult


def _risk_appetite(score: float, policy: OverlayPolicy) -> RiskAppetite:
    if score >= policy.risk_on_strong_threshold:
        return RiskAppetite.RISK_ON_STRONG
    if score >= policy.risk_on_threshold:
        return RiskAppetite.RISK_ON
    if score > policy.risk_off_threshold:
        return RiskAppetite.BALANCED
    if score > policy.risk_off_strong_threshold:
        return RiskAppetite.RISK_OFF
    return RiskAppetite.RISK_OFF_STRONG


def _volatility_state(zscore: float, policy: OverlayPolicy) -> VolatilityState:
    if zscore <= policy.volatility_calm_threshold:
        return VolatilityState.CALM
    if zscore < policy.volatility_elevated_threshold:
        return VolatilityState.NORMAL
    if zscore < policy.volatility_stress_threshold:
        return VolatilityState.ELEVATED
    return VolatilityState.STRESS


def calculate_market_overlays(
    scoring: RegimeScoreResult,
    transition_decision: TransitionDecision,
    inputs: OverlayInputs,
    *,
    policy: OverlayPolicy | None = None,
) -> MarketOverlayResult:
    applied_policy = policy or OverlayPolicy()
    if inputs.decision_date != scoring.decision_date or inputs.decision_date != transition_decision.state.decision_date:
        raise ContractValidationError("overlay input, scoring and transition dates must match")
    if (
        transition_decision.candidate_structure is not scoring.structure
        or transition_decision.candidate_stage is not scoring.stage
    ):
        raise ContractValidationError("transition candidate must match scoring result")
    risk_score = scoring.canonical_axis_values[MarketAxis.RISK_LIQUIDITY]
    if risk_score is None:
        raise ContractValidationError("risk_liquidity axis is required for risk appetite overlay")

    risk_appetite = _risk_appetite(risk_score, applied_policy)
    volatility_state = _volatility_state(inputs.volatility_zscore, applied_policy)
    shock = calculate_short_term_shock(
        inputs,
        policy=applied_policy.short_term_shock,
    )
    short_term_price_shock = shock.price_shock
    probabilities = scoring.stage_probabilities
    upward = sum(probabilities[stage] for stage in UPWARD_TRANSITION_STAGES)
    downward = sum(probabilities[stage] for stage in DOWNWARD_TRANSITION_STAGES)
    continuation = sum(probabilities[stage] for stage in CONTINUATION_STAGES)

    if (
        upward >= applied_policy.transition_probability_threshold
        and upward - downward >= applied_policy.transition_probability_gap
    ):
        transition = TransitionState.TRANSITION_UP
    elif (
        downward >= applied_policy.transition_probability_threshold
        and downward - upward >= applied_policy.transition_probability_gap
    ):
        transition = TransitionState.TRANSITION_DOWN
    else:
        transition = TransitionState.NONE

    reasons: list[MarketReasonCode] = []
    if risk_appetite in (RiskAppetite.RISK_ON, RiskAppetite.RISK_ON_STRONG):
        reasons.append(MarketReasonCode.RISK_APPETITE_IMPROVING)
    elif risk_appetite in (RiskAppetite.RISK_OFF, RiskAppetite.RISK_OFF_STRONG):
        reasons.append(MarketReasonCode.RISK_APPETITE_WEAKENING)
    if volatility_state is VolatilityState.ELEVATED:
        reasons.append(MarketReasonCode.VOLATILITY_ELEVATED)
    elif volatility_state is VolatilityState.STRESS:
        reasons.append(MarketReasonCode.VOLATILITY_STRESS)
    reasons.extend(shock.reason_codes)

    applied_structure = transition_decision.applied_structure
    primary_label = EXPECTED_PRIMARY_LABEL[applied_structure]
    if applied_structure is MarketStructure.DOWNTREND:
        primary_probability = upward
    elif applied_structure is MarketStructure.UPTREND:
        primary_probability = downward
    else:
        primary_probability = max(upward, downward)

    return MarketOverlayResult(
        risk_appetite=risk_appetite,
        volatility_state=volatility_state,
        transition=transition,
        short_term_price_shock=short_term_price_shock,
        shock_flag=shock.stress_flag,
        shock_reason_codes=shock.stress_reason_codes,
        upward_transition_probability=round(upward, 12),
        downward_transition_probability=round(downward, 12),
        continuation_probability=round(continuation, 12),
        primary_transition_label=primary_label,
        primary_transition_probability=round(primary_probability, 12),
        transition_confidence=round(abs(upward - downward), 12),
        reason_codes=tuple(dict.fromkeys(reasons)),
        policy_version=applied_policy.version,
        policy_hash=applied_policy.policy_hash(),
    )


def assemble_observed_market_state(
    snapshot: MarketFeatureSnapshot,
    scoring: RegimeScoreResult,
    confidence: ConfidenceResult,
    transition_decision: TransitionDecision,
    overlay_inputs: OverlayInputs,
    *,
    overlay_policy: OverlayPolicy | None = None,
) -> ObservedAssemblyResult:
    if snapshot.decision_date != scoring.decision_date:
        raise ContractValidationError("snapshot and scoring dates must match")
    expected_coverage = {
        axis.value: snapshot.axis_map()[axis].effective_coverage for axis in MarketAxis
    }
    if confidence.effective_coverage_by_axis != expected_coverage:
        raise ContractValidationError("confidence coverage must match feature snapshot")
    overlay = calculate_market_overlays(
        scoring,
        transition_decision,
        overlay_inputs,
        policy=overlay_policy,
    )
    axis_map = snapshot.axis_map()
    raw_axis_scores = {axis.value: axis_map[axis].raw_score for axis in MarketAxis}
    normalized_axis_scores = {
        axis.value: axis_map[axis].normalized_score for axis in MarketAxis
    }
    reason_codes = tuple(
        dict.fromkeys(
            (
                *scoring.reason_codes,
                *confidence.reason_codes,
                *transition_decision.reason_codes,
                *overlay.reason_codes,
            )
        )
    )
    observed = ObservedMarketState(
        structure=transition_decision.applied_structure,
        stage=transition_decision.applied_stage,
        stage_probabilities=scoring.stage_probabilities,
        probability_status=scoring.probability_status,
        risk_appetite=overlay.risk_appetite,
        volatility_state=overlay.volatility_state,
        transition=overlay.transition,
        short_term_price_shock=overlay.short_term_price_shock,
        shock_flag=overlay.shock_flag,
        shock_reason_codes=overlay.shock_reason_codes,
        upward_transition_probability=overlay.upward_transition_probability,
        downward_transition_probability=overlay.downward_transition_probability,
        continuation_probability=overlay.continuation_probability,
        primary_transition_label=overlay.primary_transition_label,
        primary_transition_probability=overlay.primary_transition_probability,
        transition_confidence=overlay.transition_confidence,
        confidence_score=confidence.score,
        confidence_level=confidence.level,
        raw_axis_scores=raw_axis_scores,
        normalized_axis_scores=normalized_axis_scores,
        reason_codes=reason_codes,
    )
    rule_version = OBSERVED_ASSEMBLY_VERSION
    rule_hash = canonical_sha256(
        {
            "version": rule_version,
            "scoring_rule_hash": scoring.rule_hash,
            "confidence_policy_hash": confidence.policy_hash,
            "transition_policy_hash": transition_decision.policy_hash,
            "overlay_policy_hash": overlay.policy_hash,
        }
    )
    return ObservedAssemblyResult(
        observed=observed,
        rule_version=rule_version,
        rule_hash=rule_hash,
        overlay=overlay,
    )
