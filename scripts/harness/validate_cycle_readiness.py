from __future__ import annotations

import argparse
import json

from cycle_common import run_dir, validate_cycle
from harness_common import COMMANDS_PATH, resolve_repo_path, write_json


def render_readiness(payload: dict) -> str:
    lines = [
        "# Cycle Readiness",
        "",
        f"- run_id: {payload['run_id']}",
        f"- cycle_type: {payload['cycle_type']}",
        f"- status: {payload['status']}",
        f"- config: {payload['config']}",
        f"- reason: {payload.get('reason') or 'none'}",
        "",
        "| order | stage_id | thread | status | issues |",
        "|---:|---|---|---|---|",
    ]
    for row in payload["stage_results"]:
        issues = ", ".join(row.get("issues") or []) or "none"
        lines.append(f"| {row['order']} | {row['stage_id']} | {row.get('thread')} | {row['status']} | {issues} |")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate cycle readiness without executing stages.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cycle-type", choices=["weekday", "weekend"], required=True)
    ap.add_argument("--config", default=str(COMMANDS_PATH))
    ap.add_argument("--for-execute", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_repo_path(args.config)
    result = validate_cycle(args.cycle_type, config_path, for_execute=bool(args.for_execute))
    payload = {
        "run_id": args.run_id,
        "cycle_type": args.cycle_type,
        "config": str(config_path),
        **result,
    }
    out_dir = run_dir(args.run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cycle_readiness.json"
    md_path = out_dir / "cycle_readiness.md"
    write_json(json_path, payload)
    md_path.write_text(render_readiness(payload), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
