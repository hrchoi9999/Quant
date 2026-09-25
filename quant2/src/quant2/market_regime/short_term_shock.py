from __future__ import annotations

from dataclasses import asdict, dataclass

from src.quant2.contracts.market_overlays import OverlayInputs
from src.quant2.contracts.market_regime import (
    ContractValidationError,
    MarketReasonCode,
    ShortTermPriceShock,
    canonical_sha256,
)

SHORT_TERM_SHOCK_POLICY_VERSION = "quant2.short_term_shock.v1"


@dataclass(frozen=True)
class ShortTermShockPolicy:
    drawdown_5d: float = -0.08
    drawdown_20d: float = -0.15
    volatility_zscore: float = 2.50
    fx_move_5d_abs: float = 0.05
    credit_zscore: float = 2.50
    price_surge_zscore: float = 2.50
    price_strong_rise_zscore: float = 1.50
    price_strong_fall_zscore: float = -1.50
    price_crash_zscore: float = -2.50
    version: str = SHORT_TERM_SHOCK_POLICY_VERSION

    def __post_init__(self) -> None:
        if not -1.0 <= self.drawdown_20d <= self.drawdown_5d <= 0.0:
            raise ContractValidationError("drawdown shock thresholds are invalid")
        if (
            self.volatility_zscore <= 0.0
            or self.fx_move_5d_abs <= 0.0
            or self.credit_zscore <= 0.0
        ):
            raise ContractValidationError("stress shock thresholds must be positive")
        if not (
            self.price_surge_zscore
            > self.price_strong_rise_zscore
            > 0.0
            > self.price_strong_fall_zscore
            > self.price_crash_zscore
        ):
            raise ContractValidationError("directional price shock thresholds are invalid")
        if not self.version.strip():
            raise ContractValidationError("short-term shock policy version is required")

    def policy_hash(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ShortTermShockResult:
    price_shock: ShortTermPriceShock
    stress_flag: bool
    stress_reason_codes: tuple[MarketReasonCode, ...]
    reason_codes: tuple[MarketReasonCode, ...]
    policy_version: str
    policy_hash: str

    def __post_init__(self) -> None:
        if self.stress_flag != bool(self.stress_reason_codes):
            raise ContractValidationError("stress flag and stress reasons must agree")
        if len(self.policy_hash) != 64:
            raise ContractValidationError("short-term shock policy hash must be SHA-256")


def _price_shock(
    inputs: OverlayInputs,
    policy: ShortTermShockPolicy,
) -> ShortTermPriceShock:
    if inputs.drawdown_5d <= policy.drawdown_5d or inputs.drawdown_20d <= policy.drawdown_20d:
        return ShortTermPriceShock.CRASH
    if not inputs.directional_price_available:
        return ShortTermPriceShock.UNAVAILABLE
    zscores = (
        float(inputs.return_zscore_1d),
        float(inputs.return_zscore_3d),
        float(inputs.return_zscore_5d),
    )
    strongest = max(zscores, key=abs)
    if strongest >= policy.price_surge_zscore:
        return ShortTermPriceShock.SURGE
    if strongest >= policy.price_strong_rise_zscore:
        return ShortTermPriceShock.STRONG_RISE
    if strongest <= policy.price_crash_zscore:
        return ShortTermPriceShock.CRASH
    if strongest <= policy.price_strong_fall_zscore:
        return ShortTermPriceShock.STRONG_FALL
    return ShortTermPriceShock.NORMAL


def calculate_short_term_shock(
    inputs: OverlayInputs,
    *,
    policy: ShortTermShockPolicy | None = None,
) -> ShortTermShockResult:
    applied_policy = policy or ShortTermShockPolicy()
    stress_reasons: list[MarketReasonCode] = []
    if (
        inputs.drawdown_5d <= applied_policy.drawdown_5d
        or inputs.drawdown_20d <= applied_policy.drawdown_20d
    ):
        stress_reasons.append(MarketReasonCode.SHOCK_DRAWDOWN)
    if inputs.volatility_zscore >= applied_policy.volatility_zscore:
        stress_reasons.append(MarketReasonCode.SHOCK_VOLATILITY)
    if inputs.fx_move_5d is not None and abs(inputs.fx_move_5d) >= applied_policy.fx_move_5d_abs:
        stress_reasons.append(MarketReasonCode.SHOCK_FX)
    if (
        inputs.credit_spread_zscore is not None
        and inputs.credit_spread_zscore >= applied_policy.credit_zscore
    ):
        stress_reasons.append(MarketReasonCode.SHOCK_CREDIT)

    price_shock = _price_shock(inputs, applied_policy)
    price_reason = {
        ShortTermPriceShock.SURGE: MarketReasonCode.PRICE_SURGE,
        ShortTermPriceShock.STRONG_RISE: MarketReasonCode.PRICE_STRONG_RISE,
        ShortTermPriceShock.STRONG_FALL: MarketReasonCode.PRICE_STRONG_FALL,
        ShortTermPriceShock.CRASH: MarketReasonCode.PRICE_CRASH,
        ShortTermPriceShock.UNAVAILABLE: MarketReasonCode.PRICE_SHOCK_UNAVAILABLE,
    }.get(price_shock)
    reasons = list(stress_reasons)
    if price_reason is not None:
        reasons.append(price_reason)
    policy_hash = applied_policy.policy_hash()
    return ShortTermShockResult(
        price_shock=price_shock,
        stress_flag=bool(stress_reasons),
        stress_reason_codes=tuple(stress_reasons),
        reason_codes=tuple(reasons),
        policy_version=applied_policy.version,
        policy_hash=policy_hash,
    )
