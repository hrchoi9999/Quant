from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketReasonCode,
    MarketScope,
    canonical_sha256,
)
from src.quant2.contracts.market_technical_features import TECHNICAL_FEATURE_NAMES

TREND_TRANSITION_SCHEMA_VERSION = "quant2.trend_transition_signal.v2"
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")
TREND_TRANSITION_COMPONENTS = (
    "slow_gap_level",
    "slow_gap_momentum",
    "fast_gap_level",
    "fast_gap_momentum",
    "rsi_confirmation",
    "macd_confirmation",
    "confirmation_score",
    "trend_score",
    "transition_score",
)


class TechnicalTransitionDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class TrendTransitionSignal:
    market_scope: MarketScope
    observation_date: date
    available_at: datetime
    available: bool
    raw_values: Mapping[str, float | None]
    normalized_components: Mapping[str, float | None]
    direction: TechnicalTransitionDirection | None
    strength: float | None
    reason_codes: tuple[MarketReasonCode, ...]
    source_snapshot_hash: str
    technical_rule_hash: str
    rule_version: str
    rule_hash: str
    schema_version: str = TREND_TRANSITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.market_scope not in {MarketScope.KOSPI, MarketScope.KOSDAQ}:
            raise ContractValidationError("trend transition market_scope must be KOSPI or KOSDAQ")
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ContractValidationError("trend transition available_at must be timezone-aware")
        if set(self.raw_values) != set(TECHNICAL_FEATURE_NAMES):
            raise ContractValidationError("trend transition raw_values do not match technical schema")
        if set(self.normalized_components) != set(TREND_TRANSITION_COMPONENTS):
            raise ContractValidationError("trend transition normalized components do not match schema")
        for mapping_name, values in (
            ("raw_values", self.raw_values.values()),
            ("normalized_components", self.normalized_components.values()),
        ):
            if any(value is not None and not math.isfinite(float(value)) for value in values):
                raise ContractValidationError(f"{mapping_name} values must be finite or null")
        for field_name, value in (
            ("source_snapshot_hash", self.source_snapshot_hash),
            ("technical_rule_hash", self.technical_rule_hash),
            ("rule_hash", self.rule_hash),
        ):
            if not SHA256_PATTERN.fullmatch(value):
                raise ContractValidationError(f"{field_name} must be uppercase SHA-256 hex")
        if not self.rule_version.strip():
            raise ContractValidationError("trend transition rule_version is required")
        if self.available:
            if self.direction is None or self.strength is None:
                raise ContractValidationError("available trend transition requires direction and strength")
            if any(value is None for value in self.normalized_components.values()):
                raise ContractValidationError("available trend transition components cannot be null")
            if not 0.0 <= self.strength <= 1.0:
                raise ContractValidationError("trend transition strength must be between 0 and 1")
        else:
            if self.direction is not None or self.strength is not None:
                raise ContractValidationError("unavailable trend transition direction and strength must be null")
            if not self.reason_codes:
                raise ContractValidationError("unavailable trend transition requires reason_codes")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rule_version": self.rule_version,
            "rule_hash": self.rule_hash,
            "market_scope": self.market_scope.value,
            "observation_date": self.observation_date.isoformat(),
            "available_at": self.available_at.isoformat(),
            "available": self.available,
            "raw_values": {name: self.raw_values[name] for name in TECHNICAL_FEATURE_NAMES},
            "normalized_components": {
                name: self.normalized_components[name] for name in TREND_TRANSITION_COMPONENTS
            },
            "direction": self.direction.value if self.direction else None,
            "strength": self.strength,
            "reason_codes": [reason.value for reason in self.reason_codes],
            "source_snapshot_hash": self.source_snapshot_hash,
            "technical_rule_hash": self.technical_rule_hash,
        }

    def payload_hash(self) -> str:
        return canonical_sha256(self.to_payload())
