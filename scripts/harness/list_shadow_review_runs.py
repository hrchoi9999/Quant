from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_common import ROOT, RUNS_DIR, now_stamp, read_json, write_json

TREND_DIR = ROOT / "reports" / "agent_shadow_trends"


def _safe_read(path: Path) -> dict[str, Any]:
    try:
        return read_json(path)
    except (json.JSONDecodeError, OSError) as exc:
        return {"_read_error": str(exc)}


def list_runs(limit: int | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if RUNS_DIR.exists():
        for run_dir in RUNS_DIR.iterdir():
            review_path = run_dir / "agent_shadow_review.json"
            if not run_dir.is_dir() or not review_path.exists():
                continue
            review = _safe_read(review_path)
            rows.append(
                {
                    "run_id": run_dir.name,
                    "cycle_type": review.get("cycle_type"),
                    "overall_status": review.get("overall_status"),
                    "overall_severity": review.get("overall_severity"),
                    "operation_safe_to_continue": bool(review.get("operation_safe_to_continue")),
                    "requires_manual_review": bool(review.get("requires_manual_review")),
                    "reviewed_at": review.get("reviewed_at"),
                    "agent_shadow_review_file": str(review_path),
                    "agent_next_action_recommendation_exists": (run_dir / "agent_next_action_recommendation.md").exists(),
                    "mtime": review_path.stat().st_mtime,
                }
            )
    rows.sort(key=lambda row: (str(row.get("reviewed_at") or ""), float(row.get("mtime") or 0)), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    for row in rows:
        row.pop("mtime", None)
    payload = {"generated_at": now_stamp(), "run_count": len(rows), "runs": rows}
    TREND_DIR.mkdir(parents=True, exist_ok=True)
    write_json(TREND_DIR / "shadow_review_runs.json", payload)
    (TREND_DIR / "shadow_review_runs.md").write_text(render_runs(payload), encoding="utf-8")
    return payload


def render_runs(payload: dict[str, Any]) -> str:
    lines = [
        "# Shadow Review Runs",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- run_count: {payload['run_count']}",
        "",
        "| run_id | cycle_type | status | severity | safe | manual_review | reviewed_at |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in payload["runs"]:
        lines.append(
            f"| {row['run_id']} | {row.get('cycle_type')} | {row.get('overall_status')} | "
            f"{row.get('overall_severity')} | {row.get('operation_safe_to_continue')} | "
            f"{row.get('requires_manual_review')} | {row.get('reviewed_at')} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="List harness runs that have agent shadow review outputs.")
    ap.add_argument("--limit", type=int, default=None)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    result = list_runs(args.limit)
    print(json.dumps({"run_count": result["run_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
