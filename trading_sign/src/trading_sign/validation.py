from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .types import TimingSignalRecord


@dataclass(frozen=True)
class SignalValidationRecord:
    """Validation payload that attaches realized outcomes to a stored signal."""

    signal: TimingSignalRecord
    forward_return_4w: Optional[float] = None
    forward_return_8w: Optional[float] = None
    forward_return_12w: Optional[float] = None
    path_mdd_4w: Optional[float] = None
    path_mdd_8w: Optional[float] = None
    path_mdd_12w: Optional[float] = None


def signal_churn(previous_state: Optional[str], current_state: str) -> int:
    """Simple helper for later validation of unnecessary daily state changes."""
    if previous_state is None:
        return 0
    return int(previous_state != current_state)
