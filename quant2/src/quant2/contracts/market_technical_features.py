from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketScope,
    canonical_sha256,
)

TECHNICAL_FEATURE_SCHEMA_VERSION = "quant2.market_technical_features.v1"
TECHNICAL_INDICATOR_RULE_VERSION = "quant2.market_technical_indicators.v1"
MIN_RAW_OBSERVATIONS = 65
SHA256_PATTERN = re.compile(r"^[0-9A-F]{64}$")

TECHNICAL_FEATURE_NAMES = (
    "sma5",
    "sma20",
    "sma60",
    "gap_5_20",
    "gap_20_60",
    "gap_5_20_delta_1d",
    "gap_5_20_delta_3d",
    "gap_5_20_delta_5d",
    "gap_20_60_delta_1d",
    "gap_20_60_delta_3d",
    "gap_20_60_delta_5d",
    "rsi14",
    "rsi14_delta_1d",
    "rsi14_delta_3d",
    "rsi14_delta_5d",
    "macd_line_12_26",
    "macd_signal_9",
    "macd_histogram",
    "macd_histogram_delta_1d",
    "macd_histogram_delta_3d",
    "macd_histogram_delta_5d",
)


class AdjustmentStatus(str, Enum):
    INDEX_LEVEL_NOT_APPLICABLE = "INDEX_LEVEL_NOT_APPLICABLE"


class RevisionStatus(str, Enum):
    ORIGINAL = "ORIGINAL"
    REVISED = "REVISED"
    UNKNOWN = "UNKNOWN"


class TechnicalFeatureStatus(str, Enum):
    READY = "READY"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


TECHNICAL_INDICATOR_CONTRACT = {
    "rule_version": TECHNICAL_INDICATOR_RULE_VERSION,
    "price": "unadjusted official index close; positive finite values only",
    "sma": {"windows": [5, 20, 60], "method": "arithmetic rolling mean"},
    "gaps": {
        "gap_5_20": "sma5 / sma20 - 1",
        "gap_20_60": "sma20 / sma60 - 1",
    },
    "deltas": {
        "lags": [1, 3, 5],
        "method": "current level minus lagged level; trading-observation basis",
    },
    "rsi14": {
        "method": "Wilder smoothing",
        "seed": "simple mean of first 14 gains and losses",
        "zero_loss": 100.0,
        "zero_gain_and_loss": 50.0,
    },
    "macd": {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "ema": "recursive adjust_false seeded from first close",
        "line_available_after": 26,
        "signal_available_after_macd_values": 9,
    },
    "minimum_raw_observations": MIN_RAW_OBSERVATIONS,
    "standardization": "separate prior-only expanding contract",
    "source_snapshot_hash": "ordered previous-hash plus current-observation hash chain",
    "execution": "decision uses only rows available by cutoff; allocation applies next session",
    "outcome_fields": "PROHIBITED",
}
TECHNICAL_INDICATOR_RULE_HASH = canonical_sha256(TECHNICAL_INDICATOR_CONTRACT)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class MarketCloseObservation:
    market_scope: MarketScope
    observation_date: date
    available_at: datetime
    close: float
    source_code: str
    source_snapshot_hash: str
    adjustment_status: AdjustmentStatus = AdjustmentStatus.INDEX_LEVEL_NOT_APPLICABLE
    revision_status: RevisionStatus = RevisionStatus.UNKNOWN
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.market_scope not in {MarketScope.KOSPI, MarketScope.KOSDAQ}:
            raise ContractValidationError("technical close market_scope must be KOSPI or KOSDAQ")
        _require_aware(self.available_at, "available_at")
        if self.observation_date > self.available_at.date():
            raise ContractValidationError("observation_date cannot be after available_at date")
        if not math.isfinite(float(self.close)) or float(self.close) <= 0.0:
            raise ContractValidationError("close must be finite and positive")
        if not self.source_code.strip():
            raise ContractValidationError("source_code is required")
        if not SHA256_PATTERN.fullmatch(self.source_snapshot_hash):
            raise ContractValidationError("source_snapshot_hash must be uppercase SHA-256 hex")
        if self.revision_status is RevisionStatus.UNKNOWN and not self.reason_codes:
            raise ContractValidationError("unknown revision status requires reason_codes")
        if any(not code.strip() for code in self.reason_codes):
            raise ContractValidationError("reason_codes cannot contain blanks")

    def to_payload(self) -> dict[str, Any]:
        return {
            "market_scope": self.market_scope.value,
            "observation_date": self.observation_date.isoformat(),
            "available_at": self.available_at.isoformat(),
            "close": float(self.close),
            "source_code": self.source_code,
            "source_snapshot_hash": self.source_snapshot_hash,
            "adjustment_status": self.adjustment_status.value,
            "revision_status": self.revision_status.value,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class TechnicalIndicatorSnapshot:
    market_scope: MarketScope
    observation_date: date
    available_at: datetime
    raw_observation_count: int
    values: Mapping[str, float | None]
    status: TechnicalFeatureStatus
    reason_codes: tuple[str, ...]
    source_snapshot_hash: str
    rule_version: str = TECHNICAL_INDICATOR_RULE_VERSION
    rule_hash: str = TECHNICAL_INDICATOR_RULE_HASH
    schema_version: str = TECHNICAL_FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_aware(self.available_at, "available_at")
        if self.raw_observation_count <= 0:
            raise ContractValidationError("raw_observation_count must be positive")
        if set(self.values) != set(TECHNICAL_FEATURE_NAMES):
            raise ContractValidationError("technical values do not match the frozen schema")
        for name, value in self.values.items():
            if value is not None and not math.isfinite(float(value)):
                raise ContractValidationError(f"{name} must be finite or null")
        if not SHA256_PATTERN.fullmatch(self.source_snapshot_hash):
            raise ContractValidationError("source_snapshot_hash must be uppercase SHA-256 hex")
        if not SHA256_PATTERN.fullmatch(self.rule_hash):
            raise ContractValidationError("rule_hash must be uppercase SHA-256 hex")
        if self.status is TechnicalFeatureStatus.READY:
            if self.raw_observation_count < MIN_RAW_OBSERVATIONS:
                raise ContractValidationError("ready snapshot requires minimum raw history")
            if any(value is None for value in self.values.values()):
                raise ContractValidationError("ready snapshot cannot contain null technical values")
        else:
            if not self.reason_codes:
                raise ContractValidationError("unavailable technical snapshot requires reason_codes")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rule_version": self.rule_version,
            "rule_hash": self.rule_hash,
            "market_scope": self.market_scope.value,
            "observation_date": self.observation_date.isoformat(),
            "available_at": self.available_at.isoformat(),
            "raw_observation_count": self.raw_observation_count,
            "minimum_raw_observations": MIN_RAW_OBSERVATIONS,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "source_snapshot_hash": self.source_snapshot_hash,
            "values": {name: self.values[name] for name in TECHNICAL_FEATURE_NAMES},
        }

    def payload_hash(self) -> str:
        return canonical_sha256(self.to_payload())
