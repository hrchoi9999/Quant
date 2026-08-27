from __future__ import annotations

import argparse
import json
from typing import Any

from harness_common import ROOT, now_stamp, write_json
from prepare_execute_pilot_readiness import _cycle_summary, _real_readiness

OUT_JSON = ROOT / "reports" / "harness_runs" / "weekday_execute_pilot_packet.json"
OUT_MD = ROOT / "reports" / "harness_runs" / "weekday_execute_pilot_packet.md"


def build_packet(asof: str, target_run_id: str) -> dict[str, Any]:
    readiness = _real_readiness()
    readiness_status = str(readiness.get("approval_readiness") or "unknown")
    cycle = _cycle_summary("weekday")
    blockers = []
    if readiness_status not in {"ready", "ready_with_warnings"}:
        blockers.append(f"real_readiness:{readiness_status}")
    if cycle["external_root_candidates"]:
        blockers.append("external_root_execution_approval_required")
    execute_request_possible = not blockers
    target_stage_ids = ",".join(cycle["execute_candidates"])
    payload: dict[str, Any] = {
        "generated_at": now_stamp(),
        "cycle_type": "weekday",
        "asof": asof,
        "target_run_id": target_run_id,
        "status": "ready_for_execute_approval_request" if execute_request_possible else "blocked",
        "execute_candidates": cycle["execute_candidates"],
        "deferred_stages": cycle["deferred_stages"],
        "external_root_candidates": cycle["external_root_candidates"],
        "stage_rows": cycle["stage_rows"],
        "real_readiness": readiness_status,
        "real_readiness_reason": readiness.get("reason"),
        "execute_approval_scope": "manual_operational_cycle_pilot",
        "execute_request_possible": execute_request_possible,
        "blockers": blockers,
        "external_root_approval_required": bool(cycle["external_root_candidates"]),
        "external_root_approval_targets": sorted({str(row["working_dir"]) for row in cycle["stage_rows"] if row["execute_candidate"] and row["external_root"]}),
        "approval_request_command": (
            "D:\\Quant\\venv64\\Scripts\\python.exe scripts\\harness\\build_approval_request.py "
            f"--target-run-id {target_run_id} --target-cycle-type weekday "
            f"--target-stage-ids {target_stage_ids} "
            "--approval-scope manual_operational_cycle_pilot "
            '--note "weekday execute pilot" --requested-by operator'
        ),
        "execute_command": (
            "D:\\Quant\\venv64\\Scripts\\python.exe scripts\\harness\\run_update_cycle_simple.py "
            f"--cycle weekday --asof {asof} --run-id {target_run_id} --execute --approval-id <WEEKDAY_EXECUTE_APPROVAL_ID>"
        ),
        "safety": {
            "actual_execute_performed": False,
            "weekday_weekend_combined_run_forbidden": True,
            "dry_run_approval_does_not_grant_execute": True,
            "critical_risk_stages_deferred": True,
        },
        "next_action": "resolve_blockers_before_execute_approval_request" if blockers else "create_weekday_execute_approval_request",
    }
    write_json(OUT_JSON, payload)
    OUT_MD.write_text(render_packet(payload), encoding="utf-8")
    return payload


def render_packet(payload: dict[str, Any]) -> str:
    lines = [
        "# Weekday Execute Pilot Packet",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- status: {payload['status']}",
        f"- cycle_type: {payload['cycle_type']}",
        f"- asof: {payload['asof']}",
        f"- target_run_id: {payload['target_run_id']}",
        f"- real_readiness: {payload['real_readiness']}",
        f"- real_readiness_reason: {payload.get('real_readiness_reason')}",
        f"- execute_request_possible: {payload['execute_request_possible']}",
        f"- execute_approval_scope: {payload['execute_approval_scope']}",
        "",
        "## Execute Candidates",
    ]
    lines.extend([f"- {stage_id}" for stage_id in payload["execute_candidates"]] or ["- none"])
    lines.extend(["", "## Deferred Stages"])
    lines.extend([f"- {stage_id}" for stage_id in payload["deferred_stages"]] or ["- none"])
    lines.extend(["", "## External Root Approval"])
    lines.append(f"- required: {payload['external_root_approval_required']}")
    lines.extend([f"- target: {target}" for target in payload["external_root_approval_targets"]] or ["- target: none"])
    lines.extend(["", "## Blockers"])
    lines.extend([f"- {item}" for item in payload["blockers"]] or ["- none"])
    lines.extend(
        [
            "",
            "## Commands",
            f"- approval_request: `{payload['approval_request_command']}`",
            f"- execute: `{payload['execute_command']}`",
            "",
            "## Safety",
        ]
    )
    for key, value in payload["safety"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Next Action", f"- {payload['next_action']}"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Prepare weekday execute pilot packet without executing commands.")
    ap.add_argument("--asof", required=True)
    ap.add_argument("--target-run-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = build_packet(args.asof, args.target_run_id)
    print(
        json.dumps(
            {
                "status": result["status"],
                "execute_request_possible": result["execute_request_possible"],
                "blockers": result["blockers"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
