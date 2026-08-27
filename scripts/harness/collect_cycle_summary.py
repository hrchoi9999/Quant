from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from cycle_common import read_cycle_state, run_dir, write_cycle_state
from harness_common import now_stamp, write_json


def _rel(path_text: str | None) -> str:
    return path_text or ""


def _parse_stamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _elapsed(start: Any, end: Any) -> str:
    start_dt = _parse_stamp(start)
    end_dt = _parse_stamp(end)
    if start_dt is None or end_dt is None or end_dt < start_dt:
        return ""
    seconds = int((end_dt - start_dt).total_seconds())
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _stage_table(stages: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| order | stage_id | thread | status | started_at | completed_at | elapsed | result | report |",
        "|---:|---|---|---|---|---|---:|---|---|",
    ]
    for row in stages:
        elapsed = _elapsed(row.get("started_at"), row.get("completed_at"))
        lines.append(
            f"| {row['order']} | {row['stage_id']} | {row.get('thread')} | {row.get('status')} | "
            f"{row.get('started_at') or ''} | {row.get('completed_at') or ''} | {elapsed} | "
            f"{_rel(row.get('result_file'))} | {_rel(row.get('stage_report_file'))} |"
        )
    return lines


def render_cycle_summary(state: dict[str, Any]) -> str:
    issues = [
        f"{row['stage_id']}: {row.get('error_message')}"
        for row in state["stages"]
        if row.get("status") in {"failed", "blocked", "skipped"} or row.get("error_message")
    ]
    lines = [
        "# Update Cycle Summary",
        "",
        "## Run",
        f"- run_id: {state['run_id']}",
        f"- cycle_type: {state['cycle_type']}",
        f"- mode: {state['mode']}",
        f"- status: {state['status']}",
        f"- started_at: {state.get('started_at')}",
        f"- completed_at: {state.get('completed_at')}",
        f"- total_elapsed: {_elapsed(state.get('started_at'), state.get('completed_at')) or 'unknown'}",
        f"- config: {state.get('config')}",
        "",
        "## Stage Results",
        *_stage_table(state["stages"]),
        "",
        "## Stop Reason",
        f"- {state.get('stop_reason') or 'none'}",
        "",
        "## Issues",
    ]
    lines.extend([f"- {issue}" for issue in issues] if issues else ["- none"])
    lines.extend(
        [
            "",
            "## Generated Files",
            "- cycle_state.json",
            "- cycle_plan.md",
            "- cycle_readiness.md",
            "- cycle_summary.md",
            "- final_summary.md",
            "",
            "## Next Action",
            "- Review failed/blocked stages before rerun." if issues else "- Proceed to the next planned harness task.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_final_summary(state: dict[str, Any]) -> str:
    completed = [row["stage_id"] for row in state["stages"] if row.get("status") in {"completed", "validated", "dry_run_completed"}]
    failed = [row["stage_id"] for row in state["stages"] if row.get("status") in {"failed", "blocked"}]
    files = ["cycle_state.json", "cycle_summary.md", "final_summary.md"]
    stage_elapsed = [
        f"- {row['stage_id']}: {_elapsed(row.get('started_at'), row.get('completed_at')) or 'unknown'}"
        for row in state["stages"]
    ]
    lines = [
        "# Final Update Cycle Report",
        "",
        "## Overall Status",
        f"- {state['status']}",
        "",
        "## Elapsed Time",
        f"- started_at: {state.get('started_at')}",
        f"- completed_at: {state.get('completed_at')}",
        f"- total_elapsed: {_elapsed(state.get('started_at'), state.get('completed_at')) or 'unknown'}",
        "",
        "## Stage Elapsed Time",
    ]
    lines.extend(stage_elapsed if stage_elapsed else ["- none"])
    lines.extend(
        [
            "",
            "## Completed Stages",
        ]
    )
    lines.extend([f"- {stage_id}" for stage_id in completed] if completed else ["- none"])
    lines.extend(["", "## Failed / Blocked Stages"])
    lines.extend([f"- {stage_id}" for stage_id in failed] if failed else ["- none"])
    lines.extend(["", "## Files to Review"])
    lines.extend([f"- {name}" for name in files])
    lines.extend(["", "## Next Recommended Step"])
    lines.append("- Fix blocked/failed stages and rerun from the appropriate point." if failed else "- TASK_UPDATE_HARNESS_05: Cycle Validation & Final Report Quality Gate")
    return "\n".join(lines) + "\n"


def collect(run_id: str) -> dict[str, str]:
    state = read_cycle_state(run_id)
    out_dir = run_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    state["completed_at"] = state.get("completed_at") or now_stamp()
    cycle_summary_path = out_dir / "cycle_summary.md"
    final_summary_path = out_dir / "final_summary.md"
    summary_json_path = out_dir / "cycle_summary.json"
    cycle_summary_path.write_text(render_cycle_summary(state), encoding="utf-8")
    final_summary_path.write_text(render_final_summary(state), encoding="utf-8")
    state["final_summary_file"] = str(final_summary_path)
    write_json(summary_json_path, {"state": state})
    write_cycle_state(state)
    return {
        "cycle_summary": str(cycle_summary_path),
        "final_summary": str(final_summary_path),
        "cycle_summary_json": str(summary_json_path),
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Collect cycle summary and final report.")
    ap.add_argument("--run-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(collect(args.run_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
