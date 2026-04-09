from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .config import TimingConfig

PUBLIC_EXPOSED_S_MODEL_CODES = ("STABLE", "BALANCED", "GROWTH")
PUBLIC_DISCOVERY_MODEL_CODES = ("T_STOCK_DISCOVERY", "T_ETF_DISCOVERY")
PUBLIC_CURRENT_MODEL_CODES = (*PUBLIC_EXPOSED_S_MODEL_CODES, *PUBLIC_DISCOVERY_MODEL_CODES)
NON_EXPOSED_PUBLIC_MODEL_CODES = ("AUTO",)
PUBLIC_EXPOSED_SERVICE_PROFILES = ("stable", "balanced", "growth")


@dataclass(frozen=True)
class ModelTimingProfile:
    """Model-specific timing personality."""

    profile_code: str
    signal_refresh_frequency: str
    decision_frequency: str
    expected_holding_horizon: str
    entry_style: str
    exit_style: str
    cooldown_style: str
    timing_config: TimingConfig


def _base_daily_config() -> TimingConfig:
    return TimingConfig()


def _fundamental_slow_config() -> TimingConfig:
    return TimingConfig(
        entry_min_accel=0.60,
        entry_max_overheat=0.90,
        entry_min_score=0.52,
        below_ma60_exit_weeks=3,
        nonpositive_ma60_slope_exit_weeks=3,
        cooldown_weeks_after_exit=2,
    )


def _trend_following_config() -> TimingConfig:
    return TimingConfig(
        entry_min_accel=0.50,
        entry_max_overheat=0.80,
        entry_min_score=0.50,
        below_ma60_exit_weeks=2,
        nonpositive_ma60_slope_exit_weeks=2,
        cooldown_weeks_after_exit=1,
    )


def _defensive_allocation_config() -> TimingConfig:
    return TimingConfig(
        entry_min_accel=0.45,
        entry_max_overheat=0.95,
        entry_min_score=0.45,
        below_ma60_exit_weeks=2,
        nonpositive_ma60_slope_exit_weeks=2,
        cooldown_weeks_after_exit=1,
        market_gate_blocks_new_entries=True,
        market_gate_tightens_exit=True,
    )


DEFAULT_MODEL_PROFILES: Dict[str, ModelTimingProfile] = {
    "fundamental_slow": ModelTimingProfile(
        profile_code="fundamental_slow",
        signal_refresh_frequency="daily_eod",
        decision_frequency="daily_state_weekly_interpretation",
        expected_holding_horizon="multi_month",
        entry_style="slow_confirmation",
        exit_style="slow_persistence",
        cooldown_style="moderate",
        timing_config=_fundamental_slow_config(),
    ),
    "trend_following": ModelTimingProfile(
        profile_code="trend_following",
        signal_refresh_frequency="daily_eod",
        decision_frequency="daily_state_weekly_interpretation",
        expected_holding_horizon="multi_week_to_multi_month",
        entry_style="trend_confirmed",
        exit_style="persistent_trend_break",
        cooldown_style="short",
        timing_config=_trend_following_config(),
    ),
    "defensive_allocation": ModelTimingProfile(
        profile_code="defensive_allocation",
        signal_refresh_frequency="daily_eod",
        decision_frequency="daily_state_weekly_interpretation",
        expected_holding_horizon="allocation_overlay",
        entry_style="gate_first",
        exit_style="risk_control_first",
        cooldown_style="short",
        timing_config=_defensive_allocation_config(),
    ),
}


MODEL_CODE_TO_PROFILE_CODE: Dict[str, str] = {
    "S2": "fundamental_slow",
    "S3": "trend_following",
    "S3_CORE2": "trend_following",
    "S4": "defensive_allocation",
    "S5": "defensive_allocation",
    "S6": "defensive_allocation",
    "STABLE": "defensive_allocation",
    "BALANCED": "fundamental_slow",
    "GROWTH": "trend_following",
    "AUTO": "defensive_allocation",
    "T_STOCK_DISCOVERY": "trend_following",
    "T_ETF_DISCOVERY": "trend_following",
}

# `AUTO` is intentionally kept here for legacy/internal compatibility, but it is
# not part of the current public model set and must not re-enter public snapshots.


def get_model_profile(model_code: str) -> ModelTimingProfile:
    profile_code = MODEL_CODE_TO_PROFILE_CODE.get(str(model_code).strip().upper(), "fundamental_slow")
    return DEFAULT_MODEL_PROFILES[profile_code]


def default_profile() -> ModelTimingProfile:
    return DEFAULT_MODEL_PROFILES["fundamental_slow"]


def base_config() -> TimingConfig:
    return _base_daily_config()
