from __future__ import annotations

import argparse
import json
from typing import Any

from analyze_shadow_review_trends import POLICY_PATH, TREND_DIR, analyze
from harness_common import read_json, read_yaml, write_json


def _condition(name: str, required: bool, passed: bool, detail: str) -> dict[str, Any]:
    return {"condition": name, "required": required, "passed": passed, "detail": detail}


def evaluate() -> dict[str, Any]:
    analysis_path = TREND_DIR / "shadow_trend_analysis.json"
    if not analysis_path.exists():
        analyze()
    analysis = read_json(analysis_path)
    policy = (read_yaml(POLICY_PATH).get("agent_shadow_trend_policy") or {}).get("approval_readiness_rules") or {}
    inputs = analysis["approval_readiness_inputs"]
    minimum_clean = int(policy.get("minimum_clean_runs", 2))
    conditions = [
        _condition("minimum_runs_met", True, bool(inputs["minimum_runs_met"]), f"run_count={analysis['run_count']}"),
        _condition("no_critical", bool(policy.get("require_no_critical", True)), not bool(inputs["has_critical"]), str(inputs["has_critical"])),
        _condition("no_failed_required_stage", bool(policy.get("require_no_failed_required_stage", True)), not bool(inputs["has_failed_required_stage"]), str(inputs["has_failed_required_stage"])),
        _condition("no_blocked_required_stage", bool(policy.get("require_no_blocked_required_stage", True)), not bool(inputs["has_blocked_required_stage"]), str(inputs["has_blocked_required_stage"])),
        _condition("no_missing_required_artifacts", bool(policy.get("require_no_missing_required_artifacts", True)), not bool(inputs["has_missing_required_artifacts"]), str(inputs["has_missing_required_artifacts"])),
        _condition("minimum_clean_runs", True, int(inputs["clean_runs"]) >= minimum_clean, f"clean_runs={inputs['clean_runs']} required={minimum_clean}"),
    ]
    required_failed = [row for row in conditions if row["required"] and not row["passed"]]
    warnings = []
    blockers = []
    if not inputs["minimum_runs_met"]:
        readiness = "insufficient_data"
        recommendation = "continue_shadow_review"
        blockers.append("minimum run count is not met")
    elif inputs["has_critical"] or inputs["has_failed_required_stage"] or inputs["has_blocked_required_stage"] or inputs["has_repeated_error"]:
        readiness = "not_ready"
        recommendation = "do_not_proceed" if inputs["has_critical"] else "fix_repeated_stage_issues"
        blockers.extend([row["condition"] for row in required_failed])
    elif inputs["has_missing_required_artifacts"]:
        readiness = "not_ready"
        recommendation = "fix_artifact_contracts"
        blockers.append("missing required artifacts")
    elif inputs["clean_runs"] < minimum_clean:
        readiness = "insufficient_data"
        recommendation = "continue_shadow_review"
        warnings.append("not enough clean runs")
    elif inputs["has_repeated_warning"]:
        readiness = "ready_with_warnings"
        recommendation = "continue_shadow_review"
        warnings.append("repeated warnings require manual review")
    else:
        readiness = "ready"
        recommendation = "proceed_to_approval_harness"
    payload = {
        "approval_readiness": readiness,
        "recommendation": recommendation,
        "reason": "; ".join(blockers or warnings or ["all required conditions passed"]),
        "required_conditions": conditions,
        "blocking_issues": blockers,
        "warnings": warnings,
        "analysis_file": str(analysis_path),
    }
    write_json(TREND_DIR / "approval_readiness_report.json", payload)
    (TREND_DIR / "approval_readiness_report.md").write_text(render_report(payload), encoding="utf-8")
    return payload


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Approval Readiness Report",
        "",
        "## Judgment",
        f"- approval_readiness: {payload['approval_readiness']}",
        f"- recommendation: {payload['recommendation']}",
        f"- reason: {payload['reason']}",
        "",
        "## Required Conditions",
        "| condition | required | passed | detail |",
        "|---|---:|---:|---|",
    ]
    for row in payload["required_conditions"]:
        lines.append(f"| {row['condition']} | {row['required']} | {row['passed']} | {row['detail']} |")
    lines.extend(["", "## Blocking Issues"])
    lines.extend([f"- {item}" for item in payload["blocking_issues"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in payload["warnings"]] or ["- none"])
    lines.extend(["", "## Next Step"])
    lines.append("- Proceed only by explicit human task. This report does not grant approval authority.")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Evaluate readiness to design approval harness from shadow trend analysis.")
    return ap.parse_args()


def main() -> None:
    result = evaluate()
    print(json.dumps({"approval_readiness": result["approval_readiness"], "recommendation": result["recommendation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
