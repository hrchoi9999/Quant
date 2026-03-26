# strategies/registry.py ver 2026-02-23_001
from __future__ import annotations

from typing import Any
from src.backtest.strategies.s2 import StrategyS2


def get_strategy(code: str, args: Any):
    code = (code or "S2").upper()
    if code == "S2":
        return StrategyS2(args)
    raise ValueError(f"Unknown strategy: {code}")
