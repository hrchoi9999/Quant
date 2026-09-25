"""Evidence for a separately approved, one-shot Q25 input refresh.

This does not execute collectors or grant model/publication authority. The owner
must review the exact argv and current processes before claiming the one attempt.
Existing weekday/weekend command parsing and completion gates are unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .quant25_incremental_selection import aware
from .quant25_paper_live import canonical_sha256

BASIS = "Q25_SUPPLEMENTAL_INPUT_REFRESH_V1"
TEST_ONLY = "SYNTHETIC_TEST_ONLY"
SCOPE = {"q25_inputs_only": True, "collection_attempts": 1, "ai_training": False,
         "legacy_model_runs": False, "capture_decide": False, "publication": False}
STATE_FILE = "q25_input_refresh_state.json"
RUNTIME_ARGUMENTS = {"@Q25_TARGET_SHA256@", "@Q25_TARGET_COUNT@", "@Q25_UNIVERSE_SHA256@"}


def _pinned(ref):
    if not isinstance(ref, dict) or not Path(ref.get("path", "")).is_absolute():
        raise ValueError("supplemental absolute evidence reference required")
    raw = Path(ref["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref.get("sha256"):
        raise ValueError("supplemental evidence hash mismatch")
    return json.loads(raw)


def question_text(data_day, parent_day):
    day, old = date.fromisoformat(data_day), date.fromisoformat(parent_day)
    return (f"2.5 신규 주간 서비스 자료를 완성하려면 {day.month}월 {day.day}일 종가 입력이 추가로 필요합니다. "
            f"기존 {old.month}월 {old.day}일 작업과 구분해, 2.5용 주식·ETF 및 필요한 시장 입력의 "
            "수집·가공 1회를 승인하시겠습니까? 완료된 1.0 계산은 반복하지 않고 AI 학습은 제외합니다.")


def validate_authorization(command, *, checked_at, mode, root):
    """Bind the entire original user reply, including its question and answer."""
    now = aware(checked_at)
    location = Path(root or Path(__file__).resolve().parents[3]).resolve()
    if mode not in {"ACTUAL", TEST_ONLY}:
        raise ValueError("supplemental evidence mode required")
    if mode == TEST_ONLY and not any(p.startswith(TEST_ONLY) for p in location.parts):
        raise ValueError("supplemental synthetic evidence requires isolated root")
    if mode == "ACTUAL" and now > pd.Timestamp.now(tz="UTC"):
        raise ValueError("supplemental actual check cannot use future time")
    if (command.get("schema") != BASIS or command.get("actor") != "USER"
            or command.get("action") != "COLLECT_Q25_INPUTS"
            or command.get("classification") != (TEST_ONLY if mode == TEST_ONLY else "ACTUAL_USER_COMMAND_BINDING")
            or command.get("scope") != SCOPE):
        raise ValueError("supplemental explicit bounded scope required")
    data_day, work_day = date.fromisoformat(command["data_asof"]), date.fromisoformat(command["work_asof"])
    parent_day = date.fromisoformat(command["parent_data_asof"])
    if (data_day.isoformat() != command["data_asof"] or work_day.isoformat() != command["work_asof"]
            or work_day != data_day + timedelta(days=1) or parent_day >= data_day
            or work_day.weekday() >= 5):
        raise ValueError("supplemental D-1 weekday/date scope mismatch")
    ref = command["source_event"]
    path = Path(ref["path"])
    if not path.is_absolute() or (mode == "ACTUAL" and not path.resolve().is_relative_to(
            (Path.home() / ".codex/sessions").resolve())):
        raise ValueError("supplemental original session path required")
    number = ref.get("line_number")
    if type(number) is not int or number < 1:
        raise ValueError("supplemental original event line required")
    with path.open("rb") as handle:
        raw = next((line for i, line in enumerate(handle, 1) if i == number), b"")
    if not raw or hashlib.sha256(raw).hexdigest() != ref.get("sha256"):
        raise ValueError("supplemental original event hash mismatch")
    event = json.loads(raw)
    payload = event.get("payload", {})
    content = payload.get("content", [])
    if (event.get("type") != "response_item" or payload.get("type") != "message"
            or payload.get("role") != "user" or not isinstance(content, list) or len(content) != 1
            or content[0].get("type") != "input_text"):
        raise ValueError("supplemental original direct user reply required")
    message = content[0].get("text", "")
    prefix, suffix = "<send_user_message_question_reply>", "</send_user_message_question_reply>"
    if (canonical_sha256(message) != command.get("message_sha256")
            or not message.startswith(prefix) or not message.endswith(suffix)):
        raise ValueError("supplemental full original reply binding required")
    answers = json.loads(message[len(prefix):-len(suffix)])
    if not isinstance(answers, list) or len(answers) != 1:
        raise ValueError("supplemental single question reply required")
    item = answers[0]
    expected_answer = f"{data_day.month}월 {data_day.day}일 입력 수집·가공 1회 승인"
    if (item.get("question") != question_text(command["data_asof"], command["parent_data_asof"])
            or item.get("answer") != expected_answer or item != command.get("question_reply")):
        raise ValueError("supplemental exact question/answer scope mismatch")
    question_id = json.loads(item["questionItemId"])
    if (not isinstance(question_id, list) or len(question_id) != 3
            or question_id[0] != "request_user_input_async" or question_id[2] != 0
            or not isinstance(question_id[1], str) or not question_id[1].startswith("call_")):
        raise ValueError("supplemental question identity mismatch")
    issued = aware(event["timestamp"])
    review = command.get("operator_review", {})
    reviewed = aware(review.get("reviewed_at"))
    if (issued != aware(command["issued_at"]) or not issued <= reviewed <= now
            or issued.tz_convert("Asia/Seoul").date() != work_day
            or not review.get("reviewer") or not review.get("basis")
            or any(review.get(k) is not True for k in (
                "direct_user_collection_confirmed", "latest_instruction_checked",
                "not_cancelled_or_superseded", "question_answer_mapping_confirmed"))):
        raise ValueError("supplemental current operator review/chronology required")
    return command


def _execution_review(command, review, checked_at):
    now, checked = aware(checked_at), aware(review.get("checked_at"))
    if (now.tz_convert("Asia/Seoul").date().isoformat() != command["work_asof"]
            or not aware(command["operator_review"]["reviewed_at"]) <= checked <= now
            or not pd.Timedelta(0) <= now - checked <= pd.Timedelta(minutes=2)
            or any(review.get(k) is not True for k in (
                "no_active_collection_or_db_writer", "no_active_weekend_or_full_cycle",
                "argv_scope_reviewed", "existing_parent_dates_preserved"))
            or not review.get("reviewer")):
        raise ValueError("supplemental fresh execution/overlap review required")
    plan = _pinned(review.get("execution_plan"))
    if (plan.get("scope") != SCOPE or plan.get("data_asof") != command["data_asof"]
            or plan.get("work_asof") != command["work_asof"]
            or not isinstance(plan.get("commands"), list) or not plan["commands"]
            or any(not isinstance(argv, list) or not argv or
                   any(not isinstance(arg, str) or not arg for arg in argv) for argv in plan["commands"])):
        raise ValueError("supplemental reviewed exact command plan required")
    tokens = {arg for argv in plan["commands"] for arg in argv if arg.startswith("@Q25_")}
    if tokens and (not tokens <= RUNTIME_ARGUMENTS
                   or set(plan.get("runtime_input_paths", {})) != {"target", "universe"}
                   or any(not Path(p).is_absolute() for p in plan["runtime_input_paths"].values())):
        raise ValueError("supplemental explicit runtime argument paths required")
    return plan


def claim_attempt(command_ref, *, run_id, checked_at, execution_review, mode, root):
    """Exclusive artifact claim BEFORE the OS invokes its reviewed collectors.

    A failure retains this claim. It is not permission for an automatic retry.
    No subprocess, DB or network operation is performed here.
    """
    command = validate_authorization(_pinned(command_ref), checked_at=checked_at, mode=mode, root=root)
    if run_id != command.get("run_id") or not run_id or Path(run_id).name != run_id:
        raise ValueError("supplemental single run identity required")
    now = aware(checked_at)
    _execution_review(command, execution_review, checked_at)
    base = (Path(__file__).resolve().parents[3] / "reports/quant2_0"
            if mode == "ACTUAL" else Path(root).resolve())
    directory = base / "q25_supplemental_claims"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (command["source_event"]["sha256"] + ".json")
    record = {"schema": BASIS, "run_id": run_id, "command": command_ref, "claimed_at": now.isoformat(),
              "execution_review": execution_review, "attempt": 1, "evidence_mode": mode}
    with path.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _executed_commands(plan, receipt):
    """Resolve only hashes/count derived after dated universe collection.

    Placeholders belong to the reviewed plan, never to subprocess arguments.
    Every other executed argument must match the pre-collection plan exactly.
    """
    commands = plan["commands"]
    tokens = {arg for argv in commands for arg in argv if arg.startswith("@Q25_")}
    if not tokens:
        return commands
    if not tokens <= RUNTIME_ARGUMENTS:
        raise ValueError("unsupported supplemental runtime argument")
    expected_paths, refs = plan.get("runtime_input_paths", {}), receipt.get("runtime_inputs", {})
    if set(expected_paths) != {"target", "universe"} or set(refs) != set(expected_paths):
        raise ValueError("supplemental pinned runtime target/universe required")
    for name, ref in refs.items():
        path = Path(ref["path"])
        if (not path.is_absolute() or path.resolve() != Path(expected_paths[name]).resolve()
                or hashlib.sha256(path.read_bytes()).hexdigest() != ref.get("sha256")):
            raise ValueError("supplemental runtime input hash/path mismatch")
    with Path(refs["target"]["path"]).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    tickers = [row.get("ticker", "") for row in rows]
    if (len(set(tickers)) != len(tickers)
            or any(len(t) != 6 or not t.isdigit() for t in tickers)):
        raise ValueError("supplemental runtime target must contain unique six-digit tickers")
    values = {"@Q25_TARGET_SHA256@": refs["target"]["sha256"], "@Q25_TARGET_COUNT@": str(len(rows)),
              "@Q25_UNIVERSE_SHA256@": refs["universe"]["sha256"]}
    return [[values.get(arg, arg) for arg in argv] for argv in commands]


def completed_context(contract, *, data_asof, checked_at, expected_run_id, expected_state, mode, root):
    """Validate supplemental completion without fabricating a WD01 stage."""
    if mode == TEST_ONLY:
        root = contract.get("test_root") or root
    state = _pinned(expected_state)
    path = Path(expected_state["path"]).resolve()
    command = validate_authorization(_pinned(contract.get("collection_command")),
                                     checked_at=checked_at, mode=mode, root=root)
    if (contract.get("collection_basis") != BASIS or state.get("schema") != BASIS
            or state.get("run_id") != expected_run_id or command.get("run_id") != expected_run_id
            or path.name != STATE_FILE or path.parent.name != expected_run_id
            or state.get("data_asof") != data_asof or command.get("data_asof") != data_asof
            or state.get("asof") != command["work_asof"] or state.get("scope") != SCOPE
            or state.get("collection_command_ref") != contract.get("collection_command")
            or state.get("status") != "completed" or "stages" in state):
        raise ValueError("supplemental same-run completed state required")
    if mode == "ACTUAL" and path != (Path(__file__).resolve().parents[3] / "reports/quant2_0" /
                                     expected_run_id / STATE_FILE):
        raise ValueError("supplemental canonical operating state path required")
    parent = _pinned(state.get("parent_state"))
    if (parent.get("run_id") == expected_run_id or parent.get("cycle_type") != "weekday"
            or parent.get("collection_command", {}).get("data_asof") != command["parent_data_asof"]
            or parent.get("input_target_binding", {}).get("data_asof") != command["parent_data_asof"]
            or parent.get("asof") >= state["asof"]):
        raise ValueError("supplemental original parent identity/date required")
    claim_ref = state.get("attempt_claim")
    claim = _pinned(claim_ref)
    base = (Path(__file__).resolve().parents[3] / "reports/quant2_0"
            if mode == "ACTUAL" else Path(root).resolve())
    if (Path(claim_ref["path"]).resolve() != base / "q25_supplemental_claims" /
            (command["source_event"]["sha256"] + ".json")
            or claim.get("command") != contract["collection_command"]
            or claim.get("run_id") != expected_run_id or claim.get("attempt") != 1
            or claim.get("evidence_mode") != mode):
        raise ValueError("supplemental single attempt claim mismatch")
    _execution_review(command, claim["execution_review"], claim["claimed_at"])
    receipt = _pinned(state.get("completion_receipt"))
    if (receipt.get("schema") != BASIS or receipt.get("run_id") != expected_run_id
            or receipt.get("data_asof") != data_asof or receipt.get("work_asof") != state["asof"]
            or receipt.get("scope") != SCOPE or receipt.get("attempt_claim") != claim_ref
            or receipt.get("execution_plan") != claim["execution_review"]["execution_plan"]
            or receipt.get("collection_attempts") != 1 or receipt.get("exit_code") != 0
            or receipt.get("status") != "completed" or receipt.get("parent_state") != state["parent_state"]
            or receipt.get("parent_dates_preserved") is not True
            or any(type(receipt.get(k)) is not int or receipt[k] != 0 for k in (
                "ai_training_runs", "legacy_model_runs", "capture_calls", "decide_calls", "remote_writes"))):
        raise ValueError("supplemental actual completion receipt/scope mismatch")
    plan = _pinned(receipt["execution_plan"])
    commands = _executed_commands(plan, receipt)
    results = receipt.get("command_results", [])
    def valid_result(result, argv):
        if result.get("argv") != argv:
            return False
        if result.get("status") == "skipped_no_missing_target":
            return (result.get("exit_code") is None and "--insert-only" in argv
                    and "--expected-target-count" in argv
                    and argv[argv.index("--expected-target-count") + 1] == "0"
                    and any(Path(arg).name == "fetch_krx_openapi_daily_prices.py" for arg in argv))
        return result.get("exit_code") == 0 and result.get("status", "completed") == "completed"
    if len(results) != len(commands) or not all(valid_result(r, argv) for r, argv in zip(results, commands)):
        raise ValueError("supplemental exact executed command results required")
    start, end = aware(state.get("started_at")), aware(state.get("completed_at"))
    if (receipt.get("started_at") != state["started_at"] or receipt.get("completed_at") != state["completed_at"]
            or not aware(command["issued_at"]) <= aware(state.get("created_at"))
            <= aware(claim["claimed_at"]) <= start <= end <= aware(checked_at)
            or start.tz_convert("Asia/Seoul").date().isoformat() != state["asof"]):
        raise ValueError("supplemental actual completion chronology mismatch")
    return {"run_id": expected_run_id, "data_asof": data_asof, "work_asof": state["asof"],
            "evidence_mode": mode, "user_command_at": command["issued_at"],
            "collection_started_at": state["started_at"], "collection_completed_at": state["completed_at"],
            "decision_ready": False, "historical_live_evidence": False}
