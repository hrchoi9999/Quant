from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class S4ExecutionConfig:
    fee_bps: float = 5.0
    slippage_bps: float = 5.0
    rebalance: str = "M"
    weekly_anchor_weekday: int = 2
    weekly_holiday_shift: str = "prev"
    missing_group_to_cash: bool = True


@dataclass(frozen=True)
class S4BaseWeights:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.45,
            "equity_kr_growth": 0.35,
            "equity_sector_momentum": 0.15,
            "CASH": 0.05,
        }
    )


@dataclass(frozen=True)
class S4BoundsConfig:
    min_weights: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.20,
            "equity_kr_growth": 0.10,
            "equity_sector_momentum": 0.00,
            "CASH": 0.00,
            "bond_short": 0.00,
        }
    )
    max_weights: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.60,
            "equity_kr_growth": 0.50,
            "equity_sector_momentum": 0.30,
            "CASH": 0.20,
            "bond_short": 0.20,
        }
    )


@dataclass(frozen=True)
class S4SignalConfig:
    broad_group: str = "equity_kr_broad"
    growth_group: str = "equity_kr_growth"
    sector_group: str = "equity_sector_momentum"
    fallback_group: str = "bond_short"
    ma_short: int = 20
    ma_long: int = 60
    breakout_lookback: int = 20
    return_lookback: int = 20
    value_lookback: int = 20
    trend_boost: float = 0.08
    rs_boost: float = 0.07
    participation_boost: float = 0.05
    weakening_shift_to_broad: float = 0.07
    weakening_shift_to_cash: float = 0.05
    overheat_threshold: float = 0.18
    overheat_cut: float = 0.08


@dataclass(frozen=True)
class S4RiskOnConfig:
    strategy_name: str = "S4_RISK_ON_V1"
    execution: S4ExecutionConfig = field(default_factory=S4ExecutionConfig)
    base: S4BaseWeights = field(default_factory=S4BaseWeights)
    bounds: S4BoundsConfig = field(default_factory=S4BoundsConfig)
    signals: S4SignalConfig = field(default_factory=S4SignalConfig)
