from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cycle_common import read_cycle_state, run_dir, write_cycle_state
from harness_common import now_stamp, read_json, stage_dir, write_json


def _exists(path: Path) -> str:
    return str(path) if path.exists() else ""


def _items(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] if values else ["- none"]


def _stage_artifacts(run_id: str, stage_id: str) -> dict[str, str]:
    path = stage_dir(run_id, stage_id)
    return {
        "result": _exists(path / "result.json"),
        "stage_report": _exists(path / "stage_report.md"),
        "manual_execution_report": _exists(path / "manual_execution_report.md"),
        "handoff": _exists(path / "handoff.md"),
    }


def collect(run_id: str) -> dict[str, str]:
    state = read_cycle_state(run_id)
    out_dir = run_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    stage_rows: list[dict[str, Any]] = []
    for row in state.get("stages") or []:
        stage_id = str(row["stage_id"])
        artifacts = _stage_artifacts(run_id, stage_id)
        result_path = stage_dir(run_id, stage_id) / "result.json"
        result = read_json(result_path) if result_path.exists() else {}
        stage_rows.append({**row, "artifacts": artifacts, "result": result})

    executed = [row["stage_id"] for row in stage_rows if row.get("status") in {"completed", "manual_dry_run_completed"}]
    skipped = [row["stage_id"] for row in stage_rows if str(row.get("status", "")).startswith("skipped")]
    failed = [row["stage_id"] for row in stage_rows if row.get("status") in {"failed", "blocked"}]
    final_judgment = "failed" if failed else "blocked" if state.get("status") == "blocked" else state.get("status")

    payload = {
        "run_id": run_id,
        "cycle_type": state.get("cycle_type"),
        "execution_type": state.get("execution_type"),
        "approval_file": state.get("approval_file"),
        "approval_scope": state.get("approval_scope"),
        "status": state.get("status"),
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at") or now_stamp(),
        "approval_id": state.get("approval_id"),
        "approval_gate_status": state.get("approval_gate_status"),
        "approval_based_execution": state.get("approval_based_execution"),
        "execution_approval_resolution_file": state.get("execution_approval_resolution_file"),
        "execution_approval_trace_file": state.get("execution_approval_trace_file"),
        "stage_results": stage_rows,
        "executed_stages": executed,
        "skipped_deferred_stages": skipped,
        "failed_blocked_stages": failed,
        "final_judgment": final_judgment,
    }

    lines = [
        "# Manual Operational Cycle Pilot Report",
        "",
        "## Run",
        f"- run_id: {payload['run_id']}",
        f"- cycle_type: {payload['cycle_type']}",
        f"- execution_type: {payload['execution_type']}",
        f"- approval_file: {payload['approval_file']}",
        f"- approval_scope: {payload['approval_scope']}",
        f"- status: {payload['status']}",
        f"- started_at: {payload['started_at']}",
        f"- completed_at: {payload['completed_at']}",
        "",
        "## Approval Gate",
        f"- approval_id: {payload.get('approval_id')}",
        f"- gate_status: {payload.get('approval_gate_status')}",
        f"- approval_based_execution: {payload.get('approval_based_execution')}",
        f"- execution_approval_resolution_file: {payload.get('execution_approval_resolution_file')}",
        f"- execution_approval_trace_file: {payload.get('execution_approval_trace_file')}",
        "",
        "## Approval Summary",
        "| stage_id | approval_status | approval_scope | approved_by | result |",
        "|---|---|---|---|---|",
    ]
    for row in stage_rows:
        approval = row.get("approval") or {}
        lines.append(
            f"| {row['stage_id']} | {row.get('approval_status')} | {row.get('approval_scope')} | "
            f"{approval.get('approved_by')} | {row.get('status')} |"
        )
    if final_judgment in {"completed", "approved_for_manual_cycle"}:
        next_step = "Prepare Agent Shadow Review after manual review."
    else:
        next_step = "Resolve approval/readiness issues before any rerun."
    lines.extend(
        [
            "",
            "## Stage Results",
            "| order | stage_id | thread | command | status | report |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for row in stage_rows:
        artifacts = row.get("artifacts") or {}
        command = str(row.get("command") or "")
        lines.append(f"| {row.get('order')} | {row['stage_id']} | {row.get('thread')} | `{command}` | {row.get('status')} | {artifacts.get('manual_execution_report') or artifacts.get('stage_report')} |")
    lines.extend(["", "## Executed Stages", *_items(executed)])
    lines.extend(["", "## Skipped / Deferred Stages", *_items(skipped)])
    lines.extend(["", "## Failed / Blocked Stages", *_items(failed)])
    lines.extend(["", "## Artifacts"])
    lines.extend(
        _items(
            [
                "cycle_state.json",
                "manual_cycle_approval.md",
                "manual_cycle_report.md",
                "final_summary.md",
            ]
        )
    )
    lines.extend(
        [
            "",
            "## Risk Controls",
            "- high/critical blocked: enforced",
            "- GCS publish blocked: enforced by blocked_patterns",
            "- DB sync blocked: enforced by blocked_patterns",
            "- Trading Sign blocked: enforced by blocked_patterns",
            "- trading/order blocked: enforced by blocked_patterns",
            "",
            "## Final Judgment",
            f"- {final_judgment}",
            "",
            "## Next Recommended Step",
            f"- {next_step}",
        ]
    )

    report_path = out_dir / "manual_cycle_report.md"
    report_json_path = out_dir / "manual_cycle_report.json"
    final_summary_path = out_dir / "final_summary.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(report_json_path, payload)
    final_summary_path.write_text(
        "\n".join(
            [
                "# Final Manual Operational Cycle Summary",
                "",
                f"- run_id: {run_id}",
                f"- cycle_type: {state.get('cycle_type')}",
                f"- status: {state.get('status')}",
                f"- final_judgment: {final_judgment}",
                "",
                "## Files to Review",
                "- manual_cycle_approval.md",
                "- manual_cycle_report.md",
                "- cycle_state.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    state["manual_cycle_report_file"] = str(report_path)
    state["final_summary_file"] = str(final_summary_path)
    state["completed_at"] = state.get("completed_at") or payload["completed_at"]
    write_cycle_state(state)
    return {
        "manual_cycle_report": str(report_path),
        "manual_cycle_report_json": str(report_json_path),
        "final_summary": str(final_summary_path),
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Collect a manual operational cycle report.")
    ap.add_argument("--run-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(collect(args.run_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
