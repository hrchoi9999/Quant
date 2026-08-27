from __future__ import annotations

import argparse
import json
from typing import Any

from build_approval_request import APPROVAL_ROOT
from harness_common import now_stamp, read_json, write_json


def _read(path) -> dict[str, Any]:
    try:
        return read_json(path) if path.exists() else {}
    except json.JSONDecodeError:
        return {}


def list_requests() -> dict[str, Any]:
    APPROVAL_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in APPROVAL_ROOT.iterdir():
        if not path.is_dir():
            continue
        request = _read(path / "approval_request.json")
        blocked = _read(path / "approval_request_blocked.json")
        payload = request or blocked
        if not payload:
            continue
        decision = _read(path / "approval_decision.json")
        rows.append(
            {
                "approval_id": path.name,
                "status": payload.get("approval_status"),
                "decision": decision.get("decision"),
                "scope": payload.get("approval_scope"),
                "target_run_id": payload.get("target_run_id"),
                "valid_until": decision.get("valid_until") or payload.get("expires_at"),
                "request_file": str(path / ("approval_request.json" if request else "approval_request_blocked.json")),
            }
        )
    rows.sort(key=lambda row: row["approval_id"], reverse=True)
    result = {"generated_at": now_stamp(), "approval_count": len(rows), "approvals": rows}
    write_json(APPROVAL_ROOT / "approval_request_index.json", result)
    (APPROVAL_ROOT / "approval_request_index.md").write_text(render_index(result), encoding="utf-8")
    return result


def render_index(result: dict[str, Any]) -> str:
    lines = [
        "# Approval Request Index",
        "",
        f"- generated_at: {result['generated_at']}",
        f"- approval_count: {result['approval_count']}",
        "",
        "| approval_id | status | decision | scope | target_run_id | valid_until |",
        "|---|---|---|---|---|---|",
    ]
    for row in result["approvals"]:
        lines.append(
            f"| {row['approval_id']} | {row.get('status')} | {row.get('decision')} | {row.get('scope')} | "
            f"{row.get('target_run_id')} | {row.get('valid_until')} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description="List approval requests.").parse_args()


def main() -> None:
    parse_args()
    result = list_requests()
    print(json.dumps({"approval_count": result["approval_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
