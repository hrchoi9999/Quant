from __future__ import annotations

import argparse
import json

from cycle_common import render_cycle_plan, run_dir, stage_plan_rows
from harness_common import COMMANDS_PATH, resolve_repo_path, write_json


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Create a weekday/weekend update cycle plan.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--cycle-type", choices=["weekday", "weekend"], required=True)
    ap.add_argument("--config", default=str(COMMANDS_PATH))
    ap.add_argument("--mode", default="plan")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    config_path = resolve_repo_path(args.config)
    rows = stage_plan_rows(args.cycle_type, config_path)
    out_dir = run_dir(args.run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": args.run_id,
        "cycle_type": args.cycle_type,
        "mode": args.mode,
        "config": str(config_path),
        "stages": rows,
    }
    json_path = out_dir / "cycle_plan.json"
    md_path = out_dir / "cycle_plan.md"
    write_json(json_path, payload)
    md_path.write_text(render_cycle_plan(args.run_id, args.cycle_type, args.mode, config_path, rows), encoding="utf-8")
    print(json.dumps({"cycle_plan": str(json_path), "markdown": str(md_path), "stage_count": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
