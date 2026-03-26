# contracts.py ver 2026-02-19_002
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    """Standard backtest output bundle.

    Design goals:
    - Stable contract between engine/strategies and output plugins (CSV / GSheet).
    - DataFrames are optional to allow incremental implementation (P0: summary/snapshot only).
    """

    summary_df: Optional[pd.DataFrame] = None
    snapshot_df: Optional[pd.DataFrame] = None

    equity_df: Optional[pd.DataFrame] = None
    holdings_df: Optional[pd.DataFrame] = None

    trades_df: Optional[pd.DataFrame] = None
    trades_c_df: Optional[pd.DataFrame] = None
    ledger_df: Optional[pd.DataFrame] = None
    windows_df: Optional[pd.DataFrame] = None
    selection_df: Optional[pd.DataFrame] = None

    meta: Dict[str, Any] = field(default_factory=dict)

    def require(self, *names: str) -> None:
        """Raise ValueError if any required dataframe is missing."""
        missing = []
        for n in names:
            if not hasattr(self, n):
                missing.append(n)
                continue
            if getattr(self, n) is None:
                missing.append(n)
        if missing:
            raise ValueError(f"BacktestResult missing required fields: {missing}")