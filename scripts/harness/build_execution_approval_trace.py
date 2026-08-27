from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_approval_request import approval_dir
from cycle_common import run_dir, stage_dir
from harness_common import read_json, write_json


def _read(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def _out_dir(run_id: str, stage_id: str | None) -> Path:
    return stage_dir(run_id, stage_id) if stage_id else run_dir(run_id)


def build(approval_id: str, run_id: str, stage_id: str | None = None) -> dict[str, str]:
    approval_path = approval_dir(approval_id)
    request = _read(approval_path / "approval_request.json")
    decision = _read(approval_path / "approval_decision.json")
    gate = _read(approval_path / "approval_gate_result.json")
    resolution = _read(approval_path / "execution_approval_resolution.json")
    out_dir = _out_dir(run_id, stage_id)
    result_file = out_dir / "result.json" if stage_id else out_dir / "cycle_state.json"
    report_file = out_dir / "manual_execution_report.md" if stage_id else out_dir / "manual_cycle_report.md"
    result = _read(result_file)
    constraints = decision.get("execution_constraints") or {}
    payload = {
        "approval_id": approval_id,
        "run_id": run_id,
        "stage_id": stage_id,
        "approval_request": request,
        "approval_decision": decision,
        "approval_gate_result": gate,
        "execution_approval_resolution": resolution,
        "execution_result": {
            "status": result.get("status"),
            "result_file": str(result_file),
            "report_file": str(report_file),
        },
        "final_judgment": "approved_execution_trace" if resolution.get("execution_allowed") else "blocked_execution_trace",
    }
    trace_json = out_dir / "execution_approval_trace.json"
    trace_md = out_dir / "execution_approval_trace.md"
    write_json(trace_json, payload)
    trace_md.write_text(render_trace(payload, constraints), encoding="utf-8")
    return {"execution_approval_trace_json": str(trace_json), "execution_approval_trace_md": str(trace_md)}


def render_trace(payload: dict[str, Any], constraints: dict[str, Any]) -> str:
    request = payload.get("approval_request") or {}
    decision = payload.get("approval_decision") or {}
    gate = payload.get("approval_gate_result") or {}
    resolution = payload.get("execution_approval_resolution") or {}
    result = payload.get("execution_result") or {}
    return "\n".join(
        [
            "# Execution Approval Trace",
            "",
            "## Approval",
            f"- approval_id: {payload['approval_id']}",
            f"- approval_status: {request.get('approval_status')}",
            f"- decision: {decision.get('decision')}",
            f"- valid_until: {decision.get('valid_until')}",
            f"- approval_scope: {request.get('approval_scope')}",
            "",
            "## Gate",
            f"- gate_status: {gate.get('gate_status')}",
            f"- approved: {gate.get('approved')}",
            f"- reason: {gate.get('reason')}",
            "",
            "## Resolution",
            f"- execution_allowed: {resolution.get('execution_allowed')}",
            f"- block_reason: {resolution.get('block_reason')}",
            f"- scope_match: {resolution.get('scope_match')}",
            f"- target_match: {resolution.get('target_match')}",
            f"- risk_allowed: {resolution.get('risk_allowed')}",
            f"- blocked_pattern: {resolution.get('blocked_pattern')}",
            "",
            "## Execution Constraints",
            f"- single_run_only: {constraints.get('single_run_only')}",
            f"- cycle_execute_allowed: {constraints.get('cycle_execute_allowed')}",
            f"- auto_execute_allowed: {constraints.get('auto_execute_allowed')}",
            f"- publish_allowed: {constraints.get('publish_allowed')}",
            f"- db_sync_allowed: {constraints.get('db_sync_allowed')}",
            f"- trading_sign_allowed: {constraints.get('trading_sign_allowed')}",
            f"- trading_order_allowed: {constraints.get('trading_order_allowed')}",
            "",
            "## Execution Result",
            f"- run_id: {payload['run_id']}",
            f"- stage_id: {payload.get('stage_id')}",
            f"- status: {result.get('status')}",
            f"- result_file: {result.get('result_file')}",
            f"- report_file: {result.get('report_file')}",
            "",
            "## Final Judgment",
            f"- {payload.get('final_judgment')}",
        ]
    ) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build execution approval trace.")
    ap.add_argument("--approval-id", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage-id", default=None)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(build(args.approval_id, args.run_id, args.stage_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
