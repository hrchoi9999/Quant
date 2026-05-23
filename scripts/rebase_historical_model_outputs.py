from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")
PYTHON = PROJECT_ROOT / "venv64" / "Scripts" / "python.exe"

DEFAULT_DATES = [
    "2026-03-18",
    "2026-03-19",
    "2026-03-20",
    "2026-03-25",
    "2026-03-31",
    "2026-04-01",
    "2026-04-03",
    "2026-04-06",
    "2026-04-08",
    "2026-04-10",
    "2026-04-14",
]

DATE_SCOPES = [
    PROJECT_ROOT / "reports" / "backtest_router",
    PROJECT_ROOT / "reports" / "model_compare",
    PROJECT_ROOT / "reports" / "redbot_user_reports",
    PROJECT_ROOT / "reports" / "backtest_regime_refactor",
    PROJECT_ROOT / "reports" / "backtest_s3_dev",
    PROJECT_ROOT / "reports" / "backtest_etf_allocation",
    PROJECT_ROOT / "data" / "universe",
]


def ymd(date_text: str) -> str:
    return date_text.replace("-", "")


def run(cmd: list[str], *, dry_run: bool = False) -> None:
    print("[RUN]", " ".join(cmd), flush=True)
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)


def date_files(date_text: str, *, root: Path = PROJECT_ROOT) -> list[Path]:
    stamp = ymd(date_text)
    out: list[Path] = []
    for scope in DATE_SCOPES:
        base = root / scope.relative_to(PROJECT_ROOT)
        if not base.exists():
            continue
        out.extend(p for p in base.glob(f"*{stamp}*") if p.is_file())
    return sorted(out)


def backup_existing(dates: Iterable[str], backup_root: Path) -> int:
    copied = 0
    for date_text in dates:
        for src in date_files(date_text):
            rel = src.relative_to(PROJECT_ROOT)
            dst = backup_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                continue
            shutil.copy2(src, dst)
            copied += 1
    return copied


def first_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def pick_latest(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return sorted(existing, key=lambda p: (p.stat().st_mtime, str(p)))[-1]


def collect_metrics(root: Path, dates: Iterable[str], out_path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    report_root = root / "reports"
    for date_text in dates:
        stamp = ymd(date_text)

        s2_file = pick_latest(list((report_root / "backtest_regime_refactor").glob(f"regime_bt_summary_*_{stamp}.csv")))
        if s2_file:
            df = first_csv(s2_file)
            if not df.empty:
                row = df.iloc[0].to_dict()
                rows.append(metric_row(date_text, "internal", "S2", row, s2_file, root))

        for model in ["s4", "s5", "s6"]:
            files = list((report_root / "backtest_etf_allocation").glob(f"{model}_alloc_summary_{stamp}_*.csv"))
            summary_file = pick_latest(files)
            if summary_file:
                df = first_csv(summary_file)
                if not df.empty:
                    row = df.iloc[0].to_dict()
                    rows.append(metric_row(date_text, "internal", model.upper(), row, summary_file, root))

        for profile in ["stable", "balanced", "growth"]:
            router_file = pick_latest(list((report_root / "backtest_router").glob(f"router_summary_{stamp}_*_{profile}.csv")))
            if router_file:
                df = first_csv(router_file)
                if not df.empty:
                    row = df.iloc[0].to_dict()
                    rows.append(metric_row(date_text, "user", profile, row, router_file, root))

            compare_file = pick_latest(list((report_root / "model_compare").glob(f"model_compare_summary_{stamp}_*_{profile}.csv")))
            if compare_file:
                df = first_csv(compare_file)
                for _, r in df.iterrows():
                    model_name = str(r.get("model") or "")
                    if model_name:
                        rows.append(metric_row(date_text, f"model_compare:{profile}", model_name, r.to_dict(), compare_file, root))

    out = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out


def metric_row(date_text: str, scope: str, model: str, row: dict[str, object], src: Path, root: Path) -> dict[str, object]:
    return {
        "asof": date_text,
        "scope": scope,
        "model": model,
        "start": row.get("start"),
        "end": row.get("end"),
        "cagr": row.get("cagr"),
        "mdd": row.get("mdd"),
        "sharpe": row.get("sharpe"),
        "turnover": row.get("turnover"),
        "rebalance_count": row.get("rebalance_count"),
        "source_file": str(src.relative_to(root)),
    }


def collect_portfolios(root: Path, dates: Iterable[str], out_path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    base = root / "reports" / "redbot_user_reports"
    for date_text in dates:
        stamp = ymd(date_text)
        for profile in ["stable", "balanced", "growth"]:
            path = base / f"redbot_user_report_{profile}_{stamp}.json"
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for item in payload.get("model_portfolio") or []:
                rows.append(
                    {
                        "asof": date_text,
                        "profile": profile,
                        "ticker": str(item.get("security_code") or "").zfill(6),
                        "name": item.get("display_name"),
                        "asset_group": item.get("asset_group"),
                        "weight": item.get("target_weight"),
                    }
                )
    out = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out


def compare_metrics(before: pd.DataFrame, after: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    keys = ["asof", "scope", "model"]
    metrics = ["cagr", "mdd", "sharpe", "turnover", "rebalance_count"]
    if before.empty and after.empty:
        out = pd.DataFrame(columns=keys)
    else:
        left = before[keys + [m for m in metrics if m in before.columns]].copy() if not before.empty else pd.DataFrame(columns=keys + metrics)
        right = after[keys + [m for m in metrics if m in after.columns]].copy() if not after.empty else pd.DataFrame(columns=keys + metrics)
        merged = left.merge(right, on=keys, how="outer", suffixes=("_before", "_after"))
        for metric in metrics:
            b = pd.to_numeric(merged.get(f"{metric}_before"), errors="coerce")
            a = pd.to_numeric(merged.get(f"{metric}_after"), errors="coerce")
            merged[f"{metric}_delta"] = a - b
        out = merged.sort_values(keys)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out


def compare_portfolios(before: pd.DataFrame, after: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    keys = ["asof", "profile", "ticker"]
    if before.empty and after.empty:
        out = pd.DataFrame(columns=keys)
    else:
        b = before.copy()
        a = after.copy()
        b["before_present"] = True
        a["after_present"] = True
        merged = b.merge(a, on=keys, how="outer", suffixes=("_before", "_after"))
        merged["before_present"] = merged["before_present"].fillna(False)
        merged["after_present"] = merged["after_present"].fillna(False)
        merged["change_type"] = "unchanged"
        merged.loc[merged["before_present"] & ~merged["after_present"], "change_type"] = "removed"
        merged.loc[~merged["before_present"] & merged["after_present"], "change_type"] = "added"
        bw = pd.to_numeric(merged.get("weight_before"), errors="coerce")
        aw = pd.to_numeric(merged.get("weight_after"), errors="coerce")
        merged["weight_delta"] = aw - bw
        changed_weight = merged["before_present"] & merged["after_present"] & (merged["weight_delta"].abs() > 1e-9)
        merged.loc[changed_weight, "change_type"] = "weight_changed"
        out = merged.sort_values(["asof", "profile", "change_type", "ticker"])
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out


def write_summary(run_root: Path, metrics_diff: pd.DataFrame, portfolio_diff: pd.DataFrame) -> None:
    lines = [
        "# Historical Rebase Comparison",
        "",
        f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        f"- metrics_rows: {len(metrics_diff)}",
        f"- portfolio_diff_rows: {len(portfolio_diff)}",
        "",
        "## Metric Changes With Nonzero Delta",
        "",
    ]
    if metrics_diff.empty:
        lines.append("- No metric rows found.")
    else:
        numeric_cols = [c for c in metrics_diff.columns if c.endswith("_delta")]
        tmp = metrics_diff.copy()
        tmp["_abs_delta"] = tmp[numeric_cols].abs().sum(axis=1, skipna=True)
        changed = tmp[tmp["_abs_delta"] > 1e-12].sort_values("_abs_delta", ascending=False).head(30)
        if changed.empty:
            lines.append("- No metric deltas detected.")
        else:
            for _, row in changed.iterrows():
                lines.append(
                    f"- {row['asof']} {row['scope']} {row['model']}: "
                    f"cagr_delta={row.get('cagr_delta')}, sharpe_delta={row.get('sharpe_delta')}, mdd_delta={row.get('mdd_delta')}"
                )
    lines.extend(["", "## Portfolio Change Counts", ""])
    if portfolio_diff.empty:
        lines.append("- No portfolio rows found.")
    else:
        counts = portfolio_diff.groupby(["asof", "profile", "change_type"]).size().reset_index(name="count")
        for _, row in counts.iterrows():
            lines.append(f"- {row['asof']} {row['profile']} {row['change_type']}: {row['count']}")
    (run_root / "comparison_summary.md").write_text("\n".join(lines), encoding="utf-8")


def rebase_date(date_text: str, *, dry_run: bool) -> None:
    run(
        [
            str(PYTHON),
            str(PROJECT_ROOT / "src" / "pipelines" / "rebuild_mix_universe_and_refresh_dbs.py"),
            "--asof",
            date_text,
            "--krx-source",
            "cache",
            "--price-mode",
            "skip",
            "--update-latest",
        ],
        dry_run=dry_run,
    )
    run(
        [
            str(PYTHON),
            str(PROJECT_ROOT / "src" / "features" / "build_s3_price_features_full_backfill.py"),
            "--start",
            "2017-02-08",
            "--end",
            date_text,
        ],
        dry_run=dry_run,
    )
    run(
        [str(PYTHON), str(PROJECT_ROOT / "src" / "features" / "build_s3_fund_features_monthly.py"), "--mode", "rebuild"],
        dry_run=dry_run,
    )
    ensure_etf_core_snapshot(date_text, dry_run=dry_run)
    run(
        [
            str(PYTHON),
            str(PROJECT_ROOT / "src" / "quant_service" / "run_daily_quant_pipeline.py"),
            "--asof",
            date_text,
            "--include-etf",
            "--skip-prep",
            "--skip-remote-current-publish",
            "--skip-generated-file-cleanup",
        ],
        dry_run=dry_run,
    )


def ensure_etf_core_snapshot(date_text: str, *, dry_run: bool) -> None:
    target = PROJECT_ROOT / "data" / "universe" / f"universe_etf_core_{ymd(date_text)}.csv"
    if target.exists():
        return
    candidates: list[tuple[str, Path]] = []
    for path in (PROJECT_ROOT / "data" / "universe").glob("universe_etf_core_*.csv"):
        stamp = path.stem.rsplit("_", 1)[-1]
        if stamp.isdigit() and stamp <= ymd(date_text):
            candidates.append((stamp, path))
    if not candidates:
        raise FileNotFoundError(f"no prior ETF core snapshot available for {date_text}: {target}")
    source = sorted(candidates, key=lambda item: item[0])[-1][1]
    print(f"[ALIAS] ETF core {source.name} -> {target.name}", flush=True)
    if dry_run:
        return
    shutil.copy2(source, target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild historical model output dates with current KRX-corrected price DB and compare old vs new artifacts.")
    parser.add_argument("--dates", default=",".join(DEFAULT_DATES), help="Comma-separated YYYY-MM-DD dates")
    parser.add_argument("--restore-current-asof", default="2026-04-16")
    parser.add_argument("--out-root", default=str(PROJECT_ROOT / "reports" / "historical_rebase"))
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-run", action="store_true", help="Only backup/compare current files without rebuilding")
    args = parser.parse_args()

    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    run_root = Path(args.out_root) / args.run_id
    before_root = run_root / "before"
    after_root = PROJECT_ROOT
    run_root.mkdir(parents=True, exist_ok=True)

    copied = backup_existing(dates + [args.restore_current_asof], before_root)
    print(f"[OK] backup copied files={copied} -> {before_root}")

    before_metrics = collect_metrics(before_root, dates, run_root / "before_metrics.csv")
    before_portfolios = collect_portfolios(before_root, dates, run_root / "before_portfolios.csv")
    print(f"[OK] before metrics={len(before_metrics)} portfolios={len(before_portfolios)}")

    if not args.skip_run:
        for date_text in dates:
            print(f"\n[REBASE] {date_text}")
            rebase_date(date_text, dry_run=args.dry_run)
        if args.restore_current_asof:
            print(f"\n[RESTORE CURRENT] {args.restore_current_asof}")
            rebase_date(args.restore_current_asof, dry_run=args.dry_run)
            run(
                [str(PYTHON), str(PROJECT_ROOT / "scripts" / "publish_public_current_to_gcs.py")],
                dry_run=args.dry_run,
            )

    after_metrics = collect_metrics(after_root, dates, run_root / "after_metrics.csv")
    after_portfolios = collect_portfolios(after_root, dates, run_root / "after_portfolios.csv")
    metrics_diff = compare_metrics(before_metrics, after_metrics, run_root / "metrics_diff.csv")
    portfolio_diff = compare_portfolios(before_portfolios, after_portfolios, run_root / "portfolio_diff.csv")
    write_summary(run_root, metrics_diff, portfolio_diff)

    print(json.dumps({
        "run_root": str(run_root),
        "dates": dates,
        "backup_files": copied,
        "before_metric_rows": len(before_metrics),
        "after_metric_rows": len(after_metrics),
        "metric_diff_rows": len(metrics_diff),
        "before_portfolio_rows": len(before_portfolios),
        "after_portfolio_rows": len(after_portfolios),
        "portfolio_diff_rows": len(portfolio_diff),
        "summary": str(run_root / "comparison_summary.md"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
