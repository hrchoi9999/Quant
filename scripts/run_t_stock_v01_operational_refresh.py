import argparse
from pathlib import Path
import subprocess

BASE = Path(r"D:\Quant")
PY = BASE / "venv64" / "Scripts" / "python.exe"
from tseries_refresh_utils import normalize_asof_date, normalize_run_date, run_dir


SCRIPTS = [
    BASE / "scripts" / "train_s3_two_stage_models.py",
    BASE / "scripts" / "build_s3_two_stage_threshold_candidates.py",
    BASE / "scripts" / "build_s3_operating_v2_tracking.py",
    BASE / "scripts" / "build_t_stock_v01_operational_candidates.py",
    BASE / "scripts" / "build_t_stock_v01_theme_labels.py",
    BASE / "scripts" / "build_t_stock_v01_risk_filter.py",
    BASE / "scripts" / "build_t_stock_v01_shadow_tracking.py",
    BASE / "scripts" / "build_t_stock_v01_rolling_watchlist.py",
]
SYNC_SCRIPT = BASE / r"src\quant_service\sync_tseries_operational_db.py"


def main() -> None:
    ap = argparse.ArgumentParser(description="Refresh T-STOCK-V01 operational outputs.")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD. Used for run folder naming.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD. Overrides output run date.")
    args = ap.parse_args()

    asof = normalize_asof_date(args.asof)
    run_date = normalize_run_date(args.run_date or asof)
    run_root = run_dir(run_date)
    run_root.mkdir(parents=True, exist_ok=True)

    for script in SCRIPTS:
        proc = subprocess.run(
            [str(PY), str(script), "--asof", asof, "--run-date", run_date],
            cwd=str(BASE),
        )
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)

    proc = subprocess.run(
        [str(PY), str(SYNC_SCRIPT), "--model", "stock", "--run-date", run_date],
        cwd=str(BASE),
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()

