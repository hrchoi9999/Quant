from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from harness_common import ROOT, RUNS_DIR, now_stamp, read_json, read_yaml, write_json

POLICY_PATH = ROOT / "config" / "harness" / "run_namespace_policy.yaml"
TREND_DIR = ROOT / "reports" / "agent_shadow_trends"


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"_read_error": str(exc)}


def _policy() -> dict[str, Any]:
    return read_yaml(POLICY_PATH).get("run_namespace_policy") or {}


def _contains_any(text: str, needles: list[str]) -> str | None:
    lowered = text.lower()
    for needle in needles:
        if needle.lower() in lowered:
            return needle
    return None


def _commands_from_state(state: dict[str, Any]) -> list[str]:
    commands = []
    for row in state.get("stages") or []:
        if isinstance(row, dict) and row.get("command"):
            commands.append(str(row["command"]))
    return commands


def _commands_from_stage_results(run_dir: Path) -> list[str]:
    commands: list[str] = []
    for result_path in run_dir.glob("*/result.json"):
        result = _safe_json(result_path)
        command = result.get("command")
        if command:
            commands.append(str(command))
    return commands


def _extract_metadata(run_dir: Path) -> dict[str, Any]:
    state = _safe_json(run_dir / "cycle_state.json")
    gated = _safe_json(run_dir / "approval_gated_cycle_pilot_result.json")
    manual = _safe_json(run_dir / "manual_cycle_report.json")
    shadow = _safe_json(run_dir / "agent_shadow_review.json")
    commands = _commands_from_state(state) + _commands_from_stage_results(run_dir)
    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "mode": state.get("mode") or gated.get("mode") or manual.get("mode"),
        "execution_type": state.get("execution_type") or gated.get("execution_type"),
        "approval_based_execution": bool(state.get("approval_based_execution") or gated.get("approval_based_execution")),
        "approval_id": state.get("approval_id") or gated.get("approval_id"),
        "approval_gate_status": state.get("approval_gate_status") or gated.get("approval_gate_status"),
        "cycle_type": state.get("cycle_type") or shadow.get("cycle_type"),
        "status": state.get("status") or shadow.get("overall_status") or manual.get("status"),
        "overall_severity": shadow.get("overall_severity"),
        "commands": commands,
        "files": {
            "cycle_state": str(run_dir / "cycle_state.json") if (run_dir / "cycle_state.json").exists() else None,
            "manual_cycle_report": str(run_dir / "manual_cycle_report.json") if (run_dir / "manual_cycle_report.json").exists() else None,
            "agent_shadow_review": str(run_dir / "agent_shadow_review.json") if (run_dir / "agent_shadow_review.json").exists() else None,
        },
    }


def classify_metadata(metadata: dict[str, Any], policy: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    policy = policy or _policy()
    run_id = str(metadata.get("run_id") or "")
    mode = str(metadata.get("mode") or "")
    execution_type = str(metadata.get("execution_type") or "")
    commands = [str(item) for item in metadata.get("commands") or []]
    reasons: list[str] = []

    safe = policy.get("safe_run_indicators") or {}
    matched = _contains_any(run_id, [str(item) for item in safe.get("run_id_contains") or []])
    if matched:
        reasons.append(f"run_id_contains:{matched}")
        return "safe_run", reasons
    for command in commands:
        matched = _contains_any(command, [str(item) for item in safe.get("command_contains") or []])
        if matched:
            reasons.append(f"command_contains:{matched}")
            return "safe_run", reasons

    test = policy.get("test_indicators") or {}
    matched = _contains_any(run_id, [str(item) for item in test.get("run_id_contains") or []])
    if matched:
        reasons.append(f"run_id_contains:{matched}")
        return "test_fixture", reasons

    dry = policy.get("dry_run_indicators") or {}
    matched = _contains_any(run_id, [str(item) for item in dry.get("run_id_contains") or []])
    if matched:
        reasons.append(f"run_id_contains:{matched}")
        return "dry_run", reasons
    if mode in {str(item) for item in dry.get("mode_values") or []}:
        reasons.append(f"mode:{mode}")
        return "dry_run", reasons

    real = policy.get("real_indicators") or {}
    real_execution_types = {str(item) for item in real.get("execution_type") or []}
    real_modes = {str(item) for item in real.get("mode_values") or []}
    if (
        execution_type in real_execution_types
        and mode in real_modes
        and bool(metadata.get("approval_based_execution")) is bool(real.get("approval_based_execution", True))
    ):
        reasons.append(f"execution_type:{execution_type}")
        reasons.append(f"mode:{mode}")
        reasons.append("approval_based_execution:true")
        if execution_type == "approval_gated_operational_cycle_pilot" or metadata.get("approval_gate_status"):
            return "approval_gated_operational", reasons
        return "operational_pilot", reasons

    if mode:
        reasons.append(f"unmatched_mode:{mode}")
    if execution_type:
        reasons.append(f"unmatched_execution_type:{execution_type}")
    return "unknown", reasons or ["no_namespace_indicator"]


def build_index() -> dict[str, Any]:
    policy = _policy()
    rows: list[dict[str, Any]] = []
    if RUNS_DIR.exists():
        for run_dir in sorted(RUNS_DIR.iterdir()):
            if not run_dir.is_dir():
                continue
            metadata = _extract_metadata(run_dir)
            namespace, reasons = classify_metadata(metadata, policy)
            include = bool(((policy.get("namespaces") or {}).get(namespace) or {}).get("include_in_real_readiness"))
            rows.append({**metadata, "namespace": namespace, "include_in_real_readiness": include, "classification_reasons": reasons})

    counts = Counter(row["namespace"] for row in rows)
    payload = {
        "generated_at": now_stamp(),
        "policy_file": str(POLICY_PATH),
        "run_count": len(rows),
        "namespace_counts": dict(sorted(counts.items())),
        "runs": rows,
    }
    TREND_DIR.mkdir(parents=True, exist_ok=True)
    write_json(TREND_DIR / "run_namespace_index.json", payload)
    (TREND_DIR / "run_namespace_index.md").write_text(render_index(payload), encoding="utf-8")
    return payload


def render_index(payload: dict[str, Any]) -> str:
    lines = [
        "# Run Namespace Index",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- run_count: {payload['run_count']}",
        "",
        "## Counts",
    ]
    for namespace, count in payload["namespace_counts"].items():
        lines.append(f"- {namespace}: {count}")
    lines.extend(
        [
            "",
            "## Runs",
            "| run_id | namespace | mode | execution_type | approval_based | status | reasons |",
            "|---|---|---|---|---:|---|---|",
        ]
    )
    for row in payload["runs"]:
        reasons = ", ".join(row.get("classification_reasons") or [])
        lines.append(
            f"| {row['run_id']} | {row['namespace']} | {row.get('mode')} | {row.get('execution_type')} | "
            f"{row.get('approval_based_execution')} | {row.get('status')} | {reasons} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="Classify harness runs into test/dry-run/safe/real namespaces.").parse_args()


def main() -> None:
    parse_args()
    result = build_index()
    print(json.dumps({"run_count": result["run_count"], "namespace_counts": result["namespace_counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
