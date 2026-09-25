from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Quant")
TRADING_SIGN_ROOT = PROJECT_ROOT / "trading_sign"
TRADING_SIGN_SRC = TRADING_SIGN_ROOT / "src"
TRADING_SIGN_SCRIPT = TRADING_SIGN_ROOT / "scripts" / "run_daily_public_signals.py"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run trading_sign current snapshot generation from the Quant daily pipeline."
    )
    ap.add_argument("--signal-date", required=True)
    ap.add_argument("--data-asof-date", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--exclude-tseries", action="store_true", help="Run existing public-model signals without T-series AI targets.")
    args = ap.parse_args()
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.quant2.operations import ai_retirement

    ai_retirement.load()
    args.exclude_tseries = True

    if not TRADING_SIGN_ROOT.exists():
        raise SystemExit(f"trading_sign root not found: {TRADING_SIGN_ROOT}")
    if not TRADING_SIGN_SCRIPT.exists():
        raise SystemExit(f"trading_sign runner not found: {TRADING_SIGN_SCRIPT}")

    env = os.environ.copy()
    pythonpath_parts = [str(TRADING_SIGN_SRC)]
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    cmd = [
        str(args.python),
        str(TRADING_SIGN_SCRIPT),
        "--signal-date",
        str(args.signal_date),
        "--data-asof-date",
        str(args.data_asof_date),
    ]
    if args.exclude_tseries:
        cmd.append("--exclude-tseries")
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=True)


if __name__ == "__main__":
    main()
