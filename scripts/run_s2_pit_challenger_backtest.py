from __future__ import annotations

import argparse
import sqlite3
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")
PYTHON_EXE = PROJECT_ROOT / r"venv64\Scripts\python.exe"
BACKTEST_SCRIPT = PROJECT_ROOT / r"src\backtest\run_backtest_s2_v5.py"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
REGIME_DB = PROJECT_ROOT / r"data\db\regime.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s2_pit_challenger_backtest"
FORWARD_WINDOWS = {"1M": 21, "3M": 63}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-31")
    ap.add_argument("--end", default="2026-04-23")
    ap.add_argument("--tag", default="")
    return ap.parse_args()


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def build_backtest_cmd(view_name: str, outdir: Path, start: str, end: str) -> list[str]:
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
        view_name,
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
        "--no-snapshot",
        "--outdir",
        str(outdir),
    ]


def newest_file(folder: Path, pattern: str) -> Path:
    matches = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"no files matched {pattern} in {folder}")
    return matches[0]


def run_variant(label: str, view_name: str, start: str, end: str, outroot: Path) -> dict[str, object]:
    variant_dir = outroot / label
    variant_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_backtest_cmd(view_name, variant_dir, start, end)
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True)
    equity_path = newest_file(variant_dir, "regime_bt_equity_*.csv")
    summary_path = newest_file(variant_dir, "regime_bt_summary_*.csv")
    holdings_path = newest_file(variant_dir, "regime_bt_holdings_*.csv")
    equity = pd.read_csv(equity_path, parse_dates=["date"])
    summary = pd.read_csv(summary_path)
    holdings = pd.read_csv(holdings_path, parse_dates=["rebalance_date"])
    holdings["ticker"] = holdings["ticker"].astype(str).str.zfill(6)
    holdings["weight"] = pd.to_numeric(holdings["weight"], errors="coerce").fillna(0.0)
    return {
        "label": label,
        "view_name": view_name,
        "cmd": cmd,
        "stdout_tail": "\n".join(result.stdout.strip().splitlines()[-25:]),
        "equity_path": equity_path,
        "summary_path": summary_path,
        "holdings_path": holdings_path,
        "equity": equity,
        "summary": summary,
        "holdings": holdings,
    }


def calc_cagr(nav: pd.Series, dates: pd.Series) -> float:
    if len(nav) < 2:
        return np.nan
    years = max((dates.iloc[-1] - dates.iloc[0]).days / 365.25, 1 / 252)
    start_val = float(nav.iloc[0])
    end_val = float(nav.iloc[-1])
    if start_val <= 0 or end_val <= 0:
        return np.nan
    return end_val ** (1.0 / years) - 1.0


def perf_windows(equity: pd.DataFrame, variant: str) -> pd.DataFrame:
    df = equity.copy().sort_values("date")
    df["ret"] = pd.to_numeric(df["equity"], errors="coerce").pct_change()
    windows = {
        "full_history": df["date"].min(),
        "since_2025": pd.Timestamp("2025-01-01"),
        "since_2026": pd.Timestamp("2026-01-01"),
    }
    rows: list[dict[str, object]] = []
    for period, start_date in windows.items():
        sub = df[df["date"] >= start_date].copy()
        if len(sub) < 2:
            continue
        nav = pd.to_numeric(sub["equity"], errors="coerce")
        total_return = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
        mdd = float((nav / nav.cummax() - 1.0).min())
        vol = float(sub["ret"].std(ddof=1) * np.sqrt(252)) if sub["ret"].notna().sum() > 1 else np.nan
        sharpe = (
            float((sub["ret"].mean() / sub["ret"].std(ddof=1)) * np.sqrt(252))
            if sub["ret"].notna().sum() > 1 and float(sub["ret"].std(ddof=1)) > 0
            else np.nan
        )
        rows.append(
            {
                "variant": variant,
                "period": period,
                "start_date": sub["date"].iloc[0],
                "end_date": sub["date"].iloc[-1],
                "total_return": total_return,
                "cagr": calc_cagr(nav, sub["date"]),
                "mdd": mdd,
                "annual_vol": vol,
                "sharpe": sharpe,
            }
        )
    return pd.DataFrame(rows)


def turnover_summary(holdings: pd.DataFrame, variant: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows: list[dict[str, object]] = []
    prev: set[str] | None = None
    for dt, snap in holdings.groupby("rebalance_date", sort=True):
        curr = set(snap["ticker"].astype(str).tolist())
        if prev is None:
            prev = curr
            continue
        adds = sorted(curr - prev)
        drops = sorted(prev - curr)
        detail_rows.append(
            {
                "variant": variant,
                "date": pd.Timestamp(dt),
                "prev_count": len(prev),
                "curr_count": len(curr),
                "n_add": len(adds),
                "n_drop": len(drops),
                "turnover_ratio": len(adds) / max(len(curr), 1),
                "added_tickers": ",".join(adds),
                "dropped_tickers": ",".join(drops),
            }
        )
        prev = curr
    detail = pd.DataFrame(detail_rows)
    if detail.empty:
        return detail, pd.DataFrame()
    summary = (
        detail.groupby("variant", dropna=False)
        .agg(
            rebalance_steps=("date", "count"),
            avg_add_count=("n_add", "mean"),
            avg_drop_count=("n_drop", "mean"),
            avg_turnover_ratio=("turnover_ratio", "mean"),
            median_turnover_ratio=("turnover_ratio", "median"),
            max_turnover_ratio=("turnover_ratio", "max"),
        )
        .reset_index()
    )
    return detail, summary


def load_price_wide() -> tuple[pd.DataFrame, dict[str, dict[pd.Timestamp, pd.Timestamp]]]:
    px = read_sql(
        PRICE_DB,
        "SELECT ticker, date, close FROM prices_daily WHERE close IS NOT NULL",
        parse_dates=["date"],
    )
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    wide = px.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
    dates = [pd.Timestamp(d) for d in wide.index]
    end_maps = {
        label: {dates[i]: dates[i + step] for i in range(len(dates) - step)}
        for label, step in FORWARD_WINDOWS.items()
    }
    return wide, end_maps


def load_universe_tickers() -> set[str]:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    return set(df["ticker"].astype(str).str.zfill(6).tolist())


def new_entry_quality(holdings: pd.DataFrame, price_wide: pd.DataFrame, end_maps: dict[str, dict[pd.Timestamp, pd.Timestamp]], variant: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows: list[dict[str, object]] = []
    prev: set[str] | None = None
    for dt, snap in holdings.groupby("rebalance_date", sort=True):
        curr = set(snap["ticker"].astype(str).tolist())
        if prev is None:
            prev = curr
            continue
        entries = sorted(curr - prev)
        for ticker in entries:
            if ticker not in price_wide.columns or dt not in price_wide.index:
                continue
            entry_close = price_wide.at[dt, ticker]
            if pd.isna(entry_close):
                continue
            for horizon, mapping in end_maps.items():
                end_date = mapping.get(pd.Timestamp(dt))
                if end_date is None or end_date not in price_wide.index:
                    continue
                end_close = price_wide.at[end_date, ticker]
                if pd.isna(end_close):
                    continue
                detail_rows.append(
                    {
                        "variant": variant,
                        "entry_date": pd.Timestamp(dt),
                        "ticker": ticker,
                        "horizon": horizon,
                        "end_date": end_date,
                        "forward_return": float(end_close / entry_close - 1.0),
                    }
                )
        prev = curr
    detail = pd.DataFrame(detail_rows)
    if detail.empty:
        return detail, pd.DataFrame()
    summary = (
        detail.groupby(["variant", "horizon"], dropna=False)
        .agg(
            n_entries=("ticker", "size"),
            avg_forward_return=("forward_return", "mean"),
            median_forward_return=("forward_return", "median"),
            winner_rate=("forward_return", lambda s: float((s > 0).mean())),
            loser_rate=("forward_return", lambda s: float((s <= 0).mean())),
        )
        .reset_index()
    )
    return detail, summary


def load_valid_counts(universe_tickers: set[str]) -> pd.DataFrame:
    base = read_sql(
        FUND_DB,
        """
        SELECT date, ticker, valid_fund
        FROM s2_fund_scores_monthly
        """,
        parse_dates=["date"],
    )
    base["ticker"] = base["ticker"].astype(str).str.zfill(6)
    base = base[(base["valid_fund"] == 1) & (base["ticker"].isin(universe_tickers))].copy()
    base = base.groupby("date", as_index=False).agg(baseline_valid_count=("ticker", "count"))
    pit = read_sql(
        FUND_DB,
        """
        SELECT date, ticker, valid_fund, coverage_score
        FROM s2_fund_scores_pit_monthly
        """,
        parse_dates=["date"],
    )
    pit["ticker"] = pit["ticker"].astype(str).str.zfill(6)
    pit = pit[(pit["valid_fund"] == 1) & (pit["ticker"].isin(universe_tickers))].copy()
    pit = pit.groupby("date", as_index=False).agg(
        pit_valid_count=("ticker", "count"),
        pit_avg_coverage_score=("coverage_score", "mean"),
    )
    all_cov = read_sql(
        FUND_DB,
        """
        SELECT date, ticker, coverage_score
        FROM fundamentals_pit_qh_mix400_latest
        """,
        parse_dates=["date"],
    )
    all_cov["ticker"] = all_cov["ticker"].astype(str).str.zfill(6)
    all_cov = all_cov[all_cov["ticker"].isin(universe_tickers)].copy()
    all_cov = all_cov.groupby("date", as_index=False).agg(
        pit_total_rows=("ticker", "count"),
        pit_all_avg_coverage_score=("coverage_score", "mean"),
    )
    merged = base.merge(pit, on="date", how="outer").merge(all_cov, on="date", how="outer").sort_values("date")
    merged["baseline_valid_count"] = pd.to_numeric(merged["baseline_valid_count"], errors="coerce")
    merged["pit_valid_count"] = pd.to_numeric(merged["pit_valid_count"], errors="coerce")
    merged["pit_valid_ratio_vs_baseline"] = merged["pit_valid_count"] / merged["baseline_valid_count"]
    return merged


def build_headline(perf: pd.DataFrame, turnover: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for variant in ["S2_baseline", "S2_pit_challenger"]:
        perf_row = perf[(perf["variant"] == variant) & (perf["period"] == "full_history")]
        turn_row = turnover[turnover["variant"] == variant]
        q_row = quality[(quality["variant"] == variant) & (quality["horizon"] == "1M")]
        rows.append(
            {
                "variant": variant,
                "total_return": float(perf_row["total_return"].iloc[0]) if not perf_row.empty else np.nan,
                "cagr": float(perf_row["cagr"].iloc[0]) if not perf_row.empty else np.nan,
                "mdd": float(perf_row["mdd"].iloc[0]) if not perf_row.empty else np.nan,
                "annual_vol": float(perf_row["annual_vol"].iloc[0]) if not perf_row.empty else np.nan,
                "sharpe": float(perf_row["sharpe"].iloc[0]) if not perf_row.empty else np.nan,
                "avg_turnover_ratio": float(turn_row["avg_turnover_ratio"].iloc[0]) if not turn_row.empty else np.nan,
                "avg_new_entry_1m": float(q_row["avg_forward_return"].iloc[0]) if not q_row.empty else np.nan,
                "new_entry_1m_winner_rate": float(q_row["winner_rate"].iloc[0]) if not q_row.empty else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    if len(out) == 2:
        base = out.iloc[0]
        chal = out.iloc[1]
        delta = pd.DataFrame(
            [
                {
                    "variant": "delta_challenger_minus_baseline",
                    "total_return": chal["total_return"] - base["total_return"],
                    "cagr": chal["cagr"] - base["cagr"],
                    "mdd": chal["mdd"] - base["mdd"],
                    "annual_vol": chal["annual_vol"] - base["annual_vol"],
                    "sharpe": chal["sharpe"] - base["sharpe"],
                    "avg_turnover_ratio": chal["avg_turnover_ratio"] - base["avg_turnover_ratio"],
                    "avg_new_entry_1m": chal["avg_new_entry_1m"] - base["avg_new_entry_1m"],
                    "new_entry_1m_winner_rate": chal["new_entry_1m_winner_rate"] - base["new_entry_1m_winner_rate"],
                }
            ]
        )
        out = pd.concat([out, delta], ignore_index=True)
    return out


def fmt_pct(v: float) -> str:
    return "-" if pd.isna(v) else f"{v:.2%}"


def fmt_num(v: float) -> str:
    return "-" if pd.isna(v) else f"{v:.2f}"


def build_markdown(
    headline: pd.DataFrame,
    perf: pd.DataFrame,
    turnover: pd.DataFrame,
    quality: pd.DataFrame,
    coverage: pd.DataFrame,
    baseline: dict[str, object],
    challenger: dict[str, object],
    start: str,
    end: str,
) -> str:
    lines = [
        "# S2 PIT Challenger Backtest Review",
        "",
        "## Scope",
        f"- backtest window: `{start}` ~ `{end}`",
        "- baseline: current annual-only `s2_fund_scores_monthly`",
        "- challenger: PIT `s2_fund_scores_pit_monthly`",
        "- rule choice: no artificial coverage filter was applied; each date uses only the filings that were actually available by that date",
        "- interpretation: later DART annual filings changing the portfolio is treated as normal point-in-time model behavior, not as distortion",
        "",
    ]

    if not headline.empty:
        lines.extend(
            [
                "## Headline Comparison",
                "| Variant | Total Return | CAGR | MDD | Annual Vol | Sharpe | Avg Turnover | New Entry 1M | New Entry 1M Winner Rate |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in headline.itertuples(index=False):
            lines.append(
                f"| {row.variant} | {fmt_pct(row.total_return)} | {fmt_pct(row.cagr)} | {fmt_pct(row.mdd)} | "
                f"{fmt_pct(row.annual_vol)} | {fmt_num(row.sharpe)} | {fmt_pct(row.avg_turnover_ratio)} | "
                f"{fmt_pct(row.avg_new_entry_1m)} | {fmt_pct(row.new_entry_1m_winner_rate)} |"
            )
        lines.append("")

    if not perf.empty:
        lines.extend(
            [
                "## Performance Windows",
                "| Variant | Period | Total Return | CAGR | MDD | Annual Vol | Sharpe |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in perf.sort_values(["variant", "period"]).itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.period} | {fmt_pct(row.total_return)} | {fmt_pct(row.cagr)} | "
                f"{fmt_pct(row.mdd)} | {fmt_pct(row.annual_vol)} | {fmt_num(row.sharpe)} |"
            )
        lines.append("")

    if not turnover.empty:
        lines.extend(
            [
                "## Turnover Summary",
                "| Variant | Avg Add Count | Avg Drop Count | Avg Turnover | Median Turnover | Max Turnover |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in turnover.sort_values("variant").itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.avg_add_count:.2f} | {row.avg_drop_count:.2f} | {fmt_pct(row.avg_turnover_ratio)} | "
                f"{fmt_pct(row.median_turnover_ratio)} | {fmt_pct(row.max_turnover_ratio)} |"
            )
        lines.append("")

    if not quality.empty:
        lines.extend(
            [
                "## New Entry Quality",
                "| Variant | Horizon | Entries | Avg Forward Return | Median Forward Return | Winner Rate | Loser Rate |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in quality.sort_values(["variant", "horizon"]).itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.horizon} | {row.n_entries} | {fmt_pct(row.avg_forward_return)} | "
                f"{fmt_pct(row.median_forward_return)} | {fmt_pct(row.winner_rate)} | {fmt_pct(row.loser_rate)} |"
            )
        lines.append("")

    if not coverage.empty:
        latest_pit = coverage.loc[coverage["pit_valid_count"].notna()].sort_values("date").iloc[-1]
        latest_base = coverage.loc[coverage["baseline_valid_count"].notna()].sort_values("date").iloc[-1]
        common = coverage.loc[coverage["baseline_valid_count"].notna() & coverage["pit_valid_count"].notna()].sort_values("date")
        latest_common = common.iloc[-1] if not common.empty else None
        med = coverage[["baseline_valid_count", "pit_valid_count"]].median(numeric_only=True)
        lines.extend(
            [
                "## PIT Coverage",
                f"- latest PIT date `{pd.Timestamp(latest_pit['date']).date()}`:",
                f"  - PIT valid count: `{int(latest_pit['pit_valid_count']) if pd.notna(latest_pit['pit_valid_count']) else 0}`",
                f"  - PIT all-row average coverage score: `{fmt_num(float(latest_pit['pit_all_avg_coverage_score']))}`",
                f"- latest baseline date `{pd.Timestamp(latest_base['date']).date()}`:",
                f"  - baseline valid count: `{int(latest_base['baseline_valid_count']) if pd.notna(latest_base['baseline_valid_count']) else 0}`",
                (
                    f"- latest common monthly date `{pd.Timestamp(latest_common['date']).date()}`:"
                    if latest_common is not None
                    else "- latest common monthly date: `n/a`"
                ),
            ]
        )
        if latest_common is not None:
            lines.extend(
                [
                    f"  - baseline valid count: `{int(latest_common['baseline_valid_count'])}`",
                    f"  - PIT valid count: `{int(latest_common['pit_valid_count'])}`",
                    f"  - PIT valid ratio vs baseline: `{fmt_pct(float(latest_common['pit_valid_ratio_vs_baseline']))}`",
                ]
            )
        lines.extend(
            [
                f"- median PIT valid count over the test window: `{fmt_num(float(med['pit_valid_count']))}`",
                f"- median baseline valid count over the test window: `{fmt_num(float(med['baseline_valid_count']))}`",
                "- note: baseline `valid_fund` is annual-only and much broader; PIT `valid_fund` is a stricter fully point-in-time subset, so the raw count ratio should be read as selectivity, not as a data error",
                "",
                "## Run Artifacts",
                f"- baseline summary: `{baseline['summary_path']}`",
                f"- baseline equity: `{baseline['equity_path']}`",
                f"- baseline holdings: `{baseline['holdings_path']}`",
                f"- challenger summary: `{challenger['summary_path']}`",
                f"- challenger equity: `{challenger['equity_path']}`",
                f"- challenger holdings: `{challenger['holdings_path']}`",
                "",
            ]
        )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    outdir = OUTDIR if not args.tag else Path(str(OUTDIR) + f"_{args.tag}")
    outdir.mkdir(parents=True, exist_ok=True)

    baseline = run_variant("baseline", "s2_fund_scores_monthly", args.start, args.end, outdir)
    challenger = run_variant("challenger", "s2_fund_scores_pit_monthly", args.start, args.end, outdir)

    perf = pd.concat(
        [
            perf_windows(baseline["equity"], "S2_baseline"),
            perf_windows(challenger["equity"], "S2_pit_challenger"),
        ],
        ignore_index=True,
    )

    turn_detail_base, turn_sum_base = turnover_summary(baseline["holdings"], "S2_baseline")
    turn_detail_chal, turn_sum_chal = turnover_summary(challenger["holdings"], "S2_pit_challenger")
    turnover_detail = pd.concat([turn_detail_base, turn_detail_chal], ignore_index=True)
    turnover_summary_df = pd.concat([turn_sum_base, turn_sum_chal], ignore_index=True)

    price_wide, end_maps = load_price_wide()
    entry_detail_base, entry_sum_base = new_entry_quality(baseline["holdings"], price_wide, end_maps, "S2_baseline")
    entry_detail_chal, entry_sum_chal = new_entry_quality(challenger["holdings"], price_wide, end_maps, "S2_pit_challenger")
    entry_detail = pd.concat([entry_detail_base, entry_detail_chal], ignore_index=True)
    entry_summary = pd.concat([entry_sum_base, entry_sum_chal], ignore_index=True)

    coverage = load_valid_counts(load_universe_tickers())
    coverage = coverage[(coverage["date"] >= pd.Timestamp(args.start)) & (coverage["date"] <= pd.Timestamp(args.end))].copy()
    headline = build_headline(perf, turnover_summary_df, entry_summary)

    headline.to_csv(outdir / "s2_pit_challenger_headline.csv", index=False, encoding="utf-8-sig")
    perf.to_csv(outdir / "s2_pit_challenger_performance_summary.csv", index=False, encoding="utf-8-sig")
    turnover_detail.to_csv(outdir / "s2_pit_challenger_turnover_detail.csv", index=False, encoding="utf-8-sig")
    turnover_summary_df.to_csv(outdir / "s2_pit_challenger_turnover_summary.csv", index=False, encoding="utf-8-sig")
    entry_detail.to_csv(outdir / "s2_pit_challenger_new_entry_detail.csv", index=False, encoding="utf-8-sig")
    entry_summary.to_csv(outdir / "s2_pit_challenger_new_entry_summary.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(outdir / "s2_pit_challenger_coverage.csv", index=False, encoding="utf-8-sig")
    (outdir / "s2_pit_challenger_backtest_review.md").write_text(
        build_markdown(headline, perf, turnover_summary_df, entry_summary, coverage, baseline, challenger, args.start, args.end),
        encoding="utf-8",
    )

    print(f"[DONE] outdir={outdir}")
    print(f"[BASELINE] {baseline['summary_path']}")
    print(f"[CHALLENGER] {challenger['summary_path']}")


if __name__ == "__main__":
    main()
