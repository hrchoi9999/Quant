"""As-of announced-event exclusion, never retrospective deletion of holdings."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.evaluation.normalized_nav import ExecutionTarget, next_open_after_publication
from src.quant2.evaluation.quant25_market_calibration import aware
from src.quant2.evaluation.quant25_portfolio_comparison import monthly_names, validate_weights


def announced_overlap(rules: list[dict], decision_at: str, execution_at: str,
                      next_rebalance_at: str) -> dict[str, dict]:
    decision, execution, horizon = map(aware, (decision_at, execution_at, next_rebalance_at))
    if not decision < execution <= horizon:
        raise ValueError("invalid decision/execution/horizon ordering")
    versions = {}
    for row in rules:
        if not row.get("source_hash") or row.get("ticker") in {None, "", "CASH"}:
            raise ValueError("event identity and source hash required")
        known, start = aware(row["known_at"]), aware(row["effective_from"])
        end = aware(row["effective_until"]) if row.get("effective_until") else None
        if end is not None and end <= start:
            raise ValueError("invalid event interval")
        # Select the latest then-known revision BEFORE interval filtering. An
        # amended end may remove an old open-ended exclusion entirely.
        key = (str(row["ticker"]), row.get("event_id", row["source_hash"]))
        if known <= decision:
            previous = versions.get(key)
            if previous is not None and known == aware(previous["known_at"]) and row != previous:
                raise ValueError("ambiguous same-time event revisions")
            if previous is None or known >= aware(previous["known_at"]):
                versions[key] = row
    result = {}
    for row in versions.values():
        start = aware(row["effective_from"])
        end = aware(row["effective_until"]) if row.get("effective_until") else None
        if start <= horizon and (end is None or end > execution):
            ticker = str(row["ticker"])
            if ticker not in result or start < aware(result[ticker]["effective_from"]):
                result[ticker] = row
    return result


def compile_event_targets(scores: pd.DataFrame, prices: pd.DataFrame, variant: str,
                          policy: str, calendar: list[str], rules: list[dict]) -> tuple[list, list, dict | None]:
    """Exclude unusable new entries and close known upcoming-event holdings.

    Horizon is the next scheduled monthly execution, not any future score/value.
    Excluded slots remain cash. Already untradeable holdings block valuation;
    they are never removed or fictitiously sold to make the replay continue.
    """
    if not calendar or calendar != sorted(set(calendar)):
        raise ValueError("unique ordered calendar required")
    if prices.duplicated(["ticker", "date"]).any():
        raise ValueError("duplicate price keys")
    subset = scores.loc[scores.variant.eq(variant) & scores.decision_date.lt(calendar[-1])]
    if subset.empty or subset.duplicated(["decision_date", "ticker"]).any():
        raise ValueError("missing or duplicate scores")
    dates = sorted(subset.decision_date.unique())
    sessions = pd.DatetimeIndex(pd.to_datetime(calendar))
    executions = {d: next_open_after_publication(pd.Timestamp(d + "T16:00:00+09:00"), sessions).strftime("%Y-%m-%d") for d in dates}
    quotes = prices.set_index(["date", "ticker"])
    held, events, records = set(), [], []

    def usable(day: str, ticker: str) -> bool:
        try:
            values = quotes.loc[(day, ticker), ["open", "close", "volume"]].astype(float)
            return bool(np.isfinite(values).all() and values.gt(0).all())
        except (KeyError, ValueError, TypeError):
            return False

    for index, day in enumerate(dates):
        execution = executions[day]
        horizon = executions[dates[index + 1]] if index + 1 < len(dates) else calendar[-1]
        active = announced_overlap(rules, day + "T16:00:00+09:00", execution + "T09:00:00+09:00",
                                   horizon + "T09:00:00+09:00")
        # Missing marks or an already untradeable holding need a separate
        # valuation/corporate-action contract; keep the previous book intact.
        locked = sorted(t for t in held if not usable(day, t) or
                        (t in active and aware(active[t]["effective_from"]) <= aware(execution + "T09:00:00+09:00")))
        if locked:
            return events, records, {"date": execution, "decision_date": day,
                                     "reason": "held_untradeable_or_unvalued_do_not_delete",
                                     "held_tickers": sorted(held), "locked_tickers": locked}
        names = monthly_names(subset.loc[subset.decision_date.eq(day)], held, policy)
        exclusions = []
        for ticker in names:
            if ticker in active or not usable(day, ticker):
                exclusions.append({"ticker": ticker, "weight_to_cash": .05,
                                   "reason": "announced_event_before_next_rebalance" if ticker in active else "decision_quote_unusable",
                                   "source_hash": active[ticker]["source_hash"] if ticker in active else None,
                                   "known_at": active[ticker]["known_at"] if ticker in active else day + "T16:00:00+09:00"})
        excluded = {r["ticker"] for r in exclusions}
        current = set(names) - excluded
        weights = {t: .05 for t in sorted(current)}
        weights["CASH"] = 1 - .05 * len(current)
        validate_weights(weights)
        events.append(ExecutionTarget(f"{variant}_{policy}", pd.Timestamp(day),
                                      pd.Timestamp(day + "T16:00:00+09:00"), pd.Timestamp(execution),
                                      "Q25_EVENT_EXCLUSION_V01", weights, "RECONSTRUCTED_PRICE_ONLY"))
        records.append({"decision_date": day, "execution_date": execution, "next_rebalance": horizon,
                        "variant": variant, "policy": policy, "weights": weights,
                        "excluded_entries_or_targets": exclusions,
                        "preemptive_exit_tickers": sorted(held & set(active)),
                        "previous_held": sorted(held), "retained_names": len(current & held),
                        "new_names": len(current - held), "exited_names": len(held - current)})
        held = current
    return events, records, None
