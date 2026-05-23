from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Quant")
QUANT_DB = ROOT / r"data\db\quant_service.db"
DETAIL_DB = ROOT / r"data\db\quant_service_detail.db"
PRICE_DB = ROOT / r"data\db\price.db"
DEFAULT_I_DB = ROOT / r"data\db\i_series_research_strong_rsi_raw_top30_s65_recheck.db"
OUT_DB = ROOT / r"data\db\i_series_research.db"
OUT_DIR = ROOT / r"reports\i_series_stock_v01"
STOCK_MODELS = ["S2", "S2_PIT_V01", "S3", "S3_CORE2", "S3_ACCEL_V01"]
FORWARD_COLS = ["ret_fwd_1w", "ret_fwd_2w", "ret_fwd_4w", "ret_fwd_8w", "ret_fwd_12w"]


def _zfill(frame: pd.DataFrame, col: str = "ticker") -> pd.DataFrame:
    out = frame.copy()
    out[col] = out[col].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    return out


def _pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _metrics(nav: pd.DataFrame) -> dict[str, Any]:
    if nav.empty or len(nav) < 2:
        return {
            "start": None,
            "end": None,
            "cagr": None,
            "total_return": None,
            "mdd": None,
            "sharpe": None,
            "avg_exposure": None,
            "avg_holdings": None,
            "latest_holdings": None,
        }
    work = nav.sort_values("date").copy()
    work["date"] = pd.to_datetime(work["date"])
    total_return = float(work["nav"].iloc[-1] / work["nav"].iloc[0] - 1.0)
    years = max((work["date"].iloc[-1] - work["date"].iloc[0]).days / 365.25, 1 / 252)
    cagr = float((work["nav"].iloc[-1] / work["nav"].iloc[0]) ** (1 / years) - 1.0)
    dd = work["nav"] / work["nav"].cummax() - 1.0
    ret = work["nav"].pct_change().fillna(0.0)
    vol = float(ret.std(ddof=0))
    sharpe = None if vol <= 0 else float(ret.mean() / vol * np.sqrt(252.0))
    return {
        "start": work["date"].iloc[0].strftime("%Y-%m-%d"),
        "end": work["date"].iloc[-1].strftime("%Y-%m-%d"),
        "cagr": cagr,
        "total_return": total_return,
        "mdd": float(dd.min()),
        "sharpe": sharpe,
        "avg_exposure": float(work["exposure"].mean()),
        "avg_holdings": float(work["holdings_count"].mean()),
        "latest_holdings": int(work["holdings_count"].iloc[-1]),
    }


def load_s_holdings(start: str, asof: str) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in STOCK_MODELS)
    with sqlite3.connect(str(QUANT_DB)) as con:
        current = pd.read_sql_query(
            f"""
            SELECT model_code, published_run_id
            FROM pub_model_current
            WHERE model_code IN ({placeholders})
            """,
            con,
            params=STOCK_MODELS,
        )
    rows: list[pd.DataFrame] = []
    with sqlite3.connect(str(DETAIL_DB)) as con:
        for item in current.itertuples(index=False):
            frame = pd.read_sql_query(
                """
                SELECT date AS base_date, ticker, rank_no, weight, score
                FROM run_holdings_history
                WHERE run_id = ?
                  AND date >= ?
                  AND date <= ?
                  AND ticker IS NOT NULL
                  AND upper(ticker) <> 'CASH'
                ORDER BY date, rank_no, ticker
                """,
                con,
                params=[item.published_run_id, start, asof],
                parse_dates=["base_date"],
            )
            if frame.empty:
                continue
            frame["base_model_code"] = item.model_code
            frame["published_run_id"] = item.published_run_id
            rows.append(frame)
    if not rows:
        return pd.DataFrame()
    out = _zfill(pd.concat(rows, ignore_index=True))
    out["weight"] = pd.to_numeric(out["weight"], errors="coerce").fillna(0.0)
    out["base_score"] = pd.to_numeric(out["score"], errors="coerce")
    # Some strategy exports keep rank/score history but leave weight as 0.
    # For overlay simulations, fall back to equal weight within each snapshot.
    fixed: list[pd.DataFrame] = []
    for _, frame in out.groupby(["base_model_code", "base_date"], dropna=False):
        f = frame.copy()
        if float(f["weight"].sum()) <= 1e-12 and len(f) > 0:
            f["weight"] = 1.0 / len(f)
        fixed.append(f)
    out = pd.concat(fixed, ignore_index=True)
    return out


def load_i_weekly(i_db: Path, start: str, asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(i_db)) as con:
        df = pd.read_sql_query(
            """
            SELECT date AS i_date, ticker, i_signal, i_raw_score, i_score,
                   universe_rank_no, universe_rank_score, heat_bucket, earlyness_score,
                   rsi14, ret_21d, ret_63d, ret_252d, gap_ma200
            FROM i_stock_v01_signals_weekly
            WHERE date >= ?
              AND date <= ?
            ORDER BY ticker, date
            """,
            con,
            params=[start, asof],
            parse_dates=["i_date"],
        )
    if df.empty:
        return df
    return _zfill(df)


def load_i_forward(i_db: Path, start: str, asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(i_db)) as con:
        df = pd.read_sql_query(
            f"""
            SELECT date AS base_date, ticker, {", ".join(FORWARD_COLS)}
            FROM i_stock_v01_features_daily
            WHERE date >= ?
              AND date <= ?
            ORDER BY ticker, date
            """,
            con,
            params=[start, asof],
            parse_dates=["base_date"],
        )
    return _zfill(df) if not df.empty else df


def attach_i_state(holdings: pd.DataFrame, i_weekly: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    h = holdings.sort_values(["ticker", "base_date"]).copy()
    i = i_weekly.sort_values(["ticker", "i_date"]).copy()
    for ticker, hframe in h.groupby("ticker", sort=False):
        iframe = i.loc[i["ticker"] == ticker].copy()
        if iframe.empty:
            out = hframe.copy()
            for col in [
                "i_date",
                "i_signal",
                "i_raw_score",
                "i_score",
                "universe_rank_no",
                "universe_rank_score",
                "heat_bucket",
                "earlyness_score",
                "rsi14",
                "ret_21d",
                "ret_63d",
                "ret_252d",
                "gap_ma200",
            ]:
                out[col] = np.nan
            rows.append(out)
            continue
        rows.append(
            pd.merge_asof(
                hframe.sort_values("base_date"),
                iframe.sort_values("i_date"),
                left_on="base_date",
                right_on="i_date",
                by="ticker",
                direction="backward",
            )
        )
    out = pd.concat(rows, ignore_index=True)
    out["heat_bucket"] = out["heat_bucket"].fillna("no_i_state")
    return out


def attach_forward_returns(tagged: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    f = forward.copy()
    f["base_date"] = pd.to_datetime(f["base_date"]).dt.strftime("%Y-%m-%d")
    out = tagged.copy()
    out["base_date"] = pd.to_datetime(out["base_date"]).dt.strftime("%Y-%m-%d")
    return out.merge(f, on=["ticker", "base_date"], how="left")


def summarize_forward(tagged: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, frame in tagged.groupby(["base_model_code", "heat_bucket"], dropna=False):
        row = {"base_model_code": keys[0], "heat_bucket": keys[1], "rows": int(len(frame)), "snapshots": int(frame["base_date"].nunique())}
        row["avg_weight"] = float(pd.to_numeric(frame["weight"], errors="coerce").mean())
        row["avg_base_score"] = float(pd.to_numeric(frame["base_score"], errors="coerce").mean()) if frame["base_score"].notna().any() else None
        row["avg_i_raw_score"] = float(pd.to_numeric(frame["i_raw_score"], errors="coerce").mean()) if frame["i_raw_score"].notna().any() else None
        for col in FORWARD_COLS:
            label = col.replace("ret_fwd_", "")
            vals = pd.to_numeric(frame[col], errors="coerce").dropna()
            row[f"avg_{label}"] = None if vals.empty else float(vals.mean())
            row[f"win_{label}"] = None if vals.empty else float((vals > 0).mean())
            row[f"n_{label}"] = int(len(vals))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["base_model_code", "heat_bucket"]).reset_index(drop=True)


def load_price_returns(tickers: list[str], start: str, asof: str) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in tickers)
    with sqlite3.connect(str(PRICE_DB)) as con:
        prices = pd.read_sql_query(
            f"""
            SELECT ticker, date, close
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date >= ?
              AND date <= ?
              AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            con,
            params=[*tickers, start, asof],
            parse_dates=["date"],
        )
    prices = _zfill(prices)
    close = prices.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
    return close.pct_change().fillna(0.0)


def _variant_weights(frame: pd.DataFrame, variant: str) -> dict[str, float]:
    base = {str(row.ticker): float(row.weight or 0.0) for row in frame.itertuples(index=False)}
    if variant == "baseline":
        return base
    if variant == "reaccel_cash":
        return {
            str(row.ticker): float(row.weight or 0.0)
            for row in frame.itertuples(index=False)
            if row.heat_bucket == "reacceleration"
        }
    if variant == "reaccel_overheat_cash":
        return {
            str(row.ticker): float(row.weight or 0.0)
            for row in frame.itertuples(index=False)
            if row.heat_bucket in {"reacceleration", "overheated_watch"}
        }
    if variant == "reaccel_tilt":
        adjusted: dict[str, float] = {}
        for row in frame.itertuples(index=False):
            multiplier = 1.5 if row.heat_bucket == "reacceleration" else 0.75
            adjusted[str(row.ticker)] = float(row.weight or 0.0) * multiplier
        base_exposure = sum(base.values())
        adjusted_exposure = sum(adjusted.values())
        if adjusted_exposure > 0:
            scale = base_exposure / adjusted_exposure
            adjusted = {ticker: weight * scale for ticker, weight in adjusted.items()}
        return adjusted
    raise ValueError(f"unknown variant: {variant}")


def simulate_nav(tagged: pd.DataFrame, daily_ret: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    variants = ["baseline", "reaccel_cash", "reaccel_overheat_cash", "reaccel_tilt"]
    nav_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for model, model_frame in tagged.groupby("base_model_code", sort=True):
        snapshots = sorted(pd.to_datetime(model_frame["base_date"]).drop_duplicates())
        if not snapshots:
            continue
        snap_map = {pd.Timestamp(date): frame.copy() for date, frame in model_frame.groupby(pd.to_datetime(model_frame["base_date"]))}
        for variant in variants:
            nav = 1.0
            rows: list[dict[str, Any]] = []
            for idx, snap_date in enumerate(snapshots):
                frame = snap_map[pd.Timestamp(snap_date)]
                weights = _variant_weights(frame, variant)
                next_date = snapshots[idx + 1] if idx + 1 < len(snapshots) else daily_ret.index.max()
                period_dates = daily_ret.index[(daily_ret.index >= snap_date) & (daily_ret.index <= next_date)]
                for day in period_dates:
                    if day == snap_date:
                        daily = 0.0
                    else:
                        daily = float(sum(weight * daily_ret.at[day, ticker] for ticker, weight in weights.items() if ticker in daily_ret.columns))
                        nav *= 1.0 + daily
                    rows.append(
                        {
                            "base_model_code": model,
                            "variant": variant,
                            "date": day.strftime("%Y-%m-%d"),
                            "nav": nav,
                            "daily_return": daily,
                            "holdings_count": len([w for w in weights.values() if abs(w) > 1e-12]),
                            "exposure": sum(weights.values()),
                        }
                    )
            nav_df = pd.DataFrame(rows).drop_duplicates(["date"], keep="last")
            metric = {"base_model_code": model, "variant": variant}
            metric.update(_metrics(nav_df))
            metric_rows.append(metric)
            nav_rows.extend(nav_df.to_dict("records"))
    return pd.DataFrame(nav_rows), pd.DataFrame(metric_rows)


def write_report(forward_summary: pd.DataFrame, perf: pd.DataFrame, latest: pd.DataFrame, outdir: Path, asof: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"I_REACCEL_TIMING_OVERLAY_{asof.replace('-', '')}.md"
    lines = [
        f"# I Reaccel Timing Overlay ({asof})",
        "",
        "## Forward Return By Existing Model And I Heat Bucket",
        "",
        "| model | heat bucket | rows | snaps | avg 4w | avg 8w | avg 12w | win 4w | avg i raw |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in forward_summary.itertuples(index=False):
        lines.append(
            f"| {row.base_model_code} | {row.heat_bucket} | {int(row.rows)} | {int(row.snapshots)} | "
            f"{_pct(getattr(row, 'avg_4w'))} | {_pct(getattr(row, 'avg_8w'))} | {_pct(getattr(row, 'avg_12w'))} | "
            f"{_pct(getattr(row, 'win_4w'))} | {_num(getattr(row, 'avg_i_raw_score'))} |"
        )
    lines.extend(
        [
            "",
            "## Simulated Portfolio Impact",
            "",
            "| model | variant | CAGR | total return | MDD | Sharpe | avg exposure | avg holdings | latest holdings |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in perf.sort_values(["base_model_code", "variant"]).itertuples(index=False):
        lines.append(
            f"| {row.base_model_code} | {row.variant} | {_pct(row.cagr)} | {_pct(row.total_return)} | {_pct(row.mdd)} | "
            f"{_num(row.sharpe)} | {_pct(row.avg_exposure)} | {_num(row.avg_holdings)} | {row.latest_holdings} |"
        )
    lines.extend(
        [
            "",
            "## Latest Tagged Holdings",
            "",
            "| model | heat bucket | rows | total weight | avg i raw |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    latest_summary = (
        latest.groupby(["base_model_code", "heat_bucket"], dropna=False)
        .agg(rows=("ticker", "count"), total_weight=("weight", "sum"), avg_i_raw=("i_raw_score", "mean"))
        .reset_index()
        .sort_values(["base_model_code", "heat_bucket"])
    )
    for row in latest_summary.itertuples(index=False):
        lines.append(
            f"| {row.base_model_code} | {row.heat_bucket} | {int(row.rows)} | {_pct(row.total_weight)} | {_num(row.avg_i_raw)} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation Guide",
            "",
            "- `baseline`: original S-model holdings and weights, simulated from holding snapshots.",
            "- `reaccel_cash`: keep only existing holdings tagged `reacceleration`; the rest becomes cash.",
            "- `reaccel_overheat_cash`: keep existing holdings tagged `reacceleration` or `overheated_watch`; the rest becomes cash.",
            "- `reaccel_tilt`: boost reaccel holdings by 1.5x and reduce others by 0.75x, then normalize back to the original exposure.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Test whether I reaccel state improves existing S-model timing/performance.")
    ap.add_argument("--asof", default="2026-04-29")
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--i-db", default=str(DEFAULT_I_DB))
    ap.add_argument("--out-db", default=str(OUT_DB))
    ap.add_argument("--outdir", default=str(OUT_DIR))
    args = ap.parse_args()

    holdings = load_s_holdings(args.start, args.asof)
    i_weekly = load_i_weekly(Path(args.i_db), args.start, args.asof)
    forward = load_i_forward(Path(args.i_db), args.start, args.asof)
    if holdings.empty or i_weekly.empty:
        raise SystemExit("missing holdings or I weekly signals")
    tagged = attach_i_state(holdings, i_weekly)
    tagged = attach_forward_returns(tagged, forward)
    tagged["base_date"] = pd.to_datetime(tagged["base_date"]).dt.strftime("%Y-%m-%d")
    forward_summary = summarize_forward(tagged)
    tickers = sorted(tagged["ticker"].dropna().astype(str).unique().tolist())
    daily_ret = load_price_returns(tickers, args.start, args.asof)
    nav, perf = simulate_nav(tagged, daily_ret)
    latest_date = tagged["base_date"].max()
    latest = tagged.loc[tagged["base_date"] == latest_date].copy()
    out_db = Path(args.out_db)
    with sqlite3.connect(str(out_db)) as con:
        tagged.to_sql("i_reaccel_timing_overlay_history", con, if_exists="replace", index=False)
        forward_summary.to_sql("i_reaccel_timing_overlay_forward_summary", con, if_exists="replace", index=False)
        nav.to_sql("i_reaccel_timing_overlay_nav", con, if_exists="replace", index=False)
        perf.to_sql("i_reaccel_timing_overlay_performance", con, if_exists="replace", index=False)
        latest.to_sql("i_reaccel_timing_overlay_latest", con, if_exists="replace", index=False)
        pd.DataFrame(
            [
                {
                    "asof_date": args.asof,
                    "start": args.start,
                    "i_db": str(Path(args.i_db)),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "tagged_rows": int(len(tagged)),
                    "models": ",".join(sorted(tagged["base_model_code"].unique())),
                }
            ]
        ).to_sql("i_reaccel_timing_overlay_run_meta", con, if_exists="replace", index=False)
    report = write_report(forward_summary, perf, latest, Path(args.outdir), args.asof)
    print(
        json.dumps(
            {
                "status": "ok",
                "asof": args.asof,
                "tagged_rows": int(len(tagged)),
                "summary_rows": int(len(forward_summary)),
                "perf_rows": int(len(perf)),
                "latest_rows": int(len(latest)),
                "report": str(report),
                "out_db": str(out_db),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
