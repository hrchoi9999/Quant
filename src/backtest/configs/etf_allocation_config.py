from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegimeMappingConfig:
    horizon: str = "3m"
    risk_on_min: float = 3.0
    risk_off_max: float = 1.0
    fallback_mode: str = "neutral"


@dataclass(frozen=True)
class ExecutionConfig:
    fee_bps: float = 5.0
    slippage_bps: float = 5.0
    rebalance: str = "M"
    weekly_anchor_weekday: int = 2
    weekly_holiday_shift: str = "prev"
    missing_group_to_cash: bool = True


@dataclass(frozen=True)
class PortfolioConfig:
    risk_on: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.60,
            "equity_kr_growth": 0.40,
        }
    )
    neutral: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.40,
            "bond_short": 0.40,
            "CASH": 0.20,
        }
    )
    risk_off: dict[str, float] = field(
        default_factory=lambda: {
            "bond_long": 0.30,
            "bond_short": 0.25,
            "fx_usd": 0.20,
            "commodity_gold": 0.15,
            "hedge_inverse_kr": 0.10,
        }
    )


@dataclass(frozen=True)
class EtfAllocationConfig:
    strategy_name: str = "ETF_ALLOC_P0"
    rebalance: str = "M"
    regime: RegimeMappingConfig = field(default_factory=RegimeMappingConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)

    def mode_weights(self, mode: str) -> dict[str, float]:
        mode_key = str(mode).strip().lower()
        if mode_key == "risk_on":
            return dict(self.portfolio.risk_on)
        if mode_key == "risk_off":
            return dict(self.portfolio.risk_off)
        return dict(self.portfolio.neutral)
