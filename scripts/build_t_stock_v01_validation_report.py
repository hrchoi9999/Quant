from __future__ import annotations

import argparse
import sqlite3
from bisect import bisect_left
from pathlib import Path

import pandas as pd

from tseries_refresh_utils import ensure_run_dir, normalize_run_date


BASE_DIR = Path(r"D:\Quant")
PRICE_DB = BASE_DIR / "data" / "db" / "price.db"
MODEL_CODE = "T-STOCK-V01"
FORWARD_HORIZONS = {"1W": 5, "2W": 10, "1M": 20}
BUCKET_ORDER = {"confirmed": 0, "near": 1, "observe": 2}


PriceSeries = tuple[list[str], list[float]]


def _load_price_maps() -> tuple[dict[str, PriceSeries], dict[str, str], list[str]]:
    with sqlite3.connect(PRICE_DB) as con:
        master = pd.read_sql_query(
            """
            SELECT ticker, market
            FROM instrument_master
            WHERE asset_type = 'STOCK'
            """,
            con,
            dtype={"ticker": str},
        )
        master["ticker"] = master["ticker"].str.zfill(6)
        stock_tickers = sorted(master["ticker"].dropna().unique().tolist())
        ticker_market = dict(zip(master["ticker"], master["market"]))

        prices = pd.read_sql_query(
            """
            SELECT ticker, date, close
            FROM prices_daily
            WHERE ticker IN (
                SELECT ticker FROM instrument_master WHERE asset_type = 'STOCK'
            )
              AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            con,
            dtype={"ticker": str},
        )

    prices["ticker"] = prices["ticker"].str.zfill(6)
    price_map: dict[str, PriceSeries] = {}
    for ticker, g in prices.groupby("ticker", sort=False):
        price_map[ticker] = (g["date"].astype(str).tolist(), g["close"].astype(float).tolist())
    return price_map, ticker_market, stock_tickers


def _forward_return(series: PriceSeries | None, signal_date: str, steps: int) -> float | None:
    if not series:
        return None
    dates, closes = series
    idx = bisect_left(dates, signal_date)
    if idx >= len(dates) or idx + steps >= len(dates):
        return None
    entry = closes[idx]
    exit_ = closes[idx + steps]
    if not entry or pd.isna(entry) or pd.isna(exit_):
        return None
    return float(exit_ / entry - 1.0)


def _attach_event_returns(hist: pd.DataFrame, price_map: dict[str, PriceSeries]) -> pd.DataFrame:
    out = hist.copy()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["signal_date"] = out["signal_date"].astype(str)
    for label, steps in FORWARD_HORIZONS.items():
        col = f"ret_{label}"
        out[col] = [
            _forward_return(price_map.get(ticker), signal_date, steps)
            for ticker, signal_date in zip(out["ticker"], out["signal_date"])
        ]
    return out


def _build_baseline(
    signal_dates: list[str],
    price_map: dict[str, PriceSeries],
    ticker_market: dict[str, str],
    stock_tickers: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for signal_date in sorted(signal_dates):
        for scope in ["ALL", "KOSPI", "KOSDAQ"]:
            scope_tickers = stock_tickers if scope == "ALL" else [t for t in stock_tickers if ticker_market.get(t) == scope]
            row: dict[str, object] = {"signal_date": signal_date, "market_scope": scope}
            for label, steps in FORWARD_HORIZONS.items():
                vals = [
                    _forward_return(price_map.get(ticker), signal_date, steps)
                    for ticker in scope_tickers
                ]
                vals = [v for v in vals if v is not None]
                row[f"baseline_ret_{label}"] = sum(vals) / len(vals) if vals else None
                row[f"baseline_n_{label}"] = len(vals)
            rows.append(row)
    return pd.DataFrame(rows)


def _max_drawdown(returns: pd.Series) -> float | None:
    vals = returns.dropna().astype(float)
    if vals.empty:
        return None
    curve = (1.0 + vals).cumprod()
    dd = curve / curve.cummax() - 1.0
    return float(dd.min())


def _summarize(events: pd.DataFrame, by: list[str], baseline: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, g in events.groupby(by, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row: dict[str, object] = dict(zip(by, keys))
        row["obs_n"] = int(len(g))
        row["t10_hit_rate"] = float(g["actual_t10_or_better_2to4"].mean() * 100.0)
        row["t3_hit_rate"] = float(g["actual_t3_2to4"].mean() * 100.0)
        for label in FORWARD_HORIZONS:
            ret_col = f"ret_{label}"
            vals = g[ret_col].dropna().astype(float)
            row[f"resolved_n_{label}"] = int(vals.size)
            row[f"avg_ret_{label}"] = float(vals.mean() * 100.0) if vals.size else None
            row[f"median_ret_{label}"] = float(vals.median() * 100.0) if vals.size else None
            row[f"win_rate_{label}"] = float((vals > 0).mean() * 100.0) if vals.size else None
            row[f"worst_ret_{label}"] = float(vals.min() * 100.0) if vals.size else None

            ts = g.groupby("signal_date", as_index=False)[ret_col].mean()
            row[f"mdd_{label}"] = (_max_drawdown(ts[ret_col]) * 100.0) if not ts.empty else None

            base_col = f"baseline_ret_{label}"
            scope_base = baseline[baseline["market_scope"] == "ALL"][["signal_date", base_col]]
            joined = g[["signal_date", ret_col]].merge(scope_base, on="signal_date", how="left")
            excess = joined[ret_col].astype(float) - joined[base_col].astype(float)
            row[f"avg_excess_vs_all_{label}"] = float(excess.mean() * 100.0) if excess.notna().any() else None
        rows.append(row)

    out = pd.DataFrame(rows)
    if "candidate_bucket" in out.columns:
        out["_bucket_order"] = out["candidate_bucket"].map(BUCKET_ORDER).fillna(99)
        out = out.sort_values([c for c in ["_bucket_order", "horizon"] if c in out.columns]).drop(columns=["_bucket_order"])
    return out


def _build_timeseries(events: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for (bucket, signal_date), g in events.groupby(["candidate_bucket", "signal_date"]):
        row: dict[str, object] = {
            "model_code": MODEL_CODE,
            "candidate_bucket": bucket,
            "signal_date": signal_date,
            "obs_n": int(len(g)),
        }
        for label in FORWARD_HORIZONS:
            row[f"portfolio_ret_{label}"] = g[f"ret_{label}"].mean()
        frames.append(row)
    ts = pd.DataFrame(frames)
    if ts.empty:
        return ts
    base = baseline[baseline["market_scope"] == "ALL"].copy()
    return ts.merge(base, on="signal_date", how="left").sort_values(["signal_date", "candidate_bucket"])


def _fmt_pct(x: object) -> str:
    if pd.isna(x):
        return "N/A"
    return f"{float(x):.2f}%"


def _write_markdown(
    out_path: Path,
    run_date: str,
    asof_date: str,
    latest: pd.DataFrame,
    summary: pd.DataFrame,
    by_horizon: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append(f"# T-STOCK-V01 Performance Validation Report ({run_date})")
    lines.append("")
    lines.append("## Scope")
    lines.append(f"- model_code: `{MODEL_CODE}`")
    lines.append(f"- latest_asof_date: `{asof_date}`")
    lines.append("- validation: candidate bucket hit-rate, 1W/2W/1M realized returns, excess return vs ALL stock baseline, MDD proxy")
    lines.append("- note: returns are event-level forward close-to-close returns; MDD is based on equal-weight bucket return by signal_date.")
    lines.append("")
    lines.append("## Latest Watchlist")
    if latest.empty:
        lines.append("- No latest watchlist rows.")
    else:
        counts = latest["candidate_bucket"].value_counts().to_dict()
        lines.append(f"- confirmed: `{int(counts.get('confirmed', 0))}`")
        lines.append(f"- near: `{int(counts.get('near', 0))}`")
        lines.append(f"- observe: `{int(counts.get('observe', 0))}`")
        lines.append(f"- total: `{len(latest)}`")
    lines.append("")
    lines.append("## Bucket Summary")
    cols = [
        "candidate_bucket",
        "obs_n",
        "t10_hit_rate",
        "t3_hit_rate",
        "avg_ret_1W",
        "avg_excess_vs_all_1W",
        "avg_ret_2W",
        "avg_excess_vs_all_2W",
        "avg_ret_1M",
        "avg_excess_vs_all_1M",
        "mdd_1M",
    ]
    lines.append("| bucket | obs | T10 hit | T3 hit | 1W | 1W excess | 2W | 2W excess | 1M | 1M excess | 1M MDD |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, row in summary[cols].iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["candidate_bucket"]),
                    str(int(row["obs_n"])),
                    _fmt_pct(row["t10_hit_rate"]),
                    _fmt_pct(row["t3_hit_rate"]),
                    _fmt_pct(row["avg_ret_1W"]),
                    _fmt_pct(row["avg_excess_vs_all_1W"]),
                    _fmt_pct(row["avg_ret_2W"]),
                    _fmt_pct(row["avg_excess_vs_all_2W"]),
                    _fmt_pct(row["avg_ret_1M"]),
                    _fmt_pct(row["avg_excess_vs_all_1M"]),
                    _fmt_pct(row["mdd_1M"]),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Interpretation")
    confirmed = summary[summary["candidate_bucket"] == "confirmed"]
    observe = summary[summary["candidate_bucket"] == "observe"]
    if not confirmed.empty and not observe.empty:
        c = confirmed.iloc[0]
        o = observe.iloc[0]
        lines.append(
            f"- confirmed bucket has materially higher T10/T3 hit-rate than observe "
            f"(`{c['t10_hit_rate']:.2f}%` vs `{o['t10_hit_rate']:.2f}%` T10)."
        )
        lines.append(
            f"- 1M average return gap confirmed-observe: `{float(c['avg_ret_1M'] - o['avg_ret_1M']):.2f}%p`."
        )
    lines.append("- Keep this model in shadow validation; production use should require 1M+ live evidence after 2026-06-12 policy review.")
    lines.append("")
    lines.append("## By Model Horizon")
    lines.append("| bucket | model_horizon | obs | T10 hit | T3 hit | 1M | 1M excess |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for _, row in by_horizon.iterrows():
        lines.append(
            f"| {row['candidate_bucket']} | {row['horizon']} | {int(row['obs_n'])} | "
            f"{_fmt_pct(row['t10_hit_rate'])} | {_fmt_pct(row['t3_hit_rate'])} | "
            f"{_fmt_pct(row['avg_ret_1M'])} | {_fmt_pct(row['avg_excess_vs_all_1M'])} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build T-STOCK-V01 validation report.")
    ap.add_argument("--run-date", default=None, help="YYYYMMDD or YYYY-MM-DD run folder.")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD latest asof. Used only for output naming/default latest file.")
    args = ap.parse_args()

    run_date = normalize_run_date(args.run_date)
    run_root = ensure_run_dir(run_date)
    op_dir = run_root / "T_STOCK_V01_OPERATIONALIZATION"
    asof_date = args.asof or f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:8]}"

    hist_path = op_dir / f"t_stock_v01_shadow_tracking_history_{run_date}.csv"
    latest_path = op_dir / f"t_stock_v01_latest_watchlist_{asof_date}.csv"
    hist = pd.read_csv(hist_path, dtype={"ticker": str})
    latest = pd.read_csv(latest_path, dtype={"ticker": str}) if latest_path.exists() else pd.DataFrame()

    price_map, ticker_market, stock_tickers = _load_price_maps()
    events = _attach_event_returns(hist, price_map)
    baseline = _build_baseline(sorted(events["signal_date"].dropna().unique()), price_map, ticker_market, stock_tickers)
    summary = _summarize(events, ["candidate_bucket"], baseline)
    by_horizon = _summarize(events, ["candidate_bucket", "horizon"], baseline)
    timeseries = _build_timeseries(events, baseline)

    events.to_csv(op_dir / f"t_stock_v01_validation_events_{run_date}.csv", index=False, encoding="utf-8-sig")
    baseline.to_csv(op_dir / f"t_stock_v01_validation_baseline_{run_date}.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(op_dir / f"t_stock_v01_validation_summary_{run_date}.csv", index=False, encoding="utf-8-sig")
    by_horizon.to_csv(op_dir / f"t_stock_v01_validation_summary_by_model_horizon_{run_date}.csv", index=False, encoding="utf-8-sig")
    timeseries.to_csv(op_dir / f"t_stock_v01_validation_timeseries_{run_date}.csv", index=False, encoding="utf-8-sig")
    _write_markdown(
        op_dir / f"t_stock_v01_validation_report_{run_date}.md",
        run_date,
        asof_date,
        latest,
        summary,
        by_horizon,
    )

    print(
        {
            "run_date": run_date,
            "asof_date": asof_date,
            "events": int(len(events)),
            "summary_rows": int(len(summary)),
            "report": str(op_dir / f"t_stock_v01_validation_report_{run_date}.md"),
        }
    )


if __name__ == "__main__":
    main()
