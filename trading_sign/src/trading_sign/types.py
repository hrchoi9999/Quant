from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class TimingFeatureSnapshot:
    """Per-ticker feature snapshot evaluated on a signal date.

    V1 assumes the snapshot is built from data available up to the
    previous completed trading day, even if the signal is recomputed daily.
    """

    ticker: str
    signal_date: str

    selected_by_upstream: bool
    close_above_ma60: bool
    ma60_above_ma120: bool
    ma60_slope_positive: bool
    security_name: str = ""
    is_currently_held: bool = False
    data_asof_date: Optional[str] = None
    market_gate_open: bool = True

    fund_accel_score: Optional[float] = None
    trend_align_score: Optional[float] = None
    overheat_score: Optional[float] = None
    cumulative_return_since_entry: Optional[float] = None
    drawdown_from_peak: Optional[float] = None


@dataclass(frozen=True)
class EntryDecision:
    ticker: str
    signal_date: str
    allowed: bool
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExitDecision:
    ticker: str
    signal_date: str
    should_exit: bool
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TimingSignalRecord:
    """Persistable daily timing-signal record."""

    signal_date: str
    data_asof_date: str
    ticker: str
    model_code: str
    current_state: str
    security_name: str = ""
    latest_state_change_date: str = ""
    reason_tags: List[str] = field(default_factory=list)
    reason_summary: str = ""
    entry_score: Optional[float] = None
    exit_risk_score: Optional[float] = None
    is_recommended: bool = False
    is_held: bool = False
