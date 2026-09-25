"""Read-only reconciliation of the Q25 durable journal with its paper ledger.

No review booleans, fabricated events, recovery, capture, collection or publishing.
Stored source bytes and replayed executions supply evidence; absent records stay
absent. Source matching is distinct from source completeness and Live readiness.
"""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from base64 import b64decode
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .quant25_delayed_paper_execution import replay_delayed_execution
from .quant25_forward_connection import ForwardConnection
from .quant25_incremental_selection import SOURCES
from .quant25_live_performance import KST, _EventView, read_ledger
from .quant25_monthly_start_contract import resolved_receipt
from .quant25_observed_paper_execution import paper_execution_events
from .quant25_paper_ledger import _aware, _number_text
from .quant25_paper_live import FREEZE_ID, PROFILE_MODEL_IDS, canonical_sha256

QUANT2 = Path(__file__).resolve().parents[3]
OPERATING_SESSION = QUANT2 / "reports/quant2_0/q25_os_forward_connection_20260910/observation_session_01"


def _journal(path):
    source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    source.row_factory = sqlite3.Row
    try:
        source.execute("PRAGMA query_only=ON")
        source.execute("BEGIN")
        rows = [dict(r) for r in source.execute("SELECT sequence,key,kind,body,raw FROM journal ORDER BY sequence")]
    finally:
        source.close()
    # Existing receipt-completion and execution-binding validators run on this
    # captured memory image, never ForwardConnection._connect/recover/status.
    memory = sqlite3.connect(":memory:")
    memory.row_factory = sqlite3.Row
    memory.execute("CREATE TABLE journal(sequence INTEGER, key TEXT PRIMARY KEY, kind TEXT, body TEXT, raw BLOB)")
    memory.executemany("INSERT INTO journal VALUES(:sequence,:key,:kind,:body,:raw)", rows)
    memory.execute("PRAGMA query_only=ON")
    digest = canonical_sha256([{**r, "raw": hashlib.sha256(r["raw"]).hexdigest()
                                if r["raw"] is not None else None} for r in rows])
    return memory, rows, digest


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _decision(saved, receipts, view, cutoff):
    state = saved["selection"]
    published = _aware(saved["publication_at"], "publication")
    opened = _aware(state["execution_date"] + "T09:00:00+09:00", "open")
    _require(canonical_sha256({k: v for k, v in state.items() if k != "state_sha256"})
             == state["state_sha256"], "decision state hash mismatch")
    _require(state["freeze_id"] == FREEZE_ID and state["historical"] is False
             and published < opened and published <= cutoff, "decision time/freeze/historical mismatch")
    expected = saved["request"]["receipts"]
    _require(set(expected) == SOURCES and set(state["input_evidence"]) == SOURCES,
             "decision input source set mismatch")
    for name, key in expected.items():
        record, raw = receipts[key]
        used = state["input_evidence"][name]
        _require(record["source"] == name and used["sha256"] == hashlib.sha256(raw).hexdigest()
                 and used["receipt_id"] == key
                 and _aware(record["arrived_at"], "arrival") <= published
                 and _aware(record["available_at"], "available") <= published,
                 "decision receipt bytes/availability mismatch")
    events = [view._normalize_event(e) for e in saved["events"]]
    _require(len(events) == 3 and {e["profile_id"] for e in events} == set(PROFILE_MODEL_IDS)
             and all(e["event_type"] == "target" and e["source_sha256"] == state["state_sha256"]
                     and _aware(e["observed_at"], "target observed") == published for e in events),
             "decision target event binding mismatch")
    for e in events:
        p = e["payload"]
        if "selector_provenance" in p:
            _require(p["selector_provenance"]["state_sha256"] == state["state_sha256"],
                     "target selector provenance mismatch")
            selected = state["profiles"][e["profile_id"]]
            expected_positions = sorted((str(t["ticker"]), t["asset_type"], Decimal(str(t["target_weight"])))
                                        for t in selected["target_positions"])
            actual_positions = sorted((str(t["ticker"]), t["asset_type"], Decimal(str(t["target_weight"])))
                                      for t in p["positions"])
            _require(expected_positions == actual_positions
                     and Decimal(str(p["cash_weight"])) == Decimal(str(selected["cash_target"])),
                     "target positions differ from saved selection")
        else:
            _require(p == state, "full target differs from saved selection")
    return events


def _prestate(events):
    return canonical_sha256([[e["event_id"], canonical_sha256(e)] for e in events])


def _sealed_plan(plan, key, decisions, view, previous_events):
    """Reconstruct the sealed book from preceding journal events, not assertions."""
    day = plan["execution_date"]
    _require(plan.get("schema") == "Q25_DELAYED_PAPER_PLAN_V1"
             and plan.get("classification") == "DELAYED_PAPER_PREOPEN_PLAN_NOT_EXECUTION",
             "sealed plan schema/classification mismatch")
    _require(key == plan["plan_id"] == "delayed-plan:" + day,
             "sealed plan identity mismatch")
    saved = decisions.get(plan["decision_id"])
    _require(saved is not None and canonical_sha256(saved) == plan["decision_sha256"],
             "sealed plan must reference an already recorded decision")
    _require(saved["selection"]["execution_date"] == day
             and saved["selection"]["state_sha256"] == plan["state_sha256"]
             and plan["publication_at"] == saved["publication_at"]
             and _aware(plan["publication_at"], "published") <= _aware(plan["sealed_at"], "sealed")
             < _aware(day + "T09:00:00+09:00", "open"), "sealed plan time/decision mismatch")
    _require(Decimal(plan["fee_rate"]) == view.config.fee_rate
             and plan["actual_execution"] is False and plan["broker_execution"] is False,
             "sealed plan cost/classification mismatch")
    _require(_prestate(previous_events) == plan["ledger_prestate_sha256"],
             "sealed plan previous ledger differs from recorded events")
    historical = _EventView(view.path, view.config, previous_events)
    books = {p: {k: v for k, v in historical.snapshot(p, as_of=plan["sealed_at"]).items()
                 if k in {"positions", "cash", "starting_capital"}} for p in PROFILE_MODEL_IDS}
    _require(books == plan["book_inputs"] and canonical_sha256(books) == plan["book_inputs_sha256"],
             "sealed plan book differs from recorded ledger")
    return saved


def audit_forward_sources(root: Path, *, as_of: str):
    """Reconcile immutable events and raw receipts without a caller-made review."""
    root = root.resolve()
    cutoff = _aware(as_of, "as_of").astimezone(KST)
    _require(cutoff <= datetime.now(timezone.utc), "future knowledge cutoff prohibited")
    view, ledger_hash = read_ledger(root / "paper_accounting.sqlite3")
    con, rows, journal_hash = _journal(root / "forward_receipts.sqlite3")
    findings, matched, execution_bindings, price_matches = [], [], [], []
    result = {"schema": "q25_live_source_connection_v1", "as_of": cutoff.isoformat(),
              "root": str(root), "ledger_content_sha256": ledger_hash,
              "journal_content_sha256": journal_hash,
              "registered_operating_session": root == OPERATING_SESSION.resolve(),
              "raw_source_reader_connected": True, "source_records_modified": False,
              "calendar": None, "initial_capital": None, "profiles": {}}
    try:
        config = json.loads(con.execute("SELECT body FROM journal WHERE key='config'").fetchone()[0])
        _require(config["freeze_id"] == view.config.freeze_id
                 and Decimal(str(config["capital_per_profile"])) == view.config.starting_capital
                 and Decimal(str(config["fee_rate"])) == view.config.fee_rate
                 and _aware(config["observation_started_at"], "observation start") == view.config.created_at,
                 "journal/ledger capital, fee or creation mismatch")
        result["initial_capital"] = {
            "per_profile": _number_text(view.config.starting_capital), "currency": view.config.currency,
            "recorded_at": view.config.created_at.isoformat(), "config_sha256": canonical_sha256(config),
            "journal_ledger_match": True, "is_verified_prior_close": False,
            "basis": "RECORDED_PAPER_INITIAL_CASH_NOT_BROKER_CAPITAL"}
        receipts = {}
        for row in rows:
            if row["kind"] != "receipt":
                continue
            record = resolved_receipt(con, json.loads(row["body"]))
            if _aware(record["arrived_at"], "arrival") > cutoff:
                continue
            _require(row["raw"] is not None and hashlib.sha256(row["raw"]).hexdigest() == record["sha256"]
                     and row["key"] == record["receipt_id"], "captured raw receipt hash mismatch")
            receipts[row["key"]] = (record, row["raw"])
        calendars = [(r, raw) for r, raw in receipts.values() if r["source"] == "calendar"]
        if calendars:
            record, raw = max(calendars, key=lambda item: _aware(item[0]["arrived_at"], "arrival"))
            days = json.loads(raw)
            _require(isinstance(days, list) and days == sorted(set(days))
                     and all(date.fromisoformat(d).isoformat() == d for d in days), "invalid recorded calendar")
            covered = bool(days and days[0] <= "2026-09-07" and days[-1] >= cutoff.date().isoformat())
            result["calendar"] = {"receipt_id": record["receipt_id"], "sha256": record["sha256"],
                "arrived_at": record["arrived_at"], "source_path": record["source_path"],
                "first_date": days[0] if days else None, "last_date": days[-1] if days else None,
                "covers_requested_window": covered,
                "sessions": [d for d in days if "2026-09-07" <= d <= cutoff.date().isoformat()],
                "basis": "CAPTURED_SOURCE_CALENDAR_NOT_REVIEW_SUPPLIED_DATES"}
            if not covered:
                findings.append("calendar_window_not_covered")
        else:
            findings.append("recorded_calendar_missing")
        decisions, plans = {}, {}
        verified_decisions, verified_plans = [], []
        previous_events = []
        accounting_sources = []
        for row in rows:
            body = json.loads(row["body"])
            if row["kind"] == "decision":
                if _aware(body["publication_at"], "publication") > cutoff:
                    continue
                events = _decision(body, receipts, view, cutoff)
                decisions[row["key"]] = body
                state = body["selection"]
                verified_decisions.append({"decision_id": row["key"],
                    "decision_sha256": canonical_sha256(body),
                    "publication_at": body["publication_at"],
                    "state_sha256": state["state_sha256"],
                    "decision_date": state["decision_date"],
                    "decision_cutoff": state["decision_cutoff"],
                    "execution_date": state["execution_date"],
                    "next_rebalance": state["next_rebalance"],
                    "expires_at": state.get("input_timing_context", {}).get("expires_at"),
                    "profiles": {p: {"model_id": state["profiles"][p]["model_id"],
                        "target_positions": state["profiles"][p]["target_positions"],
                        "cash_target": state["profiles"][p]["cash_target"]}
                        for p in PROFILE_MODEL_IDS}})
            elif row["kind"] == "delayed_plan":
                if _aware(body["sealed_at"], "sealed") > cutoff:
                    continue
                _sealed_plan(body, row["key"], decisions, view, previous_events)
                plans[row["key"]] = body
                verified_plans.append({"plan_id": row["key"],
                    "plan_sha256": canonical_sha256(body),
                    "decision_id": body["decision_id"],
                    "execution_date": body["execution_date"],
                    "sealed_at": body["sealed_at"]})
                continue
            elif row["kind"] == "paper_execution":
                body_events = body.get("events", [])
                binding = body.get("decision_binding", {})
                observed = body.get("confirmed_at") or binding.get("verified_at") or (body_events[0]["observed_at"] if body_events else None)
                _require(observed is not None, "execution missing observation evidence")
                if _aware(observed, "execution observed") > cutoff:
                    continue
                selected = [b for b in decisions.values() if
                            "paper-execution:" + b["selection"]["execution_date"] == row["key"]]
                _require(len(selected) == 1, "execution exact scheduled decision missing")
                saved = selected[0]
                state = saved["selection"]
                _require(row["raw"] is not None, "execution original quotes missing")
                quote_hash = hashlib.sha256(row["raw"]).hexdigest()
                mode = body.get("mode", "OBSERVED_OPEN")
                if mode == "DELAYED_PAPER":
                    plan = plans.get(body["plan_id"])
                    _require(plan is not None and canonical_sha256(plan) == body["plan_sha256"],
                             "delayed execution missing exact earlier sealed plan")
                    _require(_prestate(previous_events) == plan["ledger_prestate_sha256"],
                             "ledger changed between sealed plan and delayed execution")
                    _require(body["daily_sha256"] == quote_hash,
                             "delayed daily raw hash mismatch")
                    stored = body.get("stored_source_binding")
                    replay = replay_delayed_execution(plan, saved, json.loads(row["raw"]),
                        confirmed_at=observed, daily_sha256=quote_hash,
                        receipt_raw=b64decode(body["collection_receipt_raw_b64"], validate=True),
                        source_binding_verified=stored is not None, stored_source_binding=stored)
                    _require(replay == body, "delayed execution differs from sealed plan/raw replay")
                    # Replay proves bookkeeping, not the daily producer's claims
                    # of official bars or security-specific review provenance.
                    if stored is None:
                        findings.append("delayed_daily_and_security_review_source_binding_pending:" + row["key"])
                elif saved.get("input_timing"):
                    checker = ForwardConnection(root, freeze_dir=QUANT2 / "reports/quant2_0/q25_three_profile_freeze_20260908/run_03")
                    checker._verified_execution_target(con, row, day=cutoff.date().isoformat())
                if mode != "DELAYED_PAPER":
                    _require(mode == "OBSERVED_OPEN", "unsupported paper execution mode")
                    opened = state["execution_date"] + "T09:00:00+09:00"
                    historical = _EventView(view.path, view.config, previous_events)
                    books = {p: historical.snapshot(p, as_of=opened) for p in PROFILE_MODEL_IDS}
                    replay = paper_execution_events(state, books, json.loads(row["raw"]),
                        received_at=observed, quote_sha256=quote_hash, fee_rate=view.config.fee_rate)
                _require(replay["events"] == body["events"] and replay["audit"] == body["audit"],
                         "recorded execution/nonexecution differs from quote and decision replay")
                events = [view._normalize_event(e) for e in body["events"]]
                execution_bindings.append({"journal_key": row["key"], "decision_sha256": state["state_sha256"],
                    "quote_sha256": quote_hash, "observed_at": observed,
                    "event_ids": [e["event_id"] for e in events], "replay_matches": True,
                    "mode": mode, "plan_sha256": body.get("plan_sha256"),
                    "execution_date": state["execution_date"],
                    "stored_source_binding_verified": mode == "DELAYED_PAPER" and stored is not None})
            elif row["kind"] == "accounting":
                _require(len(body["events"]) == 1, "accounting envelope must contain one event")
                event = body["events"][0]
                if _aware(event["observed_at"], "accounting observed") > cutoff:
                    continue
                _require(row["raw"] is not None and hashlib.sha256(row["raw"]).hexdigest() == event["source_sha256"]
                         and json.loads(row["raw"]) == event["payload"], "accounting raw payload/hash mismatch")
                events = [view._normalize_event(event)]
                accounting_sources.extend(events)
            else:
                continue
            matched.extend(events)
            previous_events.extend(events)
        known = [e for e in view.events if _aware(e["observed_at"], "observed") <= cutoff]
        _require(matched == known, "journal/ledger event mismatch or undelivered outbox; owner recovery required")
        # Mark price must match a separately captured price source, not just the
        # accounting payload that contains that same asserted number.
        price_sources = []
        for record, raw in receipts.values():
            if record["source"] == "prices":
                table = pd.read_csv(io.BytesIO(raw), dtype={"ticker": str, "date": str})
                _require(not table.duplicated(["ticker", "date"]).any(), "duplicate captured price key")
                price_sources.append((record, table.set_index(["ticker", "date"])))
        price_sources.sort(key=lambda pair: _aware(pair[0]["arrived_at"], "price arrival"), reverse=True)
        for event in accounting_sources:
            p = event["payload"]
            if event["event_type"] == "mark":
                key = (p["ticker"], _aware(p["price_asof"], "mark time").astimezone(KST).date().isoformat())
                found = False
                for record, table in price_sources:
                    if key not in table.index or _aware(record["arrived_at"], "price arrival") > _aware(event["observed_at"], "mark observed"):
                        continue
                    value = Decimal(str(table.loc[key, "close"]))
                    found = value.is_finite() and value > 0 and value == Decimal(p["price"])
                    price_matches.append({"event_id": event["event_id"], "price_receipt_id": record["receipt_id"],
                                          "price_source_sha256": record["sha256"], "close_matches": found})
                    break
                if not found:
                    findings.append("mark_captured_close_missing_or_different:" + event["event_id"])
            elif event["event_type"] in {"fill", "nonfill"}:
                findings.append("standalone_accounting_execution_not_bound_to_decision:" + event["event_id"])
            elif event["event_type"] == "rights" and p["status"] == "RECEIVED":
                findings.append("rights_payment_source_binding_required:" + event["event_id"])
        if read_ledger(view.path)[1] != ledger_hash:
            raise ValueError("ledger changed during source reconciliation")
        check, _, current_journal_hash = _journal(root / "forward_receipts.sqlite3")
        check.close()
        _require(current_journal_hash == journal_hash, "journal changed during source reconciliation")
        for profile in PROFILE_MODEL_IDS:
            events = [e for e in matched if e["profile_id"] == profile]
            executions = [e for e in events if e["event_type"] in {"paper_fill", "nonfill"}]
            marks = [e for e in events if e["event_type"] == "mark"]
            result["profiles"][profile] = {"target_count": sum(e["event_type"] == "target" for e in events),
                "execution_count": len(executions), "mark_count": len(marks),
                "status": "NOT_STARTED" if not executions else "VALUATION_SOURCE_REVIEW_REQUIRED",
                "first_recorded_execution_at": executions[0]["occurred_at"] if executions else None,
                "verified_live_samples": 0, "return": None}
        result.update(status="SOURCE_RECORDS_MATCH" if not findings else "SOURCE_FOLLOWUP_REQUIRED",
            matched_event_count=len(matched), captured_receipt_count=len(receipts),
            execution_bindings=execution_bindings, mark_price_matches=price_matches,
            verified_decisions=verified_decisions, verified_plans=verified_plans,
            findings=sorted(set(findings)),
            remaining=["DAILY_HELD_SECURITY_RIGHTS_AND_PRICE_COVERAGE", "FIRST_ACTUAL_EXECUTION_AND_CLOSE",
                       "INITIAL_CAPITAL_TO_FIRST_VERIFIED_NAV", "SERVICE_CONSUMER_CONNECTION"],
            source_consistency_is_live_readiness=False, public_eligible=False)
        return result
    finally:
        con.close()
