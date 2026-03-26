from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\Quant")
ANALYTICS_DB = ROOT / "data" / "db" / "service_analytics.db"
REPORT_ROOT = ROOT / "reports" / "service_analytics_review"


def _read(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def _latest_per_model(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    latest = work.groupby("model_code", as_index=False)[date_col].max()
    return work.merge(latest, on=["model_code", date_col], how="inner")


def _fmt_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}"


def build_review(asof: str) -> dict[str, Path]:
    stamp = asof.replace("-", "")
    outdir = REPORT_ROOT / stamp
    outdir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(ANALYTICS_DB)
    try:
        overview = _read(conn, "analytics_model_run_overview")
        weekly = _read(conn, "analytics_model_weekly_snapshot")
        asset_mix = _read(conn, "analytics_model_asset_mix_weekly")
        asset_detail = _read(conn, "analytics_model_asset_detail_weekly")
        changes = _read(conn, "analytics_model_change_log")
        change_activity = _read(conn, "analytics_model_change_activity_weekly")
        lifecycle = _read(conn, "analytics_holding_lifecycle")
        change_impact = _read(conn, "analytics_model_change_impact_weekly")
        quality = _read(conn, "analytics_model_quality_weekly")
        quality_checks = _read(conn, "analytics_data_quality_checks")
    finally:
        conn.close()

    latest_weekly = _latest_per_model(weekly, "week_end")[["model_code", "week_end", "nav", "drawdown_current", "holdings_count", "cash_weight", "return_1w"]].copy()
    latest_asset_mix = _latest_per_model(asset_mix, "week_end")[["model_code", "week_end", "stock_weight", "etf_weight", "cash_weight", "other_weight", "gross_weight_check"]].copy()
    latest_asset_detail = _latest_per_model(asset_detail, "week_end")[["model_code", "week_end", "detail_bucket", "bucket_weight"]].copy()
    latest_quality = _latest_per_model(quality, "week_end")[["model_code", "week_end", "return_4w", "return_12w", "return_52w", "drawdown_current", "relative_strength_vs_benchmark_4w", "relative_strength_vs_benchmark_12w", "relative_strength_vs_benchmark_52w", "cash_weight_avg_4w", "holdings_count_avg_4w", "turnover_1w", "turnover_avg_4w", "top1_weight", "top3_weight", "top5_weight", "holdings_hhi"]].copy()
    latest_change_activity = _latest_per_model(change_activity, "week_end")[["model_code", "week_end", "new_count", "exit_count", "increase_count", "decrease_count", "event_count_total", "abs_delta_sum", "change_intensity_score"]].copy()

    changes["week_end"] = pd.to_datetime(changes["week_end"], errors="coerce")
    recent_cut = changes["week_end"].max() - pd.Timedelta(days=56)
    recent_changes = changes.loc[changes["week_end"] >= recent_cut].copy()
    recent_change_summary = (
        recent_changes.groupby(["model_code", "change_type"], as_index=False)
        .size()
        .pivot(index="model_code", columns="change_type", values="size")
        .fillna(0)
        .reset_index()
    )
    for col in ["new", "exit", "increase", "decrease"]:
        if col not in recent_change_summary.columns:
            recent_change_summary[col] = 0
    recent_change_detail = recent_changes.sort_values(["model_code", "week_end", "change_type", "delta_weight"], ascending=[True, False, True, False]).copy()

    change_impact["event_week_end"] = pd.to_datetime(change_impact["event_week_end"], errors="coerce")
    recent_change_impact = change_impact.loc[change_impact["event_week_end"] >= recent_cut].sort_values(["model_code", "event_week_end", "event_type"], ascending=[True, False, True]).copy()

    lifecycle_ranked = lifecycle.sort_values(["model_code", "holding_days_observed", "latest_weight"], ascending=[True, False, False]).copy()
    longest_holdings = lifecycle_ranked.groupby("model_code", as_index=False).head(15)

    overview_csv = outdir / f"model_run_overview_{stamp}.csv"
    latest_weekly_csv = outdir / f"latest_weekly_snapshot_{stamp}.csv"
    latest_asset_mix_csv = outdir / f"latest_asset_mix_{stamp}.csv"
    latest_asset_detail_csv = outdir / f"latest_asset_detail_{stamp}.csv"
    recent_change_summary_csv = outdir / f"recent_change_summary_{stamp}.csv"
    latest_change_activity_csv = outdir / f"latest_change_activity_{stamp}.csv"
    recent_change_detail_csv = outdir / f"recent_change_detail_8w_{stamp}.csv"
    recent_change_impact_csv = outdir / f"recent_change_impact_8w_{stamp}.csv"
    longest_holdings_csv = outdir / f"longest_holdings_{stamp}.csv"
    latest_quality_csv = outdir / f"latest_quality_metrics_{stamp}.csv"
    quality_checks_csv = outdir / f"data_quality_checks_{stamp}.csv"
    report_md = outdir / f"service_analytics_review_{stamp}.md"

    overview.to_csv(overview_csv, index=False, encoding="utf-8-sig")
    latest_weekly.to_csv(latest_weekly_csv, index=False, encoding="utf-8-sig")
    latest_asset_mix.to_csv(latest_asset_mix_csv, index=False, encoding="utf-8-sig")
    latest_asset_detail.to_csv(latest_asset_detail_csv, index=False, encoding="utf-8-sig")
    recent_change_summary.to_csv(recent_change_summary_csv, index=False, encoding="utf-8-sig")
    latest_change_activity.to_csv(latest_change_activity_csv, index=False, encoding="utf-8-sig")
    recent_change_detail.to_csv(recent_change_detail_csv, index=False, encoding="utf-8-sig")
    recent_change_impact.to_csv(recent_change_impact_csv, index=False, encoding="utf-8-sig")
    longest_holdings.to_csv(longest_holdings_csv, index=False, encoding="utf-8-sig")
    latest_quality.to_csv(latest_quality_csv, index=False, encoding="utf-8-sig")
    quality_checks.to_csv(quality_checks_csv, index=False, encoding="utf-8-sig")

    merged = overview[["model_code", "display_name", "start_date", "end_date", "cagr", "mdd", "sharpe", "history_days"]].merge(
        latest_asset_mix[["model_code", "stock_weight", "etf_weight", "cash_weight"]], on="model_code", how="left"
    ).merge(
        latest_quality[["model_code", "return_4w", "return_12w", "relative_strength_vs_benchmark_4w", "turnover_avg_4w", "top5_weight"]], on="model_code", how="left"
    ).merge(
        latest_change_activity[["model_code", "change_intensity_score"]], on="model_code", how="left"
    ).merge(
        recent_change_summary[["model_code", "new", "exit", "increase", "decrease"]], on="model_code", how="left"
    )

    lines = [
        f"# Service Analytics Review ({asof})",
        "",
        "웹서비스 미반영 상태의 내부 검토용 리포트입니다.",
        "",
        "## Model Snapshot",
        "",
        "| Model | CAGR | MDD | Sharpe | 4W | 12W | RS(4W) | Turnover(4W avg) | Top5 | Change Intensity | Stock | ETF | Cash | New(8W) | Exit(8W) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in merged.sort_values("model_code").iterrows():
        lines.append(
            f"| {row['model_code']} | {_fmt_pct(row['cagr'])} | {_fmt_pct(row['mdd'])} | {_fmt_num(row['sharpe'])} | {_fmt_pct(row['return_4w'])} | {_fmt_pct(row['return_12w'])} | {_fmt_pct(row['relative_strength_vs_benchmark_4w'])} | {_fmt_pct(row['turnover_avg_4w'])} | {_fmt_pct(row['top5_weight'])} | {_fmt_num(row['change_intensity_score'])} | {_fmt_pct(row['stock_weight'])} | {_fmt_pct(row['etf_weight'])} | {_fmt_pct(row['cash_weight'])} | {int(row['new']) if pd.notna(row['new']) else 0} | {int(row['exit']) if pd.notna(row['exit']) else 0} |"
        )

    lines.extend(["", "## Output Files", ""])
    for path in [overview_csv, latest_weekly_csv, latest_asset_mix_csv, latest_asset_detail_csv, recent_change_summary_csv, latest_change_activity_csv, recent_change_detail_csv, recent_change_impact_csv, longest_holdings_csv, latest_quality_csv, quality_checks_csv]:
        lines.append(f"- {path}")

    report_md.write_text("\n".join(lines), encoding="utf-8")

    return {
        "outdir": outdir,
        "report_md": report_md,
        "overview_csv": overview_csv,
        "latest_weekly_csv": latest_weekly_csv,
        "latest_asset_mix_csv": latest_asset_mix_csv,
        "latest_asset_detail_csv": latest_asset_detail_csv,
        "recent_change_summary_csv": recent_change_summary_csv,
        "latest_change_activity_csv": latest_change_activity_csv,
        "recent_change_detail_csv": recent_change_detail_csv,
        "recent_change_impact_csv": recent_change_impact_csv,
        "longest_holdings_csv": longest_holdings_csv,
        "latest_quality_csv": latest_quality_csv,
        "quality_checks_csv": quality_checks_csv,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build internal review reports from service analytics DB")
    parser.add_argument("--asof", default="2026-03-25")
    args = parser.parse_args()

    outputs = build_review(args.asof)
    for key, path in outputs.items():
        print(f"{key}={path}")


if __name__ == "__main__":
    main()
