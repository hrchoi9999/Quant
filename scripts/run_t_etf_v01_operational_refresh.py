from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(r"D:\Quant")
PYTHON = BASE_DIR / "venv64" / "Scripts" / "python.exe"
from tseries_refresh_utils import normalize_asof_date, normalize_run_date, run_dir


SCRIPTS = [
    BASE_DIR / "scripts" / "build_etf_tseries_pit_backfill_v1.py",
    BASE_DIR / "scripts" / "build_etf_two_stage_tuned_pit_candidates.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_strict_walkforward.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_operational_candidates.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_risk_filter.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_shadow_tracking.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_rolling_watchlist.py",
]
SYNC_SCRIPT = BASE_DIR / r"src\quant_service\sync_tseries_operational_db.py"


def run_step(script: Path, *extra: str) -> None:
    subprocess.run([str(PYTHON), str(script), *extra], check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Refresh T-ETF-V01 operational outputs.")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD. Used for run folder naming.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD. Overrides output run date.")
    args = ap.parse_args()

    asof = normalize_asof_date(args.asof)
    run_date = normalize_run_date(args.run_date or asof)
    run_root = run_dir(run_date)
    run_root.mkdir(parents=True, exist_ok=True)

    for script in SCRIPTS:
        run_step(script, "--asof", asof, "--run-date", run_date)
    run_step(Path(SYNC_SCRIPT), "--model", "etf", "--run-date", run_date)


