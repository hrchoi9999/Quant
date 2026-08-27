from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_common import (
    COMMAND_MAPPING_DIR,
    OPERATIONAL_COMMANDS_PATH,
    bind_command_template,
    command_matches_blocked_pattern,
    command_template_block_reason,
    find_command_entrypoint,
    get_stage_config,
    load_risk_policy,
    resolve_artifact,
    resolve_repo_path,
    risk_policy_allows,
    thread_root,
    write_json,
)

VALID_PREFLIGHT_STATUSES = {"candidate_found", "preflight_required", "preflight_passed", "manual_prompt_only"}


def preflight(stage_id: str, config_path: Path, *, asof: str | None = None) -> dict[str, Any]:
    config = get_stage_config(stage_id, config_path)
    binding = bind_command_template(str(config.get("command") or "").strip(), {"asof": asof})
    command = str(binding["command"]).strip()
    working_dir = str(config.get("working_dir") or "")
    thread = str(config.get("thread") or "")
    expected_thread_root = thread_root(thread)
    risk_level = str(config.get("risk_level") or "").lower()
    command_status = str(config.get("command_status") or "")
    policy = load_risk_policy()
    blocked_pattern = command_matches_blocked_pattern(command, policy) if command else None
    entrypoint = find_command_entrypoint(command, working_dir=working_dir) if command else None
    expected = list(config.get("expected_artifacts") or [])
    artifact_paths = [str(resolve_artifact(str(item), working_dir=working_dir)) for item in expected]
    execute_allowed = (
        bool(config.get("safe_run"))
        and risk_level in {"low", "medium"}
        and command_status == "approved_for_harness_execute"
        and blocked_pattern is None
    )
    execute_block_reason = None if execute_allowed else "safe_run_false_or_not_approved_for_harness_execute"

    checks = {
        "command_present": bool(command),
        "working_dir_exists": bool(working_dir) and Path(working_dir).exists(),
        "thread_root_match": expected_thread_root is not None and Path(working_dir) == expected_thread_root,
        "entrypoint_exists": entrypoint is not None and entrypoint.exists(),
        "blocked_pattern": blocked_pattern is not None,
        "risk_policy_allows_preflight": risk_policy_allows(risk_level, "preflight", policy),
        "expected_artifacts_resolved": True,
        "command_status_valid": command_status in VALID_PREFLIGHT_STATUSES,
    }
    notes: list[str] = []
    if not checks["command_present"]:
        notes.append("command is not registered")
    if command_status == "manual_prompt_only":
        notes.append("stage is manual_prompt_only; use prompt handoff instead of command harness")
    template_reason = command_template_block_reason(binding)
    if template_reason:
        notes.append(template_reason)
    if not checks["working_dir_exists"]:
        notes.append(f"working_dir missing: {working_dir}")
    if not checks["thread_root_match"]:
        notes.append(f"working_dir does not match thread root: thread={thread} root={expected_thread_root} working_dir={working_dir}")
    if command and entrypoint is None:
        notes.append("python entrypoint not detected")
    elif entrypoint is not None and not entrypoint.exists():
        notes.append(f"python entrypoint missing: {entrypoint}")
    if blocked_pattern:
        notes.append(f"blocked pattern matched: {blocked_pattern}")
    if not checks["risk_policy_allows_preflight"]:
        notes.append(f"risk policy does not allow preflight for risk_level={risk_level}")
    if not checks["command_status_valid"]:
        notes.append(f"command_status is not valid for preflight: {command_status}")
    if not execute_allowed:
        notes.append(f"execute is not allowed: {execute_block_reason}")

    passed = (
        checks["command_present"]
        and template_reason is None
        and checks["working_dir_exists"]
        and checks["thread_root_match"]
        and checks["entrypoint_exists"]
        and not checks["blocked_pattern"]
        and checks["risk_policy_allows_preflight"]
        and checks["expected_artifacts_resolved"]
        and checks["command_status_valid"]
    )
    return {
        "stage_id": stage_id,
        "command": command or None,
        "command_template": binding["command_template"],
        "command_template_variables": binding["template_variables"],
        "bound_command_variables": binding["bound_variables"],
        "unresolved_command_variables": binding["unresolved_variables"],
        "status": "passed" if passed else "failed",
        "thread": thread,
        "thread_root": str(expected_thread_root) if expected_thread_root else None,
        "risk_level": risk_level,
        "safe_run": bool(config.get("safe_run")),
        "command_status": command_status,
        "blocked": bool(blocked_pattern),
        "thread_root_match": checks["thread_root_match"],
        "entrypoint_exists": checks["entrypoint_exists"],
        "working_dir_exists": checks["working_dir_exists"],
        "command_registered": checks["command_present"],
        "execute_allowed": execute_allowed,
        "execute_block_reason": execute_block_reason,
        "checks": checks,
        "entrypoint": str(entrypoint) if entrypoint else None,
        "expected_artifacts": expected,
        "resolved_expected_artifacts": artifact_paths,
        "notes": notes,
    }


def render_markdown(result: dict[str, Any]) -> str:
    checks = result["checks"]
    lines = [
        f"# Preflight {result['stage_id']}",
        "",
        f"- status: {result['status']}",
        f"- risk_level: {result['risk_level']}",
        f"- safe_run: {result['safe_run']}",
        f"- command_status: {result.get('command_status')}",
        f"- blocked: {result['blocked']}",
        f"- execute_allowed: {result['execute_allowed']}",
        f"- execute_block_reason: {result.get('execute_block_reason')}",
        "",
        "## Command",
        "```text",
        str(result.get("command") or ""),
        "```",
        "",
        "## Checks",
    ]
    lines.extend(f"- {key}: {value}" for key, value in checks.items())
    lines.extend(["", "## Notes"])
    notes = result.get("notes") or []
    lines.extend([f"- {note}" for note in notes] if notes else ["- none"])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Preflight an operational stage command without executing it.")
    ap.add_argument("--stage-id", required=True)
    ap.add_argument("--config", default=str(OPERATIONAL_COMMANDS_PATH))
    ap.add_argument("--asof", default=None, help="Bind {asof} in configured command templates.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = preflight(args.stage_id, resolve_repo_path(args.config), asof=args.asof)
    COMMAND_MAPPING_DIR.mkdir(parents=True, exist_ok=True)
    json_path = COMMAND_MAPPING_DIR / f"preflight_{args.stage_id}.json"
    md_path = COMMAND_MAPPING_DIR / f"preflight_{args.stage_id}.md"
    write_json(json_path, result)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
