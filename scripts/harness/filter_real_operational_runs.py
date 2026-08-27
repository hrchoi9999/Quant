from __future__ import annotations

import argparse
import json
from typing import Any

from classify_harness_run_namespace import TREND_DIR, build_index
from harness_common import ROOT, now_stamp, read_json, read_yaml, write_json

REAL_NAMESPACES = {"operational_pilot", "approval_gated_operational"}
POLICY_PATH = ROOT / "config" / "harness" / "run_namespace_policy.yaml"


def _superseded_runs() -> dict[str, dict[str, str]]:
    policy = read_yaml(POLICY_PATH).get("run_namespace_policy") or {}
    rows = policy.get("superseded_real_runs") or []
    return {str(row.get("run_id")): row for row in rows if row.get("run_id")}


def _real_filter_decision(row: dict[str, Any], superseded: dict[str, dict[str, str]]) -> tuple[bool, str]:
    run_id = str(row.get("run_id") or "")
    if run_id in superseded:
        replacement = superseded[run_id].get("superseded_by") or "unknown"
        return False, f"excluded_superseded_by_retry:{replacement}"
    namespace = str(row.get("namespace") or "unknown")
    mode = str(row.get("mode") or "")
    approval_based = bool(row.get("approval_based_execution"))
    is_real = namespace in REAL_NAMESPACES and mode == "execute" and approval_based
    reason = "included_real_operational_run" if is_real else "excluded_not_real_execute_approval_run"
    return is_real, reason


def filter_real_runs() -> dict[str, Any]:
    index_path = TREND_DIR / "run_namespace_index.json"
    if not index_path.exists():
        build_index()
    index = read_json(index_path)
    superseded = _superseded_runs()
    included = []
    excluded = []
    for row in index.get("runs") or []:
        is_real, reason = _real_filter_decision(row, superseded)
        out = {**row, "real_filter_reason": reason}
        if str(row.get("run_id") or "") in superseded:
            out["superseded_by"] = superseded[str(row.get("run_id"))].get("superseded_by")
            out["superseded_reason"] = superseded[str(row.get("run_id"))].get("reason")
        if is_real:
            included.append(out)
        else:
            excluded.append(out)

    status = "ok" if included else "insufficient_real_runs"
    payload: dict[str, Any] = {
        "generated_at": now_stamp(),
        "status": status,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "included_runs": included,
        "excluded_runs": excluded,
        "source_index": str(index_path),
    }
    write_json(TREND_DIR / "real_operational_runs.json", payload)
    (TREND_DIR / "real_operational_runs.md").write_text(render_real_runs(payload), encoding="utf-8")
    return payload


def render_real_runs(payload: dict[str, Any]) -> str:
    lines = [
        "# Real Operational Runs",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- status: {payload['status']}",
        f"- included_count: {payload['included_count']}",
        f"- excluded_count: {payload['excluded_count']}",
        "",
        "## Included",
    ]
    lines.extend([f"- {row['run_id']} ({row['namespace']})" for row in payload["included_runs"]] or ["- none"])
    lines.extend(["", "## Excluded", "| run_id | namespace | mode | approval_based | reason |", "|---|---|---|---:|---|"])
    for row in payload["excluded_runs"]:
        lines.append(f"| {row['run_id']} | {row['namespace']} | {row.get('mode')} | {row.get('approval_based_execution')} | {row['real_filter_reason']} |")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="Filter real operational execute runs for readiness analysis.").parse_args()


def main() -> None:
    parse_args()
    result = filter_real_runs()
    print(json.dumps({"status": result["status"], "included_count": result["included_count"], "excluded_count": result["excluded_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
