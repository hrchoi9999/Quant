from __future__ import annotations

import argparse
import json

from cycle_common import run_dir
from harness_common import read_json


def build(run_id: str) -> dict[str, str]:
    root = run_dir(run_id)
    review_path = root / "agent_shadow_review.json"
    if not review_path.exists():
        raise SystemExit(f"missing agent_shadow_review.json: {review_path}")
    review = read_json(review_path)
    recommendation = str(review.get("next_action_recommendation") or "do_not_continue")
    severity = str(review.get("overall_severity") or "unknown")
    safe = bool(review.get("operation_safe_to_continue"))
    manual = bool(review.get("requires_manual_review"))
    blockers = [
        issue["message"]
        for issue in review.get("detected_issues") or []
        if issue.get("severity") in {"error", "critical"}
    ]
    if recommendation == "review_warnings" and not blockers:
        reason = "Warnings were detected during shadow review."
    elif safe:
        reason = "No error or critical issue was detected."
    else:
        reason = "Shadow review found blocking or incomplete conditions."
    text = "\n".join(
        [
            "# Agent Next Action Recommendation",
            "",
            "## Recommendation",
            f"- {recommendation}",
            "",
            "## Reason",
            f"- {reason}",
            f"- overall_severity: {severity}",
            f"- operation_safe_to_continue: {str(safe).lower()}",
            f"- requires_manual_review: {str(manual).lower()}",
            "",
            "## Required Human Check",
            "- Review agent_shadow_review.md before any operational rerun or approval change.",
            "",
            "## Blockers",
            *([f"- {item}" for item in blockers] if blockers else ["- none"]),
            "",
            "## Suggested Next Task",
            "- TASK_AGENT_SHADOW_02 or TASK_APPROVAL_HARNESS_01",
            "",
            "## Safety Note",
            "- This recommendation is not an automatic execution instruction.",
        ]
    )
    out = root / "agent_next_action_recommendation.md"
    out.write_text(text + "\n", encoding="utf-8")
    return {"recommendation": recommendation, "path": str(out)}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build next action recommendation from agent shadow review.")
    ap.add_argument("--run-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(build(args.run_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
