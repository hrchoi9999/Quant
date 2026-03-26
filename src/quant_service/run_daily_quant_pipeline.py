from __future__ import annotations

import argparse
from datetime import date
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Quant")


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _popen(cmd: list[str], cwd: Path) -> subprocess.Popen:
    print(f"[RUN] {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(cwd))


def build_commands(
    asof: str,
    python_exe: str,
    core_db: str,
    detail_db: str,
    core2_tag: str,
    s2_gsheet: bool,
    model_gsheet: bool,
    include_etf: bool,
    etf_start: str,
    include_service_analytics: bool,
) -> tuple[list[list[str]], list[str], list[list[str]], list[list[str]], list[str], list[str] | None, list[str] | None, list[list[str]], list[list[str]], list[list[str]]]:
    prep_cmds: list[list[str]] = [[
        python_exe,
        str(PROJECT_ROOT / r"src\pipelines\rebuild_mix_universe_and_refresh_dbs.py"),
        "--asof", asof,
        "--update-latest",
    ]]

    if include_etf:
        prep_cmds.extend([
            [python_exe, str(PROJECT_ROOT / r"src\collectors\universe\build_universe_etf_krx.py"), "--asof", asof, "--update-latest", "--upsert-instrument-master"],
            [python_exe, str(PROJECT_ROOT / r"src\collectors\prices\fetch_etf_prices_daily.py"), "--universe-csv", str(PROJECT_ROOT / r"data\universe\universe_etf_master_latest.csv"), "--start", etf_start, "--end", asof],
            [python_exe, str(PROJECT_ROOT / r"src\collectors\universe\build_universe_etf_core.py"), "--asof", asof],
        ])

    prep_cmds.extend([
        [python_exe, str(PROJECT_ROOT / r"src\features\build_s3_price_features_daily.py"), "--end", asof],
        [python_exe, str(PROJECT_ROOT / r"src\features\build_s3_fund_features_monthly.py"), "--mode", "rebuild"],
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
    if s2_gsheet:
        s2_cmd.extend([
            "--gsheet-enable", "--gsheet-cred", str(PROJECT_ROOT / r"config\quant-485814-0df3dc750a8d.json"),
            "--gsheet-id", "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs", "--gsheet-tab", "S2_snapshot",
            "--gsheet-mode", "overwrite", "--gsheet-ledger", "--gsheet-prefix", "S2",
        ])

    model_cmds = [
        [python_exe, str(PROJECT_ROOT / r"src\experiments\run_s3_trend_hold_top20.py"), "--asof", asof, "--start", "2013-10-14", "--end", asof, "--top-n", "20", "--min-holdings", "10", "--weekly-anchor-weekday", "2"],
        [python_exe, str(PROJECT_ROOT / r"src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py"), "--asof", asof, "--start", "2013-10-14", "--end", asof, "--top-n", "20", "--min-holdings", "10", "--tag", core2_tag, "--gate-enabled", "1", "--gate-open-th", "0.50", "--gate-close-th", "0.46", "--gate-use-slope", "1", "--gate-use-ma-stack", "1"],
        [python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_s4_risk_on_allocation.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M"],
        [python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_s5_neutral_allocation.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M"],
        [python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_s6_defensive_allocation.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M"],
    ]

    router_and_reports_cmds = []
    for profile in ["stable", "balanced", "growth", "auto"]:
        router_and_reports_cmds.append([python_exe, str(PROJECT_ROOT / r"src\backtest\run_backtest_multiasset_router.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M", "--service-profile", profile])
        router_and_reports_cmds.append([python_exe, str(PROJECT_ROOT / r"scripts\run_model_comparison.py"), "--asof", asof, "--start", "2023-06-08", "--end", asof, "--rebalance", "M", "--service-profile", profile])
        router_and_reports_cmds.append([python_exe, str(PROJECT_ROOT / r"src\reporting\render_redbot_user_report.py"), "--service-profile", profile, "--asof", asof])

    ingest_cmd = [python_exe, str(PROJECT_ROOT / r"src\quant_service\ingest_backtest_results.py"), "--asof", asof, "--core-db", core_db, "--detail-db", detail_db]
    publish_cmd = [python_exe, str(PROJECT_ROOT / r"src\quant_service\publish_backtest_results.py"), "--asof", asof, "--core-db", core_db, "--detail-db", detail_db]

    model_gsheet_cmd = None
    etf_model_gsheet_cmd = None
    if model_gsheet:
        model_gsheet_cmd = [python_exe, str(PROJECT_ROOT / r"src\quant_service\sync_model_holdings_gsheet.py"), "--asof", asof, "--core-db", core_db, "--detail-db", detail_db, "--gsheet-cred", str(PROJECT_ROOT / r"config\quant-485814-0df3dc750a8d.json"), "--gsheet-id", "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs", "--gsheet-mode", "overwrite"]
        etf_model_gsheet_cmd = [python_exe, str(PROJECT_ROOT / r"src\quant_service\sync_etf_model_holdings_gsheet.py"), "--asof", asof, "--report-dir", str(PROJECT_ROOT / r"reports\backtest_etf_allocation"), "--gsheet-cred", str(PROJECT_ROOT / r"config\quant-485814-0df3dc750a8d.json"), "--gsheet-id", "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs", "--gsheet-mode", "overwrite"]

    web_snapshot_cmds = [
        [python_exe, str(PROJECT_ROOT / r"service_platform\publishers\build_user_facing_snapshots.py"), "--asof", asof],
        [python_exe, str(PROJECT_ROOT / r"scripts\validate_redbot_web_snapshots.py"), "--asof", asof],
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

    return (
        prep_cmds,
        s2_cmd,
        model_cmds,
        router_and_reports_cmds,
        ingest_cmd,
        publish_cmd,
        model_gsheet_cmd,
        etf_model_gsheet_cmd,
        web_snapshot_cmds,
        service_analytics_cmds,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Run daily Quant update, backtests, publish, and web snapshot pipeline.")
    ap.add_argument("--asof", default=date.today().strftime("%Y-%m-%d"), help="YYYY-MM-DD. Default: today")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--core-db", default=str(PROJECT_ROOT / r"data\db\quant_service.db"))
    ap.add_argument("--detail-db", default=str(PROJECT_ROOT / r"data\db\quant_service_detail.db"))
    ap.add_argument("--core2-tag", default="")
    ap.add_argument("--s2-gsheet", action="store_true")
    ap.add_argument("--model-gsheet", action="store_true")
    ap.add_argument("--include-etf", action="store_true")
    ap.add_argument("--etf-start", default="2013-10-14")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--skip-service-analytics", action="store_true", help="Skip internal service analytics DB/review/bundle generation")
    args = ap.parse_args()

    core2_tag = args.core2_tag or f"daily_{args.asof.replace('-', '')}"
    prep_cmds, s2_cmd, model_cmds, router_and_reports_cmds, ingest_cmd, publish_cmd, model_gsheet_cmd, etf_model_gsheet_cmd, web_snapshot_cmds, service_analytics_cmds = build_commands(
        asof=args.asof,
        python_exe=str(args.python),
        core_db=str(args.core_db),
        detail_db=str(args.detail_db),
        core2_tag=core2_tag,
        s2_gsheet=bool(args.s2_gsheet),
        model_gsheet=bool(args.model_gsheet),
        include_etf=bool(args.include_etf),
        etf_start=str(args.etf_start),
        include_service_analytics=not bool(args.skip_service_analytics),
    )

    print("[PIPELINE]")
    print(f"  asof={args.asof}")
    print(f"  include_etf={bool(args.include_etf)}")
    print(f"  etf_start={args.etf_start}")
    print(f"  model_gsheet={bool(args.model_gsheet)}")
    print(f"  service_analytics={not bool(args.skip_service_analytics)}")

    for cmd in prep_cmds:
        _run(cmd, PROJECT_ROOT)

    _run(s2_cmd, PROJECT_ROOT)

    procs = [_popen(cmd, PROJECT_ROOT) for cmd in model_cmds]
    exit_codes = [p.wait() for p in procs]
    if any(rc != 0 for rc in exit_codes):
        raise SystemExit(f"Model jobs failed: {exit_codes}")

    for cmd in router_and_reports_cmds:
        _run(cmd, PROJECT_ROOT)

    _run(ingest_cmd, PROJECT_ROOT)
    if not args.skip_publish:
        _run(publish_cmd, PROJECT_ROOT)
        if model_gsheet_cmd is not None:
            _run(model_gsheet_cmd, PROJECT_ROOT)
        if etf_model_gsheet_cmd is not None:
            _run(etf_model_gsheet_cmd, PROJECT_ROOT)

    for cmd in web_snapshot_cmds:
        _run(cmd, PROJECT_ROOT)

    for cmd in service_analytics_cmds:
        _run(cmd, PROJECT_ROOT)

    print("[OK] daily quant pipeline completed")


if __name__ == "__main__":
    main()
