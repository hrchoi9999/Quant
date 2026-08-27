from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cycle_common import run_dir
from harness_common import now_stamp, read_json, write_json

STAGE_FILES = {
    "result": "result.json",
    "stage_report": "stage_report.md",
    "manual_execution_report": "manual_execution_report.md",
    "handoff": "handoff.md",
    "stdout": "stdout.log",
    "stderr": "stderr.log",
    "artifact_validation": "artifact_validation.json",
}


def _read_text(path: Path, limit: int = 20000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit]


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except json.JSONDecodeError as exc:
        return {"_json_error": str(exc)}


def _stage_ids_from_state(state: dict[str, Any]) -> list[str]:
    stages = state.get("stages") or []
    return [str(row.get("stage_id")) for row in stages if isinstance(row, dict) and row.get("stage_id")]


def collect(run_id: str) -> dict[str, Any]:
    root = run_dir(run_id)
    cycle_state_path = root / "cycle_state.json"
    manual_report_md_path = root / "manual_cycle_report.md"
    manual_report_json_path = root / "manual_cycle_report.json"
    final_summary_path = root / "final_summary.md"

    state = _read_json_if_exists(cycle_state_path)
    missing_files: list[str] = []
    for path in [cycle_state_path, manual_report_md_path, manual_report_json_path, final_summary_path]:
        if not path.exists():
            missing_files.append(str(path))

    stages = []
    for stage_id in _stage_ids_from_state(state):
        stage_path = root / stage_id
        row: dict[str, Any] = {"stage_id": stage_id, "stage_dir": str(stage_path)}
        for key, filename in STAGE_FILES.items():
            path = stage_path / filename
            exists_key = f"{key}_exists"
            path_key = f"{key}_path"
            row[exists_key] = path.exists()
            row[path_key] = str(path)
            if not path.exists():
                missing_files.append(str(path))
        row["result"] = _read_json_if_exists(stage_path / STAGE_FILES["result"])
        row["artifact_validation"] = _read_json_if_exists(stage_path / STAGE_FILES["artifact_validation"])
        row["stdout_sample"] = _read_text(stage_path / STAGE_FILES["stdout"])
        row["stderr_sample"] = _read_text(stage_path / STAGE_FILES["stderr"])
        row["manual_execution_report_sample"] = _read_text(stage_path / STAGE_FILES["manual_execution_report"])
        stages.append(row)

    payload = {
        "run_id": run_id,
        "run_dir": str(root),
        "cycle_state_exists": cycle_state_path.exists(),
        "manual_cycle_report_exists": manual_report_md_path.exists() and manual_report_json_path.exists(),
        "final_summary_exists": final_summary_path.exists(),
        "cycle_state": state,
        "manual_cycle_report": _read_json_if_exists(manual_report_json_path),
        "final_summary_sample": _read_text(final_summary_path),
        "stages": stages,
        "missing_files": missing_files,
        "collected_at": now_stamp(),
    }
    write_json(root / "agent_shadow_inputs.json", payload)
    return payload


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Collect file inputs for rule-based agent shadow review.")
    ap.add_argument("--run-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = collect(args.run_id)
    print(json.dumps({"run_id": args.run_id, "missing_file_count": len(result["missing_files"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
