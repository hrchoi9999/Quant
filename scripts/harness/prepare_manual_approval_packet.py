from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cycle_common import is_close_stage, run_dir
from harness_common import (
    COMMAND_MAPPING_DIR,
    OPERATIONAL_COMMANDS_PATH,
    command_matches_blocked_pattern,
    get_stage_config,
    read_json,
    resolve_repo_path,
    write_json,
)

APPROVAL_POLICY_PATH = Path("config/harness/manual_approval_policy.yaml")


def _status(path: Path) -> str | None:
    if not path.exists():
        return None
    return str(read_json(path).get("status"))


def _stage_recommendation(stage: dict[str, Any], config: dict[str, Any], preflight_status: str | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    risk_level = str(config.get("risk_level") or "")
    blocked_pattern = command_matches_blocked_pattern(str(config.get("command") or ""))
    if stage.get("status") != "dry_run_completed":
        reasons.append(f"dry_run_status={stage.get('status')}")
    if preflight_status != "passed":
        reasons.append(f"preflight_status={preflight_status}")
    if risk_level in {"critical"}:
        reasons.append(f"risk_level={risk_level}")
    if blocked_pattern:
        reasons.append(f"blocked_pattern={blocked_pattern}")
    if config.get("command_status") not in {"candidate_found", "preflight_passed", "approved_for_manual_execute"}:
        reasons.append(f"command_status={config.get('command_status')}")
    return ("manual_review_required" if reasons else "eligible_for_manual_approval", reasons)


def build_packet(run_id: str, config_path: Path = OPERATIONAL_COMMANDS_PATH) -> dict[str, Any]:
    base = run_dir(run_id)
    state = read_json(base / "cycle_state.json")
    quality_status = _status(base / "cycle_quality_gate.json")
    alignment_path = COMMAND_MAPPING_DIR / "thread_file_alignment_audit.json"
    alignment_payload = read_json(alignment_path) if alignment_path.exists() else {}
    alignment_issue_count = alignment_payload.get("issue_count")
    if alignment_issue_count is None:
        alignment_issue_count = len(alignment_payload.get("summary") or [])
    alignment_status = "passed" if alignment_path.exists() and int(alignment_issue_count) == 0 else "failed"
    stages: list[dict[str, Any]] = []
    for stage in state.get("stages") or []:
        stage_id = str(stage.get("stage_id") or "")
        if is_close_stage(stage_id):
            continue
        config = get_stage_config(stage_id, config_path)
        preflight_path = COMMAND_MAPPING_DIR / f"preflight_{stage_id}.json"
        preflight_status = _status(preflight_path)
        recommendation, reasons = _stage_recommendation(stage, config, preflight_status)
        stages.append(
            {
                "stage_id": stage_id,
                "thread": stage.get("thread"),
                "action": config.get("action"),
                "command": config.get("command"),
                "working_dir": config.get("working_dir"),
                "risk_level": config.get("risk_level"),
                "safe_run": config.get("safe_run"),
                "command_status": config.get("command_status"),
                "dry_run_status": stage.get("status"),
                "preflight_status": preflight_status,
                "result_file": stage.get("result_file"),
                "stage_report_file": stage.get("stage_report_file"),
                "handoff_file": stage.get("handoff_file"),
                "recommendation": recommendation,
                "reasons": reasons,
            }
        )
    return {
        "run_id": run_id,
        "source_name": "manual_approval_packet",
        "cycle_type": state.get("cycle_type"),
        "mode": state.get("mode"),
        "cycle_status": state.get("status"),
        "config": str(config_path),
        "quality_gate_status": quality_status,
        "thread_alignment_status": alignment_status,
        "approval_scope": "manual_execute_only",
        "harness_execute_approval": "blocked",
        "stages": stages,
    }


def render_packet(packet: dict[str, Any]) -> str:
    lines = [
        "# Manual Approval Packet",
        "",
        f"- run_id: {packet['run_id']}",
        f"- cycle_type: {packet.get('cycle_type')}",
        f"- mode: {packet.get('mode')}",
        f"- cycle_status: {packet.get('cycle_status')}",
        f"- quality_gate_status: {packet.get('quality_gate_status')}",
        f"- thread_alignment_status: {packet.get('thread_alignment_status')}",
        f"- approval_scope: {packet.get('approval_scope')}",
        f"- harness_execute_approval: {packet.get('harness_execute_approval')}",
        "",
        "## Stage Review",
        "| stage_id | thread | risk | dry-run | preflight | recommendation |",
        "|---|---|---|---|---|---|",
    ]
    for row in packet["stages"]:
        lines.append(
            f"| {row['stage_id']} | {row['thread']} | {row['risk_level']} | {row['dry_run_status']} | "
            f"{row['preflight_status']} | {row['recommendation']} |"
        )
    lines.extend(["", "## Approval Checklist"])
    checklist = [
        "cycle_quality_gate_passed",
        "thread_file_alignment_passed",
        "stage_preflight_passed",
        "operational_dry_run_completed",
        "no_blocked_pattern",
        "no approved_for_harness_execute request",
    ]
    lines.extend(f"- [ ] {item}" for item in checklist)
    lines.extend(["", "## Stage Commands"])
    for row in packet["stages"]:
        reasons = ", ".join(row["reasons"]) or "none"
        lines.extend(
            [
                f"### {row['stage_id']}",
                f"- recommendation: {row['recommendation']}",
                f"- reasons: {reasons}",
                f"- working_dir: `{row['working_dir']}`",
                "```text",
                str(row["command"]),
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Prepare manual approval review packet from an operational dry-run cycle.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--config", default=str(OPERATIONAL_COMMANDS_PATH))
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_repo_path(args.config)
    packet = build_packet(args.run_id, config_path)
    out_dir = run_dir(args.run_id)
    json_path = out_dir / "manual_approval_packet.json"
    md_path = out_dir / "manual_approval_packet.md"
    write_json(json_path, packet)
    md_path.write_text(render_packet(packet), encoding="utf-8")
    print(json.dumps({"packet": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
