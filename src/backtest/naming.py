# naming.py ver 2026-02-10_002
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class RunId:
    """Identifier used to build consistent file/sheet names."""

    stamp: str  # e.g. 3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206

    @staticmethod
    def from_parts(*, horizon: str, strategy: str, weight_scheme: str, top_n: int,
                   good_regimes: str, sma_window: int,
                   market_gate: bool, exit_below_sma_weeks: int,
                   start: str, end: str,
                   market_sma_window: Optional[int] = None,
                   market_sma_mult: Optional[float] = None) -> "RunId":
        """Create a stamp with the project's *legacy* convention.

        Legacy stamp example:
          3m_S2_RBM_top30_GR43_SMA140_MG1_EX2_20131014_20260206

        Notes:
        - `good_regimes` may come in as "4,3" (CLI). We normalize to "GR43".
        - We intentionally DO NOT append market SMA parameters to the stamp yet,
          to keep compatibility with existing golden fixtures.
        """
        mg = "MG1" if market_gate else "MG0"
        ex = f"EX{int(exit_below_sma_weeks)}"

        gr_raw = str(good_regimes).strip()
        if gr_raw.upper().startswith("GR"):
            gr = gr_raw.upper()
        else:
            digits = "".join([ch for ch in gr_raw if ch.isdigit()])
            gr = f"GR{digits}" if digits else "GR"

        parts = [
            str(horizon),
            str(strategy),
            str(weight_scheme),
            f"top{int(top_n)}",
            gr,
            f"SMA{int(sma_window)}",
            mg,
            ex,
            start.replace("-", ""),
            end.replace("-", ""),
        ]
        return RunId(stamp="_".join(parts))



@dataclass(frozen=True)
class GSheetRunNames:
    """Canonical Google Sheet titles for a given RunId."""
    snapshot: str
    trades: str
    windows: str
    trades_c: str
    ledger: str

    @staticmethod
    def from_run_id(run_id: RunId) -> "GSheetRunNames":
        # Keep titles short but unique; Google Sheet tab name limit is 100 chars.
        s = run_id.stamp
        return GSheetRunNames(
            snapshot=f"snapshot_{s}",
            trades=f"trades_{s}",
            windows=f"windows_{s}",
            trades_c=f"tradesC_{s}",
            ledger=f"ledger_{s}",
        )
