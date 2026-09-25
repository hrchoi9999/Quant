"""Evidence gates for the explicitly opted-in existing input/forward paths.

No scheduler or new execution framework. Missing real command/cycle/coverage
evidence is a blocker. Synthetic evidence remains synthetic in isolated tests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from .quant25_incremental_selection import aware, check_evidence
from .quant25_paper_live import canonical_sha256

CONTRACT = "Q25_MANUAL_INPUT_TIMING_OPT_IN_V1"
CONSUMER_CONTRACT = "Q25_CONSUMER_INPUT_TIMING_OPT_IN_V1"
PREPARATION_CONTRACT = "Q25_INPUT_PREPARATION_V1"
PREPARATION_REVIEW = "Q25_PREPARATION_CONSUMPTION_REVIEW_V1"
TEST_ONLY = "SYNTHETIC_TEST_ONLY"


def preparation_review_enabled(contract):
    """Explicit preparation review only; never an execution timing opt-in."""
    if not isinstance(contract, dict) or "consumption_review" not in contract:
        return False
    from .quant25_event_materiality import SIMPLE_POLICY

    if (contract.get("contract_id") != PREPARATION_CONTRACT
            or contract.get("consumption_review") != PREPARATION_REVIEW
            or contract.get("event_materiality_policy") != SIMPLE_POLICY
            or contract.get("enabled") is not False):
        raise ValueError("explicit preparation-only simple consumption review required")
    return True


def reject_preparation(value):
    """Preparation evidence never grants capture, selection or execution rights."""
    if isinstance(value, dict) and (
        value.get("contract_id") == PREPARATION_CONTRACT or "preparation_contract" in value
    ):
        raise ValueError("Q25_INPUT_PREPARATION_V1 is preparation only; execution input forbidden")


def opted_in(value):
    reject_preparation(value)
    if value is None or (isinstance(value, dict) and value.get("enabled") is False):
        return False
    if (not isinstance(value, dict) or value.get("enabled") is not True
            or value.get("contract_id") not in {CONTRACT, CONSUMER_CONTRACT}):
        raise ValueError("explicit manual input timing opt-in required")
    return True


def consumer_opted_in(value):
    return opted_in(value) and value["contract_id"] == CONSUMER_CONTRACT


def consumer_binding(contract, *, signal_day, checked_at, root=None):
    """Validate current collection identity without requiring receipts or model stages."""
    if not consumer_opted_in(contract) or contract.get("signal_date") != signal_day:
        raise ValueError("explicit consumer signal contract required")
    data_day = contract.get("data_asof", "")
    if data_day < signal_day:
        raise ValueError("consumer source collection predates signal")
    if "collection_basis" in contract:
        from .quant25_supplemental_collection import BASIS, completed_context

        if contract["collection_basis"] != BASIS:
            raise ValueError("unsupported consumer collection basis")
        mode = _mode(contract, root)
        context = completed_context(contract, data_asof=data_day, checked_at=checked_at,
                                    expected_run_id=contract.get("run_id"),
                                    expected_state=contract.get("harness_state"), mode=mode,
                                    root=root or contract.get("test_root"))
        collectible = aware(contract.get("collectible_at"))
        if (data_day != signal_day or collectible.tz_convert("Asia/Seoul").date() <= pd.Timestamp(signal_day).date()
                or not aware(signal_day + "T15:30:00+09:00") <= aware(context["user_command_at"])
                or collectible > aware(context["collection_started_at"])):
            raise ValueError("supplemental consumer exact signal/D-1 mismatch")
        return {**context, "contract_id": CONSUMER_CONTRACT, "signal_date": signal_day,
                "completed_data_asof": data_day, "collectible_at": collectible.isoformat(),
                "contract_sha256": canonical_sha256(contract)}
    reference = contract.get("harness_state", {})
    path = Path(reference.get("path", "")).resolve()
    if path.name != "prompt_cycle_state.json" or path.parent.name != contract.get("run_id"):
        raise ValueError("current consumer Harness state path required")
    mode = _mode(contract, root)
    if mode == "ACTUAL" and path != (Path(__file__).resolve().parents[4] / "reports" /
                                    "prompt_handoff_runs" / contract["run_id"] / path.name):
        raise ValueError("actual consumer requires current operating state path")
    proof = {**contract, "contract_id": PREPARATION_CONTRACT}
    preparation_context(proof, data_asof=data_day, checked_at=checked_at,
                        expected_run_id=contract.get("run_id"), expected_harness_state=reference, root=root)
    state = pinned(reference)
    first = state["stages"][0]
    issued = aware(state["collection_command"]["issued_at"])
    collectible = aware(contract.get("collectible_at"))
    if (collectible.tz_convert("Asia/Seoul").date() <= pd.Timestamp(signal_day).date()
            or not aware(signal_day + "T15:30:00+09:00") <= issued <= aware(first["started_at"])
            or collectible > aware(first["started_at"])):
        raise ValueError("consumer collection chronology/D-1 mismatch")
    return {"contract_id": CONSUMER_CONTRACT, "evidence_mode": mode, "signal_date": signal_day,
            "run_id": state["run_id"], "completed_data_asof": data_day, "work_asof": state["asof"],
            "user_command_at": issued.isoformat(), "collection_started_at": first["started_at"],
            "collection_completed_at": first["completed_at"], "collectible_at": collectible.isoformat(),
            "contract_sha256": canonical_sha256(contract)}


def consumer_context(contract, *, signal_day, checked_at, root=None):
    """Nine complete producer inputs are evidence only; capture creates actual receipts."""
    from .quant25_input_export import validate_input_export

    context = consumer_binding(contract, signal_day=signal_day, checked_at=checked_at, root=root)
    manifest = pinned(contract.get("input_manifest"))
    reject_preparation(manifest)
    if "manual_timing" in manifest:
        raise ValueError("consumer input manifest must not carry an execution contract")
    path = Path(contract["input_manifest"]["path"]).resolve()
    validate_input_export(path, expected_data_asof=signal_day, consumer_timing=contract, checked_at=checked_at)
    proof = {**contract, "data_asof": signal_day}
    preparation_producers(proof, manifest, manifest_path=path)
    if aware(manifest["generated_at"]) > aware(checked_at):
        raise ValueError("consumer input production after check/capture")
    calendar = json.loads((path.parent / manifest["inputs"]["calendar"]["path"]).read_bytes())
    if (signal_day not in calendar or calendar.index(signal_day) == 0
            or manifest["required_qm_observation_date"] != calendar[calendar.index(signal_day) - 1]):
        raise ValueError("consumer exact previous QM session required")
    return {**context, "input_manifest": contract["input_manifest"],
            "input_completed_at": manifest["generated_at"]}


def pinned(reference):
    if not isinstance(reference, dict) or not reference.get("path") or not reference.get("sha256"):
        raise ValueError("pinned evidence file reference required")
    path = Path(reference["path"]).resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("input timing evidence hash mismatch")
    return json.loads(raw)


def _mode(contract, root=None):
    mode = contract.get("evidence_mode")
    if mode not in {"ACTUAL", TEST_ONLY}:
        raise ValueError("explicit evidence mode required")
    if mode == TEST_ONLY:
        location = Path(root or contract.get("test_root", "")).resolve()
        reports = Path(__file__).resolve().parents[3] / "reports"
        if not location.is_relative_to(reports) or not any(p.startswith(TEST_ONLY) for p in location.parts):
            raise ValueError("synthetic timing requires isolated TEST_ONLY root")
    return mode


def _same_file_reference(left, right):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if not left.get("path") or not right.get("path"):
        return False
    first, second = Path(left["path"]), Path(right["path"])
    return (first.is_absolute() and second.is_absolute() and first.resolve() == second.resolve()
            and {k: v for k, v in left.items() if k != "path"}
            == {k: v for k, v in right.items() if k != "path"})


def preparation_context(contract, *, data_asof, checked_at, expected_run_id,
                        expected_harness_state, root=None):
    """Bind preparation to WD01 completion; never require or change cycle completion."""
    if not isinstance(contract, dict) or contract.get("contract_id") != PREPARATION_CONTRACT:
        raise ValueError("explicit preparation contract required")
    if (not expected_run_id or contract.get("run_id") != expected_run_id
            or contract.get("data_asof") != data_asof
            or expected_harness_state is None
            or not _same_file_reference(contract.get("harness_state"), expected_harness_state)):
        raise ValueError("preparation current run/state/data_asof binding mismatch")
    mode = _mode(contract, root)
    now = aware(checked_at)
    if mode == "ACTUAL" and now > pd.Timestamp.now(tz="UTC"):
        raise ValueError("actual preparation cannot use future clock")
    if "collection_basis" in contract:
        from .quant25_supplemental_collection import BASIS, completed_context

        if contract["collection_basis"] != BASIS:
            raise ValueError("unsupported preparation collection basis")
        context = completed_context(contract, data_asof=data_asof, checked_at=checked_at,
                                    expected_run_id=expected_run_id, expected_state=expected_harness_state,
                                    mode=mode, root=root or contract.get("test_root"))
        return {**context, "contract_id": PREPARATION_CONTRACT}
    state = pinned(expected_harness_state)
    command = pinned(contract.get("collection_command"))
    if (state.get("run_id") != expected_run_id
            or state.get("collection_command") != command
            or state.get("collection_command_ref") != contract.get("collection_command")
            or command.get("data_asof") != data_asof
            or command.get("classification") != (TEST_ONLY if mode == TEST_ONLY else "ACTUAL_USER_COMMAND_BINDING")):
        raise ValueError("preparation same-run command binding mismatch")
    from scripts.harness.collection_command_binding import validate_command
    state_path = Path(expected_harness_state["path"]).resolve()
    validate_command(command, state, state_path.parent.parent)
    stages = state.get("stages") or []
    if not stages:
        raise ValueError("preparation WD01/WE01 completion required")
    first = stages[0]
    prefix = {"weekday": "WD01", "weekend": "WE01"}.get(state.get("cycle_type"))
    binding = state.get("input_target_binding", {})
    if (first.get("stage_id", "").split("_")[0] != prefix
            or first.get("status") != "completed" or first.get("reported_status") != "completed"
            or binding.get("run_id") != expected_run_id
            or binding.get("cycle_type") != state.get("cycle_type")
            or binding.get("requested_asof") != state.get("asof")
            or binding.get("stage_id") != first.get("stage_id")
            or binding.get("data_asof") != data_asof
            or binding.get("report_file") != first.get("report_file")):
        raise ValueError("preparation first-stage completed report binding mismatch")
    raw = Path(binding["report_file"]).read_bytes()
    lines = raw.decode("utf-8-sig").splitlines()
    if (hashlib.sha256(raw).hexdigest() != binding.get("report_sha256")
            or [s.partition(":")[2].strip() for s in lines if s.partition(":")[0] == "data_asof"] != [data_asof]
            or [s.partition(":")[2].strip() for s in lines if s.partition(":")[0] == "status"] != ["completed"]):
        raise ValueError("preparation first-stage report hash/date/status mismatch")
    if not (aware(command["issued_at"]) <= aware(state["created_at"])
            <= aware(first["started_at"]) <= aware(first["completed_at"]) <= now):
        raise ValueError("preparation first-stage chronology mismatch")
    return {"contract_id": PREPARATION_CONTRACT, "run_id": expected_run_id,
            "data_asof": data_asof, "evidence_mode": mode,
            "decision_ready": False, "historical_live_evidence": False}


def preparation_producers(contract, manifest, *, manifest_path):
    """Reuse producer manifests as pinned per-input completion evidence, not receipts."""
    entries = manifest["inputs"]
    references = contract.get("producer_manifests")
    if not isinstance(references, dict) or set(references) != set(entries):
        raise ValueError("exact nine preparation producer references required")
    generated = aware(manifest["generated_at"])
    if generated < aware(manifest["observed_at"]):
        raise ValueError("preparation generated before observation")
    if contract["evidence_mode"] == "ACTUAL" and generated > pd.Timestamp.now(tz="UTC"):
        raise ValueError("preparation future generation timestamp")
    for name, entry in entries.items():
        if not aware(entry["observed_at"]) <= aware(entry["extracted_at"]) <= generated:
            raise ValueError(f"{name}: preparation input observation chronology")
        ref = references[name]
        if ref is None:
            if entry["ready"]:
                raise ValueError(f"{name}: completed producer evidence required")
            continue
        report = pinned(ref)
        if (Path(ref["path"]).resolve() == Path(manifest_path).resolve()
                or report.get("schema") != "q25_input_preparation_v1"
                or "preparation_contract" in report or "manual_timing" in report
                or report.get("data_asof") != contract["data_asof"]
                or report.get("run_id", contract["run_id"]) != contract["run_id"]
                or report.get("decision_ready") is not False
                or report.get("historical_live_evidence") is not False):
            raise ValueError(f"{name}: invalid producer manifest scope")
        producer = report.get("inputs", {}).get(name, {})
        fields = ("owner", "status", "ready", "sha256", "row_count", "data_asof", "source_asof")
        if any(producer.get(k) != entry.get(k) for k in fields):
            raise ValueError(f"{name}: producer input/completion mismatch")
        completed = aware(report["generated_at"])
        if not (aware(producer.get("observed_at")) <= aware(producer.get("extracted_at"))
                <= completed <= generated
                and aware(producer.get("observed_at")) <= aware(entry["observed_at"])):
            raise ValueError(f"{name}: producer observation/completion chronology")
        if entry["ready"] and (producer.get("ready") is not True
                               or producer.get("status") not in {"produced", "reused"}):
            raise ValueError(f"{name}: producer incomplete")
        file = producer.get("path")
        if file is None:
            if producer.get("ready") or producer.get("sha256") is not None:
                raise ValueError(f"{name}: producer file missing")
            continue
        parent = Path(ref["path"]).resolve().parent
        source = (parent / file).resolve()
        if (Path(file).is_absolute() or not source.is_relative_to(parent)
                or hashlib.sha256(source.read_bytes()).hexdigest() != entry.get("sha256")):
            raise ValueError(f"{name}: producer file hash/path mismatch")


def collection_context(contract, *, signal_day, checked_at, root=None):
    """Read existing Harness prompt state and its first-stage report binding.

    Explicit command attestation references a user event, not operator_note.
    Production command events must reside in the existing Codex session store.
    A completed data stage is distinct from downstream model/publish stages.
    """
    if consumer_opted_in(contract):
        return consumer_context(contract, signal_day=signal_day, checked_at=checked_at, root=root)
    if not opted_in(contract):
        raise ValueError("manual timing is disabled")
    mode = _mode(contract, root)
    now = aware(checked_at)
    if mode == "ACTUAL" and now > pd.Timestamp.now(tz="UTC"):
        raise ValueError("actual timing cannot use future clock")
    if contract.get("signal_date") != signal_day:
        raise ValueError("manual signal binding mismatch")
    state = pinned(contract.get("harness_state"))
    command = pinned(contract.get("collection_command"))
    binding = state.get("input_target_binding", {})
    collected_day = binding.get("data_asof", "")
    if command.get("classification") != (TEST_ONLY if mode == TEST_ONLY else "ACTUAL_USER_COMMAND_BINDING"):
        raise ValueError("command evidence classification mismatch")
    if (command.get("actor") != "USER" or command.get("action") != "COLLECT_DATA"
            or command.get("run_id") != state.get("run_id")
            or command.get("work_asof") != state.get("asof")
            or command.get("data_asof") != collected_day or collected_day < signal_day):
        raise ValueError("explicit user collection command/run binding required")
    # Reuse the Harness owner's original-event and operator semantic review.
    # This is provenance validation, not an independent authorization service.
    from scripts.harness.collection_command_binding import validate_command
    state_path = Path(contract["harness_state"]["path"]).resolve()
    if state.get("collection_command") != command or state.get("collection_command_ref") != contract["collection_command"]:
        raise ValueError("immutable same-run command binding missing or changed")
    validate_command(command, state, state_path.parent.parent)
    issued = aware(command["issued_at"])
    stages = state.get("stages") or []
    if not stages:
        raise ValueError("Harness collection stage evidence missing")
    first = stages[0]
    if (binding.get("run_id") != state.get("run_id") or binding.get("cycle_type") != state.get("cycle_type")
            or binding.get("requested_asof") != state.get("asof")
            or binding.get("stage_id") != first.get("stage_id")
            or binding.get("report_file") != first.get("report_file")):
        raise ValueError("Harness input_target_binding mismatch or missing")
    report = Path(binding["report_file"]).read_bytes()
    if hashlib.sha256(report).hexdigest() != binding.get("report_sha256"):
        raise ValueError("Harness first-stage report hash mismatch")
    dates = [line.partition(":")[2].strip() for line in report.decode("utf-8-sig").splitlines()
             if line.partition(":")[0] == "data_asof"]
    if dates != [collected_day]:
        raise ValueError("Harness report data_asof mismatch")
    required = contract.get("collection_stage_ids")
    if not isinstance(required, list) or not required or first["stage_id"] not in required:
        raise ValueError("explicit completed collection stage scope required")
    minimum = {"weekday": {"WD01", "WD02", "WD03"}, "weekend": {"WE01"}}.get(state.get("cycle_type"))
    if minimum is None or not minimum <= {s.split("_")[0] for s in required}:
        raise ValueError("complete Harness collection-stage scope required")
    selected = [s for s in stages if s.get("stage_id") in required]
    if (len(selected) != len(set(required)) or any(s.get("status") != "completed"
            or s.get("reported_status") != "completed" for s in selected)):
        raise ValueError("required Harness data stages incomplete")
    starts = [aware(s.get("started_at")) for s in selected]
    ends = [aware(s.get("completed_at")) for s in selected]
    if (state.get("status") != "completed" or any(s.get("status") != "completed" for s in stages)
            or not issued <= aware(state.get("created_at")) <= min(starts)
            or not max(ends) <= aware(state.get("completed_at")) <= now):
        raise ValueError("Harness cycle completion evidence missing or nonchronological")
    collectible = aware(contract.get("collectible_at"))
    close = aware(signal_day + "T15:30:00+09:00")
    if (collectible.tz_convert("Asia/Seoul").date() <= close.date()
            or not close <= issued <= min(starts) or not collectible <= min(starts)
            or any(a > b for a, b in zip(starts, ends)) or max(ends) > now
            or pd.Timestamp(collected_day).date() >= pd.Timestamp(state["asof"]).date()):
        raise ValueError("Harness manual collection chronology/D-1 mismatch")
    return {"contract_id": CONTRACT, "evidence_mode": mode, "signal_date": signal_day,
            "run_id": state["run_id"], "user_command_at": issued.isoformat(),
            "completed_data_asof": collected_day, "work_asof": state["asof"],
            "collection_started_at": min(starts).isoformat(), "collection_completed_at": max(ends).isoformat(),
            "collectible_at": collectible.isoformat(), "contract_sha256": canonical_sha256(contract)}


def validity(contract, calendar, *, signal_day, cutoff, execution=None, next_rebalance=None, root=None):
    from .quant25_bootstrap_execution_candidate import first_open
    from .quant25_manual_collection_candidate import schedule

    context = collection_context(contract, signal_day=signal_day, checked_at=cutoff, root=root)
    expiry, horizon = schedule(calendar, signal_day)
    execution = execution or first_open(calendar, cutoff)
    if aware(cutoff) >= aware(expiry) or aware(execution + "T09:00:00+09:00") >= aware(expiry):
        raise ValueError("EXPIRED_WEEKLY_SIGNAL")
    if execution != first_open(calendar, cutoff) or (next_rebalance is not None and next_rebalance != horizon):
        raise ValueError("first future open/next regular rebalance required")
    return {**context, "expires_at": expiry, "execution_date": execution, "next_rebalance": horizon}


def verify_coverage(contract, *, evidence, stocks, calendar, cutoff, execution, horizon, reviewed_after=None):
    """A complete owner coverage manifest must bind the actual input and horizon.

    This reads supplied official source bytes only. It neither searches sources
    nor converts unknown corporate actions into a no-event finding.
    """
    check_evidence(evidence, aware(cutoff), historical=False)
    latest = max(aware(r["available_at"]) for r in evidence.values())
    if consumer_opted_in(contract) and contract.get("capture_provenance"):
        latest = max(latest, aware(pinned(contract["capture_provenance"])["completed_at"]))
    return _coverage_review(contract, rules_sha=evidence["rules"]["sha256"],
        calendar_sha=evidence["calendar"]["sha256"], stocks=stocks, calendar=calendar,
        cutoff=cutoff, execution=execution, horizon=horizon,
        reviewed_after=max(latest, aware(reviewed_after)) if reviewed_after is not None else latest)


def _coverage_review(contract, *, rules_sha, calendar_sha, stocks, calendar, cutoff,
                     execution, horizon, reviewed_after):
    from .quant25_event_materiality import SIMPLE_POLICY, assess, enabled

    coverage = pinned(contract.get("event_coverage"))
    mode = _mode(contract)
    materiality = enabled(contract)
    simple = contract.get("event_materiality_policy") == SIMPLE_POLICY
    scope = coverage.get("queried_tickers", []) if materiality else coverage.get("covered_tickers", [])
    if simple:
        scope = coverage.get("reviewed_tickers", [])
    status_valid = (coverage.get("status") in {"PARTIAL", "COMPLETE"} if materiality else
                    coverage.get("status") == "COMPLETE" and coverage.get("unresolved_events") == [])
    window_valid = (coverage.get("review_window") == {"execution_date": execution, "next_rebalance": horizon}
                    if materiality else
                    aware(coverage.get("effective_from")) <= aware(execution + "T09:00:00+09:00")
                    and aware(coverage.get("effective_until")) >= aware(horizon + "T09:00:00+09:00"))
    classification = ("OFFICIAL_SOURCE_CONSUMPTION_REVIEW" if simple else "OFFICIAL_SOURCE_COVERAGE")
    if (coverage.get("classification") != (TEST_ONLY if mode == TEST_ONLY else classification)
            or not status_valid
            or coverage.get("run_id") != pinned(contract["harness_state"]).get("run_id")
            or coverage.get("rules_sha256") != rules_sha
            or coverage.get("calendar_sha256") != calendar_sha
            or not set(stocks) <= set(scope)
            or coverage.get("execution_date") != execution or execution not in calendar
            or not window_valid
            or coverage.get("reviewed_domains") != ["corporate_actions", "rights", "trading_halts"]):
        raise ValueError("official event/rights coverage incomplete or horizon mismatch")
    reviewed = aware(coverage.get("reviewed_at"))
    if not aware(reviewed_after) <= reviewed <= aware(cutoff):
        raise ValueError("fresh event/rights review required")
    sources = coverage.get("source_files", [])
    if not sources:
        raise ValueError("official coverage source bytes required")
    for source in sources:
        raw = Path(source["path"]).read_bytes()
        if (hashlib.sha256(raw).hexdigest() != source.get("sha256")
                or not source.get("source_url") or not source.get("publisher")
                or aware(source.get("observed_at")) > reviewed):
            raise ValueError("coverage source provenance mismatch")
        if mode == "ACTUAL":
            url = urlparse(source["source_url"])
            allowed = {"KRX": "krx.co.kr", "KRX_KIND": "krx.co.kr", "DART": "fss.or.kr", "KSD": "ksd.or.kr"}
            domain = allowed.get(source["publisher"])
            host = url.hostname or ""
            if (not domain or url.scheme != "https"
                    or not (host == domain or host.endswith("." + domain))):
                raise ValueError("unrecognized official coverage source authority")
    if materiality:
        return {**coverage, "consumer_assessment": assess(contract, coverage, stocks=stocks, cutoff=cutoff)}
    return coverage


def verify_prepared_materiality(contract, manifest, *, manifest_path, cutoff):
    """Review producer bytes before capture without fabricating receipt timestamps."""
    from .quant25_bootstrap_execution_candidate import first_open
    from .quant25_event_materiality import enabled
    from .quant25_manual_collection_candidate import schedule

    if not enabled(contract):
        raise ValueError("explicit materiality policy required for partial rules")
    entries = manifest["inputs"]
    parent = Path(manifest_path).resolve().parent
    values = {}
    for name in ("universe", "sector", "etf_intent", "calendar", "rules"):
        entry = entries[name]
        path = (parent / entry["path"]).resolve()
        if not path.is_relative_to(parent) or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("materiality preparation source/hash mismatch")
        values[name] = json.loads(path.read_bytes())
    if not isinstance(values["rules"], list):
        raise ValueError("materiality rules payload required")
    _, horizon = schedule(values["calendar"], contract["signal_date"])
    execution = first_open(values["calendar"], cutoff)
    scope = set(values["universe"]) | (set(values["etf_intent"]["weights"]) - {"CASH"})
    scope |= {v["ticker"] for v in values["sector"]}
    after = max([aware(manifest["generated_at"]), *(aware(v["extracted_at"]) for v in entries.values())])
    return _coverage_review(contract, rules_sha=entries["rules"]["sha256"],
        calendar_sha=entries["calendar"]["sha256"], stocks=scope, calendar=values["calendar"],
        cutoff=cutoff, execution=execution, horizon=horizon, reviewed_after=after)["consumer_assessment"]


def verify_capture_binding(contract, receipts, evidence, *, cutoff):
    """Bind the named nine receipts to this captured Harness/command context."""
    capture = pinned(contract.get("capture_provenance"))
    identity = ("contract_id", "enabled", "evidence_mode", "signal_date", "collectible_at",
                "collection_stage_ids", "harness_state", "collection_command")
    if consumer_opted_in(contract):
        identity += ("run_id", "data_asof", "input_manifest", "producer_manifests", "monthly_evidence",
                     "event_materiality_policy")
    if (capture.get("schema") != "q25_daily_input_capture_v1" or capture.get("day") != contract["signal_date"]
            or any(capture.get("manual_timing", {}).get(k) != contract.get(k) for k in identity)
            or capture.get("receipts") != evidence
            or {k: v["receipt_id"] for k, v in evidence.items()} != receipts):
        raise ValueError("capture receipt/command/cycle binding mismatch")
    context = collection_context(contract, signal_day=contract["signal_date"], checked_at=cutoff)
    if (capture.get("collection_context", {}).get("run_id") != context["run_id"]
            or capture.get("source_config", {}).get("completed_data_asof") != context["completed_data_asof"]
            or not aware(context["collection_completed_at"]) <= aware(capture.get("observed_at")) <= aware(cutoff)):
        raise ValueError("capture completion/availability binding mismatch")
    if consumer_opted_in(contract):
        manifest = pinned(contract["input_manifest"])
        if (capture.get("source_config", {}).get("input_manifest") != contract["input_manifest"]
                or capture.get("batch_id") != canonical_sha256({"input_manifest": contract["input_manifest"],
                    "harness_state": contract["harness_state"], "receipts": capture["receipts"]})
                or not aware(context["input_completed_at"]) <= aware(capture["observed_at"])
                <= aware(capture.get("completed_at")) <= aware(cutoff)
                or any(evidence[n]["sha256"] != entry["sha256"] for n, entry in manifest["inputs"].items())
                or any(not aware(r["arrived_at"]) <= aware(r["available_at"]) <= aware(capture["completed_at"])
                       for n, r in evidence.items() if n != "etf_intent")):
            raise ValueError("consumer same-batch receipt/hash/actual timing mismatch")
        observations = capture.get("input_observations")
        if observations is not None or capture.get("observation_journal_key"):
            scope = {k: v for k, v in capture["manual_timing"].items()
                     if k not in {"capture_provenance", "event_coverage", "event_materiality_review"}}
            if (not isinstance(observations, dict) or set(observations) != set(evidence) - {"etf_intent"}
                    or capture.get("observation_journal_key") != "consumer-capture:" + canonical_sha256(scope)):
                raise ValueError("consumer batch reobservation proof missing")
            parent = Path(contract["input_manifest"]["path"]).resolve().parent
            for n, observation in observations.items():
                if (observation.get("receipt_id") != receipts[n]
                        or observation.get("sha256") != evidence[n]["sha256"]
                        or observation.get("producer_path") != str((parent / manifest["inputs"][n]["path"]).resolve())
                        or not aware(capture["observed_at"]) <= aware(observation.get("read_started_at"))
                        <= aware(observation.get("verified_at")) <= aware(capture["completed_at"])):
                    raise ValueError("consumer batch reobservation binding/time mismatch")
        elif any(aware(r["arrived_at"]) < aware(capture["observed_at"])
                 for n, r in evidence.items() if n != "etf_intent"):
            # Old first-capture proofs remain valid. Old receipts alone cannot
            # assert that their unchanged bytes were read again in a new batch.
            raise ValueError("consumer batch reobservation proof missing")
    return capture


def verify_consumer_receipts(contract, evidence, *, cutoff, root=None, inputs=None):
    """Require the sealed batch's nine real journal records, including original ETF receipt."""
    import io
    import sqlite3
    from contextlib import closing

    from .quant25_incremental_selection import SOURCES
    from .quant25_monthly_evidence import verify_received_monthly
    from .quant25_monthly_start_contract import resolved_receipt

    if set(evidence) != SOURCES:
        raise ValueError("consumer all nine actual receipts required")
    receipts = {name: entry["receipt_id"] for name, entry in evidence.items()}
    capture = verify_capture_binding(contract, receipts, evidence, cutoff=cutoff)
    observed_root = Path(capture.get("observation_root", "")).resolve()
    if root is not None and observed_root != Path(root).resolve():
        raise ValueError("consumer capture belongs to another observation root")
    _mode(contract, observed_root)
    uri = (observed_root / "forward_receipts.sqlite3").as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as con:
        if capture.get("observation_journal_key"):
            observed = con.execute("SELECT body FROM journal WHERE key=? AND kind='consumer_capture'",
                                   (capture["observation_journal_key"],)).fetchone()
            if observed is None or json.loads(observed[0]) != capture:
                raise ValueError("consumer reobservation is not the recorded batch")
        for name, key in receipts.items():
            row = con.execute("SELECT body,raw FROM journal WHERE key=? AND kind='receipt'", (key,)).fetchone()
            if (row is None or resolved_receipt(con, json.loads(row[0])) != evidence[name]
                    or hashlib.sha256(row[1]).hexdigest() != evidence[name]["sha256"]):
                raise ValueError("consumer receipt is not the recorded actual input")
            if inputs is not None:
                if name in {"features", "fundamentals", "prices"}:
                    expected = pd.read_csv(io.BytesIO(row[1]), dtype={"ticker": str})
                    try:
                        pd.testing.assert_frame_equal(expected, inputs[name], check_exact=True)
                    except AssertionError as exc:
                        raise ValueError("consumer selector differs from captured input") from exc
                elif name != "etf_intent" and json.loads(row[1]) != inputs[name]:
                    raise ValueError("consumer selector differs from captured input")
            if name == "etf_intent":
                if inputs is not None:
                    target, supplied = json.loads(row[1]), inputs[name]
                    if (target["weights"] != supplied.weights or target["model_code"] != supplied.model_code
                            or pd.Timestamp(target["decision_date"]) != supplied.decision_date
                            or pd.Timestamp(target["execution_date"]) != supplied.execution_date
                            or pd.Timestamp(evidence[name].get("provider_available_at") or target["published_at"])
                            != supplied.published_at or target["run_id"] != supplied.run_id
                            or target["evidence_state"] != supplied.evidence_state):
                        raise ValueError("consumer ETF selector differs from captured target")
                monthly = verify_received_monthly(json.loads(row[1]), contract.get("monthly_evidence"),
                    signal_day=contract["signal_date"], checked_at=cutoff, availability_cutoff=cutoff,
                    observation_root=observed_root)
                if monthly != evidence[name]:
                    raise ValueError("consumer original monthly receipt mismatch")
    return capture
