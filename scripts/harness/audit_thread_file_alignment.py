from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harness_common import (
    COMMAND_MAPPING_DIR,
    COMMANDS_PATH,
    OPERATIONAL_COMMANDS_PATH,
    find_command_entrypoint,
    load_stage_commands,
    load_thread_roles,
    resolve_repo_path,
    write_json,
)


def audit_config(config_path: Path, roles: dict[str, dict[str, Any]], require_command: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stage_id, config in load_stage_commands(config_path).items():
        thread = str(config.get("thread") or "")
        role = roles.get(thread) or {}
        root = Path(str(role.get("root") or ""))
        working_dir = Path(str(config.get("working_dir") or ""))
        command = config.get("command")
        entrypoint = find_command_entrypoint(str(command or ""), working_dir=str(working_dir)) if command else None
        mismatch: list[str] = []
        if not root.exists():
            mismatch.append("thread_root_missing")
        if working_dir != root:
            mismatch.append("working_dir_not_thread_root")
        if require_command and not command:
            mismatch.append("command_not_registered")
        if command and entrypoint is None:
            mismatch.append("entrypoint_not_detected")
        if entrypoint is not None and not entrypoint.exists():
            mismatch.append("entrypoint_missing")
        rows.append(
            {
                "stage_id": stage_id,
                "thread": thread,
                "thread_root": str(root),
                "thread_root_exists": root.exists(),
                "working_dir": str(working_dir),
                "command": command,
                "entrypoint": str(entrypoint) if entrypoint else None,
                "entrypoint_exists": None if entrypoint is None else entrypoint.exists(),
                "mismatch": mismatch,
                "status": "ok" if not mismatch else "needs_fix",
            }
        )
    return rows


def render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Thread File Alignment Audit", "", f"generated_at: {payload['generated_at']}", "", "## Summary"]
    issues = payload["summary"]
    if not issues:
        lines.append("- all ok")
    else:
        for item in issues:
            lines.append(f"- {item['stage_id']} ({item['thread']}): {', '.join(item['mismatch'])}")
    lines.extend(["", "## Thread Roots"])
    for thread, row in payload["thread_roots"].items():
        lines.append(f"- {thread}: {row['root']} exists={row['exists']}")
    lines.extend(["", "## Config Details"])
    for config_path, rows in payload["configs"].items():
        lines.append(f"### {config_path}")
        for row in rows:
            lines.append(
                f"- {row['stage_id']} {row['thread']} status={row['status']} "
                f"working_dir={row['working_dir']} mismatch={row['mismatch']}"
            )
            if row["entrypoint"]:
                lines.append(f"  - entrypoint: {row['entrypoint']} exists={row['entrypoint_exists']}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Audit thread roots, working dirs, and command entrypoints.")
    ap.add_argument("--safe-config", default=str(COMMANDS_PATH))
    ap.add_argument("--operational-config", default=str(OPERATIONAL_COMMANDS_PATH))
    return ap.parse_args()


def main() -> None:
    from harness_common import now_stamp

    args = parse_args()
    roles = load_thread_roles()
    safe_path = resolve_repo_path(args.safe_config)
    operational_path = resolve_repo_path(args.operational_config)
    payload: dict[str, Any] = {
        "generated_at": now_stamp(),
        "thread_roots": {
            thread: {"root": str(row.get("root")), "exists": Path(str(row.get("root"))).exists()}
            for thread, row in roles.items()
        },
        "configs": {
            str(safe_path): audit_config(safe_path, roles, require_command=True),
            str(operational_path): audit_config(operational_path, roles, require_command=True),
        },
        "summary": [],
    }
    for config_path, rows in payload["configs"].items():
        for row in rows:
            if row["status"] != "ok":
                payload["summary"].append(
                    {
                        "config": config_path,
                        "stage_id": row["stage_id"],
                        "thread": row["thread"],
                        "mismatch": row["mismatch"],
                    }
                )
    payload["issue_count"] = len(payload["summary"])
    COMMAND_MAPPING_DIR.mkdir(parents=True, exist_ok=True)
    json_path = COMMAND_MAPPING_DIR / "thread_file_alignment_audit.json"
    md_path = COMMAND_MAPPING_DIR / "thread_file_alignment_audit.md"
    write_json(json_path, payload)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({"issue_count": len(payload["summary"]), "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
