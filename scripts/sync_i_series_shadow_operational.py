from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(r"D:\Quant")
DEFAULT_SOURCE_DB = ROOT / r"data\db\i_series_research_strong_rsi_raw_top30_s65.db"
DEFAULT_OUT_DB = ROOT / r"data\db\i_series_operational.db"
DEFAULT_OUT_DIR = ROOT / r"reports\i_series_stock_v01\operational_shadow"
MODEL_CODE = "I-STOCK-STRONG-RSI-V01"
FORWARD_COLS = ["ret_fwd_1w", "ret_fwd_2w", "ret_fwd_4w", "ret_fwd_8w", "ret_fwd_12w"]
LOOKBACK_WINDOWS = 4
COOLING_WINDOWS = 2


def _load_table(db_path: Path, sql: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as con:
        return pd.read_sql_query(sql, con, params=params)


def _zfill_ticker(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    return df


def _load_source(source_db: Path, asof: str | None) -> tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    latest = _load_table(
        source_db,
        "SELECT max(date) AS asof_date FROM i_stock_v01_backtest_holdings WHERE date <= COALESCE(?, date)",
        (asof,),
    ).iloc[0]["asof_date"]
    if pd.isna(latest):
        raise SystemExit("No I-series holdings found for requested asof.")
    latest = str(latest)

    holdings = _load_table(
        source_db,
        """
        SELECT date AS signal_date, ticker, name, portfolio_rank_no, universe_rank_no,
               universe_rank_score, i_raw_score, i_score AS display_score, i_signal, weight
        FROM i_stock_v01_backtest_holdings
        WHERE date <= ?
        """,
        (latest,),
    )
    features = _load_table(
        source_db,
        f"""
        SELECT date AS signal_date, ticker, close, i_raw_score, i_score AS display_score,
               i_signal, rsi14, rsi14_delta_5d, rsi14_delta_10d, macd_hist,
               macd_hist_delta_5d, gap_price_cloud, lagging_strength_26,
               lagging_strength_delta_10d, universe_rank_no, universe_rank_score,
               {", ".join(FORWARD_COLS)}
        FROM i_stock_v01_signals_weekly
        WHERE date <= ?
        """,
        (latest,),
    )
    nav = _load_table(
        source_db,
        """
        SELECT date, nav, daily_return, holdings_count, exposure, turnover, regime_mode
        FROM i_stock_v01_backtest_nav
        WHERE date <= ?
        ORDER BY date
        """,
        (latest,),
    )
    backtest_summary = _load_table(source_db, "SELECT * FROM i_stock_v01_backtest_summary")
    holdings["signal_date"] = pd.to_datetime(holdings["signal_date"]).dt.strftime("%Y-%m-%d")
    features["signal_date"] = pd.to_datetime(features["signal_date"]).dt.strftime("%Y-%m-%d")
    return latest, _zfill_ticker(holdings), _zfill_ticker(features), nav, backtest_summary


def _build_meta(asof: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    model_meta = pd.DataFrame(
        [
            {
                "model_code": MODEL_CODE,
                "display_name": "I-STOCK-STRONG-RSI-V01",
                "asset_scope": "stock",
                "model_family": "i_series",
                "version_label": "V01",
                "status": "shadow",
                "asof_date": asof,
                "notes": (
                    "Independent stock universe discovery model based on strong initial RSI recovery, "
                    "MACD histogram recovery, and Ichimoku cloud proximity/reclaim conditions."
                ),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        ]
    )
    score_schema = pd.DataFrame(
        [
            {
                "model_code": MODEL_CODE,
                "score_field": "i_raw_score",
                "score_role": "internal_selection",
                "scale": "uncapped",
                "description": "Uncapped raw signal strength calculated across the full stock universe.",
            },
            {
                "model_code": MODEL_CODE,
                "score_field": "universe_rank_no",
                "score_role": "universe_relative_rank",
                "scale": "1 is best",
                "description": "Rank across the full stock universe for the same signal date.",
            },
            {
                "model_code": MODEL_CODE,
                "score_field": "universe_rank_score",
                "score_role": "universe_relative_percentile",
                "scale": "0-100",
                "description": "Percentile-style score across the full stock universe for the same signal date.",
            },
            {
                "model_code": MODEL_CODE,
                "score_field": "display_score",
                "score_role": "display",
                "scale": "0-100 capped",
                "description": "User/admin-facing capped score. Do not use alone for selection when capped values tie.",
            },
        ]
    )
    return model_meta, score_schema


def _build_candidate_tables(asof: str, holdings: pd.DataFrame, features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    latest = holdings.loc[holdings["signal_date"] == asof].copy()
    latest["model_code"] = MODEL_CODE
    latest["asof_date"] = asof
    latest["candidate_bucket"] = latest["portfolio_rank_no"].map(lambda x: "core" if int(x) <= 10 else ("candidate" if int(x) <= 30 else "observe"))
    latest = latest[
        [
            "model_code",
            "asof_date",
            "candidate_bucket",
            "ticker",
            "name",
            "portfolio_rank_no",
            "universe_rank_no",
            "universe_rank_score",
            "i_raw_score",
            "display_score",
            "i_signal",
            "weight",
        ]
    ].sort_values(["portfolio_rank_no", "ticker"])

    history = holdings.copy()
    history["model_code"] = MODEL_CODE
    history = history.merge(features[["signal_date", "ticker", *FORWARD_COLS]], on=["signal_date", "ticker"], how="left")
    history["candidate_bucket"] = history["portfolio_rank_no"].map(lambda x: "core" if int(x) <= 10 else "candidate")
    history = history[
        [
            "model_code",
            "signal_date",
            "candidate_bucket",
            "ticker",
            "name",
            "portfolio_rank_no",
            "universe_rank_no",
            "universe_rank_score",
            "i_raw_score",
            "display_score",
            "i_signal",
            *FORWARD_COLS,
        ]
    ].sort_values(["signal_date", "portfolio_rank_no", "ticker"])

    summary_rows: list[dict[str, object]] = []
    for bucket, frame in history.groupby("candidate_bucket", dropna=False):
        row = {
            "model_code": MODEL_CODE,
            "asof_date": asof,
            "candidate_bucket": bucket,
            "obs_n": int(len(frame)),
            "snapshot_count": int(frame["signal_date"].nunique()),
            "avg_i_raw_score": float(frame["i_raw_score"].mean()),
            "avg_universe_rank_score": float(frame["universe_rank_score"].mean()),
        }
        for col in FORWARD_COLS:
            vals = pd.to_numeric(frame[col], errors="coerce").dropna()
            suffix = col.replace("ret_fwd_", "")
            row[f"avg_{suffix}"] = None if vals.empty else float(vals.mean())
            row[f"win_{suffix}"] = None if vals.empty else float((vals > 0).mean())
            row[f"n_{suffix}"] = int(len(vals))
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows).sort_values(["candidate_bucket"])
    return latest, history, summary


def _build_rolling_watchlist(asof: str, history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = history.copy()
    work["signal_date"] = pd.to_datetime(work["signal_date"])
    dates = sorted(work["signal_date"].dropna().unique())
    current_asof = pd.Timestamp(asof)
    recent_dates = dates[-LOOKBACK_WINDOWS:]
    cooling_dates = dates[-(LOOKBACK_WINDOWS + COOLING_WINDOWS) :]
    recent = work.loc[work["signal_date"].isin(recent_dates)].copy()
    cooling = work.loc[work["signal_date"].isin(cooling_dates)].copy()

    rows: list[dict[str, object]] = []
    for ticker, grp in cooling.groupby("ticker", sort=False):
        grp = grp.sort_values(["signal_date", "portfolio_rank_no"]).drop_duplicates("signal_date", keep="first")
        recent_grp = recent.loc[recent["ticker"] == ticker].sort_values(["signal_date", "portfolio_rank_no"]).drop_duplicates("signal_date", keep="first")
        current = grp.loc[grp["signal_date"] == current_asof]
        is_current = not current.empty
        if not is_current and grp["signal_date"].max() not in dates[-COOLING_WINDOWS - 1 : -1]:
            continue
        base = current.iloc[0] if is_current else grp.iloc[-1]
        appearances_recent = int(recent_grp["signal_date"].nunique())
        consecutive = 0
        if is_current:
            recent_set = set(recent_grp["signal_date"].tolist())
            for dt in reversed(recent_dates):
                if dt in recent_set:
                    consecutive += 1
                else:
                    break
        status = "active" if is_current and appearances_recent > 1 else ("new" if is_current else "cooling")
        tier = "core" if int(base["portfolio_rank_no"]) <= 10 else "candidate"
        rows.append(
            {
                "model_code": MODEL_CODE,
                "asof_date": asof,
                "watch_status": status,
                "watch_tier": tier,
                "is_current": int(is_current),
                "appearances_recent": appearances_recent,
                "consecutive_current": consecutive,
                "first_seen_asof": pd.Timestamp(grp["signal_date"].min()).strftime("%Y-%m-%d"),
                "last_seen_asof": pd.Timestamp(grp["signal_date"].max()).strftime("%Y-%m-%d"),
                "ticker": ticker,
                "name": base.get("name"),
                "portfolio_rank_no": int(base["portfolio_rank_no"]),
                "universe_rank_no": int(base["universe_rank_no"]),
                "universe_rank_score": float(base["universe_rank_score"]),
                "i_raw_score": float(base["i_raw_score"]),
                "display_score": float(base["display_score"]),
                "i_signal": base.get("i_signal"),
            }
        )
    latest = pd.DataFrame(rows)
    if latest.empty:
        latest = pd.DataFrame(
            columns=[
                "model_code",
                "asof_date",
                "watch_status",
                "watch_tier",
                "is_current",
                "appearances_recent",
                "consecutive_current",
                "first_seen_asof",
                "last_seen_asof",
                "ticker",
                "name",
                "portfolio_rank_no",
                "universe_rank_no",
                "universe_rank_score",
                "i_raw_score",
                "display_score",
                "i_signal",
            ]
        )
    else:
        status_rank = {"active": 0, "new": 1, "cooling": 2}
        tier_rank = {"core": 0, "candidate": 1}
        latest["status_rank"] = latest["watch_status"].map(status_rank).fillna(9)
        latest["tier_rank"] = latest["watch_tier"].map(tier_rank).fillna(9)
        latest = latest.sort_values(["tier_rank", "status_rank", "portfolio_rank_no", "ticker"]).drop(columns=["status_rank", "tier_rank"])

    summary_rows = []
    for key, col in [("active", "watch_status"), ("new", "watch_status"), ("cooling", "watch_status"), ("tier_core", "watch_tier"), ("tier_candidate", "watch_tier")]:
        value = key.replace("tier_", "") if key.startswith("tier_") else key
        summary_rows.append({"model_code": MODEL_CODE, "asof_date": asof, "bucket": key, "count": int((latest[col] == value).sum())})
    return latest, pd.DataFrame(summary_rows)


def _write_outputs(
    out_db: Path,
    out_dir: Path,
    asof: str,
    model_meta: pd.DataFrame,
    score_schema: pd.DataFrame,
    latest: pd.DataFrame,
    history: pd.DataFrame,
    summary: pd.DataFrame,
    rolling_latest: pd.DataFrame,
    rolling_summary: pd.DataFrame,
    nav: pd.DataFrame,
    backtest_summary: pd.DataFrame,
) -> Path:
    out_db.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(out_db)) as con:
        model_meta.to_sql("is_meta_models", con, if_exists="replace", index=False)
        score_schema.to_sql("is_score_schema", con, if_exists="replace", index=False)
        latest.to_sql("is_candidates_latest", con, if_exists="replace", index=False)
        history.to_sql("is_candidates_history", con, if_exists="replace", index=False)
        summary.to_sql("is_shadow_tracking_summary", con, if_exists="replace", index=False)
        rolling_latest.to_sql("is_rolling_watchlist_latest", con, if_exists="replace", index=False)
        rolling_summary.to_sql("is_rolling_watchlist_summary", con, if_exists="replace", index=False)
        nav.to_sql("is_backtest_nav", con, if_exists="replace", index=False)
        backtest_summary.to_sql("is_backtest_summary", con, if_exists="replace", index=False)
        pd.DataFrame(
            [
                {
                    "model_code": MODEL_CODE,
                    "asof_date": asof,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "latest_rows": int(len(latest)),
                    "history_rows": int(len(history)),
                    "rolling_rows": int(len(rolling_latest)),
                }
            ]
        ).to_sql("is_runs", con, if_exists="replace", index=False)

    token = asof.replace("-", "")
    latest.to_csv(out_dir / f"i_stock_strong_rsi_v01_latest_candidates_{token}.csv", index=False, encoding="utf-8-sig")
    rolling_latest.to_csv(out_dir / f"i_stock_strong_rsi_v01_rolling_watchlist_{token}.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / f"i_stock_strong_rsi_v01_shadow_summary_{token}.csv", index=False, encoding="utf-8-sig")
    report = out_dir / f"I_STOCK_STRONG_RSI_V01_SHADOW_{token}.md"
    lines = [
        f"# I-STOCK-STRONG-RSI-V01 Shadow Snapshot ({asof})",
        "",
        "## Model",
        "",
        "- status: shadow",
        "- selection: full universe raw score top30",
        "- score schema: raw/rank/display separated",
        "",
        "## Latest Candidates",
        "",
        "| rank | universe_rank | ticker | name | raw | rank_score | display | signal |",
        "| ---: | ---: | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in latest.head(30).itertuples(index=False):
        lines.append(
            f"| {int(row.portfolio_rank_no)} | {int(row.universe_rank_no)} | {row.ticker} | {row.name} | "
            f"{float(row.i_raw_score):.2f} | {float(row.universe_rank_score):.2f} | {float(row.display_score):.2f} | {row.i_signal} |"
        )
    lines.extend(["", "## Shadow Summary", "", "| bucket | obs | avg 4w | avg 8w | avg 12w | win 4w |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in summary.itertuples(index=False):
        def pct(v: object) -> str:
            return "" if pd.isna(v) else f"{float(v):.2%}"

        lines.append(
            f"| {row.candidate_bucket} | {int(row.obs_n)} | {pct(row.avg_4w)} | {pct(row.avg_8w)} | {pct(row.avg_12w)} | {pct(row.win_4w)} |"
        )
    lines.extend(["", "## Rolling Watchlist", "", "| bucket | count |", "| --- | ---: |"])
    for row in rolling_summary.itertuples(index=False):
        lines.append(f"| {row.bucket} | {int(row.count)} |")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync I-STOCK-STRONG-RSI-V01 shadow outputs into an operational DB.")
    ap.add_argument("--source-db", default=str(DEFAULT_SOURCE_DB))
    ap.add_argument("--asof", default=None)
    ap.add_argument("--out-db", default=str(DEFAULT_OUT_DB))
    ap.add_argument("--outdir", default=str(DEFAULT_OUT_DIR))
    args = ap.parse_args()

    asof, holdings, features, nav, backtest_summary = _load_source(Path(args.source_db), args.asof)
    model_meta, score_schema = _build_meta(asof)
    latest, history, summary = _build_candidate_tables(asof, holdings, features)
    rolling_latest, rolling_summary = _build_rolling_watchlist(asof, history)
    report = _write_outputs(
        Path(args.out_db),
        Path(args.outdir),
        asof,
        model_meta,
        score_schema,
        latest,
        history,
        summary,
        rolling_latest,
        rolling_summary,
        nav,
        backtest_summary,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "model_code": MODEL_CODE,
                "asof": asof,
                "latest_rows": int(len(latest)),
                "history_rows": int(len(history)),
                "rolling_rows": int(len(rolling_latest)),
                "out_db": str(Path(args.out_db)),
                "report": str(report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
