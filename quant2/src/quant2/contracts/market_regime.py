from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

SCHEMA_VERSION = "quant2.market_regime.v2"
REASON_CODE_VERSION = "quant2.market_reason_codes.v2"
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")


class ContractValidationError(ValueError):
    """Raised when a Quant 2.0 contract violates PIT or schema invariants."""


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class MarketScope(_StringEnum):
    ALL = "ALL"
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


class MarketAxis(_StringEnum):
    TREND = "trend"
    BREADTH = "breadth"
    RISK_LIQUIDITY = "risk_liquidity"
    MACRO_EARNINGS = "macro_earnings"


AXIS_NAMES = frozenset(axis.value for axis in MarketAxis)


class MarketStructure(_StringEnum):
    UPTREND = "UPTREND"
    RANGE = "RANGE"
    DOWNTREND = "DOWNTREND"


class MarketStage(_StringEnum):
    UPTREND_INITIATION = "UPTREND_INITIATION"
    UPTREND_CONTINUATION = "UPTREND_CONTINUATION"
    UPTREND_EXHAUSTION = "UPTREND_EXHAUSTION"
    RANGE_ACCUMULATION = "RANGE_ACCUMULATION"
    RANGE_DISTRIBUTION = "RANGE_DISTRIBUTION"
    DOWNTREND_INITIATION = "DOWNTREND_INITIATION"
    DOWNTREND_CONTINUATION = "DOWNTREND_CONTINUATION"
    DOWNTREND_EXHAUSTION = "DOWNTREND_EXHAUSTION"


STAGE_STRUCTURE = {
    MarketStage.UPTREND_INITIATION: MarketStructure.UPTREND,
    MarketStage.UPTREND_CONTINUATION: MarketStructure.UPTREND,
    MarketStage.UPTREND_EXHAUSTION: MarketStructure.UPTREND,
    MarketStage.RANGE_ACCUMULATION: MarketStructure.RANGE,
    MarketStage.RANGE_DISTRIBUTION: MarketStructure.RANGE,
    MarketStage.DOWNTREND_INITIATION: MarketStructure.DOWNTREND,
    MarketStage.DOWNTREND_CONTINUATION: MarketStructure.DOWNTREND,
    MarketStage.DOWNTREND_EXHAUSTION: MarketStructure.DOWNTREND,
}


class RiskAppetite(_StringEnum):
    RISK_ON_STRONG = "RISK_ON_STRONG"
    RISK_ON = "RISK_ON"
    BALANCED = "BALANCED"
    RISK_OFF = "RISK_OFF"
    RISK_OFF_STRONG = "RISK_OFF_STRONG"


class VolatilityState(_StringEnum):
    CALM = "CALM"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    STRESS = "STRESS"


class TransitionState(_StringEnum):
    TRANSITION_UP = "TRANSITION_UP"
    TRANSITION_DOWN = "TRANSITION_DOWN"
    NONE = "NONE"


class ShortTermPriceShock(_StringEnum):
    SURGE = "SURGE"
    STRONG_RISE = "STRONG_RISE"
    NORMAL = "NORMAL"
    STRONG_FALL = "STRONG_FALL"
    CRASH = "CRASH"
    UNAVAILABLE = "UNAVAILABLE"


class ConfidenceLevel(_StringEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ProbabilityStatus(_StringEnum):
    PROVISIONAL = "PROVISIONAL"
    CALIBRATED = "CALIBRATED"


class ForecastLabel(_StringEnum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"


class PrimaryTransitionLabel(_StringEnum):
    UPWARD_TRANSITION_POTENTIAL = "UPWARD_TRANSITION_POTENTIAL"
    DOWNWARD_TRANSITION_POTENTIAL = "DOWNWARD_TRANSITION_POTENTIAL"
    BREAKOUT_BREAKDOWN_POTENTIAL = "BREAKOUT_BREAKDOWN_POTENTIAL"


class MarketReasonCode(_StringEnum):
    TREND_UP_CONFIRMED = "TREND_UP_CONFIRMED"
    TREND_DOWN_CONFIRMED = "TREND_DOWN_CONFIRMED"
    TREND_DIRECTION_MIXED = "TREND_DIRECTION_MIXED"
    FAST_UPWARD_TRANSITION = "FAST_UPWARD_TRANSITION"
    FAST_DOWNWARD_TRANSITION = "FAST_DOWNWARD_TRANSITION"
    RSI_RECOVERY_CONFIRMATION = "RSI_RECOVERY_CONFIRMATION"
    RSI_WEAKENING_CONFIRMATION = "RSI_WEAKENING_CONFIRMATION"
    MACD_UP_CONFIRMATION = "MACD_UP_CONFIRMATION"
    MACD_DOWN_CONFIRMATION = "MACD_DOWN_CONFIRMATION"
    TECHNICAL_SIGNAL_CONFLICT = "TECHNICAL_SIGNAL_CONFLICT"
    TECHNICAL_FEATURE_UNAVAILABLE = "TECHNICAL_FEATURE_UNAVAILABLE"
    BREADTH_IMPROVING = "BREADTH_IMPROVING"
    BREADTH_WEAKENING = "BREADTH_WEAKENING"
    BREADTH_UNAVAILABLE = "BREADTH_UNAVAILABLE"
    RISK_APPETITE_IMPROVING = "RISK_APPETITE_IMPROVING"
    RISK_APPETITE_WEAKENING = "RISK_APPETITE_WEAKENING"
    LIQUIDITY_IMPROVING = "LIQUIDITY_IMPROVING"
    LIQUIDITY_WEAKENING = "LIQUIDITY_WEAKENING"
    VOLATILITY_ELEVATED = "VOLATILITY_ELEVATED"
    VOLATILITY_STRESS = "VOLATILITY_STRESS"
    MACRO_EARNINGS_IMPROVING = "MACRO_EARNINGS_IMPROVING"
    MACRO_EARNINGS_WEAKENING = "MACRO_EARNINGS_WEAKENING"
    MACRO_EARNINGS_UNAVAILABLE = "MACRO_EARNINGS_UNAVAILABLE"
    SIGNAL_CONFLICT = "SIGNAL_CONFLICT"
    LOW_COVERAGE = "LOW_COVERAGE"
    STATE_HYSTERESIS_HELD = "STATE_HYSTERESIS_HELD"
    MIN_DURATION_HELD = "MIN_DURATION_HELD"
    STATE_CHANGE_STEP_LIMITED = "STATE_CHANGE_STEP_LIMITED"
    STATE_CHANGE_CONFIRMED = "STATE_CHANGE_CONFIRMED"
    STATE_INITIALIZED = "STATE_INITIALIZED"
    SHOCK_DRAWDOWN = "SHOCK_DRAWDOWN"
    SHOCK_VOLATILITY = "SHOCK_VOLATILITY"
    SHOCK_FX = "SHOCK_FX"
    SHOCK_CREDIT = "SHOCK_CREDIT"
    PRICE_SURGE = "PRICE_SURGE"
    PRICE_STRONG_RISE = "PRICE_STRONG_RISE"
    PRICE_STRONG_FALL = "PRICE_STRONG_FALL"
    PRICE_CRASH = "PRICE_CRASH"
    PRICE_SHOCK_UNAVAILABLE = "PRICE_SHOCK_UNAVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_STALE = "SOURCE_STALE"
    SOURCE_LICENSE_BLOCKED = "SOURCE_LICENSE_BLOCKED"
    FORECAST_UNAVAILABLE = "FORECAST_UNAVAILABLE"
    FORECAST_PIT_INVALID = "FORECAST_PIT_INVALID"


SHOCK_REASON_CODES = frozenset(
    {
        MarketReasonCode.SHOCK_DRAWDOWN,
        MarketReasonCode.SHOCK_VOLATILITY,
        MarketReasonCode.SHOCK_FX,
        MarketReasonCode.SHOCK_CREDIT,
    }
)


EXPECTED_PRIMARY_LABEL = {
    MarketStructure.UPTREND: PrimaryTransitionLabel.DOWNWARD_TRANSITION_POTENTIAL,
    MarketStructure.RANGE: PrimaryTransitionLabel.BREAKOUT_BREAKDOWN_POTENTIAL,
    MarketStructure.DOWNTREND: PrimaryTransitionLabel.UPWARD_TRANSITION_POTENTIAL,
}


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")


def _require_probability(value: float, field_name: str) -> None:
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise ContractValidationError(f"{field_name} must be between 0 and 1")


def _require_sha256(value: str | None, field_name: str, *, required: bool) -> None:
    if value is None:
        if required:
            raise ContractValidationError(f"{field_name} is required")
        return
    if not SHA256_PATTERN.fullmatch(value):
        raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")


def _validate_axes(values: Mapping[str, float | None], field_name: str) -> None:
    if set(values) != AXIS_NAMES:
        raise ContractValidationError(f"{field_name} must contain exactly {sorted(AXIS_NAMES)}")
    for key, value in values.items():
        if value is not None and not math.isfinite(float(value)):
            raise ContractValidationError(f"{field_name}.{key} must be finite or null")


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(_normalize(key)): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(_normalize(pair[0])))
        }
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(_normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


@dataclass(frozen=True)
class SourceAvailability:
    source_code: str
    available: bool
    coverage_ratio: float
    observation_date: date | None
    published_at: datetime | None
    available_at: datetime | None
    ingested_at: datetime | None
    staleness_days: int | None
    source_snapshot_hash: str | None
    reason_codes: tuple[MarketReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_code.strip():
            raise ContractValidationError("source_code is required")
        _require_probability(self.coverage_ratio, "coverage_ratio")
        if self.staleness_days is not None and self.staleness_days < 0:
            raise ContractValidationError("staleness_days cannot be negative")
        for field_name in ["published_at", "available_at", "ingested_at"]:
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name)
        if self.available:
            if self.available_at is None or self.ingested_at is None:
                raise ContractValidationError("available source requires available_at and ingested_at")
            if self.coverage_ratio <= 0.0:
                raise ContractValidationError("available source requires positive coverage_ratio")
            _require_sha256(self.source_snapshot_hash, "source_snapshot_hash", required=True)
        elif not self.reason_codes:
            raise ContractValidationError("unavailable source requires reason_codes")
        if self.published_at and self.available_at and self.published_at > self.available_at:
            raise ContractValidationError("published_at cannot be after available_at")
        if self.observation_date and self.available_at and self.observation_date > self.available_at.date():
            raise ContractValidationError("observation_date cannot be after available_at date")
        if self.available_at and self.ingested_at and self.available_at > self.ingested_at:
            raise ContractValidationError("available_at cannot be after ingested_at")

    def validate_cutoff(self, information_cutoff_at: datetime) -> None:
        if self.available_at and self.available_at > information_cutoff_at:
            raise ContractValidationError(f"{self.source_code}.available_at exceeds information cutoff")
        if self.ingested_at and self.ingested_at > information_cutoff_at:
            raise ContractValidationError(f"{self.source_code}.ingested_at exceeds information cutoff")


@dataclass(frozen=True)
class MarketForecast:
    horizon_days: int
    available: bool
    label: ForecastLabel | None
    probability: float | None
    confidence_score: float | None
    confidence_level: ConfidenceLevel | None
    source_snapshot_hash: str | None
    reason_codes: tuple[MarketReasonCode, ...] = ()

    def __post_init__(self) -> None:
        if self.horizon_days <= 0:
            raise ContractValidationError("horizon_days must be positive")
        if self.available:
            if self.label is None or self.probability is None or self.confidence_score is None or self.confidence_level is None:
                raise ContractValidationError("available forecast requires label, probability and confidence")
            _require_probability(self.probability, "forecast_probability")
            _require_probability(self.confidence_score, "forecast_confidence_score")
            _require_sha256(self.source_snapshot_hash, "forecast.source_snapshot_hash", required=True)
        else:
            if any(value is not None for value in [self.label, self.probability, self.confidence_score, self.confidence_level]):
                raise ContractValidationError("unavailable forecast values must remain null")
            if not self.reason_codes:
                raise ContractValidationError("unavailable forecast requires reason_codes")


@dataclass(frozen=True)
class ObservedMarketState:
    structure: MarketStructure
    stage: MarketStage
    stage_probabilities: Mapping[MarketStage, float]
    probability_status: ProbabilityStatus
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
    confidence_score: float
    confidence_level: ConfidenceLevel
    raw_axis_scores: Mapping[str, float | None]
    normalized_axis_scores: Mapping[str, float | None]
    reason_codes: tuple[MarketReasonCode, ...]

    def __post_init__(self) -> None:
        if STAGE_STRUCTURE[self.stage] is not self.structure:
            raise ContractValidationError("observed stage does not belong to observed structure")
        if set(self.stage_probabilities) != set(MarketStage):
            raise ContractValidationError("stage_probabilities must contain all eight market stages")
        for stage, probability in self.stage_probabilities.items():
            _require_probability(probability, f"stage_probabilities.{stage.value}")
        if not math.isclose(sum(self.stage_probabilities.values()), 1.0, abs_tol=1e-9):
            raise ContractValidationError("stage_probabilities must sum to 1")
        for field_name in [
            "upward_transition_probability",
            "downward_transition_probability",
            "continuation_probability",
            "primary_transition_probability",
            "transition_confidence",
            "confidence_score",
        ]:
            _require_probability(getattr(self, field_name), field_name)
        transition_probability_total = (
            self.upward_transition_probability
            + self.downward_transition_probability
            + self.continuation_probability
        )
        if not math.isclose(transition_probability_total, 1.0, abs_tol=1e-9):
            raise ContractValidationError("transition probabilities must sum to 1")
        if self.primary_transition_label is not EXPECTED_PRIMARY_LABEL[self.structure]:
            raise ContractValidationError("primary_transition_label does not match observed structure")
        if self.shock_flag and not self.shock_reason_codes:
            raise ContractValidationError("shock_flag requires shock_reason_codes")
        if not self.shock_flag and self.shock_reason_codes:
            raise ContractValidationError("shock_reason_codes require shock_flag")
        if any(code not in SHOCK_REASON_CODES for code in self.shock_reason_codes):
            raise ContractValidationError("shock_reason_codes contain a non-shock code")
        _validate_axes(self.raw_axis_scores, "raw_axis_scores")
        _validate_axes(self.normalized_axis_scores, "normalized_axis_scores")
        if not self.reason_codes:
            raise ContractValidationError("observed state requires reason_codes")


@dataclass(frozen=True)
class MarketRegimeRecord:
    market_scope: MarketScope
    decision_date: date
    market_data_asof: date
    information_cutoff_at: datetime
    generated_at: datetime
    observed: ObservedMarketState
    forecasts: tuple[MarketForecast, ...]
    sources: tuple[SourceAvailability, ...]
    rule_version: str
    rule_hash: str
    reason_code_version: str = REASON_CODE_VERSION
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_aware(self.information_cutoff_at, "information_cutoff_at")
        _require_aware(self.generated_at, "generated_at")
        if self.market_data_asof > self.decision_date:
            raise ContractValidationError("market_data_asof cannot be after decision_date")
        if self.information_cutoff_at > self.generated_at:
            raise ContractValidationError("information_cutoff_at cannot be after generated_at")
        if self.information_cutoff_at.date() != self.decision_date:
            raise ContractValidationError("decision_date must match information_cutoff_at date")
        if not self.rule_version.strip():
            raise ContractValidationError("rule_version is required")
        _require_sha256(self.rule_hash, "rule_hash", required=True)
        source_codes = [source.source_code for source in self.sources]
        if len(source_codes) != len(set(source_codes)):
            raise ContractValidationError("source_code values must be unique")
        if not source_codes:
            raise ContractValidationError("at least one source availability record is required")
        for source in self.sources:
            source.validate_cutoff(self.information_cutoff_at)
        horizons = [forecast.horizon_days for forecast in self.forecasts]
        if len(horizons) != len(set(horizons)):
            raise ContractValidationError("forecast horizons must be unique")

    def to_payload(self) -> dict[str, Any]:
        availability_by_source = {source.source_code: source.available for source in self.sources}
        coverage_by_source = {source.source_code: source.coverage_ratio for source in self.sources}
        source_snapshot_hashes = {
            source.source_code: source.source_snapshot_hash
            for source in self.sources
            if source.source_snapshot_hash is not None
        }
        return _normalize(
            {
                "schema_version": self.schema_version,
                "reason_code_version": self.reason_code_version,
                "rule_version": self.rule_version,
                "rule_hash": self.rule_hash,
                "decision_date": self.decision_date,
                "market_scope": self.market_scope,
                "market_data_asof": self.market_data_asof,
                "information_cutoff_at": self.information_cutoff_at,
                "generated_at": self.generated_at,
                "observed_structure": self.observed.structure,
                "observed_stage": self.observed.stage,
                "stage_probabilities": self.observed.stage_probabilities,
                "probability_status": self.observed.probability_status,
                "risk_appetite": self.observed.risk_appetite,
                "volatility_state": self.observed.volatility_state,
                "transition": self.observed.transition,
                "short_term_price_shock": self.observed.short_term_price_shock,
                "shock_flag": self.observed.shock_flag,
                "shock_reason_codes": self.observed.shock_reason_codes,
                "upward_transition_probability": self.observed.upward_transition_probability,
                "downward_transition_probability": self.observed.downward_transition_probability,
                "continuation_probability": self.observed.continuation_probability,
                "primary_transition_label": self.observed.primary_transition_label,
                "primary_transition_probability": self.observed.primary_transition_probability,
                "transition_confidence": self.observed.transition_confidence,
                "observed_regime_confidence": self.observed.confidence_score,
                "observed_regime_confidence_level": self.observed.confidence_level,
                "raw_axis_scores": self.observed.raw_axis_scores,
                "normalized_axis_scores": self.observed.normalized_axis_scores,
                "reason_codes": self.observed.reason_codes,
                "forecasts": self.forecasts,
                "availability_by_source": availability_by_source,
                "coverage_by_source": coverage_by_source,
                "source_snapshot_hashes": source_snapshot_hashes,
                "source_records": self.sources,
            }
        )

    def payload_hash(self) -> str:
        return canonical_sha256(self.to_payload())
