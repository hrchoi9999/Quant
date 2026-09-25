"""Apply known trading restrictions to research targets; never fabricate sells."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.evaluation.normalized_nav import normalize_weights
from src.quant2.evaluation.quant25_market_calibration import aware


def guard_restricted_entries(
    weights: Mapping[str, float], held_tickers: set[str], *, decision_at: str,
    execution_at: str, restrictions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Only known restrictions, not a complete tradability/universe certificate.

    A dated restriction is valid on [effective_from, effective_until). Its end,
    if supplied, must already be known at known_at. No inferred resumption.
    Restricted existing positions block the event for a separate holding policy.
    """
    decision, execution = aware(decision_at), aware(execution_at)
    if execution <= decision:
        raise ValueError("execution must follow decision")
    target = normalize_weights(weights)
    exclusions, blocked = [], []
    seen = set()
    for row in restrictions:
        ticker = str(row["ticker"])
        if ticker == "CASH" or not row.get("source_hash"):
            raise ValueError("security restriction and source hash required")
        known, start = aware(row["known_at"]), aware(row["effective_from"])
        end = aware(row["effective_until"]) if row.get("effective_until") else None
        if end is not None and end <= start:
            raise ValueError("invalid restriction interval")
        if known > decision or start > execution or (end is not None and execution >= end):
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        if ticker in held_tickers:
            blocked.append(ticker)
        elif target.get(ticker, 0) > 0:
            removed = target.pop(ticker)
            target["CASH"] += removed
            exclusions.append({"ticker": ticker, "weight_to_cash": removed,
                               "source_hash": str(row["source_hash"])})
    return {"candidate_id": "Q25_KNOWN_RESTRICTION_GUARD_V1",
            "status": "BLOCKED_HELD_RESTRICTION" if blocked else "KNOWN_RESTRICTIONS_SCREENED",
            "weights": None if blocked else target, "excluded_entries": exclusions,
            "blocked_held_tickers": sorted(blocked), "operationally_actionable": False,
            "coverage": "KNOWN_RESTRICTIONS_ONLY_NOT_FULL_TRADABILITY"}
