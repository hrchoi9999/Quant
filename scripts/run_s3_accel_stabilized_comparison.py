from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"
HISTORICAL_MCAP_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger_backtest_historical_mcap\historical_mcap_signal_dates.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s3_accel_stabilized"
START_DATE = pd.Timestamp("2024-01-31")
FORWARD_WINDOWS = {"1M": 21, "3M": 63}
MODEL_CODE = "S3"

S3_RULE = {
    "ma_gap_min": 0.60,
    "vol_ratio_min": 2.30,
    "mcap_max": 5_000_000_000_000.0,
    "fund_accel_min": 0.55,
    "mom20_min": 0.10,
}

STABLE_RULE = {
    "buffer_slots": 4,
    "max_replacements": 4,
    "min_holding_periods": 3,
    "entry_score_advantage": 0.015,
    "force_add_top_rank": 10,
}


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def load_run_id() -> str:
    df = read_sql(
        QS_DB,
        """
        SELECT published_run_id
        FROM pub_model_current
        WHERE model_code='S3'
        """,
    )
    if df.empty:
        raise RuntimeError("published_run_id not found for S3")
    return str(df.iloc[0]["published_run_id"])


def load_baseline_holdings(run_id: str) -> pd.DataFrame:
    df = read_sql(
        QS_DETAIL_DB,
        """
        SELECT date, ticker, rank_no, weight, score
        FROM run_holdings_history
        WHERE run_id=?
        ORDER BY date, rank_no, ticker
        """,
        params=(run_id,),
        parse_dates=["date"],
    )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in ["rank_no", "weight", "score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[df["date"] >= START_DATE].copy()


def load_universe() -> pd.DataFrame:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["mcap"] = pd.to_numeric(df.get("mcap"), errors="coerce")
    cols = [c for c in ["ticker", "name", "market", "mcap"] if c in df.columns]
    return df[cols].copy()


def load_historical_mcap() -> pd.DataFrame:
    df = pd.read_csv(HISTORICAL_MCAP_CSV, dtype={"ticker": str}, parse_dates=["date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["mcap"] = pd.to_numeric(df["mcap"], errors="coerce")
    return df[["date", "ticker", "mcap"]].drop_duplicates(["date", "ticker"])


def load_price_and_forward_maps() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[pd.Timestamp, pd.Timestamp]]]:
    px = read_sql(
        PRICE_DB,
        "SELECT ticker, date, close FROM prices_daily WHERE close IS NOT NULL",
        parse_dates=["date"],
    )
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    wide = px.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
    returns = wide.pct_change().fillna(0.0)
    dates = [pd.Timestamp(d) for d in wide.index]
    end_maps = {
        label: {dates[i]: dates[i + step] for i in range(len(dates) - step)}
        for label, step in FORWARD_WINDOWS.items()
    }
    return wide, returns, end_maps


def load_price_features() -> pd.DataFrame:
    df = read_sql(
        S3_DB,
        """
        SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope
        FROM s3_price_features_daily
        """,
        parse_dates=["date"],
    )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in ["close", "vol_ratio_20", "mom20", "ma60", "ma120", "ma60_slope"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["breakout60"] = pd.to_numeric(df["breakout60"], errors="coerce").fillna(0.0)
    df["trend_up"] = ((df["ma60"] > df["ma120"]) & (df["ma60_slope"] > 0)).astype(int)
    df["ma_gap_60"] = df["close"] / df["ma60"] - 1.0
    return df


def load_s3_fund_features() -> pd.DataFrame:
    df = read_sql(
        S3_DB,
        """
        SELECT ticker, date, available_from, growth_score, fund_accel_score
        FROM s3_fund_features_monthly
        """,
        parse_dates=["date", "available_from"],
    )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["growth_score"] = pd.to_numeric(df["growth_score"], errors="coerce")
    df["fund_accel_score"] = pd.to_numeric(df["fund_accel_score"], errors="coerce")
    return df


def latest_snapshot(df: pd.DataFrame, asof: pd.Timestamp, date_col: str = "date") -> pd.DataFrame:
    snap = df[df[date_col] <= asof].copy()
    if snap.empty:
        return snap
    return snap.sort_values(["ticker", date_col]).groupby("ticker", as_index=False).tail(1)


def build_candidates(
    asof: pd.Timestamp,
    universe: pd.DataFrame,
    price_feat: pd.DataFrame,
    fund_feat: pd.DataFrame,
    historical_mcap: pd.DataFrame,
) -> pd.DataFrame:
    px_snap = price_feat[price_feat["date"] == asof].copy()
    if px_snap.empty:
        return pd.DataFrame()
    fund_snap = latest_snapshot(fund_feat, asof, "available_from")
    mcap_snap = historical_mcap[historical_mcap["date"] == asof][["ticker", "mcap"]].copy()

    snap = (
        universe.drop(columns=["mcap"], errors="ignore")
        .merge(px_snap, on="ticker", how="left")
        .merge(fund_snap[["ticker", "growth_score", "fund_accel_score"]], on="ticker", how="left")
        .merge(mcap_snap, on="ticker", how="left")
    )
    snap["mom20_pct"] = snap["mom20"].rank(pct=True)
    snap["vol_ratio_pct"] = snap["vol_ratio_20"].rank(pct=True)
    snap["fund_level_pct"] = snap["growth_score"].rank(pct=True)
    snap["fund_accel_pct"] = snap["fund_accel_score"].rank(pct=True)
    snap["base_score"] = (
        0.30 * snap["fund_level_pct"].fillna(0)
        + 0.20 * snap["fund_accel_pct"].fillna(0)
        + 0.25 * snap["mom20_pct"].fillna(0)
        + 0.10 * snap["vol_ratio_pct"].fillna(0)
        + 0.05 * snap["breakout60"].fillna(0)
        + 0.10 * snap["trend_up"].fillna(0)
    )
    snap["orig_accel_strength"] = snap["fund_accel_pct"].fillna(0)
    snap["accel_strong"] = (snap["fund_accel_pct"].fillna(0) >= 0.70).astype(int)
    snap["accel_weak"] = (snap["fund_accel_pct"].fillna(0) < 0.30).astype(int)
    snap["overheat"] = (
        (snap["ma_gap_60"] >= S3_RULE["ma_gap_min"])
        & (snap["vol_ratio_20"] >= S3_RULE["vol_ratio_min"])
        & (snap["mcap"] <= S3_RULE["mcap_max"])
        & (snap["fund_accel_score"] >= S3_RULE["fund_accel_min"])
        & (snap["mom20"] >= S3_RULE["mom20_min"])
    ).astype(int)
    snap["adj_score"] = (
        snap["base_score"].fillna(0)
        + 0.05 * snap["orig_accel_strength"]
        + 0.02 * snap["accel_strong"]
        - 0.10 * snap["overheat"] * snap["accel_weak"]
    )
    snap = snap.sort_values(["adj_score", "base_score", "ticker"], ascending=[False, False, True]).reset_index(drop=True)
    snap["adj_rank"] = np.arange(1, len(snap) + 1)
    return snap


def make_portfolio_rows(
    dt: pd.Timestamp,
    tickers: list[str],
    score_map: dict[str, float],
    source: str,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["date", "ticker", "rank_no", "weight", "score", "holding_source"])
    weight = 1.0 / len(tickers)
    return pd.DataFrame(
        {
            "date": dt,
            "ticker": tickers,
            "rank_no": list(range(1, len(tickers) + 1)),
            "weight": weight,
            "score": [score_map.get(t, np.nan) for t in tickers],
            "holding_source": source,
        }
    )


def build_orig_penalty_holdings(
    dt: pd.Timestamp,
    baseline: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    chosen = candidates.head(len(baseline)).copy()
    score_map = dict(zip(candidates["ticker"], candidates["adj_score"]))
    return make_portfolio_rows(dt, chosen["ticker"].tolist(), score_map, "orig_penalty_aux")


def build_stable_holdings(
    dt: pd.Timestamp,
    target_n: int,
    candidates: pd.DataFrame,
    prev_holdings: list[str] | None,
    holding_age: dict[str, int],
) -> tuple[pd.DataFrame, dict[str, int], pd.DataFrame]:
    if prev_holdings is None:
        chosen = candidates.head(target_n).copy()
        new_age = {ticker: 1 for ticker in chosen["ticker"].tolist()}
        reasons = chosen.assign(
            action="initial_seed",
            from_rank=np.nan,
            to_rank=chosen["adj_rank"],
            score_advantage=np.nan,
        )[["ticker", "action", "from_rank", "to_rank", "score_advantage"]]
        score_map = dict(zip(candidates["ticker"], candidates["adj_score"]))
        holdings = make_portfolio_rows(dt, chosen["ticker"].tolist(), score_map, "orig_penalty_stable")
        return holdings, new_age, reasons

    score_map = dict(zip(candidates["ticker"], candidates["adj_score"]))
    rank_map = dict(zip(candidates["ticker"], candidates["adj_rank"]))
    current = [ticker for ticker in prev_holdings if ticker in score_map]
    if len(current) < target_n:
        refill = [t for t in candidates["ticker"].tolist() if t not in set(current)]
        current.extend(refill[: target_n - len(current)])

    desired = candidates.head(target_n + STABLE_RULE["buffer_slots"]).copy()
    desired_set = set(desired["ticker"].tolist())
    strict_top_set = set(candidates.head(target_n)["ticker"].tolist())
    current_scores = pd.DataFrame({"ticker": current})
    current_scores["adj_rank"] = current_scores["ticker"].map(rank_map)
    current_scores["adj_score"] = current_scores["ticker"].map(score_map)
    current_scores["age"] = current_scores["ticker"].map(lambda t: holding_age.get(t, 1))

    forced_drop_mask = (
        (~current_scores["ticker"].isin(desired_set))
        & (current_scores["age"] >= STABLE_RULE["min_holding_periods"])
    )
    forced_drop = current_scores[forced_drop_mask].sort_values(["adj_rank", "adj_score"], ascending=[False, True]).copy()

    entrants = candidates[~candidates["ticker"].isin(current)].copy()
    entrants["score_advantage"] = entrants["adj_score"] - current_scores["adj_score"].min()
    entrant_mask = (
        ((entrants["adj_rank"] <= STABLE_RULE["force_add_top_rank"]) | entrants["ticker"].isin(strict_top_set))
        & (entrants["score_advantage"] >= STABLE_RULE["entry_score_advantage"])
    )
    entrants = entrants[entrant_mask].sort_values(["adj_rank", "adj_score"], ascending=[True, False]).copy()

    max_replace = min(
        STABLE_RULE["max_replacements"],
        len(forced_drop),
        len(entrants),
    )
    drop_candidates = forced_drop.head(max_replace).copy()
    add_candidates = entrants.head(max_replace).copy()

    next_holdings = [t for t in current if t not in set(drop_candidates["ticker"])]
    next_holdings.extend(add_candidates["ticker"].tolist())

    if len(next_holdings) < target_n:
        fill = [
            t for t in candidates["ticker"].tolist()
            if t not in set(next_holdings)
        ]
        next_holdings.extend(fill[: target_n - len(next_holdings)])
    else:
        next_holdings = next_holdings[:target_n]

    next_ranked = (
        pd.DataFrame({"ticker": next_holdings})
        .assign(adj_rank=lambda d: d["ticker"].map(rank_map), adj_score=lambda d: d["ticker"].map(score_map))
        .sort_values(["adj_rank", "adj_score", "ticker"], ascending=[True, False, True])
    )
    next_holdings = next_ranked["ticker"].tolist()

    next_age: dict[str, int] = {}
    for ticker in next_holdings:
        if ticker in current and ticker not in set(drop_candidates["ticker"]):
            next_age[ticker] = holding_age.get(ticker, 1) + 1
        else:
            next_age[ticker] = 1

    reason_rows = []
    for row in drop_candidates.itertuples(index=False):
        reason_rows.append(
            {
                "ticker": row.ticker,
                "action": "drop_outside_buffer",
                "from_rank": row.adj_rank,
                "to_rank": np.nan,
                "score_advantage": np.nan,
            }
        )
    for row in add_candidates.itertuples(index=False):
        reason_rows.append(
            {
                "ticker": row.ticker,
                "action": "add_high_accel_advantage",
                "from_rank": np.nan,
                "to_rank": row.adj_rank,
                "score_advantage": row.score_advantage,
            }
        )
    reasons = pd.DataFrame(reason_rows)
    score_map = dict(zip(candidates["ticker"], candidates["adj_score"]))
    holdings = make_portfolio_rows(dt, next_holdings, score_map, "orig_penalty_stable")
    return holdings, next_age, reasons


def simulate_variant_nav(variant_holdings: pd.DataFrame, returns_wide: pd.DataFrame) -> pd.DataFrame:
    if variant_holdings.empty:
        return pd.DataFrame()
    rebalance_dates = sorted(pd.to_datetime(variant_holdings["date"].dropna().unique()))
    nav = 1.0
    rows = [{"date": rebalance_dates[0], "nav": nav}]
    groups = {pd.Timestamp(d): g.copy() for d, g in variant_holdings.groupby("date")}
    for i, start in enumerate(rebalance_dates):
        end = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else returns_wide.index.max()
        held = groups[start]
        tickers = held["ticker"].tolist()
        weights = held.set_index("ticker")["weight"]
        period = returns_wide.loc[(returns_wide.index > start) & (returns_wide.index <= end), tickers]
        if period.empty:
            continue
        for day, day_ret in period.iterrows():
            nav *= 1.0 + float((day_ret.reindex(weights.index).fillna(0.0) * weights).sum())
            rows.append({"date": day, "nav": nav})
    return pd.DataFrame(rows)


def compute_perf(nav_df: pd.DataFrame, variant: str) -> list[dict[str, object]]:
    if nav_df.empty:
        return []
    nav_df = nav_df.sort_values("date").copy()
    nav_df["ret"] = nav_df["nav"].pct_change()
    windows = {
        "full_history": START_DATE,
        "since_2025": pd.Timestamp("2025-01-01"),
        "since_2026": pd.Timestamp("2026-01-01"),
    }
    rows = []
    for period, start_dt in windows.items():
        sub = nav_df[nav_df["date"] >= start_dt].copy()
        if len(sub) < 2:
            continue
        years = max((sub["date"].iloc[-1] - sub["date"].iloc[0]).days / 365.25, 1 / 252)
        total_return = float(sub["nav"].iloc[-1] / sub["nav"].iloc[0] - 1.0)
        cagr = float((sub["nav"].iloc[-1] / sub["nav"].iloc[0]) ** (1.0 / years) - 1.0)
        dd = sub["nav"] / sub["nav"].cummax() - 1.0
        vol = float(sub["ret"].std() * np.sqrt(252)) if sub["ret"].notna().sum() > 1 else np.nan
        sharpe = float((sub["ret"].mean() / sub["ret"].std()) * np.sqrt(252)) if sub["ret"].notna().sum() > 1 and sub["ret"].std() > 0 else np.nan
        rows.append(
            {
                "model_code": MODEL_CODE,
                "variant": variant,
                "period": period,
                "start_date": sub["date"].iloc[0],
                "end_date": sub["date"].iloc[-1],
                "total_return": total_return,
                "cagr": cagr,
                "mdd": float(dd.min()),
                "annual_vol": vol,
                "sharpe": sharpe,
            }
        )
    return rows


def turnover_summary(holdings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for variant, grp in holdings.groupby("variant"):
        prev: set[str] | None = None
        for dt, snap in grp.groupby("date", sort=True):
            curr = set(snap["ticker"].tolist())
            if prev is None:
                prev = curr
                continue
            adds = sorted(curr - prev)
            drops = sorted(prev - curr)
            rows.append(
                {
                    "model_code": MODEL_CODE,
                    "variant": variant,
                    "date": pd.Timestamp(dt),
                    "n_add": len(adds),
                    "n_drop": len(drops),
                    "turnover_ratio": len(adds) / max(len(curr), 1),
                }
            )
            prev = curr
    detail = pd.DataFrame(rows)
    summary = (
        detail.groupby(["model_code", "variant"], dropna=False)
        .agg(
            avg_add_count=("n_add", "mean"),
            avg_drop_count=("n_drop", "mean"),
            avg_turnover_ratio=("turnover_ratio", "mean"),
            median_turnover_ratio=("turnover_ratio", "median"),
            max_turnover_ratio=("turnover_ratio", "max"),
        )
        .reset_index()
    )
    return detail, summary


def new_entry_quality(
    holdings: pd.DataFrame,
    price_wide: pd.DataFrame,
    end_maps: dict[str, dict[pd.Timestamp, pd.Timestamp]],
) -> pd.DataFrame:
    rows = []
    for variant, grp in holdings.groupby("variant"):
        prev: set[str] | None = None
        for dt, snap in grp.groupby("date", sort=True):
            curr = set(snap["ticker"].tolist())
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
                    rows.append(
                        {
                            "model_code": MODEL_CODE,
                            "variant": variant,
                            "entry_date": pd.Timestamp(dt),
                            "ticker": ticker,
                            "horizon": horizon,
                            "end_date": end_date,
                            "forward_return": float(end_close / entry_close - 1.0),
                        }
                    )
            prev = curr
    detail = pd.DataFrame(rows)
    return (
        detail.groupby(["model_code", "variant", "horizon"], dropna=False)
        .agg(
            n_entries=("ticker", "size"),
            avg_forward_return=("forward_return", "mean"),
            median_forward_return=("forward_return", "median"),
            winner_rate=("forward_return", lambda s: float((s > 0).mean())),
            loser_rate=("forward_return", lambda s: float((s <= 0).mean())),
        )
        .reset_index()
    )


def overlap_summary(holdings: pd.DataFrame) -> pd.DataFrame:
    base = holdings[holdings["variant"] == "baseline"]
    rows = []
    for variant in [v for v in holdings["variant"].dropna().unique() if v != "baseline"]:
        cmp = holdings[holdings["variant"] == variant]
        for dt in sorted(set(base["date"]) & set(cmp["date"])):
            b = set(base.loc[base["date"] == dt, "ticker"])
            c = set(cmp.loc[cmp["date"] == dt, "ticker"])
            rows.append(
                {
                    "model_code": MODEL_CODE,
                    "variant": variant,
                    "date": dt,
                    "overlap_ratio": len(b & c) / max(len(b | c), 1),
                }
            )
    detail = pd.DataFrame(rows)
    return detail.groupby(["model_code", "variant"], dropna=False).agg(
        avg_overlap_ratio=("overlap_ratio", "mean"),
        min_overlap_ratio=("overlap_ratio", "min"),
    ).reset_index()


def build_markdown(
    headline: pd.DataFrame,
    perf: pd.DataFrame,
    turnover_summary_df: pd.DataFrame,
    quality: pd.DataFrame,
    overlap: pd.DataFrame,
    stable_reason_summary: pd.DataFrame,
) -> str:
    lines = [
        "# S3 Accel Stabilized Comparison",
        "",
        "## Scope",
        "- model: `S3`",
        f"- window start: `{START_DATE.date().isoformat()}`",
        "- compared variants:",
        "  - `baseline`: current published S3",
        "  - `orig_penalty_aux`: original accel high-turnover branch",
        "  - `orig_penalty_stable`: stabilized branch with buffer / replacement cap / minimum hold",
        "",
        "## Stable Rules",
        f"- buffer slots: `{STABLE_RULE['buffer_slots']}`",
        f"- weekly max replacements: `{STABLE_RULE['max_replacements']}`",
        f"- minimum holding periods: `{STABLE_RULE['min_holding_periods']}`",
        f"- minimum entry score advantage: `{STABLE_RULE['entry_score_advantage']:.3f}`",
        f"- forced-add rank threshold: top `{STABLE_RULE['force_add_top_rank']}`",
        "",
    ]
    lines.extend([
        "## Headline Comparison",
        "| Variant | Total Return | CAGR | MDD | Sharpe | Avg Turnover | New Entry 1M | Winner Rate 1M | Avg Overlap |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in headline.itertuples(index=False):
        lines.append(
            f"| {row.variant} | {row.total_return:.2%} | {row.cagr:.2%} | {row.mdd:.2%} | "
            f"{('-' if pd.isna(row.sharpe) else f'{row.sharpe:.2f}')} | {row.avg_turnover_ratio:.2%} | "
            f"{row.avg_forward_return_1m:.2%} | {row.winner_rate_1m:.2%} | {row.avg_overlap_ratio:.2%} |"
        )
    lines.append("")
    lines.extend([
        "## Performance Windows",
        "| Variant | Period | Total Return | CAGR | MDD | Annual Vol | Sharpe |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in perf.sort_values(["variant", "period"]).itertuples(index=False):
        lines.append(
            f"| {row.variant} | {row.period} | {row.total_return:.2%} | {row.cagr:.2%} | "
            f"{row.mdd:.2%} | {('-' if pd.isna(row.annual_vol) else f'{row.annual_vol:.2%}')} | "
            f"{('-' if pd.isna(row.sharpe) else f'{row.sharpe:.2f}')} |"
        )
    lines.append("")
    if not stable_reason_summary.empty:
        lines.extend([
            "## Stable Rebalance Reasons",
            "| Action | Count | Avg Score Advantage |",
            "|---|---:|---:|",
        ])
        for row in stable_reason_summary.itertuples(index=False):
            lines.append(
                f"| {row.action} | {int(row.n_rows)} | {('-' if pd.isna(row.avg_score_advantage) else f'{row.avg_score_advantage:.4f}')} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    run_id = load_run_id()
    baseline = load_baseline_holdings(run_id)
    universe = load_universe()
    historical_mcap = load_historical_mcap()
    price_wide, returns_wide, end_maps = load_price_and_forward_maps()
    price_feat = load_price_features()
    fund_feat = load_s3_fund_features()

    baseline_rows = []
    penalty_rows = []
    stable_rows = []
    stable_reason_frames = []
    prev_holdings: list[str] | None = None
    holding_age: dict[str, int] = {}

    for dt, hist in baseline.groupby("date", sort=True):
        hist = hist.copy().sort_values(["rank_no", "ticker"]).reset_index(drop=True)
        hist["weight"] = hist["weight"].fillna(1.0 / len(hist) if len(hist) else np.nan)
        hist["variant"] = "baseline"
        hist["holding_source"] = "baseline_original"
        hist["model_code"] = MODEL_CODE
        baseline_rows.append(hist[["date", "ticker", "rank_no", "weight", "score", "variant", "holding_source", "model_code"]])

        candidates = build_candidates(
            asof=pd.Timestamp(dt),
            universe=universe,
            price_feat=price_feat,
            fund_feat=fund_feat,
            historical_mcap=historical_mcap,
        )
        if candidates.empty:
            continue

        penalty_hold = build_orig_penalty_holdings(pd.Timestamp(dt), hist, candidates)
        penalty_hold["variant"] = "orig_penalty_aux"
        penalty_hold["model_code"] = MODEL_CODE
        penalty_rows.append(penalty_hold[["date", "ticker", "rank_no", "weight", "score", "variant", "holding_source", "model_code"]])

        stable_hold, holding_age, stable_reasons = build_stable_holdings(
            dt=pd.Timestamp(dt),
            target_n=len(hist),
            candidates=candidates,
            prev_holdings=prev_holdings,
            holding_age=holding_age,
        )
        stable_hold["variant"] = "orig_penalty_stable"
        stable_hold["model_code"] = MODEL_CODE
        stable_rows.append(stable_hold[["date", "ticker", "rank_no", "weight", "score", "variant", "holding_source", "model_code"]])
        if not stable_reasons.empty:
            stable_reasons["date"] = pd.Timestamp(dt)
            stable_reason_frames.append(stable_reasons)
        prev_holdings = stable_hold.sort_values("rank_no")["ticker"].tolist()

    holdings = pd.concat(
        [
            pd.concat(baseline_rows, ignore_index=True),
            pd.concat(penalty_rows, ignore_index=True),
            pd.concat(stable_rows, ignore_index=True),
        ],
        ignore_index=True,
    )
    stable_reasons = pd.concat(stable_reason_frames, ignore_index=True) if stable_reason_frames else pd.DataFrame()

    perf_rows: list[dict[str, object]] = []
    for variant, grp in holdings.groupby("variant"):
        nav = simulate_variant_nav(grp[["date", "ticker", "rank_no", "weight", "score", "holding_source"]], returns_wide)
        perf_rows.extend(compute_perf(nav, variant))
    perf = pd.DataFrame(perf_rows)

    turnover_detail, turnover_df = turnover_summary(holdings[["variant", "date", "ticker"]].drop_duplicates())
    quality = new_entry_quality(holdings[["variant", "date", "ticker"]].drop_duplicates(), price_wide, end_maps)
    overlap = overlap_summary(holdings[["variant", "date", "ticker"]].drop_duplicates())

    headline = (
        perf[perf["period"] == "full_history"][["variant", "total_return", "cagr", "mdd", "sharpe"]]
        .merge(turnover_df[["variant", "avg_turnover_ratio"]], on="variant", how="left")
        .merge(
            quality[quality["horizon"] == "1M"][["variant", "avg_forward_return", "winner_rate"]],
            on="variant",
            how="left",
        )
        .merge(overlap[["variant", "avg_overlap_ratio"]], on="variant", how="left")
        .rename(columns={"avg_forward_return": "avg_forward_return_1m", "winner_rate": "winner_rate_1m"})
    )

    stable_reason_summary = pd.DataFrame()
    if not stable_reasons.empty:
        stable_reason_summary = (
            stable_reasons.groupby("action", dropna=False)
            .agg(
                n_rows=("ticker", "size"),
                avg_score_advantage=("score_advantage", "mean"),
            )
            .reset_index()
            .sort_values("n_rows", ascending=False)
        )

    headline.to_csv(OUTDIR / "s3_accel_stabilized_headline.csv", index=False)
    perf.to_csv(OUTDIR / "s3_accel_stabilized_performance_summary.csv", index=False)
    turnover_detail.to_csv(OUTDIR / "s3_accel_stabilized_turnover_detail.csv", index=False)
    turnover_df.to_csv(OUTDIR / "s3_accel_stabilized_turnover_summary.csv", index=False)
    quality.to_csv(OUTDIR / "s3_accel_stabilized_new_entry_quality.csv", index=False)
    overlap.to_csv(OUTDIR / "s3_accel_stabilized_overlap_summary.csv", index=False)
    holdings.to_csv(OUTDIR / "s3_accel_stabilized_holdings_history.csv", index=False)
    if not stable_reasons.empty:
        stable_reasons.to_csv(OUTDIR / "s3_accel_stabilized_rebalance_reasons.csv", index=False)
    if not stable_reason_summary.empty:
        stable_reason_summary.to_csv(OUTDIR / "s3_accel_stabilized_rebalance_reason_summary.csv", index=False)

    report = build_markdown(headline, perf, turnover_df, quality, overlap, stable_reason_summary)
    (OUTDIR / "s3_accel_stabilized_comparison.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
