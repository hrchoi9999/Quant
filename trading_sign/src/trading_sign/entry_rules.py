from __future__ import annotations

from dataclasses import dataclass

from .config import TimingConfig
from .state import TickerState
from .types import EntryDecision, TimingFeatureSnapshot


@dataclass
class DefaultEntryRule:
    """Conservative V1 entry rule.

    Entry requires:
    - upstream selection
    - long trend alignment
    - minimum fundamentals acceleration
    - no active cooldown
    - no severe overheat
    """

    config: TimingConfig

    def evaluate(self, snapshot: TimingFeatureSnapshot, state: TickerState) -> EntryDecision:
        reasons: list[str] = []

        if not snapshot.selected_by_upstream:
            reasons.append("not_selected_by_upstream")
        if not snapshot.close_above_ma60:
            reasons.append("close_below_ma60")
        if not snapshot.ma60_above_ma120:
            reasons.append("ma60_not_above_ma120")
        if not snapshot.ma60_slope_positive:
            reasons.append("ma60_slope_not_positive")
        if state.cooldown_weeks_left > 0:
            reasons.append("cooldown_active")
        if self.config.market_gate_blocks_new_entries and not snapshot.market_gate_open:
            reasons.append("market_gate_closed")

        accel = float(snapshot.fund_accel_score or 0.0)
        trend = float(snapshot.trend_align_score or 0.0)
        overheat = float(snapshot.overheat_score or 0.0)

        if accel < self.config.entry_min_accel:
            reasons.append("weak_fund_accel")
        if overheat > self.config.entry_max_overheat:
            reasons.append("overheated")

        score = (
            self.config.weight_accel * accel
            + self.config.weight_trend * trend
            - self.config.weight_overheat_penalty * overheat
        )

        allowed = (not reasons) and (score >= self.config.entry_min_score)
        if not allowed and score < self.config.entry_min_score:
            reasons.append("entry_score_below_threshold")

        return EntryDecision(
            ticker=snapshot.ticker,
            signal_date=snapshot.signal_date,
            allowed=allowed,
            score=score,
            reasons=reasons,
        )
