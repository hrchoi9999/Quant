from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_common import read_json, stage_dir


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _list_items(values: list[str]) -> str:
    if not values:
        return "  - none"
    return "\n".join(f"  - {value}" for value in values)


def render_manual_report(result: dict[str, Any], stage_path: Path) -> str:
    approval = result.get("approval") or {}
    preflight = result.get("preflight") or {}
    artifact = result.get("artifact_validation") or {}
    stdout_path = stage_path / "stdout.log"
    stderr_path = stage_path / "stderr.log"
    issues = []
    if result.get("error_message"):
        issues.append(str(result["error_message"]))
    if result.get("status") in {"failed", "blocked"}:
        issues.append(f"status={result.get('status')}")
    return f"""# Manual Operational Stage Execution Report

## Run
- run_id: {result.get("run_id")}
- stage_id: {result.get("stage_id")}
- thread: {result.get("thread")}
- action: {result.get("action")}
- command: {result.get("command")}
- working_dir: {result.get("working_dir")}
- execution_type: {result.get("execution_type")}
- approval_status: {result.get("approval_status")}
- approval_scope: {result.get("approval_scope")}
- status: {result.get("status")}
- return_code: {result.get("return_code")}

## Approval
- approval_file: {result.get("approval_file")}
- approved_by: {approval.get("approved_by")}
- approved_at: {approval.get("approved_at")}
- notes: {approval.get("notes")}

## Approval Gate
- approval_id: {result.get("approval_id")}
- gate_status: {result.get("approval_gate_status")}
- approval_based_execution: {result.get("approval_based_execution")}
- execution_approval_resolution_file: {result.get("execution_approval_resolution_file")}
- execution_approval_trace_file: {result.get("execution_approval_trace_file")}
- block_reason: {result.get("error_message") if result.get("approval_gate_checked") and result.get("status") == "blocked" else None}

## Preflight
- status: {preflight.get("status")}
- thread_root_match: {preflight.get("thread_root_match")}
- entrypoint_exists: {preflight.get("entrypoint_exists")}
- blocked_pattern: {preflight.get("blocked")}
- risk_level: {preflight.get("risk_level")}

## Execution Logs
- stdout: stdout.log ({len(_read_text(stdout_path))} chars)
- stderr: stderr.log ({len(_read_text(stderr_path))} chars)

## Artifact Validation
- status: {artifact.get("status")}
- found:
{_list_items(list(artifact.get("found") or []))}
- missing:
{_list_items(list(artifact.get("missing") or []))}

## Result
- {result.get("status")}

## Issues
{_list_items(issues)}

## Next Recommended Step
- Review this report before any additional manual operational pilot.
"""


def collect(run_id: str, stage_id: str) -> Path:
    path = stage_dir(run_id, stage_id)
    result_path = path / "result.json"
    if not result_path.exists():
        raise SystemExit(f"missing result.json: {result_path}")
    result = read_json(result_path)
    out = path / "manual_execution_report.md"
    out.write_text(render_manual_report(result, path), encoding="utf-8")
    return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Collect a manual operational execution report.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    out = collect(args.run_id, args.stage_id)
    print(json.dumps({"manual_execution_report": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
