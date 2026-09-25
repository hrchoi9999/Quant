"""Pinned reconstruction inputs, independent of the old observation databases."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .quant25_daily_valuation_sources import _owner_coverage
from .quant25_live_source_connection import _journal, audit_forward_sources
from .quant25_paper_ledger import _aware

SCHEMA = "q25_paper_source_context_v1"


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def capture_context(operating_root: Path, *, as_of: str, output: Path) -> str:
    """Archive audited decisions/calendar/coverage once; never modify the DBs."""
    audit = audit_forward_sources(operating_root, as_of=as_of)
    journal, rows, journal_hash = _journal(operating_root / "forward_receipts.sqlite3")
    journal.close()
    _require(journal_hash == audit["journal_content_sha256"], "journal changed after audit")
    owners = _owner_coverage(rows, audit)
    calendar = audit["calendar"]
    calendar_raw = next(row["raw"] for row in rows
                        if row["key"] == calendar["receipt_id"] and row["kind"] == "receipt")
    _require(hashlib.sha256(calendar_raw).hexdigest() == calendar["sha256"],
             "captured calendar SHA mismatch")
    calendar_sessions = json.loads(calendar_raw)
    for owner in owners.values():
        if "scope" in owner:
            owner["scope"] = sorted(owner["scope"])
    after = audit_forward_sources(operating_root, as_of=as_of)
    _require(all(audit[key] == after[key] for key in
                 ("ledger_content_sha256", "journal_content_sha256")),
             "observation source changed during capture")
    payload = {"schema": SCHEMA, "captured_at": datetime.now(timezone.utc).isoformat(),
               "purpose": "RECONSTRUCTION_INPUTS_NOT_OBSERVED_LIVE",
               "audit": audit, "owner_coverage": owners,
               "calendar_sessions": calendar_sessions}
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def load_context(path: Path, expected_sha256: str, *, as_of: str):
    """The externally pinned bytes are the trust root; no archived paths are read."""
    raw = path.read_bytes()
    _require(expected_sha256 and hashlib.sha256(raw).hexdigest() == expected_sha256.lower(),
             "source context SHA mismatch")
    payload = json.loads(raw)
    _require(payload.get("schema") == SCHEMA and
             payload.get("purpose") == "RECONSTRUCTION_INPUTS_NOT_OBSERVED_LIVE",
             "wrong source context")
    audit = payload["audit"]
    cutoff = _aware(as_of, "requested as_of")
    _require(_aware(audit["as_of"], "audit as_of") <=
             _aware(payload["captured_at"], "context capture") <= cutoff <=
             datetime.now(timezone.utc), "source context cutoff mismatch")
    sessions = payload["calendar_sessions"]
    _require(sessions == sorted(set(sessions)) and sessions and
             all(date.fromisoformat(day).isoformat() == day for day in sessions) and
             sessions[0] == audit["calendar"]["first_date"] <= "2026-09-07" and
             sessions[-1] == audit["calendar"]["last_date"] >= cutoff.date().isoformat(),
             "source context calendar does not cover requested window")
    _require(audit["calendar"]["sessions"] == [day for day in sessions if
             "2026-09-07" <= day <= _aware(audit["as_of"], "audit as_of").date().isoformat()],
             "audited calendar prefix changed")
    audit["calendar"]["sessions"] = [day for day in sessions if
                                     "2026-09-07" <= day <= cutoff.date().isoformat()]
    owners = payload["owner_coverage"]
    for decision in audit["verified_decisions"]:
        _require(_aware(decision["publication_at"], "publication") <=
                 _aware(audit["as_of"], "audit as_of"), "future context decision")
        _require(decision["state_sha256"] in owners, "source context owner review missing")
    for owner in owners.values():
        owner["scope"] = set(owner.get("scope", []))
    return audit, owners
