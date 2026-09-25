"""Immutable preparation exports, never decision receipts or historical Live."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from ..evaluation.quant25_selection_candidate import corrected_fund_snapshot
from .quant25_daily_input_capture import _read_db
from .quant25_incremental_selection import SOURCES
from .quant25_monthly_evidence import verify_received_monthly

SCHEMA = "q25_input_preparation_v1"
EXTERNAL = ("qm", "sector", "calendar", "rules", "etf_intent")


def export_manual_candidate_inputs(*, sources, timing, output, exported_at):
    """Export nine already prepared synthetic files. No DB reads or collection.

    This entry point is deliberately separate from ordinary preparation export.
    Its manifest can only feed the isolated manual candidate capture function.
    """
    from .quant25_incremental_selection import aware, check_evidence
    from .quant25_manual_collection_candidate import stamp, validate_collection, validate_monthly

    output = Path(output).resolve()
    if (not output.is_relative_to(Path(__file__).resolve().parents[3] / "reports")
            or not output.name.startswith("SYNTHETIC_TEST_ONLY_MANUAL") or output.exists()):
        raise ValueError("new isolated manual candidate export directory required")
    if set(sources) != SOURCES:
        raise ValueError("exact nine synthetic source files required")
    check_evidence(sources, aware(timing["collection_completed_at"]), historical=False)
    blobs = {name: _source(item).read_bytes() for name, item in sources.items()}
    calendar = json.loads(blobs["calendar"])
    validate_collection(timing, calendar, checked_at=exported_at)
    day = timing["signal_date"]
    index = calendar.index(day)
    if index == 0:
        raise ValueError("previous QM session required")
    # Content validation is shared with the existing exporter; the synthetic
    # ETF branch alone has its own availability-cutoff contract.
    import io
    for name, raw in blobs.items():
        value = (pd.read_csv(io.BytesIO(raw), dtype={"ticker": str})
                 if name in {"features", "fundamentals", "prices"} else json.loads(raw))
        if name == "etf_intent":
            validate_monthly(value, calendar, signal_day=day, availability_cutoff=exported_at)
        else:
            errors = _content_errors(name, value, day, calendar[index - 1])
            if errors:
                raise ValueError(f"{name}: {errors}")
    output.mkdir(parents=True, exist_ok=False)
    entries = {}
    for name, raw in blobs.items():
        file = name + (".csv" if name in {"features", "fundamentals", "prices"} else ".json")
        (output / file).write_bytes(raw)
        entries[name] = {**sources[name], "path": file}
    body = stamp({"schema": "q25_manual_candidate_export_v1", "timing": timing,
                  "exported_at": exported_at, "inputs": entries, "collection_executed": False,
                  "operating_db_writes": 0, "decision_ready": False})
    path = output / "manifest.json"
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return path


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _source(item):
    path = Path(item["path"]).resolve()
    if _sha(path) != item["sha256"]:
        raise ValueError(f"source hash mismatch: {path}")
    return path


def _storage(paths):
    return {str(p): [p.stat().st_size, p.stat().st_mtime_ns]
            for path in paths for p in (Path(path), Path(str(path) + "-wal"), Path(str(path) + "-journal"))
            if p.exists()}


def _entry(owner, day, observed, **fields):
    return dict(owner=owner, data_asof=day, observed_at=observed, extracted_at=observed,
                provider_available_at=None, arrived_at=None, available_at=None,
                historical_live_evidence=False, forward_capture_eligible=False,
                **fields)


def _owner_errors(name, source, day, qm_day):
    status = source.get("status")
    if source.get("decision_reference_date") != day:
        return ["owner has not confirmed this target input"]
    if status == "COMPLETED":
        return []
    if name == "calendar" and status == "COMPLETED_FOR_EXPLICIT_CONFIRMED_SCOPE":
        coverage = source.get("confirmed_coverage", {})
        if (coverage.get("status") == status
                and coverage.get("verified_start", "9999") <= qm_day
                and coverage.get("verified_end", "") > day
                and coverage.get("lookback_end") == qm_day
                and coverage.get("lookback_sessions", 0) >= 64):
            return []
        return ["calendar explicit confirmed coverage missing or insufficient"]
    return ["owner has not confirmed this target input"]


def _content_errors(name, value, day, qm_day, *, source=None, checked_at=None, availability_cutoff=None):
    errors = []
    if name in {"features", "fundamentals", "prices"}:
        if "ticker" not in value or value.empty:
            return ["empty frame or missing ticker"]
        keys = ["ticker", "date"] if name == "prices" else ["ticker"]
        if value.duplicated(keys).any():
            errors.append("duplicate keys")
        column = "fund_date" if name == "fundamentals" else "date"
        dates = pd.to_datetime(value[column], errors="coerce")
        if dates.gt(pd.Timestamp(day)).any():
            errors.append("future rows")
        if name in {"features", "prices"} and (dates.isna().any() or dates.max() != pd.Timestamp(day)):
            errors.append("missing target data date")
        if name == "features" and not dates.eq(pd.Timestamp(day)).all():
            errors.append("features must be exact target date")
        if name == "fundamentals":
            for field in ("available_from", "prior_date", "prior_available_from"):
                if pd.to_datetime(value[field], errors="coerce").gt(pd.Timestamp(day)).any():
                    errors.append(f"future {field}")
    elif name == "universe":
        if not isinstance(value, list) or not value or len(value) != len(set(value)) or "CASH" in value:
            errors.append("invalid universe")
    elif name == "qm":
        if not isinstance(value, dict) or value.get("asof_date") != qm_day or qm_day >= day:
            errors.append("wrong QM observation date")
    elif name == "sector":
        if not isinstance(value, list) or any(not isinstance(r, dict) or "ticker" not in r for r in value):
            errors.append("invalid sector shape")
    elif name == "calendar":
        if not isinstance(value, list) or value != sorted(set(value)):
            errors.append("invalid calendar shape")
        elif day not in value or qm_day not in value or max(value, default="") <= day:
            errors.append("calendar missing observation/decision/next session")
    elif name == "rules":
        if not isinstance(value, list):
            errors.append("invalid rules shape")
    elif name == "etf_intent":
        required = {"model_code", "decision_date", "published_at", "execution_date", "weights", "evidence_state"}
        if not isinstance(value, dict) or not required <= set(value):
            return ["ETF publication fields missing"]
        try:
            actual_monthly = value.get("evidence_state") == "ACTUAL_PRODUCER_PUBLICATION"
            if actual_monthly:
                verify_received_monthly(value, (source or {}).get("monthly_evidence"),
                                        signal_day=day, checked_at=checked_at or _now(),
                                        availability_cutoff=availability_cutoff)
            decision = pd.Timestamp(value["decision_date"])
            execution = pd.Timestamp(value["execution_date"])
            published = pd.Timestamp(value["published_at"])
            weights = pd.Series(value["weights"], dtype=float)
            if (decision > pd.Timestamp(day) or execution <= decision or published.tzinfo is None
                    or (published > pd.Timestamp(availability_cutoff) if availability_cutoff is not None else
                        published.date() > date.fromisoformat(day))
                    or (availability_cutoff is not None and not actual_monthly)
                    or (not actual_monthly and value["evidence_state"] != "CAPTURED_OR_OFFICIAL")
                    or weights.empty or not weights.ge(0).all()
                    or not weights.map(lambda v: float("-inf") < v < float("inf")).all()
                    or abs(weights.sum() - 1) > 1e-6):
                errors.append("ETF publication/weights not eligible")
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
            errors.append(f"invalid ETF publication values/evidence: {exc}")
    return errors


def validate_input_export(manifest_path, *, expected_data_asof, require_all_ready=True,
                          expected_run_id=None, expected_harness_state=None,
                          consumer_timing=None, checked_at=None):
    """Validate exact nine files/statuses/hashes/dates; raise ValueError fail-closed."""
    path = Path(manifest_path).resolve()
    manifest = _json(path)
    consumer_cutoff = None
    if consumer_timing is not None:
        from .quant25_input_timing import consumer_binding, pinned, reject_preparation
        reject_preparation(manifest)
        if "manual_timing" in manifest or not require_all_ready or checked_at is None:
            raise ValueError("consumer validation requires complete inputs and explicit check time")
        consumer_binding(consumer_timing, signal_day=expected_data_asof, checked_at=checked_at)
        reference = consumer_timing.get("input_manifest", {})
        if Path(reference.get("path", "")).resolve() != path or pinned(reference) != manifest:
            raise ValueError("consumer manifest binding mismatch")
        consumer_cutoff = checked_at
    from .quant25_input_timing import collection_context, opted_in, preparation_context, preparation_producers
    preparation = manifest.get("preparation_contract")
    context = None
    preparation_review = False
    if "preparation_contract" in manifest:
        if "manual_timing" in manifest:
            raise ValueError("preparation and execution timing contracts cannot be combined")
        context = preparation_context(preparation, data_asof=expected_data_asof,
                                      checked_at=manifest["observed_at"], root=path.parent,
                                      expected_run_id=expected_run_id,
                                      expected_harness_state=expected_harness_state)
        from .quant25_input_timing import preparation_review_enabled
        preparation_review = preparation_review_enabled(preparation)
        if preparation_review:
            from .quant25_incremental_selection import aware
            consumer_cutoff = checked_at or preparation.get("reviewed_at")
            if not (aware(manifest["observed_at"]) <= aware(manifest["generated_at"])
                    <= aware(preparation.get("reviewed_at")) <= aware(consumer_cutoff)
                    <= pd.Timestamp.now(tz="UTC")):
                raise ValueError("preparation actual review chronology mismatch")
            if not preparation.get("signal_date") or preparation["signal_date"] > expected_data_asof:
                raise ValueError("preparation review reference signal exceeds fixed data date")
    use_manual = opted_in(manifest.get("manual_timing"))
    if use_manual:
        collection_context(manifest["manual_timing"], signal_day=expected_data_asof,
                           checked_at=manifest["observed_at"], root=path.parent)
    errors = []
    if manifest.get("schema") != SCHEMA or manifest.get("data_asof") != expected_data_asof:
        errors.append("schema or target data_asof mismatch")
    entries = manifest.get("inputs", {})
    if set(entries) != SOURCES:
        raise ValueError("exact nine input names required")
    if manifest.get("path_base") != "manifest_directory":
        errors.append("unsupported path base")
    frames = {}
    for name, entry in entries.items():
        status = entry.get("status")
        if status not in {"produced", "reused", "blocked"} or type(entry.get("ready")) is not bool:
            errors.append(f"{name}: invalid status/ready")
        if entry.get("ready") != (status in {"produced", "reused"}):
            errors.append(f"{name}: status/ready mismatch")
        if entry.get("ready") and name in EXTERNAL:
            errors.extend(f"{name}: {item}" for item in _owner_errors(
                name, entry.get("source_provenance", {}), expected_data_asof,
                manifest["required_qm_observation_date"]))
        if status == "blocked" and not entry.get("blocked_reasons"):
            errors.append(f"{name}: missing blocked reason")
        for field in ("observed_at", "extracted_at"):
            stamp = pd.Timestamp(entry.get(field)) if entry.get(field) else pd.NaT
            if pd.isna(stamp) or stamp.tzinfo is None:
                errors.append(f"{name}: actual {field} required")
        file = entry.get("path")
        if file is None:
            if entry.get("ready") or entry.get("sha256") is not None:
                errors.append(f"{name}: missing required file")
            continue
        target = (path.parent / file).resolve()
        if Path(file).is_absolute() or not target.is_relative_to(path.parent) or not target.is_file():
            errors.append(f"{name}: invalid/missing file")
            continue
        if _sha(target) != entry.get("sha256"):
            errors.append(f"{name}: hash mismatch")
            continue
        value = (pd.read_csv(target, dtype={"ticker": str}) if name in {"features", "fundamentals", "prices"}
                 else _json(target))
        count = len(value) if not isinstance(value, dict) else 1
        if count != entry.get("row_count"):
            errors.append(f"{name}: row count mismatch")
        found = _content_errors(name, value, expected_data_asof, manifest["required_qm_observation_date"],
                                source=entry.get("source_provenance"),
                                checked_at=consumer_cutoff or entry.get("observed_at"),
                                availability_cutoff=(consumer_cutoff if consumer_cutoff is not None else
                                                     manifest["observed_at"] if use_manual else None))
        if entry.get("ready") and found:
            errors.extend(f"{name}: {item}" for item in found)
        frames[name] = value
    stocks = frames.get("universe")
    if stocks is not None:
        if len(stocks) != manifest.get("expected_stock_count"):
            errors.append("wrong stock cohort size")
        for name in ("features", "fundamentals"):
            if name in frames and set(frames[name].ticker) != set(stocks):
                errors.append(f"{name}: stock cohort mismatch")
    if "prices" in frames:
        allowed = set(manifest.get("price_tickers", []))
        if not set(frames["prices"].ticker) <= allowed:
            errors.append("prices outside declared scope")
    all_ready = all(entry.get("ready") is True for entry in entries.values())
    materiality = None
    materiality_error = None
    if consumer_timing is not None:
        from .quant25_event_materiality import enabled
        if enabled(consumer_timing):
            from .quant25_input_timing import verify_prepared_materiality
            materiality = verify_prepared_materiality(consumer_timing, manifest, manifest_path=path,
                                                       cutoff=consumer_cutoff)
    if preparation_review:
        from .quant25_input_timing import verify_prepared_materiality
        try:
            materiality = verify_prepared_materiality(preparation, manifest, manifest_path=path,
                                                       cutoff=consumer_cutoff)
        except (ValueError, KeyError, OSError, TypeError) as exc:
            # A diagnostic partial result is not consumption approval. Strict
            # callers still fail below; no source status or evidence is repaired.
            materiality_error = str(exc)
    if type(manifest.get("all_inputs_ready")) is not bool or manifest["all_inputs_ready"] != all_ready:
        errors.append("all_inputs_ready mismatch")
    if manifest.get("decision_ready") is not False or manifest.get("historical_live_evidence") is not False:
        errors.append("preparation must not claim decisions or Live")
    if manifest.get("operating_db_writes") != 0 or manifest.get("source_db_storage_unchanged") is not True:
        errors.append("DB read-only preservation evidence missing")
    consumer_eligible = (materiality is not None
                         and all(e["ready"] for n, e in entries.items() if n != "rules"))
    if require_all_ready and not all_ready and not consumer_eligible:
        errors.append("blocked inputs remain")
    if require_all_ready and materiality_error is not None:
        errors.append("preparation consumption review blocked: " + materiality_error)
    if errors:
        raise ValueError("; ".join(errors))
    if context is not None:
        preparation_producers(preparation, manifest, manifest_path=path)
    result = {"status": "pass" if all_ready else "pass_partial", "data_asof": expected_data_asof,
            "all_inputs_ready": all_ready, "ready_count": sum(e["ready"] for e in entries.values()),
            "blocked_inputs": [k for k, e in entries.items() if not e["ready"]],
            "verified_file_count": len(frames)}
    if context is not None:
        result.update(context, preparation_status=("completed" if all_ready else
                      "partial" if result["ready_count"] else "blocked"))
    if materiality is not None:
        result.update(consumer_inputs_eligible=consumer_eligible, event_materiality=materiality,
                      source_readiness_unchanged=True)
    elif preparation_review:
        result.update(consumer_inputs_eligible=False, source_readiness_unchanged=True,
                      event_materiality={"policy": preparation["event_materiality_policy"],
                          "status": "BLOCKED_REVIEW", "error": materiality_error,
                          "coverage": preparation.get("event_coverage"),
                          "review": preparation.get("event_materiality_review"),
                          "restrictions_validated": False})
    if preparation_review:
        result.update(preparation_review_only=True, preparation_reviewed_at=consumer_cutoff,
                      execution_authorized=False)
    return result


def export_inputs(config, *, data_asof, output, manual_timing=None, preparation_contract=None):
    """Prepare local four inputs even when external five remain blocked."""
    day = date.fromisoformat(data_asof)
    observed = _now()
    from .quant25_input_timing import (
        collection_context,
        consumer_opted_in,
        opted_in,
        preparation_context,
        preparation_producers,
        reject_preparation,
    )
    reject_preparation(config)
    if consumer_opted_in(manual_timing):
        raise ValueError("consumer timing consumes pinned producer files; export activation is not supported")
    if preparation_contract is not None:
        if not isinstance(preparation_contract, dict):
            raise ValueError("explicit preparation contract required")
        if manual_timing is not None:
            raise ValueError("preparation and execution timing contracts cannot be combined")
        preparation_context(preparation_contract, data_asof=data_asof, checked_at=observed, root=output,
                            expected_run_id=preparation_contract.get("run_id"),
                            expected_harness_state=preparation_contract.get("harness_state"))
    use_manual = opted_in(manual_timing)
    if use_manual:
        collection = collection_context(manual_timing, signal_day=data_asof, checked_at=observed, root=output)
    if day > pd.Timestamp(observed).tz_convert("Asia/Seoul").date():
        raise ValueError("future data_asof forbidden")
    if config.get("completed_data_asof") != (collection["completed_data_asof"] if use_manual else data_asof):
        raise ValueError("completed data_asof mismatch")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("new output directory required")
    source_universe = _source(config["universe"])
    universe = pd.read_csv(source_universe, dtype={"ticker": str})
    stocks = universe.ticker.tolist()
    if len(stocks) != config["expected_stock_count"] or len(set(stocks)) != len(stocks):
        raise ValueError("exact unique stock cohort required")
    if set(universe["asof"].astype(str)) != {config["universe"]["data_asof"]}:
        raise ValueError("universe source date mismatch")
    core_path = _source(config["core_universe"])
    core = pd.read_csv(core_path, dtype={"ticker": str})
    sector_path = _source(config["sector_scope"])
    sector_value = _json(sector_path)
    sectors = sector_value.get("candidates") if isinstance(sector_value, dict) else sector_value
    tickers = sorted(set(stocks) | set(core.ticker) | {v["ticker"] for v in sectors})
    db_paths = [config["features_db"], config["price_db"]]
    before = _storage(db_paths)
    keys = ",".join("?" for _ in stocks)
    features = _read_db(config["features_db"],
                        f"SELECT * FROM s3_price_features_daily WHERE date=? AND ticker IN ({keys}) ORDER BY ticker",
                        (data_asof, *stocks))
    fund = _read_db(config["features_db"],
                   f"SELECT * FROM s3_fund_features_monthly WHERE date<=? AND ticker IN ({keys}) ORDER BY ticker,date",
                   (data_asof, *stocks))
    funds = corrected_fund_snapshot(fund, data_asof, stocks)
    price_keys = ",".join("?" for _ in tickers)
    sessions = _read_db(config["price_db"],
                        f"SELECT DISTINCT date FROM prices_daily WHERE date<=? AND ticker IN ({price_keys}) ORDER BY date DESC LIMIT 65",
                        (data_asof, *tickers)).date.tolist()
    if not sessions or sessions[0] != data_asof:
        raise ValueError("price target date missing")
    prices = _read_db(config["price_db"],
                      f"SELECT ticker,date,open,close,volume FROM prices_daily WHERE date BETWEEN ? AND ? AND ticker IN ({price_keys}) ORDER BY date,ticker",
                      (sessions[-1], data_asof, *tickers))
    if before != _storage(db_paths):
        raise ValueError("source DB changed during export; retry only after writer review")
    for name, frame in (("features", features), ("fundamentals", funds)):
        if set(frame.ticker) != set(stocks):
            raise ValueError(f"{name}: incomplete cohort")
    qm_day = config["required_qm_observation_date"]
    for name, frame in (("features", features), ("fundamentals", funds), ("prices", prices)):
        errors = _content_errors(name, frame, data_asof, qm_day)
        if errors:
            raise ValueError(f"{name}: {errors}")
    output.mkdir(parents=True, exist_ok=False)
    entries = {}
    for name, value in (("features", features), ("fundamentals", funds), ("prices", prices), ("universe", stocks)):
        path = output / (name + (".json" if name == "universe" else ".csv"))
        if name == "universe":
            path.write_text(json.dumps(value), encoding="utf-8")
        else:
            value.to_csv(path, index=False)
        entries[name] = _entry("Quant OS", data_asof, observed, status="produced", ready=True,
                               path=path.name, sha256=_sha(path), row_count=len(value),
                               source_asof=(config["universe"]["data_asof"] if name == "universe"
                                            else sorted(funds.fund_date.dropna().astype(str).unique()) if name == "fundamentals"
                                            else data_asof),
                               blocked_reasons=[], evidence_classification="DB_READONLY_PREPARATION")
    for name in EXTERNAL:
        source = config.get("external", {}).get(name, {})
        reasons = list(source.get("blocked_reasons", []))
        path = None
        sha = None
        count = 0
        if source.get("path"):
            try:
                original = _source(source)
                value = _json(original)
                reasons.extend(_content_errors(name, value, data_asof, qm_day,
                                                source=source, checked_at=observed,
                                                availability_cutoff=observed if use_manual else None))
                path = output / (name + ".json")
                path.write_bytes(original.read_bytes())
                sha = _sha(path)
                count = len(value) if not isinstance(value, dict) else 1
            except (OSError, ValueError, TypeError, KeyError) as exc:
                reasons.append(f"external input unavailable or invalid: {exc}")
                path = None
        else:
            reasons.append(source.get("reason", "owner input not available"))
        reasons.extend(_owner_errors(name, source, data_asof, qm_day))
        ready = not reasons
        entries[name] = _entry(source.get("owner", "QuantMarket" if name != "etf_intent" else "Quant OS"),
                               source.get("data_asof"), observed, status="reused" if ready else "blocked",
                               ready=ready, path=path.name if path else None, sha256=sha, row_count=count,
                               source_asof=source.get("data_asof"), source_provenance=source,
                               blocked_reasons=sorted(set(reasons)),
                               evidence_classification=source.get("evidence_classification", "UNKNOWN"))
    manifest = {"schema": SCHEMA, "data_asof": data_asof, "all_inputs_ready": all(e["ready"] for e in entries.values()),
                "path_base": "manifest_directory", "generated_at": _now(), "observed_at": observed,
                "required_qm_observation_date": qm_day, "expected_stock_count": len(stocks),
                "price_tickers": tickers, "price_window": {"start": sessions[-1], "end": data_asof,
                    "observed_sessions": len(sessions), "basis": "existing_scoped_price_dates_not_confirmed_calendar",
                    "purpose": "64_prior_observation_sessions_plus_decision_day"},
                "inputs": entries, "source_config": config, "source_db_storage": before,
                "source_db_storage_unchanged": before == _storage(db_paths), "db_access": "mode=ro; query_only=ON",
                "decision_ready": False, "historical_live_evidence": False, "operating_db_writes": 0,
                "fund_transform": "corrected_fund_snapshot; publication PIT not newly certified"}
    path = output / "manifest.json"
    if use_manual:
        manifest["manual_timing"] = manual_timing
        manifest["collection_context"] = collection
    if preparation_contract is not None:
        manifest["preparation_contract"] = preparation_contract
        # Do not publish a ready preparation manifest before producer verification.
        preparation_producers(preparation_contract, manifest, manifest_path=path)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    result = validate_input_export(
        path, expected_data_asof=data_asof, require_all_ready=False,
        expected_run_id=preparation_contract.get("run_id") if preparation_contract else None,
        expected_harness_state=preparation_contract.get("harness_state") if preparation_contract else None)
    (output / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {"manifest": str(path), **result}
