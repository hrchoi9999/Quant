"""Pinned valuation inputs must not reopen retired DBs or expand their cutoff."""
import hashlib
import json

import pytest

from src.quant2.adapters import quant25_paper_source_context as context


def _context(tmp_path):
    payload = {
        "schema": context.SCHEMA,
        "purpose": "RECONSTRUCTION_INPUTS_NOT_OBSERVED_LIVE",
        "captured_at": "2026-09-24T10:00:00+09:00",
        "audit": {
            "as_of": "2026-09-24T09:00:00+09:00",
            "root": str(tmp_path / "absent_original_db"),
            "calendar": {"sessions": ["2026-09-07", "2026-09-23"],
                         "first_date": "2026-09-07", "last_date": "2026-09-28"},
            "verified_decisions": [{"state_sha256": "state",
                                    "publication_at": "2026-09-16T18:00:00+09:00"}],
        },
        "owner_coverage": {"state": {"status": "BOUND", "scope": ["000001"]}},
        "calendar_sessions": ["2026-09-07", "2026-09-23", "2026-09-28"],
    }
    return payload


def _save(tmp_path, payload):
    path = tmp_path / "context.json"
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_context_is_independent_of_original_paths(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("retired observation DB was accessed")

    monkeypatch.setattr(context, "audit_forward_sources", forbidden)
    monkeypatch.setattr(context, "_journal", forbidden)
    path, sha = _save(tmp_path, _context(tmp_path))
    audit, owners = context.load_context(path, sha, as_of="2026-09-25T09:00:00+09:00")
    assert len(audit["verified_decisions"]) == 1
    assert owners["state"]["scope"] == {"000001"}
    assert audit["calendar"]["sessions"] == ["2026-09-07", "2026-09-23"]


def test_modified_context_is_rejected_before_consumption(tmp_path):
    path, sha = _save(tmp_path, _context(tmp_path))
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA mismatch"):
        context.load_context(path, sha, as_of="2026-09-25T09:00:00+09:00")


@pytest.mark.parametrize("case", ["capture", "calendar", "decision", "owner"])
def test_context_cannot_expand_evidence_window(tmp_path, case):
    payload = _context(tmp_path)
    if case == "capture":
        payload["captured_at"] = "2026-09-25T10:00:00+09:00"
    elif case == "calendar":
        payload["calendar_sessions"] = ["2026-09-07", "2026-09-23"]
    elif case == "decision":
        payload["audit"]["verified_decisions"][0]["publication_at"] = "2026-09-24T11:00:00+09:00"
    else:
        payload["owner_coverage"] = {}
    path, sha = _save(tmp_path, payload)
    with pytest.raises(ValueError):
        context.load_context(path, sha, as_of="2026-09-25T09:00:00+09:00")
