from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

from src.quant2.contracts.market_features import MarketFeatureSnapshot
from src.quant2.contracts.market_regime import ContractValidationError, MarketReasonCode, canonical_sha256
from src.quant2.contracts.market_technical_features import (
    TechnicalFeatureStatus,
    TechnicalIndicatorSnapshot,
)
from src.quant2.contracts.trend_transition import (
    TREND_TRANSITION_COMPONENTS,
    TechnicalTransitionDirection,
    TrendTransitionSignal,
)

TREND_TRANSITION_RULE_VERSION = "quant2.trend_transition.v2"


@dataclass(frozen=True)
class TrendTransitionPolicy:
    slow_gap_scale: float = 0.05
    fast_gap_scale: float = 0.03
    gap_delta_1d_scale: float = 0.005
    gap_delta_3d_scale: float = 0.012
    gap_delta_5d_scale: float = 0.020
    rsi_level_scale: float = 20.0
    rsi_delta_1d_scale: float = 4.0
    rsi_delta_3d_scale: float = 10.0
    rsi_delta_5d_scale: float = 15.0
    macd_level_pct_scale: float = 0.010
    macd_delta_pct_scale: float = 0.005
    direction_threshold: float = 0.20
    continuation_level_weight: float = 0.80
    continuation_momentum_weight: float = 0.20
    trend_continuation_weight: float = 0.65
    trend_fast_level_weight: float = 0.35
    transition_fast_momentum_weight: float = 0.65
    transition_confirmation_weight: float = 0.35
    confirmation_rsi_weight: float = 0.60
    confirmation_macd_weight: float = 0.40
    version: str = TREND_TRANSITION_RULE_VERSION

    def __post_init__(self) -> None:
        positive_fields = (
            "slow_gap_scale",
            "fast_gap_scale",
            "gap_delta_1d_scale",
            "gap_delta_3d_scale",
            "gap_delta_5d_scale",
            "rsi_level_scale",
            "rsi_delta_1d_scale",
            "rsi_delta_3d_scale",
            "rsi_delta_5d_scale",
            "macd_level_pct_scale",
            "macd_delta_pct_scale",
        )
        if any(
            not math.isfinite(getattr(self, field)) or getattr(self, field) <= 0.0
            for field in positive_fields
        ):
            raise ContractValidationError("trend transition scales must be finite and positive")
        if not 0.0 < self.direction_threshold < 1.0:
            raise ContractValidationError("direction_threshold must be between 0 and 1")
        weight_groups = (
            (self.continuation_level_weight, self.continuation_momentum_weight),
            (self.trend_continuation_weight, self.trend_fast_level_weight),
            (self.transition_fast_momentum_weight, self.transition_confirmation_weight),
            (self.confirmation_rsi_weight, self.confirmation_macd_weight),
        )
        if any(
            any(weight < 0.0 for weight in weights)
            or not math.isclose(sum(weights), 1.0, abs_tol=1e-12)
            for weights in weight_groups
        ):
            raise ContractValidationError("trend transition weight groups must sum to one")
        if not self.version.strip():
            raise ContractValidationError("trend transition version is required")

    def rule_manifest(self) -> dict[str, object]:
        manifest = asdict(self)
        manifest["gap_momentum_lag_weights"] = {"1d": 0.50, "3d": 0.30, "5d": 0.20}
        manifest["rsi_momentum_lag_weights"] = {"1d": 0.20, "3d": 0.30, "5d": 0.50}
        manifest["macd_confirmation_total_transition_weight"] = (
            self.transition_confirmation_weight * self.confirmation_macd_weight
        )
        manifest["rsi_overbought_rule"] = "RSI above 70 alone never creates a down signal"
        manifest["macd_rule"] = "confirmation only; never an independent additive market axis"
        return manifest

    def rule_hash(self) -> str:
        return canonical_sha256(self.rule_manifest())


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _weighted(values: tuple[float, ...], weights: tuple[float, ...]) -> float:
    return sum(value * weight for value, weight in zip(values, weights))


def build_trend_transition_signal(
    snapshot: TechnicalIndicatorSnapshot,
    *,
    policy: TrendTransitionPolicy | None = None,
) -> TrendTransitionSignal:
    applied_policy = policy or TrendTransitionPolicy()
    rule_hash = applied_policy.rule_hash()
    raw_values = dict(snapshot.values)
    if snapshot.status is not TechnicalFeatureStatus.READY:
        return TrendTransitionSignal(
            market_scope=snapshot.market_scope,
            observation_date=snapshot.observation_date,
            available_at=snapshot.available_at,
            available=False,
            raw_values=raw_values,
            normalized_components={name: None for name in TREND_TRANSITION_COMPONENTS},
            direction=None,
            strength=None,
            reason_codes=(MarketReasonCode.TECHNICAL_FEATURE_UNAVAILABLE,),
            source_snapshot_hash=snapshot.source_snapshot_hash,
            technical_rule_hash=snapshot.rule_hash,
            rule_version=applied_policy.version,
            rule_hash=rule_hash,
        )

    def value(name: str) -> float:
        item = raw_values[name]
        if item is None:
            raise ContractValidationError(f"ready technical snapshot has null {name}")
        return float(item)

    slow_gap_level = _clip(value("gap_20_60") / applied_policy.slow_gap_scale)
    slow_gap_momentum = _weighted(
        (
            _clip(value("gap_20_60_delta_1d") / applied_policy.gap_delta_1d_scale),
            _clip(value("gap_20_60_delta_3d") / applied_policy.gap_delta_3d_scale),
            _clip(value("gap_20_60_delta_5d") / applied_policy.gap_delta_5d_scale),
        ),
        (0.50, 0.30, 0.20),
    )
    fast_gap_level = _clip(value("gap_5_20") / applied_policy.fast_gap_scale)
    fast_gap_momentum = _weighted(
        (
            _clip(value("gap_5_20_delta_1d") / applied_policy.gap_delta_1d_scale),
            _clip(value("gap_5_20_delta_3d") / applied_policy.gap_delta_3d_scale),
            _clip(value("gap_5_20_delta_5d") / applied_policy.gap_delta_5d_scale),
        ),
        (0.50, 0.30, 0.20),
    )
    rsi_level = _clip((value("rsi14") - 50.0) / applied_policy.rsi_level_scale)
    rsi_momentum = _weighted(
        (
            _clip(value("rsi14_delta_1d") / applied_policy.rsi_delta_1d_scale),
            _clip(value("rsi14_delta_3d") / applied_policy.rsi_delta_3d_scale),
            _clip(value("rsi14_delta_5d") / applied_policy.rsi_delta_5d_scale),
        ),
        (0.20, 0.30, 0.50),
    )
    rsi_confirmation = _clip(0.30 * rsi_level + 0.70 * rsi_momentum)
    scale_base = value("sma20")
    if scale_base <= 0.0:
        raise ContractValidationError("sma20 must be positive for MACD normalization")
    macd_level = _clip(
        value("macd_histogram") / scale_base / applied_policy.macd_level_pct_scale
    )
    macd_momentum = _weighted(
        tuple(
            _clip(
                value(f"macd_histogram_delta_{lag}d")
                / scale_base
                / applied_policy.macd_delta_pct_scale
            )
            for lag in (1, 3, 5)
        ),
        (0.50, 0.30, 0.20),
    )
    macd_confirmation = _clip(0.50 * macd_level + 0.50 * macd_momentum)
    confirmation_score = _clip(
        applied_policy.confirmation_rsi_weight * rsi_confirmation
        + applied_policy.confirmation_macd_weight * macd_confirmation
    )
    continuation_score = _clip(
        applied_policy.continuation_level_weight * slow_gap_level
        + applied_policy.continuation_momentum_weight * slow_gap_momentum
    )
    trend_score = _clip(
        applied_policy.trend_continuation_weight * continuation_score
        + applied_policy.trend_fast_level_weight * fast_gap_level
    )
    transition_score = _clip(
        applied_policy.transition_fast_momentum_weight * fast_gap_momentum
        + applied_policy.transition_confirmation_weight * confirmation_score
    )
    if transition_score >= applied_policy.direction_threshold:
        direction = TechnicalTransitionDirection.UP
    elif transition_score <= -applied_policy.direction_threshold:
        direction = TechnicalTransitionDirection.DOWN
    else:
        direction = TechnicalTransitionDirection.NEUTRAL

    reasons: list[MarketReasonCode] = []
    if continuation_score > applied_policy.direction_threshold:
        reasons.append(MarketReasonCode.TREND_UP_CONFIRMED)
    elif continuation_score < -applied_policy.direction_threshold:
        reasons.append(MarketReasonCode.TREND_DOWN_CONFIRMED)
    else:
        reasons.append(MarketReasonCode.TREND_DIRECTION_MIXED)
    if direction is TechnicalTransitionDirection.UP:
        reasons.append(MarketReasonCode.FAST_UPWARD_TRANSITION)
    elif direction is TechnicalTransitionDirection.DOWN:
        reasons.append(MarketReasonCode.FAST_DOWNWARD_TRANSITION)
    if rsi_confirmation >= applied_policy.direction_threshold:
        reasons.append(MarketReasonCode.RSI_RECOVERY_CONFIRMATION)
    elif rsi_confirmation <= -applied_policy.direction_threshold:
        reasons.append(MarketReasonCode.RSI_WEAKENING_CONFIRMATION)
    if macd_confirmation >= applied_policy.direction_threshold:
        reasons.append(MarketReasonCode.MACD_UP_CONFIRMATION)
    elif macd_confirmation <= -applied_policy.direction_threshold:
        reasons.append(MarketReasonCode.MACD_DOWN_CONFIRMATION)
    if continuation_score * transition_score < 0.0:
        reasons.append(MarketReasonCode.TECHNICAL_SIGNAL_CONFLICT)

    components = {
        "slow_gap_level": slow_gap_level,
        "slow_gap_momentum": slow_gap_momentum,
        "fast_gap_level": fast_gap_level,
        "fast_gap_momentum": fast_gap_momentum,
        "rsi_confirmation": rsi_confirmation,
        "macd_confirmation": macd_confirmation,
        "confirmation_score": confirmation_score,
        "trend_score": trend_score,
        "transition_score": transition_score,
    }
    return TrendTransitionSignal(
        market_scope=snapshot.market_scope,
        observation_date=snapshot.observation_date,
        available_at=snapshot.available_at,
        available=True,
        raw_values=raw_values,
        normalized_components={key: round(value, 12) for key, value in components.items()},
        direction=direction,
        strength=round(abs(transition_score), 12),
        reason_codes=tuple(dict.fromkeys(reasons)),
        source_snapshot_hash=snapshot.source_snapshot_hash,
        technical_rule_hash=snapshot.rule_hash,
        rule_version=applied_policy.version,
        rule_hash=rule_hash,
    )


def attach_trend_transition_signal(
    feature_snapshot: MarketFeatureSnapshot,
    technical_snapshot: TechnicalIndicatorSnapshot,
    *,
    policy: TrendTransitionPolicy | None = None,
) -> MarketFeatureSnapshot:
    signal = build_trend_transition_signal(technical_snapshot, policy=policy)
    return replace(feature_snapshot, trend_transition=signal)
