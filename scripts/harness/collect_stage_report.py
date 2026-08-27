from __future__ import annotations

import argparse

from harness_common import read_json, stage_dir


def _list_items(values: list[str]) -> str:
    if not values:
        return "  - none"
    return "\n".join(f"  - {item}" for item in values)


def render_report(result: dict) -> str:
    validation = result.get("artifact_validation") or {}
    return f"""# Stage Report

## Summary
- run_id: {result.get("run_id")}
- stage_id: {result.get("stage_id")}
- thread: {result.get("thread")}
- action: {result.get("action")}
- mode: {result.get("mode")}
- status: {result.get("status")}
- return_code: {result.get("return_code")}
- risk_level: {result.get("risk_level")}
- safe_run: {result.get("safe_run")}

## Command
```text
{result.get("command") or ""}
```

## Logs
- stdout: {result.get("stdout_log")}
- stderr: {result.get("stderr_log")}

## Artifact Validation
- status: {validation.get("status")}
- found:
{_list_items(list(validation.get("found") or []))}
- missing:
{_list_items(list(validation.get("missing") or []))}

## Error
{result.get("error_message") or "none"}

## Next Action
Check `handoff.md` and proceed only when status is `completed` or `validated`.
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Collect a markdown report for one harness stage.")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stage-id", required=True)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = stage_dir(args.run_id, args.stage_id)
    result_path = out_dir / "result.json"
    if not result_path.exists():
        raise SystemExit(f"missing result.json: {result_path}")
    report = render_report(read_json(result_path))
    out = out_dir / "stage_report.md"
    out.write_text(report, encoding="utf-8")
    print(f"stage_report={out}")


if __name__ == "__main__":
    main()
