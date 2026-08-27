from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_approval_request import approval_dir
from cycle_common import is_close_stage, run_dir, stage_plan_rows
from harness_common import (
    COMMAND_MAPPING_DIR,
    OPERATIONAL_COMMANDS_PATH,
    bind_command_template,
    command_matches_blocked_pattern,
    command_template_block_reason,
    find_command_entrypoint,
    now_stamp,
    read_json,
    resolve_repo_path,
    write_json,
)
from run_manual_approved_stage import APPROVED_STATUSES, REJECTED_STATUSES, find_approval

CYCLE_APPROVAL_SCOPES = {
    "manual_operational_cycle_dry_run",
    "manual_operational_cycle_pilot",
    "first_real_weekday_pilot",
    "first_full_weekday_pilot",
    "cycle_manual_execute",
    "approved_for_manual_cycle",
}
REQUIRED_STAGES = {
    "weekday": {
        "WD01_QUANT_FRONT",
        "WD02_MARKET_COLLECT",
        "WD03_MARKET_ANALYSIS",
        "WD04_QUANT_REAR",
        "WD05_PORTFOLIO_ANALYSIS",
        "WD06_PRE_GCS_PUBLISH",
    },
    "weekend": {
        "WE01_QUANT_WEEKEND_PIPELINE",
    },
}
OPTIONAL_DEFERRED_STAGES: set[str] = set()


def preflight_for_stage(stage_id: str) -> dict[str, Any]:
    path = COMMAND_MAPPING_DIR / f"preflight_{stage_id}.json"
    return read_json(path) if path.exists() else {"status": "missing"}


def approval_is_cycle_scoped(approval: dict[str, Any] | None) -> bool:
    if not approval:
        return False
    status = str(approval.get("approval_status") or "")
    scope = str(approval.get("approval_scope") or "")
    return status in APPROVED_STATUSES and scope in CYCLE_APPROVAL_SCOPES


def _approval_issue(approval: dict[str, Any] | None) -> str | None:
    if not approval:
        return "approval_missing"
    status = str(approval.get("approval_status") or "")
    scope = str(approval.get("approval_scope") or "")
    if status in REJECTED_STATUSES:
        return f"approval_rejected:{status}"
    if status not in APPROVED_STATUSES:
        return f"approval_not_accepted:{status}"
    if scope not in CYCLE_APPROVAL_SCOPES:
        return f"approval_scope_not_allowed:{scope}"
    return None


def validate_stage_for_cycle(
    run_id: str,
    cycle_type: str,
    row: dict[str, Any],
    approval_file: Path,
    *,
    asof: str | None = None,
) -> dict[str, Any]:
    stage_id = str(row["stage_id"])
    required = stage_id in REQUIRED_STAGES[cycle_type]
    optional_deferred = stage_id in OPTIONAL_DEFERRED_STAGES
    if is_close_stage(stage_id):
        return {
            **row,
            "required": False,
            "selected_for_execution": True,
            "approval": {},
            "approval_status": "not_required",
            "approval_scope": "not_required",
            "validation_status": "approved",
            "result": "close_stage",
            "issues": [],
            "preflight": {"status": "not_required"},
        }

    approval, approval_path = find_approval(stage_id, approval_file)
    approved = approval_is_cycle_scoped(approval)
    issues: list[str] = []
    approval_issue = _approval_issue(approval)

    if approval_issue:
        issues.append(approval_issue)

    if optional_deferred and not approved:
        return {
            **row,
            "required": required,
            "selected_for_execution": False,
            "approval": approval or {},
            "approval_file": str(approval_path) if approval_path else str(approval_file),
            "approval_status": approval.get("approval_status") if approval else None,
            "approval_scope": approval.get("approval_scope") if approval else None,
            "validation_status": "skipped_deferred",
            "result": "optional_deferred_without_cycle_approval",
            "issues": issues,
            "preflight": preflight_for_stage(stage_id),
        }

    binding = bind_command_template(str(row.get("command") or "").strip(), {"asof": asof})
    command = str(binding["command"]).strip()
    row = {
        **row,
        "command_template": binding["command_template"],
        "command": command,
        "command_template_variables": binding["template_variables"],
        "bound_command_variables": binding["bound_variables"],
        "unresolved_command_variables": binding["unresolved_variables"],
    }
    working_dir = Path(str(row.get("working_dir") or ""))
    risk_level = str(row.get("risk_level") or "").lower()
    preflight = preflight_for_stage(stage_id)
    blocked_pattern = command_matches_blocked_pattern(command) if command else None
    entrypoint = find_command_entrypoint(command, str(working_dir)) if command else None

    if not command:
        issues.append("command_not_registered")
    template_issue = command_template_block_reason(binding)
    if template_issue:
        issues.append(template_issue)
    if not working_dir.exists():
        issues.append(f"working_dir_missing:{working_dir}")
    if entrypoint is None:
        issues.append("entrypoint_not_detected")
    elif not entrypoint.exists():
        issues.append(f"entrypoint_missing:{entrypoint}")
    if preflight.get("status") != "passed":
        issues.append(f"preflight_not_passed:{preflight.get('status')}")
    if preflight.get("thread_root_match") is False:
        issues.append("thread_root_alignment_failed")
    if preflight.get("entrypoint_exists") is False:
        issues.append("preflight_entrypoint_missing")
    if risk_level in {"critical"}:
        issues.append(f"blocked_risk_level:{risk_level}")
    if blocked_pattern:
        issues.append(f"blocked_pattern:{blocked_pattern}")

    selected = approved and (required or optional_deferred)
    if any(issue.startswith(("blocked_risk_level:", "blocked_pattern:")) for issue in issues):
        validation_status = "blocked"
    elif any(
        issue.startswith(("command_", "working_dir_", "entrypoint_", "preflight_", "thread_root_", "unresolved command template"))
        for issue in issues
    ):
        validation_status = "not_ready"
    elif approved:
        validation_status = "approved"
    else:
        validation_status = "not_approved"

    return {
        **row,
        "required": required,
        "selected_for_execution": bool(selected and validation_status == "approved"),
        "approval": approval or {},
        "approval_file": str(approval_path) if approval_path else str(approval_file),
        "approval_status": approval.get("approval_status") if approval else None,
        "approval_scope": approval.get("approval_scope") if approval else None,
        "effective_command_status": approval.get("approval_status") if approval else row.get("command_status"),
        "validation_status": validation_status,
        "result": validation_status,
        "issues": issues,
        "preflight": preflight,
        "entrypoint": str(entrypoint) if entrypoint else None,
        "blocked_pattern": blocked_pattern,
    }


def overall_status(cycle_type: str, stage_results: list[dict[str, Any]]) -> str:
    blocking = [row for row in stage_results if row.get("required") and row.get("validation_status") == "blocked"]
    selected_blocking = [
        row
        for row in stage_results
        if row.get("approval_status") in APPROVED_STATUSES
        and row.get("approval_scope") in CYCLE_APPROVAL_SCOPES
        and row.get("validation_status") == "blocked"
    ]
    not_ready = [row for row in stage_results if row.get("required") and row.get("validation_status") == "not_ready"]
    selected_not_ready = [row for row in stage_results if row.get("selected_for_execution") and row.get("validation_status") == "not_ready"]
    required = [row for row in stage_results if row.get("required")]
    required_approved = [row for row in required if row.get("validation_status") == "approved"]
    if blocking or selected_blocking:
        return "blocked"
    if not_ready or selected_not_ready:
        return "not_ready"
    if len(required_approved) == len(REQUIRED_STAGES[cycle_type]):
        return "approved_for_manual_cycle"
    return "partial_approval_only"


def render_cycle_approval(payload: dict[str, Any]) -> str:
    lines = [
        "# Manual Cycle Approval Validation",
        "",
        f"- run_id: {payload['run_id']}",
        f"- cycle_type: {payload['cycle_type']}",
        f"- status: {payload['status']}",
        f"- approval_file: {payload['approval_file']}",
        f"- generated_at: {payload['generated_at']}",
        "",
        "| order | stage_id | required | selected | approval_status | approval_scope | validation | issues |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for row in payload["stage_results"]:
        issues = ", ".join(row.get("issues") or []) or "none"
        lines.append(
            f"| {row.get('order')} | {row.get('stage_id')} | {row.get('required')} | "
            f"{row.get('selected_for_execution')} | {row.get('approval_status')} | {row.get('approval_scope')} | "
            f"{row.get('validation_status')} | {issues} |"
        )
    return "\n".join(lines) + "\n"


def validate_cycle_approval(run_id: str, cycle_type: str, approval_file: Path, *, asof: str | None = None) -> dict[str, Any]:
    approval_file = resolve_repo_path(approval_file)
    rows = stage_plan_rows(cycle_type, OPERATIONAL_COMMANDS_PATH)
    stage_results = [validate_stage_for_cycle(run_id, cycle_type, row, approval_file, asof=asof) for row in rows]
    payload = {
        "run_id": run_id,
        "cycle_type": cycle_type,
        "approval_file": str(approval_file),
        "approval_scopes_allowed": sorted(CYCLE_APPROVAL_SCOPES),
        "asof": asof,
        "required_stages": sorted(REQUIRED_STAGES[cycle_type]),
        "status": overall_status(cycle_type, stage_results),
        "generated_at": now_stamp(),
        "stage_results": stage_results,
    }
    out_dir = run_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "manual_cycle_approval.json", payload)
    (out_dir / "manual_cycle_approval.md").write_text(render_cycle_approval(payload), encoding="utf-8")
    return payload


def approval_file_from_approval_id(approval_id: str, run_id: str, cycle_type: str) -> Path:
    out = approval_dir(approval_id)
    request_path = out / "approval_request.json"
    decision_path = out / "approval_decision.json"
    request = read_json(request_path) if request_path.exists() else {}
    decision = read_json(decision_path) if decision_path.exists() else {}
    approvals = []
    if (
        request.get("target_run_id") == run_id
        and request.get("target_cycle_type") == cycle_type
        and decision.get("decision") == "approved"
        and request.get("approval_scope") in CYCLE_APPROVAL_SCOPES
    ):
        approvals = [
            {
                "stage_id": stage_id,
                "approval_status": "approved",
                "approval_scope": request.get("approval_scope"),
                "approved_by": decision.get("decided_by"),
                "approved_at": decision.get("decided_at"),
                "notes": f"approval_id={approval_id}",
            }
            for stage_id in request.get("target_stage_ids") or []
        ]
    compat_path = out / "approval_execution_compat.json"
    write_json(compat_path, {"approvals": approvals, "source_approval_id": approval_id})
    return compat_path


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate manual approval for one operational cycle pilot.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cycle-type", choices=["weekday", "weekend"], required=True)
    ap.add_argument("--approval-file", default=None)
    ap.add_argument("--approval-id", default=None)
    ap.add_argument("--asof", default=None, help="Bind {asof} in configured command templates.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.approval_id:
        approval_file = approval_file_from_approval_id(args.approval_id, args.run_id, args.cycle_type)
    elif args.approval_file:
        approval_file = resolve_repo_path(args.approval_file)
    else:
        raise SystemExit("--approval-file or --approval-id is required")
    result = validate_cycle_approval(args.run_id, args.cycle_type, approval_file, asof=args.asof)
    print(json.dumps({"status": result["status"], "run_id": args.run_id}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
