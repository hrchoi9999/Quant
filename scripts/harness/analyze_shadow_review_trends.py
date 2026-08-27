from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from collect_multi_run_shadow_inputs import TREND_DIR
from collect_multi_run_shadow_inputs import collect as collect_inputs
from harness_common import ROOT, now_stamp, read_json, read_yaml, resolve_repo_path, write_json

POLICY_PATH = ROOT / "config" / "harness" / "agent_shadow_trend_policy.yaml"


def trend_policy() -> dict[str, Any]:
    return read_yaml(POLICY_PATH).get("agent_shadow_trend_policy") or {}


def _severity_counts(stage_reviews: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(row.get("severity") or "info") for row in stage_reviews)


def _runtime_seconds(stage: dict[str, Any]) -> float | None:
    row = stage.get("cycle_state") or {}
    start = row.get("started_at")
    end = row.get("completed_at")
    if not start or not end:
        return None
    try:
        return (datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds()
    except ValueError:
        return None


def _stability(row: dict[str, Any], run_count: int) -> str:
    if row["critical_count"] or row["failed_count"] or row["blocked_count"]:
        return "blocked"
    if row["error_count"] or row["artifact_missing_count"]:
        return "unstable"
    if run_count < 2:
        return "insufficient_data"
    if row["warning_count"] or row["skipped_count"]:
        return "watch"
    return "stable"


def _issue_key(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(issue.get("severity") or "info"),
        str(issue.get("stage_id") or "cycle"),
        str(issue.get("source") or "unknown"),
        str(issue.get("message") or ""),
    )


def analyze(input_path: Path | None = None) -> dict[str, Any]:
    input_path = resolve_repo_path(input_path) if input_path else TREND_DIR / "multi_run_shadow_inputs.json"
    if not input_path.exists():
        collect_inputs(limit=10)
    inputs = read_json(input_path)
    policy = trend_policy()
    thresholds = policy.get("repeated_issue_thresholds") or {}
    runtime_policy = policy.get("runtime_anomaly") or {}
    runs = inputs.get("runs") or []

    overall = {
        "clean_runs": 0,
        "warning_runs": 0,
        "error_runs": 0,
        "critical_runs": 0,
        "safe_to_continue_runs": 0,
        "manual_review_required_runs": 0,
    }
    stage_acc: dict[str, dict[str, Any]] = {}
    issue_counter: Counter[tuple[str, str, str, str]] = Counter()
    artifact_missing: defaultdict[str, list[str]] = defaultdict(list)
    approval_issue_counter: Counter[tuple[str, str]] = Counter()
    runtimes: defaultdict[str, list[float]] = defaultdict(list)
    has_failed_required = False
    has_blocked_required = False
    has_missing_required_artifacts = False

    for run in runs:
        review = run.get("agent_shadow_review") or {}
        severity = str(review.get("overall_severity") or "info")
        if severity == "critical":
            overall["critical_runs"] += 1
        elif severity == "error":
            overall["error_runs"] += 1
        elif severity == "warning":
            overall["warning_runs"] += 1
        else:
            overall["clean_runs"] += 1
        if review.get("operation_safe_to_continue"):
            overall["safe_to_continue_runs"] += 1
        if review.get("requires_manual_review"):
            overall["manual_review_required_runs"] += 1

        for issue in review.get("detected_issues") or []:
            issue_counter[_issue_key(issue)] += 1

        for artifact in review.get("artifact_review") or []:
            if artifact.get("validation_status") in {"failed", "missing"} or artifact.get("missing"):
                stage_id = str(artifact.get("stage_id") or "unknown")
                missing = artifact.get("missing") or []
                artifact_missing[stage_id].extend([str(item) for item in missing] or [str(artifact.get("validation_status"))])

        for ap in review.get("approval_preflight_review") or []:
            issue = str(ap.get("issue") or "none")
            if issue != "none":
                approval_issue_counter[(str(ap.get("stage_id") or "unknown"), issue)] += 1

        by_stage = {str(row.get("stage_id")): row for row in review.get("stage_reviews") or []}
        for stage in run.get("stages") or []:
            stage_id = str(stage.get("stage_id") or "")
            if not stage_id:
                continue
            cycle_row = stage.get("cycle_state") or {}
            review_row = by_stage.get(stage_id, {})
            acc = stage_acc.setdefault(
                stage_id,
                {
                    "stage_id": stage_id,
                    "thread": cycle_row.get("thread") or review_row.get("thread"),
                    "run_count": 0,
                    "completed_count": 0,
                    "failed_count": 0,
                    "blocked_count": 0,
                    "skipped_count": 0,
                    "skipped_deferred_count": 0,
                    "warning_count": 0,
                    "error_count": 0,
                    "critical_count": 0,
                    "artifact_missing_count": 0,
                },
            )
            acc["run_count"] += 1
            status = str(review_row.get("status") or cycle_row.get("status") or "unknown")
            if status in {"completed", "manual_dry_run_completed", "approved"}:
                acc["completed_count"] += 1
            elif status == "failed":
                acc["failed_count"] += 1
            elif status == "blocked":
                acc["blocked_count"] += 1
            elif status == "skipped":
                acc["skipped_count"] += 1
            elif status == "skipped_deferred":
                acc["skipped_deferred_count"] += 1
            severity_counts = _severity_counts([review_row] if review_row else [])
            acc["warning_count"] += severity_counts["warning"]
            acc["error_count"] += severity_counts["error"]
            acc["critical_count"] += severity_counts["critical"]
            artifact = stage.get("artifact_validation") or {}
            if artifact.get("status") in {"failed", "missing"} or artifact.get("missing"):
                acc["artifact_missing_count"] += 1
                if bool(cycle_row.get("required")):
                    has_missing_required_artifacts = True
            if bool(cycle_row.get("required")) and status == "failed":
                has_failed_required = True
            if bool(cycle_row.get("required")) and status == "blocked":
                has_blocked_required = True
            runtime = _runtime_seconds(stage)
            if runtime is not None:
                runtimes[stage_id].append(runtime)

    repeated_issues = []
    for key, count in issue_counter.items():
        severity, stage_id, source, message = key
        threshold = int(thresholds.get(f"{severity}_repeat_count", 2))
        if count >= threshold:
            repeated_issues.append({"severity": severity, "stage_id": stage_id, "source": source, "count": count, "message": message})

    artifact_contract_issues = [
        {"stage_id": stage_id, "missing_count": len(values), "missing_artifacts": sorted(set(values))}
        for stage_id, values in sorted(artifact_missing.items())
        if len(values) >= int(thresholds.get("artifact_missing_repeat_count", 1))
    ]

    runtime_anomalies = []
    if runtime_policy.get("enabled"):
        minimum = int(runtime_policy.get("minimum_baseline_runs", 3))
        for stage_id, values in runtimes.items():
            if len(values) < minimum:
                continue
            baseline_values = values[:-1]
            if not baseline_values:
                continue
            baseline = sum(baseline_values) / len(baseline_values)
            latest = values[-1]
            ratio = latest / baseline if baseline else 0
            if ratio >= float(runtime_policy.get("critical_ratio", 2.0)):
                severity = "critical"
            elif ratio >= float(runtime_policy.get("warning_ratio", 1.5)):
                severity = "warning"
            else:
                continue
            runtime_anomalies.append({"stage_id": stage_id, "baseline": baseline, "latest": latest, "ratio": ratio, "severity": severity})

    stage_trends = []
    for row in stage_acc.values():
        row["repeated_issue"] = any(issue["stage_id"] == row["stage_id"] for issue in repeated_issues)
        row["stability"] = _stability(row, int(row["run_count"]))
        stage_trends.append(row)
    stage_trends.sort(key=lambda row: str(row["stage_id"]))

    payload = {
        "generated_at": now_stamp(),
        "run_count": len(runs),
        "runs_analyzed": [run["run_id"] for run in runs],
        "overall_trend": overall,
        "stage_trends": stage_trends,
        "repeated_issues": repeated_issues,
        "artifact_contract_issues": artifact_contract_issues,
        "runtime_anomalies": runtime_anomalies,
        "approval_preflight_issues": [
            {"stage_id": stage_id, "issue": issue, "count": count}
            for (stage_id, issue), count in approval_issue_counter.items()
        ],
        "approval_readiness_inputs": {
            "minimum_runs_met": len(runs) >= int(policy.get("minimum_runs_for_trend", 2)),
            "clean_runs": overall["clean_runs"],
            "has_critical": overall["critical_runs"] > 0 or any(issue["severity"] == "critical" for issue in repeated_issues),
            "has_failed_required_stage": has_failed_required,
            "has_blocked_required_stage": has_blocked_required,
            "has_missing_required_artifacts": has_missing_required_artifacts,
            "has_repeated_error": any(issue["severity"] in {"error", "critical"} for issue in repeated_issues),
            "has_repeated_warning": any(issue["severity"] == "warning" for issue in repeated_issues),
        },
        "runtime_anomaly_status": "insufficient_data" if not runtime_anomalies else "detected",
    }
    write_json(TREND_DIR / "shadow_trend_analysis.json", payload)
    (TREND_DIR / "shadow_trend_analysis.md").write_text(render_analysis(payload), encoding="utf-8")
    return payload


def render_analysis(payload: dict[str, Any]) -> str:
    lines = [
        "# Shadow Trend Analysis",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- run_count: {payload['run_count']}",
        f"- runs_analyzed: {', '.join(payload['runs_analyzed'])}",
        "",
        "## Overall Trend",
    ]
    for key, value in payload["overall_trend"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Stage Trends", "| stage_id | stability | warning | error | critical | artifact_missing |", "|---|---|---:|---:|---:|---:|"])
    for row in payload["stage_trends"]:
        lines.append(f"| {row['stage_id']} | {row['stability']} | {row['warning_count']} | {row['error_count']} | {row['critical_count']} | {row['artifact_missing_count']} |")
    lines.extend(["", "## Repeated Issues"])
    lines.extend([f"- {issue['severity']} {issue['stage_id']} {issue['source']}: {issue['message']} ({issue['count']})" for issue in payload["repeated_issues"]] or ["- none"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Analyze multi-run agent shadow review trends.")
    ap.add_argument("--input", default=str(TREND_DIR / "multi_run_shadow_inputs.json"))
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = analyze(resolve_repo_path(args.input))
    print(json.dumps({"run_count": result["run_count"], "repeated_issue_count": len(result["repeated_issues"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
