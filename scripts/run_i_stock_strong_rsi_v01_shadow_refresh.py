from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(r"D:\Quant")
MODEL_CODE = "I-STOCK-STRONG-RSI-V01"
RESEARCH_DB = ROOT / r"data\db\i_series_research_strong_rsi_raw_top30_s65.db"
RESEARCH_OUTDIR = ROOT / r"reports\i_series_stock_v01\strong_rsi_raw_top30_s65"
OP_DB = ROOT / r"data\db\i_series_operational.db"
OP_OUTDIR = ROOT / r"reports\i_series_stock_v01\operational_shadow"


def _run(cmd: list[str]) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run I-STOCK-STRONG-RSI-V01 shadow refresh.")
    ap.add_argument("--asof", required=True)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    python_exe = str(args.python)
    _run(
        [
            python_exe,
            str(ROOT / r"scripts\build_i_stock_v01_research.py"),
            "--model-code",
            MODEL_CODE,
            "--start",
            "2017-01-01",
            "--asof",
            args.asof,
            "--top-n",
            "30",
            "--min-score",
            "65",
            "--signal-profile",
            "early_strong_rsi",
            "--disable-liquidity-score",
            "--disable-buy-conversion-filter",
            "--selection-score",
            "raw",
            "--regime-mode",
            "none",
            "--out-db",
            str(RESEARCH_DB),
            "--outdir",
            str(RESEARCH_OUTDIR),
        ]
    )
    _run(
        [
            python_exe,
            str(ROOT / r"scripts\sync_i_series_shadow_operational.py"),
            "--source-db",
            str(RESEARCH_DB),
            "--asof",
            args.asof,
            "--out-db",
            str(OP_DB),
            "--outdir",
            str(OP_OUTDIR),
        ]
    )


if __name__ == "__main__":
    main()
