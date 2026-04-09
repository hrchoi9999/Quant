from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimingConfig:
    """V1 timing overlay thresholds.

    These defaults intentionally lean conservative:
    trend alignment and fundamentals acceleration must both confirm
    before entry, while exits require persistence instead of one-off noise.

    The overlay is designed for:
    - daily end-of-day signal refresh
    - previous-trading-day data cutoff
    - mid- to long-horizon interpretation
    """

    signal_refresh_frequency: str = "daily_eod"
    signal_data_cutoff: str = "previous_trading_day_close"
    decision_style: str = "mid_long_horizon"

    entry_min_accel: float = 0.55
    entry_max_overheat: float = 0.85
    entry_min_score: float = 0.50

    below_ma60_exit_weeks: int = 2
    nonpositive_ma60_slope_exit_weeks: int = 2
    cooldown_weeks_after_exit: int = 2

    market_gate_blocks_new_entries: bool = True
    market_gate_tightens_exit: bool = True

    weight_accel: float = 0.45
    weight_trend: float = 0.35
    weight_overheat_penalty: float = 0.20
