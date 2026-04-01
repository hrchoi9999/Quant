from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
DB_PATH = PROJECT_ROOT / r"data\db\tseries_operational.db"
PRICE_DB_PATH = PROJECT_ROOT / r"data\db\price.db"
T_SERIES_BUCKETS = ("confirmed", "near", "observe")
PERFORMANCE_BUCKETS = {
    "T-STOCK-V01": ("confirmed", "near"),
    "T-ETF-V01": ("historical_stage2", "historical_stage1", "confirmed", "near"),
}
BUCKET_MAP = {
    "historical_stage2": "confirmed",
    "historical_stage1": "near",
}
PERIOD_SPECS = (
    ("3M", 3),
    ("6M", 6),
    ("1Y", 12),
    ("2Y", 24),
    ("3Y", 36),
    ("5Y", 60),
)
ANNUALIZATION_FACTOR = {
    "T-STOCK-V01": 52.0,
    "T-ETF-V01": 12.0,
}


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _latest_asof(con: sqlite3.Connection, model_code: str) -> str | None:
    row = con.execute(
        "SELECT MAX(asof_date) AS asof_date FROM ts_runs WHERE model_code = ?",
        (model_code,),
    ).fetchone()
    return None if row is None else row["asof_date"]


def load_model_meta(con: sqlite3.Connection, model_code: str) -> dict | None:
    row = con.execute(
        """
        SELECT model_code, display_name, asset_scope, stage_structure, version_label, status, notes
        FROM ts_meta_models
        WHERE model_code = ?
        """,
        (model_code,),
    ).fetchone()
    return None if row is None else dict(row)


def load_current_profile(con: sqlite3.Connection, model_code: str, asof_date: str | None = None) -> dict | None:
    resolved_asof = asof_date or _latest_asof(con, model_code)
    if not resolved_asof:
        return None
    row = con.execute(
        """
        SELECT profile_id, profile_code, asof_date, stage1_threshold, stage2_confirmed_th,
               stage2_near_th, risk_filter_version, notes
        FROM ts_threshold_profiles
        WHERE model_code = ? AND asof_date = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (model_code, resolved_asof),
    ).fetchone()
    return None if row is None else dict(row)


def load_latest_candidates(con: sqlite3.Connection, model_code: str, asof_date: str | None = None) -> pd.DataFrame:
    resolved_asof = asof_date or _latest_asof(con, model_code)
    if not resolved_asof:
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT model_code, asof_date, candidate_bucket, ticker, name, market, asset_class,
               group_key, theme_bucket, theme_name_kr, is_s2_overlap,
               stage1_prob, stage2_prob, mcap, liquidity_20d_value,
               risk_filtered_flag, source_run_id, details_json
        FROM ts_candidates_latest
        WHERE model_code = ? AND asof_date = ?
        ORDER BY
            CASE candidate_bucket
                WHEN 'confirmed' THEN 1
                WHEN 'near' THEN 2
                WHEN 'observe' THEN 3
                ELSE 9
            END,
            COALESCE(stage2_prob, 0) DESC,
            COALESCE(stage1_prob, 0) DESC,
            ticker
        """,
        con,
        params=[model_code, resolved_asof],
    )


def load_shadow_summary(con: sqlite3.Connection, model_code: str, asof_date: str | None = None) -> pd.DataFrame:
    resolved_asof = asof_date or _latest_asof(con, model_code)
    if not resolved_asof:
        return pd.DataFrame()
    return pd.read_sql_query(
        """
        SELECT model_code, asof_date, candidate_bucket, horizon, obs_n,
               t10_hit_rate, t3_hit_rate, avg_stage1_prob, avg_stage2_prob
        FROM ts_shadow_tracking_summary
        WHERE model_code = ? AND asof_date = ?
        ORDER BY candidate_bucket, horizon
        """,
        con,
        params=[model_code, resolved_asof],
    )


def load_run_meta(con: sqlite3.Connection, model_code: str, asof_date: str | None = None) -> dict | None:
    resolved_asof = asof_date or _latest_asof(con, model_code)
    if not resolved_asof:
        return None
    row = con.execute(
        """
        SELECT ts_run_id, model_code, profile_id, asof_date, refresh_kind, status,
               source_snapshot_ref, started_at, finished_at, outdir, notes
        FROM ts_runs
        WHERE model_code = ? AND asof_date = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (model_code, resolved_asof),
    ).fetchone()
    return None if row is None else dict(row)


def load_candidate_history(con: sqlite3.Connection, model_code: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT model_code, signal_date, horizon, candidate_bucket, ticker, name, market,
               asset_class, group_key, theme_bucket, theme_name_kr, stage1_prob, stage2_prob
        FROM ts_candidates_history
        WHERE model_code = ?
        ORDER BY signal_date, candidate_bucket, ticker
        """,
        con,
        params=[model_code],
    )


def _normalize_history_bucket(bucket: str) -> str:
    return BUCKET_MAP.get(str(bucket or "").strip(), str(bucket or "").strip())


def _load_prices(tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    placeholders = ",".join(["?"] * len(tickers))
    with sqlite3.connect(str(PRICE_DB_PATH)) as price_con:
        prices = pd.read_sql_query(
            f"""
            SELECT ticker, date, close
            FROM prices_daily
            WHERE ticker IN ({placeholders}) AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            price_con,
            params=tickers,
        )
    if prices.empty:
        return prices
    prices["ticker"] = prices["ticker"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"])
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    return prices.dropna(subset=["close"]).sort_values(["ticker", "date"]).reset_index(drop=True)


def _build_portfolio_nav(history: pd.DataFrame, model_code: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    buckets = set(PERFORMANCE_BUCKETS.get(model_code, ("confirmed", "near")))
    work = history.copy()
    work["ticker"] = work["ticker"].astype(str).str.zfill(6)
    work["mapped_bucket"] = work["candidate_bucket"].map(_normalize_history_bucket)
    work = work.loc[
        work["candidate_bucket"].isin(buckets) | work["mapped_bucket"].isin({"confirmed", "near"})
    ]
    if work.empty:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    work["signal_date"] = pd.to_datetime(work["signal_date"])
    bucket_priority = {"confirmed": 0, "near": 1, "observe": 2}
    work["bucket_rank"] = work["mapped_bucket"].map(lambda v: bucket_priority.get(v, 9))
    work = (
        work.sort_values(["signal_date", "ticker", "bucket_rank"])
        .drop_duplicates(subset=["signal_date", "ticker"], keep="first")
        .reset_index(drop=True)
    )

    signal_dates = sorted(work["signal_date"].dropna().unique())
    if len(signal_dates) < 2:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    periods = pd.DataFrame(
        {
            "signal_date": signal_dates[:-1],
            "next_signal_date": signal_dates[1:],
        }
    )
    positions = work[["signal_date", "ticker"]].drop_duplicates().merge(periods, on="signal_date", how="inner")
    if positions.empty:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    prices = _load_prices(sorted(positions["ticker"].dropna().unique().tolist()))
    if prices.empty:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    matched_frames: list[pd.DataFrame] = []
    for ticker, ticker_positions in positions.groupby("ticker", sort=False):
        ticker_prices = prices.loc[prices["ticker"] == ticker, ["date", "close"]].copy()
        if ticker_prices.empty:
            continue
        ticker_prices = ticker_prices.sort_values("date").reset_index(drop=True)
        ticker_positions = ticker_positions.sort_values("signal_date").reset_index(drop=True)
        entry = pd.merge_asof(
            ticker_positions,
            ticker_prices.rename(columns={"date": "entry_price_date", "close": "entry_close"}),
            left_on="signal_date",
            right_on="entry_price_date",
            direction="backward",
        )
        exit_ = pd.merge_asof(
            ticker_positions.sort_values("next_signal_date").reset_index(drop=True),
            ticker_prices.rename(columns={"date": "exit_price_date", "close": "exit_close"}),
            left_on="next_signal_date",
            right_on="exit_price_date",
            direction="backward",
        )
        ticker_periods = entry[["signal_date", "next_signal_date", "ticker", "entry_close"]].copy()
        ticker_periods["exit_close"] = exit_["exit_close"].values
        matched_frames.append(ticker_periods)

    if not matched_frames:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    period_positions = pd.concat(matched_frames, ignore_index=True)
    period_positions = period_positions.dropna(subset=["entry_close", "exit_close"])
    period_positions = period_positions.loc[period_positions["entry_close"] > 0]
    if period_positions.empty:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    period_positions["period_return"] = (period_positions["exit_close"] / period_positions["entry_close"]) - 1.0
    period_returns = (
        period_positions.groupby(["signal_date", "next_signal_date"], as_index=False)
        .agg(period_return=("period_return", "mean"), basket_size=("ticker", "nunique"))
        .sort_values("next_signal_date")
        .reset_index(drop=True)
    )
    if period_returns.empty:
        return pd.DataFrame(columns=["date", "nav", "period_return", "basket_size"])

    nav_rows: list[dict[str, Any]] = [
        {
            "date": period_returns.iloc[0]["signal_date"],
            "nav": 1.0,
            "period_return": None,
            "basket_size": int(period_returns.iloc[0]["basket_size"]),
        }
    ]
    nav = 1.0
    for row in period_returns.itertuples():
        nav *= 1.0 + float(row.period_return)
        nav_rows.append(
            {
                "date": row.next_signal_date,
                "nav": nav,
                "period_return": float(row.period_return),
                "basket_size": int(row.basket_size),
            }
        )
    return pd.DataFrame(nav_rows).sort_values("date").reset_index(drop=True)


def _append_latest_mark_to_market(
    nav_df: pd.DataFrame,
    latest_candidates: pd.DataFrame,
    asof_date: str | None,
    model_code: str,
) -> pd.DataFrame:
    if nav_df.empty or latest_candidates.empty or not asof_date:
        return nav_df

    target_date = pd.Timestamp(asof_date)
    last_nav_date = pd.Timestamp(nav_df["date"].max())
    if target_date <= last_nav_date:
        return nav_df

    buckets = set(PERFORMANCE_BUCKETS.get(model_code, ("confirmed", "near")))
    current = latest_candidates.copy()
    current["mapped_bucket"] = current["candidate_bucket"].map(_normalize_history_bucket)
    current = current.loc[
        current["candidate_bucket"].isin(buckets) | current["mapped_bucket"].isin({"confirmed", "near"})
    ].copy()
    if current.empty:
        return nav_df

    current["ticker"] = current["ticker"].astype(str).str.zfill(6)
    basket_size = int(current["ticker"].drop_duplicates().nunique())
    if basket_size == 0:
        return nav_df

    extra = pd.DataFrame(
        [
            {
                "date": target_date,
                "nav": float(nav_df.iloc[-1]["nav"]),
                "period_return": 0.0,
                "basket_size": basket_size,
            }
        ]
    )
    return pd.concat([nav_df, extra], ignore_index=True).sort_values("date").reset_index(drop=True)


def _compute_period_metrics(nav_df: pd.DataFrame, annualization_factor: float) -> dict[str, Any] | None:
    if nav_df.empty or len(nav_df) < 2:
        return None
    work = nav_df.dropna(subset=["nav"]).copy()
    if len(work) < 2:
        return None
    start_nav = float(work.iloc[0]["nav"])
    end_nav = float(work.iloc[-1]["nav"])
    start_date = pd.Timestamp(work.iloc[0]["date"])
    end_date = pd.Timestamp(work.iloc[-1]["date"])
    days = max((end_date - start_date).days, 1)
    total_return = (end_nav / start_nav) - 1.0
    cagr = (end_nav / start_nav) ** (365.25 / days) - 1.0 if days > 0 else total_return
    drawdown = (work["nav"] / work["nav"].cummax()) - 1.0
    mdd = float(drawdown.min()) if not drawdown.empty else 0.0
    returns = work["nav"].pct_change().dropna()
    sharpe = None
    if not returns.empty:
        std = float(returns.std(ddof=0))
        if std > 0:
            sharpe = float(returns.mean() / std * (annualization_factor ** 0.5))
    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "total_return": round(float(total_return), 6),
        "cagr": round(float(cagr), 6),
        "mdd": round(float(mdd), 6),
        "sharpe": None if sharpe is None else round(float(sharpe), 6),
    }


def build_performance_summary(
    con: sqlite3.Connection,
    model_code: str,
    asof_date: str | None = None,
    latest_candidates: pd.DataFrame | None = None,
) -> dict[str, Any] | None:
    history = load_candidate_history(con, model_code)
    nav_df = _build_portfolio_nav(history, model_code)
    if latest_candidates is not None:
        nav_df = _append_latest_mark_to_market(nav_df, latest_candidates, asof_date, model_code)
    if nav_df.empty:
        return None

    annualization_factor = ANNUALIZATION_FACTOR.get(model_code, 52.0)
    end_date = pd.Timestamp(nav_df["date"].max())
    period_metrics: list[dict[str, Any]] = []
    period_map: dict[str, dict[str, Any]] = {}

    for label, months in PERIOD_SPECS:
        cutoff = end_date - pd.DateOffset(months=months)
        start_idx = nav_df["date"].searchsorted(cutoff, side="right") - 1
        if start_idx < 0:
            continue
        metric = _compute_period_metrics(nav_df.iloc[start_idx:].copy(), annualization_factor)
        if not metric:
            continue
        payload = {"period": label, **metric}
        period_metrics.append(payload)
        period_map[label] = payload

    full_metric = _compute_period_metrics(nav_df.copy(), annualization_factor)
    if full_metric:
        full_payload = {"period": "FULL", **full_metric}
        period_metrics.append(full_payload)
        period_map["FULL"] = full_payload

    if not period_metrics:
        return None

    primary_period = "1Y" if "1Y" in period_map else ("6M" if "6M" in period_map else "FULL")
    primary = period_map.get(primary_period, period_metrics[-1])
    asset_label = "stock" if model_code == "T-STOCK-V01" else "ETF"
    return {
        "headline_metrics": {
            "primary_period": primary_period,
            "display_metric": "cagr",
            "cagr": primary.get("cagr"),
            "total_return": primary.get("total_return"),
            "mdd": primary.get("mdd"),
            "sharpe": primary.get("sharpe"),
            "trailing_3m": period_map.get("3M"),
            "trailing_6m": period_map.get("6M"),
            "trailing_1y": period_map.get("1Y"),
            "reference_5y": period_map.get("5Y"),
            "reference_full": period_map.get("FULL"),
            "last_realized_date": end_date.strftime("%Y-%m-%d"),
        },
        "period_metrics": period_metrics,
        "performance_subject_name": f"T-series {asset_label} discovery basket",
        "performance_subject_type": "shadow_portfolio",
        "portfolio_generation_basis": (
            "Equal-weight basket of confirmed and near candidates, rebalanced at each signal date "
            "using historical candidate history, with the latest current candidate basket appended as a terminal asof marker when available."
        ),
    }


def build_snapshot(con: sqlite3.Connection, model_code: str, asof_date: str | None = None) -> dict:
    latest_asof = asof_date or _latest_asof(con, model_code)
    meta = load_model_meta(con, model_code)
    profile = load_current_profile(con, model_code, latest_asof)
    run_meta = load_run_meta(con, model_code, latest_asof)
    candidates = load_latest_candidates(con, model_code, latest_asof)
    shadow = load_shadow_summary(con, model_code, latest_asof)
    performance_summary = build_performance_summary(con, model_code, latest_asof, candidates)

    bucket_counts = {}
    if not candidates.empty:
        bucket_counts = candidates.groupby("candidate_bucket").size().sort_index().to_dict()

    top_by_bucket: dict[str, list[dict]] = {}
    if not candidates.empty:
        for bucket, frame in candidates.groupby("candidate_bucket", sort=False):
            cols = [
                "ticker",
                "name",
                "market",
                "theme_bucket",
                "theme_name_kr",
                "stage1_prob",
                "stage2_prob",
                "is_s2_overlap",
            ]
            keep = [c for c in cols if c in frame.columns]
            top_by_bucket[bucket] = frame[keep].head(10).to_dict(orient="records")

    shadow_rows = [] if shadow.empty else shadow.to_dict(orient="records")
    return {
        "model_code": model_code,
        "asof_date": latest_asof,
        "meta": meta,
        "profile": profile,
        "run": run_meta,
        "bucket_counts": bucket_counts,
        "top_by_bucket": top_by_bucket,
        "shadow_summary": shadow_rows,
        "performance_summary": performance_summary,
    }


def _print_snapshot(snapshot: dict) -> None:
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Read latest T-series operational snapshot")
    ap.add_argument("--model-code", required=True, choices=["T-STOCK-V01", "T-ETF-V01"])
    ap.add_argument("--asof")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    con = connect(Path(args.db))
    try:
        snapshot = build_snapshot(con, args.model_code, args.asof)
    finally:
        con.close()
    _print_snapshot(snapshot)


if __name__ == "__main__":
    main()
