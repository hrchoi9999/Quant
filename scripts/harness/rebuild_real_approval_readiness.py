from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from filter_real_operational_runs import TREND_DIR, filter_real_runs
from harness_common import ROOT, now_stamp, read_json, read_yaml, write_json

POLICY_PATH = ROOT / "config" / "harness" / "agent_shadow_trend_policy.yaml"


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"_read_error": str(exc)}


def _issue_summary(run_id: str, run_dir: Path) -> dict[str, Any]:
    review = _safe_json(run_dir / "agent_shadow_review.json")
    state = _safe_json(run_dir / "cycle_state.json")
    severity = str(review.get("overall_severity") or "info")
    status = str(state.get("status") or review.get("overall_status") or "unknown")
    stage_statuses = Counter(str(row.get("status") or "unknown") for row in state.get("stages") or [] if isinstance(row, dict))
    warnings = [issue for issue in review.get("detected_issues") or [] if issue.get("severity") == "warning"]
    errors = [issue for issue in review.get("detected_issues") or [] if issue.get("severity") in {"error", "critical"}]
    return {
        "run_id": run_id,
        "status": status,
        "overall_severity": severity,
        "operation_safe_to_continue": bool(review.get("operation_safe_to_continue")),
        "requires_manual_review": bool(review.get("requires_manual_review")),
        "stage_status_counts": dict(stage_statuses),
        "warning_count": len(warnings),
        "error_or_critical_issue_count": len(errors),
        "has_critical": severity == "critical" or any(issue.get("severity") == "critical" for issue in review.get("detected_issues") or []),
        "has_error": severity == "error" or bool(errors),
        "has_failed_or_blocked": status in {"failed", "blocked"} or bool(stage_statuses.get("failed") or stage_statuses.get("blocked")),
    }


def rebuild() -> dict[str, Any]:
    real_path = TREND_DIR / "real_operational_runs.json"
    if not real_path.exists():
        filter_real_runs()
    real_runs = read_json(real_path)
    policy = (read_yaml(POLICY_PATH).get("agent_shadow_trend_policy") or {}).get("approval_readiness_rules") or {}
    minimum_clean = int(policy.get("minimum_clean_runs", 2))
    minimum_runs = max(minimum_clean, 2)

    summaries = []
    for row in real_runs.get("included_runs") or []:
        run_id = str(row["run_id"])
        summaries.append(_issue_summary(run_id, Path(str(row["run_dir"]))))

    clean_runs = [
        row
        for row in summaries
        if not row["has_critical"] and not row["has_error"] and not row["has_failed_or_blocked"] and row["warning_count"] == 0
    ]
    has_blocker = any(row["has_critical"] or row["has_error"] or row["has_failed_or_blocked"] for row in summaries)
    has_warning = any(row["warning_count"] for row in summaries)
    blockers: list[str] = []
    warnings: list[str] = []
    if len(summaries) < minimum_runs:
        status = "insufficient_data"
        recommendation = "collect_real_operational_pilot_runs"
        blockers.append(f"real run count {len(summaries)} is below required {minimum_runs}")
    elif has_blocker:
        status = "not_ready"
        recommendation = "fix_real_operational_run_blockers"
        blockers.extend(
            f"{row['run_id']} status={row['status']} severity={row['overall_severity']}"
            for row in summaries
            if row["has_critical"] or row["has_error"] or row["has_failed_or_blocked"]
        )
    elif len(clean_runs) < minimum_clean:
        status = "insufficient_data"
        recommendation = "collect_clean_real_runs"
        blockers.append(f"clean real run count {len(clean_runs)} is below required {minimum_clean}")
    elif has_warning:
        status = "ready_with_warnings"
        recommendation = "manual_review_before_approval_request"
        warnings.append("real runs contain warnings")
    else:
        status = "ready"
        recommendation = "real_approval_request_allowed"

    payload = {
        "generated_at": now_stamp(),
        "approval_readiness": status,
        "recommendation": recommendation,
        "reason": "; ".join(blockers or warnings or ["real operational readiness conditions passed"]),
        "real_run_count": len(summaries),
        "clean_real_run_count": len(clean_runs),
        "minimum_real_runs_required": minimum_runs,
        "fixture_runs_excluded": True,
        "real_readiness_required": True,
        "included_real_runs": [row["run_id"] for row in summaries],
        "run_summaries": summaries,
        "blocking_issues": blockers,
        "warnings": warnings,
        "source_real_operational_runs": str(real_path),
    }
    write_json(TREND_DIR / "real_approval_readiness_report.json", payload)
    (TREND_DIR / "real_approval_readiness_report.md").write_text(render_report(payload), encoding="utf-8")
    return payload


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Real Approval Readiness Report",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- approval_readiness: {payload['approval_readiness']}",
        f"- recommendation: {payload['recommendation']}",
        f"- reason: {payload['reason']}",
        f"- real_run_count: {payload['real_run_count']}",
        f"- clean_real_run_count: {payload['clean_real_run_count']}",
        f"- fixture_runs_excluded: {payload['fixture_runs_excluded']}",
        "",
        "## Included Real Runs",
    ]
    lines.extend([f"- {run_id}" for run_id in payload["included_real_runs"]] or ["- none"])
    lines.extend(["", "## Blocking Issues"])
    lines.extend([f"- {item}" for item in payload["blocking_issues"]] or ["- none"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in payload["warnings"]] or ["- none"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="Rebuild approval readiness from real operational runs only.").parse_args()


def main() -> None:
    parse_args()
    result = rebuild()
    print(json.dumps({"approval_readiness": result["approval_readiness"], "real_run_count": result["real_run_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
