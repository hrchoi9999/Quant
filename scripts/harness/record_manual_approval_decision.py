from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from typing import Any

from build_approval_request import approval_dir, load_policy
from harness_common import now_stamp, read_json, write_json

DECISIONS = {"approved", "rejected", "deferred", "revoked", "expired"}


def _constraints(decision: str, request: dict[str, Any]) -> dict[str, bool]:
    scope = str(request.get("approval_scope") or "")
    first_real_weekday_pilot = scope == "first_real_weekday_pilot"
    first_full_weekday_pilot = scope == "first_full_weekday_pilot"
    return {
        "single_run_only": True,
        "cycle_execute_allowed": decision == "approved"
        and (("cycle" in scope and "dry_run" not in scope) or first_real_weekday_pilot or first_full_weekday_pilot),
        "first_real_weekday_pilot_allowed": decision == "approved" and first_real_weekday_pilot,
        "first_full_weekday_pilot_allowed": decision == "approved" and first_full_weekday_pilot,
        "cycle_dry_run_allowed": decision == "approved" and scope == "manual_operational_cycle_dry_run",
        "auto_execute_allowed": False,
        "auto_repeat_allowed": False,
        "publish_allowed": False,
        "db_sync_allowed": False,
        "trading_sign_allowed": False,
        "trading_order_allowed": False,
    }


def record(approval_id: str, decision: str, decided_by: str, note: str, valid_hours: int) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise SystemExit(f"unsupported decision: {decision}")
    out = approval_dir(approval_id)
    request_path = out / "approval_request.json"
    if not request_path.exists():
        raise SystemExit(f"missing approval_request.json: {request_path}")
    request = read_json(request_path)
    policy = load_policy()
    if request.get("approval_scope") in set(policy.get("forbidden_approval_scopes") or []):
        decision = "rejected"
        note = (note + " forbidden approval_scope").strip()
    if request.get("risk_level") in set(policy.get("blocked_risk_levels") or []):
        decision = "rejected"
        note = (note + " blocked risk_level").strip()
    decided_at = now_stamp()
    valid_until = (datetime.fromisoformat(decided_at) + timedelta(hours=valid_hours)).isoformat(timespec="seconds")
    payload = {
        "approval_id": approval_id,
        "decision": decision,
        "decided_by": decided_by,
        "decided_at": decided_at,
        "approval_scope": request.get("approval_scope"),
        "approved_stage_ids": request.get("target_stage_ids") if decision == "approved" else [],
        "rejected_stage_ids": [] if decision == "approved" else request.get("target_stage_ids"),
        "decision_note": note,
        "valid_until": valid_until,
        "execution_constraints": _constraints(decision, request),
    }
    write_json(out / "approval_decision.json", payload)
    (out / "approval_decision.md").write_text(render_decision(payload), encoding="utf-8")
    request["approval_status"] = decision
    request["decision_file"] = str(out / "approval_decision.json")
    write_json(request_path, request)
    (out / "approval_request.md").write_text(render_updated_request(request), encoding="utf-8")
    return payload


def render_decision(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Approval Decision",
            "",
            f"- approval_id: {payload['approval_id']}",
            f"- decision: {payload['decision']}",
            f"- decided_by: {payload['decided_by']}",
            f"- decided_at: {payload['decided_at']}",
            f"- approval_scope: {payload['approval_scope']}",
            f"- approved_stage_ids: {', '.join(payload['approved_stage_ids'])}",
            f"- rejected_stage_ids: {', '.join(payload['rejected_stage_ids'])}",
            f"- valid_until: {payload['valid_until']}",
            f"- decision_note: {payload['decision_note']}",
        ]
    ) + "\n"


def render_updated_request(request: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Approval Request",
            "",
            f"- approval_id: {request['approval_id']}",
            f"- request_type: {request['request_type']}",
            f"- target_run_id: {request['target_run_id']}",
            f"- target_cycle_type: {request['target_cycle_type']}",
            f"- target_stage_ids: {', '.join(request['target_stage_ids'])}",
            f"- approval_scope: {request['approval_scope']}",
            f"- risk_level: {request['risk_level']}",
            f"- readiness_status: {request['readiness_status']}",
            f"- approval_status: {request['approval_status']}",
            f"- decision_file: {request.get('decision_file')}",
            "",
            "## Safety",
            "- This request does not grant automatic execution authority.",
        ]
    ) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Record a manual approval decision.")
    ap.add_argument("--approval-id", required=True)
    ap.add_argument("--decision", choices=sorted(DECISIONS), required=True)
    ap.add_argument("--decided-by", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--valid-hours", type=int, default=24)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = record(args.approval_id, args.decision, args.decided_by, args.note, args.valid_hours)
    print(json.dumps({"approval_id": args.approval_id, "decision": result["decision"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
