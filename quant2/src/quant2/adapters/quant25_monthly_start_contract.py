"""Initial monthly INPUT timing and durable completion evidence, not order timing."""

import hashlib
import json
import os
import uuid
from pathlib import Path

import pandas as pd

INITIAL_CONTRACT = "Q25_INITIAL_MONTHLY_INPUT_CURRENT_PUBLICATION_V1_20260911"


def read_contract(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("initial timing contract hash mismatch")
    value = json.loads(raw)
    if (value.get("contract_id") != INITIAL_CONTRACT or value.get("scope") != "INITIAL_MONTHLY_INPUT_ONLY"
            or value.get("portfolio_selection_enabled") is not False
            or value.get("paper_execution_enabled") is not False or not value.get("approval_basis")):
        raise ValueError("explicit approved initial input-only contract required")
    return value


def verify_bundle_files(folder):
    folder = Path(folder).resolve()
    raw = (folder / "READY.json").read_bytes()
    ready = json.loads(raw)
    for name, digest in ready["file_sha256"].items():
        if Path(name).name != name or hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError("publication bundle hash mismatch")
    return ready, hashlib.sha256(raw).hexdigest()


def confirm_visibility(folder, clock):
    """Confirm already-visible sealed bytes; restart never backdates missing proof."""
    folder = Path(folder).resolve()
    ready, ready_hash = verify_bundle_files(folder)
    path = folder / "VISIBILITY.json"
    if path.exists():
        raw = path.read_bytes()
        proof = json.loads(raw)
        if proof["ready_sha256"] != ready_hash:
            raise ValueError("visibility evidence conflict")
        return proof, hashlib.sha256(raw).hexdigest()
    moment = pd.Timestamp(clock())
    if moment.tzinfo is None or moment < pd.Timestamp(ready["commit_started_at"]):
        raise ValueError("visibility clock precedes commit")
    proof = {
        "contract_id": INITIAL_CONTRACT, "ready_sha256": ready_hash,
        "classification": ready["classification"], "confirmed_visible_at": moment.isoformat(),
        "publication_sha256": ready["file_sha256"]["publication.json"],
        "target_sha256": ready["file_sha256"]["target.json"],
        "basis": "POST_RENAME_FULL_BYTES_VERIFICATION_OR_CURRENT_RESTART_OBSERVATION",
    }
    raw = (json.dumps(proof, sort_keys=True, indent=2) + "\n").encode()
    temporary = folder / (".visibility-" + uuid.uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(temporary, path)
    return proof, hashlib.sha256(raw).hexdigest()


def resolved_receipt(con, record):
    if not record.get("completion_required"):
        return record
    key = "receipt-completion:" + record["receipt_id"]
    row = con.execute("SELECT body FROM journal WHERE key=? AND kind='receipt_completion'", (key,)).fetchone()
    if row is None:
        raise ValueError("receipt completion evidence missing; not available")
    done = json.loads(row[0])
    if done["sha256"] != record["sha256"] or done["receipt_id"] != record["receipt_id"]:
        raise ValueError("receipt completion binding mismatch")
    moment = done["completed_at"]
    if pd.Timestamp(moment) < pd.Timestamp(record["first_observed_at"]):
        raise ValueError("receipt completion precedes observation")
    return {**record, "arrived_at": moment, "available_at": moment, "receipt_completed_at": moment,
            "completion_required": False, "completion_evidence": done}


def complete_receipt(connection, record):
    """Called AFTER primary receipt commit; missing evidence gets current re-observation."""
    with connection._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        key = "receipt-completion:" + record["receipt_id"]
        prior = con.execute("SELECT body FROM journal WHERE key=?", (key,)).fetchone()
        if prior is None:
            # Primary bytes were committed by the previous transaction, before this sample.
            moment = pd.Timestamp(connection.clock())
            if moment.tzinfo is None or moment < pd.Timestamp(record["first_observed_at"]):
                raise ValueError("invalid receipt completion clock")
            connection._put(con, key, "receipt_completion", {
                "receipt_id": record["receipt_id"], "sha256": record["sha256"],
                "completed_at": moment.isoformat(), "contract_id": INITIAL_CONTRACT,
                "basis": "POST_PRIMARY_COMMIT_VERIFIED_OR_CURRENT_RESTART_OBSERVATION",
                "classification": record["classification"],
            })
        result = resolved_receipt(con, record)
    return result
