from __future__ import annotations

import argparse
import json

from build_approval_request import approval_dir
from harness_common import read_json


def _read(path):
    return read_json(path) if path.exists() else {}


def build(approval_id: str) -> dict[str, str]:
    out = approval_dir(approval_id)
    request = _read(out / "approval_request.json")
    decision = _read(out / "approval_decision.json")
    gate = _read(out / "approval_gate_result.json")
    constraints = decision.get("execution_constraints") or {}
    risk = request.get("risk_controls") or {}
    lines = [
        "# Approval Packet",
        "",
        "## Approval",
        f"- approval_id: {approval_id}",
        f"- request_type: {request.get('request_type')}",
        f"- approval_scope: {request.get('approval_scope')}",
        f"- status: {request.get('approval_status')}",
        f"- decision: {decision.get('decision')}",
        f"- valid_until: {decision.get('valid_until')}",
        "",
        "## Target",
        f"- target_run_id: {request.get('target_run_id')}",
        f"- target_cycle_type: {request.get('target_cycle_type')}",
        f"- target_stage_ids: {', '.join(request.get('target_stage_ids') or [])}",
        "",
        "## Readiness",
        f"- readiness_status: {request.get('readiness_status')}",
        f"- agent_recommendation: {request.get('agent_recommendation')}",
        "",
        "## Risk Controls",
        f"- high/critical blocked: {risk.get('high_critical_blocked')}",
        f"- GCS publish blocked: {risk.get('publish_blocked')}",
        f"- DB sync blocked: {risk.get('db_sync_blocked')}",
        f"- Trading Sign blocked: {risk.get('trading_sign_blocked')}",
        f"- trading/order blocked: {risk.get('trading_order_blocked')}",
        "",
        "## Human Decision",
        f"- decided_by: {decision.get('decided_by')}",
        f"- decided_at: {decision.get('decided_at')}",
        f"- decision_note: {decision.get('decision_note')}",
        "",
        "## Gate Validation",
        f"- gate_status: {gate.get('gate_status')}",
        f"- approved: {gate.get('approved')}",
        f"- reason: {gate.get('reason')}",
        "",
        "## Execution Constraints",
        f"- single_run_only: {constraints.get('single_run_only')}",
        f"- auto_execute_allowed: {constraints.get('auto_execute_allowed')}",
        f"- publish_allowed: {constraints.get('publish_allowed')}",
        f"- db_sync_allowed: {constraints.get('db_sync_allowed')}",
        f"- trading_sign_allowed: {constraints.get('trading_sign_allowed')}",
        f"- trading_order_allowed: {constraints.get('trading_order_allowed')}",
        "",
        "## Files",
        "- approval_request.json",
        "- approval_decision.json",
        "- approval_gate_result.json",
    ]
    packet = out / "approval_packet.md"
    packet.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"approval_packet": str(packet)}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build approval packet.")
    ap.add_argument("--approval-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(build(args.approval_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
