from __future__ import annotations

import subprocess
from pathlib import Path

BASE_DIR = Path(r"D:\Quant")
PYTHON = BASE_DIR / "venv64" / "Scripts" / "python.exe"
REQUIRED_INPUTS = [
    BASE_DIR / r"reports\model_upgrade_research\20260401\ETF_TWO_STAGE_DISCOVERY_TUNED_PIT\etf_two_stage_tuned_pit_stage1_candidates_2026-03-31.csv",
    BASE_DIR / r"reports\model_upgrade_research\20260401\ETF_TWO_STAGE_DISCOVERY_TUNED_PIT\etf_two_stage_tuned_pit_stage2_confirmed_2026-03-31.csv",
    BASE_DIR / r"reports\model_upgrade_research\20260401\ETF_TWO_STAGE_DISCOVERY_TUNED_PIT\etf_two_stage_tuned_pit_stage2_near_2026-03-31.csv",
    BASE_DIR / r"reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_STRICT_WALKFORWARD\etf_tseries_pit_strict_walkforward_top_picks.csv",
]
SCRIPTS = [
    BASE_DIR / "scripts" / "build_etf_tseries_pit_operational_candidates.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_risk_filter.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_shadow_tracking.py",
    BASE_DIR / "scripts" / "build_etf_tseries_pit_rolling_watchlist.py",
]
SYNC_SCRIPT = BASE_DIR / r"src\quant_service\sync_tseries_operational_db.py"


def run_step(script: Path, *extra: str) -> None:
    subprocess.run([str(PYTHON), str(script), *extra], check=True)


if __name__ == "__main__":
    missing = [str(p) for p in REQUIRED_INPUTS if not p.exists()]
    if missing:
        print("[T-ETF-V01] skip refresh; missing inputs:")
        for item in missing:
            print(f"  - {item}")
    else:
        for script in SCRIPTS:
            run_step(script)
        run_step(Path(SYNC_SCRIPT), "--model", "etf")


