from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
PRICE_DB = PROJECT_ROOT / r"data\db\price.db"
FUND_DB = PROJECT_ROOT / r"data\db\fundamentals.db"
S3_DB = PROJECT_ROOT / r"data\db_s3\features_s3.db"
UNIVERSE_CSV = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger_backtest"
FORWARD_WINDOWS = {"1M": 21, "3M": 63}

S2_RULE = {
    "score_min": 200.0,
    "fund_accel_min": 0.60,
    "trend_up": 0,
    "ma_gap_low": -0.12,
    "ma_gap_high": 0.08,
    "mom20_low": -0.15,
    "mom20_high": 0.10,
    "top_n_per_date": 5,
}

S3_RULE = {
    "ma_gap_min": 0.60,
    "vol_ratio_min": 2.30,
    "mcap_max": 5_000_000_000_000.0,
    "fund_accel_min": 0.55,
    "mom20_min": 0.10,
}

S3_CORE2_RULE = {
    "ma_gap_min": 0.45,
    "vol_ratio_min": 2.00,
    "mcap_max": 3_000_000_000_000.0,
    "fund_accel_min": 0.55,
    "mom20_min": 0.10,
}


@dataclass(frozen=True)
class ModelSpec:
    model_code: str
    challenger_label: str
    baseline_label: str


SPECS = [
    ModelSpec("S2", "S2_challenger_reversal_pocket", "S2_baseline"),
    ModelSpec("S3", "S3_challenger_overheat_reject", "S3_baseline"),
    ModelSpec("S3_CORE2", "S3_CORE2_challenger_overheat_reject", "S3_CORE2_baseline"),
]


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def load_published_runs() -> dict[str, str]:
    df = read_sql(
        QS_DB,
        """
        SELECT model_code, published_run_id
        FROM pub_model_current
        WHERE model_code IN ('S2', 'S3', 'S3_CORE2')
        """,
    )
    return dict(zip(df["model_code"], df["published_run_id"]))


def load_baseline_holdings(run_id: str) -> pd.DataFrame:
    df = read_sql(
        QS_DETAIL_DB,
        """
        SELECT run_id, date, ticker, rank_no, weight, score
        FROM run_holdings_history
        WHERE run_id=?
        ORDER BY date, rank_no, ticker
        """,
        params=(run_id,),
        parse_dates=["date"],
    )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["rank_no"] = pd.to_numeric(df["rank_no"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    return df


def load_universe() -> pd.DataFrame:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["mcap"] = pd.to_numeric(df.get("mcap"), errors="coerce")
    cols = [c for c in ["ticker", "name", "market", "mcap"] if c in df.columns]
    return df[cols].copy()


def load_historical_mcap(csv_path: str | None) -> pd.DataFrame:
    if not csv_path:
        return pd.DataFrame(columns=["date", "ticker", "mcap", "list_shares"])
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"historical mcap file not found: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, parse_dates=["date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["mcap"] = pd.to_numeric(df.get("mcap"), errors="coerce")
    if "list_shares" in df.columns:
        df["list_shares"] = pd.to_numeric(df.get("list_shares"), errors="coerce")
    else:
        df["list_shares"] = np.nan
    return df[["date", "ticker", "mcap", "list_shares"]].drop_duplicates(["date", "ticker"])


def load_prices() -> tuple[pd.DataFrame, pd.DataFrame, list[pd.Timestamp], dict[str, dict[pd.Timestamp, pd.Timestamp]]]:
    px = read_sql(
        PRICE_DB,
        "SELECT ticker, date, close FROM prices_daily WHERE close IS NOT NULL",
        parse_dates=["date"],
    )
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px = px.dropna(subset=["close"]).sort_values(["date", "ticker"]).reset_index(drop=True)
    wide = px.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
    dates = [pd.Timestamp(d) for d in wide.index]
    end_maps: dict[str, dict[pd.Timestamp, pd.Timestamp]] = {}
    for label, step in FORWARD_WINDOWS.items():
        end_maps[label] = {dates[i]: dates[i + step] for i in range(len(dates) - step)}
    return px, wide, dates, end_maps


def load_common_features() -> tuple[pd.DataFrame, pd.DataFrame]:
    price_feat = read_sql(
        S3_DB,
        """
        SELECT ticker, date, close, vol_ratio_20, mom20, breakout60, ma60, ma120, ma60_slope
        FROM s3_price_features_daily
        """,
        parse_dates=["date"],
    )
    price_feat["ticker"] = price_feat["ticker"].astype(str).str.zfill(6)
    for col in ["close", "vol_ratio_20", "mom20", "ma60", "ma120", "ma60_slope"]:
        price_feat[col] = pd.to_numeric(price_feat[col], errors="coerce")
    price_feat["breakout60"] = pd.to_numeric(price_feat["breakout60"], errors="coerce").fillna(0.0)
    price_feat["trend_up"] = ((price_feat["ma60"] > price_feat["ma120"]) & (price_feat["ma60_slope"] > 0)).astype(int)
    price_feat["ma_gap_60"] = price_feat["close"] / price_feat["ma60"] - 1.0

    fund_feat = read_sql(
        S3_DB,
        """
        SELECT ticker, date, available_from, growth_score, fund_accel_score
        FROM s3_fund_features_monthly
        """,
        parse_dates=["date", "available_from"],
    )
    fund_feat["ticker"] = fund_feat["ticker"].astype(str).str.zfill(6)
    fund_feat["growth_score"] = pd.to_numeric(fund_feat["growth_score"], errors="coerce")
    fund_feat["fund_accel_score"] = pd.to_numeric(fund_feat["fund_accel_score"], errors="coerce")
    return price_feat, fund_feat


def latest_fund_snapshot(fund_feat: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    snap = fund_feat[fund_feat["available_from"] <= asof].copy()
    if snap.empty:
        return snap
    return snap.sort_values(["ticker", "available_from", "date"]).groupby("ticker", as_index=False).tail(1)


def load_s2_fund_scores() -> pd.DataFrame:
    df = read_sql(
        FUND_DB,
        """
        SELECT date, ticker, growth_score AS s2_growth_score, score_rank, valid_fund
        FROM s2_fund_scores_monthly
        """,
        parse_dates=["date"],
    )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["s2_growth_score"] = pd.to_numeric(df["s2_growth_score"], errors="coerce")
    df["score_rank"] = pd.to_numeric(df["score_rank"], errors="coerce")
    df["valid_fund"] = pd.to_numeric(df["valid_fund"], errors="coerce").fillna(0).astype(int)
    return df


def build_s2_candidates(
    asof: pd.Timestamp,
    universe: pd.DataFrame,
    price_feat: pd.DataFrame,
    fund_feat: pd.DataFrame,
    s2_fund: pd.DataFrame,
    baseline_tickers: set[str],
    historical_mcap: pd.DataFrame,
) -> pd.DataFrame:
    fund_date = s2_fund.loc[s2_fund["date"] <= asof, "date"].max()
    if pd.isna(fund_date):
        return pd.DataFrame()
    s2_snap = s2_fund[(s2_fund["date"] == fund_date) & (s2_fund["valid_fund"] == 1)].copy()
    px_snap = price_feat[price_feat["date"] == asof].copy()
    common_fund = latest_fund_snapshot(fund_feat, asof)
    snap = (
        universe.merge(s2_snap[["ticker", "s2_growth_score", "score_rank"]], on="ticker", how="inner")
        .merge(px_snap[["ticker", "mom20", "vol_ratio_20", "breakout60", "trend_up", "ma_gap_60"]], on="ticker", how="left")
        .merge(common_fund[["ticker", "growth_score", "fund_accel_score"]], on="ticker", how="left")
    )
    if not historical_mcap.empty:
        snap = snap.drop(columns=["mcap"], errors="ignore").merge(
            historical_mcap[historical_mcap["date"] == asof][["ticker", "mcap", "list_shares"]],
            on="ticker",
            how="left",
        )
    snap["date"] = asof
    snap["selected"] = snap["ticker"].isin(baseline_tickers).astype(int)
    snap["score_value"] = snap["s2_growth_score"]
    return snap


def build_s3_like_candidates(
    model_code: str,
    asof: pd.Timestamp,
    universe: pd.DataFrame,
    price_feat: pd.DataFrame,
    fund_feat: pd.DataFrame,
    baseline_tickers: set[str],
    historical_mcap: pd.DataFrame,
) -> pd.DataFrame:
    px_snap = price_feat[price_feat["date"] == asof].copy()
    if px_snap.empty:
        return pd.DataFrame()
    fund_snap = latest_fund_snapshot(fund_feat, asof)
    snap = universe.merge(px_snap, on="ticker", how="left").merge(
        fund_snap[["ticker", "growth_score", "fund_accel_score"]], on="ticker", how="left"
    )
    if not historical_mcap.empty:
        snap = snap.drop(columns=["mcap"], errors="ignore").merge(
            historical_mcap[historical_mcap["date"] == asof][["ticker", "mcap", "list_shares"]],
            on="ticker",
            how="left",
        )
    snap["mom20_pct"] = snap["mom20"].rank(pct=True)
    snap["vol_ratio_pct"] = snap["vol_ratio_20"].rank(pct=True)
    snap["fund_level_pct"] = snap["growth_score"].rank(pct=True)
    snap["fund_accel_pct"] = snap["fund_accel_score"].rank(pct=True)
    if model_code == "S3":
        snap["score_value"] = (
            0.30 * snap["fund_level_pct"].fillna(0)
            + 0.20 * snap["fund_accel_pct"].fillna(0)
            + 0.25 * snap["mom20_pct"].fillna(0)
            + 0.10 * snap["vol_ratio_pct"].fillna(0)
            + 0.05 * snap["breakout60"].fillna(0)
            + 0.10 * snap["trend_up"].fillna(0)
        )
    else:
        snap["score_value"] = 0.60 * snap["mom20_pct"].fillna(0) + 0.40 * snap["vol_ratio_pct"].fillna(0)
    snap["date"] = asof
    snap["selected"] = snap["ticker"].isin(baseline_tickers).astype(int)
    return snap


def apply_s2_challenger(baseline: pd.DataFrame, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if baseline.empty or candidates.empty:
        return baseline.copy(), pd.DataFrame()
    rule = S2_RULE
    pocket = candidates[
        (candidates["selected"] == 0)
        & (candidates["score_value"] >= rule["score_min"])
        & (candidates["fund_accel_score"] >= rule["fund_accel_min"])
        & (candidates["trend_up"] == rule["trend_up"])
        & (candidates["ma_gap_60"].between(rule["ma_gap_low"], rule["ma_gap_high"]))
        & (candidates["mom20"].between(rule["mom20_low"], rule["mom20_high"]))
    ].copy()
    if pocket.empty:
        out = baseline.copy()
        out["holding_source"] = "baseline_keep"
        return out, pd.DataFrame()
    pocket = pocket.sort_values(["score_value", "ticker"], ascending=[False, True]).head(rule["top_n_per_date"]).copy()
    replace_n = min(len(pocket), len(baseline))
    removed = baseline.sort_values(["rank_no", "ticker"], ascending=[False, True]).head(replace_n).copy()
    keep = baseline.loc[~baseline["ticker"].isin(removed["ticker"])].copy()

    add = pd.DataFrame(
        {
            "date": baseline["date"].iloc[0],
            "ticker": pocket["ticker"].tolist()[:replace_n],
            "score": pocket["score_value"].tolist()[:replace_n],
            "rank_no": list(range(len(keep) + 1, len(keep) + replace_n + 1)),
            "weight": 1.0 / len(baseline),
            "holding_source": "challenger_add_reversal",
        }
    )
    keep = keep.copy()
    keep["holding_source"] = "baseline_keep"
    challenger = pd.concat([keep, add], ignore_index=True)
    challenger["weight"] = 1.0 / len(challenger)
    changes = pd.concat(
        [
            removed.assign(change_type="drop_for_reversal"),
            add.assign(change_type="add_reversal"),
        ],
        ignore_index=True,
    )
    return challenger, changes


def reject_mask(df: pd.DataFrame, rule: dict[str, float]) -> pd.Series:
    return (
        (df["ma_gap_60"] >= rule["ma_gap_min"])
        & (df["vol_ratio_20"] >= rule["vol_ratio_min"])
        & (df["mcap"] <= rule["mcap_max"])
        & (df["fund_accel_score"] >= rule["fund_accel_min"])
        & (df["mom20"] >= rule["mom20_min"])
    )


def apply_s3_family_challenger(model_code: str, baseline: pd.DataFrame, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if baseline.empty or candidates.empty:
        return baseline.copy(), pd.DataFrame()
    rule = S3_RULE if model_code == "S3" else S3_CORE2_RULE
    selected = candidates[candidates["selected"] == 1].copy()
    selected["reject_flag"] = reject_mask(selected, rule).astype(int)
    remove = selected[selected["reject_flag"] == 1].copy()
    keep = baseline.loc[~baseline["ticker"].isin(remove["ticker"])].copy()
    target_n = len(baseline)
    fill_n = max(target_n - len(keep), 0)
    pool = candidates[candidates["selected"] == 0].copy()
    pool = pool.loc[~reject_mask(pool, rule)].copy()
    pool = pool.sort_values(["score_value", "ticker"], ascending=[False, True]).head(fill_n).copy()

    add = pd.DataFrame(
        {
            "date": baseline["date"].iloc[0],
            "ticker": pool["ticker"].tolist(),
            "score": pool["score_value"].tolist(),
            "rank_no": list(range(len(keep) + 1, len(keep) + len(pool) + 1)),
            "weight": 1.0 / target_n if target_n else np.nan,
            "holding_source": "challenger_add_replacement",
        }
    )
    keep = keep.copy()
    keep["holding_source"] = "baseline_keep"
    challenger = pd.concat([keep, add], ignore_index=True)
    if not challenger.empty:
        challenger["weight"] = 1.0 / len(challenger)

    changes = pd.concat(
        [
            remove.assign(change_type="drop_overheat")[["date", "ticker", "score_value", "change_type"]],
            pool.assign(change_type="add_replacement")[["date", "ticker", "score_value", "change_type"]],
        ],
        ignore_index=True,
    )
    changes = changes.rename(columns={"score_value": "score"})
    return challenger, changes


def build_model_variants(
    spec: ModelSpec,
    run_id: str,
    universe: pd.DataFrame,
    price_feat: pd.DataFrame,
    fund_feat: pd.DataFrame,
    s2_fund: pd.DataFrame,
    historical_mcap: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = load_baseline_holdings(run_id)
    baseline_rows: list[pd.DataFrame] = []
    challenger_rows: list[pd.DataFrame] = []
    change_rows: list[pd.DataFrame] = []

    for dt, hist in base.groupby("date", sort=True):
        hist = hist.copy().sort_values(["rank_no", "ticker"]).reset_index(drop=True)
        hist["weight"] = hist["weight"].fillna(1.0 / len(hist) if len(hist) else np.nan)
        hist["variant"] = spec.baseline_label
        hist["holding_source"] = "baseline_original"
        baseline_rows.append(hist[["date", "ticker", "rank_no", "weight", "score", "variant", "holding_source"]])

        baseline_tickers = set(hist["ticker"].tolist())
        if spec.model_code == "S2":
            candidates = build_s2_candidates(
                pd.Timestamp(dt), universe, price_feat, fund_feat, s2_fund, baseline_tickers, historical_mcap
            )
            challenger_hist, changes = apply_s2_challenger(hist[["date", "ticker", "rank_no", "weight", "score"]], candidates)
        else:
            candidates = build_s3_like_candidates(
                spec.model_code, pd.Timestamp(dt), universe, price_feat, fund_feat, baseline_tickers, historical_mcap
            )
            challenger_hist, changes = apply_s3_family_challenger(spec.model_code, hist[["date", "ticker", "rank_no", "weight", "score"]], candidates)

        challenger_hist["variant"] = spec.challenger_label
        challenger_rows.append(challenger_hist[["date", "ticker", "rank_no", "weight", "score", "variant", "holding_source"]])
        if not changes.empty:
            changes["model_code"] = spec.model_code
            changes["variant"] = spec.challenger_label
            change_rows.append(changes)

    holdings = pd.concat(baseline_rows + challenger_rows, ignore_index=True)
    changes = pd.concat(change_rows, ignore_index=True) if change_rows else pd.DataFrame()
    holdings["model_code"] = spec.model_code
    return holdings, changes


def simulate_variant_nav(variant_holdings: pd.DataFrame, returns_wide: pd.DataFrame) -> pd.DataFrame:
    if variant_holdings.empty:
        return pd.DataFrame()
    rebalance_dates = sorted(pd.to_datetime(variant_holdings["date"].dropna().unique()))
    nav = 1.0
    rows = [{"date": rebalance_dates[0], "nav": nav, "holdings_count": int((variant_holdings["date"] == rebalance_dates[0]).sum())}]
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
            aligned = day_ret.reindex(weights.index).fillna(0.0)
            port_ret = float((aligned * weights).sum())
            nav *= 1.0 + port_ret
            rows.append({"date": day, "nav": nav, "holdings_count": len(tickers)})
    return pd.DataFrame(rows)


def compute_perf(nav_df: pd.DataFrame, label: str) -> list[dict[str, object]]:
    if nav_df.empty:
        return []
    nav_df = nav_df.sort_values("date").copy()
    nav_df["ret"] = nav_df["nav"].pct_change()
    out = []
    windows = {
        "full_history": nav_df["date"].min(),
        "since_2020": pd.Timestamp("2020-01-01"),
        "since_2024": pd.Timestamp("2024-01-01"),
    }
    for period, start_date in windows.items():
        sub = nav_df[nav_df["date"] >= start_date].copy()
        if len(sub) < 2:
            continue
        start_nav = float(sub["nav"].iloc[0])
        end_nav = float(sub["nav"].iloc[-1])
        years = max((sub["date"].iloc[-1] - sub["date"].iloc[0]).days / 365.25, 1 / 252)
        total_return = end_nav / start_nav - 1.0
        cagr = (end_nav / start_nav) ** (1.0 / years) - 1.0 if start_nav > 0 else np.nan
        drawdown = sub["nav"] / sub["nav"].cummax() - 1.0
        vol = float(sub["ret"].std() * np.sqrt(252)) if sub["ret"].notna().sum() > 1 else np.nan
        sharpe = float((sub["ret"].mean() / sub["ret"].std()) * np.sqrt(252)) if sub["ret"].notna().sum() > 1 and sub["ret"].std() > 0 else np.nan
        out.append(
            {
                "variant": label,
                "period": period,
                "start_date": sub["date"].iloc[0],
                "end_date": sub["date"].iloc[-1],
                "total_return": total_return,
                "cagr": cagr,
                "mdd": float(drawdown.min()),
                "annual_vol": vol,
                "sharpe": sharpe,
            }
        )
    return out


def turnover_summary(holdings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows = []
    summary_rows = []
    for (model_code, variant), grp in holdings.groupby(["model_code", "variant"]):
        prev: set[str] | None = None
        for dt, snap in grp.groupby("date", sort=True):
            curr = set(snap["ticker"].tolist())
            if prev is None:
                prev = curr
                continue
            adds = sorted(curr - prev)
            drops = sorted(prev - curr)
            turnover_ratio = len(adds) / max(len(curr), 1)
            detail_rows.append(
                {
                    "model_code": model_code,
                    "variant": variant,
                    "date": pd.Timestamp(dt),
                    "prev_count": len(prev),
                    "curr_count": len(curr),
                    "n_add": len(adds),
                    "n_drop": len(drops),
                    "turnover_ratio": turnover_ratio,
                    "added_tickers": ",".join(adds),
                    "dropped_tickers": ",".join(drops),
                }
            )
            prev = curr
    detail = pd.DataFrame(detail_rows)
    if not detail.empty:
        summary = (
            detail.groupby(["model_code", "variant"], dropna=False)
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
    else:
        summary = pd.DataFrame()
    return detail, summary


def new_entry_quality(holdings: pd.DataFrame, price_wide: pd.DataFrame, end_maps: dict[str, dict[pd.Timestamp, pd.Timestamp]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_lookup = price_wide
    detail_rows = []
    for (model_code, variant), grp in holdings.groupby(["model_code", "variant"]):
        prev: set[str] | None = None
        for dt, snap in grp.groupby("date", sort=True):
            curr = set(snap["ticker"].tolist())
            if prev is None:
                prev = curr
                continue
            entries = sorted(curr - prev)
            for ticker in entries:
                if ticker not in price_lookup.columns or dt not in price_lookup.index:
                    continue
                entry_close = price_lookup.at[dt, ticker]
                if pd.isna(entry_close):
                    continue
                for horizon, mapping in end_maps.items():
                    end_date = mapping.get(pd.Timestamp(dt))
                    if end_date is None or end_date not in price_lookup.index:
                        continue
                    end_close = price_lookup.at[end_date, ticker]
                    if pd.isna(end_close):
                        continue
                    detail_rows.append(
                        {
                            "model_code": model_code,
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
    return detail, summary


def build_comparison(perf: pd.DataFrame, turnover: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for spec in SPECS:
        base_perf = perf[(perf["variant"] == spec.baseline_label) & (perf["period"] == "full_history")]
        chal_perf = perf[(perf["variant"] == spec.challenger_label) & (perf["period"] == "full_history")]
        base_turn = turnover[turnover["variant"] == spec.baseline_label]
        chal_turn = turnover[turnover["variant"] == spec.challenger_label]
        base_q = quality[(quality["variant"] == spec.baseline_label) & (quality["horizon"] == "1M")]
        chal_q = quality[(quality["variant"] == spec.challenger_label) & (quality["horizon"] == "1M")]
        rows.append(
            {
                "model_code": spec.model_code,
                "baseline_variant": spec.baseline_label,
                "challenger_variant": spec.challenger_label,
                "baseline_total_return": float(base_perf["total_return"].iloc[0]) if not base_perf.empty else np.nan,
                "challenger_total_return": float(chal_perf["total_return"].iloc[0]) if not chal_perf.empty else np.nan,
                "baseline_cagr": float(base_perf["cagr"].iloc[0]) if not base_perf.empty else np.nan,
                "challenger_cagr": float(chal_perf["cagr"].iloc[0]) if not chal_perf.empty else np.nan,
                "baseline_mdd": float(base_perf["mdd"].iloc[0]) if not base_perf.empty else np.nan,
                "challenger_mdd": float(chal_perf["mdd"].iloc[0]) if not chal_perf.empty else np.nan,
                "baseline_avg_turnover": float(base_turn["avg_turnover_ratio"].iloc[0]) if not base_turn.empty else np.nan,
                "challenger_avg_turnover": float(chal_turn["avg_turnover_ratio"].iloc[0]) if not chal_turn.empty else np.nan,
                "baseline_new_entry_1m": float(base_q["avg_forward_return"].iloc[0]) if not base_q.empty else np.nan,
                "challenger_new_entry_1m": float(chal_q["avg_forward_return"].iloc[0]) if not chal_q.empty else np.nan,
                "baseline_new_entry_1m_winner_rate": float(base_q["winner_rate"].iloc[0]) if not base_q.empty else np.nan,
                "challenger_new_entry_1m_winner_rate": float(chal_q["winner_rate"].iloc[0]) if not chal_q.empty else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["delta_total_return"] = out["challenger_total_return"] - out["baseline_total_return"]
        out["delta_cagr"] = out["challenger_cagr"] - out["baseline_cagr"]
        out["delta_mdd"] = out["challenger_mdd"] - out["baseline_mdd"]
        out["delta_avg_turnover"] = out["challenger_avg_turnover"] - out["baseline_avg_turnover"]
        out["delta_new_entry_1m"] = out["challenger_new_entry_1m"] - out["baseline_new_entry_1m"]
        out["delta_new_entry_1m_winner_rate"] = (
            out["challenger_new_entry_1m_winner_rate"] - out["baseline_new_entry_1m_winner_rate"]
        )
    return out


def to_markdown(
    comparison: pd.DataFrame,
    perf: pd.DataFrame,
    turnover: pd.DataFrame,
    quality: pd.DataFrame,
    historical_mcap_used: bool,
) -> str:
    mcap_note = (
        "- historical market-cap is injected from KRX OpenAPI signal-date snapshots"
        if historical_mcap_used
        else "- caveat: `S3 / S3_CORE2` challenger still uses latest-universe `mcap` as a static proxy because historical daily market-cap is not yet stored as an operational DB feature"
    )
    lines = [
        "# S-Series Challenger Backtest Comparison",
        "",
        "## Scope",
        "- models: `S2`, `S3`, `S3_CORE2`",
        "- baseline: current published internal holdings history",
        "- challenger: filter-enhanced reconstruction using the challenger rules designed on 2026-04-24",
        "- portfolio simulation: baseline and challenger are replayed with the same close-to-close engine for fair comparison",
        mcap_note,
        "",
    ]

    if not comparison.empty:
        lines.extend(
            [
                "## Headline Comparison",
                "| Model | Baseline Return | Challenger Return | Delta Return | Baseline CAGR | Challenger CAGR | Baseline MDD | Challenger MDD | Baseline Turnover | Challenger Turnover | Baseline New Entry 1M | Challenger New Entry 1M |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in comparison.itertuples(index=False):
            lines.append(
                f"| {row.model_code} | {row.baseline_total_return:.2%} | {row.challenger_total_return:.2%} | {row.delta_total_return:.2%} | "
                f"{row.baseline_cagr:.2%} | {row.challenger_cagr:.2%} | {row.baseline_mdd:.2%} | {row.challenger_mdd:.2%} | "
                f"{row.baseline_avg_turnover:.2%} | {row.challenger_avg_turnover:.2%} | {row.baseline_new_entry_1m:.2%} | {row.challenger_new_entry_1m:.2%} |"
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
            vol_txt = "-" if pd.isna(row.annual_vol) else f"{row.annual_vol:.2%}"
            shp_txt = "-" if pd.isna(row.sharpe) else f"{row.sharpe:.2f}"
            lines.append(
                f"| {row.variant} | {row.period} | {row.total_return:.2%} | {row.cagr:.2%} | {row.mdd:.2%} | {vol_txt} | {shp_txt} |"
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
        for row in turnover.sort_values(["model_code", "variant"]).itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.avg_add_count:.2f} | {row.avg_drop_count:.2f} | {row.avg_turnover_ratio:.2%} | "
                f"{row.median_turnover_ratio:.2%} | {row.max_turnover_ratio:.2%} |"
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
        for row in quality.sort_values(["model_code", "variant", "horizon"]).itertuples(index=False):
            lines.append(
                f"| {row.variant} | {row.horizon} | {row.n_entries} | {row.avg_forward_return:.2%} | {row.median_forward_return:.2%} | "
                f"{row.winner_rate:.2%} | {row.loser_rate:.2%} |"
            )
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical-mcap-csv", default="", help="Optional CSV with columns: date,ticker,mcap[,list_shares]")
    ap.add_argument("--tag", default="", help="Optional suffix for output directory")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    outdir = OUTDIR if not args.tag else Path(str(OUTDIR) + f"_{args.tag}")
    outdir.mkdir(parents=True, exist_ok=True)

    runs = load_published_runs()
    universe = load_universe()
    historical_mcap = load_historical_mcap(args.historical_mcap_csv)
    _px_long, price_wide, _dates, end_maps = load_prices()
    returns_wide = price_wide.pct_change().fillna(0.0)
    price_feat, fund_feat = load_common_features()
    s2_fund = load_s2_fund_scores()

    holdings_frames = []
    changes_frames = []
    for spec in SPECS:
        holdings, changes = build_model_variants(
            spec, runs[spec.model_code], universe, price_feat, fund_feat, s2_fund, historical_mcap
        )
        holdings_frames.append(holdings)
        if not changes.empty:
            changes_frames.append(changes)

    holdings_all = pd.concat(holdings_frames, ignore_index=True)
    changes_all = pd.concat(changes_frames, ignore_index=True) if changes_frames else pd.DataFrame()

    nav_frames = []
    perf_rows = []
    for (model_code, variant), grp in holdings_all.groupby(["model_code", "variant"]):
        nav = simulate_variant_nav(grp[["date", "ticker", "weight"]], returns_wide)
        if nav.empty:
            continue
        nav["model_code"] = model_code
        nav["variant"] = variant
        nav_frames.append(nav)
        perf_rows.extend(compute_perf(nav[["date", "nav"]], variant))

    nav_all = pd.concat(nav_frames, ignore_index=True) if nav_frames else pd.DataFrame()
    perf = pd.DataFrame(perf_rows)
    if not perf.empty:
        perf["model_code"] = perf["variant"].str.extract(r"^(S2|S3_CORE2|S3)")

    turnover_detail, turnover = turnover_summary(holdings_all)
    entry_detail, entry_quality = new_entry_quality(holdings_all, price_wide, end_maps)
    comparison = build_comparison(perf, turnover, entry_quality)

    holdings_all.to_csv(outdir / "s_series_challenger_holdings_history.csv", index=False, encoding="utf-8-sig")
    if not changes_all.empty:
        changes_all.to_csv(outdir / "s_series_challenger_holdings_changes.csv", index=False, encoding="utf-8-sig")
    if not nav_all.empty:
        nav_all.to_csv(outdir / "s_series_challenger_nav_history.csv", index=False, encoding="utf-8-sig")
    if not perf.empty:
        perf.to_csv(outdir / "s_series_challenger_performance_summary.csv", index=False, encoding="utf-8-sig")
    if not turnover_detail.empty:
        turnover_detail.to_csv(outdir / "s_series_challenger_turnover_detail.csv", index=False, encoding="utf-8-sig")
    if not turnover.empty:
        turnover.to_csv(outdir / "s_series_challenger_turnover_summary.csv", index=False, encoding="utf-8-sig")
    if not entry_detail.empty:
        entry_detail.to_csv(outdir / "s_series_challenger_new_entry_detail.csv", index=False, encoding="utf-8-sig")
    if not entry_quality.empty:
        entry_quality.to_csv(outdir / "s_series_challenger_new_entry_quality_summary.csv", index=False, encoding="utf-8-sig")
    if not comparison.empty:
        comparison.to_csv(outdir / "s_series_challenger_comparison.csv", index=False, encoding="utf-8-sig")

    (outdir / "s_series_challenger_backtest_review.md").write_text(
        to_markdown(comparison, perf, turnover, entry_quality, historical_mcap_used=not historical_mcap.empty),
        encoding="utf-8",
    )
    print(f"[OK] wrote {outdir}")


if __name__ == "__main__":
    main()
