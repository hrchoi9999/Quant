from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_common import ROOT, RUNS_DIR, now_stamp, read_json, write_json
from list_shadow_review_runs import TREND_DIR, list_runs


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except json.JSONDecodeError as exc:
        return {"_json_error": str(exc)}


def _read_text_if_exists(path: Path, limit: int = 20000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _stage_payload(run_dir: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for stage in state.get("stages") or []:
        if not isinstance(stage, dict) or not stage.get("stage_id"):
            continue
        stage_id = str(stage["stage_id"])
        stage_dir = run_dir / stage_id
        result_path = stage_dir / "result.json"
        artifact_path = stage_dir / "artifact_validation.json"
        rows.append(
            {
                "stage_id": stage_id,
                "cycle_state": stage,
                "result_exists": result_path.exists(),
                "result": _read_json_if_exists(result_path),
                "artifact_validation_exists": artifact_path.exists(),
                "artifact_validation": _read_json_if_exists(artifact_path),
            }
        )
    return rows


def _select_run_ids(run_ids: str | None, limit: int) -> list[str]:
    if run_ids:
        return [item.strip() for item in run_ids.split(",") if item.strip()]
    runs = list_runs(limit)
    return [str(row["run_id"]) for row in runs["runs"]]


def collect(run_ids: str | None = None, limit: int = 10) -> dict[str, Any]:
    selected = _select_run_ids(run_ids, limit)
    runs = []
    missing_files: list[str] = []
    for run_id in selected:
        run_dir = RUNS_DIR / run_id
        paths = {
            "agent_shadow_review": run_dir / "agent_shadow_review.json",
            "agent_next_action_recommendation": run_dir / "agent_next_action_recommendation.md",
            "cycle_state": run_dir / "cycle_state.json",
            "manual_cycle_report": run_dir / "manual_cycle_report.json",
            "final_summary": run_dir / "final_summary.md",
        }
        for path in paths.values():
            if not path.exists():
                missing_files.append(str(path))
        state = _read_json_if_exists(paths["cycle_state"])
        runs.append(
            {
                "run_id": run_id,
                "run_dir": str(run_dir),
                "agent_shadow_review": _read_json_if_exists(paths["agent_shadow_review"]),
                "agent_next_action_recommendation": _read_text_if_exists(paths["agent_next_action_recommendation"]),
                "cycle_state": state,
                "manual_cycle_report": _read_json_if_exists(paths["manual_cycle_report"]),
                "final_summary_sample": _read_text_if_exists(paths["final_summary"]),
                "stages": _stage_payload(run_dir, state),
            }
        )
    payload = {
        "generated_at": now_stamp(),
        "run_count": len(runs),
        "runs": runs,
        "missing_files": missing_files,
        "source": str(ROOT / "reports" / "harness_runs"),
    }
    TREND_DIR.mkdir(parents=True, exist_ok=True)
    write_json(TREND_DIR / "multi_run_shadow_inputs.json", payload)
    return payload


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Collect multi-run inputs for shadow trend analysis.")
    ap.add_argument("--run-ids", default=None)
    ap.add_argument("--limit", type=int, default=10)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = collect(args.run_ids, args.limit)
    print(json.dumps({"run_count": result["run_count"], "missing_file_count": len(result["missing_files"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
