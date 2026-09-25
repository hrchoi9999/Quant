from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

try:
    from .retirement_policy import command_retirement_reason
except ImportError:  # Standalone CLI uses the script directory as its import root.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from retirement_policy import command_retirement_reason

ROOT = Path(__file__).resolve().parents[2]
COMMANDS_PATH = ROOT / "config" / "harness" / "stage_commands.yaml"
OPERATIONAL_COMMANDS_PATH = ROOT / "config" / "harness" / "stage_commands_operational.yaml"
RISK_POLICY_PATH = ROOT / "config" / "harness" / "stage_command_risk_policy.yaml"
THREAD_ROLES_PATH = ROOT / "config" / "harness" / "thread_roles.yaml"
WEEKDAY_PIPELINE_PATH = ROOT / "config" / "harness" / "update_pipeline_weekday.yaml"
WEEKEND_PIPELINE_PATH = ROOT / "config" / "harness" / "update_pipeline_weekend.yaml"
RUNS_DIR = ROOT / "reports" / "harness_runs"
COMMAND_MAPPING_DIR = ROOT / "reports" / "harness_command_mapping"
ALLOWED_EXECUTE_RISK = {"low", "medium"}
BLOCKED_RISK = {"high", "critical"}
COMMAND_TEMPLATE_RE = re.compile(r"{(?P<name>[A-Za-z_][A-Za-z0-9_]*)}")


def now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing yaml: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"yaml root must be mapping: {path}")
    return data


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)


def resolve_repo_path(path_text: str | Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT / path


def load_stage_commands(path: Path = COMMANDS_PATH) -> dict[str, dict[str, Any]]:
    data = read_yaml(path)
    stages = data.get("stages")
    if not isinstance(stages, dict):
        raise SystemExit(f"missing stages mapping: {path}")
    return stages


def get_stage_config(stage_id: str, path: Path = COMMANDS_PATH) -> dict[str, Any]:
    stages = load_stage_commands(path)
    config = stages.get(stage_id)
    if not isinstance(config, dict):
        raise SystemExit(f"stage_id not found in {path}: {stage_id}")
    return config


def load_risk_policy(path: Path = RISK_POLICY_PATH) -> dict[str, Any]:
    data = read_yaml(path)
    return {
        "risk_policy": data.get("risk_policy") or {},
        "blocked_patterns": [str(item) for item in (data.get("blocked_patterns") or [])],
    }


def command_matches_blocked_pattern(command: str, policy: dict[str, Any] | None = None) -> str | None:
    retired = command_retirement_reason(command)
    if retired:
        return retired
    policy = policy or load_risk_policy()
    normalized = command.lower()
    for pattern in policy.get("blocked_patterns") or []:
        if str(pattern).lower() in normalized:
            return str(pattern)
    return None


def risk_policy_allows(risk_level: str, action: str, policy: dict[str, Any] | None = None) -> bool:
    policy = policy or load_risk_policy()
    row = (policy.get("risk_policy") or {}).get(str(risk_level).lower()) or {}
    return bool(row.get(f"allow_{action}"))


def command_template_variables(command: str) -> list[str]:
    return sorted({match.group("name") for match in COMMAND_TEMPLATE_RE.finditer(command or "")})


def bind_command_template(command: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    variables = variables or {}
    template_variables = command_template_variables(command)
    rendered = command or ""
    unresolved: list[str] = []
    bound: dict[str, str] = {}
    for name in template_variables:
        value = variables.get(name)
        if value is None or str(value).strip() == "":
            unresolved.append(name)
            continue
        rendered = rendered.replace("{" + name + "}", str(value))
        bound[name] = str(value)
    return {
        "command_template": command,
        "command": rendered,
        "template_variables": template_variables,
        "bound_variables": bound,
        "unresolved_variables": unresolved,
        "resolved": not unresolved,
    }


def command_template_block_reason(binding: dict[str, Any]) -> str | None:
    unresolved = binding.get("unresolved_variables") or []
    if unresolved:
        return "unresolved command template variables: " + ", ".join(str(item) for item in unresolved)
    return None


def load_thread_roles(path: Path = THREAD_ROLES_PATH) -> dict[str, dict[str, Any]]:
    data = read_yaml(path)
    threads = data.get("threads")
    if not isinstance(threads, dict):
        raise SystemExit(f"missing threads mapping: {path}")
    return threads


def thread_root(thread: str, path: Path = THREAD_ROLES_PATH) -> Path | None:
    roles = load_thread_roles(path)
    row = roles.get(thread)
    if not isinstance(row, dict) or not row.get("root"):
        return None
    return Path(str(row["root"]))


def find_python_entrypoint(command: str, working_dir: str | None = None) -> Path | None:
    if not command:
        return None
    matches = re.findall(r"(?P<path>[A-Za-z]:[\\/][^\s\"']+?\.py|[^\s\"']+?\.py)", command)
    if not matches:
        return None
    return resolve_artifact(matches[-1], working_dir=working_dir)


def find_command_entrypoint(command: str, working_dir: str | None = None) -> Path | None:
    if not command:
        return None
    file_match = re.search(r"-File\s+(?P<path>[A-Za-z]:[\\/][^\s\"']+?\.(?:ps1|py)|[^\s\"']+?\.(?:ps1|py))", command, re.IGNORECASE)
    if file_match:
        return resolve_artifact(file_match.group("path"), working_dir=working_dir)
    script_match = re.search(r"(?P<path>[A-Za-z]:[\\/][^\s\"']+?\.(?:py|ps1)|[^\s\"']+?\.(?:py|ps1))", command, re.IGNORECASE)
    if script_match:
        return resolve_artifact(script_match.group("path"), working_dir=working_dir)
    return None


def stage_dir(run_id: str, stage_id: str) -> Path:
    return RUNS_DIR / run_id / stage_id


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_artifact(path_text: str, working_dir: str | None = None) -> Path:
    raw = Path(path_text)
    if raw.is_absolute():
        return raw
    base = Path(working_dir) if working_dir else ROOT
    return base / raw


def validate_expected_artifacts(run_id: str, stage_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or get_stage_config(stage_id)
    expected = list(config.get("expected_artifacts") or [])
    found: list[str] = []
    missing: list[str] = []
    working_dir = str(config.get("working_dir") or ROOT)
    for item in expected:
        path = resolve_artifact(str(item), working_dir=working_dir)
        if path.exists():
            found.append(str(path))
        else:
            missing.append(str(path))
    status = "not_required" if not expected else "passed" if not missing else "failed"
    return {
        "run_id": run_id,
        "stage_id": stage_id,
        "status": status,
        "expected_artifacts": expected,
        "found": found,
        "missing": missing,
        "checked_at": now_stamp(),
    }


def cycle_type_for_stage(stage_id: str) -> str:
    if stage_id.startswith("WD"):
        return "weekday"
    if stage_id.startswith("WE"):
        return "weekend"
    return "unknown"


def pipeline_path_for_stage(stage_id: str) -> Path | None:
    cycle_type = cycle_type_for_stage(stage_id)
    if cycle_type == "weekday":
        return WEEKDAY_PIPELINE_PATH
    if cycle_type == "weekend":
        return WEEKEND_PIPELINE_PATH
    return None


def next_stage_info(stage_id: str) -> dict[str, str | None]:
    path = pipeline_path_for_stage(stage_id)
    if path is None or not path.exists():
        return {"next_thread": None, "next_action": None}
    data = read_yaml(path)
    stages = data.get("stages") or []
    if not isinstance(stages, list):
        return {"next_thread": None, "next_action": None}
    for idx, row in enumerate(stages):
        if not isinstance(row, dict) or row.get("stage_id") != stage_id:
            continue
        if idx + 1 >= len(stages):
            return {"next_thread": None, "next_action": None}
        next_row = stages[idx + 1]
        if not isinstance(next_row, dict):
            return {"next_thread": None, "next_action": None}
        return {
            "next_thread": str(next_row.get("thread") or ""),
            "next_action": str(next_row.get("stage_id") or ""),
        }
    return {"next_thread": None, "next_action": None}


def write_handoff(stage_path: Path, result: dict[str, Any], output_files: list[str]) -> Path:
    next_info = next_stage_info(str(result["stage_id"]))
    validation = result.get("artifact_validation") or {}
    known_issues = result.get("error_message") or "none"
    text = f"""[PIPELINE HANDOFF]

run_id: {result["run_id"]}
cycle_type: {cycle_type_for_stage(str(result["stage_id"]))}
stage_id: {result["stage_id"]}
thread: {result.get("thread")}
status: {result.get("status")}
started_at: {result.get("started_at")}
completed_at: {result.get("completed_at")}
input_used:
  - stage_commands.yaml
output_created:
{chr(10).join(f"  - {name}" for name in output_files)}
validation_result: {validation.get("status", "not_checked")}
known_issues: {known_issues}
next_thread: {next_info.get("next_thread") or "none"}
next_action: {next_info.get("next_action") or "none"}
operator_note: Auto-generated by run_stage.py
"""
    out = stage_path / "handoff.md"
    out.write_text(text, encoding="utf-8")
    return out


def update_run_state_if_exists(run_id: str, stage_id: str, result: dict[str, Any], handoff_file: str) -> None:
    path = RUNS_DIR / run_id / "run_state.json"
    if not path.exists():
        return
    state = read_json(path)
    stage_payload = {
        "status": result.get("status"),
        "started_at": result.get("started_at"),
        "completed_at": result.get("completed_at"),
        "validation_result": (result.get("artifact_validation") or {}).get("status"),
        "known_issues": [] if not result.get("error_message") else [result.get("error_message")],
        "handoff_file": handoff_file,
    }
    stages = state.get("stages")
    if isinstance(stages, dict):
        existing = stages.get(stage_id)
        if isinstance(existing, dict):
            existing.update(stage_payload)
        else:
            stages[stage_id] = stage_payload
    elif isinstance(stages, list):
        matched = False
        for row in stages:
            if isinstance(row, dict) and row.get("stage_id") == stage_id:
                row.update(stage_payload)
                matched = True
                break
        if not matched:
            stages.append({"stage_id": stage_id, **stage_payload})
    else:
        state["stages"] = {stage_id: stage_payload}
    write_json(path, state)
