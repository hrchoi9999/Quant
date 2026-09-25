"""Explicit monthly ETF publication-to-receipt connection; never runs a model.

The owner supplies independently verified publication evidence and pinned hashes.
Hash/contract validation is not proof that an owner declaration is authentic.
No historical target is relabelled, and no scheduler/export is enabled here.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path

import pandas as pd

from src.backtest.configs.s6_defensive_config import S6DefensiveConfig
from src.evaluation.normalized_nav import next_open_after_publication

from .quant25_incremental_selection import CANDIDATE_CONTRACT, aware
from .quant25_monthly_start_contract import (
    INITIAL_CONTRACT,
    complete_receipt,
    read_contract,
    verify_bundle_files,
)
from .quant25_paper_live import canonical_sha256

SCHEMA = "q25_monthly_etf_publication_v1"
SEMANTICS = "UNSCALED_MONTHLY_TARGET_NOT_HOLDINGS"
PRODUCER = "quant25_cadence.etf_events:M"
SOURCE_SUFFIXES = (
    "quant25_cadence.py",
    "s6_defensive_config.py",
    "s6_defensive_allocator.py",
)


def _read(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("source hash mismatch")
    return raw, json.loads(raw)


def _digest(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("explicit SHA256 required")
    return value


def _day(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is not None or stamp != stamp.normalize():
        raise ValueError("unambiguous session date required")
    return stamp.strftime("%Y-%m-%d")


def validate_monthly_publication(
    target, publication, calendar, *, freeze, received_at, target_sha256, calendar_sha256,
    test_only=False, candidate_timing=None,
):
    """Pure receipt preflight. Publication timestamps are never synthesized."""
    evidence = "TEST_ONLY" if test_only else "ACTUAL_PRODUCER_PUBLICATION"
    initial = publication.get("timing_contract_id") == INITIAL_CONTRACT
    if candidate_timing is not None and not test_only:
        raise ValueError("candidate timing is preflight only; operating policy not approved")
    if test_only and any(
        value.get("actual_publication") is not False or value.get("active") is not False
        for value in (target, publication)
    ):
        raise ValueError("explicit inactive TEST_ONLY packet required")
    if (
        publication.get("schema") != SCHEMA
        or publication.get("owner") != "Quant OS"
        or publication.get("classification") != evidence
        or publication.get("semantics") != SEMANTICS
        or publication.get("producer") != PRODUCER
    ):
        raise ValueError("actual frozen monthly target publication evidence required")
    if not isinstance(publication.get("publication_id"), str) or not publication["publication_id"].strip():
        raise ValueError("owner publication ID required")
    for field in ("freeze_id", "freeze_manifest_sha256", "execution_contract_sha256"):
        if publication.get(field) != freeze[field]:
            raise ValueError("frozen revision mismatch")
    sources = {
        Path(p).name: h for p, h in freeze["manifest"]["source_hashes"].items() if Path(p).name in SOURCE_SUFFIXES
    }
    if len(sources) != len(SOURCE_SUFFIXES):
        raise ValueError('Frozen calculation source references incomplete')
    if publication.get('calculation_revision') is not None:
        from src.quant2.operations.etf_revision import read_revision, revision_sources
        revision = read_revision(publication['calculation_revision'], publication.get('calculation_revision_sha256'), freeze)
        if not test_only and _day(target['decision_date']) < revision['effective_from_decision_date']:
            raise ValueError('Calculation revision cannot rewrite earlier monthly decisions')
        sources.update(revision_sources(revision))
    elif publication.get('calculation_revision_sha256') is not None:
        raise ValueError('Missing calculation revision ID')
    if publication.get("producer_source_hashes") != sources:
        raise ValueError("producer source revision mismatch")
    metadata_hashes = [
        h
        for p, h in freeze["execution_contract"]["source_hashes"].items()
        if p.replace("\\", "/").endswith("/etf_meta.csv")
    ]
    if len(metadata_hashes) != 1 or publication.get("metadata_sha256") != metadata_hashes[0]:
        raise ValueError("frozen ETF metadata revision mismatch")
    if publication.get("target_sha256") != _digest(target_sha256):
        raise ValueError("publication target hash mismatch")
    inputs = publication.get("generation_input_sha256", {})
    if set(inputs) != {"prices", "calendar", "previous_target_state"}:
        raise ValueError("generation input provenance required")
    for digest in inputs.values():
        _digest(digest)
    if inputs["calendar"] != calendar_sha256:
        raise ValueError("generation calendar mismatch")
    if (
        target.get("model_code") != "S6_REFERENCE"
        or target.get("run_id") != "Q25_CADENCE_ETF"
        or target.get("evidence_state") != evidence
    ):
        raise ValueError("research or generic S6 target cannot become actual monthly intent")
    decision, execution = _day(target.get("decision_date")), _day(target.get("execution_date"))
    if calendar != sorted(set(calendar)) or decision not in calendar or execution not in calendar:
        raise ValueError("confirmed ordered calendar and target sessions required")
    if any(_day(d) != d for d in calendar):
        raise ValueError("canonical calendar dates required")
    month = pd.Timestamp(decision).to_period("M")
    month_end = month.end_time.strftime("%Y-%m-%d")
    monthly = [d for d in calendar if pd.Timestamp(d).to_period("M") == month]
    if calendar[-1] <= month_end or decision != max(monthly):
        raise ValueError("completed month-end and next confirmed session required; no initial seed default")
    reference_execution = calendar[calendar.index(decision) + 1]
    if candidate_timing is None and execution != reference_execution:
        raise ValueError("ETF reference execution must be the next confirmed session")
    if publication.get("data_asof") != decision:
        raise ValueError("generation data_asof must equal decision session")
    published, generated, received = (
        aware(target.get("published_at")),
        aware(publication.get("generated_at")),
        aware(received_at),
    )
    if aware(publication.get("published_at")) != published:
        raise ValueError("publication timestamp mismatch")
    if not (aware(decision + "T15:30:00+09:00") <= generated <= published <= received):
        raise ValueError("missing, future or nonchronological generation/publication/receipt time")
    if initial:
        ends = {}
        for d in calendar:
            ends[pd.Timestamp(d).to_period("M")] = d
        completed = [d for period, d in ends.items()
                     if calendar[-1] > period.end_time.strftime("%Y-%m-%d")
                     and aware(d + "T15:30:00+09:00") <= generated]
        if (not completed or decision != max(completed) or candidate_timing is not None
                or target.get("timing_contract_id") != INITIAL_CONTRACT
                or target.get("reference_execution_date") != reference_execution
                or target.get("portfolio_order") is not False or target.get("weekly_execution_date") is not None
                or publication.get("initial_branch") != "EXPLICIT_UNINVESTED_CASH_CANDIDATE"
                or publication.get("publication_time_basis") != "EMISSION_ONLY_USE_VISIBILITY_EVIDENCE"):
            raise ValueError("initial input-only latest completed monthly contract required")
        _digest(publication.get("initial_contract_sha256"))
    if candidate_timing is not None:
        if (
            candidate_timing.get("contract_id") != CANDIDATE_CONTRACT
            or candidate_timing.get("classification") != "TEST_ONLY"
            or candidate_timing.get("sealed_target") is not False
            or target.get("reference_execution_date") != reference_execution
        ):
            raise ValueError("new unsealed target timing candidate required; BLOCKED_STALE_TARGET")
        first_open = next_open_after_publication(max(published, received), pd.DatetimeIndex(calendar))
        if execution != first_open.strftime("%Y-%m-%d"):
            raise ValueError("new target must use first open after emission and input readiness")
    if not initial and published >= aware(execution + "T09:00:00+09:00"):
        raise ValueError("publication after reference execution window")
    weights = target.get("weights", {})
    if (
        not isinstance(weights, dict)
        or not weights
        or "CASH" not in weights
        or any(
            isinstance(w, bool) or not isinstance(w, (float, int)) or not math.isfinite(w) or w < 0 or w > 1
            for w in weights.values()
        )
        or abs(sum(weights.values()) - 1) > 1e-9
        or len([t for t, w in weights.items() if t != "CASH" and w > 0]) > 5
    ):
        raise ValueError("fully funded unscaled monthly ETF weights required")
    return {
        "decision_date": decision,
        "published_at": published.isoformat(),
        "received_at": received.isoformat(),
        "semantics": SEMANTICS,
        "freeze_id": freeze["freeze_id"],
        "target_sha256": target_sha256,
        "publication_id": publication["publication_id"],
        "historical_receipt_inferred": False,
        "counts_as_live_sample": False,
    }


def receive_monthly_etf_intent(
    connection, target_path, publication_path, calendar_path, *, target_sha256, publication_sha256, calendar_sha256,
    preflight_only=False, candidate_timing=None, visibility_path=None, visibility_sha256=None,
    test_only_receipt=False, after_primary_commit=None, backup_evidence=None,
):
    """Append an atomic binding and ordinary receipt in an initialized journal.

    Call only for an owner-verified *actual* publication. The output is directly
    usable as the etf_intent receipt in the existing nine-input connection.
    Reuse preserves first reception; conflicting publications fail closed.
    """
    if test_only_receipt:
        if not connection.root.name.startswith("SYNTHETIC_TEST_ONLY") or any(
            not Path(p).resolve().is_relative_to(connection.root) for p in (target_path, publication_path, calendar_path)
        ):
            raise ValueError("test receipts require isolated marked journal and packet paths")
    elif after_primary_commit is not None:
        raise ValueError("actual receiver forbids injected commit hooks")
    if preflight_only:
        root = connection.root.resolve()
        if not root.name.startswith("SYNTHETIC_TEST_ONLY") or any(
            not Path(p).resolve().is_relative_to(root) for p in (target_path, publication_path, calendar_path)
        ):
            raise ValueError("preflight requires isolated SYNTHETIC_TEST_ONLY packet paths")
    elif candidate_timing is not None:
        raise ValueError("candidate timing cannot write an actual receipt")
    freeze = connection._freeze()
    raw, target = _read(target_path, target_sha256)
    publication_raw, publication = _read(publication_path, publication_sha256)
    _, calendar = _read(calendar_path, calendar_sha256)
    received = aware(connection.clock()).isoformat()
    check = validate_monthly_publication(
        target,
        publication,
        calendar,
        freeze=freeze,
        received_at=received,
        target_sha256=target_sha256,
        calendar_sha256=calendar_sha256,
        test_only=preflight_only or test_only_receipt,
        candidate_timing=candidate_timing,
    )
    # Validate membership using the exact frozen metadata, not today's generic S6 universe.
    quant_root = Path(__file__).resolve().parents[4]
    meta_refs = [
        (p, h)
        for p, h in freeze["execution_contract"]["source_hashes"].items()
        if p.replace("\\", "/").endswith("/etf_meta.csv")
    ]
    meta_path, meta_hash = meta_refs[0]
    meta_path = quant_root / Path(meta_path)
    meta_raw = meta_path.read_bytes()
    if hashlib.sha256(meta_raw).hexdigest() != meta_hash:
        raise ValueError("frozen metadata bytes changed")
    meta = pd.read_csv(io.BytesIO(meta_raw), dtype={"ticker": str})
    if not set(target["weights"]) <= set(meta.ticker) | {"CASH"}:
        raise ValueError("target outside frozen metadata universe")
    inverse = set(meta.loc[meta.is_inverse.eq(1), "ticker"])
    if sum(target["weights"].get(t, 0) for t in inverse) > S6DefensiveConfig().bounds.inverse_cap + 1e-9:
        raise ValueError("frozen inverse cap exceeded")
    if preflight_only:
        return {
            **check, "classification": "TEST_ONLY", "status": "PREFLIGHT_PASSED_NOT_RECEIVED",
            "active": False, "actual_publication": False, "actual_receipt": False,
            "journal_written": False, "owner_authenticity_verified": False,
            "execution_date": target["execution_date"], "candidate_timing": candidate_timing,
            "activation_blockers": ["actual_producer_publication_required", "operating_start_not_approved"]
            + (["late_input_execution_policy_not_approved"] if candidate_timing is not None else []),
        }
    initial = publication.get("timing_contract_id") == INITIAL_CONTRACT
    visibility = None
    if initial:
        if not test_only_receipt:
            from .quant25_forward_connection import _now
            if connection.clock is not _now:
                raise ValueError("actual receiver forbids injected clocks")
            if not backup_evidence:
                raise ValueError("verified pre-write safety backup required")
            _read(backup_evidence["path"], backup_evidence["sha256"])
        if visibility_path is None:
            raise ValueError("durable publication visibility evidence required")
        _, visibility = _read(visibility_path, visibility_sha256)
        folder = Path(target_path).resolve().parent
        if any(Path(p).resolve().parent != folder for p in (publication_path, calendar_path, visibility_path)):
            raise ValueError("one sealed publication bundle required")
        ready, ready_sha = verify_bundle_files(folder)
        if (visibility.get("contract_id") != INITIAL_CONTRACT or visibility.get("ready_sha256") != ready_sha
                or visibility.get("target_sha256") != target_sha256
                or visibility.get("publication_sha256") != publication_sha256
                or visibility.get("classification") != publication["classification"]
                or ready["classification"] != publication["classification"]
                or not aware(publication["published_at"]) <= aware(visibility["confirmed_visible_at"]) <= aware(received)):
            raise ValueError("publication completion lineage/time mismatch")
        contract = read_contract(publication["initial_contract_path"], publication["initial_contract_sha256"])
        if (contract["decision_date"] != target["decision_date"]
                or contract["prices_sha256"] != publication["generation_input_sha256"]["prices"]
                or contract["calendar_sha256"] != calendar_sha256):
            raise ValueError("initial input contract scope mismatch")
        if not test_only_receipt and (Path(contract["observation_root"]).resolve() != connection.root
                or folder.parent != Path(contract["publication_root"]).resolve()):
            raise ValueError("actual publication/receiver differs from approved roots")
    key = f"receipt:etf_intent:{target_sha256}"
    binding_key = f"monthly-etf:{freeze['freeze_id']}:{check['decision_date']}"
    binding = {
        "publication": publication,
        "publication_sha256": publication_sha256,
        "calendar_sha256": calendar_sha256,
        "receipt_id": key,
        "validation": "CONTRACT_AND_HASH_ONLY_OWNER_AUTHENTICITY_REQUIRED",
    }
    if initial:
        binding.update(visibility=visibility, visibility_sha256=visibility_sha256,
                       timing_contract_id=INITIAL_CONTRACT)
    with connection._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        for row in con.execute("SELECT body FROM journal WHERE kind='monthly_etf_publication'"):
            saved = json.loads(row["body"])
            if saved["publication"]["publication_id"] == publication["publication_id"] and saved != binding:
                raise ValueError("immutable publication ID conflict")
        previous = con.execute("SELECT body FROM journal WHERE key=?", (binding_key,)).fetchone()
        prior_receipt = con.execute("SELECT body,raw FROM journal WHERE key=?", (key,)).fetchone()
        if prior_receipt and not previous:
            raise ValueError("unbound older receipt cannot be retroactively certified")
        connection._put(con, binding_key, "monthly_etf_publication", binding, publication_raw)
        if prior_receipt:
            record = json.loads(prior_receipt["body"])
            if prior_receipt["raw"] != raw:
                raise ValueError("receipt bytes mismatch")
            if aware(record.get("first_observed_at") or record["arrived_at"]) > aware(received):
                raise ValueError("receiver clock moved backward")
            if not initial:
                return record
        elif previous:
            raise ValueError("publication binding lacks its receipt")
        else:
            record = {
            "receipt_id": key,
            "source": "etf_intent",
            "sha256": target_sha256,
            "source_path": str(Path(target_path).resolve()),
            "arrived_at": received,
            "available_at": received,
            "provider_available_at": check["published_at"],
            "availability_basis": "FIRST_OBSERVED_LOCAL_BYTES_WITH_OWNER_PUBLICATION",
            "historical_receipt_inferred": False,
            "counts_as_live_sample": False,
            "publication_binding_sha256": canonical_sha256(binding),
            }
            if initial:
                record.update(completion_required=True, first_observed_at=received, arrived_at=None, available_at=None,
                              provider_available_at=visibility["confirmed_visible_at"],
                              availability_basis="DURABLE_VISIBILITY_AND_POST_RECEIPT_COMMIT_CONFIRMATION",
                              classification="TEST_ONLY" if test_only_receipt else "ACTUAL_PRODUCER_PUBLICATION",
                              timing_contract_id=INITIAL_CONTRACT, backup_evidence=backup_evidence,
                              actual_receipt=not test_only_receipt, portfolio_execution_date=None)
            connection._put(con, key, "receipt", record, raw)
    if initial:
        if after_primary_commit is not None:
            after_primary_commit()
        return complete_receipt(connection, record)
    return record
