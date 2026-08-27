from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from collect_cycle_summary import collect as collect_cycle_summary
from collect_stage_report import render_report
from cycle_common import (
    initial_cycle_state,
    is_close_stage,
    is_default_safe_config,
    render_cycle_plan,
    run_dir,
    stage_plan_rows,
    state_path,
    validate_cycle,
    write_cycle_state,
)
from harness_common import COMMANDS_PATH, now_stamp, read_json, resolve_repo_path, stage_dir, write_json
from run_stage import run_stage


def _write_plan(run_id: str, cycle_type: str, mode: str, config_path: Path) -> None:
    rows = stage_plan_rows(cycle_type, config_path)
    out_dir = run_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        out_dir / "cycle_plan.json",
        {"run_id": run_id, "cycle_type": cycle_type, "mode": mode, "config": str(config_path), "stages": rows},
    )
    (out_dir / "cycle_plan.md").write_text(render_cycle_plan(run_id, cycle_type, mode, config_path, rows), encoding="utf-8")


def _write_readiness(run_id: str, cycle_type: str, config_path: Path, *, for_execute: bool) -> dict[str, Any]:
    result = validate_cycle(cycle_type, config_path, for_execute=for_execute)
    payload = {"run_id": run_id, "cycle_type": cycle_type, "config": str(config_path), **result}
    out_dir = run_dir(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "cycle_readiness.json", payload)
    lines = [
        "# Cycle Readiness",
        "",
        f"- run_id: {run_id}",
        f"- cycle_type: {cycle_type}",
        f"- status: {payload['status']}",
        f"- reason: {payload.get('reason') or 'none'}",
        "",
        "| order | stage_id | status | issues |",
        "|---:|---|---|---|",
    ]
    for row in payload["stage_results"]:
        issues = ", ".join(row.get("issues") or []) or "none"
        lines.append(f"| {row['order']} | {row['stage_id']} | {row['status']} | {issues} |")
    (out_dir / "cycle_readiness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def _update_stage(state: dict[str, Any], stage_id: str, **updates: Any) -> dict[str, Any]:
    for row in state["stages"]:
        if row["stage_id"] == stage_id:
            row.update(updates)
            return row
    raise SystemExit(f"stage not found in cycle_state: {stage_id}")


def _mark_skipped_after_stop(state: dict[str, Any], stop_stage_id: str) -> None:
    seen = False
    for row in state["stages"]:
        if row["stage_id"] == stop_stage_id:
            seen = True
            continue
        if seen and row["status"] == "pending":
            row["status"] = "skipped"
            row["error_message"] = "skipped after prior stage stopped cycle"


def _collect_stage_report(run_id: str, stage_id: str) -> str:
    out_dir = stage_dir(run_id, stage_id)
    result_path = out_dir / "result.json"
    if not result_path.exists():
        raise SystemExit(f"missing stage result: {result_path}")
    report_path = out_dir / "stage_report.md"
    report_path.write_text(render_report(read_json(result_path)), encoding="utf-8")
    return str(report_path)


def _stage_can_continue(mode: str, status: str) -> bool:
    if mode == "dry-run":
        return status == "dry_run_completed"
    return status in {"completed", "validated"}


def run_cycle(run_id: str, cycle_type: str, mode: str, config_path: Path, *, asof: str | None = None) -> dict[str, Any]:
    config_path = resolve_repo_path(config_path)
    if mode == "execute-safe" and not is_default_safe_config(config_path):
        message = "BLOCKED: operational config execute-safe is not allowed because allow_operational_execute=false."
        raise SystemExit(message)

    _write_plan(run_id, cycle_type, mode, config_path)
    readiness = _write_readiness(run_id, cycle_type, config_path, for_execute=(mode == "execute-safe"))
    state = initial_cycle_state(run_id, cycle_type, mode, config_path, status="planned" if mode == "plan" else "running")

    if mode == "plan":
        for row in state["stages"]:
            row["status"] = "planned"
        state["completed_at"] = now_stamp()
        write_cycle_state(state)
        return {"status": state["status"], "cycle_state": str(state_path(run_id))}

    if mode == "execute-safe" and readiness["status"] in {"blocked", "not_ready"}:
        state["status"] = "blocked"
        state["stop_reason"] = readiness.get("reason") or "cycle readiness failed for execute-safe"
        state["completed_at"] = now_stamp()
        for row in state["stages"]:
            row["status"] = "skipped"
            row["error_message"] = state["stop_reason"]
        write_cycle_state(state)
        collect_cycle_summary(run_id)
        return {"status": state["status"], "cycle_state": str(state_path(run_id))}

    stage_ids = [row["stage_id"] for row in state["stages"]]
    for stage_id in stage_ids:
        state["current_stage"] = stage_id
        if is_close_stage(stage_id):
            _update_stage(state, stage_id, status="completed", started_at=now_stamp(), completed_at=now_stamp())
            state["status"] = "completed"
            state["completed_at"] = now_stamp()
            write_cycle_state(state)
            collect_cycle_summary(run_id)
            break

        started_at = now_stamp()
        _update_stage(state, stage_id, status="running", started_at=started_at)
        write_cycle_state(state)

        result = run_stage(run_id, stage_id, execute=(mode == "execute-safe"), config_path=config_path, asof=asof)
        result_file = str(result["result_path"])
        handoff_file = str(result["handoff_path"])
        report_file = _collect_stage_report(run_id, stage_id)
        status = str(result.get("status"))
        error_message = result.get("error_message")
        _update_stage(
            state,
            stage_id,
            status=status,
            completed_at=now_stamp(),
            result_file=result_file,
            stage_report_file=report_file,
            handoff_file=handoff_file,
            error_message=error_message,
        )
        if not _stage_can_continue(mode, status):
            state["status"] = "blocked" if status == "blocked" else "failed"
            state["stop_reason"] = error_message or f"stage stopped cycle with status={status}"
            state["completed_at"] = now_stamp()
            _mark_skipped_after_stop(state, stage_id)
            write_cycle_state(state)
            collect_cycle_summary(run_id)
            break
        write_cycle_state(state)

    return {"status": read_json(state_path(run_id))["status"], "cycle_state": str(state_path(run_id))}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run a weekday/weekend update cycle through configured harness stages.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cycle-type", choices=["weekday", "weekend"], required=True)
    ap.add_argument("--mode", choices=["plan", "dry-run", "execute-safe"], default="dry-run")
    ap.add_argument("--config", default=str(COMMANDS_PATH))
    ap.add_argument("--asof", default=None, help="Bind {asof} in configured command templates.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = run_cycle(args.run_id, args.cycle_type, args.mode, resolve_repo_path(args.config), asof=args.asof)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
