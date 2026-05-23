from __future__ import annotations

import sqlite3
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
HISTORICAL_MCAP_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger_backtest_historical_mcap\historical_mcap_signal_dates.csv"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s3_pit_auxiliary_comparison"
START_DATE = pd.Timestamp("2024-01-31")
FORWARD_WINDOWS = {"1M": 21, "3M": 63}
MODELS = ("S3", "S3_CORE2")

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


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def load_runs() -> dict[str, str]:
    df = read_sql(
        QS_DB,
        """
        SELECT model_code, published_run_id
        FROM pub_model_current
        WHERE model_code IN ('S3','S3_CORE2')
        """,
    )
    return dict(zip(df["model_code"], df["published_run_id"]))


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
    df["rank_no"] = pd.to_numeric(df["rank_no"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
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
    end_maps = {label: {dates[i]: dates[i + step] for i in range(len(dates) - step)} for label, step in FORWARD_WINDOWS.items()}
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


def load_pit_features() -> pd.DataFrame:
    df = read_sql(
        FUND_DB,
        """
        SELECT date, ticker, coverage_score, pit_growth_score,
               q_revenue_yoy, q_op_income_yoy,
               q_revenue_yoy_delta_1q, q_op_income_yoy_delta_1q,
               annual_component, quarter_component, accel_component
        FROM fundamentals_pit_qh_mix400_latest
        """,
        parse_dates=["date"],
    )
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in [
        "coverage_score", "pit_growth_score", "q_revenue_yoy", "q_op_income_yoy",
        "q_revenue_yoy_delta_1q", "q_op_income_yoy_delta_1q",
        "annual_component", "quarter_component", "accel_component",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def latest_snapshot(df: pd.DataFrame, asof: pd.Timestamp, date_col: str = "date") -> pd.DataFrame:
    snap = df[df[date_col] <= asof].copy()
    if snap.empty:
        return snap
    return snap.sort_values(["ticker", date_col]).groupby("ticker", as_index=False).tail(1)


def build_candidates(
    model_code: str,
    asof: pd.Timestamp,
    baseline_tickers: set[str],
    universe: pd.DataFrame,
    price_feat: pd.DataFrame,
    fund_feat: pd.DataFrame,
    pit_feat: pd.DataFrame,
    historical_mcap: pd.DataFrame,
) -> pd.DataFrame:
    px_snap = price_feat[price_feat["date"] == asof].copy()
    if px_snap.empty:
        return pd.DataFrame()
    fund_snap = latest_snapshot(fund_feat, asof, "available_from")
    pit_snap = latest_snapshot(pit_feat, asof, "date")
    mcap_snap = historical_mcap[historical_mcap["date"] == asof][["ticker", "mcap"]].copy()

    snap = (
        universe.drop(columns=["mcap"], errors="ignore")
        .merge(px_snap, on="ticker", how="left")
        .merge(fund_snap[["ticker", "growth_score", "fund_accel_score"]], on="ticker", how="left")
        .merge(pit_snap[[
            "ticker", "coverage_score", "pit_growth_score", "q_revenue_yoy", "q_op_income_yoy",
            "q_revenue_yoy_delta_1q", "q_op_income_yoy_delta_1q", "annual_component", "quarter_component", "accel_component"
        ]], on="ticker", how="left")
        .merge(mcap_snap, on="ticker", how="left")
    )
    snap["mom20_pct"] = snap["mom20"].rank(pct=True)
    snap["vol_ratio_pct"] = snap["vol_ratio_20"].rank(pct=True)
    snap["fund_level_pct"] = snap["growth_score"].rank(pct=True)
    snap["fund_accel_pct"] = snap["fund_accel_score"].rank(pct=True)
    snap["pit_level_pct"] = 1.0 - snap["pit_growth_score"].rank(pct=True)
    snap["pit_quarter_pct"] = snap["q_op_income_yoy"].rank(pct=True)
    snap["pit_accel_pct"] = snap["q_op_income_yoy_delta_1q"].rank(pct=True)
    snap["pit_strength"] = (
        0.45 * snap["pit_level_pct"].fillna(0)
        + 0.30 * snap["pit_quarter_pct"].fillna(0)
        + 0.25 * snap["pit_accel_pct"].fillna(0)
    )
    snap["pit_confirmed"] = (snap["coverage_score"] >= 0.7).astype(int)
    snap["pit_weak"] = (
        (snap["pit_confirmed"] == 1)
        & (
            (snap["q_op_income_yoy"].fillna(-999) <= 0)
            | (snap["q_op_income_yoy_delta_1q"].fillna(-999) <= 0)
            | (snap["pit_strength"].fillna(0) < 0.45)
        )
    ).astype(int)
    snap["pit_strong"] = (
        (snap["pit_confirmed"] == 1)
        & (snap["q_op_income_yoy"].fillna(-999) > 0)
        & (snap["q_op_income_yoy_delta_1q"].fillna(-999) > 0)
        & (snap["pit_strength"].fillna(0) >= 0.60)
    ).astype(int)
    if model_code == "S3":
        snap["base_score"] = (
            0.30 * snap["fund_level_pct"].fillna(0)
            + 0.20 * snap["fund_accel_pct"].fillna(0)
            + 0.25 * snap["mom20_pct"].fillna(0)
            + 0.10 * snap["vol_ratio_pct"].fillna(0)
            + 0.05 * snap["breakout60"].fillna(0)
            + 0.10 * snap["trend_up"].fillna(0)
        )
    else:
        snap["base_score"] = 0.60 * snap["mom20_pct"].fillna(0) + 0.40 * snap["vol_ratio_pct"].fillna(0)
    snap["date"] = asof
    snap["selected"] = snap["ticker"].isin(baseline_tickers).astype(int)
    return snap


def overheat_mask(df: pd.DataFrame, model_code: str) -> pd.Series:
    rule = S3_RULE if model_code == "S3" else S3_CORE2_RULE
    return (
        (df["ma_gap_60"] >= rule["ma_gap_min"])
        & (df["vol_ratio_20"] >= rule["vol_ratio_min"])
        & (df["mcap"] <= rule["mcap_max"])
        & (df["fund_accel_score"] >= rule["fund_accel_min"])
        & (df["mom20"] >= rule["mom20_min"])
    )


def make_portfolio_rows(dt: pd.Timestamp, tickers: list[str], score_map: dict[str, float], source: str) -> pd.DataFrame:
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


def variant_reject(model_code: str, baseline: pd.DataFrame, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = candidates[candidates["selected"] == 1].copy()
    selected["reject_flag"] = (overheat_mask(selected, model_code) & (selected["pit_weak"] == 1)).astype(int)
    remove = selected[selected["reject_flag"] == 1].copy()
    keep_tickers = [t for t in baseline["ticker"].tolist() if t not in set(remove["ticker"])]
    fill_n = len(baseline) - len(keep_tickers)
    pool = candidates[(candidates["selected"] == 0) & ~((overheat_mask(candidates, model_code)) & (candidates["pit_weak"] == 1))].copy()
    pool = pool.sort_values(["base_score", "pit_strength", "ticker"], ascending=[False, False, True]).head(fill_n)
    final_tickers = keep_tickers + pool["ticker"].tolist()
    score_map = dict(zip(candidates["ticker"], candidates["base_score"]))
    holdings = make_portfolio_rows(baseline["date"].iloc[0], final_tickers, score_map, "pit_reject_aux")
    changes = pd.concat(
        [
            remove.assign(change_type="drop_overheat_pitweak")[["date", "ticker", "base_score", "change_type"]],
            pool.assign(change_type="add_replacement")[["date", "ticker", "base_score", "change_type"]],
        ],
        ignore_index=True,
    ).rename(columns={"base_score": "score"})
    return holdings, changes


def variant_penalty(model_code: str, baseline: pd.DataFrame, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cand = candidates.copy()
    oh = overheat_mask(cand, model_code).astype(int)
    cand["adj_score"] = (
        cand["base_score"].fillna(0)
        + 0.05 * cand["pit_strength"].fillna(0) * cand["pit_confirmed"].fillna(0)
        + 0.02 * cand["pit_strong"].fillna(0)
        - 0.10 * oh * cand["pit_weak"].fillna(0)
    )
    chosen = cand.sort_values(["adj_score", "base_score", "ticker"], ascending=[False, False, True]).head(len(baseline)).copy()
    score_map = dict(zip(cand["ticker"], cand["adj_score"]))
    holdings = make_portfolio_rows(baseline["date"].iloc[0], chosen["ticker"].tolist(), score_map, "pit_penalty_aux")
    baseline_set = set(baseline["ticker"])
    changes = pd.concat(
        [
            baseline.loc[~baseline["ticker"].isin(chosen["ticker"])].assign(change_type="drop_penalty_reorder")[["date", "ticker", "score", "change_type"]],
            chosen.loc[~chosen["ticker"].isin(baseline_set)].assign(change_type="add_penalty_reorder")[["date", "ticker", "adj_score", "change_type"]].rename(columns={"adj_score": "score"}),
        ],
        ignore_index=True,
    )
    return holdings, changes


def variant_tiebreak(model_code: str, baseline: pd.DataFrame, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    band_n = max(len(baseline) * 2, 40)
    band = candidates.sort_values(["base_score", "ticker"], ascending=[False, True]).head(band_n).copy()
    band["tie_score"] = (
        band["base_score"].fillna(0)
        + 0.02 * band["pit_strength"].fillna(0) * band["pit_confirmed"].fillna(0)
        + 0.01 * band["pit_strong"].fillna(0)
        - 0.02 * band["pit_weak"].fillna(0)
    )
    chosen = band.sort_values(["tie_score", "base_score", "ticker"], ascending=[False, False, True]).head(len(baseline)).copy()
    score_map = dict(zip(band["ticker"], band["tie_score"]))
    holdings = make_portfolio_rows(baseline["date"].iloc[0], chosen["ticker"].tolist(), score_map, "pit_tiebreak_aux")
    baseline_set = set(baseline["ticker"])
    changes = pd.concat(
        [
            baseline.loc[~baseline["ticker"].isin(chosen["ticker"])].assign(change_type="drop_tiebreak")[["date", "ticker", "score", "change_type"]],
            chosen.loc[~chosen["ticker"].isin(baseline_set)].assign(change_type="add_tiebreak")[["date", "ticker", "tie_score", "change_type"]].rename(columns={"tie_score": "score"}),
        ],
        ignore_index=True,
    )
    return holdings, changes


VARIANTS = {
    "pit_reject_aux": variant_reject,
    "pit_penalty_aux": variant_penalty,
    "pit_tiebreak_aux": variant_tiebreak,
}


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


def compute_perf(nav_df: pd.DataFrame, model_code: str, variant: str) -> list[dict[str, object]]:
    if nav_df.empty:
        return []
    nav_df = nav_df.sort_values("date").copy()
    nav_df["ret"] = nav_df["nav"].pct_change()
    windows = {"full_history": START_DATE, "since_2025": pd.Timestamp("2025-01-01"), "since_2026": pd.Timestamp("2026-01-01")}
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
        rows.append({
            "model_code": model_code,
            "variant": variant,
            "period": period,
            "start_date": sub["date"].iloc[0],
            "end_date": sub["date"].iloc[-1],
            "total_return": total_return,
            "cagr": cagr,
            "mdd": float(dd.min()),
            "annual_vol": vol,
            "sharpe": sharpe,
        })
    return rows


def turnover_summary(holdings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model_code, variant), grp in holdings.groupby(["model_code", "variant"]):
        prev: set[str] | None = None
        for dt, snap in grp.groupby("date", sort=True):
            curr = set(snap["ticker"].tolist())
            if prev is None:
                prev = curr
                continue
            adds = sorted(curr - prev)
            drops = sorted(prev - curr)
            rows.append({
                "model_code": model_code,
                "variant": variant,
                "date": pd.Timestamp(dt),
                "n_add": len(adds),
                "n_drop": len(drops),
                "turnover_ratio": len(adds) / max(len(curr), 1),
            })
            prev = curr
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail
    return (
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


def new_entry_quality(holdings: pd.DataFrame, price_wide: pd.DataFrame, end_maps: dict[str, dict[pd.Timestamp, pd.Timestamp]]) -> pd.DataFrame:
    rows = []
    for (model_code, variant), grp in holdings.groupby(["model_code", "variant"]):
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
                    rows.append({
                        "model_code": model_code,
                        "variant": variant,
                        "entry_date": pd.Timestamp(dt),
                        "ticker": ticker,
                        "horizon": horizon,
                        "end_date": end_date,
                        "forward_return": float(end_close / entry_close - 1.0),
                    })
            prev = curr
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail
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
    rows = []
    for model_code in MODELS:
        base = holdings[(holdings["model_code"] == model_code) & (holdings["variant"] == "baseline")]
        for variant in [v for v in holdings["variant"].dropna().unique() if v not in {"baseline"}]:
            cmp = holdings[(holdings["model_code"] == model_code) & (holdings["variant"] == variant)]
            if cmp.empty:
                continue
            for dt in sorted(set(base["date"]) & set(cmp["date"])):
                b = set(base.loc[base["date"] == dt, "ticker"])
                c = set(cmp.loc[cmp["date"] == dt, "ticker"])
                rows.append({
                    "model_code": model_code,
                    "variant": variant,
                    "date": dt,
                    "overlap_ratio": len(b & c) / max(len(b | c), 1),
                    "baseline_count": len(b),
                    "variant_count": len(c),
                })
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail
    return detail.groupby(["model_code", "variant"], dropna=False).agg(
        avg_overlap_ratio=("overlap_ratio", "mean"),
        min_overlap_ratio=("overlap_ratio", "min"),
    ).reset_index()


def build_markdown(headline: pd.DataFrame, perf: pd.DataFrame, turnover: pd.DataFrame, quality: pd.DataFrame, overlap: pd.DataFrame) -> str:
    lines = [
        "# S3 PIT Auxiliary Comparison",
        "",
        "## Scope",
        f"- models: `{', '.join(MODELS)}`",
        f"- window start: `{START_DATE.date().isoformat()}`",
        "- baseline: current published internal holdings replay",
        "- auxiliary PIT variants:",
        "  - `pit_reject_aux`: overheat + PIT-weak selected holdings only 제거",
        "  - `pit_penalty_aux`: 전체 후보에 PIT 보너스/패널티를 넣어 재정렬",
        "  - `pit_tiebreak_aux`: 상위 후보 band 안에서만 PIT로 미세 재정렬",
        "",
    ]
    if not headline.empty:
        lines.extend([
            "## Headline Comparison",
            "| Model | Variant | Total Return | CAGR | MDD | Sharpe | Avg Turnover | New Entry 1M | Winner Rate 1M | Avg Overlap |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for row in headline.itertuples(index=False):
            lines.append(
                f"| {row.model_code} | {row.variant} | {row.total_return:.2%} | {row.cagr:.2%} | {row.mdd:.2%} | "
                f"{('-' if pd.isna(row.sharpe) else f'{row.sharpe:.2f}')} | {row.avg_turnover_ratio:.2%} | "
                f"{row.avg_forward_return_1m:.2%} | {row.winner_rate_1m:.2%} | {row.avg_overlap_ratio:.2%} |"
            )
        lines.append("")
    if not perf.empty:
        lines.extend([
            "## Performance Windows",
            "| Model | Variant | Period | Total Return | CAGR | MDD | Annual Vol | Sharpe |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ])
        for row in perf.sort_values(["model_code", "variant", "period"]).itertuples(index=False):
            lines.append(
                f"| {row.model_code} | {row.variant} | {row.period} | {row.total_return:.2%} | {row.cagr:.2%} | "
                f"{row.mdd:.2%} | {('-' if pd.isna(row.annual_vol) else f'{row.annual_vol:.2%}')} | {('-' if pd.isna(row.sharpe) else f'{row.sharpe:.2f}')} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    runs = load_runs()
    universe = load_universe()
    historical_mcap = load_historical_mcap()
    price_wide, returns_wide, end_maps = load_price_and_forward_maps()
    price_feat = load_price_features()
    fund_feat = load_s3_fund_features()
    pit_feat = load_pit_features()

    holdings_frames = []
    changes_frames = []
    nav_rows: list[dict[str, object]] = []

    for model_code in MODELS:
        base = load_baseline_holdings(runs[model_code])
        baseline_rows = []
        variant_rows = {k: [] for k in VARIANTS}
        variant_changes = {k: [] for k in VARIANTS}

        for dt, hist in base.groupby("date", sort=True):
            hist = hist.copy().sort_values(["rank_no", "ticker"]).reset_index(drop=True)
            hist["weight"] = hist["weight"].fillna(1.0 / len(hist) if len(hist) else np.nan)
            hist["variant"] = "baseline"
            hist["holding_source"] = "baseline_original"
            hist["model_code"] = model_code
            baseline_rows.append(hist[["date", "ticker", "rank_no", "weight", "score", "variant", "holding_source", "model_code"]])

            candidates = build_candidates(
                model_code=model_code,
                asof=pd.Timestamp(dt),
                baseline_tickers=set(hist["ticker"].tolist()),
                universe=universe,
                price_feat=price_feat,
                fund_feat=fund_feat,
                pit_feat=pit_feat,
                historical_mcap=historical_mcap,
            )
            if candidates.empty:
                continue
            baseline_core = hist[["date", "ticker", "rank_no", "weight", "score"]].copy()
            for variant_name, fn in VARIANTS.items():
                variant_holdings, variant_changes_df = fn(model_code, baseline_core, candidates)
                variant_holdings["variant"] = variant_name
                variant_holdings["model_code"] = model_code
                variant_rows[variant_name].append(variant_holdings[["date", "ticker", "rank_no", "weight", "score", "variant", "holding_source", "model_code"]])
                if not variant_changes_df.empty:
                    variant_changes_df["variant"] = variant_name
                    variant_changes_df["model_code"] = model_code
                    variant_changes[variant_name].append(variant_changes_df)

        model_holdings = [pd.concat(baseline_rows, ignore_index=True)]
        for variant_name, frames in variant_rows.items():
            if frames:
                model_holdings.append(pd.concat(frames, ignore_index=True))
        holdings_model = pd.concat(model_holdings, ignore_index=True)
        holdings_frames.append(holdings_model)

        for variant_name, frames in variant_changes.items():
            if frames:
                changes_frames.append(pd.concat(frames, ignore_index=True))

        for variant, grp in holdings_model.groupby("variant"):
            nav = simulate_variant_nav(grp[["date", "ticker", "weight"]], returns_wide)
            if nav.empty:
                continue
            nav["model_code"] = model_code
            nav["variant"] = variant
            nav_rows.extend(compute_perf(nav, model_code, variant))

    holdings_all = pd.concat(holdings_frames, ignore_index=True)
    changes_all = pd.concat(changes_frames, ignore_index=True) if changes_frames else pd.DataFrame()
    perf = pd.DataFrame(nav_rows)
    turnover = turnover_summary(holdings_all)
    quality = new_entry_quality(holdings_all, price_wide, end_maps)
    overlap = overlap_summary(holdings_all)

    headline = (
        perf[perf["period"] == "full_history"][["model_code", "variant", "total_return", "cagr", "mdd", "sharpe"]]
        .merge(turnover[["model_code", "variant", "avg_turnover_ratio"]], on=["model_code", "variant"], how="left")
        .merge(
            quality[quality["horizon"] == "1M"][["model_code", "variant", "avg_forward_return", "winner_rate"]].rename(
                columns={"avg_forward_return": "avg_forward_return_1m", "winner_rate": "winner_rate_1m"}
            ),
            on=["model_code", "variant"],
            how="left",
        )
        .merge(overlap[["model_code", "variant", "avg_overlap_ratio"]], on=["model_code", "variant"], how="left")
        .sort_values(["model_code", "variant"])
    )

    holdings_all.to_csv(OUTDIR / "s3_pit_aux_holdings_history.csv", index=False, encoding="utf-8-sig")
    changes_all.to_csv(OUTDIR / "s3_pit_aux_changes.csv", index=False, encoding="utf-8-sig")
    perf.to_csv(OUTDIR / "s3_pit_aux_performance_summary.csv", index=False, encoding="utf-8-sig")
    turnover.to_csv(OUTDIR / "s3_pit_aux_turnover_summary.csv", index=False, encoding="utf-8-sig")
    quality.to_csv(OUTDIR / "s3_pit_aux_new_entry_quality.csv", index=False, encoding="utf-8-sig")
    overlap.to_csv(OUTDIR / "s3_pit_aux_overlap_summary.csv", index=False, encoding="utf-8-sig")
    headline.to_csv(OUTDIR / "s3_pit_aux_headline.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s3_pit_auxiliary_comparison.md").write_text(build_markdown(headline, perf, turnover, quality, overlap), encoding="utf-8")
    print(f"[OK] wrote {OUTDIR}")


if __name__ == "__main__":
    main()
