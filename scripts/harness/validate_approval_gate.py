from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from build_approval_request import approval_dir, load_policy
from harness_common import (
    OPERATIONAL_COMMANDS_PATH,
    command_matches_blocked_pattern,
    load_stage_commands,
    now_stamp,
    write_json,
)


def _read(path):
    import json as _json

    return _json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _gate_status(checks: dict[str, bool]) -> str:
    if checks["decision_exists"] and not checks["not_expired"]:
        return "expired"
    if checks["blocked_pattern"] or not checks["risk_allowed"]:
        return "blocked"
    pass_checks = {
        **checks,
        "blocked_pattern": not checks["blocked_pattern"],
        "auto_execute_allowed": not checks["auto_execute_allowed"],
        "publish_allowed": not checks["publish_allowed"],
        "db_sync_allowed": not checks["db_sync_allowed"],
        "trading_sign_allowed": not checks["trading_sign_allowed"],
        "trading_order_allowed": not checks["trading_order_allowed"],
    }
    return "passed" if all(pass_checks.values()) else "failed"


EXECUTION_SCOPE_MAP = {
    "manual_operational_stage_pilot": {"single_stage_manual_pilot", "manual_stage_execute"},
    "manual_operational_cycle_dry_run": {"manual_operational_cycle_dry_run"},
    "manual_operational_cycle_pilot": {
        "manual_operational_cycle_pilot",
        "manual_cycle_execute",
        "first_real_weekday_pilot",
        "first_full_weekday_pilot",
    },
}
FIRST_REAL_WEEKDAY_STAGES = {"WD02_MARKET_COLLECT", "WD03_MARKET_ANALYSIS", "WD05_PORTFOLIO_ANALYSIS"}
FIRST_REAL_WEEKDAY_FORBIDDEN_STAGES = {"WD01_QUANT_FRONT", "WD04_QUANT_REAR"}
FIRST_FULL_WEEKDAY_STAGES = {
    "WD01_QUANT_FRONT",
    "WD02_MARKET_COLLECT",
    "WD03_MARKET_ANALYSIS",
    "WD04_QUANT_REAR",
    "WD05_PORTFOLIO_ANALYSIS",
    "WD06_PRE_GCS_PUBLISH",
}


def _scope_matches(scope: str | None, execution_type: str) -> bool:
    return str(scope or "") in EXECUTION_SCOPE_MAP.get(execution_type, {execution_type})


def _first_real_controls_pass(request: dict[str, Any], decision: dict[str, Any], target_cycle_type: str | None) -> bool:
    scope = request.get("approval_scope")
    if scope not in {"first_real_weekday_pilot", "first_full_weekday_pilot"}:
        return True
    stages = set(request.get("target_stage_ids") or [])
    constraints = decision.get("execution_constraints") or {}
    if scope == "first_full_weekday_pilot":
        return all(
            [
                request.get("target_cycle_type") == "weekday",
                target_cycle_type in {None, "weekday"},
                stages == FIRST_FULL_WEEKDAY_STAGES,
                bool(request.get("first_full_weekday_pilot")),
                bool(request.get("real_readiness_exception_approved")),
                request.get("readiness_status") == "insufficient_data",
                bool(request.get("external_root_execution_approved")),
                bool(request.get("single_run_only")),
                bool(request.get("weekday_weekend_combined_run_forbidden")),
                request.get("auto_repeat_allowed") is False,
                bool(constraints.get("first_full_weekday_pilot_allowed")),
                bool(constraints.get("single_run_only")),
                constraints.get("auto_repeat_allowed") is False,
            ]
        )
    return all(
        [
            request.get("target_cycle_type") == "weekday",
            target_cycle_type in {None, "weekday"},
            stages == FIRST_REAL_WEEKDAY_STAGES,
            not (stages & FIRST_REAL_WEEKDAY_FORBIDDEN_STAGES),
            bool(request.get("first_real_pilot")),
            bool(request.get("real_readiness_exception_approved")),
            request.get("readiness_status") == "insufficient_data",
            bool(request.get("external_root_execution_approved")),
            bool(request.get("single_run_only")),
            bool(request.get("weekday_weekend_combined_run_forbidden")),
            request.get("auto_repeat_allowed") is False,
            bool(constraints.get("first_real_weekday_pilot_allowed")),
            bool(constraints.get("single_run_only")),
            constraints.get("auto_repeat_allowed") is False,
        ]
    )


def validate(
    approval_id: str,
    target_run_id: str,
    execution_type: str,
    *,
    target_stage_id: str | None = None,
    target_cycle_type: str | None = None,
) -> dict[str, Any]:
    out = approval_dir(approval_id)
    request = _read(out / "approval_request.json")
    decision = _read(out / "approval_decision.json")
    policy = load_policy()
    stages = load_stage_commands(OPERATIONAL_COMMANDS_PATH)
    approved_stage_ids = list(decision.get("approved_stage_ids") or [])
    blocked_pattern = False
    for stage_id in approved_stage_ids:
        command = str((stages.get(stage_id) or {}).get("command") or "")
        if command_matches_blocked_pattern(command):
            blocked_pattern = True
    now = datetime.fromisoformat(now_stamp())
    valid_until_text = str(decision.get("valid_until") or "")
    try:
        not_expired = bool(valid_until_text) and datetime.fromisoformat(valid_until_text) >= now
    except ValueError:
        not_expired = False
    constraints = decision.get("execution_constraints") or {}
    request_scope = request.get("approval_scope")
    request_stages = set(request.get("target_stage_ids") or [])
    scope_match = _scope_matches(str(request_scope or ""), execution_type) and decision.get("approval_scope") == request_scope
    target_stage_match = True if not target_stage_id else target_stage_id in request_stages
    target_cycle_match = True if not target_cycle_type else request.get("target_cycle_type") == target_cycle_type
    checks = {
        "request_exists": bool(request),
        "decision_exists": bool(decision),
        "decision_approved": decision.get("decision") == "approved",
        "not_expired": not_expired,
        "scope_match": scope_match,
        "target_run_match": request.get("target_run_id") == target_run_id,
        "target_stage_match": target_stage_match,
        "target_cycle_match": target_cycle_match,
        "first_real_controls": _first_real_controls_pass(request, decision, target_cycle_type),
        "risk_allowed": request.get("risk_level") in set(policy.get("max_risk_level_for_manual_approval") or []),
        "blocked_pattern": blocked_pattern,
        "auto_execute_allowed": bool(constraints.get("auto_execute_allowed")),
        "publish_allowed": bool(constraints.get("publish_allowed")),
        "db_sync_allowed": bool(constraints.get("db_sync_allowed")),
        "trading_sign_allowed": bool(constraints.get("trading_sign_allowed")),
        "trading_order_allowed": bool(constraints.get("trading_order_allowed")),
    }
    pass_checks = {
        **checks,
        "blocked_pattern": not checks["blocked_pattern"],
        "auto_execute_allowed": not checks["auto_execute_allowed"],
        "publish_allowed": not checks["publish_allowed"],
        "db_sync_allowed": not checks["db_sync_allowed"],
        "trading_sign_allowed": not checks["trading_sign_allowed"],
        "trading_order_allowed": not checks["trading_order_allowed"],
    }
    status = _gate_status(checks)
    reason = "passed" if status == "passed" else ", ".join(key for key, value in pass_checks.items() if not value)
    payload = {
        "approval_id": approval_id,
        "target_run_id": target_run_id,
        "target_stage_id": target_stage_id,
        "target_cycle_type": target_cycle_type,
        "execution_type": execution_type,
        "gate_status": status,
        "approved": status == "passed",
        "reason": reason,
        "checks": checks,
        "validated_at": now_stamp(),
    }
    write_json(out / "approval_gate_result.json", payload)
    (out / "approval_gate_result.md").write_text(render_gate(payload), encoding="utf-8")
    return payload


def render_gate(payload: dict[str, Any]) -> str:
    lines = [
        "# Approval Gate Result",
        "",
        f"- approval_id: {payload['approval_id']}",
        f"- target_run_id: {payload['target_run_id']}",
        f"- execution_type: {payload['execution_type']}",
        f"- gate_status: {payload['gate_status']}",
        f"- approved: {payload['approved']}",
        f"- reason: {payload['reason']}",
        "",
        "## Checks",
    ]
    lines.extend([f"- {key}: {value}" for key, value in payload["checks"].items()])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate a human approval gate.")
    ap.add_argument("--approval-id", required=True)
    ap.add_argument("--target-run-id", required=True)
    ap.add_argument("--target-stage-id", default=None)
    ap.add_argument("--target-cycle-type", default=None)
    ap.add_argument("--execution-type", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = validate(
        args.approval_id,
        args.target_run_id,
        args.execution_type,
        target_stage_id=args.target_stage_id,
        target_cycle_type=args.target_cycle_type,
    )
    print(json.dumps({"approval_id": args.approval_id, "gate_status": result["gate_status"]}, ensure_ascii=False, indent=2))
    if result["gate_status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
