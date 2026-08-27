from __future__ import annotations

import argparse
import json

from analyze_shadow_review_trends import TREND_DIR, analyze
from harness_common import read_json


def build() -> dict[str, str]:
    path = TREND_DIR / "shadow_trend_analysis.json"
    if not path.exists():
        analyze()
    data = read_json(path)
    lines = [
        "# Agent Shadow Trend Report",
        "",
        "## Scope",
        f"- generated_at: {data['generated_at']}",
        f"- run_count: {data['run_count']}",
        f"- runs_analyzed: {', '.join(data['runs_analyzed'])}",
        "",
        "## Overall Trend",
    ]
    for key, value in data["overall_trend"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Stage Stability",
            "| stage_id | thread | completed | failed | blocked | warning | error | critical | missing_artifact | stability |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in data["stage_trends"]:
        lines.append(
            f"| {row['stage_id']} | {row.get('thread')} | {row['completed_count']} | {row['failed_count']} | "
            f"{row['blocked_count']} | {row['warning_count']} | {row['error_count']} | {row['critical_count']} | "
            f"{row['artifact_missing_count']} | {row['stability']} |"
        )
    lines.extend(["", "## Repeated Issues", "| severity | stage_id | source | count | message |", "|---|---|---|---:|---|"])
    for issue in data["repeated_issues"]:
        lines.append(f"| {issue['severity']} | {issue['stage_id']} | {issue['source']} | {issue['count']} | {issue['message']} |")
    if not data["repeated_issues"]:
        lines.append("| info | none | none | 0 | none |")
    lines.extend(["", "## Artifact Contract Issues", "| stage_id | missing_count | missing_artifacts |", "|---|---:|---|"])
    for issue in data["artifact_contract_issues"]:
        lines.append(f"| {issue['stage_id']} | {issue['missing_count']} | {', '.join(issue['missing_artifacts'])} |")
    if not data["artifact_contract_issues"]:
        lines.append("| none | 0 | none |")
    lines.extend(["", "## Runtime Anomalies", "| stage_id | baseline | latest | ratio | severity |", "|---|---:|---:|---:|---|"])
    for item in data["runtime_anomalies"]:
        lines.append(f"| {item['stage_id']} | {item['baseline']:.2f} | {item['latest']:.2f} | {item['ratio']:.2f} | {item['severity']} |")
    if not data["runtime_anomalies"]:
        lines.append("| none | 0 | 0 | 0 | insufficient_data |")
    lines.extend(["", "## Approval / Preflight Issues", "| stage_id | issue | count |", "|---|---|---:|"])
    for issue in data["approval_preflight_issues"]:
        lines.append(f"| {issue['stage_id']} | {issue['issue']} | {issue['count']} |")
    if not data["approval_preflight_issues"]:
        lines.append("| none | none | 0 |")
    readiness = data["approval_readiness_inputs"]
    lines.extend(
        [
            "",
            "## Operational Interpretation",
            f"- minimum_runs_met: {readiness['minimum_runs_met']}",
            f"- has_critical: {readiness['has_critical']}",
            f"- has_repeated_error: {readiness['has_repeated_error']}",
            f"- has_repeated_warning: {readiness['has_repeated_warning']}",
            "",
            "## Next Suggested Action",
            "- Run approval readiness evaluation before approval harness design.",
        ]
    )
    out = TREND_DIR / "shadow_trend_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"shadow_trend_report": str(out)}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build a human-readable shadow trend report.")
    return ap.parse_args()


def main() -> None:
    print(json.dumps(build(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
