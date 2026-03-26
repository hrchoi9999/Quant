from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smoke validate ETF allocation backtest.")
    ap.add_argument("--asof", default="2026-03-17")
    ap.add_argument("--start", default="2024-01-02")
    ap.add_argument("--end", default="2026-03-17")
    ap.add_argument("--rebalance", default="M", choices=["M", "W"])
    ap.add_argument("--force-mode", default="", choices=["", "risk_on", "neutral", "risk_off"])
    ap.add_argument("--outdir", default=str(PROJECT_ROOT / r"reports\backtest_etf_allocation"))
    args = ap.parse_args()

    cmd = [
        str(PROJECT_ROOT / r"venv64\Scripts\python.exe"),
        str(PROJECT_ROOT / r"src\backtest\run_backtest_etf_allocation.py"),
        "--asof",
        str(args.asof),
        "--start",
        str(args.start),
        "--end",
        str(args.end),
        "--rebalance",
        str(args.rebalance).upper(),
        "--outdir",
        str(args.outdir),
    ]
    if args.force_mode:
        cmd.extend(["--force-mode", str(args.force_mode)])
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))

    outdir = Path(args.outdir)
    mode_tag = f"_{str(args.force_mode).lower()}" if str(args.force_mode).strip() else ""
    stamp = f"{str(args.asof).replace('-', '')}_{str(args.rebalance).upper()}_{str(args.start).replace('-', '')}_{str(args.end).replace('-', '')}{mode_tag}"
    summary_path = outdir / f"etf_alloc_summary_{stamp}.csv"
    equity_path = outdir / f"etf_alloc_equity_{stamp}.csv"
    weights_path = outdir / f"etf_alloc_weights_{stamp}.csv"
    trades_path = outdir / f"etf_alloc_trades_{stamp}.csv"

    for path in [summary_path, equity_path, weights_path, trades_path]:
        if not path.exists():
            raise AssertionError(f"Missing output file: {path}")

    summary_df = pd.read_csv(summary_path)
    equity_df = pd.read_csv(equity_path)
    weights_df = pd.read_csv(weights_path)
    trades_df = pd.read_csv(trades_path)

    if summary_df.empty:
        raise AssertionError("summary is empty")
    if equity_df.empty:
        raise AssertionError("equity is empty")
    if weights_df.empty:
        raise AssertionError("weights is empty")

    required_summary = {"strategy", "start", "end", "cagr", "mdd", "sharpe", "turnover", "rebalance_count"}
    missing_summary = required_summary - set(summary_df.columns)
    if missing_summary:
        raise AssertionError(f"summary missing columns: {sorted(missing_summary)}")

    required_equity = {"date", "port_ret", "equity", "mode", "cash_weight"}
    if not required_equity.issubset(set(equity_df.columns)):
        raise AssertionError(f"equity missing columns: {sorted(required_equity - set(equity_df.columns))}")

    required_weights = {"rebalance_date", "trade_date", "mode", "group_key", "ticker", "weight"}
    if not required_weights.issubset(set(weights_df.columns)):
        raise AssertionError(f"weights missing columns: {sorted(required_weights - set(weights_df.columns))}")

    modes = set(weights_df["mode"].dropna().astype(str).tolist())
    expected_mode = str(args.force_mode).lower() if args.force_mode else ""
    if expected_mode and expected_mode not in modes:
        raise AssertionError(f"forced mode not found in weights output: {expected_mode}")
    if not expected_mode and not modes.intersection({"risk_on", "neutral", "risk_off"}):
        raise AssertionError("weights output does not contain expected modes")

    if not trades_df.empty and "side" not in trades_df.columns:
        raise AssertionError("trades missing side column")

    print(f"[OK] summary={summary_path}")
    print(f"[OK] equity_rows={len(equity_df)}")
    print(f"[OK] weights_rows={len(weights_df)}")
    print(f"[OK] trades_rows={len(trades_df)}")
    print(f"[OK] modes={sorted(modes)}")


if __name__ == "__main__":
    main()
