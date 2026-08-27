from __future__ import annotations

import argparse
import json
from typing import Any

from build_approval_request import approval_dir
from harness_common import now_stamp, read_json, write_json
from validate_approval_gate import validate as validate_gate


def _read(path):
    return read_json(path) if path.exists() else {}


def _block_reason(gate: dict[str, Any], request: dict[str, Any], decision: dict[str, Any]) -> str | None:
    if not request:
        return "approval_request_missing"
    if not decision:
        return "approval_decision_missing"
    if decision.get("decision") != "approved":
        return "approval_not_approved"
    if gate.get("gate_status") == "expired":
        return "approval_expired"
    if gate.get("gate_status") != "passed":
        checks = gate.get("checks") or {}
        if not checks.get("scope_match", True):
            return "scope_mismatch"
        if not checks.get("target_run_match", True) or not checks.get("target_stage_match", True) or not checks.get("target_cycle_match", True):
            return "target_mismatch"
        if not checks.get("risk_allowed", True):
            return "risk_blocked"
        if checks.get("blocked_pattern"):
            return "blocked_pattern_detected"
        if checks.get("auto_execute_allowed"):
            return "auto_execute_not_allowed"
        if checks.get("publish_allowed"):
            return "publish_not_allowed"
        if checks.get("db_sync_allowed"):
            return "db_sync_not_allowed"
        if checks.get("trading_sign_allowed"):
            return "trading_sign_not_allowed"
        if checks.get("trading_order_allowed"):
            return "trading_order_not_allowed"
        return "approval_gate_not_passed"
    return None


def resolve(
    approval_id: str,
    execution_type: str,
    target_run_id: str,
    *,
    target_stage_id: str | None = None,
    target_cycle_type: str | None = None,
) -> dict[str, Any]:
    out = approval_dir(approval_id)
    request = _read(out / "approval_request.json")
    decision = _read(out / "approval_decision.json")
    gate = validate_gate(
        approval_id,
        target_run_id,
        execution_type,
        target_stage_id=target_stage_id,
        target_cycle_type=target_cycle_type,
    )
    constraints = decision.get("execution_constraints") or {}
    checks = gate.get("checks") or {}
    block_reason = _block_reason(gate, request, decision)
    valid_until = decision.get("valid_until")
    payload = {
        "approval_id": approval_id,
        "execution_type": execution_type,
        "target_run_id": target_run_id,
        "target_stage_id": target_stage_id,
        "target_cycle_type": target_cycle_type,
        "approval_resolved": bool(request and decision),
        "execution_allowed": block_reason is None,
        "gate_status": gate.get("gate_status"),
        "approval_status": request.get("approval_status"),
        "decision": decision.get("decision"),
        "valid_until": valid_until,
        "scope_match": bool(checks.get("scope_match")),
        "target_match": bool(checks.get("target_run_match")) and bool(checks.get("target_stage_match", True)) and bool(checks.get("target_cycle_match", True)),
        "risk_allowed": bool(checks.get("risk_allowed")),
        "blocked_pattern": bool(checks.get("blocked_pattern")),
        "execution_constraints": constraints,
        "block_reason": block_reason,
        "approval_request_file": str(out / "approval_request.json"),
        "approval_decision_file": str(out / "approval_decision.json"),
        "approval_gate_result_file": str(out / "approval_gate_result.json"),
        "execution_approval_resolution_file": str(out / "execution_approval_resolution.json"),
        "resolved_at": now_stamp(),
    }
    write_json(out / "execution_approval_resolution.json", payload)
    (out / "execution_approval_resolution.md").write_text(render_resolution(payload), encoding="utf-8")
    return payload


def render_resolution(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Execution Approval Resolution",
            "",
            f"- approval_id: {payload['approval_id']}",
            f"- execution_type: {payload['execution_type']}",
            f"- target_run_id: {payload['target_run_id']}",
            f"- target_stage_id: {payload.get('target_stage_id')}",
            f"- target_cycle_type: {payload.get('target_cycle_type')}",
            f"- execution_allowed: {payload['execution_allowed']}",
            f"- gate_status: {payload.get('gate_status')}",
            f"- approval_status: {payload.get('approval_status')}",
            f"- decision: {payload.get('decision')}",
            f"- valid_until: {payload.get('valid_until')}",
            f"- block_reason: {payload.get('block_reason')}",
            "",
            "## Checks",
            f"- scope_match: {payload['scope_match']}",
            f"- target_match: {payload['target_match']}",
            f"- risk_allowed: {payload['risk_allowed']}",
            f"- blocked_pattern: {payload['blocked_pattern']}",
        ]
    ) + "\n"


def approval_row_from_resolution(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage_id": payload.get("target_stage_id"),
        "approval_status": "approved" if payload.get("execution_allowed") else payload.get("approval_status"),
        "approval_scope": _scope_from_execution_type(str(payload.get("execution_type") or "")),
        "approved_by": "approval_harness",
        "approved_at": payload.get("resolved_at"),
        "notes": f"approval_id={payload.get('approval_id')}",
    }


def _scope_from_execution_type(execution_type: str) -> str:
    if execution_type == "manual_operational_stage_pilot":
        return "single_stage_manual_pilot"
    if execution_type == "manual_operational_cycle_dry_run":
        return "manual_operational_cycle_dry_run"
    if execution_type == "manual_operational_cycle_pilot":
        return "manual_operational_cycle_pilot"
    return execution_type


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Resolve approval gate before manual execution.")
    ap.add_argument("--approval-id", required=True)
    ap.add_argument("--execution-type", required=True)
    ap.add_argument("--target-run-id", required=True)
    ap.add_argument("--target-stage-id", default=None)
    ap.add_argument("--target-cycle-type", default=None)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = resolve(
        args.approval_id,
        args.execution_type,
        args.target_run_id,
        target_stage_id=args.target_stage_id,
        target_cycle_type=args.target_cycle_type,
    )
    print(json.dumps({"approval_id": args.approval_id, "execution_allowed": result["execution_allowed"]}, ensure_ascii=False, indent=2))
    if not result["execution_allowed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
