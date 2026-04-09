from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from trading_sign.pipeline import run_daily_signal_generation_from_public_sources
from trading_sign.snapshot import write_current_snapshots


def _default_signal_date() -> str:
    return date.today().isoformat()


def _default_data_asof_date(signal_date: str) -> str:
    dt = datetime.strptime(signal_date, "%Y-%m-%d").date()
    return (dt - timedelta(days=1)).isoformat()


def main() -> None:
    ap = argparse.ArgumentParser(description="Run thread-local daily public timing signals.")
    ap.add_argument("--signal-date", default=_default_signal_date())
    ap.add_argument("--data-asof-date", default="")
    ap.add_argument("--db-path", default=r"D:\Quant\trading_sign\data\db\trading_sign.db")
    ap.add_argument(
        "--output-dir",
        default=r"D:\Quant\trading_sign\service_platform\web\public_data\current",
    )
    ap.add_argument("--exclude-tseries", action="store_true")
    args = ap.parse_args()

    signal_date = str(args.signal_date)
    data_asof_date = str(args.data_asof_date).strip() or _default_data_asof_date(signal_date)
    db_path = Path(args.db_path)
    output_dir = Path(args.output_dir)

    results = run_daily_signal_generation_from_public_sources(
        signal_date=signal_date,
        data_asof_date=data_asof_date,
        db_path=db_path,
        include_tseries=not bool(args.exclude_tseries),
    )
    write_current_snapshots(output_dir, results)

    total_signals = sum(result.record_count for result in results)
    print("[ok] trading_sign daily signal run complete")
    print(f"signal_date={signal_date}")
    print(f"data_asof_date={data_asof_date}")
    print(f"model_count={len(results)}")
    print(f"signal_count={total_signals}")
    print(f"db_path={db_path}")
    print(f"output_dir={output_dir}")


if __name__ == "__main__":
    main()
