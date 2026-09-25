"""Read-only daily valuation of recorded Q25 events; never synthesizes trading.

The owner review binds the exact ledger, trading calendar, close marks and
cashflow checks. Without that review this reader reports coverage, not returns.
The existing ledger performs all cash/units/fee accounting on an in-memory view.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .quant25_forward_connection import evaluation_period_status
from .quant25_paper_ledger import (
    CLASSIFICATION,
    PROFILE_IDS,
    SCHEMA_VERSION,
    LedgerConfig,
    Quant25PaperLedger,
    _aware,
    _decimal,
    _number_text,
)
from .quant25_paper_live import FREEZE_ID, canonical_sha256

KST = timezone(timedelta(hours=9))
SCHEMA = "q25_daily_live_performance_v1"


class _EventView(Quant25PaperLedger):
    """Reuse the ledger arithmetic without opening or modifying its source."""

    def __init__(self, path, config, events):
        super().__init__(path, config)
        self.events = events

    def _connect(self):
        return sqlite3.connect(":memory:")

    def _events(self, connection, profile_id):
        return [e for e in self.events if e["profile_id"] == profile_id]


def read_ledger(path: Path):
    """Pin metadata and event rows in one SQLite read transaction, including WAL."""
    path = path.resolve()
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        metadata = dict(con.execute("SELECT * FROM ledger_metadata WHERE singleton=1").fetchone())
        rows = [dict(r) for r in con.execute("SELECT * FROM ledger_events ORDER BY sequence")]
    finally:
        con.close()
    if (metadata["schema_version"] != SCHEMA_VERSION or metadata["freeze_id"] != FREEZE_ID
            or metadata["classification"] != CLASSIFICATION
            or set(json.loads(metadata["profiles_json"])) != PROFILE_IDS):
        raise ValueError("unsupported ledger metadata")
    config = LedgerConfig(FREEZE_ID, _decimal(metadata["starting_capital"], "capital", positive=True),
                          metadata["currency"], _decimal(metadata["fee_rate"], "fee"),
                          _aware(metadata["created_at"], "created_at"))
    events = [json.loads(r["event_json"]) for r in rows]
    view = _EventView(path, config, events)
    previous = {}
    for row, event in zip(rows, events):
        normalized = view._normalize_event(event)
        if (canonical_sha256(event) != row["payload_sha256"] or normalized != event
                or any(row[k] != event[k] for k in (
                    "event_id", "profile_id", "event_type", "occurred_at", "observed_at", "source_sha256"))):
            raise ValueError("ledger event hash or columns mismatch")
        observed = _aware(event["observed_at"], "observed_at")
        if observed < previous.get(event["profile_id"], config.created_at):
            raise ValueError("ledger observation order mismatch")
        previous[event["profile_id"]] = observed
    digest = canonical_sha256({"metadata": metadata, "rows": rows})
    return view, digest


def _captured_target(event):
    payload = event["payload"]
    provenance = payload.get("selector_provenance", payload)
    timing = provenance.get("input_timing_context", {})
    return (provenance.get("classification") == "CAPTURED_INPUT_PREPARATION"
            and payload.get("historical") is not True
            and timing.get("evidence_mode", "ACTUAL") == "ACTUAL")


def _validate_review(review, digest, as_of, dates):
    if (review.get("schema") != "q25_live_evidence_review_v1"
            or review.get("ledger_content_sha256") != digest
            or _aware(review.get("as_of"), "review as_of") != as_of
            or not str(review.get("review_ref", "")).strip()
            or review.get("evidence_mode") not in {"ACTUAL", "SYNTHETIC_TEST_ONLY"}):
        raise ValueError("review must bind this exact ledger and knowledge cutoff")
    calendar = review["calendar"]
    if (not dates or calendar.get("start") != dates[0] or calendar.get("end") != dates[-1]
            or not str(calendar.get("source_ref", "")).strip()):
        raise ValueError("reviewed calendar must cover the full live window")
    sessions = {}
    for item in calendar["sessions"]:
        day = item["date"]
        close = _aware(item["close_at"], "session close").astimezone(KST)
        if day not in dates or day in sessions or close.date().isoformat() != day:
            raise ValueError("invalid or duplicate calendar session")
        sessions[day] = close
    if list(sessions) != sorted(sessions):
        raise ValueError("sessions must be ordered")
    if set(review["profiles"]) != PROFILE_IDS:
        raise ValueError("exactly three profile reviews required")
    return sessions


def _daily(view, profile, close, as_of, proof, delayed_bindings=None):
    # Late-arriving closes may value the past; original decisions/fills stay fixed.
    delayed_bindings = delayed_bindings or {}
    def effective_at(event):
        binding = delayed_bindings.get(event["event_id"])
        if binding and event["event_type"] == "nonfill":
            return _aware(binding["execution_date"] + "T09:00:00+09:00", "planned paper open")
        return _aware(event["occurred_at"], "occurred")

    known = [e for e in view.events if e["profile_id"] == profile
             and _aware(e["observed_at"], "observed") <= as_of]
    events = [e for e in known if e["event_type"] != "mark"
              and effective_at(e) <= close]
    marks = [e for e in known if e["event_type"] == "mark"
             and _aware(e["payload"]["price_asof"], "price_asof") == close]
    # Marks are evaluated by their price timestamp; receipt order selects revisions.
    book = _EventView(view.path, view.config, events + marks).snapshot(profile)
    reasons = []
    ids = set(proof.get("verified_event_ids", []))
    if any(e["event_id"] not in ids for e in events + marks):
        reasons.append("unreviewed_recorded_events")
    targets = [e for e in events if e["event_type"] == "target"]
    executions = [e for e in events if e["event_type"] in {"paper_fill", "nonfill"}]
    if not executions:
        reasons.append("target_only_not_started")
    for execution in executions:
        preceding = [t for t in targets if _aware(t["observed_at"], "target recorded")
                     < effective_at(execution) and _captured_target(t)]
        bound_hash = execution["payload"].get("execution_evidence", {}).get("target_sha256")
        if not preceding or (execution["event_type"] == "paper_fill"
                             and not any(t["source_sha256"] == bound_hash for t in preceding)):
            reasons.append("execution_decision_provenance_missing")
        delayed = execution["event_id"] in delayed_bindings
        if (_aware(execution["observed_at"], "observed").astimezone(KST).date()
                != effective_at(execution).astimezone(KST).date() and not delayed):
            reasons.append("retrospective_execution_not_live")
        if (execution["payload"].get("execution_evidence", {}).get("kind") == "delayed_daily_open_paper_fill"
                and not delayed):
            reasons.append("sealed_delayed_source_binding_missing")
    if any(e["event_type"] == "fill" for e in events):
        reasons.append("broker_fills_outside_paper_policy")
    close_ids = set(proof.get("close_mark_event_ids", []))
    latest_marks = {e["payload"]["ticker"]: e for e in marks}
    if any(p["ticker"] not in latest_marks
           or latest_marks[p["ticker"]]["event_id"] not in close_ids for p in book["positions"]):
        reasons.append("verified_close_marks_missing")
    day_proof = proof.get("days", {}).get(close.date().isoformat(), {})
    cashflow_status = day_proof.get("cashflow_status")
    if (cashflow_status not in {"REVIEWED_NO_PENDING_RIGHTS", "REVIEWED_PRICE_ONLY_UNCONFIRMED_CASH"}
            or not str(day_proof.get("source_ref", "")).strip()):
        reasons.append("cashflow_coverage_unverified")
    rights = {e["payload"]["right_id"]: e["payload"] for e in events if e["event_type"] == "rights"}
    pending = [r for r in rights.values() if r["status"] != "RECEIVED"]
    warnings = []
    if pending and (any(r["entitlement_type"] != "CASH" for r in pending)
                    or cashflow_status != "REVIEWED_PRICE_ONLY_UNCONFIRMED_CASH"):
        reasons.append("unresolved_rights")
    if cashflow_status == "REVIEWED_PRICE_ONLY_UNCONFIRMED_CASH":
        warnings.append("UNCONFIRMED_CASH_RIGHTS_EXCLUDED_NOT_TOTAL_RETURN")
    if close > as_of:
        reasons.append("session_not_closed")
    if book["nav"] is None or Decimal(book["nav"]) <= 0:
        reasons.append("nav_unavailable")
    # Do not expose an open-price snapshot or idle cash as a daily close NAV.
    return {"nav": book["nav"] if not reasons else None,
            "cash": book["cash"], "total_fees": book["total_fees"],
            "position_count": len(book["positions"]),
            "warnings": warnings,
            "valuation_basis": "PRICE_ONLY_UNCONFIRMED_CASH_EXCLUDED" if warnings else "RECORDED_CASH_RECEIPTS_BASIS",
            "reasons": sorted(set(reasons))}


def evaluate_ledger(path: Path, *, as_of: str, review: dict | None = None):
    cutoff = _aware(as_of, "as_of").astimezone(KST)
    view, digest = read_ledger(path)
    source, delayed_bindings = None, {}
    if (review is not None and path.name == "paper_accounting.sqlite3"
            and (path.parent / "forward_receipts.sqlite3").is_file()):
        # Only source replay can validate the delayed-time exception; caller
        # review flags/IDs never authorize it. Import locally to avoid a cycle.
        from .quant25_live_source_connection import audit_forward_sources
        source = audit_forward_sources(path.parent, as_of=as_of)
        if source["ledger_content_sha256"] != digest:
            raise ValueError("ledger changed during source-connected valuation")
        delayed_bindings = {event_id: binding for binding in source["execution_bindings"]
                            if binding["mode"] == "DELAYED_PAPER" and binding["stored_source_binding_verified"]
                            for event_id in binding["event_ids"]}
    period = evaluation_period_status(cutoff.isoformat())
    dates = [r["date"] for r in next(iter(period["profiles"].values()))["coverage"]]
    sessions = _validate_review(review, digest, cutoff, dates) if review is not None else None
    period.pop("profiles")
    period.update(performance_evidence_reader_connected=False,
                  coverage_basis="owner_reviewed_trading_calendar" if sessions is not None
                  else "calendar_dates_not_confirmed_trading_sessions")
    actual_review = review is not None and review["evidence_mode"] == "ACTUAL"
    result = {"schema": SCHEMA, "as_of": cutoff.isoformat(), "ledger_path": str(view.path),
              "ledger_content_sha256": digest, "ledger_event_count": len(view.events),
              "review_sha256": canonical_sha256(review) if review else None,
              "classification": "PRIVATE_LEDGER_VALUATION_CANDIDATE_NOT_CERTIFIED_LIVE",
              "evaluation_periods": period, "profiles": {}, "candidate_valuations": {},
              "valuation_reader_connected": True,
              "independent_source_evidence_connected": False,
              "owner_review_is_not_source_authentication": True,
              "return_basis": "reviewed_close_to_close_cash_receipts_basis_after_recorded_fees",
              "first_close_is_baseline_not_starting_capital": True,
              "source_ledger_modified": False, "targets_are_fills": False,
              "public_eligible": False, "strategy_changed": False}
    if source is not None:
        result.update(source_connection=source, raw_source_reader_connected=True)
    for profile in sorted(PROFILE_IDS):
        coverage, navs, previous, peak, mdd = [], [], None, None, Decimal(0)
        gap_after_start = False
        known = [e for e in view.events if e["profile_id"] == profile
                 and _aware(e["observed_at"], "observed") <= cutoff]
        started = any(e["event_type"] in {"paper_fill", "nonfill"} for e in known)
        for day in dates:
            row = {"date": day, "nav": None, "return": None, "drawdown": None,
                   "counts_as_live_sample": False, "status": "live_window_unverified"}
            if sessions is None:
                row["reasons"] = ["owner_evidence_review_missing"]
            elif day not in sessions:
                row["status"] = "non_session"
            else:
                daily = _daily(view, profile, sessions[day], cutoff, review["profiles"][profile], delayed_bindings)
                row.update(daily)
                if not actual_review:
                    row.update(status="synthetic_test_not_live", nav=None)
                elif daily["nav"] is not None:
                    nav = Decimal(daily["nav"])
                    row["status"] = "candidate_close_baseline" if previous is None else "candidate_daily_return"
                    if previous is not None:
                        row["return"] = _number_text(nav / previous - 1)
                    else:
                        peak = nav
                    peak = max(peak, nav)
                    drawdown = nav / peak - 1
                    row["drawdown"] = _number_text(drawdown)
                    mdd = min(mdd, drawdown)
                    previous = nav
                    navs.append((day, nav))
                if row["nav"] is None:
                    gap_after_start = gap_after_start or bool(navs)
                    previous, peak = None, None
            coverage.append(row)
        samples = [r for r in coverage if r["return"] is not None]
        continuous = len(navs) >= 2 and not gap_after_start
        counts = {k: sum(e["event_type"] == k for e in known)
                  for k in ("target", "paper_fill", "nonfill", "fill", "mark", "rights")}
        # A review's labels/hash cannot prove raw-source or calendar authenticity.
        # Keep calculations separate from the official Live response throughout.
        result["candidate_valuations"][profile] = {
            "status": "PRIVATE_REVIEWED_CANDIDATE_NOT_LIVE", "event_counts": counts,
            "first_reviewed_close_date": navs[0][0] if navs else None,
            "first_candidate_return_date": samples[0]["date"] if samples else None,
            "last_reviewed_close_date": navs[-1][0] if navs else None,
            "candidate_return_samples": len(samples), "coverage": coverage,
            "close_baseline_cumulative_return": _number_text(navs[-1][1] / navs[0][1] - 1) if continuous else None,
            "max_drawdown": None,
            "close_baseline_max_drawdown": _number_text(mdd) if continuous else None,
            "summary_basis": "first_reviewed_close_to_last_close" if continuous else "insufficient_or_gapped_evidence"}
        result["profiles"][profile] = {
            "status": "NOT_STARTED" if not started else "LIVE_WINDOW_UNVERIFIED", "event_counts": counts,
            "first_verified_close_date": None, "first_verified_performance_date": None,
            "last_verified_close_date": None, "verified_live_samples": 0, "cumulative_return": None,
            "max_drawdown": None, "summary_basis": "independent_source_evidence_connection_pending",
            "coverage": [{"date": d, "nav": None, "return": None, "drawdown": None,
                          "status": "live_window_unverified", "counts_as_live_sample": False,
                          "reasons": ["independent_source_evidence_connection_pending"]} for d in dates]}
    return result
