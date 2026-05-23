from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(r"D:\Quant")
PYTHON_EXE = PROJECT_ROOT / r"venv64\Scripts\python.exe"
BACKTEST_SCRIPT = PROJECT_ROOT / r"src\backtest\run_backtest_s2_v5.py"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
REGIME_DB = PROJECT_ROOT / r"data\db\regime.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"
OUTDIR = PROJECT_ROOT / r"reports\backtest_s2_pit_v01"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run operational S2_PIT_V01 backtest.")
    ap.add_argument("--start", default="2024-01-31")
    ap.add_argument("--end", required=True)
    ap.add_argument("--outdir", default=str(OUTDIR))
    return ap.parse_args()


def build_cmd(start: str, end: str, outdir: Path) -> list[str]:
    return [
        str(PYTHON_EXE),
        str(BACKTEST_SCRIPT),
        "--regime-db",
        str(REGIME_DB),
        "--regime-table",
        "regime_history",
        "--price-db",
        str(PRICE_DB),
        "--price-table",
        "prices_daily",
        "--fundamentals-db",
        str(FUND_DB),
        "--fundamentals-view",
        "s2_fund_scores_pit_monthly",
        "--universe-file",
        str(UNIVERSE_CSV),
        "--ticker-col",
        "ticker",
        "--horizon",
        "3m",
        "--start",
        start,
        "--end",
        end,
        "--rebalance",
        "W",
        "--weekly-anchor-weekday",
        "2",
        "--weekly-holiday-shift",
        "prev",
        "--good-regimes",
        "4,3",
        "--top-n",
        "30",
        "--sma-window",
        "140",
        "--market-gate",
        "--market-scope",
        "KOSPI",
        "--market-sma-window",
        "60",
        "--market-sma-mult",
        "1.02",
        "--fee-bps",
        "5",
        "--slippage-bps",
        "5",
        "--gsheet-ledger",
        "--outdir",
        str(outdir),
    ]


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = build_cmd(args.start, args.end, outdir)
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
    print(f"[OK] S2_PIT_V01 backtest completed -> {outdir}")


if __name__ == "__main__":
    sys.exit(main())
