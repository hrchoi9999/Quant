from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from src.quant2.contracts.market_regime import ContractValidationError

STANDARDIZATION_VERSION = "quant2.expanding_zscore.v1"


class StandardizationStatus(str, Enum):
    READY = "READY"
    MISSING_VALUE = "MISSING_VALUE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    ZERO_VARIANCE = "ZERO_VARIANCE"


@dataclass(frozen=True)
class RawFeatureObservation:
    observation_date: date
    available_at: datetime
    value: float | None

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ContractValidationError("available_at must be timezone-aware")
        if self.observation_date > self.available_at.date():
            raise ContractValidationError("observation_date cannot be after available_at date")
        if self.value is not None and not math.isfinite(float(self.value)):
            raise ContractValidationError("observation value must be finite or null")


@dataclass(frozen=True)
class StandardizedObservation:
    observation_date: date
    available_at: datetime
    raw_value: float | None
    standardized_value: float | None
    reference_count: int
    reference_mean: float | None
    reference_std: float | None
    status: StandardizationStatus
    version: str = STANDARDIZATION_VERSION


@dataclass(frozen=True)
class ExpandingZScorePolicy:
    min_periods: int = 20
    clip_abs: float = 3.0
    version: str = STANDARDIZATION_VERSION

    def __post_init__(self) -> None:
        if self.min_periods < 2:
            raise ContractValidationError("min_periods must be at least 2")
        if not math.isfinite(self.clip_abs) or self.clip_abs <= 0.0:
            raise ContractValidationError("clip_abs must be finite and positive")
        if not self.version.strip():
            raise ContractValidationError("standardization version is required")


def expanding_zscore(
    observations: tuple[RawFeatureObservation, ...],
    *,
    policy: ExpandingZScorePolicy | None = None,
) -> tuple[StandardizedObservation, ...]:
    """Standardize each value against prior available observations only."""

    applied_policy = policy or ExpandingZScorePolicy()
    if not observations:
        return ()
    for previous, current in zip(observations, observations[1:]):
        if current.available_at <= previous.available_at:
            raise ContractValidationError("observations must have strictly increasing available_at")
        if current.observation_date <= previous.observation_date:
            raise ContractValidationError("observations must have strictly increasing observation_date")

    history: list[float] = []
    results: list[StandardizedObservation] = []
    for observation in observations:
        reference_count = len(history)
        reference_mean = statistics.fmean(history) if history else None
        reference_std = statistics.pstdev(history) if len(history) >= 2 else None

        if observation.value is None:
            status = StandardizationStatus.MISSING_VALUE
            standardized_value = None
        elif reference_count < applied_policy.min_periods:
            status = StandardizationStatus.INSUFFICIENT_HISTORY
            standardized_value = None
        elif reference_std is None or math.isclose(reference_std, 0.0, abs_tol=1e-12):
            status = StandardizationStatus.ZERO_VARIANCE
            standardized_value = None
        else:
            zscore = (float(observation.value) - float(reference_mean)) / reference_std
            standardized_value = max(-applied_policy.clip_abs, min(applied_policy.clip_abs, zscore))
            status = StandardizationStatus.READY

        results.append(
            StandardizedObservation(
                observation_date=observation.observation_date,
                available_at=observation.available_at,
                raw_value=observation.value,
                standardized_value=standardized_value,
                reference_count=reference_count,
                reference_mean=reference_mean,
                reference_std=reference_std,
                status=status,
                version=applied_policy.version,
            )
        )
        if observation.value is not None:
            history.append(float(observation.value))

    return tuple(results)
