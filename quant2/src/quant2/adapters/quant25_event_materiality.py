"""Explicit Q25 consumption judgments; preserve partial sources and ledger uncertainty."""
from __future__ import annotations

from .quant25_incremental_selection import aware

POLICY = "Q25_EVENT_MATERIALITY_V1"
SIMPLE_POLICY = "Q25_SIMPLE_EVENT_CONSUMPTION_V1"
DOMAINS = ["corporate_actions", "rights", "trading_halts"]


def enabled(contract):
    from .quant25_input_timing import consumer_opted_in, preparation_review_enabled
    value = contract.get("event_materiality_policy") if isinstance(contract, dict) else None
    if value is None:
        return False
    if preparation_review_enabled(contract):
        return True
    if value not in {POLICY, SIMPLE_POLICY} or not consumer_opted_in(contract):
        raise ValueError("explicit consumer event materiality policy required")
    return True


def assess(contract, coverage, *, stocks, cutoff):
    from .quant25_input_timing import pinned

    if not enabled(contract):
        raise ValueError("event materiality policy disabled")
    if contract["event_materiality_policy"] == SIMPLE_POLICY:
        from .quant25_simple_event_consumption import assess_simple
        return assess_simple(contract, coverage, stocks=stocks, cutoff=cutoff)
    scope = set(stocks)
    checks = coverage.get("domain_checks", [])
    if (coverage.get("query_failures") != [] or len(checks) != len(DOMAINS)
            or {c.get("domain") for c in checks} != set(DOMAINS)):
        raise ValueError("required event source/domain query evidence missing")
    hashes = {s["sha256"] for s in coverage["source_files"]}
    for item in checks:
        if (item.get("status") != "QUERY_COMPLETED" or item.get("failures") != []
                or not scope <= set(item.get("queried_tickers", []))
                or not item.get("source_sha256") or not set(item["source_sha256"]) <= hashes
                or not aware(item.get("lookback_start")) <= aware(item.get("through_at"))
                <= aware(coverage["reviewed_at"])):
            raise ValueError("required event source/domain query failed or scope incomplete")
    review = pinned(contract.get("event_materiality_review"))
    if (review.get("schema") != POLICY or review.get("status") != "REVIEWED"
            or review.get("coverage") != contract["event_coverage"]
            or not review.get("reviewer")
            or not aware(coverage["reviewed_at"]) <= aware(review.get("reviewed_at")) <= aware(cutoff)):
        raise ValueError("materiality review binding/time missing")
    unresolved = coverage.get("unresolved_events")
    if not isinstance(unresolved, list) or any(not isinstance(e, dict) for e in unresolved):
        raise ValueError("identified unresolved events required; never erase unknowns")
    by_id = {e.get("event_id"): e for e in unresolved}
    decisions = review.get("decisions", [])
    if (None in by_id or len(by_id) != len(unresolved)
            or len(decisions) != len(by_id)
            or {d.get("event_id") for d in decisions} != set(by_id)):
        raise ValueError("one materiality decision for every unresolved event required")
    warnings, restricted, valuations, distributions = [], set(), set(), set()
    for decision in decisions:
        source = by_id[decision["event_id"]]
        ticker = source.get("ticker")
        effects = decision.get("direct_effects", {})
        names = {"units_valid", "tradable", "price_valid"}
        if (ticker not in scope or decision.get("ticker") != ticker or not decision.get("reason")
                or not decision.get("source_sha256") or not set(decision["source_sha256"]) <= hashes
                or set(effects) != names or any(type(v) is not bool for v in effects.values())):
            raise ValueError("materiality effect/source/ticker evidence incomplete")
        action = decision.get("action")
        if action in {"WARN_LIMITED", "WARN_DISTRIBUTION"}:
            if not all(effects.values()):
                raise ValueError("warning cannot waive unknown units/price/tradability")
            if action == "WARN_DISTRIBUTION":
                distributions.add(ticker)
        elif action == "RESTRICT_SECURITY":
            if all(effects.values()):
                raise ValueError("security restriction requires unresolved units/price/tradability")
            restricted.add(ticker)
            if not effects["units_valid"] or not effects["price_valid"]:
                valuations.add(ticker)
        else:
            raise ValueError("unknown materiality consumption action")
        warnings.append(dict(decision))
    return {"policy": POLICY, "source_status": coverage["status"],
            "source_unresolved_events": unresolved, "review": contract["event_materiality_review"],
            "warnings": warnings, "new_entry_restricted_tickers": sorted(restricted),
            "valuation_restricted_tickers": sorted(valuations),
            "unconfirmed_distribution_tickers": sorted(distributions),
            "total_return_status": "UNCONFIRMED_DISTRIBUTIONS" if distributions else "NOT_CERTIFIED_BY_EVENT_REVIEW",
            "cash_or_receivables_created": False, "future_no_event_claim": False}


def held_profile_restrictions(assessment, snapshots):
    """Recorded holdings identify affected securities; never suspend a whole profile."""
    restricted = set(assessment["new_entry_restricted_tickers"])
    valuation = set(assessment["valuation_restricted_tickers"])
    result = {}
    for profile, snapshot in snapshots.items():
        held = {p["ticker"] for p in snapshot["positions"] if float(p["units"]) > 0}
        affected = sorted(held & restricted)
        if affected:
            result[profile] = {"held_tickers": affected, "action": "PRESERVE_AFFECTED_UNITS_NO_ORDERS",
                "valuation_status": "UNCONFIRMED_AFFECTED_POSITIONS" if held & valuation else "PRICE_ONLY_IF_CURRENT_VALID",
                "affected_valuation_tickers": sorted(held & valuation), "position_source": "RECORDED_Q25_LEDGER"}
    return result
