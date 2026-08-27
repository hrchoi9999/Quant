from __future__ import annotations

from pathlib import Path
from typing import Any

from harness_common import (
    COMMANDS_PATH,
    ROOT,
    RUNS_DIR,
    command_matches_blocked_pattern,
    find_command_entrypoint,
    load_stage_commands,
    load_thread_roles,
    now_stamp,
    read_json,
    read_yaml,
    resolve_repo_path,
    risk_policy_allows,
    stage_dir,
    write_json,
)

CYCLE_POLICY_PATH = ROOT / "config" / "harness" / "cycle_runner_policy.yaml"
CLOSE_STAGE_SUFFIX = "_HARNESS_CLOSE"


def load_cycle_policy(path: Path = CYCLE_POLICY_PATH) -> dict[str, Any]:
    return read_yaml(path)


def cycle_stage_ids(cycle_type: str, policy: dict[str, Any] | None = None) -> list[str]:
    policy = policy or load_cycle_policy()
    row = (policy.get("cycle_types") or {}).get(cycle_type)
    if not isinstance(row, dict):
        raise SystemExit(f"unsupported cycle_type: {cycle_type}")
    stages = row.get("stages")
    if not isinstance(stages, list):
        raise SystemExit(f"missing stage list for cycle_type: {cycle_type}")
    return [str(stage_id) for stage_id in stages]


def is_close_stage(stage_id: str) -> bool:
    return stage_id.endswith(CLOSE_STAGE_SUFFIX)


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def is_default_safe_config(config_path: Path) -> bool:
    return resolve_repo_path(config_path).resolve() == COMMANDS_PATH.resolve()


def config_label(config_path: Path) -> str:
    path = resolve_repo_path(config_path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def stage_plan_rows(cycle_type: str, config_path: Path = COMMANDS_PATH) -> list[dict[str, Any]]:
    config_path = resolve_repo_path(config_path)
    commands = load_stage_commands(config_path)
    rows: list[dict[str, Any]] = []
    for order, stage_id in enumerate(cycle_stage_ids(cycle_type), start=1):
        if is_close_stage(stage_id):
            rows.append(
                {
                    "order": order,
                    "stage_id": stage_id,
                    "thread": "Quant",
                    "action": "Harness close and summary generation",
                    "command": None,
                    "working_dir": str(ROOT),
                    "risk_level": "low",
                    "safe_run": True,
                    "command_status": "close_stage",
                    "close_stage": True,
                }
            )
            continue
        config = commands.get(stage_id)
        if not isinstance(config, dict):
            rows.append(
                {
                    "order": order,
                    "stage_id": stage_id,
                    "thread": None,
                    "action": None,
                    "command": None,
                    "working_dir": None,
                    "risk_level": None,
                    "safe_run": None,
                    "command_status": None,
                    "close_stage": False,
                    "missing_config": True,
                }
            )
            continue
        rows.append(
            {
                "order": order,
                "stage_id": stage_id,
                "thread": config.get("thread"),
                "action": config.get("action"),
                "command": config.get("command"),
                "working_dir": config.get("working_dir"),
                "risk_level": config.get("risk_level"),
                "safe_run": bool(config.get("safe_run")),
                "command_status": config.get("command_status"),
                "close_stage": False,
                "missing_config": False,
            }
        )
    return rows


def render_cycle_plan(run_id: str, cycle_type: str, mode: str, config_path: Path, rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Update Cycle Plan",
        "",
        f"- run_id: {run_id}",
        f"- cycle_type: {cycle_type}",
        f"- mode: {mode}",
        f"- config: {config_label(config_path)}",
        "",
        "| order | stage_id | thread | risk | command_status | command |",
        "|---:|---|---|---|---|---|",
    ]
    for row in rows:
        command = str(row.get("command") or "close")
        lines.append(
            f"| {row['order']} | {row['stage_id']} | {row.get('thread')} | {row.get('risk_level')} | "
            f"{row.get('command_status')} | `{command}` |"
        )
    return "\n".join(lines) + "\n"


def readiness_for_stage(row: dict[str, Any], roles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if row.get("close_stage"):
        return {
            **row,
            "status": "ready",
            "issues": [],
            "blocked": False,
            "entrypoint": None,
            "entrypoint_exists": None,
        }
    issues: list[str] = []
    blocked = False
    thread = str(row.get("thread") or "")
    root = Path(str((roles.get(thread) or {}).get("root") or ""))
    working_dir = Path(str(row.get("working_dir") or ""))
    command = str(row.get("command") or "").strip()
    risk_level = str(row.get("risk_level") or "").lower()
    entrypoint = find_command_entrypoint(command, working_dir=str(working_dir)) if command else None
    blocked_pattern = command_matches_blocked_pattern(command) if command else None

    if row.get("missing_config"):
        issues.append("stage_command_config_missing")
    if not command:
        issues.append("command_not_registered")
    if not working_dir.exists():
        issues.append("working_dir_missing")
        blocked = True
    if root and working_dir != root:
        issues.append("working_dir_not_thread_root")
    if command and entrypoint is None:
        issues.append("entrypoint_not_detected")
    if entrypoint is not None and not entrypoint.exists():
        issues.append("entrypoint_missing")
        blocked = True
    if blocked_pattern:
        issues.append(f"blocked_pattern:{blocked_pattern}")
        blocked = True
    if risk_level in {"critical"}:
        issues.append(f"blocked_risk_level:{risk_level}")
        blocked = True
    if command and not risk_policy_allows(risk_level, "dry_run"):
        issues.append(f"risk_policy_dry_run_not_allowed:{risk_level}")
    status = "blocked" if blocked else "not_ready" if issues else "ready"
    return {
        **row,
        "status": status,
        "issues": issues,
        "blocked": blocked,
        "entrypoint": str(entrypoint) if entrypoint else None,
        "entrypoint_exists": None if entrypoint is None else entrypoint.exists(),
    }


def validate_cycle(cycle_type: str, config_path: Path = COMMANDS_PATH, *, for_execute: bool = False) -> dict[str, Any]:
    config_path = resolve_repo_path(config_path)
    rows = stage_plan_rows(cycle_type, config_path)
    roles = load_thread_roles()
    stage_results = [readiness_for_stage(row, roles) for row in rows]
    blocking = [row for row in stage_results if row["status"] == "blocked"]
    not_ready = [row for row in stage_results if row["status"] == "not_ready"]
    high_risk = [row for row in stage_results if any(str(issue).startswith("blocked_risk_level:") for issue in row["issues"])]
    if for_execute and not is_default_safe_config(config_path):
        return {
            "status": "blocked",
            "stage_results": stage_results,
            "reason": "operational config execute-safe is not allowed because allow_operational_execute=false",
        }
    if blocking:
        status = "blocked"
    elif not_ready:
        status = "not_ready"
    elif not is_default_safe_config(config_path):
        status = "ready_for_dry_run"
    else:
        status = "ready"
    return {
        "status": status,
        "stage_results": stage_results,
        "reason": None,
        "high_risk_stage_count": len(high_risk),
    }


def initial_cycle_state(run_id: str, cycle_type: str, mode: str, config_path: Path, *, status: str = "running") -> dict[str, Any]:
    rows = stage_plan_rows(cycle_type, config_path)
    return {
        "run_id": run_id,
        "cycle_type": cycle_type,
        "mode": mode,
        "config": config_label(config_path),
        "status": status,
        "started_at": now_stamp(),
        "completed_at": None,
        "current_stage": rows[0]["stage_id"] if rows else None,
        "stages": [
            {
                "stage_id": row["stage_id"],
                "order": row["order"],
                "thread": row.get("thread"),
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "result_file": None,
                "stage_report_file": None,
                "handoff_file": None,
                "error_message": None,
            }
            for row in rows
        ],
        "stop_reason": None,
        "final_summary_file": None,
    }


def state_path(run_id: str) -> Path:
    return run_dir(run_id) / "cycle_state.json"


def read_cycle_state(run_id: str) -> dict[str, Any]:
    return read_json(state_path(run_id))


def write_cycle_state(state: dict[str, Any]) -> None:
    write_json(state_path(str(state["run_id"])), state)


def stage_result_path(run_id: str, stage_id: str) -> Path:
    return stage_dir(run_id, stage_id) / "result.json"


def stage_report_path(run_id: str, stage_id: str) -> Path:
    return stage_dir(run_id, stage_id) / "stage_report.md"


def handoff_path(run_id: str, stage_id: str) -> Path:
    return stage_dir(run_id, stage_id) / "handoff.md"
