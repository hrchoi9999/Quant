from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketAxis,
    MarketReasonCode,
    MarketScope,
    SourceAvailability,
    canonical_sha256,
)
from src.quant2.contracts.trend_transition import TrendTransitionSignal

FEATURE_SCHEMA_VERSION = "quant2.market_feature_snapshot.v2"


def _require_probability(value: float, field_name: str) -> None:
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise ContractValidationError(f"{field_name} must be between 0 and 1")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class AxisFeatureSnapshot:
    axis: MarketAxis
    available: bool
    raw_score: float | None
    normalized_score: float | None
    coverage_ratio: float
    freshness_ratio: float
    staleness_days: int | None
    source_codes: tuple[str, ...]
    reason_codes: tuple[MarketReasonCode, ...] = ()

    def __post_init__(self) -> None:
        _require_probability(self.coverage_ratio, "coverage_ratio")
        _require_probability(self.freshness_ratio, "freshness_ratio")
        if self.staleness_days is not None and self.staleness_days < 0:
            raise ContractValidationError("staleness_days cannot be negative")
        if len(self.source_codes) != len(set(self.source_codes)):
            raise ContractValidationError("axis source_codes must be unique")
        if any(not source_code.strip() for source_code in self.source_codes):
            raise ContractValidationError("axis source_codes cannot contain blanks")

        if self.available:
            if self.raw_score is None or self.normalized_score is None:
                raise ContractValidationError("available axis requires raw_score and normalized_score")
            if not math.isfinite(float(self.raw_score)) or not math.isfinite(float(self.normalized_score)):
                raise ContractValidationError("available axis scores must be finite")
            if self.coverage_ratio <= 0.0 or self.freshness_ratio <= 0.0:
                raise ContractValidationError("available axis requires positive coverage and freshness")
            if not self.source_codes:
                raise ContractValidationError("available axis requires source_codes")
        else:
            if self.raw_score is not None or self.normalized_score is not None:
                raise ContractValidationError("unavailable axis scores must remain null")
            if not self.reason_codes:
                raise ContractValidationError("unavailable axis requires reason_codes")

    @property
    def effective_coverage(self) -> float:
        if not self.available:
            return 0.0
        return self.coverage_ratio * self.freshness_ratio


@dataclass(frozen=True)
class MarketFeatureSnapshot:
    market_scope: MarketScope
    decision_date: date
    market_data_asof: date
    information_cutoff_at: datetime
    axes: tuple[AxisFeatureSnapshot, ...]
    sources: tuple[SourceAvailability, ...]
    trend_transition: TrendTransitionSignal | None = None
    schema_version: str = FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_aware(self.information_cutoff_at, "information_cutoff_at")
        if self.market_data_asof > self.decision_date:
            raise ContractValidationError("market_data_asof cannot be after decision_date")
        if self.information_cutoff_at.date() != self.decision_date:
            raise ContractValidationError("decision_date must match information_cutoff_at date")

        axis_values = [axis.axis for axis in self.axes]
        if len(axis_values) != len(set(axis_values)):
            raise ContractValidationError("market feature axes must be unique")
        if set(axis_values) != set(MarketAxis):
            raise ContractValidationError("market feature snapshot requires all four axes")

        source_by_code = {source.source_code: source for source in self.sources}
        if len(source_by_code) != len(self.sources):
            raise ContractValidationError("source_code values must be unique")
        if not source_by_code:
            raise ContractValidationError("market feature snapshot requires source records")
        for source in self.sources:
            source.validate_cutoff(self.information_cutoff_at)
        for axis in self.axes:
            missing_codes = set(axis.source_codes) - set(source_by_code)
            if missing_codes:
                raise ContractValidationError(f"axis references unknown sources: {sorted(missing_codes)}")
            if axis.available and any(not source_by_code[code].available for code in axis.source_codes):
                raise ContractValidationError("available axis cannot reference an unavailable source")
        if self.trend_transition is not None:
            if self.trend_transition.market_scope is not self.market_scope:
                raise ContractValidationError("trend transition market_scope must match feature snapshot")
            if self.trend_transition.observation_date > self.market_data_asof:
                raise ContractValidationError("trend transition observation_date exceeds market_data_asof")
            if self.trend_transition.available_at > self.information_cutoff_at:
                raise ContractValidationError("trend transition available_at exceeds information cutoff")

    def axis_map(self) -> dict[MarketAxis, AxisFeatureSnapshot]:
        return {axis.axis: axis for axis in self.axes}

    def to_payload(self) -> dict[str, Any]:
        axes = {
            axis.axis.value: {
                "available": axis.available,
                "raw_score": axis.raw_score,
                "normalized_score": axis.normalized_score,
                "coverage_ratio": axis.coverage_ratio,
                "freshness_ratio": axis.freshness_ratio,
                "effective_coverage": axis.effective_coverage,
                "staleness_days": axis.staleness_days,
                "source_codes": list(axis.source_codes),
                "reason_codes": [code.value for code in axis.reason_codes],
            }
            for axis in sorted(self.axes, key=lambda item: item.axis.value)
        }
        source_records = [
            {
                "source_code": source.source_code,
                "available": source.available,
                "coverage_ratio": source.coverage_ratio,
                "observation_date": source.observation_date.isoformat() if source.observation_date else None,
                "published_at": source.published_at.isoformat() if source.published_at else None,
                "available_at": source.available_at.isoformat() if source.available_at else None,
                "ingested_at": source.ingested_at.isoformat() if source.ingested_at else None,
                "staleness_days": source.staleness_days,
                "source_snapshot_hash": source.source_snapshot_hash,
                "reason_codes": [code.value for code in source.reason_codes],
            }
            for source in sorted(self.sources, key=lambda item: item.source_code)
        ]
        return {
            "schema_version": self.schema_version,
            "market_scope": self.market_scope.value,
            "decision_date": self.decision_date.isoformat(),
            "market_data_asof": self.market_data_asof.isoformat(),
            "information_cutoff_at": self.information_cutoff_at.isoformat(),
            "axes": axes,
            "source_records": source_records,
            "source_snapshot_hashes": {
                source.source_code: source.source_snapshot_hash
                for source in sorted(self.sources, key=lambda item: item.source_code)
                if source.source_snapshot_hash is not None
            },
            "trend_transition": (
                self.trend_transition.to_payload() if self.trend_transition is not None else None
            ),
        }

    def payload_hash(self) -> str:
        return canonical_sha256(self.to_payload())
