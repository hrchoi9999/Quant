from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class S6ExecutionConfig:
    fee_bps: float = 5.0
    slippage_bps: float = 5.0
    rebalance: str = "M"
    weekly_anchor_weekday: int = 2
    weekly_holiday_shift: str = "prev"
    missing_group_to_cash: bool = True


@dataclass(frozen=True)
class S6BaseWeights:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "bond_long": 0.25,
            "bond_short": 0.25,
            "fx_usd": 0.20,
            "commodity_gold": 0.15,
            "CASH": 0.10,
            "hedge_inverse_kr": 0.05,
        }
    )


@dataclass(frozen=True)
class S6BoundsConfig:
    min_weights: dict[str, float] = field(
        default_factory=lambda: {
            "bond_long": 0.00,
            "bond_short": 0.10,
            "fx_usd": 0.00,
            "commodity_gold": 0.00,
            "CASH": 0.00,
            "hedge_inverse_kr": 0.00,
        }
    )
    max_weights: dict[str, float] = field(
        default_factory=lambda: {
            "bond_long": 0.40,
            "bond_short": 0.50,
            "fx_usd": 0.30,
            "commodity_gold": 0.25,
            "CASH": 0.30,
            "hedge_inverse_kr": 0.15,
        }
    )
    inverse_cap: float = 0.15


@dataclass(frozen=True)
class S6SignalConfig:
    market_group: str = "equity_kr_broad"
    vol_lookback: int = 20
    vol_expand_threshold: float = 0.015
    market_drawdown_5d: float = -0.04
    market_drawdown_20d: float = -0.08
    usd_momo_20d: float = 0.02
    gold_momo_20d: float = 0.03
    bond_long_momo_20d: float = 0.01
    stress_short_bond_boost: float = 0.07
    stress_cash_boost: float = 0.05
    stress_inverse_boost: float = 0.05
    drawdown_short_bond_boost: float = 0.05
    drawdown_cash_boost: float = 0.05
    usd_boost: float = 0.05
    gold_boost: float = 0.05
    bond_long_boost: float = 0.05
    cut_from_bond_long: float = 0.05
    cut_from_cash: float = 0.03
    cut_from_short_bond: float = 0.05
    prefer_short_bond_over_long_bond_in_crash: bool = True


@dataclass(frozen=True)
class S6DefensiveConfig:
    strategy_name: str = "S6_DEFENSIVE_V1"
    execution: S6ExecutionConfig = field(default_factory=S6ExecutionConfig)
    base: S6BaseWeights = field(default_factory=S6BaseWeights)
    bounds: S6BoundsConfig = field(default_factory=S6BoundsConfig)
    signals: S6SignalConfig = field(default_factory=S6SignalConfig)
