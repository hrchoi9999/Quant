"""Consume bounded owner judgments without claiming complete source coverage."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .quant25_event_materiality import SIMPLE_POLICY
from .quant25_incremental_selection import aware


def _context_hashes(coverage, source, owner, *, reviewed_at):
    """Bound local metadata supplements official sources without becoming one."""
    from .quant25_input_timing import pinned

    rows = coverage.get("context_files", [])
    hashes = set()
    for item in rows:
        kind = item.get("evidence_kind")
        if (kind not in {"FIXED_INPUT_PRICE", "DERIVED_LOCAL_STORED_DART_METADATA"}
                or item not in source.get("source_files", [])
                or not item.get("path") or not item.get("sha256")
                or item["sha256"] in hashes
                or hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() != item["sha256"]
                or aware(item.get("observed_at")) > aware(reviewed_at)):
            raise ValueError("local context must retain owner source identity/hash/time")
        if kind == "FIXED_INPUT_PRICE":
            prepared = pinned(owner.get("preparation_reference"))
            if (prepared.get("data_asof") != owner.get("data_asof")
                    or item.get("data_asof") != prepared.get("data_asof")
                    or prepared.get("inputs", {}).get("prices", {}).get("sha256") != item["sha256"]):
                raise ValueError("local price context must bind exact owner preparation")
        hashes.add(item["sha256"])
    return hashes


def assess_simple(contract, coverage, *, stocks, cutoff):
    from .quant25_input_timing import pinned

    review = pinned(contract.get("event_materiality_review"))
    if (review.get("schema") != SIMPLE_POLICY or review.get("status") != "REVIEWED"
            or review.get("coverage") != contract["event_coverage"] or not review.get("reviewer")
            or not aware(coverage["reviewed_at"]) <= aware(review.get("reviewed_at")) <= aware(cutoff)):
        raise ValueError("simple consumption review binding/time missing")
    owner = pinned(review.get("owner_judgment"))
    source = pinned(coverage.get("source_coverage"))
    if (owner.get("schema") != "q25_simple_event_handling_v1"
            or owner.get("status") != "REVIEW_COMPLETE_CONSUMER_NOT_ACTIVATED"
            or owner.get("prior_coverage") != coverage["source_coverage"]
            or owner.get("signal_date") != contract.get("signal_date")
            or owner.get("rules_reference", {}).get("sha256") != coverage["rules_sha256"]
            or source.get("rules_sha256") != coverage["rules_sha256"]
            or source.get("calendar_sha256") != coverage["calendar_sha256"]
            or owner.get("source_coverage_status") != source.get("status")
            or coverage.get("status") != source.get("status")
            or coverage.get("unresolved_events") != owner.get("unresolved_events_preserved")
            or not aware(owner.get("reviewed_at")) <= aware(review["reviewed_at"])
            or not aware(cutoff) < aware(owner.get("expires_at"))):
        raise ValueError("owner source/status/signal binding mismatch or expired")
    window = owner.get("conditional_window", [])
    if (len(window) != 2 or not aware(window[0]) <= aware(coverage["execution_date"] + "T09:00:00+09:00")
            < aware(window[1]) or aware(window[1]) != aware(coverage["review_window"]["next_rebalance"] + "T09:00:00+09:00")):
        raise ValueError("simple review outside owner conditional window")
    cases = owner.get("cases", [])
    contexts = review.get("contexts", {})
    tickers = [c.get("ticker") for c in cases]
    unresolved = owner["unresolved_events_preserved"]
    if (not cases or len(tickers) != len(set(tickers)) or set(contexts) != set(tickers)
            or set(tickers) != {e.get("ticker") for e in unresolved}
            or len(unresolved) != len(tickers) or not set(tickers) <= set(stocks)):
        raise ValueError("one actual context per unresolved owner case required")
    hashes = {s["sha256"] for s in coverage["source_files"]}
    hashes |= _context_hashes(coverage, source, owner, reviewed_at=review["reviewed_at"])
    warnings, restricted, valuations, distributions = [], set(), set(), set()
    names = {"units_valid", "tradable", "price_valid"}
    for case in cases:
        ticker = case["ticker"]
        context = contexts[ticker]
        effects = context.get("direct_effects", {})
        evidence = context.get("evidence", {})
        case_hashes = [s["sha256"] for s in case.get("sources", [])]
        if (case.get("processing") not in {"WARN_CONDITIONAL", "WARN_PRICE_ONLY"}
                or not case_hashes or not set(case_hashes) <= hashes
                or not context.get("reason") or set(effects) != names
                or any(v is not None and type(v) is not bool for v in effects.values())):
            raise ValueError("simple case effects/source evidence incomplete")
        for name, value in effects.items():
            if value is None:
                continue
            ref = evidence.get(name, {})
            if (not ref.get("path") or not ref.get("basis") or not ref.get("sha256")
                    or hashlib.sha256(Path(ref["path"]).read_bytes()).hexdigest() != ref["sha256"]
                    or aware(ref.get("observed_at")) > aware(review["reviewed_at"])):
                raise ValueError("direct effect requires bound source and observation time")
        distribution = case["processing"] == "WARN_PRICE_ONLY"
        if distribution:
            distributions.add(ticker)
        action = "WARN_DISTRIBUTION" if distribution else "WARN_LIMITED"
        if any(v is not True for v in effects.values()):
            action = "RESTRICT_SECURITY"
            restricted.add(ticker)
            if effects["units_valid"] is not True or effects["price_valid"] is not True:
                valuations.add(ticker)
        warnings.append({"event_id": "owner:" + ticker, "ticker": ticker, "action": action,
                         "reason": context["reason"], "source_sha256": case_hashes,
                         "direct_effects": effects, "owner_processing": case["processing"],
                         "source_unknown_fields": case.get("source_unknown_fields", {}),
                         "unconfirmed_distribution": distribution})
    return {"policy": SIMPLE_POLICY, "source_status": coverage["status"],
            "source_unresolved_events": unresolved, "source_coverage": coverage["source_coverage"],
            "review": contract["event_materiality_review"], "owner_judgment": review["owner_judgment"],
            "warnings": warnings, "new_entry_restricted_tickers": sorted(restricted),
            "valuation_restricted_tickers": sorted(valuations),
            "unconfirmed_distribution_tickers": sorted(distributions),
            "total_return_status": "UNCONFIRMED_DISTRIBUTIONS" if distributions else "NOT_CERTIFIED_BY_EVENT_REVIEW",
            "cash_or_receivables_created": False, "future_no_event_claim": False,
            "complete_domain_coverage": False, "source_gaps_preserved": True,
            "local_context_files": coverage.get("context_files", []),
            "local_context_is_official_source": False}
