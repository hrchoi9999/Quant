"""Research rule: previous-close breach, next-open funded reduction only."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LeverageTrimRule:
    tickers: tuple[str, ...]
    trigger: float = .05
    target: float = .05

    def __post_init__(self):
        if (not self.tickers or len(set(self.tickers)) != len(self.tickers)
                or any(not t or t == "CASH" for t in self.tickers)
                or not 0 < self.target <= self.trigger < 1):
            raise ValueError("declared leveraged securities and trim thresholds required")


def reduction_notional(value, nav, target, cost_bps):
    """Solve (value-sale)/(nav-fee*sale)=target, without buying on a gap down."""
    if (not all(math.isfinite(x) for x in (value, nav, target, cost_bps))
            or not 0 <= value <= nav or nav <= 0 or not 0 < target < 1 or not 0 <= cost_bps < 10000):
        raise ValueError("invalid trim financing")
    return max(0.0, min(value, (value - target * nav) / (1 - target * cost_bps / 10000)))
