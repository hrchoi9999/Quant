"""Read-only daily DB views to the existing nine-input selector contract.

No collection or feature recalculation. External calendar/QM/monthly ETF/rules
are explicit hash-pinned inputs; no fabricated sessions or historical receipts.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd

from src.quant2.evaluation.quant25_selection_candidate import corrected_fund_snapshot

from .quant25_forward_connection import ForwardConnection
from .quant25_incremental_selection import aware
from .quant25_monthly_evidence import verify_received_monthly


def capture_manual_candidate_inputs(connection, manifest_path, *, expected_sha256, monthly_receipt_id):
    """Capture a prepared synthetic manual batch; reuse its bound monthly receipt."""
    from .quant25_manual_collection_candidate import ManualCollectionCandidate, read_candidate_export, stamp

    if type(connection) is not ManualCollectionCandidate:
        raise ValueError("isolated manual candidate connection required")
    path = Path(manifest_path).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("manual export manifest hash mismatch")
    body, files = read_candidate_export(path, checked_at=connection.clock())
    with connection._connect() as con:
        monthly = connection._record(con, monthly_receipt_id)
        bindings = [json.loads(r[0])["receipt_id"] for r in con.execute(
            "SELECT body FROM journal WHERE kind='candidate_monthly_received'")]
        if (monthly_receipt_id not in bindings or not monthly
                or monthly["sha256"] != hashlib.sha256(files["etf_intent"]).hexdigest()):
            raise ValueError("bound synthetic monthly receipt required")
    receipts = {"etf_intent": monthly_receipt_id}
    for name, item in body["inputs"].items():
        if name != "etf_intent":
            receipts[name] = connection.capture(name, path.parent / item["path"],
                                                expected_sha256=item["sha256"])["receipt_id"]
    result = stamp({"batch_id": "manual-batch:" + expected_sha256, "timing": body["timing"],
                    "source_evidence": body["inputs"], "receipts": receipts,
                    "manifest_sha256": expected_sha256, "captured_at": aware(connection.clock()).isoformat()})
    with connection._connect() as con:
        connection._put(con, result["batch_id"], "manual_batch", result)
    return result


def _read_db(path, query, params=()):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        return pd.read_sql_query(query, con, params=params)


def capture_daily_inputs(connection: ForwardConnection, config, *, day, output: Path, manual_timing=None):
    from .quant25_input_timing import consumer_opted_in, reject_preparation
    reject_preparation(config)
    reject_preparation(manual_timing)
    output = output.resolve()
    if not output.is_relative_to(connection.root) or (output.exists() and not consumer_opted_in(manual_timing)):
        raise ValueError("new private input directory required")
    if consumer_opted_in(manual_timing):
        return _capture_consumer_inputs(connection, config, day=day, output=output, contract=manual_timing)
    now = aware(connection.clock()).tz_convert("Asia/Seoul")
    from .quant25_input_timing import collection_context, opted_in, validity
    use_manual = opted_in(manual_timing)
    if use_manual:
        collection = collection_context(manual_timing, signal_day=day, checked_at=now, root=connection.root)
    elif now.strftime("%Y-%m-%d") != day or now < aware(day + "T15:30:00+09:00"):
        raise ValueError("only actual same-day completed closing inputs may be captured for decisions")
    if config.get("completed_data_asof") != (collection["completed_data_asof"] if use_manual else day):
        raise ValueError("upstream completion asof mismatch")
    external = {}
    blobs = {}
    verified_monthly = None
    for name in ("qm", "etf_intent", "rules", "calendar", "universe", "sector"):
        source = config[name]
        path = Path(source["path"])
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("external source hash mismatch")
        external[name] = json.loads(raw) if name != "universe" else pd.read_csv(path, dtype={"ticker": str})
        if name == "etf_intent" and external[name].get("evidence_state") == "ACTUAL_PRODUCER_PUBLICATION":
            verified_monthly = verify_received_monthly(
                external[name], source.get("monthly_evidence"), signal_day=day, checked_at=now,
                observation_root=connection.root, availability_cutoff=now if use_manual else None,
            )
        elif use_manual and name == "etf_intent":
            raise ValueError("opt-in requires original actual monthly publication evidence")
        elif source.get("evidence_classification") != "CAPTURED_OR_OFFICIAL":
            raise ValueError("historical reconstructed dependencies are not forward inputs")
        blobs[name] = raw
    calendar = external["calendar"]
    if use_manual:
        validity(manual_timing, calendar, signal_day=day, cutoff=now, root=connection.root)
    if calendar != sorted(set(calendar)) or day not in calendar:
        raise ValueError("explicit confirmed calendar required")
    index = calendar.index(day)
    if index == 0 or index + 1 >= len(calendar):
        raise ValueError("calendar lacks observed and next confirmed session")
    if external["qm"].get("asof_date") != calendar[index - 1]:
        raise ValueError("QM must describe exact previous session")
    if config["universe"].get("data_asof") != day:
        raise ValueError("current universe asof required")
    stocks = external["universe"].ticker.astype(str).tolist()
    if not stocks or len(stocks) != len(set(stocks)):
        raise ValueError("nonempty unique stock universe required")
    features = _read_db(config["features_db"],
                        "SELECT * FROM s3_price_features_daily WHERE date=? ORDER BY ticker", (day,))
    features["ticker"] = features.ticker.astype(str)
    features = features.loc[features.ticker.isin(stocks)]
    if set(features.ticker) != set(stocks):
        raise ValueError("missing daily features for declared universe")
    fund = _read_db(config["features_db"], "SELECT * FROM s3_fund_features_monthly WHERE date<=? ORDER BY ticker,date", (day,))
    fund["ticker"] = fund.ticker.astype(str)
    funds = corrected_fund_snapshot(fund, day, stocks)
    start = calendar[max(0, index - 65)]
    prices = _read_db(config["price_db"], "SELECT ticker,date,open,close,volume FROM prices_daily WHERE date BETWEEN ? AND ? ORDER BY date,ticker", (start, day))
    prices["ticker"] = prices.ticker.astype(str)
    if prices.empty or prices.date.max() != day:
        raise ValueError("daily price input is stale")
    # No operational writes. Stage immutable CSVs only after all read gates pass.
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, frame in {"features": features, "fundamentals": funds, "prices": prices}.items():
        files[name] = output / (name + ".csv")
        frame.to_csv(files[name], index=False)
    for name in ("qm", "etf_intent", "rules", "calendar", "sector"):
        files[name] = output / (name + ".json")
        files[name].write_bytes(blobs[name])
    files["universe"] = output / "universe.json"
    files["universe"].write_text(json.dumps(stocks), encoding="utf-8")
    receipts = {name: verified_monthly if name == "etf_intent" and verified_monthly is not None
                else connection.capture(name, path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                for name, path in files.items()}
    provenance = {"schema": "q25_daily_input_capture_v1", "day": day, "observed_at": now.isoformat(),
                  "source_config": config, "receipts": receipts, "operating_db_writes": 0,
                  "fund_transform": "corrected_fund_snapshot", "historical_arrival_inferred": False}
    if use_manual:
        provenance.update(manual_timing=manual_timing, collection_context=collection)
    (output / "capture_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    from src.quant2.operations.q25_input_evidence import export_daily_scope

    export_daily_scope(day=day, calendar=calendar, stocks=stocks, prices=prices, config=config)
    return receipts


def _capture_consumer_inputs(connection, config, *, day, output, contract):
    """Use existing verified producer bytes; no extraction and no pre-existing nine-receipt gate."""
    from .quant25_input_timing import consumer_context, pinned, validity
    from .quant25_paper_live import canonical_sha256

    contract = json.loads(json.dumps(contract))
    now = aware(connection.clock()).isoformat()
    context = consumer_context(contract, signal_day=day, checked_at=now, root=connection.root)
    if (config.get("completed_data_asof") != context["completed_data_asof"]
            or config.get("input_manifest") != contract["input_manifest"]):
        raise ValueError("consumer capture config/run/manifest mismatch")
    manifest = pinned(contract["input_manifest"])
    parent = Path(contract["input_manifest"]["path"]).resolve().parent
    blobs = {name: (parent / entry["path"]).read_bytes() for name, entry in manifest["inputs"].items()}
    if any(hashlib.sha256(blobs[n]).hexdigest() != e["sha256"] for n, e in manifest["inputs"].items()):
        raise ValueError("consumer input changed before capture")
    validity(contract, json.loads(blobs["calendar"]), signal_day=day, cutoff=now, root=connection.root)
    monthly = verify_received_monthly(json.loads(blobs["etf_intent"]), contract.get("monthly_evidence"),
                                      signal_day=day, checked_at=now, observation_root=connection.root,
                                      availability_cutoff=now)
    if monthly["sha256"] != manifest["inputs"]["etf_intent"]["sha256"]:
        raise ValueError("consumer original monthly receipt hash mismatch")
    scope = {k: v for k, v in contract.items()
             if k not in {"capture_provenance", "event_coverage", "event_materiality_review"}}
    observation_key = "consumer-capture:" + canonical_sha256(scope)
    with connection._connect() as con:
        row = con.execute("SELECT body FROM journal WHERE key=? AND kind='consumer_capture'",
                          (observation_key,)).fetchone()
    prior = json.loads(row[0]) if row else None
    if output.exists():
        if prior is None or any(not (output / manifest["inputs"][n]["path"]).is_file()
                               or (output / manifest["inputs"][n]["path"]).read_bytes() != raw
                               for n, raw in blobs.items()):
            raise ValueError("consumer capture directory conflicts with sealed observation")
        proof_path = output / "capture_provenance.json"
        if proof_path.exists() and json.loads(proof_path.read_bytes()) != prior:
            raise ValueError("consumer capture proof conflicts with journal")
        if not proof_path.exists():
            proof_path.write_text(json.dumps(prior, indent=2), encoding="utf-8")
        return prior["receipts"]
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, raw in blobs.items():
        files[name] = output / manifest["inputs"][name]["path"]
        files[name].parent.mkdir(parents=True, exist_ok=True)
        files[name].write_bytes(raw)
    if prior is not None:
        (output / "capture_provenance.json").write_text(json.dumps(prior, indent=2), encoding="utf-8")
        return prior["receipts"]
    receipts = {name: monthly if name == "etf_intent" else connection.capture(
        name, files[name], expected_sha256=manifest["inputs"][name]["sha256"]) for name in blobs}
    completed = aware(connection.clock()).isoformat()
    provenance = {"schema": "q25_daily_input_capture_v1", "day": day, "observed_at": now,
                  "completed_at": completed, "source_config": config,
                  "receipts": receipts, "manual_timing": contract, "collection_context": context,
                  "operating_db_writes": 0, "historical_arrival_inferred": False,
                  "observation_root": str(connection.root.resolve()),
                  "batch_id": canonical_sha256({"input_manifest": contract["input_manifest"],
                      "harness_state": contract["harness_state"], "receipts": receipts})}
    # The first receipt is immutable. This records a real read/hash check in
    # this batch, even when byte-identical inputs reuse an older receipt.
    provenance.update(observation_journal_key=observation_key, input_observations={
        n: {"receipt_id": receipts[n]["receipt_id"], "sha256": manifest["inputs"][n]["sha256"],
            "producer_path": str((parent / manifest["inputs"][n]["path"]).resolve()),
            "read_started_at": now, "verified_at": completed}
        for n in blobs if n != "etf_intent"})
    with connection._connect() as con:
        connection._put(con, observation_key, "consumer_capture", provenance)
    (output / "capture_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return receipts
