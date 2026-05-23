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
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_selection_gap"
HORIZONS = {"1M": 21, "3M": 63}
MODELS = ("S2", "S3", "S3_CORE2")


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def load_prices() -> pd.DataFrame:
    px = read_sql(PRICE_DB, "SELECT ticker, date, close FROM prices_daily WHERE close IS NOT NULL", parse_dates=["date"])
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    return px.dropna(subset=["close"]).sort_values(["ticker", "date"]).reset_index(drop=True)


def trading_maps(px: pd.DataFrame) -> dict[str, dict[pd.Timestamp, pd.Timestamp]]:
    dates = sorted(pd.to_datetime(px["date"].dropna().unique()))
    out: dict[str, dict[pd.Timestamp, pd.Timestamp]] = {}
    for label, step in HORIZONS.items():
        out[label] = {pd.Timestamp(dates[i]): pd.Timestamp(dates[i + step]) for i in range(len(dates) - step)}
    return out


def latest_runs() -> dict[str, str]:
    df = read_sql(
        QS_DB,
        """
        SELECT model_code, published_run_id
        FROM pub_model_current
        WHERE model_code IN ('S2','S3','S3_CORE2')
        """,
    )
    return dict(zip(df["model_code"], df["published_run_id"]))


def load_universe() -> pd.DataFrame:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    if "mcap" in df.columns:
        df["mcap"] = pd.to_numeric(df["mcap"], errors="coerce")
    return df[["ticker", "name", "market", "mcap"]].copy()


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
    price_feat["breakout60"] = pd.to_numeric(price_feat["breakout60"], errors="coerce").fillna(0)
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


def pick_latest_fund_asof(fund_df: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    work = fund_df[fund_df["available_from"] <= asof].copy()
    if work.empty:
        return work
    return work.sort_values(["ticker", "available_from", "date"]).groupby("ticker", as_index=False).tail(1)


def selected_table(model_code: str, run_id: str) -> pd.DataFrame:
    table_map = {
        "S2": "run_signal_details_s2",
        "S3": "run_signal_details_s3",
        "S3_CORE2": "run_signal_details_s3_core2",
    }
    table = table_map[model_code]
    df = read_sql(QS_DETAIL_DB, f"SELECT date, ticker FROM {table} WHERE run_id=?", params=(run_id,), parse_dates=["date"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df


def build_s2_candidates(
    selected: pd.DataFrame,
    universe: pd.DataFrame,
    price_feat: pd.DataFrame,
    fund_feat: pd.DataFrame,
) -> pd.DataFrame:
    s2_fund = read_sql(
        FUND_DB,
        """
        SELECT date, ticker, growth_score AS s2_growth_score, score_rank, valid_fund
        FROM s2_fund_scores_monthly
        """,
        parse_dates=["date"],
    )
    s2_fund["ticker"] = s2_fund["ticker"].astype(str).str.zfill(6)
    s2_fund["s2_growth_score"] = pd.to_numeric(s2_fund["s2_growth_score"], errors="coerce")
    s2_fund["score_rank"] = pd.to_numeric(s2_fund["score_rank"], errors="coerce")
    s2_fund["valid_fund"] = pd.to_numeric(s2_fund["valid_fund"], errors="coerce").fillna(0).astype(int)

    rows = []
    for dt in sorted(selected["date"].dropna().unique()):
        dt = pd.Timestamp(dt)
        fund_date = s2_fund.loc[s2_fund["date"] <= dt, "date"].max()
        if pd.isna(fund_date):
            continue
        fs = s2_fund[(s2_fund["date"] == fund_date) & (s2_fund["valid_fund"] == 1)].copy()
        pf = price_feat[price_feat["date"] == dt].copy()
        common_fund = pick_latest_fund_asof(fund_feat, dt)
        snap = (
            universe.merge(fs[["ticker", "s2_growth_score", "score_rank"]], on="ticker", how="inner")
            .merge(pf, on=["ticker"], how="left", suffixes=("", "_px"))
            .merge(common_fund[["ticker", "growth_score", "fund_accel_score"]], on="ticker", how="left")
        )
        snap["date"] = dt
        sel_set = set(selected.loc[selected["date"] == dt, "ticker"])
        snap["selected"] = snap["ticker"].isin(sel_set).astype(int)
        snap["score_value"] = snap["s2_growth_score"]
        rows.append(
            snap[
                [
                    "date",
                    "ticker",
                    "name",
                    "market",
                    "mcap",
                    "selected",
                    "score_value",
                    "s2_growth_score",
                    "score_rank",
                    "growth_score",
                    "fund_accel_score",
                    "mom20",
                    "vol_ratio_20",
                    "breakout60",
                    "trend_up",
                    "ma_gap_60",
                ]
            ].copy()
        )
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out["model_code"] = "S2"
    return out


def build_s3_like_candidates(
    model_code: str,
    selected: pd.DataFrame,
    universe: pd.DataFrame,
    price_feat: pd.DataFrame,
    fund_feat: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for dt in sorted(selected["date"].dropna().unique()):
        dt = pd.Timestamp(dt)
        pf = price_feat[price_feat["date"] == dt].copy()
        if pf.empty:
            continue
        fs = pick_latest_fund_asof(fund_feat, dt)
        snap = universe.merge(pf, on="ticker", how="left").merge(
            fs[["ticker", "growth_score", "fund_accel_score"]], on="ticker", how="left"
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
        snap["date"] = dt
        sel_set = set(selected.loc[selected["date"] == dt, "ticker"])
        snap["selected"] = snap["ticker"].isin(sel_set).astype(int)
        rows.append(
            snap[
                [
                    "date",
                    "ticker",
                    "name",
                    "market",
                    "mcap",
                    "selected",
                    "score_value",
                    "growth_score",
                    "fund_accel_score",
                    "mom20",
                    "vol_ratio_20",
                    "breakout60",
                    "trend_up",
                    "ma_gap_60",
                ]
            ].copy()
        )
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out["model_code"] = model_code
    return out


def attach_forward_returns(base: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    maps = trading_maps(px)
    px_start = px.rename(columns={"close": "entry_close"})
    px_end = px.rename(columns={"date": "end_date", "close": "end_close"})
    frames = []
    for horizon, mapping in maps.items():
        frame = base.copy()
        frame["horizon"] = horizon
        frame["end_date"] = pd.to_datetime(frame["date"]).map(mapping)
        frame = frame[frame["end_date"].notna()].copy()
        if frame.empty:
            continue
        frame = frame.merge(px_start, on=["ticker", "date"], how="left")
        frame = frame.merge(px_end, on=["ticker", "end_date"], how="left")
        frame["forward_return"] = frame["end_close"] / frame["entry_close"] - 1.0
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def classify_groups(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["forward_return_pct_rank"] = work.groupby(["model_code", "horizon", "date"])["forward_return"].rank(pct=True, method="average")
    conditions = [
        (work["selected"] == 1) & (work["forward_return"] > 0),
        (work["selected"] == 1) & (work["forward_return"] <= 0),
        (work["selected"] == 0) & (work["forward_return"] > 0) & (work["forward_return_pct_rank"] >= 0.90),
    ]
    labels = ["selected_winner", "selected_loser", "missed_winner"]
    work["diagnostic_group"] = np.select(conditions, labels, default="other")
    return work


def summarize_groups(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    target = df[df["diagnostic_group"] != "other"].copy()
    summary = (
        target.groupby(["model_code", "horizon", "diagnostic_group"], dropna=False)
        .agg(
            n_obs=("ticker", "size"),
            n_dates=("date", "nunique"),
            avg_forward_return=("forward_return", "mean"),
            median_forward_return=("forward_return", "median"),
            avg_score=("score_value", "mean"),
            avg_growth_score=("growth_score", "mean"),
            avg_s2_growth_score=("s2_growth_score", "mean"),
            avg_fund_accel=("fund_accel_score", "mean"),
            avg_mom20=("mom20", "mean"),
            avg_vol_ratio_20=("vol_ratio_20", "mean"),
            breakout_rate=("breakout60", "mean"),
            trend_up_rate=("trend_up", "mean"),
            avg_ma_gap_60=("ma_gap_60", "mean"),
            avg_mcap=("mcap", "mean"),
        )
        .reset_index()
    )

    comp_rows = []
    compare_cols = [
        "avg_score",
        "avg_growth_score",
        "avg_s2_growth_score",
        "avg_fund_accel",
        "avg_mom20",
        "avg_vol_ratio_20",
        "breakout_rate",
        "trend_up_rate",
        "avg_ma_gap_60",
    ]
    for (model_code, horizon), sub in summary.groupby(["model_code", "horizon"]):
        pivot = sub.set_index("diagnostic_group")
        if {"selected_winner", "selected_loser"}.issubset(pivot.index):
            row = {"model_code": model_code, "horizon": horizon, "comparison": "winner_minus_loser"}
            for col in compare_cols:
                row[col] = pivot.at["selected_winner", col] - pivot.at["selected_loser", col]
            comp_rows.append(row)
        if {"missed_winner", "selected_loser"}.issubset(pivot.index):
            row = {"model_code": model_code, "horizon": horizon, "comparison": "missed_winner_minus_loser"}
            for col in compare_cols:
                row[col] = pivot.at["missed_winner", col] - pivot.at["selected_loser", col]
            comp_rows.append(row)
    return summary, pd.DataFrame(comp_rows)


def top_examples(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    target = df[df["diagnostic_group"].isin(["selected_loser", "missed_winner"])].copy()
    losers = (
        target[target["diagnostic_group"] == "selected_loser"]
        .sort_values(["model_code", "horizon", "forward_return", "date"], ascending=[True, True, True, False])
        .groupby(["model_code", "horizon"], as_index=False)
        .head(15)
    )
    missed = (
        target[target["diagnostic_group"] == "missed_winner"]
        .sort_values(["model_code", "horizon", "forward_return", "date"], ascending=[True, True, False, False])
        .groupby(["model_code", "horizon"], as_index=False)
        .head(15)
    )
    return losers, missed


def build_md(summary: pd.DataFrame, comp: pd.DataFrame, losers: pd.DataFrame, missed: pd.DataFrame) -> str:
    lines = [
        "# S-Series Selection Gap Diagnostic",
        "",
        "- analysis focus: `S2`, `S3`, `S3_CORE2`",
        "- primary horizons: `1M`, `3M`",
        "- group rule",
        "  - `selected_winner`: selected and forward return > 0",
        "  - `selected_loser`: selected and forward return <= 0",
        "  - `missed_winner`: not selected and same-date forward return top 10% with positive return",
        "",
    ]

    lines.append("## Group Summary")
    lines.append("| Model | Horizon | Group | N | Avg Return | Avg Score | Avg Mom20 | Breakout Rate | Trend Up Rate |")
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.model_code} | {row.horizon} | {row.diagnostic_group} | {row.n_obs} | {row.avg_forward_return:.2%} | "
            f"{row.avg_score if pd.notna(row.avg_score) else '-'} | "
            f"{row.avg_mom20 if pd.notna(row.avg_mom20) else '-'} | "
            f"{row.breakout_rate:.2%} | {row.trend_up_rate:.2%} |"
        )
    lines.append("")

    lines.append("## Feature Gap")
    for (model_code, horizon), sub in comp.groupby(["model_code", "horizon"], sort=True):
        lines.append(f"### {model_code} {horizon}")
        for row in sub.itertuples(index=False):
            lines.append(
                f"- `{row.comparison}`: mom20 `{row.avg_mom20:+.4f}`, vol_ratio `{row.avg_vol_ratio_20:+.4f}`, "
                f"breakout `{row.breakout_rate:+.2%}`, trend_up `{row.trend_up_rate:+.2%}`, ma_gap `{row.avg_ma_gap_60:+.2%}`"
            )
        lines.append("")

    lines.append("## Top Selected Losers")
    for (model_code, horizon), sub in losers.groupby(["model_code", "horizon"], sort=True):
        lines.append(f"### {model_code} {horizon}")
        for row in sub.itertuples(index=False):
            lines.append(
                f"- `{pd.Timestamp(row.date).strftime('%Y-%m-%d')}` `{row.ticker}` `{row.name}` "
                f"return `{row.forward_return:.2%}`, score `{row.score_value:.4f}`"
            )
        lines.append("")

    lines.append("## Top Missed Winners")
    for (model_code, horizon), sub in missed.groupby(["model_code", "horizon"], sort=True):
        lines.append(f"### {model_code} {horizon}")
        for row in sub.itertuples(index=False):
            lines.append(
                f"- `{pd.Timestamp(row.date).strftime('%Y-%m-%d')}` `{row.ticker}` `{row.name}` "
                f"return `{row.forward_return:.2%}`, score `{row.score_value:.4f}`"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    runs = latest_runs()
    universe = load_universe()
    price_feat, fund_feat = load_common_features()
    prices = load_prices()

    frames = []
    for model_code in MODELS:
        selected = selected_table(model_code, runs[model_code])
        if model_code == "S2":
            frames.append(build_s2_candidates(selected, universe, price_feat, fund_feat))
        else:
            frames.append(build_s3_like_candidates(model_code, selected, universe, price_feat, fund_feat))
    base = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)
    detail = attach_forward_returns(base, prices)
    detail = detail[detail["horizon"].isin(["1M", "3M"])].copy()
    detail = classify_groups(detail)

    summary, comp = summarize_groups(detail)
    losers, missed = top_examples(detail)

    detail.to_csv(OUTDIR / "s_series_selection_gap_detail.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTDIR / "s_series_selection_gap_summary.csv", index=False, encoding="utf-8-sig")
    comp.to_csv(OUTDIR / "s_series_selection_gap_feature_comparison.csv", index=False, encoding="utf-8-sig")
    losers.to_csv(OUTDIR / "s_series_top_selected_losers.csv", index=False, encoding="utf-8-sig")
    missed.to_csv(OUTDIR / "s_series_top_missed_winners.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "s_series_selection_gap_review.md").write_text(build_md(summary, comp, losers, missed), encoding="utf-8")
    print(f"[OK] wrote {OUTDIR}")


if __name__ == "__main__":
    main()
