from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "data_quality" / "validation_suite"


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _command_label(cmd: list[str]) -> str:
    for part in cmd:
        text = str(part)
        if text.endswith(".py"):
            return Path(text).name
    return Path(str(cmd[0])).name if cmd else ""


def _commands(mode: str, asof: str, python_exe: str) -> list[list[str]]:
    daily_contract = [
        [python_exe, str(ROOT / "scripts" / "validate_redbot_web_snapshots.py"), "--asof", asof, "--skip-build"],
        [python_exe, str(ROOT / "scripts" / "validate_redbot_history_payloads.py"), "--asof", asof],
        [python_exe, str(ROOT / "scripts" / "validate_admin_new_entry_tracker.py"), "--asof", asof, "--mode", "quick"],
        [python_exe, str(ROOT / "scripts" / "validate_trading_sign_snapshots.py"), "--asof", asof],
        [python_exe, str(ROOT / "scripts" / "validate_daily_pipeline_contract.py"), "--asof", asof],
    ]
    if mode == "daily_contract":
        return daily_contract
    if mode == "research_validation":
        return [
            [python_exe, str(ROOT / "scripts" / "validate_admin_new_entry_tracker.py"), "--asof", asof, "--mode", "full"],
            [python_exe, str(ROOT / "scripts" / "build_internal_model_validation_current.py"), "--asof", asof],
            *daily_contract,
        ]
    if mode == "pre_gcs_publish":
        return [
            [python_exe, str(ROOT / "scripts" / "validate_daily_pipeline_contract.py"), "--asof", asof],
            [python_exe, str(ROOT / "scripts" / "validate_trading_sign_snapshots.py"), "--asof", asof],
        ]
    raise ValueError(f"unsupported validation suite mode: {mode}")


def _run(cmd: list[str]) -> dict[str, Any]:
    started = datetime.now()
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    elapsed = round(time.perf_counter() - start, 3)
    row: dict[str, Any] = {
        "label": _command_label(cmd),
        "command": " ".join(str(part) for part in cmd),
        "return_code": int(proc.returncode),
        "elapsed_seconds": elapsed,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    if proc.stdout:
        row["stdout_tail"] = proc.stdout[-4000:]
    if proc.stderr:
        row["stderr_tail"] = proc.stderr[-4000:]
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description="Run standardized Quant validation command suites.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument(
        "--mode",
        choices=["daily_contract", "research_validation", "pre_gcs_publish"],
        default="daily_contract",
    )
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--keep-going", action="store_true", help="Run all checks even after a failure.")
    args = ap.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    rows = []
    status = "pass"
    for cmd in _commands(str(args.mode), str(args.asof), str(args.python)):
        row = _run(cmd)
        rows.append(row)
        print(f"[{row['return_code']}] {row['label']} elapsed={row['elapsed_seconds']}s")
        if int(row["return_code"]) != 0:
            status = "fail"
            if not args.keep_going:
                break

    payload = {
        "source_name": "quant_validation_suite",
        "status": status,
        "mode": args.mode,
        "asof": args.asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "command_count": len(rows),
        "failed": [row for row in rows if int(row["return_code"]) != 0],
        "commands": rows,
    }
    out_path = REPORT_DIR / f"quant_validation_suite_{args.mode}_{_token(args.asof)}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "mode": args.mode, "asof": args.asof, "report": str(out_path)}, ensure_ascii=False, indent=2))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
