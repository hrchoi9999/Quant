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
REPORT_DIR = ROOT / r"reports\ai_overlay_backtest"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"


COMMANDS = [
    ("downside_risk_overlay_backtest", r"scripts\run_downside_risk_ai_weekly_overlay_backtest.py"),
    ("valuation_overlay_backtest", r"scripts\run_valuation_ai_weekly_overlay_backtest.py"),
    ("candidate_rank_delta_overlay_backtest", r"scripts\run_candidate_rank_delta_weekly_overlay_backtest.py"),
    ("combo_strategy_overlay_backtest", r"scripts\run_ai_overlay_combo_strategy_backtest.py"),
    ("policy_map_overlay_backtest", r"scripts\run_ai_overlay_policy_map_backtest.py"),
    ("policy_map_current_payload", r"scripts\build_ai_overlay_policy_map_current_payload.py"),
]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _run_command(label: str, script_path: Path, asof: str, python_exe: str) -> dict[str, Any]:
    started = time.perf_counter()
    cmd = [python_exe, str(script_path), "--asof", asof]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    elapsed = round(time.perf_counter() - started, 3)
    row: dict[str, Any] = {
        "label": label,
        "script": str(script_path),
        "returncode": int(proc.returncode),
        "elapsed_seconds": elapsed,
    }
    if proc.stdout:
        row["stdout_tail"] = proc.stdout[-4000:]
    if proc.stderr:
        row["stderr_tail"] = proc.stderr[-4000:]
    if proc.returncode != 0:
        raise RuntimeError(json.dumps(row, ensure_ascii=False, indent=2))
    return row


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_outputs(asof: str) -> dict[str, Any]:
    token = _token(asof)
    required = {
        "downside_risk": REPORT_DIR / f"downside_risk_ai_weekly_overlay_backtest_{token}.json",
        "valuation": REPORT_DIR / f"valuation_ai_weekly_overlay_backtest_{token}.json",
        "candidate_rank_delta": REPORT_DIR / f"candidate_rank_delta_ai_weekly_overlay_backtest_{token}.json",
        "combo_strategy": REPORT_DIR / f"ai_overlay_combo_strategy_backtest_{token}.json",
        "policy_map": REPORT_DIR / f"ai_overlay_policy_map_backtest_{token}.json",
        "internal_models_payload": ADMIN_CURRENT_DIR / "internal_models_ai_overlay_shadow_current.json",
        "ai_learning_payload": ADMIN_CURRENT_DIR / "ai_learning_overlay_monitor_current.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing expected outputs: " + ", ".join(missing))

    backtest_status = {}
    for key in ["downside_risk", "valuation", "candidate_rank_delta", "combo_strategy", "policy_map"]:
        data = _read_json(required[key])
        backtest_status[key] = {
            "status": data.get("status"),
            "rows": data.get("period_rows") or data.get("holdings_rows") or data.get("scored_rows"),
        }
        if data.get("status") != "ok":
            raise ValueError(f"{key} status is not ok: {data.get('status')}")

    payload_status = {}
    for key in ["internal_models_payload", "ai_learning_payload"]:
        data = _read_json(required[key])
        payload_asof = data.get("as_of_date") or data.get("asof")
        payload_status[key] = {
            "as_of_date": payload_asof,
            "status": data.get("status"),
            "source_name": data.get("source_name"),
        }
        if payload_asof != asof:
            raise ValueError(f"{key} as_of_date mismatch: {payload_asof} != {asof}")

    return {
        "required_outputs": {key: str(path) for key, path in required.items()},
        "backtest_status": backtest_status,
        "payload_status": payload_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run operational AI overlay shadow tracking refresh.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    asof = str(args.asof)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    command_results = []
    for label, rel_script in COMMANDS:
        command_results.append(_run_command(label, ROOT / rel_script, asof, str(args.python)))

    validation = _validate_outputs(asof)
    payload = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asof": asof,
        "purpose": "operational refresh for AI overlay shadow tracking and web current payloads",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "commands": command_results,
        "validation": validation,
    }
    out_path = REPORT_DIR / f"ai_overlay_shadow_operational_refresh_{_token(asof)}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
