from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date

from src.quant2.contracts.market_regime import (
    STAGE_STRUCTURE,
    ContractValidationError,
    MarketReasonCode,
    MarketStage,
    MarketStructure,
    canonical_sha256,
)
from src.quant2.market_regime.scoring import RegimeScoreResult

TRANSITION_POLICY_VERSION = "quant2.market_transition.v1"
TRANSITION_POLICY_V2_VERSION = "quant2.market_transition.v2"

STAGE_CYCLE = (
    MarketStage.DOWNTREND_CONTINUATION,
    MarketStage.DOWNTREND_EXHAUSTION,
    MarketStage.RANGE_ACCUMULATION,
    MarketStage.UPTREND_INITIATION,
    MarketStage.UPTREND_CONTINUATION,
    MarketStage.UPTREND_EXHAUSTION,
    MarketStage.RANGE_DISTRIBUTION,
    MarketStage.DOWNTREND_INITIATION,
)


@dataclass(frozen=True)
class TransitionPolicy:
    minimum_state_days: int = 3
    confirmation_days: int = 2
    structure_entry_margin: float = 0.08
    stage_entry_margin: float = 0.05
    pending_release_margin: float = 0.02
    max_stage_steps_per_day: int = 1
    version: str = TRANSITION_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.minimum_state_days < 1:
            raise ContractValidationError("minimum_state_days must be positive")
        if self.confirmation_days < 1:
            raise ContractValidationError("confirmation_days must be positive")
        for field_name in (
            "structure_entry_margin",
            "stage_entry_margin",
            "pending_release_margin",
        ):
            value = getattr(self, field_name)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ContractValidationError(f"{field_name} must be between 0 and 1")
        if self.pending_release_margin >= min(self.structure_entry_margin, self.stage_entry_margin):
            raise ContractValidationError("pending_release_margin must be below entry margins")
        if self.max_stage_steps_per_day != 1:
            raise ContractValidationError("research v1 permits exactly one stage step per day")
        if not self.version.strip():
            raise ContractValidationError("transition policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class TransitionPolicyV2:
    """Confirm the raw candidate, then move directly instead of cycling stages."""

    minimum_state_days: int = 3
    confirmation_days: int = 2
    structure_entry_margin: float = 0.08
    stage_entry_margin: float = 0.05
    pending_release_margin: float = 0.02
    version: str = TRANSITION_POLICY_V2_VERSION

    def __post_init__(self) -> None:
        if self.minimum_state_days < 1:
            raise ContractValidationError("minimum_state_days must be positive")
        if self.confirmation_days < 1:
            raise ContractValidationError("confirmation_days must be positive")
        for field_name in (
            "structure_entry_margin",
            "stage_entry_margin",
            "pending_release_margin",
        ):
            value = getattr(self, field_name)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ContractValidationError(f"{field_name} must be between 0 and 1")
        if self.pending_release_margin >= min(
            self.structure_entry_margin, self.stage_entry_margin
        ):
            raise ContractValidationError("pending_release_margin must be below entry margins")
        if not self.version.strip():
            raise ContractValidationError("transition policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class RegimeTransitionState:
    decision_date: date
    structure: MarketStructure
    stage: MarketStage
    days_in_state: int
    pending_stage: MarketStage | None = None
    pending_days: int = 0

    def __post_init__(self) -> None:
        if STAGE_STRUCTURE[self.stage] is not self.structure:
            raise ContractValidationError("transition state stage does not belong to structure")
        if self.days_in_state < 1:
            raise ContractValidationError("days_in_state must be positive")
        if self.pending_stage is None and self.pending_days != 0:
            raise ContractValidationError("pending_days requires pending_stage")
        if self.pending_stage is not None and self.pending_days < 1:
            raise ContractValidationError("pending_stage requires positive pending_days")
        if self.pending_stage is self.stage:
            raise ContractValidationError("pending_stage must differ from current stage")


@dataclass(frozen=True)
class TransitionDecision:
    state: RegimeTransitionState
    candidate_structure: MarketStructure
    candidate_stage: MarketStage
    applied_structure: MarketStructure
    applied_stage: MarketStage
    changed: bool
    candidate_advantage: float
    reason_codes: tuple[MarketReasonCode, ...]
    policy_version: str
    policy_hash: str


def _candidate_advantage(previous: RegimeTransitionState, candidate: RegimeScoreResult) -> tuple[float, bool]:
    if candidate.structure is previous.structure:
        advantage = candidate.stage_scores[candidate.stage] - candidate.stage_scores[previous.stage]
        return advantage, False
    advantage = (
        candidate.structure_scores[candidate.structure]
        - candidate.structure_scores[previous.structure]
    )
    return advantage, True


def _next_stage_toward(current: MarketStage, target: MarketStage) -> MarketStage:
    current_index = STAGE_CYCLE.index(current)
    target_index = STAGE_CYCLE.index(target)
    forward_steps = (target_index - current_index) % len(STAGE_CYCLE)
    backward_steps = (current_index - target_index) % len(STAGE_CYCLE)
    if forward_steps <= backward_steps:
        return STAGE_CYCLE[(current_index + 1) % len(STAGE_CYCLE)]
    return STAGE_CYCLE[(current_index - 1) % len(STAGE_CYCLE)]


def apply_regime_transition(
    previous: RegimeTransitionState | None,
    candidate: RegimeScoreResult,
    *,
    policy: TransitionPolicy | TransitionPolicyV2 | None = None,
) -> TransitionDecision:
    applied_policy = policy or TransitionPolicy()
    policy_hash = applied_policy.policy_hash()

    if previous is None:
        state = RegimeTransitionState(
            decision_date=candidate.decision_date,
            structure=candidate.structure,
            stage=candidate.stage,
            days_in_state=1,
        )
        return TransitionDecision(
            state=state,
            candidate_structure=candidate.structure,
            candidate_stage=candidate.stage,
            applied_structure=state.structure,
            applied_stage=state.stage,
            changed=True,
            candidate_advantage=1.0,
            reason_codes=(MarketReasonCode.STATE_INITIALIZED,),
            policy_version=applied_policy.version,
            policy_hash=policy_hash,
        )

    if candidate.decision_date <= previous.decision_date:
        raise ContractValidationError("candidate decision_date must be after previous state")

    if candidate.stage is previous.stage:
        state = RegimeTransitionState(
            decision_date=candidate.decision_date,
            structure=previous.structure,
            stage=previous.stage,
            days_in_state=previous.days_in_state + 1,
        )
        return TransitionDecision(
            state=state,
            candidate_structure=candidate.structure,
            candidate_stage=candidate.stage,
            applied_structure=state.structure,
            applied_stage=state.stage,
            changed=False,
            candidate_advantage=0.0,
            reason_codes=(),
            policy_version=applied_policy.version,
            policy_hash=policy_hash,
        )

    advantage, structure_change = _candidate_advantage(previous, candidate)
    entry_margin = (
        applied_policy.structure_entry_margin
        if structure_change
        else applied_policy.stage_entry_margin
    )
    reasons: list[MarketReasonCode] = []

    if previous.pending_stage is candidate.stage:
        if advantage >= applied_policy.pending_release_margin:
            pending_stage = candidate.stage
            pending_days = previous.pending_days + 1
        else:
            pending_stage = None
            pending_days = 0
            reasons.append(MarketReasonCode.STATE_HYSTERESIS_HELD)
    elif advantage >= entry_margin:
        pending_stage = candidate.stage
        pending_days = 1
    else:
        pending_stage = None
        pending_days = 0
        reasons.append(MarketReasonCode.STATE_HYSTERESIS_HELD)

    if previous.days_in_state < applied_policy.minimum_state_days:
        reasons.append(MarketReasonCode.MIN_DURATION_HELD)
    if pending_days < applied_policy.confirmation_days:
        reasons.append(MarketReasonCode.STATE_HYSTERESIS_HELD)

    can_change = (
        previous.days_in_state >= applied_policy.minimum_state_days
        and pending_stage is not None
        and pending_days >= applied_policy.confirmation_days
    )
    if not can_change:
        state = RegimeTransitionState(
            decision_date=candidate.decision_date,
            structure=previous.structure,
            stage=previous.stage,
            days_in_state=previous.days_in_state + 1,
            pending_stage=pending_stage,
            pending_days=pending_days,
        )
        return TransitionDecision(
            state=state,
            candidate_structure=candidate.structure,
            candidate_stage=candidate.stage,
            applied_structure=state.structure,
            applied_stage=state.stage,
            changed=False,
            candidate_advantage=round(advantage, 12),
            reason_codes=tuple(dict.fromkeys(reasons)),
            policy_version=applied_policy.version,
            policy_hash=policy_hash,
        )

    direct_transition = isinstance(applied_policy, TransitionPolicyV2)
    applied_stage = (
        candidate.stage
        if direct_transition
        else _next_stage_toward(previous.stage, candidate.stage)
    )
    if not direct_transition and applied_stage is not candidate.stage:
        reasons.append(MarketReasonCode.STATE_CHANGE_STEP_LIMITED)
    reasons.append(MarketReasonCode.STATE_CHANGE_CONFIRMED)
    state = RegimeTransitionState(
        decision_date=candidate.decision_date,
        structure=STAGE_STRUCTURE[applied_stage],
        stage=applied_stage,
        days_in_state=1,
    )
    return TransitionDecision(
        state=state,
        candidate_structure=candidate.structure,
        candidate_stage=candidate.stage,
        applied_structure=state.structure,
        applied_stage=state.stage,
        changed=True,
        candidate_advantage=round(advantage, 12),
        reason_codes=tuple(dict.fromkeys(reasons)),
        policy_version=applied_policy.version,
        policy_hash=policy_hash,
    )
