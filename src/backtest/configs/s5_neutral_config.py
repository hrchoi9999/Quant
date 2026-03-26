from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class S5ExecutionConfig:
    fee_bps: float = 5.0
    slippage_bps: float = 5.0
    rebalance: str = "M"
    weekly_anchor_weekday: int = 2
    weekly_holiday_shift: str = "prev"
    missing_group_to_cash: bool = True


@dataclass(frozen=True)
class S5BaseWeights:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.25,
            "equity_low_vol": 0.20,
            "equity_dividend": 0.15,
            "equity_covered_call": 0.10,
            "bond_short": 0.20,
            "CASH": 0.10,
        }
    )


@dataclass(frozen=True)
class S5BoundsConfig:
    min_weights: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.10,
            "equity_low_vol": 0.00,
            "equity_dividend": 0.00,
            "equity_covered_call": 0.00,
            "bond_short": 0.10,
            "CASH": 0.00,
        }
    )
    max_weights: dict[str, float] = field(
        default_factory=lambda: {
            "equity_kr_broad": 0.40,
            "equity_low_vol": 0.30,
            "equity_dividend": 0.25,
            "equity_covered_call": 0.20,
            "bond_short": 0.40,
            "CASH": 0.30,
        }
    )


@dataclass(frozen=True)
class S5SignalConfig:
    broad_group: str = "equity_kr_broad"
    low_vol_group: str = "equity_low_vol"
    dividend_group: str = "equity_dividend"
    covered_call_group: str = "equity_covered_call"
    fallback_group: str = "bond_short"
    lookback_vol_short: int = 10
    lookback_vol_long: int = 20
    rsi_window: int = 5
    boll_window: int = 20
    boll_k: float = 2.0
    adx_like_abs_ret_20d: float = 0.05
    vol_contraction_ratio: float = 0.85
    uncertainty_vol_threshold: float = 0.015
    oversold_rsi_threshold: float = 30.0
    rebound_rsi_threshold: float = 45.0
    broad_reversion_boost: float = 0.08
    low_vol_boost: float = 0.05
    dividend_boost: float = 0.04
    covered_call_boost: float = 0.03
    uncertainty_bond_boost: float = 0.08
    uncertainty_cash_boost: float = 0.05
    overheat_bond_boost: float = 0.06
    overheat_cash_boost: float = 0.04


@dataclass(frozen=True)
class S5NeutralConfig:
    strategy_name: str = "S5_NEUTRAL_V1"
    execution: S5ExecutionConfig = field(default_factory=S5ExecutionConfig)
    base: S5BaseWeights = field(default_factory=S5BaseWeights)
    bounds: S5BoundsConfig = field(default_factory=S5BoundsConfig)
    signals: S5SignalConfig = field(default_factory=S5SignalConfig)
