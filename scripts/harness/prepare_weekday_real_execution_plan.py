from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cycle_common import stage_plan_rows, validate_cycle
from harness_common import (
    OPERATIONAL_COMMANDS_PATH,
    ROOT,
    bind_command_template,
    command_matches_blocked_pattern,
    load_risk_policy,
    now_stamp,
    read_json,
    risk_policy_allows,
    write_json,
)
from rebuild_real_approval_readiness import TREND_DIR, rebuild

OUT_JSON = ROOT / "reports" / "harness_runs" / "weekday_real_execution_plan.json"
OUT_MD = ROOT / "reports" / "harness_runs" / "weekday_real_execution_plan.md"


def _load_readiness() -> dict[str, Any]:
    path = TREND_DIR / "real_approval_readiness_report.json"
    if not path.exists():
        rebuild()
    return read_json(path)


def _outside_workspace(path_text: str | None) -> bool:
    if not path_text:
        return False
    try:
        Path(path_text).resolve().relative_to(ROOT.resolve())
        return False
    except ValueError:
        return True


def _stage_rows() -> list[dict[str, Any]]:
    validation = validate_cycle("weekday", OPERATIONAL_COMMANDS_PATH)
    by_stage = {row["stage_id"]: row for row in validation.get("stage_results") or []}
    risk_policy = load_risk_policy()
    rows = []
    for row in stage_plan_rows("weekday", OPERATIONAL_COMMANDS_PATH):
        stage_id = str(row["stage_id"])
        validation_row = by_stage.get(stage_id) or {}
        risk_level = str(row.get("risk_level") or "low").lower()
        command = str(row.get("command") or "")
        binding = bind_command_template(command, {"asof": "<ASOF>"})
        blocked_pattern = command_matches_blocked_pattern(command) if command else None
        blockers = list(validation_row.get("issues") or [])
        if risk_level in {"critical"} and f"blocked_risk_level:{risk_level}" not in blockers:
            blockers.append(f"blocked_risk_level:{risk_level}")
        if blocked_pattern:
            blockers.append(f"blocked_pattern:{blocked_pattern}")
        is_close = bool(row.get("close_stage"))
        generic_execute_allowed = (not is_close) and risk_policy_allows(risk_level, "execute", risk_policy) and blocked_pattern is None
        manual_approval_execute_allowed = (not is_close) and risk_level in {"low", "medium", "high"} and blocked_pattern is None
        deferred_reason = None
        if is_close:
            deferred_reason = None
        elif risk_level in {"critical"}:
            deferred_reason = f"risk_level:{risk_level}"
        pilot_included = bool(manual_approval_execute_allowed and not is_close and deferred_reason is None)
        rows.append(
            {
                **row,
                "validation_status": validation_row.get("status"),
                "blockers": blockers,
                "command_with_asof_placeholder": binding["command"],
                "template_variables": binding["template_variables"],
                "asof_required": "asof" in binding["template_variables"],
                "generic_execute_allowed": generic_execute_allowed,
                "manual_approval_execute_allowed": manual_approval_execute_allowed,
                "pilot_included": pilot_included,
                "deferred_reason": deferred_reason,
                "external_thread_root": _outside_workspace(str(row.get("working_dir") or "")),
            }
        )
    return rows


def prepare() -> dict[str, Any]:
    readiness = _load_readiness()
    readiness_status = str(readiness.get("approval_readiness") or "unknown")
    rows = _stage_rows()
    stage_blockers = [
        f"{row['stage_id']}:{', '.join(row['blockers'])}"
        for row in rows
        if row.get("pilot_included") and row.get("blockers") and not row.get("close_stage")
    ]
    deferred_stages = [f"{row['stage_id']}:{row['deferred_reason']}" for row in rows if row.get("deferred_reason")]
    readiness_allows_request = readiness_status in {"ready", "ready_with_warnings"}
    approval_request_possible = readiness_allows_request and not stage_blockers
    approval_gated_dry_run_possible = not stage_blockers
    blockers = []
    if not readiness_allows_request:
        blockers.append(f"real readiness is {readiness_status}")
    blockers.extend(stage_blockers)
    dry_run_command = (
        "D:\\Quant\\venv64\\Scripts\\python.exe scripts\\harness\\run_manual_approved_cycle.py "
        "--run-id <WEEKDAY_RUN_ID> --cycle-type weekday --approval-id <APPROVAL_ID> --asof <ASOF> --dry-run"
    )
    execute_command = (
        "D:\\Quant\\venv64\\Scripts\\python.exe scripts\\harness\\run_manual_approved_cycle.py "
        "--run-id <WEEKDAY_RUN_ID> --cycle-type weekday --approval-id <APPROVAL_ID> --asof <ASOF> --execute"
    )
    payload: dict[str, Any] = {
        "generated_at": now_stamp(),
        "readiness_status": readiness_status,
        "readiness_report": str(TREND_DIR / "real_approval_readiness_report.json"),
        "included_real_runs": readiness.get("included_real_runs") or [],
        "excluded_fixture_runs_source": str(TREND_DIR / "real_operational_runs.json"),
        "weekday_target_stages": rows,
        "deferred_stages": deferred_stages,
        "approval_request_possible": approval_request_possible,
        "approval_gated_dry_run_possible": approval_gated_dry_run_possible,
        "execute_pilot_possible": False,
        "approval_gated_dry_run_command": dry_run_command,
        "approval_gated_execute_command": execute_command,
        "blockers": blockers,
        "next_action": "create_real_approval_request" if approval_request_possible else "run_approval_gated_dry_run_or_collect_real_readiness",
        "safety_controls": {
            "fixture_test_readiness_excluded": True,
            "gcs_publish_blocked": True,
            "db_sync_blocked": True,
            "trading_sign_blocked": True,
            "live_trading_blocked": True,
            "auto_approval": False,
            "auto_scheduling": False,
        },
    }
    write_json(OUT_JSON, payload)
    OUT_MD.write_text(render_plan(payload), encoding="utf-8")
    return payload


def render_plan(payload: dict[str, Any]) -> str:
    lines = [
        "# Weekday Real Execution Plan",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- readiness_status: {payload['readiness_status']}",
        f"- included_real_runs: {', '.join(payload['included_real_runs']) or 'none'}",
        f"- approval_request_possible: {payload['approval_request_possible']}",
        f"- approval_gated_dry_run_possible: {payload['approval_gated_dry_run_possible']}",
        f"- execute_pilot_possible: {payload['execute_pilot_possible']}",
        f"- deferred_stages: {', '.join(payload['deferred_stages']) or 'none'}",
        "",
        "## Weekday Target Stages",
        "| order | stage_id | thread | risk | pilot | generic_execute | manual_approval_execute | external_root | deferred | blockers |",
        "|---:|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in payload["weekday_target_stages"]:
        blockers = ", ".join(row.get("blockers") or []) or "none"
        lines.append(
            f"| {row['order']} | {row['stage_id']} | {row.get('thread')} | {row.get('risk_level')} | "
            f"{row.get('pilot_included')} | {row.get('generic_execute_allowed')} | "
            f"{row.get('manual_approval_execute_allowed')} | {row.get('external_thread_root')} | "
            f"{row.get('deferred_reason') or 'none'} | {blockers} |"
        )
    lines.extend(["", "## Commands"])
    lines.append(f"- dry_run: `{payload['approval_gated_dry_run_command']}`")
    lines.append(f"- execute: `{payload['approval_gated_execute_command']}`")
    lines.extend(["", "## Blockers"])
    lines.extend([f"- {item}" for item in payload["blockers"]] or ["- none"])
    lines.extend(["", "## Next Action", f"- {payload['next_action']}"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="Prepare the weekday real execution approval plan without executing it.").parse_args()


def main() -> None:
    parse_args()
    result = prepare()
    print(
        json.dumps(
            {
                "readiness_status": result["readiness_status"],
                "approval_request_possible": result["approval_request_possible"],
                "execute_pilot_possible": result["execute_pilot_possible"],
                "blocker_count": len(result["blockers"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
