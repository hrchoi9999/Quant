# rebuild_growth_valuation_ai_pipeline.py ver 2026-05-06_001
from __future__ import annotations

import argparse
from datetime import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\Quant")
TIMING_ROWS: list[dict[str, object]] = []


def _run(cmd: list[str]) -> None:
    started_at = datetime.now()
    start = time.perf_counter()
    print(f"[RUN] {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=str(ROOT), check=False)
    elapsed = time.perf_counter() - start
    finished_at = datetime.now()
    label = next((Path(part).name for part in cmd if str(part).endswith(".py")), None)
    if label is None and len(cmd) >= 3 and cmd[1] == "-m":
        label = str(cmd[2])
    TIMING_ROWS.append(
        {
            "label": label or Path(str(cmd[0])).name,
            "return_code": int(completed.returncode),
            "elapsed_seconds": round(float(elapsed), 3),
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "command": " ".join(str(part) for part in cmd),
        }
    )
    print(f"[DONE] rc={completed.returncode} elapsed={elapsed:.1f}s label={label}")
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(int(completed.returncode), cmd)


def _write_timing_report(
    asof: str,
    status: str,
    started_at: datetime,
    start_mono: float,
) -> Path:
    out_dir = ROOT / "reports" / "pipeline_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"valuation_ai_pipeline_timing_{asof}_{stamp}.json"
    report_status = "interrupted_or_failed" if status == "running" else status
    payload = {
        "status": report_status,
        "asof": asof,
        "started_at": started_at.isoformat(timespec="seconds"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "wall_elapsed_seconds": round(time.perf_counter() - start_mono, 3),
        "command_count": len(TIMING_ROWS),
        "summed_command_seconds": round(sum(float(row.get("elapsed_seconds") or 0.0) for row in TIMING_ROWS), 3),
        "top_commands": sorted(TIMING_ROWS, key=lambda row: float(row.get("elapsed_seconds") or 0.0), reverse=True)[:15],
        "commands": TIMING_ROWS,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[TIMING] wrote {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI-GROWTH-VALUATION-V01 end-to-end pipeline.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--start", default="2017-01-01")
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-train-if-current", action="store_true", help="Skip training when the asof model artifact already exists")
    args = parser.parse_args()

    py = str(args.python)
    status = "running"
    started_at = datetime.now()
    start_mono = time.perf_counter()
    try:
        _run([py, "-m", "src.models.valuation_ai.build_market_context", "--start", args.start, "--end", args.asof])
        _run([py, "-m", "src.models.valuation_ai.build_features", "--start", args.start, "--end", args.asof])
        _run([py, "-m", "src.models.valuation_ai.build_labels"])
        model_path = ROOT / "data" / "models" / "valuation_ai" / f"AI-GROWTH-VALUATION-V01_{args.asof.replace('-', '')}_001.joblib"
        should_skip_train = bool(args.skip_train) or (bool(args.skip_train_if_current) and model_path.exists())
        if should_skip_train:
            print(f"[SKIP] train_model skipped; model_path={model_path}")
        else:
            _run(
                [
                    py,
                    "-m",
                    "src.models.valuation_ai.train_model",
                    "--train-end",
                    args.train_end,
                    "--valid-start",
                    args.valid_start,
                    "--valid-end",
                    args.asof,
                ]
            )
        _run([py, "-m", "src.models.valuation_ai.predict_scores", "--asof", args.asof])
        _run([py, "-m", "src.models.valuation_ai.evaluate_model", "--asof", args.asof])
        _run([py, str(ROOT / "scripts" / "build_valuation_ai_challenger_current.py"), "--asof", args.asof])
        _run([py, str(ROOT / "scripts" / "build_valuation_ai_challenger_shadow_tracker.py"), "--performance-asof", args.asof])
        _run([py, str(ROOT / "scripts" / "build_valuation_ai_shadow_monitor_report.py")])
        _run(
            [
                py,
                str(ROOT / "scripts" / "build_ai_combined_candidate_validation_report.py"),
                "--asof",
                args.asof,
                "--performance-asof",
                args.asof,
            ]
        )
        _run([py, str(ROOT / "scripts" / "build_ai_learning_models_admin_payload.py"), "--asof", args.asof])
        status = "ok"
    finally:
        _write_timing_report(args.asof, status, started_at, start_mono)
    print(
        json.dumps(
            {
                "status": "ok",
                "model_code": "AI-GROWTH-VALUATION-V01",
                "model_name_ko": "주가수준평가AI",
                "asof": args.asof,
                "start": args.start,
                "admin_outputs": [
                    str(ROOT / "service_platform" / "web" / "admin_data" / "current" / "valuation_ai_challenger_current.json"),
                    str(ROOT / "service_platform" / "web" / "admin_data" / "current" / "valuation_ai_challenger_shadow_performance.json"),
                ],
                "monitor_report": str(ROOT / "reports" / "valuation_ai" / f"valuation_ai_shadow_monitor_{args.asof.replace('-', '')}_to_{args.asof.replace('-', '')}.md"),
                "combined_monitor_report": str(ROOT / "reports" / "valuation_ai" / f"ai_combined_candidate_validation_{args.asof.replace('-', '')}_to_{args.asof.replace('-', '')}.md"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
