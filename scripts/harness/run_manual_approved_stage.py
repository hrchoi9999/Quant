from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from build_execution_approval_trace import build as build_execution_approval_trace
from collect_manual_execution_report import collect as collect_manual_report
from collect_stage_report import render_report
from harness_common import (
    COMMAND_MAPPING_DIR,
    OPERATIONAL_COMMANDS_PATH,
    ROOT,
    bind_command_template,
    command_matches_blocked_pattern,
    command_template_block_reason,
    find_command_entrypoint,
    get_stage_config,
    now_stamp,
    read_json,
    resolve_repo_path,
    risk_policy_allows,
    stage_dir,
    validate_expected_artifacts,
    write_handoff,
    write_json,
)
from resolve_approval_for_execution import approval_row_from_resolution
from resolve_approval_for_execution import resolve as resolve_execution_approval

APPROVED_STATUSES = {"approved", "approved_for_manual_execute", "manual_approved"}
DEFAULT_APPROVAL_SCOPES = {"single_stage_manual_pilot"}
REJECTED_STATUSES = {
    "pending",
    "rejected",
    "blocked",
    "dry_run_only",
    "candidate_found",
    "preflight_required",
    "preflight_failed",
}
DEFAULT_APPROVAL_DIR = ROOT / "reports" / "harness_approval"


def _approval_candidates() -> list[Path]:
    paths = []
    if DEFAULT_APPROVAL_DIR.exists():
        paths.extend(DEFAULT_APPROVAL_DIR.glob("*.json"))
    paths.extend((ROOT / "reports" / "harness_runs").glob("*/manual_approval_packet.json"))
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)


def _approval_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("approvals"), list):
        return [row for row in payload["approvals"] if isinstance(row, dict)]
    if isinstance(payload.get("stages"), list):
        rows = []
        for row in payload["stages"]:
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "stage_id": row.get("stage_id"),
                    "approval_status": row.get("approval_status") or row.get("manual_approval_status") or row.get("command_status"),
                    "approved_by": row.get("approved_by"),
                    "approved_at": row.get("approved_at"),
                    "approval_scope": row.get("approval_scope") or payload.get("approval_scope"),
                    "notes": row.get("notes"),
                }
            )
        return rows
    return []


def find_approval(stage_id: str, approval_file: Path | None) -> tuple[dict[str, Any] | None, Path | None]:
    paths = [approval_file] if approval_file else _approval_candidates()
    for path in [p for p in paths if p is not None]:
        if not path.exists():
            continue
        payload = read_json(path)
        for row in _approval_rows(payload):
            if row.get("stage_id") == stage_id:
                return row, path
    return None, approval_file


def _preflight(stage_id: str) -> dict[str, Any]:
    path = COMMAND_MAPPING_DIR / f"preflight_{stage_id}.json"
    return read_json(path) if path.exists() else {"status": "missing"}


def _block(
    run_id: str,
    stage_id: str,
    config: dict[str, Any],
    reason: str,
    approval: dict[str, Any] | None,
    approval_path: Path | None,
    *,
    execution_type: str = "manual_operational_pilot",
    cycle_execute: bool = False,
    approval_id: str | None = None,
    approval_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir = stage_dir(run_id, stage_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "run_id": run_id,
        "stage_id": stage_id,
        "thread": config.get("thread"),
        "action": config.get("action"),
        "mode": "manual-operational",
        "command": config.get("command"),
        "working_dir": config.get("working_dir"),
        "safe_run": bool(config.get("safe_run")),
        "risk_level": str(config.get("risk_level") or ""),
        "status": "blocked",
        "return_code": None,
        "started_at": None,
        "completed_at": now_stamp(),
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
        "expected_artifacts": list(config.get("expected_artifacts") or []),
        "artifact_validation": {"status": "not_checked", "missing": [], "found": []},
        "error_message": reason,
        "command_template": config.get("command_template") or config.get("command"),
        "command_template_variables": list(config.get("command_template_variables") or []),
        "bound_command_variables": dict(config.get("bound_command_variables") or {}),
        "unresolved_command_variables": list(config.get("unresolved_command_variables") or []),
        "execution_type": execution_type,
        "approval_required": True,
        "approval_status": approval.get("approval_status") if approval else None,
        "approval_file": str(approval_path) if approval_path else None,
        "approval_scope": approval.get("approval_scope") if approval else None,
        "operational_execute": False,
        "cycle_execute": bool(cycle_execute),
        "approval": approval or {},
        "preflight": _preflight(stage_id),
        "approval_id": approval_id,
        "approval_gate_checked": bool(approval_id),
        "approval_gate_status": (approval_resolution or {}).get("gate_status"),
        "execution_approval_resolution_file": (approval_resolution or {}).get("execution_approval_resolution_file"),
        "execution_approval_trace_file": None,
        "approval_based_execution": bool(approval_id),
    }
    (out_dir / "stdout.log").write_text("", encoding="utf-8")
    (out_dir / "stderr.log").write_text(reason + "\n", encoding="utf-8")
    (out_dir / "command.txt").write_text(str(config.get("command") or "") + "\n", encoding="utf-8")
    write_json(out_dir / "result.json", result)
    write_json(out_dir / "manual_execution_blocked.json", result)
    (out_dir / "manual_execution_blocked.md").write_text(
        f"# Manual Execution Blocked\n\n- stage_id: {stage_id}\n- reason: {reason}\n",
        encoding="utf-8",
    )
    collect_manual_report(run_id, stage_id)
    return result


def _write_result_and_reports(run_id: str, stage_id: str, result: dict[str, Any]) -> dict[str, Any]:
    out_dir = stage_dir(run_id, stage_id)
    write_json(out_dir / "result.json", result)
    if result.get("status") == "blocked":
        write_json(out_dir / "manual_execution_blocked.json", result)
    else:
        (out_dir / "stage_report.md").write_text(render_report(result), encoding="utf-8")
    collect_manual_report(run_id, stage_id)
    return result


def _attach_approval_trace(run_id: str, stage_id: str, approval_id: str, result: dict[str, Any]) -> dict[str, Any]:
    trace = build_execution_approval_trace(approval_id, run_id, stage_id)
    result["execution_approval_trace_file"] = trace["execution_approval_trace_json"]
    return _write_result_and_reports(run_id, stage_id, result)


def _validate_execution_allowed(
    stage_id: str,
    config: dict[str, Any],
    approval: dict[str, Any] | None,
    allowed_scopes: set[str] | None = None,
) -> str | None:
    allowed_scopes = allowed_scopes or DEFAULT_APPROVAL_SCOPES
    if approval is None:
        return "approval file missing or approval not found"
    approval_status = str(approval.get("approval_status") or "")
    if approval_status in REJECTED_STATUSES:
        return f"approval rejected: {approval_status}"
    if approval_status not in APPROVED_STATUSES:
        return f"approval not accepted: {approval_status}"
    if approval.get("approval_scope") not in allowed_scopes:
        scopes = ", ".join(sorted(allowed_scopes))
        return f"approval_scope is not allowed ({scopes}): {approval.get('approval_scope')}"
    command = str(config.get("command") or "").strip()
    if not command:
        return "command is empty"
    working_dir = Path(str(config.get("working_dir") or ""))
    if not working_dir.exists():
        return f"working_dir missing: {working_dir}"
    entrypoint = find_command_entrypoint(command, str(working_dir))
    if entrypoint is None or not entrypoint.exists():
        return f"entrypoint missing: {entrypoint}"
    risk_level = str(config.get("risk_level") or "").lower()
    if risk_level not in {"low", "medium", "high"}:
        return f"risk_level is not allowed for manual pilot: {risk_level}"
    if not risk_policy_allows(risk_level, "preflight"):
        return f"risk policy preflight not allowed: {risk_level}"
    blocked = command_matches_blocked_pattern(command)
    if blocked:
        return f"blocked pattern matched: {blocked}"
    preflight = _preflight(stage_id)
    if preflight.get("status") != "passed":
        return f"preflight not passed: {preflight.get('status')}"
    if not preflight.get("thread_root_match", False):
        return "preflight thread root alignment failed"
    if not preflight.get("entrypoint_exists", False):
        return "preflight entrypoint missing"
    return None


def run_manual_stage(
    run_id: str,
    stage_id: str,
    config_path: Path,
    approval_file: Path | None,
    execute: bool,
    *,
    allowed_scopes: set[str] | None = None,
    execution_type: str = "manual_operational_pilot",
    cycle_execute: bool = False,
    approval_id: str | None = None,
    approval_resolution: dict[str, Any] | None = None,
    approval_override: dict[str, Any] | None = None,
    asof: str | None = None,
) -> dict[str, Any]:
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
    approval_path: Path | None = None
    if approval_id:
        approval_resolution = approval_resolution or resolve_execution_approval(
            approval_id,
            "manual_operational_stage_pilot",
            run_id,
            target_stage_id=stage_id,
        )
        if not approval_resolution.get("execution_allowed"):
            result = _block(
                run_id,
                stage_id,
                config,
                str(approval_resolution.get("block_reason") or "approval_gate_not_passed"),
                approval_override,
                approval_path,
                execution_type=execution_type,
                cycle_execute=cycle_execute,
                approval_id=approval_id,
                approval_resolution=approval_resolution,
            )
            return _attach_approval_trace(run_id, stage_id, approval_id, result)
        approval = approval_override or approval_row_from_resolution(approval_resolution)
        approval_path = Path(str(approval_resolution.get("approval_decision_file")))
    else:
        approval, approval_path = find_approval(stage_id, approval_file)
    reason = command_template_block_reason(binding) or _validate_execution_allowed(stage_id, config, approval, allowed_scopes=allowed_scopes)
    if reason:
        result = _block(
            run_id,
            stage_id,
            config,
            reason,
            approval,
            approval_path,
            execution_type=execution_type,
            cycle_execute=cycle_execute,
            approval_id=approval_id,
            approval_resolution=approval_resolution,
        )
        if approval_id:
            return _attach_approval_trace(run_id, stage_id, approval_id, result)
        return result

    out_dir = stage_dir(run_id, stage_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    command = str(config.get("command") or "")
    (out_dir / "command.txt").write_text(command + "\n", encoding="utf-8")
    stdout_path = out_dir / "stdout.log"
    stderr_path = out_dir / "stderr.log"
    started_at = now_stamp() if execute else None
    return_code = None
    status = "manual_dry_run_completed"
    if execute:
        proc = subprocess.run(
            command,
            cwd=str(Path(str(config.get("working_dir")))),
            text=True,
            capture_output=True,
            shell=True,
            check=False,
        )
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
        return_code = int(proc.returncode)
        status = "completed" if proc.returncode == 0 else "failed"
    else:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
    completed_at = now_stamp()
    artifact = validate_expected_artifacts(run_id, stage_id, config)
    write_json(out_dir / "artifact_validation.json", artifact)
    result = {
        "run_id": run_id,
        "stage_id": stage_id,
        "thread": config.get("thread"),
        "action": config.get("action"),
        "mode": "manual-operational",
        "command": command,
        "working_dir": config.get("working_dir"),
        "safe_run": bool(config.get("safe_run")),
        "risk_level": str(config.get("risk_level") or ""),
        "status": status,
        "return_code": return_code,
        "started_at": started_at,
        "completed_at": completed_at,
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
        "expected_artifacts": list(config.get("expected_artifacts") or []),
        "artifact_validation": {
            "status": artifact["status"],
            "missing": artifact["missing"],
            "found": artifact["found"],
        },
        "error_message": None if status in {"completed", "manual_dry_run_completed"} else f"command failed with return_code={return_code}",
        "command_template": config.get("command_template"),
        "command_template_variables": config.get("command_template_variables"),
        "bound_command_variables": config.get("bound_command_variables"),
        "unresolved_command_variables": config.get("unresolved_command_variables"),
        "execution_type": execution_type,
        "approval_required": True,
        "approval_status": approval.get("approval_status"),
        "approval_file": str(approval_path),
        "approval_scope": approval.get("approval_scope"),
        "operational_execute": bool(execute),
        "cycle_execute": bool(cycle_execute),
        "approval": approval,
        "preflight": _preflight(stage_id),
        "approval_id": approval_id,
        "approval_gate_checked": bool(approval_id),
        "approval_gate_status": (approval_resolution or {}).get("gate_status"),
        "execution_approval_resolution_file": (approval_resolution or {}).get("execution_approval_resolution_file"),
        "execution_approval_trace_file": None,
        "approval_based_execution": bool(approval_id),
    }
    write_json(out_dir / "result.json", result)
    (out_dir / "stage_report.md").write_text(render_report(result), encoding="utf-8")
    write_handoff(
        out_dir,
        result,
        [
            "command.txt",
            "stdout.log",
            "stderr.log",
            "result.json",
            "artifact_validation.json",
            "stage_report.md",
            "manual_execution_report.md",
        ],
    )
    collect_manual_report(run_id, stage_id)
    if approval_id:
        return _attach_approval_trace(run_id, stage_id, approval_id, result)
    return result


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run one manually approved operational stage pilot.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage-id", required=True)
    ap.add_argument("--config", default=str(OPERATIONAL_COMMANDS_PATH))
    ap.add_argument("--approval-file", default=None)
    ap.add_argument("--approval-id", default=None)
    ap.add_argument("--asof", default=None, help="Bind {asof} in configured command templates.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = run_manual_stage(
        args.run_id,
        args.stage_id,
        resolve_repo_path(args.config),
        resolve_repo_path(args.approval_file) if args.approval_file else None,
        execute=bool(args.execute),
        approval_id=args.approval_id,
        asof=args.asof,
    )
    print(json.dumps({"status": result["status"], "run_id": args.run_id, "stage_id": args.stage_id}, ensure_ascii=False, indent=2))
    if result["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
