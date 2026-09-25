from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from src.quant2.contracts.market_regime import ContractValidationError


@dataclass(frozen=True)
class OverlayInputs:
    decision_date: date
    volatility_zscore: float
    drawdown_5d: float
    drawdown_20d: float
    fx_move_5d: float | None = None
    credit_spread_zscore: float | None = None
    return_1d: float | None = None
    return_3d: float | None = None
    return_5d: float | None = None
    return_zscore_1d: float | None = None
    return_zscore_3d: float | None = None
    return_zscore_5d: float | None = None

    def __post_init__(self) -> None:
        for field_name in ("volatility_zscore", "drawdown_5d", "drawdown_20d"):
            if not math.isfinite(float(getattr(self, field_name))):
                raise ContractValidationError(f"{field_name} must be finite")
        optional_fields = (
            "fx_move_5d",
            "credit_spread_zscore",
            "return_1d",
            "return_3d",
            "return_5d",
            "return_zscore_1d",
            "return_zscore_3d",
            "return_zscore_5d",
        )
        for field_name in optional_fields:
            value = getattr(self, field_name)
            if value is not None and not math.isfinite(float(value)):
                raise ContractValidationError(f"{field_name} must be finite or null")
        for field_name in ("drawdown_5d", "drawdown_20d"):
            value = getattr(self, field_name)
            if not -1.0 <= value <= 0.0:
                raise ContractValidationError(f"{field_name} must be between -1 and 0")

        directional_fields = (
            self.return_1d,
            self.return_3d,
            self.return_5d,
            self.return_zscore_1d,
            self.return_zscore_3d,
            self.return_zscore_5d,
        )
        if any(value is not None for value in directional_fields) and not all(
            value is not None for value in directional_fields
        ):
            raise ContractValidationError(
                "short-term return and z-score inputs must be all present or all null"
            )
        for field_name in ("return_1d", "return_3d", "return_5d"):
            value = getattr(self, field_name)
            if value is not None and value <= -1.0:
                raise ContractValidationError(f"{field_name} must be greater than -1")

    @property
    def directional_price_available(self) -> bool:
        return self.return_1d is not None
