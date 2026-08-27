from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_execution_approval_trace import build as build_execution_approval_trace
from collect_manual_cycle_report import collect as collect_manual_cycle_report
from cycle_common import is_close_stage, run_dir, stage_dir, state_path, write_cycle_state
from harness_common import OPERATIONAL_COMMANDS_PATH, now_stamp, read_json, resolve_repo_path, write_json
from resolve_approval_for_execution import resolve as resolve_execution_approval
from run_manual_approved_stage import run_manual_stage
from validate_cycle_approval import CYCLE_APPROVAL_SCOPES, approval_file_from_approval_id, validate_cycle_approval


def _write_dry_run(run_id: str, cycle_type: str, approval_payload: dict[str, Any]) -> None:
    out_dir = run_dir(run_id)
    rows = approval_payload["stage_results"]
    payload = {
        "run_id": run_id,
        "cycle_type": cycle_type,
        "status": approval_payload["status"],
        "approval_file": approval_payload["approval_file"],
        "generated_at": now_stamp(),
        "stage_results": rows,
    }
    write_json(out_dir / "manual_cycle_dry_run.json", payload)
    lines = [
        "# Manual Cycle Dry Run",
        "",
        f"- run_id: {run_id}",
        f"- cycle_type: {cycle_type}",
        f"- status: {payload['status']}",
        f"- approval_file: {payload['approval_file']}",
        "",
        "| order | stage_id | selected | validation | issues |",
        "|---:|---|---|---|---|",
    ]
    for row in rows:
        issues = ", ".join(row.get("issues") or []) or "none"
        lines.append(f"| {row.get('order')} | {row.get('stage_id')} | {row.get('selected_for_execution')} | {row.get('validation_status')} | {issues} |")
    (out_dir / "manual_cycle_dry_run.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _initial_state(run_id: str, cycle_type: str, mode: str, approval_payload: dict[str, Any], *, status: str) -> dict[str, Any]:
    approval_scope = next(
        (
            row.get("approval_scope")
            for row in approval_payload["stage_results"]
            if row.get("approval_scope") in CYCLE_APPROVAL_SCOPES
        ),
        "manual_operational_cycle_pilot",
    )
    return {
        "run_id": run_id,
        "cycle_type": cycle_type,
        "mode": mode,
        "config": str(OPERATIONAL_COMMANDS_PATH),
        "status": status,
        "started_at": now_stamp(),
        "completed_at": None,
        "current_stage": None,
        "execution_type": "manual_operational_cycle_pilot",
        "approval_file": approval_payload["approval_file"],
        "approval_scope": approval_scope,
        "cycle_execute": mode == "execute",
        "auto_approval": False,
        "agent_decision": False,
        "manual_cycle_approval_status": approval_payload["status"],
        "stages": [
            {
                "stage_id": row["stage_id"],
                "order": row["order"],
                "thread": row.get("thread"),
                "action": row.get("action"),
                "command": row.get("command"),
                "required": row.get("required"),
                "selected_for_execution": row.get("selected_for_execution"),
                "approval_status": row.get("approval_status"),
                "approval_scope": row.get("approval_scope"),
                "approval": row.get("approval") or {},
                "validation_status": row.get("validation_status"),
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "result_file": None,
                "stage_report_file": None,
                "manual_execution_report_file": None,
                "handoff_file": None,
                "error_message": None,
            }
            for row in approval_payload["stage_results"]
        ],
        "stop_reason": None,
        "manual_cycle_report_file": None,
        "final_summary_file": None,
    }


def _attach_approval_state(state: dict[str, Any], approval_id: str | None, resolution: dict[str, Any] | None) -> dict[str, Any]:
    state["approval_id"] = approval_id
    state["approval_gate_checked"] = bool(approval_id)
    state["approval_gate_status"] = (resolution or {}).get("gate_status")
    state["approval_based_execution"] = bool(approval_id)
    state["execution_approval_resolution_file"] = (resolution or {}).get("execution_approval_resolution_file")
    state["execution_approval_trace_file"] = None
    return state


def _write_cycle_block(run_id: str, state: dict[str, Any], reason: str, approval_id: str | None = None) -> dict[str, Any]:
    out = run_dir(run_id)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": run_id, "status": "blocked", "reason": reason, "approval_id": approval_id, "completed_at": now_stamp()}
    write_json(out / "manual_cycle_execution_blocked.json", payload)
    (out / "manual_cycle_execution_blocked.md").write_text(f"# Manual Cycle Execution Blocked\n\n- reason: {reason}\n", encoding="utf-8")
    state["status"] = "blocked"
    state["stop_reason"] = reason
    state["completed_at"] = now_stamp()
    for row in state.get("stages") or []:
        if row.get("status") == "pending":
            row["status"] = "skipped"
            row["error_message"] = reason
    write_cycle_state(state)
    if approval_id:
        trace = build_execution_approval_trace(approval_id, run_id)
        state["execution_approval_trace_file"] = trace["execution_approval_trace_json"]
        write_cycle_state(state)
    collect_manual_cycle_report(run_id)
    return {"status": "blocked", "cycle_state": str(state_path(run_id))}


def _update_stage(state: dict[str, Any], stage_id: str, **updates: Any) -> None:
    for row in state["stages"]:
        if row["stage_id"] == stage_id:
            row.update(updates)
            return
    raise SystemExit(f"stage not found in state: {stage_id}")


def _skip_after_stop(state: dict[str, Any], stop_stage_id: str) -> None:
    seen = False
    for row in state["stages"]:
        if row["stage_id"] == stop_stage_id:
            seen = True
            continue
        if seen and row["status"] == "pending":
            row["status"] = "skipped"
            row["error_message"] = "skipped after prior stage stopped cycle"


def _stage_paths(run_id: str, stage_id: str) -> dict[str, str]:
    path = stage_dir(run_id, stage_id)
    return {
        "result_file": str(path / "result.json"),
        "stage_report_file": str(path / "stage_report.md"),
        "manual_execution_report_file": str(path / "manual_execution_report.md"),
        "handoff_file": str(path / "handoff.md"),
    }


def run_manual_cycle(
    run_id: str,
    cycle_type: str,
    approval_file: Path | None,
    *,
    execute: bool,
    approval_id: str | None = None,
    asof: str | None = None,
) -> dict[str, Any]:
    approval_resolution = None
    if approval_id:
        execution_type = "manual_operational_cycle_pilot" if execute else "manual_operational_cycle_dry_run"
        approval_resolution = resolve_execution_approval(
            approval_id,
            execution_type,
            run_id,
            target_cycle_type=cycle_type,
        )
        approval_file = approval_file_from_approval_id(approval_id, run_id, cycle_type)
    elif approval_file is None:
        raise SystemExit("--approval-file or --approval-id is required")

    approval_payload = validate_cycle_approval(run_id, cycle_type, approval_file, asof=asof)
    mode = "execute" if execute else "dry-run"
    state = _initial_state(run_id, cycle_type, mode, approval_payload, status="running")
    state["asof"] = asof
    _attach_approval_state(state, approval_id, approval_resolution)
    write_cycle_state(state)

    if approval_id and not approval_resolution.get("execution_allowed"):
        return _write_cycle_block(run_id, state, str(approval_resolution.get("block_reason") or "approval_gate_not_passed"), approval_id)

    if not execute:
        _write_dry_run(run_id, cycle_type, approval_payload)
        for row in state["stages"]:
            row["status"] = "approved" if row.get("validation_status") == "approved" else row.get("validation_status")
            row["completed_at"] = now_stamp()
        state["status"] = approval_payload["status"]
        state["completed_at"] = now_stamp()
        write_cycle_state(state)
        collect_manual_cycle_report(run_id)
        if approval_id:
            trace = build_execution_approval_trace(approval_id, run_id)
            state["execution_approval_trace_file"] = trace["execution_approval_trace_json"]
            write_cycle_state(state)
            collect_manual_cycle_report(run_id)
        return {"status": state["status"], "cycle_state": str(state_path(run_id))}

    if approval_payload["status"] != "approved_for_manual_cycle":
        state["status"] = approval_payload["status"]
        state["stop_reason"] = f"manual cycle approval validation status={approval_payload['status']}"
        state["completed_at"] = now_stamp()
        for row in state["stages"]:
            row["status"] = "skipped"
            row["error_message"] = state["stop_reason"]
        write_cycle_state(state)
        collect_manual_cycle_report(run_id)
        if approval_id:
            trace = build_execution_approval_trace(approval_id, run_id)
            state["execution_approval_trace_file"] = trace["execution_approval_trace_json"]
            write_cycle_state(state)
        return {"status": state["status"], "cycle_state": str(state_path(run_id))}

    for row in approval_payload["stage_results"]:
        stage_id = str(row["stage_id"])
        state["current_stage"] = stage_id
        if is_close_stage(stage_id):
            _update_stage(state, stage_id, status="completed", started_at=now_stamp(), completed_at=now_stamp())
            state["status"] = "completed"
            state["completed_at"] = now_stamp()
            write_cycle_state(state)
            collect_manual_cycle_report(run_id)
            break
        if row.get("validation_status") == "skipped_deferred":
            _update_stage(
                state,
                stage_id,
                status="skipped_deferred",
                completed_at=now_stamp(),
                error_message="optional/deferred stage without cycle approval",
            )
            write_cycle_state(state)
            continue
        if not row.get("selected_for_execution"):
            _update_stage(state, stage_id, status="skipped", completed_at=now_stamp(), error_message="stage not selected for execution")
            write_cycle_state(state)
            continue

        _update_stage(state, stage_id, status="running", started_at=now_stamp())
        write_cycle_state(state)
        result = run_manual_stage(
            run_id,
            stage_id,
            OPERATIONAL_COMMANDS_PATH,
            resolve_repo_path(approval_file),
            execute=True,
            allowed_scopes=CYCLE_APPROVAL_SCOPES,
            execution_type="manual_operational_cycle_pilot",
            cycle_execute=True,
            approval_id=approval_id,
            approval_resolution=approval_resolution,
            approval_override={
                "stage_id": stage_id,
                "approval_status": "approved",
                "approval_scope": "manual_operational_cycle_pilot",
                "approved_by": "approval_harness",
                "approved_at": (approval_resolution or {}).get("resolved_at"),
                "notes": f"approval_id={approval_id}",
            }
            if approval_id
            else None,
            asof=asof,
        )
        status = str(result.get("status"))
        _update_stage(
            state,
            stage_id,
            status=status,
            completed_at=now_stamp(),
            error_message=result.get("error_message"),
            **_stage_paths(run_id, stage_id),
        )
        if status in {"failed", "blocked"}:
            state["status"] = status
            state["stop_reason"] = result.get("error_message") or f"stage stopped cycle with status={status}"
            state["completed_at"] = now_stamp()
            _skip_after_stop(state, stage_id)
            write_cycle_state(state)
            collect_manual_cycle_report(run_id)
            if approval_id:
                trace = build_execution_approval_trace(approval_id, run_id)
                state["execution_approval_trace_file"] = trace["execution_approval_trace_json"]
                write_cycle_state(state)
            break
        write_cycle_state(state)

    if approval_id:
        trace = build_execution_approval_trace(approval_id, run_id)
        state = read_json(state_path(run_id))
        state["execution_approval_trace_file"] = trace["execution_approval_trace_json"]
        write_cycle_state(state)
    return {"status": read_json(state_path(run_id))["status"], "cycle_state": str(state_path(run_id))}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run one manually approved operational cycle pilot.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cycle-type", choices=["weekday", "weekend"], required=True)
    ap.add_argument("--approval-file", default=None)
    ap.add_argument("--approval-id", default=None)
    ap.add_argument("--asof", default=None, help="Bind {asof} in configured command templates.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = run_manual_cycle(
        args.run_id,
        args.cycle_type,
        resolve_repo_path(args.approval_file) if args.approval_file else None,
        execute=bool(args.execute),
        approval_id=args.approval_id,
        asof=args.asof,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.execute and result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
