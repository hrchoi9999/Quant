from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cycle_common import read_cycle_state
from harness_common import (
    OPERATIONAL_COMMANDS_PATH,
    ROOT,
    command_matches_blocked_pattern,
    load_stage_commands,
    now_stamp,
    read_json,
    read_yaml,
    resolve_repo_path,
    write_json,
)

APPROVAL_ROOT = ROOT / "reports" / "harness_approvals"
POLICY_PATH = ROOT / "config" / "harness" / "approval_harness_policy.yaml"
DEFAULT_READINESS = ROOT / "reports" / "agent_shadow_trends" / "approval_readiness_report.json"
REAL_READINESS = ROOT / "reports" / "agent_shadow_trends" / "real_approval_readiness_report.json"
DEFAULT_TREND = ROOT / "reports" / "agent_shadow_trends" / "shadow_trend_analysis.json"
RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
FIRST_REAL_WEEKDAY_PILOT_SCOPE = "first_real_weekday_pilot"
FIRST_FULL_WEEKDAY_PILOT_SCOPE = "first_full_weekday_pilot"
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
FIRST_REAL_EXTERNAL_ROOTS = ["D:/QuantMarket", "D:/QuantAnalysis"]
REAL_APPROVAL_SCOPES = {
    "single_stage_manual_pilot",
    "manual_operational_cycle_pilot",
    FIRST_REAL_WEEKDAY_PILOT_SCOPE,
    FIRST_FULL_WEEKDAY_PILOT_SCOPE,
    "manual_stage_execute",
    "manual_cycle_execute",
}
DRY_RUN_APPROVAL_SCOPES = {
    "manual_operational_cycle_dry_run",
}


def load_policy() -> dict[str, Any]:
    return read_yaml(POLICY_PATH).get("approval_harness_policy") or {}


def approval_dir(approval_id: str) -> Path:
    return APPROVAL_ROOT / approval_id


def approval_id_for(scope: str) -> str:
    suffix = (
        scope.replace("manual_operational_cycle_dry_run", "manual_cycle_dry_run")
        .replace("manual_operational_cycle_pilot", "manual_cycle")
        .replace("single_stage_manual_pilot", "manual_stage")
    )
    return "APPROVAL_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + suffix


def _target_stage_ids(target_run_id: str, explicit: str | None) -> list[str]:
    if explicit:
        return [item.strip() for item in explicit.split(",") if item.strip()]
    try:
        state = read_cycle_state(target_run_id)
    except SystemExit:
        return []
    ids = []
    for row in state.get("stages") or []:
        if row.get("selected_for_execution") and not str(row.get("stage_id", "")).endswith("_HARNESS_CLOSE"):
            ids.append(str(row["stage_id"]))
    return ids


def _risk_and_blocked(stage_ids: list[str]) -> tuple[str, list[str]]:
    commands = load_stage_commands(OPERATIONAL_COMMANDS_PATH)
    risk = "low"
    blocked: list[str] = []
    for stage_id in stage_ids:
        row = commands.get(stage_id) or {}
        level = str(row.get("risk_level") or "low").lower()
        if RISK_ORDER.get(level, 0) > RISK_ORDER.get(risk, 0):
            risk = level
        command = str(row.get("command") or "")
        pattern = command_matches_blocked_pattern(command)
        if pattern:
            blocked.append(f"{stage_id}:{pattern}")
    return risk, blocked


def _source_files(target_run_id: str, readiness_file: Path, trend_file: Path) -> dict[str, str]:
    run_dir = ROOT / "reports" / "harness_runs" / target_run_id
    return {
        "approval_readiness_report": str(readiness_file),
        "shadow_trend_report": str(ROOT / "reports" / "agent_shadow_trends" / "shadow_trend_report.md"),
        "agent_shadow_review": str(run_dir / "agent_shadow_review.json"),
        "manual_cycle_report": str(run_dir / "manual_cycle_report.json"),
        "trend_analysis": str(trend_file),
    }


def _resolve_readiness_file(readiness_file: Path, approval_scope: str) -> tuple[Path, bool]:
    readiness_file = resolve_repo_path(readiness_file)
    real_required = approval_scope in REAL_APPROVAL_SCOPES
    if real_required and readiness_file.resolve() == DEFAULT_READINESS.resolve() and REAL_READINESS.exists():
        return REAL_READINESS, real_required
    return readiness_file, real_required


def _block(approval_id: str, reason: str, payload: dict[str, Any]) -> dict[str, Any]:
    out = approval_dir(approval_id)
    out.mkdir(parents=True, exist_ok=True)
    blocked = {**payload, "approval_id": approval_id, "approval_status": "blocked", "blocked_reason": reason}
    write_json(out / "approval_request_blocked.json", blocked)
    (out / "approval_request_blocked.md").write_text(
        f"# Approval Request Blocked\n\n- approval_id: {approval_id}\n- reason: {reason}\n",
        encoding="utf-8",
    )
    return blocked


def build_request(
    target_run_id: str,
    target_cycle_type: str,
    target_stage_ids: str | None,
    approval_scope: str,
    readiness_file: Path,
    trend_analysis_file: Path,
    note: str,
    requested_by: str,
    real_readiness_exception_approved: bool = False,
    external_root_execution_approved: bool = False,
    single_run_only: bool = False,
    weekday_weekend_combined_forbidden: bool = False,
    auto_repeat_forbidden: bool = False,
) -> dict[str, Any]:
    policy = load_policy()
    readiness_file, real_readiness_required = _resolve_readiness_file(readiness_file, approval_scope)
    trend_analysis_file = resolve_repo_path(trend_analysis_file)
    readiness = read_json(readiness_file) if readiness_file.exists() else {}
    readiness_bypassed_for_dry_run = approval_scope in DRY_RUN_APPROVAL_SCOPES
    first_real_weekday_pilot = approval_scope == FIRST_REAL_WEEKDAY_PILOT_SCOPE
    first_full_weekday_pilot = approval_scope == FIRST_FULL_WEEKDAY_PILOT_SCOPE
    readiness_status = "not_required_for_dry_run" if readiness_bypassed_for_dry_run else str(readiness.get("approval_readiness") or "")
    agent_recommendation = "approval_gated_dry_run_allowed" if readiness_bypassed_for_dry_run else str(readiness.get("recommendation") or "")
    stage_ids = _target_stage_ids(target_run_id, target_stage_ids)
    risk_level, blocked_patterns = _risk_and_blocked(stage_ids)
    requested_at = now_stamp()
    default_hours = int((policy.get("approval_expiry") or {}).get("default_hours", 24))
    approval_id = approval_id_for(approval_scope)
    base = {
        "request_type": approval_scope,
        "target_run_id": target_run_id,
        "target_cycle_type": target_cycle_type,
        "target_stage_ids": stage_ids,
        "approval_scope": approval_scope,
        "risk_level": risk_level,
        "requested_at": requested_at,
        "requested_by": requested_by,
        "readiness_status": readiness_status,
        "readiness_source": str(readiness_file),
        "fixture_runs_excluded": bool(readiness.get("fixture_runs_excluded")) if real_readiness_required else False,
        "real_readiness_required": real_readiness_required,
        "readiness_bypassed_for_dry_run": readiness_bypassed_for_dry_run,
        "first_real_pilot": first_real_weekday_pilot,
        "first_full_weekday_pilot": first_full_weekday_pilot,
        "real_readiness_exception_approved": bool(real_readiness_exception_approved),
        "real_readiness_exception_reason": "insufficient_data" if real_readiness_exception_approved else None,
        "external_root_execution_approved": bool(external_root_execution_approved),
        "external_root_approval_targets": FIRST_REAL_EXTERNAL_ROOTS if (first_real_weekday_pilot or first_full_weekday_pilot) else [],
        "forbidden_stage_ids": sorted(FIRST_REAL_WEEKDAY_FORBIDDEN_STAGES) if first_real_weekday_pilot else [],
        "single_run_only": bool(single_run_only),
        "auto_repeat_allowed": False,
        "auto_repeat_forbidden": bool(auto_repeat_forbidden),
        "weekday_weekend_combined_run_forbidden": bool(weekday_weekend_combined_forbidden),
        "agent_recommendation": agent_recommendation,
        "source_files": _source_files(target_run_id, readiness_file, trend_analysis_file),
        "notes": note,
    }
    allowed_readiness = set(((policy.get("readiness_gate") or {}).get("allowed_readiness") or []))
    first_real_readiness_exception = (
        (first_real_weekday_pilot or first_full_weekday_pilot)
        and real_readiness_exception_approved
        and readiness_status == "insufficient_data"
    )
    if first_real_weekday_pilot:
        if target_cycle_type != "weekday":
            return _block(approval_id, f"first real pilot requires weekday cycle: {target_cycle_type}", base)
        if set(stage_ids) != FIRST_REAL_WEEKDAY_STAGES:
            return _block(approval_id, "first real pilot target stages must be exactly WD02, WD03, WD05", base)
        if set(stage_ids) & FIRST_REAL_WEEKDAY_FORBIDDEN_STAGES:
            return _block(approval_id, "first real pilot includes forbidden WD01/WD04 stage", base)
        if not external_root_execution_approved:
            return _block(approval_id, "external root execution approval is required", base)
        if not real_readiness_exception_approved:
            return _block(approval_id, "real_readiness insufficient_data exception approval is required", base)
        if not single_run_only:
            return _block(approval_id, "single run only confirmation is required", base)
        if not weekday_weekend_combined_forbidden:
            return _block(approval_id, "weekday/weekend combined run forbid confirmation is required", base)
        if not auto_repeat_forbidden:
            return _block(approval_id, "auto repeat forbid confirmation is required", base)
    if first_full_weekday_pilot:
        if target_cycle_type != "weekday":
            return _block(approval_id, f"first full weekday pilot requires weekday cycle: {target_cycle_type}", base)
        if set(stage_ids) != FIRST_FULL_WEEKDAY_STAGES:
            return _block(approval_id, "first full weekday pilot target stages must be exactly WD01, WD02, WD03, WD04, WD05, WD06", base)
        if not external_root_execution_approved:
            return _block(approval_id, "external root execution approval is required", base)
        if not real_readiness_exception_approved:
            return _block(approval_id, "real_readiness insufficient_data exception approval is required", base)
        if not single_run_only:
            return _block(approval_id, "single run only confirmation is required", base)
        if not weekday_weekend_combined_forbidden:
            return _block(approval_id, "weekday/weekend combined run forbid confirmation is required", base)
        if not auto_repeat_forbidden:
            return _block(approval_id, "auto repeat forbid confirmation is required", base)
    if real_readiness_required and readiness_file.resolve() != REAL_READINESS.resolve():
        return _block(approval_id, f"real readiness report is required: {REAL_READINESS}", base)
    if real_readiness_required and not bool(readiness.get("fixture_runs_excluded")):
        return _block(approval_id, "readiness report does not confirm fixture/test run exclusion", base)
    if not readiness_bypassed_for_dry_run and not first_real_readiness_exception and readiness_status not in allowed_readiness:
        return _block(approval_id, f"readiness_status is not allowed: {readiness_status}", base)
    if approval_scope in set(policy.get("forbidden_approval_scopes") or []):
        return _block(approval_id, f"forbidden approval_scope: {approval_scope}", base)
    if approval_scope not in set(policy.get("allowed_approval_scopes") or []):
        return _block(approval_id, f"approval_scope is not allowed: {approval_scope}", base)
    if risk_level in set(policy.get("blocked_risk_levels") or []):
        return _block(approval_id, f"blocked risk_level: {risk_level}", base)
    if blocked_patterns:
        return _block(approval_id, "blocked pattern matched: " + ", ".join(blocked_patterns), base)

    expires_at = (datetime.fromisoformat(requested_at) + timedelta(hours=default_hours)).isoformat(timespec="seconds")
    payload = {
        "approval_id": approval_id,
        **base,
        "risk_controls": {
            "high_critical_blocked": True,
            "blocked_patterns_checked": True,
            "publish_blocked": True,
            "db_sync_blocked": True,
            "trading_sign_blocked": True,
            "trading_order_blocked": True,
        },
        "approval_status": "requested",
        "decision_file": None,
        "expires_at": expires_at,
    }
    out = approval_dir(approval_id)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "approval_request.json", payload)
    (out / "approval_request.md").write_text(render_request(payload), encoding="utf-8")
    return payload


def render_request(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Approval Request",
            "",
            f"- approval_id: {payload['approval_id']}",
            f"- request_type: {payload['request_type']}",
            f"- target_run_id: {payload['target_run_id']}",
            f"- target_cycle_type: {payload['target_cycle_type']}",
            f"- target_stage_ids: {', '.join(payload['target_stage_ids'])}",
            f"- approval_scope: {payload['approval_scope']}",
            f"- risk_level: {payload['risk_level']}",
            f"- readiness_status: {payload['readiness_status']}",
            f"- readiness_source: {payload['readiness_source']}",
            f"- fixture_runs_excluded: {payload['fixture_runs_excluded']}",
            f"- real_readiness_required: {payload['real_readiness_required']}",
            f"- readiness_bypassed_for_dry_run: {payload.get('readiness_bypassed_for_dry_run')}",
            f"- agent_recommendation: {payload['agent_recommendation']}",
            f"- approval_status: {payload['approval_status']}",
            f"- expires_at: {payload['expires_at']}",
            "",
            "## Safety",
            "- This request does not grant automatic execution authority.",
        ]
    ) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build a human approval request.")
    ap.add_argument("--target-run-id", required=True)
    ap.add_argument("--target-cycle-type", default="")
    ap.add_argument("--target-stage-ids", default=None)
    ap.add_argument("--approval-scope", required=True)
    ap.add_argument("--readiness-file", default=str(DEFAULT_READINESS))
    ap.add_argument("--trend-analysis-file", default=str(DEFAULT_TREND))
    ap.add_argument("--note", default="")
    ap.add_argument("--requested-by", default="harness")
    ap.add_argument("--real-readiness-exception-approved", action="store_true")
    ap.add_argument("--external-root-execution-approved", action="store_true")
    ap.add_argument("--single-run-only", action="store_true")
    ap.add_argument("--weekday-weekend-combined-forbidden", action="store_true")
    ap.add_argument("--auto-repeat-forbidden", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = build_request(
        args.target_run_id,
        args.target_cycle_type,
        args.target_stage_ids,
        args.approval_scope,
        resolve_repo_path(args.readiness_file),
        resolve_repo_path(args.trend_analysis_file),
        args.note,
        args.requested_by,
        args.real_readiness_exception_approved,
        args.external_root_execution_approved,
        args.single_run_only,
        args.weekday_weekend_combined_forbidden,
        args.auto_repeat_forbidden,
    )
    print(json.dumps({"approval_id": result["approval_id"], "approval_status": result["approval_status"]}, ensure_ascii=False, indent=2))
    if result["approval_status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
