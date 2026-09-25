"""Optional user-event provenance, not an authorization service or scheduler."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
TEST_ONLY = "SYNTHETIC_TEST_ONLY"


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def aware(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("collection evidence timestamp must include timezone")
    return stamp


def validate_command(command, state, run_root):
    """Check provenance and explicit operator review; hashes do not grant authority.

    This intentionally does not interpret arbitrary conversational instructions.
    An ambiguous message stays unbound; existing non-opt-in operation is unchanged.
    """
    expected = {"actor": "USER", "action": "COLLECT_DATA", "run_id": state["run_id"],
                "work_asof": state["asof"], "cycle_type": state["cycle_type"]}
    if any(command.get(k) != v for k, v in expected.items()):
        raise ValueError("collection command/run scope mismatch")
    data_day = date.fromisoformat(command["data_asof"])
    if data_day.isoformat() != command["data_asof"] or data_day >= date.fromisoformat(state["asof"]):
        raise ValueError("collection data_asof must precede work_asof")
    classification = command.get("classification")
    if classification not in {TEST_ONLY, "ACTUAL_USER_COMMAND_BINDING"}:
        raise ValueError("explicit collection evidence classification required")
    run_root = Path(run_root).resolve()
    if not state["run_id"] or Path(state["run_id"]).name != state["run_id"]:
        raise ValueError("collection run_id must be a single directory name")
    if classification == TEST_ONLY and not any(p.startswith(TEST_ONLY) for p in run_root.parts):
        raise ValueError("synthetic collection binding requires isolated TEST_ONLY root")
    stored = state.get("collection_command_ref")
    if stored:
        stored_path = (run_root / state["run_id"] / "collection_command.json").resolve()
        if Path(stored["path"]).resolve() != stored_path:
            raise ValueError("collection command reference outside run")
        stored_raw = stored_path.read_bytes()
        if (hashlib.sha256(stored_raw).hexdigest() != stored["sha256"]
                or json.loads(stored_raw) != command):
            raise ValueError("stored collection command changed")
    ref = command["source_event"]
    path = Path(ref["path"])
    if not path.is_absolute():
        raise ValueError("absolute original event path required")
    path = path.resolve()
    if classification != TEST_ONLY and not path.is_relative_to((Path.home() / ".codex" / "sessions").resolve()):
        raise ValueError("actual command must reference original session user event")
    number = ref["line_number"]
    if type(number) is not int or number < 1:
        raise ValueError("original event line required")
    with path.open("rb") as handle:
        raw = next((line for i, line in enumerate(handle, 1) if i == number), b"")
    if not raw or hashlib.sha256(raw).hexdigest() != ref["sha256"]:
        raise ValueError("original event hash mismatch")
    event = json.loads(raw)
    payload = event.get("payload", {})
    message = None
    if event.get("type") == "event_msg" and payload.get("type") == "user_message":
        message = payload.get("message")
    elif (event.get("type") == "response_item" and payload.get("type") == "message"
          and payload.get("role") == "user"):
        content = payload.get("content")
        if (isinstance(content, list) and len(content) == 1
                and content[0].get("type") == "input_text"):
            message = content[0].get("text")
    if not isinstance(message, str) or canonical_sha256(message) != command.get("message_sha256"):
        raise ValueError("original direct user message required")
    lowered = message.lower()
    forbidden = ("<codex_delegation", "heartbeat", "자동점검", "자동 점검", "취소", "중단",
                 "하지 마", "하지마", "하지 않", "금지", "cancel", "do not", "don't",
                 "개발", "수정", "연구", "다음 작업", "예약", "자동", "반복", "매일", "?")
    if any(word in lowered for word in forbidden):
        raise ValueError("relayed, automatic or cancelled message is not a collection command")
    # A direct user may ask the master to instruct Harness; the relay itself is never evidence.
    harness_dispatch = re.fullmatch(
        r"(?:ㅇㅋ\.\s*)?(?:일단\s+)?(?:\d{4}-\d{2}-\d{2}|\d{1,2}월\s*\d{1,2}일)"
        r"\s+종가\s+기준\s+(?:주중|주말)\s+하네스\s+작업을\s+하라고\s+하네스에\s+"
        r"지시해(?:\s*줘|\s*주세요)?[.!。\s]*", message,
    )
    imperative = harness_dispatch or re.search(
        r"(?:진행|실행|수집|갱신|업데이트)\s*(?:해(?:\s*줘|\s*주세요|\s*주십시오)?|하라|하세요|한다)[.!。\s]*$",
        message,
    ) or re.match(r"^(?:please\s+)?(?:collect|run|start|update)\b", lowered)
    if not imperative:
        raise ValueError("explicit collection imperative required; statements/questions stay unbound")
    cycle_words = {"weekday": ("주중", "weekday"), "weekend": ("주말", "weekend")}
    if (not any(word in lowered for word in cycle_words[state["cycle_type"]])
            or any(word in lowered for c, words in cycle_words.items() if c != state["cycle_type"] for word in words)
            or not any(word in lowered for word in ("수집", "하네스", "파이프라인", "collect", "harness", "pipeline"))
            or (not harness_dispatch and not any(word in lowered for word in (
                "진행", "실행", "갱신", "업데이트", "collect", "run", "start", "update")))):
        raise ValueError("explicit single-cycle collection instruction required")
    issued = aware(event["timestamp"])
    if issued != aware(command["issued_at"]):
        raise ValueError("command timestamp differs from original event")
    # Undated imperatives use reviewed date context, not a required user phrasing.
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", message)
    korean_dates = re.findall(r"(\d{1,2})월\s*(\d{1,2})일", message)
    if dates or korean_dates:
        if (any(value != data_day.isoformat() for value in dates)
                or any((int(m), int(d)) != (data_day.month, data_day.day) for m, d in korean_dates)):
            raise ValueError("message target differs from collection data_asof")
    review = command.get("operator_review", {})
    if (not review.get("reviewer") or not review.get("basis")
            or any(review.get(k) is not True for k in (
                "direct_user_collection_confirmed", "target_cycle_confirmed",
                "latest_instruction_checked", "not_cancelled_or_superseded"))):
        raise ValueError("operator semantic and latest-instruction review required")
    if not dates and not korean_dates and not any(word in lowered for word in ("오늘", "today")):
        context = review.get("target_date_context", {})
        if (context.get("work_asof") != state["asof"]
                or context.get("data_asof") != command["data_asof"]
                or not isinstance(context.get("basis"), str) or not context["basis"].strip()):
            raise ValueError("undated collection instruction requires reviewed target date context")
    started = aware(state["stages"][0]["started_at"])
    reviewed = aware(review["reviewed_at"])
    if (not issued <= reviewed <= started
            or any(stamp.astimezone(KST).date().isoformat() != state["asof"]
                   for stamp in (issued, reviewed, started))):
        raise ValueError("command/review/start chronology mismatch")
    return command
