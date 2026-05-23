from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"
HISTORICAL_MCAP_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger_backtest_historical_mcap\historical_mcap_signal_dates.csv"
S3_REPORT_DIR = PROJECT_ROOT / r"reports\backtest_s3_dev"
OUTDIR = PROJECT_ROOT / r"reports\backtest_s3_accel_v01"

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
DATE_TOKEN_RE = re.compile(r"(20\d{2}-\d{2}-\d{2}|20\d{6})")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run operational S3_ACCEL_V01 backtest.")
    ap.add_argument("--asof", required=True)
    ap.add_argument("--outdir", default=str(OUTDIR))
    return ap.parse_args()


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def _extract_last_yyyymmdd(text: str) -> str | None:
    normalized = [match.replace("-", "") for match in DATE_TOKEN_RE.findall(str(text))]
    return normalized[-1] if normalized else None


def _latest_path_lte(directory: Path, pattern: str, requested_token: str) -> Path:
    candidates: list[tuple[str, float, Path]] = []
    for path in directory.glob(pattern):
        token = _extract_last_yyyymmdd(path.stem)
        if token is None or token > requested_token:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((token, mtime, path))
    if not candidates:
        raise FileNotFoundError(f"no files matched {pattern} on or before {requested_token} in {directory}")
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def load_latest_s3_reports(asof: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    token = asof.replace("-", "")
    nav_path = _latest_path_lte(S3_REPORT_DIR, "s3_nav_hold_top20_*_*.csv", token)
    suffix = nav_path.name.replace("s3_nav_hold_top20_", "")
    holdings_path = S3_REPORT_DIR / f"s3_holdings_history_top20_{suffix}"
    if not holdings_path.exists():
        raise FileNotFoundError(f"missing paired holdings file for {nav_path.name}: {holdings_path}")
    nav = pd.read_csv(nav_path, parse_dates=["date"])
    holdings = pd.read_csv(holdings_path, dtype={"ticker": str}, parse_dates=["date"])
    holdings["ticker"] = holdings["ticker"].astype(str).str.zfill(6)
    return nav, holdings


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


def load_price_and_return_maps() -> tuple[pd.DataFrame, pd.DataFrame]:
    px = read_sql(
        PRICE_DB,
        "SELECT ticker, date, close FROM prices_daily WHERE close IS NOT NULL",
        parse_dates=["date"],
    )
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    wide = px.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
    returns = wide.pct_change().fillna(0.0)
    return wide, returns


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


def latest_snapshot(df: pd.DataFrame, asof: pd.Timestamp, date_col: str) -> pd.DataFrame:
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


def build_stable_holdings(
    dt: pd.Timestamp,
    target_n: int,
    candidates: pd.DataFrame,
    prev_holdings: list[str] | None,
    holding_age: dict[str, int],
) -> tuple[pd.DataFrame, dict[str, int]]:
    score_map = dict(zip(candidates["ticker"], candidates["adj_score"]))
    rank_map = dict(zip(candidates["ticker"], candidates["adj_rank"]))
    if prev_holdings is None:
        chosen = candidates.head(target_n).copy()
        next_age = {ticker: 1 for ticker in chosen["ticker"].tolist()}
        return chosen, next_age

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

    forced_drop = current_scores[
        (~current_scores["ticker"].isin(desired_set))
        & (current_scores["age"] >= STABLE_RULE["min_holding_periods"])
    ].sort_values(["adj_rank", "adj_score"], ascending=[False, True])

    entrants = candidates[~candidates["ticker"].isin(current)].copy()
    if current_scores.empty:
        current_floor = entrants["adj_score"].min() if not entrants.empty else 0.0
    else:
        current_floor = current_scores["adj_score"].min()
    entrants["score_advantage"] = entrants["adj_score"] - current_floor
    entrants = entrants[
        ((entrants["adj_rank"] <= STABLE_RULE["force_add_top_rank"]) | entrants["ticker"].isin(strict_top_set))
        & (entrants["score_advantage"] >= STABLE_RULE["entry_score_advantage"])
    ].sort_values(["adj_rank", "adj_score"], ascending=[True, False])

    max_replace = min(STABLE_RULE["max_replacements"], len(forced_drop), len(entrants))
    drop_candidates = forced_drop.head(max_replace).copy()
    add_candidates = entrants.head(max_replace).copy()

    next_holdings = [t for t in current if t not in set(drop_candidates["ticker"])]
    next_holdings.extend(add_candidates["ticker"].tolist())
    if len(next_holdings) < target_n:
        fill = [t for t in candidates["ticker"].tolist() if t not in set(next_holdings)]
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

    chosen = candidates[candidates["ticker"].isin(next_holdings)].copy()
    chosen["forced_order"] = chosen["ticker"].map({ticker: i for i, ticker in enumerate(next_holdings)})
    chosen = chosen.sort_values(["forced_order", "adj_rank", "ticker"]).drop(columns=["forced_order"])
    return chosen, next_age


def simulate_nav(holdings: pd.DataFrame, returns_wide: pd.DataFrame) -> pd.DataFrame:
    rebalance_dates = sorted(pd.to_datetime(holdings["date"].dropna().unique()))
    if not rebalance_dates:
        return pd.DataFrame(columns=["date", "nav"])
    nav = 1.0
    rows = [{"date": rebalance_dates[0], "nav": nav}]
    groups = {pd.Timestamp(d): g.copy() for d, g in holdings.groupby("date")}
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


def build_summary(nav_df: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    nav = nav_df.copy().sort_values("date")
    nav["ret"] = nav["nav"].pct_change().fillna(0.0)
    peak = nav["nav"].cummax()
    dd = nav["nav"] / peak - 1.0
    years = max((nav["date"].iloc[-1] - nav["date"].iloc[0]).days / 365.25, 1 / 252)
    total_return = float(nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1.0)
    cagr = float((nav["nav"].iloc[-1] / nav["nav"].iloc[0]) ** (1.0 / years) - 1.0)
    vol = float(nav["ret"].std(ddof=1) * np.sqrt(252)) if nav["ret"].notna().sum() > 1 else np.nan
    sharpe = (
        float((nav["ret"].mean() / nav["ret"].std(ddof=1)) * np.sqrt(252))
        if nav["ret"].notna().sum() > 1 and float(nav["ret"].std(ddof=1)) > 0
        else np.nan
    )
    rebalance_count = int(holdings["date"].nunique())
    return pd.DataFrame(
        [
            {
                "strategy": "S3_ACCEL_V01",
                "start": nav["date"].iloc[0].strftime("%Y-%m-%d"),
                "end": nav["date"].iloc[-1].strftime("%Y-%m-%d"),
                "cagr": cagr,
                "sharpe": sharpe,
                "mdd": float(dd.min()),
                "avg_daily_ret": float(nav["ret"].mean()),
                "vol_daily": float(nav["ret"].std(ddof=1)) if nav["ret"].notna().sum() > 1 else np.nan,
                "rebalance_count": rebalance_count,
                "top_n": int(holdings.groupby("date").size().median()),
                "buffer_slots": STABLE_RULE["buffer_slots"],
                "max_replacements": STABLE_RULE["max_replacements"],
                "min_holding_periods": STABLE_RULE["min_holding_periods"],
                "entry_score_advantage": STABLE_RULE["entry_score_advantage"],
                "force_add_top_rank": STABLE_RULE["force_add_top_rank"],
                "total_return": total_return,
                "final_nav": float(nav["nav"].iloc[-1]),
            }
        ]
    )


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    baseline_nav, baseline_holdings = load_latest_s3_reports(args.asof)
    universe = load_universe()
    historical_mcap = load_historical_mcap()
    _, returns_wide = load_price_and_return_maps()
    price_feat = load_price_features()
    fund_feat = load_s3_fund_features()

    hold_frames = []
    prev_holdings: list[str] | None = None
    holding_age: dict[str, int] = {}

    baseline_counts = baseline_holdings.groupby("date").size().to_dict()
    date_order = sorted(pd.to_datetime(d) for d in baseline_counts.keys())
    for dt in date_order:
        candidates = build_candidates(dt, universe, price_feat, fund_feat, historical_mcap)
        if candidates.empty:
            continue
        target_n = int(baseline_counts.get(dt, 20))
        chosen, holding_age = build_stable_holdings(dt, target_n, candidates, prev_holdings, holding_age)
        if chosen.empty:
            continue
        chosen = chosen.copy()
        chosen["date"] = pd.Timestamp(dt)
        chosen["weight"] = 1.0 / len(chosen)
        chosen["rank_no"] = np.arange(1, len(chosen) + 1)
        chosen["ticker"] = chosen["ticker"].astype(str).str.zfill(6)
        hold_frames.append(
            chosen[
                [
                    "date",
                    "ticker",
                    "name",
                    "market",
                    "mcap",
                    "adj_score",
                    "close",
                    "ma60",
                    "ma120",
                    "ma60_slope",
                    "mom20",
                    "vol_ratio_20",
                    "breakout60",
                    "growth_score",
                    "fund_accel_score",
                    "rank_no",
                    "weight",
                ]
            ].rename(columns={"adj_score": "s3_score"})
        )
        prev_holdings = chosen.sort_values("rank_no")["ticker"].tolist()

    holdings = pd.concat(hold_frames, ignore_index=True)
    nav = simulate_nav(holdings[["date", "ticker", "rank_no", "weight", "s3_score"]].rename(columns={"s3_score": "score"}), returns_wide)
    nav["date"] = pd.to_datetime(nav["date"])
    holdings["date"] = pd.to_datetime(holdings["date"])

    gate_map = baseline_nav.copy()
    gate_map["date"] = pd.to_datetime(gate_map["date"])
    if "gate_open" not in gate_map.columns:
        gate_map["gate_open"] = np.nan
    if "gate_breadth" not in gate_map.columns:
        gate_map["gate_breadth"] = np.nan
    gate_map = gate_map[["date", "gate_open", "gate_breadth"]].drop_duplicates("date")
    rebalance_meta = holdings.groupby("date").agg(holdings=("ticker", "size")).reset_index()
    nav = nav.merge(rebalance_meta, on="date", how="left").merge(gate_map, on="date", how="left")
    nav["holdings"] = nav["holdings"].ffill().fillna(0).astype(int)
    nav["cash_weight"] = 0.0
    nav["exposure"] = np.where(nav["holdings"] > 0, 1.0, 0.0)

    summary = build_summary(nav, holdings)
    end_token = args.asof.replace("-", "")
    start_token = holdings["date"].min().strftime("%Y%m%d")
    nav_name = f"s3_accel_v01_nav_{start_token}_{end_token}.csv"
    holdings_name = f"s3_accel_v01_holdings_{start_token}_{end_token}.csv"
    last_name = f"s3_accel_v01_last_{end_token}.csv"
    summary_name = f"s3_accel_v01_summary_{start_token}_{end_token}.csv"

    nav.to_csv(outdir / nav_name, index=False, encoding="utf-8-sig")
    holdings.sort_values(["date", "rank_no", "ticker"]).to_csv(outdir / holdings_name, index=False, encoding="utf-8-sig")
    holdings.loc[holdings["date"] == holdings["date"].max()].sort_values(["rank_no", "ticker"]).to_csv(
        outdir / last_name, index=False, encoding="utf-8-sig"
    )
    summary.to_csv(outdir / summary_name, index=False, encoding="utf-8-sig")
    print(f"[OK] S3_ACCEL_V01 backtest completed -> {outdir}")


if __name__ == "__main__":
    main()
