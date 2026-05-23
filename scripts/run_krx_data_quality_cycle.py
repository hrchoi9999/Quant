from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_ROOT = ROOT / "reports" / "data_quality" / "krx_operation_cycle"


@dataclass(frozen=True)
class CycleCommand:
    label: str
    asset_scope: str
    operation: str
    start: str
    end: str
    command: list[str]


def _parse_date(value: str) -> date:
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def _fmt(value: date) -> str:
    return value.strftime("%Y%m%d")


def _db_fmt(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def _default_python() -> str:
    candidate = ROOT / "venv64" / "Scripts" / "python.exe"
    return str(candidate) if candidate.exists() else sys.executable


def _window_for_args(args: argparse.Namespace) -> tuple[date, date]:
    asof = _parse_date(args.asof)
    if args.start or args.end:
        if not args.start or not args.end:
            raise ValueError("--start and --end must be provided together")
        return _parse_date(args.start), _parse_date(args.end)

    if args.cadence == "daily":
        return asof - timedelta(days=int(args.daily_lookback_days)), asof
    if args.cadence == "weekly":
        return asof - timedelta(days=int(args.weekly_lookback_days)), asof
    if args.cadence == "monthly":
        return asof - timedelta(days=int(args.monthly_lookback_days)), asof
    if args.cadence == "quarterly":
        year = int(args.target_year) if args.target_year else asof.year - 1
        return date(year, 1, 1), date(year, 12, 31)
    if args.cadence == "custom":
        raise ValueError("custom cadence requires --start and --end")
    raise ValueError(f"unsupported cadence: {args.cadence}")


def _default_operation(cadence: str) -> str:
    if cadence == "daily":
        return "audit"
    return "backfill"


def _scope_specs(args: argparse.Namespace) -> list[tuple[str, str, str]]:
    scopes = []
    requested = str(args.asset_scope).lower()
    if requested in {"stock", "both"}:
        scopes.append(("stock", "KOSPI,KOSDAQ", str(Path(args.stock_tickers_file))))
    if requested in {"etf", "both"}:
        scopes.append(("etf", "ETF", str(Path(args.etf_tickers_file))))
    return scopes


def _build_command(
    *,
    python_exe: str,
    operation: str,
    start: date,
    end: date,
    markets: str,
    tickers_file: str,
    ticker_col: str,
    sleep: float,
    notes: str,
    apply: bool,
) -> list[str]:
    if operation == "audit":
        return [
            python_exe,
            str(ROOT / "scripts" / "audit_krx_price_integrity.py"),
            "--start",
            _fmt(start),
            "--end",
            _fmt(end),
            "--markets",
            markets,
            "--tickers-file",
            tickers_file,
            "--ticker-col",
            ticker_col,
            "--sleep",
            str(float(sleep)),
            "--notes",
            notes,
        ]
    if operation == "backfill":
        cmd = [
            python_exe,
            str(ROOT / "scripts" / "backfill_krx_openapi_prices.py"),
            "--start",
            _fmt(start),
            "--end",
            _fmt(end),
            "--markets",
            markets,
            "--tickers-file",
            tickers_file,
            "--ticker-col",
            ticker_col,
            "--sleep",
            str(float(sleep)),
            "--notes",
            notes,
        ]
        if not apply:
            cmd.append("--dry-run")
        return cmd
    raise ValueError(f"unsupported operation: {operation}")


def _write_plan(
    *,
    out_dir: Path,
    run_id: str,
    args: argparse.Namespace,
    start: date,
    end: date,
    operation: str,
    commands: list[CycleCommand],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "cadence": args.cadence,
        "operation": operation,
        "apply": bool(args.apply),
        "execute": bool(args.execute),
        "asset_scope": args.asset_scope,
        "start": _db_fmt(start),
        "end": _db_fmt(end),
        "commands": [asdict(item) for item in commands],
    }
    (out_dir / "plan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# KRX Data Quality Cycle Plan",
        "",
        f"- run_id: `{run_id}`",
        f"- cadence: `{args.cadence}`",
        f"- operation: `{operation}`",
        f"- date_range: `{_db_fmt(start)} ~ {_db_fmt(end)}`",
        f"- asset_scope: `{args.asset_scope}`",
        f"- execute: `{bool(args.execute)}`",
        f"- apply_to_price_db: `{bool(args.apply)}`",
        "",
        "## Commands",
        "",
    ]
    for idx, item in enumerate(commands, start=1):
        lines.extend(
            [
                f"### {idx}. {item.label}",
                "",
                f"- scope: `{item.asset_scope}`",
                f"- operation: `{item.operation}`",
                f"- range: `{item.start} ~ {item.end}`",
                "",
                "```powershell",
                " ".join(item.command),
                "```",
                "",
            ]
        )
    (out_dir / "plan.md").write_text("\n".join(lines), encoding="utf-8")


def _execute_commands(out_dir: Path, commands: list[CycleCommand]) -> list[dict[str, object]]:
    results = []
    for idx, item in enumerate(commands, start=1):
        log_path = out_dir / f"command_{idx:02d}_{item.asset_scope}_{item.operation}.log"
        print(f"[RUN] {item.label}")
        proc = subprocess.run(
            item.command,
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log_path.write_text(proc.stdout or "", encoding="utf-8")
        result = {
            "label": item.label,
            "asset_scope": item.asset_scope,
            "operation": item.operation,
            "returncode": proc.returncode,
            "log_path": str(log_path),
        }
        results.append(result)
        print(f"[DONE] {item.label} returncode={proc.returncode} log={log_path}")
        if proc.returncode != 0:
            break
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan or execute the KRX rolling data-quality cycle for audit/backfill operations."
    )
    parser.add_argument("--asof", default=date.today().strftime("%Y%m%d"), help="Cycle anchor date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--cadence", choices=["daily", "weekly", "monthly", "quarterly", "custom"], default="daily")
    parser.add_argument("--operation", choices=["auto", "audit", "backfill"], default="auto")
    parser.add_argument("--asset-scope", choices=["stock", "etf", "both"], default="both")
    parser.add_argument("--start", default="", help="Override start date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", default="", help="Override end date, YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--target-year", type=int, default=0, help="Quarterly cadence target full year. Defaults to previous year.")
    parser.add_argument("--daily-lookback-days", type=int, default=14)
    parser.add_argument("--weekly-lookback-days", type=int, default=93)
    parser.add_argument("--monthly-lookback-days", type=int, default=366)
    parser.add_argument("--stock-tickers-file", default=str(ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"))
    parser.add_argument("--etf-tickers-file", default=str(ROOT / r"data\universe\universe_etf_master_latest.csv"))
    parser.add_argument("--ticker-col", default="ticker")
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--python", default=_default_python())
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--execute", action="store_true", help="Actually run the planned commands. Default is plan-only.")
    parser.add_argument("--apply", action="store_true", help="Allow backfill commands to upsert into price.db. Default is dry-run.")
    args = parser.parse_args()

    start, end = _window_for_args(args)
    if start > end:
        raise ValueError(f"start must be <= end: {start} > {end}")

    operation = _default_operation(args.cadence) if args.operation == "auto" else str(args.operation)
    run_id = f"krx_cycle_{args.cadence}_{operation}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(args.out_root) / run_id

    commands: list[CycleCommand] = []
    for scope, markets, tickers_file in _scope_specs(args):
        if not Path(tickers_file).exists():
            raise FileNotFoundError(f"missing tickers file for {scope}: {tickers_file}")
        notes = f"krx_cycle cadence={args.cadence} operation={operation} scope={scope} apply={bool(args.apply)}"
        command = _build_command(
            python_exe=str(args.python),
            operation=operation,
            start=start,
            end=end,
            markets=markets,
            tickers_file=tickers_file,
            ticker_col=str(args.ticker_col),
            sleep=float(args.sleep),
            notes=notes,
            apply=bool(args.apply),
        )
        commands.append(
            CycleCommand(
                label=f"{scope}_{operation}_{_fmt(start)}_{_fmt(end)}",
                asset_scope=scope,
                operation=operation,
                start=_db_fmt(start),
                end=_db_fmt(end),
                command=command,
            )
        )

    _write_plan(out_dir=out_dir, run_id=run_id, args=args, start=start, end=end, operation=operation, commands=commands)
    print(f"[DONE] plan_dir={out_dir}")
    if not args.execute:
        print("[DONE] plan-only mode. Add --execute to run commands.")
        return

    results = _execute_commands(out_dir, commands)
    (out_dir / "execution_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item for item in results if int(item["returncode"]) != 0]
    if failed:
        raise SystemExit(1)
    print(f"[DONE] execution_results={out_dir / 'execution_results.json'}")


if __name__ == "__main__":
    main()
