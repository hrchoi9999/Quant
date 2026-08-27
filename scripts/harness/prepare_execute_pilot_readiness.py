from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_common import (
    COMMAND_MAPPING_DIR,
    OPERATIONAL_COMMANDS_PATH,
    ROOT,
    command_matches_blocked_pattern,
    load_stage_commands,
    now_stamp,
    read_json,
    write_json,
)
from validate_cycle_approval import OPTIONAL_DEFERRED_STAGES, REQUIRED_STAGES

OUT_JSON = ROOT / "reports" / "harness_runs" / "execute_pilot_readiness_report.json"
OUT_MD = ROOT / "reports" / "harness_runs" / "execute_pilot_readiness_report.md"
REAL_READINESS_PATH = ROOT / "reports" / "agent_shadow_trends" / "real_approval_readiness_report.json"


def _outside_workspace(path_text: str | None) -> bool:
    if not path_text:
        return False
    try:
        Path(path_text).resolve().relative_to(ROOT.resolve())
        return False
    except ValueError:
        return True


def _preflight_status(stage_id: str) -> str:
    path = COMMAND_MAPPING_DIR / f"preflight_{stage_id}.json"
    if not path.exists():
        return "missing"
    return str(read_json(path).get("status") or "unknown")


def _real_readiness() -> dict[str, Any]:
    if not REAL_READINESS_PATH.exists():
        return {"approval_readiness": "missing", "reason": "real readiness report missing"}
    return read_json(REAL_READINESS_PATH)


def _stage_row(cycle_type: str, stage_id: str, config: dict[str, Any]) -> dict[str, Any]:
    risk_level = str(config.get("risk_level") or "").lower()
    command = str(config.get("command") or "")
    command_status = str(config.get("command_status") or "")
    blocked_pattern = command_matches_blocked_pattern(command)
    required = stage_id in REQUIRED_STAGES[cycle_type]
    optional_deferred = stage_id in OPTIONAL_DEFERRED_STAGES
    external_root = _outside_workspace(str(config.get("working_dir") or ""))
    blockers: list[str] = []
    warnings: list[str] = []
    if risk_level in {"high", "critical"}:
        blockers.append(f"risk_level:{risk_level}")
    if command_status == "manual_prompt_only":
        blockers.append("manual_prompt_only")
    if not command:
        blockers.append("command_not_registered")
    if blocked_pattern:
        blockers.append(f"blocked_pattern:{blocked_pattern}")
    if external_root:
        warnings.append("external_root_requires_explicit_execution_approval")
    if _preflight_status(stage_id) != "passed" and required:
        blockers.append(f"preflight:{_preflight_status(stage_id)}")
    execute_candidate = required and not blockers
    deferred_reason = None
    if optional_deferred:
        deferred_reason = "optional_deferred"
    if command_status == "manual_prompt_only":
        deferred_reason = "manual_prompt_only"
    if risk_level in {"high", "critical"}:
        deferred_reason = f"blocked_risk_level:{risk_level}"
    return {
        "stage_id": stage_id,
        "thread": config.get("thread"),
        "action": config.get("action"),
        "risk_level": risk_level,
        "working_dir": config.get("working_dir"),
        "external_root": external_root,
        "required": required,
        "optional_deferred": optional_deferred,
        "execute_candidate": execute_candidate,
        "deferred_reason": deferred_reason,
        "preflight_status": _preflight_status(stage_id),
        "blockers": blockers,
        "warnings": warnings,
    }


def _cycle_rows(cycle_type: str) -> list[dict[str, Any]]:
    commands = load_stage_commands(OPERATIONAL_COMMANDS_PATH)
    prefix = "WD" if cycle_type == "weekday" else "WE"
    return [_stage_row(cycle_type, stage_id, config) for stage_id, config in commands.items() if stage_id.startswith(prefix)]


def _cycle_summary(cycle_type: str) -> dict[str, Any]:
    rows = _cycle_rows(cycle_type)
    candidates = [row["stage_id"] for row in rows if row["execute_candidate"]]
    deferred = [row["stage_id"] for row in rows if row["deferred_reason"]]
    external = [row["stage_id"] for row in rows if row["external_root"] and row["execute_candidate"]]
    blockers = [f"{row['stage_id']}:{', '.join(row['blockers'])}" for row in rows if row["execute_candidate"] and row["blockers"]]
    return {
        "cycle_type": cycle_type,
        "execute_candidates": candidates,
        "deferred_stages": deferred,
        "external_root_candidates": external,
        "stage_rows": rows,
        "blockers": blockers,
        "execute_approval_scope": "manual_operational_cycle_pilot",
        "dry_run_approval_scope": "manual_operational_cycle_dry_run",
    }


def build_report() -> dict[str, Any]:
    readiness = _real_readiness()
    readiness_status = str(readiness.get("approval_readiness") or "unknown")
    cycle_summaries = [_cycle_summary("weekday"), _cycle_summary("weekend")]
    global_blockers = []
    if readiness_status not in {"ready", "ready_with_warnings"}:
        global_blockers.append(f"real_readiness:{readiness_status}")
    for cycle in cycle_summaries:
        if cycle["external_root_candidates"]:
            global_blockers.append(f"{cycle['cycle_type']}:external_root_execution_approval_required")
    payload = {
        "generated_at": now_stamp(),
        "status": "blocked" if global_blockers else "ready_for_execute_approval_request",
        "real_readiness": readiness_status,
        "real_readiness_reason": readiness.get("reason"),
        "weekday_weekend_combined_run_forbidden": True,
        "cycle_summaries": cycle_summaries,
        "execute_approval_conditions": [
            "cycle-specific approval only",
            "approval_scope must be manual_operational_cycle_pilot or manual_cycle_execute",
            "real readiness must be ready or ready_with_warnings",
            "external root execution requires explicit operator approval",
            "critical risk stages remain deferred",
            "asof must be explicitly bound",
        ],
        "global_blockers": global_blockers,
        "next_action": "resolve_global_blockers_before_execute_approval_request" if global_blockers else "create_cycle_specific_execute_approval_request",
    }
    write_json(OUT_JSON, payload)
    OUT_MD.write_text(render_report(payload), encoding="utf-8")
    return payload


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Execute Pilot Readiness Review",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- status: {payload['status']}",
        f"- real_readiness: {payload['real_readiness']}",
        f"- real_readiness_reason: {payload.get('real_readiness_reason')}",
        f"- weekday_weekend_combined_run_forbidden: {payload['weekday_weekend_combined_run_forbidden']}",
        "",
        "## Global Blockers",
    ]
    lines.extend([f"- {item}" for item in payload["global_blockers"]] or ["- none"])
    for cycle in payload["cycle_summaries"]:
        lines.extend(
            [
                "",
                f"## {cycle['cycle_type'].title()}",
                f"- execute_candidates: {', '.join(cycle['execute_candidates']) or 'none'}",
                f"- deferred_stages: {', '.join(cycle['deferred_stages']) or 'none'}",
                f"- external_root_candidates: {', '.join(cycle['external_root_candidates']) or 'none'}",
                f"- execute_approval_scope: {cycle['execute_approval_scope']}",
                f"- dry_run_approval_scope: {cycle['dry_run_approval_scope']}",
                "",
                "| stage_id | candidate | deferred | risk | external_root | preflight | blockers | warnings |",
                "|---|---:|---|---|---:|---|---|---|",
            ]
        )
        for row in cycle["stage_rows"]:
            lines.append(
                f"| {row['stage_id']} | {row['execute_candidate']} | {row.get('deferred_reason') or 'none'} | "
                f"{row['risk_level']} | {row['external_root']} | {row['preflight_status']} | "
                f"{', '.join(row['blockers']) or 'none'} | {', '.join(row['warnings']) or 'none'} |"
            )
    lines.extend(["", "## Execute Approval Conditions"])
    lines.extend([f"- {item}" for item in payload["execute_approval_conditions"]])
    lines.extend(["", "## Next Action", f"- {payload['next_action']}"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="Prepare execute pilot readiness review without executing commands.").parse_args()


def main() -> None:
    parse_args()
    result = build_report()
    print(
        json.dumps(
            {
                "status": result["status"],
                "real_readiness": result["real_readiness"],
                "global_blockers": result["global_blockers"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
