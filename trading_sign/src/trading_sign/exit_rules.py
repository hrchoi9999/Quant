from __future__ import annotations

from dataclasses import dataclass

from .config import TimingConfig
from .state import TickerState
from .types import ExitDecision, TimingFeatureSnapshot


@dataclass
class DefaultExitRule:
    """Stateful V1 exit rule with persistence requirements."""

    config: TimingConfig

    def evaluate(self, snapshot: TimingFeatureSnapshot, state: TickerState) -> ExitDecision:
        reasons: list[str] = []

        if not state.in_position:
            return ExitDecision(
                ticker=snapshot.ticker,
                signal_date=snapshot.signal_date,
                should_exit=False,
                reasons=["not_in_position"],
            )

        if snapshot.close_above_ma60:
            state.below_ma60_streak = 0
        else:
            state.below_ma60_streak += 1

        if snapshot.ma60_slope_positive:
            state.nonpositive_ma60_slope_streak = 0
        else:
            state.nonpositive_ma60_slope_streak += 1

        if state.below_ma60_streak >= self.config.below_ma60_exit_weeks:
            reasons.append("below_ma60_persistent")
        if state.nonpositive_ma60_slope_streak >= self.config.nonpositive_ma60_slope_exit_weeks:
            reasons.append("ma60_slope_nonpositive_persistent")
        if (
            self.config.market_gate_tightens_exit
            and not snapshot.market_gate_open
            and not snapshot.close_above_ma60
        ):
            reasons.append("market_gate_closed_with_trend_break")

        return ExitDecision(
            ticker=snapshot.ticker,
            signal_date=snapshot.signal_date,
            should_exit=bool(reasons),
            reasons=reasons,
        )
