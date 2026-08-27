from __future__ import annotations

import argparse
import json

from harness_common import OPERATIONAL_COMMANDS_PATH, read_yaml, resolve_repo_path, write_yaml

ALLOWED_TRANSITIONS = {
    "candidate_required": {"candidate_found"},
    "candidate_found": {"preflight_passed", "preflight_failed"},
    "preflight_failed": {"candidate_found"},
    "preflight_passed": {"approved_for_manual_execute"},
}


def promote(stage_id: str, to_status: str, config_path) -> dict[str, str]:
    if to_status == "approved_for_harness_execute":
        raise SystemExit("BLOCKED: approved_for_harness_execute is not allowed in TASK_UPDATE_HARNESS_03.")
    data = read_yaml(config_path)
    stages = data.get("stages") or {}
    stage = stages.get(stage_id)
    if not isinstance(stage, dict):
        raise SystemExit(f"stage_id not found: {stage_id}")
    current = str(stage.get("command_status") or "candidate_required")
    if to_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise SystemExit(f"invalid transition: {current} -> {to_status}")
    stage["command_status"] = to_status
    write_yaml(config_path, data)
    return {"stage_id": stage_id, "from_status": current, "to_status": to_status, "config": str(config_path)}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Promote an operational stage command status with TASK 03 limits.")
    ap.add_argument("--stage-id", required=True)
    ap.add_argument("--to-status", required=True)
    ap.add_argument("--config", default=str(OPERATIONAL_COMMANDS_PATH))
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = promote(args.stage_id, args.to_status, resolve_repo_path(args.config))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
