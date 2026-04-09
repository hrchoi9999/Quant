from pathlib import Path
import subprocess
import sys

BASE = Path(r"D:\Quant")
PY = BASE / "venv64" / "Scripts" / "python.exe"
REQUIRED_GLOBS = [
    BASE / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_THRESHOLD_CANDIDATES\operating_v2_stage1_candidates_*.csv",
    BASE / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_THRESHOLD_CANDIDATES\operating_v2_stage2_confirmed_candidates_*.csv",
    BASE / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_THRESHOLD_CANDIDATES\operating_v2_stage2_near_candidates_*.csv",
    BASE / r"reports\model_upgrade_research\20260331\S3_OPERATING_V2_TRACKING\operating_v2_stage1_tracking_history.csv",
    BASE / r"reports\model_upgrade_research\20260331\S3_OPERATING_V2_TRACKING\operating_v2_stage2_only_tracking_history.csv",
]
SCRIPTS = [
    BASE / "scripts" / "build_t_stock_v01_operational_candidates.py",
    BASE / "scripts" / "build_t_stock_v01_theme_labels.py",
    BASE / "scripts" / "build_t_stock_v01_risk_filter.py",
    BASE / "scripts" / "build_t_stock_v01_shadow_tracking.py",
]
SYNC_SCRIPT = BASE / r"src\quant_service\sync_tseries_operational_db.py"


def main() -> None:
    missing = [str(p) for p in REQUIRED_GLOBS if not list(p.parent.glob(p.name))]
    if missing:
        print("[T-STOCK-V01] skip refresh; missing inputs:")
        for item in missing:
            print(f"  - {item}")
        return

    for script in SCRIPTS:
        proc = subprocess.run([str(PY), str(script)], cwd=str(BASE))
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)

    proc = subprocess.run([str(PY), str(SYNC_SCRIPT), "--model", "stock"], cwd=str(BASE))
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()

