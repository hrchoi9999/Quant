from __future__ import annotations

import argparse
import atexit
import csv
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Quant")
DEFAULT_QM_MARKET_CONTEXT_DIR = Path(
    r"D:\QuantMarket\service_platform\quant_model_handoff\market_context\current"
)
TIMING_LOCK = threading.Lock()
TIMING_ROWS: list[dict[str, object]] = []
TIMING_REPORT_PATH: Path | None = None
PIPELINE_STATUS = "not_started"
PIPELINE_STARTED_AT: datetime | None = None
PIPELINE_START_MONO: float | None = None


def _resume_hint_for_group(group_name: str) -> str:
    hints = {
        "prep": "Fix the data/prep issue, then rerun --data-refresh-only for the same asof.",
        "models": "Fix the model issue, then rerun --model-run-only for the same asof after QM handoff is ready.",
        "router_reports": "Rerun --model-run-only for the same asof, or manually rerun router/report commands and downstream publish steps.",
        "tseries_shadow": "Rerun the failed T-series refresh command, then continue from I-series/publish steps.",
        "iseries_shadow": "Rerun the failed I-series refresh command, then continue from publish steps.",
        "publish_ingest": "Rerun ingest/publish for the same asof, then rebuild web/admin current payloads.",
        "web_snapshot": "Rerun web snapshot/history payload commands for the same asof, then validate contract.",
        "admin_tracker": "Rerun admin tracker build/validation for the same asof, then continue AI/trading/contract steps.",
        "ai_overlay": "Rerun the failed AI overlay command, then continue remaining AI/trading/contract steps.",
        "trading_sign": "Rerun trading_sign generation and validation for the same asof, then validate contract.",
        "contract": "Inspect the contract report, fix missing/stale payloads, then rerun validate_daily_pipeline_contract.py.",
        "remote_publish": "Rerun GCS publish only after local contract validation passes.",
        "generated_csv_db_sync": "Rerun sync_generated_csv_to_db.py for the same asof.",
        "generated_cleanup": "Rerun cleanup_generated_files.py for the same asof if archival cleanup is required.",
    }
    return hints.get(group_name, "Fix the failed command, then rerun the same stage or downstream commands for the same asof.")


def _command_label(cmd: list[str]) -> str:
    if not cmd:
        return ""
    for part in cmd:
        text = str(part)
        if text.endswith(".py"):
            return Path(text).name
    if len(cmd) >= 3 and cmd[1] == "-m":
        return str(cmd[2])
    return Path(str(cmd[0])).name


def _record_timing(
    *,
    group_name: str,
    item_name: str,
    cmd: list[str],
    started_at: datetime,
    finished_at: datetime,
    elapsed_seconds: float,
    return_code: int,
) -> None:
    with TIMING_LOCK:
        TIMING_ROWS.append(
            {
                "group": group_name,
                "item": item_name,
                "label": _command_label(cmd),
                "return_code": int(return_code),
                "elapsed_seconds": round(float(elapsed_seconds), 3),
                "started_at": started_at.isoformat(timespec="seconds"),
                "finished_at": finished_at.isoformat(timespec="seconds"),
                "command": " ".join(str(part) for part in cmd),
            }
        )


def _run_timed(cmd: list[str], cwd: Path, group_name: str, item_name: str) -> int:
    started_at = datetime.now()
    start = time.perf_counter()
    completed = subprocess.run(cmd, cwd=str(cwd), check=False)
    elapsed = time.perf_counter() - start
    finished_at = datetime.now()
    _record_timing(
        group_name=group_name,
        item_name=item_name,
        cmd=cmd,
        started_at=started_at,
        finished_at=finished_at,
        elapsed_seconds=elapsed,
        return_code=int(completed.returncode),
    )
    print(f"[DONE:{group_name}] rc={completed.returncode} elapsed={elapsed:.1f}s label={_command_label(cmd)}")
    return int(completed.returncode)


def _configure_timing_report(asof: str) -> None:
    global TIMING_REPORT_PATH, PIPELINE_STARTED_AT, PIPELINE_START_MONO
    PIPELINE_STARTED_AT = datetime.now()
    PIPELINE_START_MONO = time.perf_counter()
    out_dir = PROJECT_ROOT / "reports" / "pipeline_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    TIMING_REPORT_PATH = out_dir / f"daily_quant_pipeline_timing_{asof}_{stamp}.json"
    print(f"[TIMING] report={TIMING_REPORT_PATH}")


def _write_timing_report() -> None:
    if TIMING_REPORT_PATH is None:
        return
    rows = sorted(TIMING_ROWS, key=lambda row: str(row.get("started_at", "")))
    total = round(sum(float(row.get("elapsed_seconds") or 0.0) for row in rows), 3)
    by_group: dict[str, float] = {}
    group_bounds: dict[str, tuple[datetime, datetime]] = {}
    for row in rows:
        group = str(row.get("group") or "unknown")
        by_group[group] = round(by_group.get(group, 0.0) + float(row.get("elapsed_seconds") or 0.0), 3)
        try:
            started_at = datetime.fromisoformat(str(row.get("started_at")))
            finished_at = datetime.fromisoformat(str(row.get("finished_at")))
        except ValueError:
            continue
        if group not in group_bounds:
            group_bounds[group] = (started_at, finished_at)
        else:
            prev_start, prev_finish = group_bounds[group]
            group_bounds[group] = (min(prev_start, started_at), max(prev_finish, finished_at))
    group_wall = {
        group: round((finished_at - started_at).total_seconds(), 3)
        for group, (started_at, finished_at) in group_bounds.items()
    }
    wall_elapsed = None
    if PIPELINE_START_MONO is not None:
        wall_elapsed = round(time.perf_counter() - PIPELINE_START_MONO, 3)
    status = "interrupted_or_failed" if PIPELINE_STATUS == "running" else PIPELINE_STATUS
    failed_rows = [row for row in rows if int(row.get("return_code") or 0) != 0]
    failed_row = failed_rows[0] if failed_rows else None
    last_completed = next((row for row in reversed(rows) if int(row.get("return_code") or 0) == 0), None)
    failure = None
    if failed_row is not None:
        failed_group = str(failed_row.get("group") or "unknown")
        failure = {
            "group": failed_group,
            "item": failed_row.get("item"),
            "label": failed_row.get("label"),
            "return_code": failed_row.get("return_code"),
            "command": failed_row.get("command"),
            "resume_hint": _resume_hint_for_group(failed_group),
        }
    payload = {
        "status": status,
        "started_at": PIPELINE_STARTED_AT.isoformat(timespec="seconds") if PIPELINE_STARTED_AT else None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "wall_elapsed_seconds": wall_elapsed,
        "command_count": len(rows),
        "completed_command_count": len([row for row in rows if int(row.get("return_code") or 0) == 0]),
        "failed_command_count": len(failed_rows),
        "last_completed_command": last_completed,
        "failure": failure,
        "summed_command_seconds": total,
        "group_elapsed_seconds_sum": by_group,
        "group_wall_elapsed_seconds": group_wall,
        "top_commands": sorted(rows, key=lambda row: float(row.get("elapsed_seconds") or 0.0), reverse=True)[:15],
        "commands": rows,
    }
    TIMING_REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[TIMING] wrote {TIMING_REPORT_PATH}")


atexit.register(_write_timing_report)


def _run(cmd: list[str], cwd: Path, group_name: str = "serial", item_name: str = "") -> None:
    print(f"[RUN] {' '.join(cmd)}")
    return_code = _run_timed(cmd, cwd, group_name, item_name or _command_label(cmd))
    if return_code != 0:
        print(f"[FAIL:{group_name}] rc={return_code} label={_command_label(cmd)}")
        print(f"[RESUME_HINT] {_resume_hint_for_group(group_name)}")
        raise subprocess.CalledProcessError(return_code, cmd)


def _normalize_asof(value: str) -> str:
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _qm_market_context_status(asof: str, handoff_dir: Path) -> dict[str, object]:
    manifest_path = handoff_dir / "quant_model_handoff_manifest.json"
    forecast_path = handoff_dir / "market_forecast_ai_calibrated_daily_current.csv"
    status: dict[str, object] = {
        "handoff_dir": str(handoff_dir),
        "manifest_path": str(manifest_path),
        "forecast_path": str(forecast_path),
        "manifest_exists": manifest_path.exists(),
        "forecast_exists": forecast_path.exists(),
        "production_ready": False,
        "forecast_horizon": "20d",
        "max_forecast_asof": None,
        "scopes_20d": [],
        "ready": False,
    }
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_status = manifest.get("status") or {}
            status["production_ready"] = bool(manifest_status.get("production_ready"))
            status["manifest_generated_at"] = manifest.get("generated_at")
            status["handoff_version"] = manifest.get("handoff_version")
            status["manifest_asof_date"] = _normalize_asof(str(manifest.get("asof_date") or ""))
            status["manifest_latest_asof_date"] = _normalize_asof(str(manifest.get("latest_asof_date") or ""))
            status["manifest_expected_asof_date"] = _normalize_asof(str(manifest.get("expected_asof_date") or ""))
        except Exception as exc:  # pragma: no cover - defensive operational logging
            status["manifest_error"] = str(exc)
    if forecast_path.exists():
        max_asof = ""
        scopes: set[str] = set()
        try:
            with forecast_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if str(row.get("forecast_horizon") or "").strip() != "20d":
                        continue
                    row_asof = _normalize_asof(str(row.get("asof_date") or ""))
                    if row_asof > max_asof:
                        max_asof = row_asof
                    if row_asof == _normalize_asof(asof):
                        scope = str(row.get("market_scope") or "").strip()
                        if scope:
                            scopes.add(scope)
            status["max_forecast_asof"] = max_asof or None
            status["scopes_20d"] = sorted(scopes)
        except Exception as exc:  # pragma: no cover - defensive operational logging
            status["forecast_error"] = str(exc)
    target_asof = _normalize_asof(asof)
    required_scopes = {"ALL", "KOSPI", "KOSDAQ"}
    scopes_20d = set(status.get("scopes_20d") or [])
    manifest_dates = [
        status.get("manifest_asof_date"),
        status.get("manifest_latest_asof_date"),
        status.get("manifest_expected_asof_date"),
    ]
    manifest_date_ready = all((not value) or value == target_asof for value in manifest_dates)
    status["manifest_date_ready"] = manifest_date_ready
    status["ready"] = bool(
        status.get("manifest_exists")
        and status.get("forecast_exists")
        and status.get("production_ready")
        and manifest_date_ready
        and status.get("max_forecast_asof") >= target_asof
        and required_scopes.issubset(scopes_20d)
    )
    status["required_scopes_20d"] = sorted(required_scopes)
    status["target_asof"] = target_asof
    return status


def _check_qm_market_context(asof: str, handoff_dir: Path, allow_stale: bool) -> None:
    status = _qm_market_context_status(asof, handoff_dir)
    print("[QM MARKET CONTEXT]")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if status.get("ready"):
        return
    message = (
        "QM market context is not ready for Quant model run. "
        f"target_asof={status.get('target_asof')} max_forecast_asof={status.get('max_forecast_asof')} "
        f"scopes_20d={status.get('scopes_20d')}"
    )
    if allow_stale:
        print(f"[WARN] {message} | continuing because --allow-stale-qm-market-context is set")
        return
    raise SystemExit(
        f"{message}. Run Quant with --data-refresh-only first, let QM rebuild market context, "
        "then rerun Quant with --model-run-only."
    )


def _run_parallel(cmds: list[list[str]], cwd: Path, group_name: str, max_workers: int) -> None:
    if not cmds:
        return
    worker_count = max(1, min(int(max_workers), len(cmds)))
    if worker_count == 1:
        for index, cmd in enumerate(cmds):
            _run(cmd, cwd, group_name, f"{index + 1}/{len(cmds)}")
        return

    def _worker(index: int, cmd: list[str]) -> tuple[int, list[str], int]:
        print(f"[RUN:{group_name}:{index + 1}/{len(cmds)}] {' '.join(cmd)}")
        return_code = _run_timed(cmd, cwd, group_name, f"{index + 1}/{len(cmds)}")
        return index, cmd, int(return_code)

    failures: list[tuple[int, list[str], int]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(_worker, index, cmd) for index, cmd in enumerate(cmds)]
        for future in as_completed(futures):
            index, cmd, return_code = future.result()
            if return_code != 0:
                failures.append((index, cmd, return_code))
    if failures:
        details = "; ".join(
            f"#{index + 1} rc={return_code}: {' '.join(cmd)}"
            for index, cmd, return_code in sorted(failures, key=lambda item: item[0])
        )
        raise SystemExit(f"{group_name} jobs failed: {details}")


def _run_profile_sequences(
    cmds: list[list[str]],
    cwd: Path,
    max_workers: int,
) -> None:
    if not cmds:
        return
    sequences = []
    for index in range(0, len(cmds), 3):
        chunk = cmds[index : index + 3]
        profile = "unknown"
        for part_index, part in enumerate(chunk[0]):
            if part == "--service-profile" and part_index + 1 < len(chunk[0]):
                profile = str(chunk[0][part_index + 1])
                break
        sequences.append((profile, chunk))

    worker_count = max(1, min(int(max_workers), len(sequences)))
    if worker_count == 1:
        for profile, chunk in sequences:
            for cmd in chunk:
                _run(cmd, cwd, "router_reports", profile)
        return

    def _worker(profile: str, chunk: list[list[str]]) -> tuple[str, list[tuple[list[str], int]]]:
        failures: list[tuple[list[str], int]] = []
        for cmd in chunk:
            print(f"[RUN:router_reports:{profile}] {' '.join(cmd)}")
            return_code = _run_timed(cmd, cwd, "router_reports", profile)
            if return_code != 0:
                failures.append((cmd, return_code))
                break
        return profile, failures

    failures: list[tuple[str, list[tuple[list[str], int]]]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(_worker, profile, chunk) for profile, chunk in sequences]
        for future in as_completed(futures):
            profile, profile_failures = future.result()
            if profile_failures:
                failures.append((profile, profile_failures))
    if failures:
        details = "; ".join(
            f"{profile}: " + ", ".join(f"rc={return_code}: {' '.join(cmd)}" for cmd, return_code in items)
            for profile, items in failures
        )
        raise SystemExit(f"router/profile jobs failed: {details}")


def build_commands(
    asof: str,
    python_exe: str,
    core_db: str,
    detail_db: str,
    core2_tag: str,
    include_etf: bool,
    etf_start: str,
    include_service_analytics: bool,
    include_tseries_shadow: bool,
    include_iseries_shadow: bool,
    include_ai_overlay: bool,
    include_ai_research: bool,
    include_remote_current_publish: bool,
    include_generated_cleanup: bool,
    full_regime_rebuild: bool,
    full_validation: bool,
    pipeline_mode: str,
) -> tuple[list[list[str]], list[str], list[list[str]], list[list[str]], list[list[str]], list[list[str]], list[str], list[str], list[list[str]], list[list[str]], list[list[str]], list[list[str]], list[list[str]], list[list[str]], list[list[str]], list[list[str]]]:
    token = asof.replace("-", "")
    prep_cmds: list[list[str]] = [[
        python_exe,
        str(PROJECT_ROOT / r"src\pipelines\rebuild_mix_universe_and_refresh_dbs.py"),
        "--asof", asof,
        "--update-latest",
    ]]
    if full_regime_rebuild:
        prep_cmds[0].extend(["--regime-years", "10"])

    if include_etf:
        prep_cmds.extend([
            [python_exe, str(PROJECT_ROOT / r"src\collectors\universe\build_universe_etf_krx.py"), "--asof", asof, "--update-latest", "--upsert-instrument-master"],
            [python_exe, str(PROJECT_ROOT / r"src\collectors\price\fetch_krx_openapi_daily_prices.py"), "--start", asof, "--end", asof, "--markets", "ETF", "--tickers-file", str(PROJECT_ROOT / r"data\universe\universe_etf_master_latest.csv"), "--ticker-col", "ticker"],
            [python_exe, str(PROJECT_ROOT / r"src\collectors\universe\build_universe_etf_core.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\sync_multiasset_metadata.py"), "--asof", asof],
        ])

    prep_cmds.extend([
        [python_exe, str(PROJECT_ROOT / r"src\features\build_s3_price_features_daily.py"), "--end", asof],
        [python_exe, str(PROJECT_ROOT / r"src\features\build_s3_fund_features_monthly.py"), "--mode", "rebuild"],
        [
            python_exe,
            str(PROJECT_ROOT / r"src\fundamentals\build_fundamentals_pit_qh_monthly.py"),
            "--dart-db",
            str(PROJECT_ROOT / r"data\db\dart_main.db"),
            "--universe-file",
            str(PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"),
            "--ticker-col",
            "ticker",
            "--price-db",
            str(PROJECT_ROOT / r"data\db\price.db"),
            "--price-table",
            "prices_daily",
            "--end",
            asof,
            "--out-db",
            str(PROJECT_ROOT / r"data\db\fundamentals.db"),
        ],
    ])

    s2_cmd = [
        python_exe, "-m", "src.backtest.run_backtest_v5", "--s2-refactor",
        "--regime-db", str(PROJECT_ROOT / r"data\db\regime.db"), "--regime-table", "regime_history",
        "--price-db", str(PROJECT_ROOT / r"data\db\price.db"), "--price-table", "prices_daily",
        "--fundamentals-db", str(PROJECT_ROOT / r"data\db\fundamentals.db"), "--fundamentals-view", "s2_fund_scores_monthly",
        "--universe-file", str(PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"), "--ticker-col", "ticker",
        "--horizon", "3m", "--start", "2013-10-14", "--end", asof,
        "--rebalance", "W", "--weekly-anchor-weekday", "2", "--weekly-holiday-shift", "prev",
        "--good-regimes", "4,3", "--top-n", "30", "--sma-window", "140",
        "--market-gate", "--market-scope", "KOSPI", "--market-sma-window", "60", "--market-sma-mult", "1.02",
        "--fee-bps", "5", "--slippage-bps", "5", "--outdir", str(PROJECT_ROOT / r"reports\backtest_regime_refactor"),
    ]

    model_cmds = [
        [python_exe, str(PROJECT_ROOT / r"src\experiments\run_s3_trend_hold_top20.py"), "--asof", asof, "--start", "2013-10-14", "--end", asof, "--top-n", "20", "--min-holdings", "10", "--weekly-anchor-weekday", "2"],
        [python_exe, str(PROJECT_ROOT / r"src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py"), "--asof", asof, "--start", "2013-10-14", "--end", asof, "--top-n", "20", "--min-holdings", "10", "--tag", core2_tag, "--gate-enabled", "1", "--gate-open-th", "0.50", "--gate-close-th", "0.46", "--gate-use-slope", "1", "--gate-use-ma-stack", "1"],
        [python_exe, str(PROJECT_ROOT / r"scripts\run_s2_pit_v01_operational_backtest.py"), "--end", asof],
        [python_exe, str(PROJECT_ROOT / r"scripts\run_s3_accel_v01_operational_backtest.py"), "--asof", asof],
        [python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_s4_risk_on_allocation.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M"],
        [python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_s5_neutral_allocation.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M"],
        [python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_s6_defensive_allocation.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M"],
    ]

    tseries_shadow_cmds: list[list[str]] = []
    if include_tseries_shadow:
        tseries_shadow_cmds.append([python_exe, str(PROJECT_ROOT / r"scripts\run_t_stock_v01_operational_refresh.py"), "--asof", asof])
        if include_etf:
            tseries_shadow_cmds.append([python_exe, str(PROJECT_ROOT / r"scripts\run_t_etf_v01_operational_refresh.py"), "--asof", asof])

    iseries_shadow_cmds: list[list[str]] = []
    if include_iseries_shadow:
        iseries_shadow_cmds.append([python_exe, str(PROJECT_ROOT / r"scripts\run_i_stock_strong_rsi_v01_shadow_refresh.py"), "--asof", asof, "--python", python_exe])

    router_and_reports_cmds = []
    for profile in ["stable", "balanced", "growth"]:
        router_and_reports_cmds.append([python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_multiasset_router.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M", "--service-profile", profile])
        router_and_reports_cmds.append([python_exe, str(PROJECT_ROOT / r"scripts\run_model_comparison.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M", "--service-profile", profile])
        router_and_reports_cmds.append([python_exe, str(PROJECT_ROOT / r"src\reporting\render_redbot_user_report.py"), "--service-profile", profile, "--asof", asof])

    ingest_cmd = [python_exe, str(PROJECT_ROOT / r"src\quant_service\ingest_backtest_results.py"), "--asof", asof, "--core-db", core_db, "--detail-db", detail_db]
    publish_cmd = [python_exe, str(PROJECT_ROOT / r"src\quant_service\publish_backtest_results.py"), "--asof", asof, "--core-db", core_db, "--detail-db", detail_db]

    web_snapshot_cmds = [
        [python_exe, str(PROJECT_ROOT / r"service_platform\publishers\build_user_facing_snapshots.py"), "--asof", asof],
        [python_exe, str(PROJECT_ROOT / r"scripts\validate_redbot_web_snapshots.py"), "--asof", asof, "--skip-build"],
        [python_exe, str(PROJECT_ROOT / r"service_platform\publishers\build_redbot_history_payloads.py"), "--asof", asof],
        [python_exe, str(PROJECT_ROOT / r"scripts\validate_redbot_history_payloads.py"), "--asof", asof],
    ]

    admin_new_entry_cmds: list[list[str]] = [
        [python_exe, str(PROJECT_ROOT / r"scripts\build_admin_new_entry_tracker.py"), "--asof", asof],
        [
            python_exe,
            str(PROJECT_ROOT / r"scripts\validate_admin_new_entry_tracker.py"),
            "--asof",
            asof,
            "--mode",
            "full" if full_validation else "quick",
        ],
    ]
    ai_overlay_cmds: list[list[str]] = []
    if include_ai_overlay:
        ai_daily_light_cmds = [
            [
                python_exe,
                str(PROJECT_ROOT / r"scripts\build_ai_overlay_v01.py"),
                "--asof",
                asof,
                "--admin-payload",
                str(PROJECT_ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"),
                "--feature-set",
                "kiwoom_dart",
            ],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_ai_shadow_performance_tracker.py"), "--asof", asof],
            [
                python_exe,
                str(PROJECT_ROOT / r"scripts\build_ai_live_shadow_tracker.py"),
                "--shadow-asof",
                "all",
                "--asof",
                asof,
            ],
            [python_exe, str(PROJECT_ROOT / r"scripts\compare_ai_common_vs_model_specific.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_ai_shadow_observation_payload.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_downside_risk_ai_shadow_tracker.py"), "--shadow-asof", "all", "--performance-asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_ai_learning_models_admin_payload.py"), "--asof", asof],
        ]
        ai_training_cmds = [
            [python_exe, str(PROJECT_ROOT / r"scripts\build_downside_risk_ai_v01.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_candidate_rank_delta_ai_v01.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_theme_persistence_ai_v01.py"), "--asof", asof],
        ]
        e_series_research_cmds = [
            [python_exe, str(PROJECT_ROOT / r"scripts\build_e_series_etf_role_taxonomy.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_etf_tseries_pit_backfill_v1.py"), "--run-date", token, "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_e_series_etf_mart_v2.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_e_series_etf_sleeve_selection_ai_v1.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_sleeve_portfolio_backtest.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_etf_ai_shadow_portfolio.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_ai_learning_models_admin_payload.py"), "--asof", asof],
        ]
        e_series_policy_research_cmds = [
            [python_exe, str(PROJECT_ROOT / r"scripts\fetch_krx_etf_distributions.py"), "--asof", asof, "--max-dates", "1"],
            [python_exe, str(PROJECT_ROOT / r"scripts\fetch_issuer_etf_distributions.py"), "--asof", asof, "--providers", "kodex,tiger,ace,sol,csv", "--kodex-pages", "2", "--max-notices", "20", "--provider-sleep", "0.8"],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_total_return_adjustment_check.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_selection_policy_walk_forward.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_tail_risk_policy_walk_forward.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_mode_switch_policy_walk_forward.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_e_series_etf_mode_switch_holdings_compare.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_mode_switch_cost_adjusted.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_mode_switch_turnover_buffer.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_mode_switch_stability_check.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_operational_hardening.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_e_series_etf_operational_policy_hierarchy.py"), "--asof", asof],
            [
                python_exe,
                str(PROJECT_ROOT / r"scripts\run_ai_overlay_shadow_operational_refresh.py"),
                "--asof",
                asof,
                "--python",
                python_exe,
            ],
        ]
        if pipeline_mode == "research_full":
            e_series_distribution_cmds = e_series_policy_research_cmds[:2]
            e_series_total_return_cmds = e_series_policy_research_cmds[2:3]
            e_series_walk_forward_cmds = e_series_policy_research_cmds[3:12]
            ai_overlay_operational_backtest_cmds = e_series_policy_research_cmds[12:]
            ai_overlay_cmds = (
                ai_training_cmds
                + ai_daily_light_cmds[:6]
                + e_series_distribution_cmds
                + e_series_research_cmds[:3]
                + e_series_total_return_cmds
                + e_series_research_cmds[3:5]
                + e_series_walk_forward_cmds
                + ai_overlay_operational_backtest_cmds
                + e_series_research_cmds[5:]
            )
            if include_ai_research:
                ai_overlay_cmds.insert(
                    len(ai_training_cmds) + len(ai_daily_light_cmds[:6]) + len(e_series_distribution_cmds) + 5,
                    [python_exe, str(PROJECT_ROOT / r"scripts\run_e_series_etf_selection_policy_ablation.py"), "--asof", asof],
                )
        else:
            ai_overlay_cmds = ai_daily_light_cmds

    trading_sign_cmds: list[list[str]] = [
        [
            python_exe,
            str(PROJECT_ROOT / r"scripts\run_trading_sign_from_quant_pipeline.py"),
            "--signal-date",
            asof,
            "--data-asof-date",
            asof,
            "--python",
            python_exe,
        ],
        [python_exe, str(PROJECT_ROOT / r"scripts\validate_trading_sign_snapshots.py"), "--asof", asof],
    ]

    prepublish_contract_cmds: list[list[str]] = []
    if pipeline_mode == "research_full":
        prepublish_contract_cmds.append(
            [python_exe, str(PROJECT_ROOT / r"scripts\build_internal_model_validation_current.py"), "--asof", asof]
        )
    prepublish_contract_cmds.append(
        [python_exe, str(PROJECT_ROOT / r"scripts\validate_daily_pipeline_contract.py"), "--asof", asof]
    )

    remote_publish_cmds: list[list[str]] = []
    if include_remote_current_publish:
        remote_publish_cmds = [
            [python_exe, str(PROJECT_ROOT / r"scripts\publish_public_current_to_gcs.py")],
        ]

    service_analytics_cmds: list[list[str]] = []
    if include_service_analytics:
        service_analytics_cmds = [
            [python_exe, str(PROJECT_ROOT / r"scripts\build_service_analytics.py")],
            [python_exe, str(PROJECT_ROOT / r"scripts\validate_service_analytics.py")],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_service_analytics_review.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_service_analytics_bundle_p1.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\validate_service_analytics_bundle_p1.py")],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_service_analytics_bundle_p2.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\validate_service_analytics_bundle_p2.py")],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_service_analytics_bundle_p3.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\validate_service_analytics_bundle_p3.py")],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_service_analytics_bundle_p4.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\validate_service_analytics_bundle_p4.py")],
            [python_exe, str(PROJECT_ROOT / r"scripts\build_service_analytics_bundle_p5.py"), "--asof", asof],
            [python_exe, str(PROJECT_ROOT / r"scripts\validate_service_analytics_bundle_p5.py")],
        ]

    generated_cleanup_cmds: list[list[str]] = []
    if include_generated_cleanup:
        generated_cleanup_cmds = [
            [python_exe, str(PROJECT_ROOT / r"scripts\cleanup_generated_files.py"), "--asof", asof, "--execute", "--write-manifest"],
        ]

    return (
        prep_cmds,
        s2_cmd,
        model_cmds,
        router_and_reports_cmds,
        tseries_shadow_cmds,
        iseries_shadow_cmds,
        ingest_cmd,
        publish_cmd,
        web_snapshot_cmds,
        admin_new_entry_cmds,
        ai_overlay_cmds,
        trading_sign_cmds,
        remote_publish_cmds,
        service_analytics_cmds,
        generated_cleanup_cmds,
        prepublish_contract_cmds,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Run daily Quant update, backtests, publish, and web snapshot pipeline.")
    ap.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"), help="YYYY-MM-DD. Default: today")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--core-db", default=str(PROJECT_ROOT / r"data\db\quant_service.db"))
    ap.add_argument("--detail-db", default=str(PROJECT_ROOT / r"data\db\quant_service_detail.db"))
    ap.add_argument("--core2-tag", default="")
    ap.add_argument("--s2-gsheet", action="store_true", help="Deprecated no-op. Google Sheets sync has been disabled.")
    ap.add_argument("--model-gsheet", action="store_true", help="Deprecated no-op. Google Sheets sync has been disabled.")
    ap.add_argument("--include-etf", action="store_true")
    ap.add_argument("--etf-start", default="2013-10-14", help="Deprecated no-op. ETF daily refresh now uses KRX OpenAPI asof-only collection.")
    ap.add_argument("--skip-prep", action="store_true", help="Skip universe/data refresh and feature prep steps")
    ap.add_argument(
        "--data-refresh-only",
        action="store_true",
        help="Run only data/universe/feature prep, then stop before strategy/AI model execution.",
    )
    ap.add_argument(
        "--model-run-only",
        action="store_true",
        help="Skip data refresh and run strategy/AI/publish stages after QM market context is ready.",
    )
    ap.add_argument(
        "--pipeline-mode",
        choices=["daily_light", "research_full"],
        default="daily_light",
        help=(
            "daily_light runs operational current payload updates only; research_full also runs "
            "AI retraining, E-series full rebuilds, backtests, and walk-forward validation jobs."
        ),
    )
    ap.add_argument(
        "--qm-market-context-dir",
        default=str(DEFAULT_QM_MARKET_CONTEXT_DIR),
        help="QuantMarket handoff current directory used for model-run readiness checks.",
    )
    ap.add_argument(
        "--allow-stale-qm-market-context",
        action="store_true",
        help="Allow model execution even when QM market context is not ready for the requested asof.",
    )
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument(
        "--include-service-analytics",
        action="store_true",
        help="Opt in to internal service analytics DB/review/admin preview bundle generation",
    )
    ap.add_argument(
        "--skip-service-analytics",
        action="store_true",
        help="Deprecated compatibility flag. Internal service analytics are now skipped by default.",
    )
    ap.add_argument("--skip-tseries-shadow", action="store_true", help="Skip T-STOCK-V01 / T-ETF-V01 shadow refresh outputs")
    ap.add_argument("--skip-iseries-shadow", action="store_true", help="Skip I-STOCK-STRONG-RSI-V01 shadow refresh outputs")
    ap.add_argument("--skip-ai-overlay", action="store_true", help="Skip AI overlay shadow scoring and performance tracking")
    ap.add_argument(
        "--include-ai-research",
        action="store_true",
        help="With --pipeline-mode research_full, also run optional research/ablation AI jobs excluded from daily operation.",
    )
    ap.add_argument("--skip-trading-sign", action="store_true", help="Skip trading_sign current snapshot generation and validation")
    ap.add_argument("--skip-remote-current-publish", action="store_true", help="Skip canonical GCS republish of current public snapshot files")
    ap.add_argument("--skip-generated-csv-db-sync", action="store_true", help="Skip syncing dated generated CSV outputs into generated_outputs.db")
    ap.add_argument("--skip-generated-file-cleanup", action="store_true", help="Skip conservative archive cleanup of dated generated files")
    ap.add_argument("--full-regime-rebuild", action="store_true", help="Use a 10-year regime refresh instead of the operational incremental window")
    ap.add_argument("--full-validation", action="store_true", help="Run full admin new-entry coverage validation instead of daily quick validation")
    ap.add_argument("--model-workers", type=int, default=4, help="Maximum parallel workers for independent model backtests")
    ap.add_argument("--profile-workers", type=int, default=3, help="Maximum parallel workers for stable/balanced/growth router and report chains")
    args = ap.parse_args()
    if args.data_refresh_only and args.model_run_only:
        raise SystemExit("--data-refresh-only and --model-run-only cannot be used together.")
    if args.model_run_only:
        args.skip_prep = True
    global PIPELINE_STATUS
    PIPELINE_STATUS = "running"
    _configure_timing_report(args.asof)

    core2_tag = args.core2_tag or f"daily_{args.asof.replace('-', '')}"
    prep_cmds, s2_cmd, model_cmds, router_and_reports_cmds, tseries_shadow_cmds, iseries_shadow_cmds, ingest_cmd, publish_cmd, web_snapshot_cmds, admin_new_entry_cmds, ai_overlay_cmds, trading_sign_cmds, remote_publish_cmds, service_analytics_cmds, generated_cleanup_cmds, prepublish_contract_cmds = build_commands(
        asof=args.asof,
        python_exe=str(args.python),
        core_db=str(args.core_db),
        detail_db=str(args.detail_db),
        core2_tag=core2_tag,
        include_etf=bool(args.include_etf),
        etf_start=str(args.etf_start),
        include_service_analytics=bool(args.include_service_analytics) and not bool(args.skip_service_analytics),
        include_tseries_shadow=not bool(args.skip_tseries_shadow),
        include_iseries_shadow=not bool(args.skip_iseries_shadow),
        include_ai_overlay=not bool(args.skip_ai_overlay),
        include_ai_research=bool(args.include_ai_research),
        include_remote_current_publish=not bool(args.skip_remote_current_publish),
        include_generated_cleanup=not bool(args.skip_generated_file_cleanup),
        full_regime_rebuild=bool(args.full_regime_rebuild),
        full_validation=bool(args.full_validation),
        pipeline_mode=str(args.pipeline_mode),
    )

    if args.s2_gsheet or args.model_gsheet:
        print("[WARN] Google Sheets integration has been disabled. Legacy gsheet flags are ignored.")

    print("[PIPELINE]")
    print(f"  asof={args.asof}")
    print(f"  include_etf={bool(args.include_etf)}")
    print(f"  etf_start={args.etf_start}")
    print(f"  prep={not bool(args.skip_prep)}")
    print(f"  data_refresh_only={bool(args.data_refresh_only)}")
    print(f"  model_run_only={bool(args.model_run_only)}")
    print(f"  pipeline_mode={args.pipeline_mode}")
    print(f"  qm_market_context_dir={args.qm_market_context_dir}")
    print(f"  allow_stale_qm_market_context={bool(args.allow_stale_qm_market_context)}")
    print("  gsheet_sync=False (disabled)")
    print(
        "  service_analytics="
        f"{bool(args.include_service_analytics) and not bool(args.skip_service_analytics)}"
    )
    print(f"  tseries_shadow={not bool(args.skip_tseries_shadow)}")
    print(f"  iseries_shadow={not bool(args.skip_iseries_shadow)}")
    print(f"  ai_overlay={not bool(args.skip_ai_overlay)}")
    print(f"  ai_research={bool(args.include_ai_research)}")
    print(f"  trading_sign={not bool(args.skip_trading_sign)}")
    print(f"  remote_current_publish={not bool(args.skip_remote_current_publish)}")
    print(f"  generated_csv_db_sync={not bool(args.skip_generated_csv_db_sync)}")
    print(f"  generated_file_cleanup={not bool(args.skip_generated_file_cleanup)}")
    print(f"  full_regime_rebuild={bool(args.full_regime_rebuild)}")
    print(f"  full_validation={bool(args.full_validation)}")
    print(f"  model_workers={int(args.model_workers)}")
    print(f"  profile_workers={int(args.profile_workers)}")

    if not args.skip_prep:
        for cmd in prep_cmds:
            _run(cmd, PROJECT_ROOT, "prep")
    else:
        print("[SKIP] prep commands skipped by --skip-prep")

    if args.data_refresh_only:
        PIPELINE_STATUS = "ok"
        print("[OK] data refresh stage completed; stopping before model execution by --data-refresh-only")
        return

    _check_qm_market_context(
        args.asof,
        Path(args.qm_market_context_dir),
        bool(args.allow_stale_qm_market_context),
    )

    _run_parallel([s2_cmd, *model_cmds], PROJECT_ROOT, "models", int(args.model_workers))

    _run_profile_sequences(router_and_reports_cmds, PROJECT_ROOT, int(args.profile_workers))

    for cmd in tseries_shadow_cmds:
        _run(cmd, PROJECT_ROOT, "tseries_shadow")

    for cmd in iseries_shadow_cmds:
        _run(cmd, PROJECT_ROOT, "iseries_shadow")

    _run(ingest_cmd, PROJECT_ROOT, "publish_ingest")
    if not args.skip_publish:
        _run(publish_cmd, PROJECT_ROOT, "publish_ingest")

    for cmd in web_snapshot_cmds:
        _run(cmd, PROJECT_ROOT, "web_snapshot")

    for cmd in admin_new_entry_cmds:
        _run(cmd, PROJECT_ROOT, "admin_tracker")

    for cmd in ai_overlay_cmds:
        _run(cmd, PROJECT_ROOT, "ai_overlay")

    if not args.skip_trading_sign:
        for cmd in trading_sign_cmds:
            _run(cmd, PROJECT_ROOT, "trading_sign")

    for cmd in prepublish_contract_cmds:
        _run(cmd, PROJECT_ROOT, "contract")

    for cmd in remote_publish_cmds:
        effective_cmd = list(cmd)
        if args.skip_trading_sign:
            effective_cmd.append("--skip-trading-sign-current")
        _run(effective_cmd, PROJECT_ROOT, "remote_publish")

    if not args.skip_generated_csv_db_sync:
        _run(
            [str(args.python), str(PROJECT_ROOT / r"scripts\sync_generated_csv_to_db.py"), "--asof", args.asof],
            PROJECT_ROOT,
            "generated_csv_db_sync",
        )

    for cmd in service_analytics_cmds:
        _run(cmd, PROJECT_ROOT, "service_analytics")

    for cmd in generated_cleanup_cmds:
        _run(cmd, PROJECT_ROOT, "generated_cleanup")

    PIPELINE_STATUS = "ok"
    print("[OK] daily quant pipeline completed")


if __name__ == "__main__":
    main()

