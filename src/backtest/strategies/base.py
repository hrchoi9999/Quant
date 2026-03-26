# strategies/base.py ver 2026-02-23_001
"""Strategy interface contracts.

NOTE:
- Legacy/refactor 공존을 위해 `Strategy` 심볼을 제공합니다.
  (일부 레거시 코드에서 Strategy import 경로가 혼재되어 있었으나, 현재는 src.backtest.strategies.base로 통일함)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class RebalanceDecision:
    """Strategy output for a rebalance decision.

    - weights: pd.Series indexed by ticker, values in [0,1], sum<=1.
    - meta: optional structured metadata (used to build rich legacy-compatible CSV outputs)
    """
    weights: pd.Series
    meta: Dict[str, Any] = field(default_factory=dict)


class StrategyBase:
    """Minimal strategy interface for backtest engine."""

    name: str = "StrategyBase"

    def decide(self, asof: pd.Timestamp, *args, **kwargs) -> Optional[RebalanceDecision]:
        raise NotImplementedError


# Backward-compatible alias (do NOT remove)
Strategy = StrategyBase
