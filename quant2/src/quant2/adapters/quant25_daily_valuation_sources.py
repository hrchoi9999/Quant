"""Read-only, date/security-scoped Q25 close and rights source verification.

This reader never infers a no-event claim from an old target review. Positive
daily flags require saved collector rows, security-review bytes and the exact
decision coverage scope. A recorded rights payload is not a payment receipt.
"""
from __future__ import annotations

import hashlib
import json
from base64 import b64decode
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .quant25_delayed_paper_execution import (
    replay_stored_source_binding,
    verify_stored_source_binding,
)
from .quant25_input_timing import _coverage_review, pinned
from .quant25_live_performance import KST, _EventView, read_ledger
from .quant25_live_source_connection import OPERATING_SESSION, _journal, audit_forward_sources
from .quant25_paper_ledger import _aware, _number_text
from .quant25_paper_live import PROFILE_MODEL_IDS, canonical_sha256


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _owner_coverage(rows, audit):
    """Recheck saved decision references against their original scope and time."""
    receipts = {r["key"]: r for r in rows if r["kind"] == "receipt"}
    verified = {d["decision_id"]: d for d in audit["verified_decisions"]}
    result = {}
    for row in rows:
        if row["kind"] != "decision" or row["key"] not in verified:
            continue
        saved = json.loads(row["body"])
        state = saved["selection"]
        _require(state["state_sha256"] == verified[row["key"]]["state_sha256"],
                 "audited decision changed")
        contract = saved.get("input_timing")
        if contract is None:
            result[state["state_sha256"]] = {"status": "MISSING", "reason": "decision_owner_coverage_missing"}
            continue
        try:
            coverage = pinned(contract["event_coverage"])
            scope = set(coverage.get("reviewed_tickers") or coverage.get("queried_tickers") or [])
            evidence = state["input_evidence"]
            calendar_key = saved["request"]["receipts"]["calendar"]
            calendar = json.loads(receipts[calendar_key]["raw"])
            reviewed_after = max(_aware(item["available_at"], "available_at")
                                 for item in evidence.values())
            bound = _coverage_review(contract, rules_sha=evidence["rules"]["sha256"],
                calendar_sha=evidence["calendar"]["sha256"], stocks=scope,
                calendar=calendar, cutoff=saved["publication_at"],
                execution=state["execution_date"], horizon=state["next_rebalance"],
                reviewed_after=reviewed_after)
            assessment = bound["consumer_assessment"]
            result[state["state_sha256"]] = {"status": "BOUND", "scope": scope,
                "from": state["execution_date"], "until": state["next_rebalance"],
                "coverage_sha256": contract["event_coverage"]["sha256"],
                "review_sha256": contract["event_materiality_review"]["sha256"],
                "warnings": {w["ticker"]: w for w in assessment["warnings"]},
                "source_status": assessment["source_status"]}
        except (KeyError, OSError, ValueError, TypeError) as exc:
            result[state["state_sha256"]] = {"status": "MISSING",
                "reason": "decision_owner_coverage_unverifiable:" + type(exc).__name__}
    return result


def _receipt_matches(daily, cutoff):
    receipt = daily.get("collection_receipt")
    _require(isinstance(receipt, dict) and receipt.get("data_asof") == daily["asof_date"],
             "daily collection receipt date missing")
    raw = Path(receipt["path"]).read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == receipt["sha256"],
             "daily collection receipt hash mismatch")
    original = json.loads(raw)
    _require(all(original.get(k) == receipt.get(k) for k in
                 ("cycle_id", "user_command_ref", "data_asof", "completed_at"))
             and _aware(daily["asof_date"] + "T15:30:00+09:00", "close")
             <= _aware(receipt["completed_at"], "completed_at") <= cutoff,
             "daily collection receipt content/time mismatch")


def _daily_window(daily, bundle, cutoff):
    close = _aware(daily["asof_date"] + "T15:30:00+09:00", "close")
    collector = json.loads(b64decode(bundle["collector_raw_b64"], validate=True))
    review = json.loads(b64decode(bundle["security_review_raw_b64"], validate=True))
    _require(close <= _aware(collector["completed_at"], "collector completed") <= cutoff
             and close <= _aware(review["reviewed_at"], "security reviewed") <= cutoff,
             "daily collector/review before close or after cutoff")
    _require(all(close <= _aware(row["created_at"], "price created") <= cutoff
                 and close <= _aware(row["updated_at"], "price updated") <= cutoff
                 for row in bundle["price_rows"]),
             "daily price row predates close or exceeds cutoff")
    _require(all(Decimal(str(row["close"])).is_finite()
                 and Decimal(str(row["close"])) > 0 for row in bundle["price_rows"]),
             "daily close must be positive and finite")


def _daily_sources(root, rows, audit, *, cutoff, evidence_path, expected_sha256):
    """Use saved execution bytes first; an optional new date needs pinned bytes."""
    sources = {}
    bound_keys = {b["journal_key"]: b for b in audit["execution_bindings"]}
    for row in rows:
        if row["kind"] != "paper_execution" or row["key"] not in bound_keys:
            continue
        binding = bound_keys[row["key"]]
        body = json.loads(row["body"])
        if binding["mode"] != "DELAYED_PAPER" or not binding["stored_source_binding_verified"]:
            continue
        daily = json.loads(row["raw"])
        _require(hashlib.sha256(row["raw"]).hexdigest() == binding["quote_sha256"],
                 "saved daily raw differs from audited execution")
        receipt_raw = b64decode(body["collection_receipt_raw_b64"], validate=True)
        receipt = daily["collection_receipt"]
        _require(hashlib.sha256(receipt_raw).hexdigest() == receipt["sha256"] and
                 all(json.loads(receipt_raw).get(k) == receipt.get(k) for k in
                     ("cycle_id", "user_command_ref", "data_asof", "completed_at")),
                 "saved daily receipt differs from original journal bytes")
        bundle = replay_stored_source_binding(daily, body["stored_source_binding"],
                                               confirmed_at=body["confirmed_at"])
        _daily_window(daily, bundle, cutoff)
        sources[daily["asof_date"]] = (daily, bundle, binding["quote_sha256"])
    if evidence_path is not None:
        _require(expected_sha256 is not None, "daily evidence expected SHA required")
        index_path = Path(evidence_path).resolve()
        raw = index_path.read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == expected_sha256,
                 "daily evidence hash mismatch")
        document = json.loads(raw)
        if document.get("schema") == "Q25_DAILY_VALUATION_EVIDENCE_SET_V1":
            entries = document.get("entries")
            _require(isinstance(entries, list) and entries and all(
                isinstance(item, dict) and set(item) == {"path", "sha256"} for item in entries),
                "daily evidence index entries required")
        else:
            entries = [{"path": str(index_path), "sha256": expected_sha256}]
        for entry in entries:
            path = Path(entry["path"])
            path = (index_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
            _require(path.is_relative_to(Path(__file__).resolve().parents[3] / "reports"),
                     "daily evidence must be within private reports")
            daily_raw = path.read_bytes()
            digest = hashlib.sha256(daily_raw).hexdigest()
            _require(digest == entry["sha256"], "daily evidence entry hash mismatch")
            daily = json.loads(daily_raw)
            day = daily["asof_date"]
            if day in sources and sources[day][2] == digest:
                continue  # Already verified from the immutable execution journal.
            _require(daily.get("schema") == "Q25_DELAYED_DAILY_EVIDENCE_V1"
                     and daily.get("classification") == "STORED_DAILY_OPEN_ASSUMPTION_NOT_SAME_DAY_PIT",
                     "saved daily source schema/classification required")
            _receipt_matches(daily, cutoff)
            bundle = verify_stored_source_binding(daily, confirmed_at=cutoff.isoformat())
            _daily_window(daily, bundle, cutoff)
            _require(day not in sources or sources[day][2] == digest,
                     "new daily evidence conflicts with journal")
            sources[day] = (daily, bundle, digest)
    return sources


def _day_positions(view, known, day):
    close = _aware(day + "T15:30:00+09:00", "close")
    through = [e for e in known if _aware(e["occurred_at"], "occurred_at") <= close]
    historical = _EventView(view.path, view.config, through)
    snapshots = {p: historical.snapshot(p) for p in PROFILE_MODEL_IDS}
    return snapshots


def verify_daily_sources(root: Path, *, as_of: str, audit: dict,
                         evidence_path: Path | None = None, expected_sha256: str | None = None) -> dict:
    """Return scoped source judgments; missing evidence stays unknown."""
    root = Path(root).resolve()
    cutoff = _aware(as_of, "as_of").astimezone(KST)
    _require(cutoff <= datetime.now(timezone.utc), "future source cutoff prohibited")
    fresh = audit_forward_sources(root, as_of=cutoff.isoformat())
    _require(audit == fresh, "caller audit differs from source reconciliation")
    view, ledger_hash = read_ledger(root / "paper_accounting.sqlite3")
    journal, rows, journal_hash = _journal(root / "forward_receipts.sqlite3")
    journal.close()
    _require((ledger_hash, journal_hash) ==
             (fresh["ledger_content_sha256"], fresh["journal_content_sha256"]),
             "source changed after reconciliation")
    owners = _owner_coverage(rows, fresh)
    sources = _daily_sources(root, rows, fresh, cutoff=cutoff,
                             evidence_path=evidence_path, expected_sha256=expected_sha256)
    known = [e for e in view.events if _aware(e["observed_at"], "observed_at") <= cutoff]
    bindings = fresh["execution_bindings"]
    calendar_info = fresh.get("calendar") or {}
    sessions = calendar_info.get("sessions", [])
    # Pre-live synthetic rigs use dates before the fixed 9/7 Live window.
    if root != OPERATING_SESSION.resolve() and not sessions and calendar_info.get("receipt_id"):
        calendar_row = next((r for r in rows if r["key"] == calendar_info["receipt_id"]), None)
        _require(calendar_row is not None and hashlib.sha256(calendar_row["raw"]).hexdigest()
                 == calendar_info["sha256"], "synthetic captured calendar mismatch")
        sessions = json.loads(calendar_row["raw"])
    days = {}
    if bindings:
        start = min(b["execution_date"] for b in bindings)
        for day in sessions:
            if day < start or day > cutoff.date().isoformat():
                continue
            snapshots = _day_positions(view, known, day)
            held = {p["ticker"] for book in snapshots.values() for p in book["positions"]}
            traded = {e["payload"]["ticker"] for e in known
                      if e["event_type"] in {"fill", "paper_fill"}
                      and _aware(e["occurred_at"], "occurred_at").astimezone(KST).date().isoformat() == day}
            rights_tickers = {e["payload"]["ticker"] for e in known if e["event_type"] == "rights"
                              and _aware(e["occurred_at"], "occurred_at").astimezone(KST).date().isoformat() == day}
            relevant = held | traded | rights_tickers
            daily, bundle, daily_hash = sources.get(day, (None, None, None))
            quotes = {q["ticker"]: q for q in daily["quotes"]} if daily else {}
            price_rows = {r["ticker"]: r for r in bundle["price_rows"]} if bundle else {}
            price_hashes = {r["ticker"]: canonical_sha256(r)
                for r in bundle["price_rows"]} if bundle else {}
            applicable = [b for b in bindings if b["execution_date"] <= day]
            owner = owners.get(applicable[-1]["decision_sha256"], {}) if applicable else {}
            reasons, securities = [], {}
            for ticker in sorted(relevant):
                security_reasons = []
                quote = quotes.get(ticker)
                valid_scope = owner.get("status") == "BOUND" and ticker in owner["scope"] and \
                    owner["from"] <= day < owner["until"]
                if not valid_scope:
                    security_reasons.append(owner.get("reason", "decision_owner_coverage_outside_window"))
                if daily is None or quote is None:
                    security_reasons.append("daily_security_source_missing")
                exact = quote is not None and quote.get("source_kind") == "OFFICIAL_DAILY_OHLCV"
                flagged = exact and quote.get("event_coverage_confirmed") is True and \
                    quote.get("unresolved_event") is False
                units = True if flagged and quote.get("units_valid") is True and valid_scope else None
                price = True if flagged and quote.get("valuation_valid") is True and valid_scope else None
                rights = quote.get("rights_review", {}) if exact else {}
                pending = [e for e in known if e["event_type"] == "rights" and
                           e["profile_id"] in snapshots and e["payload"].get("ticker") == ticker and
                           _aware(e["occurred_at"], "rights occurred") <=
                           _aware(day + "T15:30:00+09:00", "close")]
                received = any(e["payload"]["status"] == "RECEIVED" for e in pending)
                stock_right = any(e["payload"]["entitlement_type"] != "CASH" for e in pending)
                if stock_right:
                    units = None
                    price = None
                    security_reasons.append("rights_units_or_price_source_unverified")
                if received:
                    security_reasons.append("rights_payment_source_unverified")
                warning = owner.get("warnings", {}).get(ticker, {})
                cash_unknown = warning.get("unconfirmed_distribution") is True or any(
                    e["payload"]["status"] != "RECEIVED" for e in pending)
                if units is True and price is True and cash_unknown and not stock_right and not received:
                    cash_policy = "PRICE_ONLY_UNCONFIRMED_CASH"
                elif units is True and price is True and rights.get("status") == "CLEAR" and not pending:
                    cash_policy = "RECORDED_RECEIPTS_ONLY"
                else:
                    cash_policy = "UNVERIFIED"
                hashes = ([daily_hash, daily["stored_sources"]["collector_receipt_sha256"],
                           daily["stored_sources"]["security_review_sha256"],
                           price_hashes[ticker], rights.get("source_sha256")]
                          if exact else [])
                if valid_scope:
                    hashes.extend((owner["coverage_sha256"], owner["review_sha256"]))
                securities[ticker] = {"units_valid": units, "price_valid": price,
                                      "cash_policy": cash_policy,
                                      "close": _number_text(Decimal(str(price_rows[ticker]["close"])))
                                      if exact else None,
                                      "source_hashes": sorted(set(h for h in hashes if h)),
                                      "reasons": sorted(set(security_reasons))}
                if units is not True:
                    security_reasons.append("units_unverified")
                if price is not True:
                    security_reasons.append("price_unverified")
                securities[ticker]["reasons"] = sorted(set(security_reasons))
            days[day] = {"securities": securities, "rights_event_ids": [],
                         "reasons": sorted(set(reasons))}
    after_view, after_ledger = read_ledger(root / "paper_accounting.sqlite3")
    del after_view
    after_journal, _, after_hash = _journal(root / "forward_receipts.sqlite3")
    after_journal.close()
    _require((after_ledger, after_hash) == (ledger_hash, journal_hash),
             "source changed during daily verification")
    connected = bool(sources)
    findings = sorted({owner.get("reason") for owner in owners.values()
                       if owner.get("status") != "BOUND" and owner.get("reason")})
    if bindings and not sessions:
        findings.append("captured_calendar_sessions_missing")
    return {"ledger_sha256": ledger_hash, "journal_sha256": journal_hash,
            "days": days, "source_connected": connected,
            "evidence_mode": ("ACTUAL_SAVED_SOURCE" if root == OPERATING_SESSION.resolve()
                              else "SYNTHETIC_TEST_ONLY") if connected else "MISSING",
            "provider_raw_pit_verified": False,
            "rights_payment_source_verified": False, "findings": findings}
