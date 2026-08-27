from __future__ import annotations

import argparse
import json
from typing import Any

from collect_agent_shadow_inputs import STAGE_FILES
from collect_agent_shadow_inputs import collect as collect_inputs
from cycle_common import run_dir
from harness_common import ROOT, now_stamp, read_json, read_yaml, write_json

POLICY_PATH = ROOT / "config" / "harness" / "agent_shadow_review_policy.yaml"
SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2, "critical": 3}


def _max_severity(values: list[str]) -> str:
    if not values:
        return "info"
    return max(values, key=lambda value: SEVERITY_RANK.get(value, 0))


def _policy() -> dict[str, Any]:
    return read_yaml(POLICY_PATH).get("agent_shadow_review_policy") or {}


def _scan_text(stage_id: str, source: str, text: str, patterns: dict[str, list[str]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    lowered = text.lower()
    for severity in ["critical", "error", "warning"]:
        for pattern in patterns.get(severity) or []:
            if str(pattern).lower() in lowered:
                issues.append(
                    {
                        "severity": severity,
                        "stage_id": stage_id,
                        "source": source,
                        "message": f"log pattern matched: {pattern}",
                    }
                )
    return issues


def _status_severity(status: str, required: bool) -> str:
    if status in {"failed", "blocked"}:
        return "error"
    if status == "skipped" and required:
        return "error"
    if status in {"approved", "approved_for_manual_cycle", "skipped"}:
        return "warning"
    return "info"


def _recommend_for_stage(status: str, severity: str, artifact_missing: bool) -> str:
    if severity == "critical":
        return "do_not_continue"
    if status == "failed":
        return "fix_failed_stage"
    if status == "blocked":
        return "resolve_blocked_stage"
    if artifact_missing:
        return "fix_missing_artifacts"
    if severity == "warning":
        return "review_warnings"
    return "proceed_to_manual_review"


def _stage_state_by_id(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("stage_id")): row for row in state.get("stages") or [] if isinstance(row, dict)}


def review(run_id: str) -> dict[str, Any]:
    root = run_dir(run_id)
    input_path = root / "agent_shadow_inputs.json"
    inputs = read_json(input_path) if input_path.exists() else collect_inputs(run_id)
    policy = _policy()
    patterns = policy.get("log_scan_patterns") or {}
    state = inputs.get("cycle_state") or {}
    stage_state = _stage_state_by_id(state)

    detected_issues: list[dict[str, str]] = []
    artifact_review: list[dict[str, Any]] = []
    approval_preflight_review: list[dict[str, Any]] = []
    stage_reviews: list[dict[str, Any]] = []

    for stage_input in inputs.get("stages") or []:
        stage_id = str(stage_input["stage_id"])
        row = stage_state.get(stage_id, {})
        status = str(row.get("status") or "unknown")
        required = bool(row.get("required"))
        stage_issues: list[dict[str, str]] = []

        for key in ["stderr", "stdout", "manual_execution_report"]:
            sample = str(stage_input.get(f"{key}_sample") or "")
            if sample:
                stage_issues.extend(_scan_text(stage_id, f"{key}.log" if key in {"stderr", "stdout"} else "manual_execution_report.md", sample, patterns))

        result = stage_input.get("result") or {}
        artifact = stage_input.get("artifact_validation") or {}
        preflight = result.get("preflight") or {}
        approval = row.get("approval") or result.get("approval") or {}
        artifact_missing = bool(artifact.get("missing"))
        if artifact.get("status") == "failed" or artifact_missing:
            stage_issues.append(
                {
                    "severity": "warning",
                    "stage_id": stage_id,
                    "source": "artifact_validation.json",
                    "message": f"artifact validation issue: {artifact.get('status')}",
                }
            )

        selected = bool(row.get("selected_for_execution"))
        close_stage = stage_id.endswith("_HARNESS_CLOSE")
        result_expected = selected and not close_stage
        if result_expected and status in {"approved", "running", "pending"} and not stage_input.get("result_exists"):
            stage_issues.append(
                {
                    "severity": "warning",
                    "stage_id": stage_id,
                    "source": "result.json",
                    "message": "selected stage has no execution result file",
                }
            )

        if status == "skipped" and required:
            stage_issues.append(
                {
                    "severity": "error",
                    "stage_id": stage_id,
                    "source": "cycle_state.json",
                    "message": "required stage skipped",
                }
            )

        missing_stage_files = [
            filename
            for key, filename in STAGE_FILES.items()
            if result_expected and not bool(stage_input.get(f"{key}_exists"))
        ]
        if missing_stage_files:
            stage_issues.append(
                {
                    "severity": "warning",
                    "stage_id": stage_id,
                    "source": "agent_shadow_inputs.json",
                    "message": "missing selected stage files: " + ", ".join(missing_stage_files),
                }
            )

        detected_issues.extend(stage_issues)
        severities = [_status_severity(status, required), *[issue["severity"] for issue in stage_issues]]
        if close_stage and status == "approved":
            severities = ["info", *[issue["severity"] for issue in stage_issues]]
        severity = _max_severity(severities)
        artifact_review.append(
            {
                "stage_id": stage_id,
                "validation_status": artifact.get("status") or "missing" if result_expected else artifact.get("status") or "not_required",
                "missing": artifact.get("missing") or [],
                "found": artifact.get("found") or [],
            }
        )
        approval_issue = "none"
        if result_expected and not (approval.get("approval_status") or row.get("approval_status") or result.get("approval_status")):
            approval_issue = "approval missing for selected stage"
        approval_preflight_review.append(
            {
                "stage_id": stage_id,
                "approval_status": row.get("approval_status") or result.get("approval_status"),
                "preflight_status": preflight.get("status") or ("not_available" if selected else "not_required"),
                "issue": approval_issue,
            }
        )
        stage_reviews.append(
            {
                "order": row.get("order"),
                "stage_id": stage_id,
                "thread": row.get("thread"),
                "status": status,
                "severity": severity,
                "issue_count": len(stage_issues),
                "recommendation": _recommend_for_stage(status, severity, artifact_missing),
            }
        )

    stage_ids = {str(row.get("stage_id")) for row in state.get("stages") or [] if isinstance(row, dict)}
    missing_root_files = inputs.get("missing_files") or []
    for path in missing_root_files:
        if "\\agent_shadow" in str(path):
            continue
        if any(f"\\{stage_id}\\" in str(path) for stage_id in stage_ids):
            continue
        detected_issues.append(
            {
                "severity": "warning",
                "stage_id": "cycle",
                "source": "agent_shadow_inputs.json",
                "message": f"missing file: {path}",
            }
        )

    log_scan_summary = {
        "critical": sum(1 for issue in detected_issues if issue["severity"] == "critical"),
        "error": sum(1 for issue in detected_issues if issue["severity"] == "error"),
        "warning": sum(1 for issue in detected_issues if issue["severity"] == "warning"),
    }
    overall_status = str(state.get("status") or "unknown")
    overall_severity = _max_severity([row["severity"] for row in stage_reviews] + [issue["severity"] for issue in detected_issues])
    failed_or_blocked = any(row.get("status") in {"failed", "blocked"} for row in stage_reviews)
    terminal_ok = all(row.get("status") in {"completed", "manual_dry_run_completed", "skipped_deferred"} for row in stage_reviews)
    operation_safe = overall_severity not in {"critical", "error"} and not failed_or_blocked and terminal_ok
    requires_manual_review = bool(detected_issues) or overall_severity in {"warning", "error", "critical"}
    if overall_severity == "critical":
        recommendation = "do_not_continue"
    elif any(row.get("status") == "failed" for row in stage_reviews):
        recommendation = "fix_failed_stage"
    elif any(row.get("status") == "blocked" for row in stage_reviews):
        recommendation = "resolve_blocked_stage"
    elif any(issue["source"] == "artifact_validation.json" for issue in detected_issues):
        recommendation = "fix_missing_artifacts"
    elif requires_manual_review:
        recommendation = "review_warnings"
    else:
        recommendation = "proceed_to_manual_review"

    payload = {
        "run_id": run_id,
        "mode": "shadow_only",
        "overall_status": overall_status,
        "overall_severity": overall_severity,
        "operation_safe_to_continue": operation_safe,
        "requires_manual_review": requires_manual_review,
        "stage_reviews": stage_reviews,
        "detected_issues": detected_issues,
        "artifact_review": artifact_review,
        "approval_preflight_review": approval_preflight_review,
        "log_scan_summary": log_scan_summary,
        "forbidden_actions_confirmation": {
            "command_executed_by_agent": False,
            "approval_changed_by_agent": False,
            "source_code_modified_by_agent": False,
            "publish_executed_by_agent": False,
            "trading_or_order_executed_by_agent": False,
        },
        "next_action_recommendation": recommendation,
        "reviewed_at": now_stamp(),
        "cycle_type": state.get("cycle_type"),
        "execution_type": state.get("execution_type"),
    }
    write_json(root / "agent_shadow_review.json", payload)
    (root / "agent_shadow_review.md").write_text(render_review(payload), encoding="utf-8")
    return payload


def render_review(payload: dict[str, Any]) -> str:
    lines = [
        "# Agent Shadow Review",
        "",
        "## Run",
        f"- run_id: {payload['run_id']}",
        f"- cycle_type: {payload.get('cycle_type')}",
        f"- execution_type: {payload.get('execution_type')}",
        f"- status: {payload.get('overall_status')}",
        f"- reviewed_at: {payload.get('reviewed_at')}",
        "- mode: shadow_only",
        "",
        "## Overall Judgment",
        f"- severity: {payload['overall_severity']}",
        "- summary: rule-based file review completed",
        f"- operation_safe_to_continue: {str(payload['operation_safe_to_continue']).lower()}",
        f"- requires_manual_review: {str(payload['requires_manual_review']).lower()}",
        "",
        "## Stage Review",
        "| order | stage_id | thread | status | severity | issue_count | recommendation |",
        "|---:|---|---|---|---|---:|---|",
    ]
    for row in payload["stage_reviews"]:
        lines.append(
            f"| {row.get('order')} | {row['stage_id']} | {row.get('thread')} | {row['status']} | "
            f"{row['severity']} | {row['issue_count']} | {row['recommendation']} |"
        )
    lines.extend(["", "## Detected Issues", "| severity | stage_id | source | message |", "|---|---|---|---|"])
    for issue in payload["detected_issues"]:
        lines.append(f"| {issue['severity']} | {issue['stage_id']} | {issue['source']} | {issue['message']} |")
    if not payload["detected_issues"]:
        lines.append("| info | none | none | none |")
    lines.extend(["", "## Artifact Review", "| stage_id | validation_status | missing | found |", "|---|---|---|---|"])
    for row in payload["artifact_review"]:
        lines.append(f"| {row['stage_id']} | {row['validation_status']} | {len(row.get('missing') or [])} | {len(row.get('found') or [])} |")
    lines.extend(["", "## Approval / Preflight Review", "| stage_id | approval_status | preflight_status | issue |", "|---|---|---|---|"])
    for row in payload["approval_preflight_review"]:
        lines.append(f"| {row['stage_id']} | {row.get('approval_status')} | {row.get('preflight_status')} | {row.get('issue')} |")
    summary = payload["log_scan_summary"]
    lines.extend(
        [
            "",
            "## Log Scan Summary",
            f"- critical: {summary['critical']}",
            f"- error: {summary['error']}",
            f"- warning: {summary['warning']}",
            "",
            "## Forbidden Actions Confirmation",
            "- command executed by agent: false",
            "- approval changed by agent: false",
            "- source code modified by agent: false",
            "- publish executed by agent: false",
            "- trading/sign/order executed by agent: false",
            "",
            "## Next Action Recommendation",
            f"- {payload['next_action_recommendation']}",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run rule-based shadow review for a manual operational cycle.")
    ap.add_argument("--run-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = review(args.run_id)
    print(json.dumps({"run_id": args.run_id, "overall_severity": result["overall_severity"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
