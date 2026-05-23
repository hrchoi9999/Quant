from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
INPUT_DIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger_backtest_historical_mcap"
OUTDIR = INPUT_DIR
WINDOW_START = pd.Timestamp("2025-04-24")
WINDOW_END = pd.Timestamp("2026-04-23")
MODEL_CODE = "S3_CORE2"
BASELINE = "S3_CORE2_baseline"
CHALLENGER = "S3_CORE2_challenger_overheat_reject"


def load_csv(name: str, **kwargs) -> pd.DataFrame:
    path = INPUT_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, **kwargs)
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    if "added_tickers" in df.columns:
        df["added_tickers"] = df["added_tickers"].astype(str)
    if "dropped_tickers" in df.columns:
        df["dropped_tickers"] = df["dropped_tickers"].astype(str)
    return df


def compute_window_perf(nav: pd.DataFrame) -> dict[str, float | str]:
    nav = nav.sort_values("date").copy()
    nav = nav[(nav["date"] >= WINDOW_START) & (nav["date"] <= WINDOW_END)].copy()
    if len(nav) < 2:
        return {}
    start_nav = float(nav["nav"].iloc[0])
    end_nav = float(nav["nav"].iloc[-1])
    total_return = end_nav / start_nav - 1.0
    years = max((nav["date"].iloc[-1] - nav["date"].iloc[0]).days / 365.25, 1 / 252)
    cagr = (end_nav / start_nav) ** (1.0 / years) - 1.0 if start_nav > 0 else np.nan
    dd = nav["nav"] / nav["nav"].cummax() - 1.0
    rets = nav["nav"].pct_change().dropna()
    vol = float(rets.std() * np.sqrt(252)) if len(rets) > 1 else np.nan
    sharpe = float((rets.mean() / rets.std()) * np.sqrt(252)) if len(rets) > 1 and rets.std() > 0 else np.nan
    return {
        "start_date": nav["date"].iloc[0].date().isoformat(),
        "end_date": nav["date"].iloc[-1].date().isoformat(),
        "total_return": total_return,
        "cagr": cagr,
        "mdd": float(dd.min()),
        "annual_vol": vol,
        "sharpe": sharpe,
    }


def build_overlap_table(holdings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    subset = holdings[
        (holdings["model_code"] == MODEL_CODE)
        & (holdings["variant"].isin([BASELINE, CHALLENGER]))
        & (holdings["date"] >= WINDOW_START)
        & (holdings["date"] <= WINDOW_END)
    ].copy()
    for dt, grp in subset.groupby("date", sort=True):
        base = set(grp.loc[grp["variant"] == BASELINE, "ticker"])
        chal = set(grp.loc[grp["variant"] == CHALLENGER, "ticker"])
        union = base | chal
        inter = base & chal
        rows.append(
            {
                "date": pd.Timestamp(dt),
                "baseline_count": len(base),
                "challenger_count": len(chal),
                "overlap_count": len(inter),
                "overlap_ratio": len(inter) / max(len(union), 1),
                "baseline_only": ",".join(sorted(base - chal)),
                "challenger_only": ",".join(sorted(chal - base)),
            }
        )
    return pd.DataFrame(rows)


def to_markdown(summary: pd.DataFrame, turnover: pd.DataFrame, quality: pd.DataFrame, overlap: pd.DataFrame, changes: pd.DataFrame) -> str:
    lines = [
        "# S3_CORE2 Recent 1Y Shadow Comparison",
        "",
        f"- window: {WINDOW_START.date().isoformat()} to {WINDOW_END.date().isoformat()}",
        "- source: historical-mcap challenger backtest replay",
        "",
        "## Performance",
        "| Variant | Total Return | CAGR | MDD | Annual Vol | Sharpe |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        vol_txt = "-" if pd.isna(row.annual_vol) else f"{row.annual_vol:.2%}"
        shp_txt = "-" if pd.isna(row.sharpe) else f"{row.sharpe:.2f}"
        lines.append(
            f"| {row.variant} | {row.total_return:.2%} | {row.cagr:.2%} | {row.mdd:.2%} | {vol_txt} | {shp_txt} |"
        )
    lines.append("")

    if not turnover.empty:
        lines.extend(
            [
                "## Turnover",
                "| Variant | Avg Add | Avg Drop | Avg Turnover | Median Turnover | Max Turnover |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in turnover.itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.avg_add_count:.2f} | {row.avg_drop_count:.2f} | {row.avg_turnover_ratio:.2%} | "
                f"{row.median_turnover_ratio:.2%} | {row.max_turnover_ratio:.2%} |"
            )
        lines.append("")

    if not quality.empty:
        lines.extend(
            [
                "## New Entry Quality",
                "| Variant | Horizon | Entries | Avg Forward Return | Median Forward Return | Winner Rate |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in quality.itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.horizon} | {row.n_entries} | {row.avg_forward_return:.2%} | {row.median_forward_return:.2%} | {row.winner_rate:.2%} |"
            )
        lines.append("")

    if not overlap.empty:
        avg_overlap = overlap["overlap_ratio"].mean()
        min_overlap = overlap["overlap_ratio"].min()
        lines.extend(
            [
                "## Baseline vs Challenger Overlap",
                f"- average overlap ratio: {avg_overlap:.2%}",
                f"- minimum overlap ratio: {min_overlap:.2%}",
                "",
                "### Lowest Overlap Dates",
                "| Date | Overlap Ratio | Overlap Count | Baseline Count | Challenger Count |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in overlap.sort_values(["overlap_ratio", "date"]).head(10).itertuples(index=False):
            lines.append(
                f"| {row.date.date().isoformat()} | {row.overlap_ratio:.2%} | {row.overlap_count} | {row.baseline_count} | {row.challenger_count} |"
            )
        lines.append("")

    if not changes.empty:
        lines.extend(
            [
                "## Recent Replacements",
                "| Date | Change Type | Ticker | Score |",
                "|---|---|---|---:|",
            ]
        )
        for row in changes.sort_values(["date", "change_type", "ticker"]).tail(20).itertuples(index=False):
            score_txt = "-" if pd.isna(row.score) else f"{row.score:.6f}"
            lines.append(f"| {row.date.date().isoformat()} | {row.change_type} | {str(row.ticker).zfill(6)} | {score_txt} |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    nav = load_csv("s_series_challenger_nav_history.csv", parse_dates=["date"])
    turnover_detail = load_csv("s_series_challenger_turnover_detail.csv", parse_dates=["date"])
    entry_detail = load_csv("s_series_challenger_new_entry_detail.csv", parse_dates=["entry_date", "end_date"])
    holdings = load_csv("s_series_challenger_holdings_history.csv", parse_dates=["date"])
    changes = load_csv("s_series_challenger_holdings_changes.csv", parse_dates=["date"])

    summary_rows = []
    for variant in [BASELINE, CHALLENGER]:
        stats = compute_window_perf(nav[(nav["model_code"] == MODEL_CODE) & (nav["variant"] == variant)])
        if stats:
            stats["variant"] = variant
            summary_rows.append(stats)
    summary = pd.DataFrame(summary_rows)

    turnover = (
        turnover_detail[
            (turnover_detail["model_code"] == MODEL_CODE)
            & (turnover_detail["variant"].isin([BASELINE, CHALLENGER]))
            & (turnover_detail["date"] >= WINDOW_START)
            & (turnover_detail["date"] <= WINDOW_END)
        ]
        .groupby("variant", dropna=False)
        .agg(
            avg_add_count=("n_add", "mean"),
            avg_drop_count=("n_drop", "mean"),
            avg_turnover_ratio=("turnover_ratio", "mean"),
            median_turnover_ratio=("turnover_ratio", "median"),
            max_turnover_ratio=("turnover_ratio", "max"),
        )
        .reset_index()
    )

    quality = (
        entry_detail[
            (entry_detail["model_code"] == MODEL_CODE)
            & (entry_detail["variant"].isin([BASELINE, CHALLENGER]))
            & (entry_detail["entry_date"] >= WINDOW_START)
            & (entry_detail["entry_date"] <= WINDOW_END)
        ]
        .groupby(["variant", "horizon"], dropna=False)
        .agg(
            n_entries=("ticker", "size"),
            avg_forward_return=("forward_return", "mean"),
            median_forward_return=("forward_return", "median"),
            winner_rate=("forward_return", lambda s: float((s > 0).mean())),
        )
        .reset_index()
    )

    overlap = build_overlap_table(holdings)
    recent_changes = changes[
        (changes["model_code"] == MODEL_CODE)
        & (changes["variant"] == CHALLENGER)
        & (changes["date"] >= WINDOW_START)
        & (changes["date"] <= WINDOW_END)
    ].copy()

    summary.to_csv(OUTDIR / "s3_core2_recent1y_shadow_summary.csv", index=False, encoding="utf-8-sig")
    turnover.to_csv(OUTDIR / "s3_core2_recent1y_shadow_turnover.csv", index=False, encoding="utf-8-sig")
    quality.to_csv(OUTDIR / "s3_core2_recent1y_shadow_new_entry_quality.csv", index=False, encoding="utf-8-sig")
    overlap.to_csv(OUTDIR / "s3_core2_recent1y_shadow_overlap.csv", index=False, encoding="utf-8-sig")
    recent_changes.to_csv(OUTDIR / "s3_core2_recent1y_shadow_changes.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s3_core2_recent1y_shadow_compare.md").write_text(
        to_markdown(summary, turnover, quality, overlap, recent_changes),
        encoding="utf-8",
    )
    print(f"[OK] wrote {OUTDIR}")


if __name__ == "__main__":
    main()
