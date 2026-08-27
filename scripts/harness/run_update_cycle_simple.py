from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from cycle_common import run_dir
from harness_common import OPERATIONAL_COMMANDS_PATH, ROOT, now_stamp, read_json, write_json
from run_manual_approved_cycle import run_manual_cycle
from run_update_cycle import run_cycle

REAL_READINESS_PATH = ROOT / "reports" / "agent_shadow_trends" / "real_approval_readiness_report.json"
APPROVAL_ROOT = ROOT / "reports" / "harness_approvals"
FORBIDDEN_COMBINED_CYCLE_REASON = "weekday_weekend_combined_run_forbidden"
FIRST_REAL_WEEKDAY_STAGES = {"WD02_MARKET_COLLECT", "WD03_MARKET_ANALYSIS", "WD05_PORTFOLIO_ANALYSIS"}
FIRST_FULL_WEEKDAY_STAGES = {
    "WD01_QUANT_FRONT",
    "WD02_MARKET_COLLECT",
    "WD03_MARKET_ANALYSIS",
    "WD04_QUANT_REAR",
    "WD05_PORTFOLIO_ANALYSIS",
    "WD06_PRE_GCS_PUBLISH",
}


def _default_run_id(cycle: str, mode: str, asof: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_asof = asof.replace("-", "")
    return f"{stamp}_simple_{cycle}_{mode}_{safe_asof}"


def _target_cycles(cycle: str) -> list[str]:
    if cycle == "all":
        raise SystemExit(FORBIDDEN_COMBINED_CYCLE_REASON)
    return [cycle]


def _mode(args: argparse.Namespace) -> str:
    if args.execute:
        return "execute"
    if args.plan:
        return "plan"
    return "dry-run"


def _approval_id_for(args: argparse.Namespace, cycle: str) -> str | None:
    return args.approval_id


def _readiness_status() -> str:
    if not REAL_READINESS_PATH.exists():
        return "missing"
    return str(read_json(REAL_READINESS_PATH).get("approval_readiness") or "unknown")


def _approval_request(approval_id: str | None) -> dict[str, Any]:
    if not approval_id:
        return {}
    path = APPROVAL_ROOT / approval_id / "approval_request.json"
    return read_json(path) if path.exists() else {}


def _first_real_readiness_exception_allowed(args: argparse.Namespace, cycle: str, readiness: str) -> bool:
    if readiness != "insufficient_data" or cycle != "weekday":
        return False
    request = _approval_request(_approval_id_for(args, cycle))
    if request.get("approval_scope") == "first_full_weekday_pilot":
        return all(
            [
                request.get("target_cycle_type") == "weekday",
                set(request.get("target_stage_ids") or []) == FIRST_FULL_WEEKDAY_STAGES,
                bool(request.get("real_readiness_exception_approved")),
                bool(request.get("external_root_execution_approved")),
                bool(request.get("single_run_only")),
                bool(request.get("weekday_weekend_combined_run_forbidden")),
                request.get("auto_repeat_allowed") is False,
            ]
        )
    return all(
        [
            request.get("approval_scope") == "first_real_weekday_pilot",
            request.get("target_cycle_type") == "weekday",
            set(request.get("target_stage_ids") or []) == FIRST_REAL_WEEKDAY_STAGES,
            bool(request.get("real_readiness_exception_approved")),
            bool(request.get("external_root_execution_approved")),
            bool(request.get("single_run_only")),
            bool(request.get("weekday_weekend_combined_run_forbidden")),
            request.get("auto_repeat_allowed") is False,
        ]
    )


def _execute_blockers(args: argparse.Namespace, cycles: list[str]) -> list[str]:
    if not args.execute:
        return []
    blockers = []
    readiness = _readiness_status()
    first_real_exception = any(_first_real_readiness_exception_allowed(args, cycle, readiness) for cycle in cycles)
    if readiness not in {"ready", "ready_with_warnings"} and not first_real_exception:
        blockers.append(f"real_readiness:{readiness}")
    for cycle in cycles:
        if not _approval_id_for(args, cycle):
            blockers.append(f"{cycle}:approval_id_missing")
    return blockers


def _cycle_run_id(base_run_id: str, cycle: str, total_cycles: int) -> str:
    if total_cycles == 1:
        return base_run_id
    return f"{base_run_id}_{cycle}"


def _run_one_cycle(args: argparse.Namespace, cycle: str, run_id: str, mode: str) -> dict[str, Any]:
    if mode == "plan" or (mode == "dry-run" and not args.approval_id):
        return {
            "cycle": cycle,
            "run_id": run_id,
            "mode": mode,
            **run_cycle(run_id, cycle, mode, OPERATIONAL_COMMANDS_PATH, asof=args.asof),
        }
    if mode == "dry-run" and args.approval_id:
        return {
            "cycle": cycle,
            "run_id": run_id,
            "mode": "approval-gated-dry-run",
            "approval_id": args.approval_id,
            **run_manual_cycle(run_id, cycle, None, execute=False, approval_id=args.approval_id, asof=args.asof),
        }
    approval_id = _approval_id_for(args, cycle)
    if not approval_id:
        return {"cycle": cycle, "run_id": run_id, "mode": mode, "status": "blocked", "error_message": "approval_id_missing"}
    return {
        "cycle": cycle,
        "run_id": run_id,
        "mode": mode,
        "approval_id": approval_id,
        **run_manual_cycle(run_id, cycle, None, execute=True, approval_id=approval_id, asof=args.asof),
    }


def _overall_status(results: list[dict[str, Any]], blockers: list[str]) -> str:
    if blockers:
        return "blocked"
    statuses = {str(row.get("status") or "") for row in results}
    if not results:
        return "blocked"
    if statuses <= {"completed", "planned"}:
        return "completed"
    if statuses <= {"completed", "planned", "approved_for_manual_cycle", "ready_for_dry_run"}:
        return "completed"
    if any(status in {"failed", "blocked", "not_ready"} for status in statuses):
        return "blocked"
    return "review_required"


def render_summary(payload: dict[str, Any]) -> str:
    lines = [
        "# Simple Update Cycle Run",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- operator_run_id: {payload['operator_run_id']}",
        f"- cycle: {payload['cycle']}",
        f"- mode: {payload['mode']}",
        f"- asof: {payload['asof']}",
        f"- status: {payload['status']}",
        f"- real_readiness: {payload['real_readiness']}",
        "",
        "## Results",
        "| cycle | run_id | status | cycle_state |",
        "|---|---|---|---|",
    ]
    for row in payload["results"]:
        lines.append(f"| {row.get('cycle')} | {row.get('run_id')} | {row.get('status')} | {row.get('cycle_state')} |")
    lines.extend(["", "## Blockers"])
    lines.extend([f"- {item}" for item in payload["blockers"]] or ["- none"])
    lines.extend(["", "## Operator View"])
    if payload["mode"] == "execute":
        lines.append("- Execute mode is allowed only with real readiness and explicit approval IDs.")
    elif any(str(row.get("mode")) == "approval-gated-dry-run" for row in payload["results"]):
        lines.append("- This run used approval gate validation for dry-run only. It did not execute operational commands.")
    else:
        lines.append("- This run did not execute operational commands.")
    return "\n".join(lines) + "\n"


def run_simple(args: argparse.Namespace) -> dict[str, Any]:
    mode = _mode(args)
    operator_run_id = args.run_id or _default_run_id(args.cycle, mode, args.asof)
    if args.cycle == "all":
        payload = {
            "generated_at": now_stamp(),
            "operator_run_id": operator_run_id,
            "cycle": args.cycle,
            "mode": mode,
            "asof": args.asof,
            "real_readiness": _readiness_status(),
            "status": "blocked",
            "blockers": [FORBIDDEN_COMBINED_CYCLE_REASON],
            "results": [],
        }
        out = run_dir(operator_run_id)
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "operator_summary.json", payload)
        (out / "operator_summary.md").write_text(render_summary(payload), encoding="utf-8")
        return payload
    cycles = _target_cycles(args.cycle)
    blockers = _execute_blockers(args, cycles)
    results: list[dict[str, Any]] = []
    if not blockers:
        for cycle in cycles:
            cycle_run_id = _cycle_run_id(operator_run_id, cycle, len(cycles))
            results.append(_run_one_cycle(args, cycle, cycle_run_id, mode))
    payload = {
        "generated_at": now_stamp(),
        "operator_run_id": operator_run_id,
        "cycle": args.cycle,
        "mode": mode,
        "asof": args.asof,
        "real_readiness": _readiness_status(),
        "status": _overall_status(results, blockers),
        "blockers": blockers,
        "results": results,
    }
    out = run_dir(operator_run_id)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "operator_summary.json", payload)
    (out / "operator_summary.md").write_text(render_summary(payload), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Simple operator wrapper for weekday/weekend update cycles.")
    ap.add_argument("--cycle", choices=["weekday", "weekend"], required=True)
    ap.add_argument("--asof", required=True)
    ap.add_argument("--run-id", default=None)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    ap.add_argument("--approval-id", default=None)
    return ap.parse_args()


def main() -> None:
    result = run_simple(parse_args())
    print(json.dumps({"status": result["status"], "operator_run_id": result["operator_run_id"]}, ensure_ascii=False, indent=2))
    if result["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
