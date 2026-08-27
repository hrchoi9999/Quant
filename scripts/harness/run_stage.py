from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

from harness_common import (
    ALLOWED_EXECUTE_RISK,
    BLOCKED_RISK,
    COMMANDS_PATH,
    ROOT,
    bind_command_template,
    command_matches_blocked_pattern,
    command_template_block_reason,
    get_stage_config,
    now_stamp,
    resolve_repo_path,
    stage_dir,
    update_run_state_if_exists,
    validate_expected_artifacts,
    write_handoff,
    write_json,
)


def block_result(run_id: str, stage_id: str, config: dict[str, Any], reason: str, mode: str) -> dict[str, Any]:
    return base_result(run_id, stage_id, config, mode) | {
        "status": "blocked",
        "error_message": reason,
    }


def base_result(run_id: str, stage_id: str, config: dict[str, Any], mode: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "stage_id": stage_id,
        "thread": config.get("thread"),
        "action": config.get("action"),
        "mode": mode,
        "command": config.get("command"),
        "working_dir": config.get("working_dir"),
        "safe_run": bool(config.get("safe_run")),
        "risk_level": str(config.get("risk_level") or ""),
        "command_status": config.get("command_status"),
        "status": "dry_run_completed" if mode == "dry-run" else "completed",
        "return_code": None,
        "started_at": None,
        "completed_at": None,
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
        "expected_artifacts": list(config.get("expected_artifacts") or []),
        "artifact_validation": {
            "status": "not_checked",
            "missing": [],
            "found": [],
        },
        "error_message": None,
        "command_template": config.get("command_template") or config.get("command"),
        "command_template_variables": list(config.get("command_template_variables") or []),
        "bound_command_variables": dict(config.get("bound_command_variables") or {}),
        "unresolved_command_variables": list(config.get("unresolved_command_variables") or []),
    }


def execution_block_reason(config: dict[str, Any]) -> str | None:
    command = str(config.get("command") or "").strip()
    risk_level = str(config.get("risk_level") or "").lower()
    command_status = config.get("command_status")
    if command_status == "manual_prompt_only":
        return "stage is manual_prompt_only"
    if not command:
        return "command is empty"
    blocked_pattern = command_matches_blocked_pattern(command)
    if blocked_pattern:
        return f"blocked pattern matched: {blocked_pattern}"
    if not bool(config.get("safe_run")):
        return "safe_run is false"
    if risk_level in BLOCKED_RISK:
        return f"risk_level is blocked: {risk_level}"
    if risk_level not in ALLOWED_EXECUTE_RISK:
        return f"risk_level is not allowed for execute: {risk_level}"
    if command_status is not None and command_status != "approved_for_harness_execute":
        return f"command_status is not approved for harness execute: {command_status}"
    return None


def run_stage(run_id: str, stage_id: str, execute: bool, config_path: Path = COMMANDS_PATH, *, asof: str | None = None) -> dict[str, Any]:
    config = get_stage_config(stage_id, config_path)
    binding = bind_command_template(str(config.get("command") or ""), {"asof": asof})
    config = {
        **config,
        "command_template": binding["command_template"],
        "command": binding["command"],
        "command_template_variables": binding["template_variables"],
        "bound_command_variables": binding["bound_variables"],
        "unresolved_command_variables": binding["unresolved_variables"],
    }
    mode = "execute" if execute else "dry-run"
    out_dir = stage_dir(run_id, stage_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    command = str(config.get("command") or "")
    (out_dir / "command.txt").write_text(command + "\n", encoding="utf-8")
    stdout_path = out_dir / "stdout.log"
    stderr_path = out_dir / "stderr.log"

    template_reason = command_template_block_reason(binding)
    if template_reason:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(template_reason + "\n", encoding="utf-8")
        result = block_result(run_id, stage_id, config, template_reason, mode)
    elif not execute:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        result = base_result(run_id, stage_id, config, mode)
    else:
        reason = execution_block_reason(config)
        if reason is not None:
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(reason + "\n", encoding="utf-8")
            result = block_result(run_id, stage_id, config, reason, mode)
        else:
            started_at = now_stamp()
            proc = subprocess.run(
                command,
                cwd=str(Path(str(config.get("working_dir") or ROOT))),
                text=True,
                capture_output=True,
                shell=True,
                check=False,
            )
            completed_at = now_stamp()
            stdout_path.write_text(proc.stdout or "", encoding="utf-8")
            stderr_path.write_text(proc.stderr or "", encoding="utf-8")
            result = base_result(run_id, stage_id, config, mode)
            result["return_code"] = int(proc.returncode)
            result["started_at"] = started_at
            result["completed_at"] = completed_at
            result["status"] = "completed" if proc.returncode == 0 else "failed"
            if proc.returncode != 0:
                result["error_message"] = f"command failed with return_code={proc.returncode}"

    artifact_validation = validate_expected_artifacts(run_id, stage_id, config)
    result["artifact_validation"] = {
        "status": artifact_validation["status"],
        "missing": artifact_validation["missing"],
        "found": artifact_validation["found"],
    }
    write_json(out_dir / "artifact_validation.json", artifact_validation)
    write_json(out_dir / "result.json", result)
    output_files = ["command.txt", "stdout.log", "stderr.log", "result.json", "artifact_validation.json"]
    handoff_path = write_handoff(out_dir, result, output_files)
    update_run_state_if_exists(run_id, stage_id, result, str(handoff_path))
    return result | {"result_path": str(out_dir / "result.json"), "handoff_path": str(handoff_path)}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run or dry-run a configured update harness stage.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage-id", required=True)
    ap.add_argument("--config", default=str(COMMANDS_PATH), help="Stage command yaml. Defaults to safe placeholder config.")
    ap.add_argument("--asof", default=None, help="Bind {asof} in configured command templates.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Render command and result without execution. Default.")
    mode.add_argument("--execute", action="store_true", help="Execute only when safe_run=true and risk_level is low/medium.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = run_stage(args.run_id, args.stage_id, execute=bool(args.execute), config_path=resolve_repo_path(args.config), asof=args.asof)
    write_json(Path(str(result["result_path"])), {k: v for k, v in result.items() if k not in {"result_path", "handoff_path"}})
    print(f"status={result['status']} result={result['result_path']} handoff={result['handoff_path']}")


if __name__ == "__main__":
    main()
