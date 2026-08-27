from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cycle_common import is_close_stage, run_dir
from harness_common import ROOT, read_json, read_yaml, resolve_repo_path, write_json

QUALITY_POLICY_PATH = ROOT / "config" / "harness" / "cycle_quality_gate_policy.yaml"


def _load_policy(path: Path = QUALITY_POLICY_PATH) -> dict[str, Any]:
    data = read_yaml(path)
    policy = data.get("cycle_quality_gate")
    if not isinstance(policy, dict):
        raise SystemExit(f"missing cycle_quality_gate policy: {path}")
    return policy


def _contains_sections(path: Path, sections: list[str]) -> list[str]:
    if not path.exists():
        return sections
    text = path.read_text(encoding="utf-8")
    return [section for section in sections if section not in text]


def _stage_file(path_text: str | None) -> Path | None:
    return Path(path_text) if path_text else None


def validate_cycle_outputs(run_id: str, policy_path: Path = QUALITY_POLICY_PATH) -> dict[str, Any]:
    policy = _load_policy(policy_path)
    base = run_dir(run_id)
    state_path = base / "cycle_state.json"
    checks: list[dict[str, Any]] = []
    issues: list[str] = []

    for name in policy["required_run_files"]:
        path = base / str(name)
        ok = path.exists()
        checks.append({"check": "required_run_file", "target": str(path), "ok": ok})
        if not ok:
            issues.append(f"missing_run_file:{name}")

    if not state_path.exists():
        return {
            "run_id": run_id,
            "status": "failed",
            "checks": checks,
            "issues": issues,
            "summary": {"missing_state": True, "issue_count": len(issues)},
        }

    state = read_json(state_path)
    mode = str(state.get("mode") or "")
    cycle_status = str(state.get("status") or "")
    config = str(state.get("config") or "")
    allowed_cycle_statuses = set(policy.get("allowed_cycle_statuses") or [])
    pass_cycle_statuses = set(policy.get("pass_cycle_statuses") or [])
    stage_success = set((policy.get("stage_success_by_mode") or {}).get(mode) or [])
    close_success = set(policy.get("close_stage_success_statuses") or [])
    fail_stage_statuses = set(policy.get("fail_stage_statuses") or [])

    if cycle_status not in allowed_cycle_statuses:
        issues.append(f"invalid_cycle_status:{cycle_status}")
    if cycle_status not in pass_cycle_statuses:
        issues.append(f"cycle_status_not_pass:{cycle_status}")
    if policy.get("block_operational_execute_safe") and mode == "execute-safe" and "stage_commands_operational" in config:
        issues.append("operational_execute_safe_detected")

    final_summary_file = _stage_file(state.get("final_summary_file"))
    if policy.get("require_final_summary_file_match") and final_summary_file != base / "final_summary.md":
        issues.append("final_summary_file_mismatch")

    for section in _contains_sections(base / "final_summary.md", list(policy.get("final_summary_required_sections") or [])):
        issues.append(f"final_summary_missing_section:{section}")
    for section in _contains_sections(base / "cycle_summary.md", list(policy.get("cycle_summary_required_sections") or [])):
        issues.append(f"cycle_summary_missing_section:{section}")

    for row in state.get("stages") or []:
        stage_id = str(row.get("stage_id") or "")
        status = str(row.get("status") or "")
        if is_close_stage(stage_id):
            if status not in close_success:
                issues.append(f"{stage_id}:invalid_close_status:{status}")
            continue

        if status in fail_stage_statuses:
            issues.append(f"{stage_id}:failed_or_blocked:{status}")
        if policy.get("require_no_skipped_for_pass") and status == "skipped":
            issues.append(f"{stage_id}:skipped")
        if status not in stage_success and cycle_status == "completed":
            issues.append(f"{stage_id}:unexpected_stage_status:{status}")
        if policy.get("require_no_error_message_for_pass") and row.get("error_message"):
            issues.append(f"{stage_id}:error_message:{row.get('error_message')}")

        for field, filename in [
            ("result_file", "result.json"),
            ("stage_report_file", "stage_report.md"),
            ("handoff_file", "handoff.md"),
        ]:
            path = _stage_file(row.get(field))
            if path is None or not path.exists():
                issues.append(f"{stage_id}:missing_{filename}")
                checks.append({"check": field, "stage_id": stage_id, "target": str(path), "ok": False})
            else:
                checks.append({"check": field, "stage_id": stage_id, "target": str(path), "ok": True})

        result_path = _stage_file(row.get("result_file"))
        if result_path and result_path.exists():
            result = read_json(result_path)
            if result.get("status") != status:
                issues.append(f"{stage_id}:state_result_status_mismatch:{status}!={result.get('status')}")

    status = "passed" if not issues else "failed"
    return {
        "run_id": run_id,
        "status": status,
        "cycle_status": cycle_status,
        "mode": mode,
        "config": config,
        "checks": checks,
        "issues": issues,
        "summary": {
            "issue_count": len(issues),
            "stage_count": len(state.get("stages") or []),
        },
    }


def render_quality_gate(result: dict[str, Any]) -> str:
    issue_count = int(result.get("summary", {}).get("issue_count", len(result.get("issues") or [])))
    lines = [
        "# Cycle Quality Gate",
        "",
        f"- run_id: {result['run_id']}",
        f"- status: {result['status']}",
        f"- cycle_status: {result.get('cycle_status')}",
        f"- mode: {result.get('mode')}",
        f"- issue_count: {issue_count}",
        "",
        "## Issues",
    ]
    lines.extend([f"- {issue}" for issue in result["issues"]] if result["issues"] else ["- none"])
    lines.extend(["", "## Checks"])
    for check in result["checks"]:
        target = check.get("target") or check.get("stage_id")
        lines.append(f"- {check['check']}: ok={check['ok']} target={target}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate cycle outputs and final report quality gate.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--policy", default=str(QUALITY_POLICY_PATH))
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    policy_path = resolve_repo_path(args.policy)
    result = validate_cycle_outputs(args.run_id, policy_path)
    out_dir = run_dir(args.run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cycle_quality_gate.json"
    md_path = out_dir / "cycle_quality_gate.md"
    write_json(json_path, result)
    md_path.write_text(render_quality_gate(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
