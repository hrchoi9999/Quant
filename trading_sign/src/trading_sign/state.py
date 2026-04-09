from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TickerState:
    ticker: str
    in_position: bool = False
    entry_signal_date: Optional[str] = None
    entry_exec_date: Optional[str] = None
    entry_price: Optional[float] = None
    holding_weeks: int = 0
    below_ma60_streak: int = 0
    nonpositive_ma60_slope_streak: int = 0
    cooldown_weeks_left: int = 0
    last_exit_reason: Optional[str] = None
    last_exit_signal_date: Optional[str] = None

    def register_entry(
        self,
        *,
        signal_date: str,
        exec_date: Optional[str] = None,
        entry_price: Optional[float] = None,
    ) -> None:
        self.in_position = True
        self.entry_signal_date = signal_date
        self.entry_exec_date = exec_date
        self.entry_price = entry_price
        self.holding_weeks = 0
        self.below_ma60_streak = 0
        self.nonpositive_ma60_slope_streak = 0
        self.cooldown_weeks_left = 0

    def register_exit(
        self,
        *,
        signal_date: str,
        reason: str,
        cooldown_weeks: int,
    ) -> None:
        self.in_position = False
        self.holding_weeks = 0
        self.cooldown_weeks_left = max(0, int(cooldown_weeks))
        self.last_exit_reason = reason
        self.last_exit_signal_date = signal_date
        self.below_ma60_streak = 0
        self.nonpositive_ma60_slope_streak = 0

    def advance_rebalance(self) -> None:
        if self.in_position:
            self.holding_weeks += 1
        elif self.cooldown_weeks_left > 0:
            self.cooldown_weeks_left -= 1


@dataclass
class PortfolioState:
    rebalance_date: Optional[str] = None
    market_gate_open: bool = True
    cash_weight: float = 0.0
