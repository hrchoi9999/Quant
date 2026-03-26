from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(r"D:\Quant")
QUANT_SERVICE_DB = PROJECT_ROOT / "data" / "db" / "quant_service.db"
QUANT_SERVICE_DETAIL_DB = PROJECT_ROOT / "data" / "db" / "quant_service_detail.db"
PRICE_DB = PROJECT_ROOT / "data" / "db" / "price.db"
SERVICE_ANALYTICS_DB = PROJECT_ROOT / "data" / "db" / "service_analytics.db"
CHANGE_WEIGHT_EPS = 0.001
REENTRY_GAP_DAYS = 45


@dataclass(frozen=True)
class SourceDbs:
    quant_service: Path = QUANT_SERVICE_DB
    quant_service_detail: Path = QUANT_SERVICE_DETAIL_DB
    price: Path = PRICE_DB
    target: Path = SERVICE_ANALYTICS_DB


def _normalize_ticker(value: object) -> str:
    text = str(value).strip()
    upper = text.upper()
    if upper.lstrip('0') == 'CASH':
        return 'CASH'
    return text.zfill(6) if text.isdigit() else upper


def _read_sql(db_path: Path, query: str, params: tuple | None = None) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(query, conn, params=params or ())
    finally:
        conn.close()


def _write_df(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    df.to_sql(table, conn, if_exists="replace", index=False)


def _fill_missing_weights(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out['weight'] = pd.to_numeric(out['weight'], errors='coerce')
    groups = []
    for _, grp in out.groupby(['run_id', 'date'], sort=False):
        work = grp.copy()
        if work['weight'].notna().any():
            work['weight'] = work['weight'].fillna(0.0)
        else:
            noncash_mask = work['ticker'].astype(str).str.upper() != 'CASH'
            n = int(noncash_mask.sum())
            if n > 0:
                work.loc[noncash_mask, 'weight'] = 1.0 / n
                work.loc[~noncash_mask, 'weight'] = 0.0
            else:
                work['weight'] = 1.0 / max(len(work), 1)
        groups.append(work)
    return pd.concat(groups, ignore_index=True)


def _current_runs(db: Path) -> pd.DataFrame:
    return _read_sql(
        db,
        """
        WITH ranked_completed AS (
            SELECT
                rr.*,
                ROW_NUMBER() OVER (
                    PARTITION BY rr.model_code
                    ORDER BY rr.asof_date DESC, COALESCE(rr.finished_at, rr.created_at) DESC, rr.run_id DESC
                ) AS rn
            FROM run_runs rr
            WHERE rr.status = 'completed'
        ), latest_completed AS (
            SELECT *
            FROM ranked_completed
            WHERE rn = 1
        ), preferred_runs AS (
            SELECT
                lc.model_code,
                COALESCE(pc.published_run_id, lc.run_id) AS run_id,
                pc.published_at,
                pc.data_asof,
                pc.latest_nav,
                pc.latest_drawdown,
                pc.latest_holdings_count,
                pc.latest_rebalance_date,
                pc.risk_grade,
                pc.display_name AS published_display_name,
                mm.display_name AS meta_display_name,
                lc.start_date,
                lc.end_date,
                lc.asof_date,
                lc.status,
                lc.outdir
            FROM latest_completed lc
            LEFT JOIN pub_model_current pc ON pc.model_code = lc.model_code
            LEFT JOIN meta_models mm ON mm.model_code = lc.model_code
        )
        SELECT
            p.model_code,
            p.run_id,
            COALESCE(p.published_display_name, p.meta_display_name, p.model_code) AS display_name,
            p.published_at,
            COALESCE(p.data_asof, p.asof_date) AS data_asof,
            COALESCE(p.latest_nav, s.final_nav) AS latest_nav,
            COALESCE(p.latest_drawdown, s.mdd) AS latest_drawdown,
            p.latest_holdings_count,
            p.latest_rebalance_date,
            p.risk_grade,
            p.start_date,
            p.end_date,
            p.asof_date,
            p.status,
            p.outdir,
            s.cagr,
            s.sharpe,
            s.mdd,
            s.total_return,
            s.turnover,
            s.rebalance_count,
            s.trade_count,
            s.final_nav
        FROM preferred_runs p
        LEFT JOIN run_summary s ON s.run_id = p.run_id
        ORDER BY p.model_code
        """,
    )


def build_model_run_overview(source: SourceDbs) -> pd.DataFrame:
    df = _current_runs(source.quant_service)
    if df.empty:
        return df
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    df["asof_date"] = pd.to_datetime(df["asof_date"], errors="coerce")
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    df["history_days"] = (df["end_date"] - df["start_date"]).dt.days + 1
    return df


def _nav_history_for_runs(source: SourceDbs, run_ids: list[str], run_meta: pd.DataFrame) -> pd.DataFrame:
    if not run_ids:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(run_ids))
    query = f"""
        SELECT
            run_id,
            date,
            nav,
            drawdown,
            holdings_count,
            cash_weight,
            exposure,
            benchmark_nav
        FROM run_nav_daily
        WHERE run_id IN ({placeholders})
        ORDER BY date
    """
    df = _read_sql(source.quant_service_detail, query, tuple(run_ids))
    if df.empty:
        return df
    return df.merge(run_meta[["run_id", "model_code"]], on="run_id", how="left")


def build_weekly_snapshot(source: SourceDbs, overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty:
        return pd.DataFrame()
    nav_df = _nav_history_for_runs(source, overview_df["run_id"].tolist(), overview_df[["run_id", "model_code"]].drop_duplicates())
    if nav_df.empty:
        return nav_df
    nav_df["date"] = pd.to_datetime(nav_df["date"], errors="coerce")
    nav_df["week_end"] = nav_df["date"].dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize())
    nav_df = nav_df.sort_values(["model_code", "date"])
    weekly = (
        nav_df.groupby(["model_code", "run_id", "week_end"], as_index=False)
        .tail(1)
        .rename(columns={"date": "snapshot_date"})
        .reset_index(drop=True)
    )
    weekly["return_1w"] = weekly.groupby("model_code")["nav"].pct_change()
    weekly["drawdown_current"] = weekly["drawdown"]
    return weekly[[
        "model_code",
        "run_id",
        "week_end",
        "snapshot_date",
        "nav",
        "drawdown_current",
        "holdings_count",
        "cash_weight",
        "exposure",
        "benchmark_nav",
        "return_1w",
    ]].copy()


def _instrument_master(source: SourceDbs) -> pd.DataFrame:
    df = _read_sql(
        source.price,
        """
        SELECT ticker, name, asset_type, market
        FROM instrument_master
        """,
    )
    if not df.empty:
        df["ticker"] = df["ticker"].map(_normalize_ticker)
    return df

def _etf_meta(source: SourceDbs) -> pd.DataFrame:
    df = _read_sql(
        source.price,
        """
        SELECT ticker, asset_class, group_key, currency_exposure, is_inverse, is_leveraged
        FROM etf_meta
        """,
    )
    if not df.empty:
        df["ticker"] = df["ticker"].map(_normalize_ticker)
    return df


def _holdings_history_for_runs(source: SourceDbs, run_ids: list[str], run_meta: pd.DataFrame) -> pd.DataFrame:
    if not run_ids:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(run_ids))
    query = f"""
        SELECT
            run_id,
            date,
            ticker,
            rank_no,
            weight,
            score,
            entry_date,
            entry_price,
            current_price,
            cum_return_since_entry,
            reason_summary
        FROM run_holdings_history
        WHERE run_id IN ({placeholders})
        ORDER BY date, ticker
    """
    df = _read_sql(source.quant_service_detail, query, tuple(run_ids))
    if df.empty:
        return df
    df = df.merge(run_meta[["run_id", "model_code"]], on="run_id", how="left")
    df = _fill_missing_weights(df)
    return df


def build_asset_mix_weekly(source: SourceDbs, overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty:
        return pd.DataFrame()
    holdings = _holdings_history_for_runs(source, overview_df["run_id"].tolist(), overview_df[["run_id", "model_code"]].drop_duplicates())
    if holdings.empty:
        return holdings
    master = _instrument_master(source)
    holdings["date"] = pd.to_datetime(holdings["date"], errors="coerce")
    holdings["ticker"] = holdings["ticker"].map(_normalize_ticker)
    holdings = holdings.merge(master, how="left", on="ticker")
    holdings["week_end"] = holdings["date"].dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize())
    latest_dates = holdings.groupby(["model_code", "run_id", "week_end"], as_index=False)["date"].max()
    latest = holdings.merge(latest_dates, on=["model_code", "run_id", "week_end", "date"], how="inner")
    latest["asset_bucket"] = latest["asset_type"].fillna("OTHER").replace({"STOCK": "stock", "ETF": "etf"})
    latest.loc[latest["ticker"].astype(str).str.upper() == "CASH", "asset_bucket"] = "cash"
    grouped = latest.groupby(["model_code", "run_id", "week_end", "asset_bucket"], as_index=False)["weight"].sum()
    pivot = grouped.pivot_table(
        index=["model_code", "run_id", "week_end"],
        columns="asset_bucket",
        values="weight",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    for col in ["stock", "etf", "cash", "OTHER"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    cash_weekly = build_weekly_snapshot(source, overview_df)[["model_code", "run_id", "week_end", "cash_weight"]]
    out = pivot.merge(cash_weekly, on=["model_code", "run_id", "week_end"], how="left")
    out["cash_weight_snapshot"] = out["cash_weight"].fillna(0.0)
    out["cash_weight_holdings"] = out["cash"]
    out["cash_weight"] = out[["cash_weight_snapshot", "cash_weight_holdings"]].max(axis=1)
    invested_sum = out["stock"] + out["etf"] + out["OTHER"]
    target_invested = (1.0 - out["cash_weight"]).clip(lower=0.0)
    scale = (target_invested / invested_sum).where((invested_sum > 0) & (invested_sum > target_invested), 1.0).fillna(1.0)
    out["stock"] = out["stock"] * scale
    out["etf"] = out["etf"] * scale
    out["OTHER"] = out["OTHER"] * scale
    out["other_weight"] = out["OTHER"]
    out["gross_weight_check"] = out["stock"] + out["etf"] + out["other_weight"] + out["cash_weight"]
    return out.rename(columns={"stock": "stock_weight", "etf": "etf_weight"})[[
        "model_code", "run_id", "week_end", "stock_weight", "etf_weight", "cash_weight", "other_weight", "gross_weight_check"
    ]].copy()


def build_change_log_weekly(source: SourceDbs, overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty:
        return pd.DataFrame()
    holdings = _holdings_history_for_runs(source, overview_df["run_id"].tolist(), overview_df[["run_id", "model_code"]].drop_duplicates())
    if holdings.empty:
        return holdings
    master = _instrument_master(source)
    holdings["date"] = pd.to_datetime(holdings["date"], errors="coerce")
    holdings["ticker"] = holdings["ticker"].map(_normalize_ticker)
    holdings = holdings.merge(master[["ticker", "name", "asset_type"]], on="ticker", how="left")
    holdings["week_end"] = holdings["date"].dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize())
    latest_dates = holdings.groupby(["model_code", "run_id", "week_end"], as_index=False)["date"].max()
    weekly = holdings.merge(latest_dates, on=["model_code", "run_id", "week_end", "date"], how="inner")
    weekly = weekly[["model_code", "run_id", "week_end", "ticker", "name", "asset_type", "weight"]].copy()
    weekly = weekly.sort_values(["model_code", "week_end", "ticker"])

    rows = []
    for model_code, model_df in weekly.groupby("model_code"):
        week_keys = list(model_df["week_end"].drop_duplicates().sort_values())
        prev_map: dict[str, float] = {}
        prev_meta_map: dict[str, dict[str, object]] = {}
        run_id = str(model_df["run_id"].iloc[0])
        for week_end in week_keys:
            cur_df = model_df.loc[model_df["week_end"] == week_end].copy()
            cur_map = {str(row["ticker"]): float(row["weight"] or 0.0) for _, row in cur_df.iterrows()}
            cur_meta_map = {
                str(row["ticker"]): {
                    "name": row["name"],
                    "asset_type": row["asset_type"],
                }
                for _, row in cur_df.iterrows()
            }
            tickers = sorted(set(prev_map) | set(cur_map))
            for ticker in tickers:
                prev_w_raw = float(prev_map.get(ticker, 0.0))
                cur_w_raw = float(cur_map.get(ticker, 0.0))
                prev_active = prev_w_raw >= CHANGE_WEIGHT_EPS
                cur_active = cur_w_raw >= CHANGE_WEIGHT_EPS
                delta = cur_w_raw - prev_w_raw

                if not prev_active and not cur_active:
                    continue

                if not prev_active and cur_active:
                    change_type = "new"
                elif prev_active and not cur_active:
                    change_type = "exit"
                else:
                    if abs(delta) < CHANGE_WEIGHT_EPS:
                        continue
                    change_type = "increase" if delta > 0 else "decrease"

                meta = cur_meta_map.get(ticker) or prev_meta_map.get(ticker) or {}
                rows.append(
                    {
                        "model_code": model_code,
                        "run_id": run_id,
                        "week_end": week_end,
                        "ticker": ticker,
                        "name": meta.get("name"),
                        "asset_type": meta.get("asset_type"),
                        "weight_prev": prev_w_raw,
                        "weight_curr": cur_w_raw,
                        "delta_weight": delta,
                        "change_type": change_type,
                        "classification_eps": CHANGE_WEIGHT_EPS,
                        "is_material_change": 1,
                    }
                )
            prev_map = cur_map
            prev_meta_map = cur_meta_map

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.merge(master[["ticker", "name", "asset_type"]].rename(columns={"name": "name_master", "asset_type": "asset_type_master"}), on="ticker", how="left")
    out["name"] = out["name"].fillna(out["name_master"])
    out["asset_type"] = out["asset_type"].fillna(out["asset_type_master"])
    cash_mask = out["ticker"].astype(str).str.upper() == "CASH"
    out.loc[cash_mask, "name"] = out.loc[cash_mask, "name"].fillna("현금")
    out.loc[cash_mask, "asset_type"] = out.loc[cash_mask, "asset_type"].fillna("CASH")
    return out.drop(columns=["name_master", "asset_type_master"])


def build_holding_lifecycle(source: SourceDbs, overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty:
        return pd.DataFrame()
    holdings = _holdings_history_for_runs(source, overview_df["run_id"].tolist(), overview_df[["run_id", "model_code"]].drop_duplicates())
    if holdings.empty:
        return holdings
    master = _instrument_master(source)
    holdings["date"] = pd.to_datetime(holdings["date"], errors="coerce")
    holdings["entry_date"] = pd.to_datetime(holdings["entry_date"], errors="coerce")
    holdings["ticker"] = holdings["ticker"].map(_normalize_ticker)
    holdings = holdings.merge(master[["ticker", "name", "asset_type"]], on="ticker", how="left", suffixes=("", "_master"))
    rows = []
    for (model_code, run_id, ticker), grp in holdings.groupby(["model_code", "run_id", "ticker"]):
        grp = grp.sort_values("date").copy()
        grp["gap_days"] = grp["date"].diff().dt.days.fillna(0)
        grp["episode_break"] = grp["gap_days"] > REENTRY_GAP_DAYS
        grp["episode_no"] = grp["episode_break"].cumsum().astype(int) + 1
        total_episodes = int(grp["episode_no"].max())
        for episode_no, eg in grp.groupby("episode_no"):
            eg = eg.sort_values("date")
            rows.append(
                {
                    "model_code": model_code,
                    "run_id": run_id,
                    "ticker": ticker,
                    "name": eg["name"].dropna().iloc[0] if eg["name"].notna().any() else None,
                    "asset_type": eg["asset_type"].dropna().iloc[0] if eg["asset_type"].notna().any() else None,
                    "first_seen_date": eg["date"].min(),
                    "last_seen_date": eg["date"].max(),
                    "holding_days_observed": int(eg["date"].nunique()),
                    "entry_date_min": eg["entry_date"].min(),
                    "latest_weight": float(eg["weight"].iloc[-1]) if not eg.empty else None,
                    "latest_return_since_entry": float(eg["cum_return_since_entry"].iloc[-1]) if pd.notna(eg["cum_return_since_entry"].iloc[-1]) else None,
                    "latest_reason_summary": eg["reason_summary"].dropna().iloc[-1] if eg["reason_summary"].notna().any() else None,
                    "episode_no": int(episode_no),
                    "total_episodes_for_ticker": total_episodes,
                    "is_current_episode": 1 if int(episode_no) == total_episodes else 0,
                    "reentry_count": max(total_episodes - 1, 0),
                    "gap_rule_days": REENTRY_GAP_DAYS,
                }
            )
    return pd.DataFrame(rows)


def build_structure_metrics_weekly(source: SourceDbs, overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty:
        return pd.DataFrame()
    holdings = _holdings_history_for_runs(source, overview_df["run_id"].tolist(), overview_df[["run_id", "model_code"]].drop_duplicates())
    if holdings.empty:
        return pd.DataFrame()
    holdings["date"] = pd.to_datetime(holdings["date"], errors="coerce")
    holdings["ticker"] = holdings["ticker"].map(_normalize_ticker)
    holdings["week_end"] = holdings["date"].dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize())
    latest_dates = holdings.groupby(["model_code", "run_id", "week_end"], as_index=False)["date"].max()
    weekly = holdings.merge(latest_dates, on=["model_code", "run_id", "week_end", "date"], how="inner")
    weekly = weekly.sort_values(["model_code", "run_id", "week_end", "weight"], ascending=[True, True, True, False]).copy()

    rows = []
    for (model_code, run_id, week_end), grp in weekly.groupby(["model_code", "run_id", "week_end"]):
        weights = grp["weight"].fillna(0.0).astype(float).sort_values(ascending=False).tolist()
        top1 = sum(weights[:1])
        top3 = sum(weights[:3])
        top5 = sum(weights[:5])
        hhi = float(sum(w * w for w in weights))
        rows.append({
            "model_code": model_code,
            "run_id": run_id,
            "week_end": week_end,
            "top1_weight": float(top1),
            "top3_weight": float(top3),
            "top5_weight": float(top5),
            "holdings_hhi": hhi,
        })

    out = pd.DataFrame(rows).sort_values(["model_code", "week_end"]).reset_index(drop=True)
    turnover_vals = []
    for model_code, grp in weekly.groupby("model_code"):
        prev_map: dict[str, float] = {}
        for week_end, week_df in grp.groupby("week_end"):
            cur_map = {str(r["ticker"]): float(r["weight"] or 0.0) for _, r in week_df.iterrows()}
            tickers = sorted(set(prev_map) | set(cur_map))
            turnover = 0.5 * sum(abs(float(cur_map.get(t, 0.0)) - float(prev_map.get(t, 0.0))) for t in tickers)
            turnover_vals.append({
                "model_code": model_code,
                "week_end": week_end,
                "turnover_1w": float(turnover),
            })
            prev_map = cur_map
    turnover_df = pd.DataFrame(turnover_vals)
    if not turnover_df.empty:
        out = out.merge(turnover_df, on=["model_code", "week_end"], how="left")
    else:
        out["turnover_1w"] = pd.NA
    return out


def build_quality_weekly(weekly_snapshot_df: pd.DataFrame, asset_mix_df: pd.DataFrame, structure_df: pd.DataFrame) -> pd.DataFrame:
    if weekly_snapshot_df.empty:
        return pd.DataFrame()
    merged = weekly_snapshot_df.merge(
        asset_mix_df[["model_code", "run_id", "week_end", "stock_weight", "etf_weight"]],
        on=["model_code", "run_id", "week_end"],
        how="left",
    )
    if structure_df is not None and not structure_df.empty:
        merged = merged.merge(
            structure_df[["model_code", "run_id", "week_end", "top1_weight", "top3_weight", "top5_weight", "holdings_hhi", "turnover_1w"]],
            on=["model_code", "run_id", "week_end"],
            how="left",
        )
    merged = merged.sort_values(["model_code", "week_end"]).copy()
    structure_cols = ["top1_weight", "top3_weight", "top5_weight", "holdings_hhi"]
    for col in structure_cols:
        if col in merged.columns:
            merged[col] = merged.groupby("model_code")[col].ffill()
    if "turnover_1w" in merged.columns:
        merged["turnover_1w"] = merged["turnover_1w"].fillna(0.0)
    merged["return_4w"] = merged.groupby("model_code")["nav"].pct_change(4)
    merged["return_12w"] = merged.groupby("model_code")["nav"].pct_change(12)
    merged["return_52w"] = merged.groupby("model_code")["nav"].pct_change(52)
    merged["benchmark_return_4w"] = merged.groupby("model_code")["benchmark_nav"].pct_change(4, fill_method=None)
    merged["benchmark_return_12w"] = merged.groupby("model_code")["benchmark_nav"].pct_change(12, fill_method=None)
    merged["benchmark_return_52w"] = merged.groupby("model_code")["benchmark_nav"].pct_change(52, fill_method=None)
    merged["relative_strength_vs_benchmark_4w"] = merged["return_4w"] - merged["benchmark_return_4w"]
    merged["relative_strength_vs_benchmark_12w"] = merged["return_12w"] - merged["benchmark_return_12w"]
    merged["relative_strength_vs_benchmark_52w"] = merged["return_52w"] - merged["benchmark_return_52w"]
    merged["cash_weight_avg_4w"] = merged.groupby("model_code")["cash_weight"].rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
    merged["holdings_count_avg_4w"] = merged.groupby("model_code")["holdings_count"].rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
    merged["turnover_avg_4w"] = merged.groupby("model_code")["turnover_1w"].rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
    return merged[[
        "model_code", "run_id", "week_end", "nav", "return_1w", "return_4w", "return_12w", "return_52w", "drawdown_current",
        "relative_strength_vs_benchmark_4w", "relative_strength_vs_benchmark_12w", "relative_strength_vs_benchmark_52w",
        "cash_weight_avg_4w", "holdings_count_avg_4w", "stock_weight", "etf_weight", "cash_weight",
        "turnover_1w", "turnover_avg_4w", "top1_weight", "top3_weight", "top5_weight", "holdings_hhi"
    ]].copy()


def build_asset_detail_weekly(source: SourceDbs, overview_df: pd.DataFrame) -> pd.DataFrame:
    if overview_df.empty:
        return pd.DataFrame()
    holdings = _holdings_history_for_runs(source, overview_df["run_id"].tolist(), overview_df[["run_id", "model_code"]].drop_duplicates())
    if holdings.empty:
        return pd.DataFrame()
    master = _instrument_master(source)
    etf_meta = _etf_meta(source)
    holdings["date"] = pd.to_datetime(holdings["date"], errors="coerce")
    holdings["ticker"] = holdings["ticker"].map(_normalize_ticker)
    holdings = holdings.merge(master[["ticker", "asset_type"]], on="ticker", how="left")
    holdings = holdings.merge(etf_meta[["ticker", "group_key", "is_inverse"]], on="ticker", how="left")
    holdings["week_end"] = holdings["date"].dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize())
    latest_dates = holdings.groupby(["model_code", "run_id", "week_end"], as_index=False)["date"].max()
    weekly = holdings.merge(latest_dates, on=["model_code", "run_id", "week_end", "date"], how="inner")

    def classify(row: pd.Series) -> str:
        ticker = str(row.get("ticker") or "").upper()
        if ticker == "CASH":
            return "cash"
        asset_type = str(row.get("asset_type") or "").upper()
        group_key = str(row.get("group_key") or "").lower()
        if asset_type == "STOCK":
            return "stock_equity"
        if asset_type == "ETF":
            if "covered_call" in group_key:
                return "etf_covered_call"
            if "inverse" in group_key or bool(row.get("is_inverse")):
                return "etf_inverse"
            if "bond" in group_key:
                return "etf_bond"
            if "fx" in group_key or "usd" in group_key:
                return "etf_fx"
            if "gold" in group_key or "commodity" in group_key:
                return "etf_gold"
            if "equity" in group_key:
                return "etf_equity"
            return "etf_other"
        return "other"

    weekly["detail_bucket"] = weekly.apply(classify, axis=1)
    grouped = weekly.groupby(["model_code", "run_id", "week_end", "detail_bucket"], as_index=False)["weight"].sum().rename(columns={"weight": "bucket_weight"})
    totals = grouped.groupby(["model_code", "run_id", "week_end"], as_index=False)["bucket_weight"].sum().rename(columns={"bucket_weight": "bucket_total"})
    grouped = grouped.merge(totals, on=["model_code", "run_id", "week_end"], how="left")
    grouped["bucket_weight"] = grouped["bucket_weight"] / grouped["bucket_total"].replace(0, 1.0)
    return grouped.drop(columns=["bucket_total"])


def build_change_activity_weekly(change_log_df: pd.DataFrame, weekly_snapshot_df: pd.DataFrame) -> pd.DataFrame:
    if change_log_df.empty:
        return pd.DataFrame()
    changes = change_log_df.copy()
    changes["week_end"] = pd.to_datetime(changes["week_end"], errors="coerce")
    base = (
        changes.groupby(["model_code", "run_id", "week_end"], as_index=False)
        .agg(
            new_count=("change_type", lambda s: int((s == "new").sum())),
            exit_count=("change_type", lambda s: int((s == "exit").sum())),
            increase_count=("change_type", lambda s: int((s == "increase").sum())),
            decrease_count=("change_type", lambda s: int((s == "decrease").sum())),
            abs_delta_sum=("delta_weight", lambda s: float(s.abs().sum())),
        )
    )
    base["event_count_total"] = base[["new_count", "exit_count", "increase_count", "decrease_count"]].sum(axis=1)
    weekly = weekly_snapshot_df[["model_code", "run_id", "week_end", "holdings_count"]].copy()
    weekly["week_end"] = pd.to_datetime(weekly["week_end"], errors="coerce")
    out = weekly.merge(base, on=["model_code", "run_id", "week_end"], how="left")
    for col in ["new_count", "exit_count", "increase_count", "decrease_count", "event_count_total"]:
        out[col] = out[col].fillna(0).astype(int)
    out["abs_delta_sum"] = out["abs_delta_sum"].fillna(0.0)
    holdings_base = out["holdings_count"].astype(float).where(out["holdings_count"].astype(float) != 0, pd.NA)
    count_ratio = (out["event_count_total"].astype(float) / holdings_base).fillna(0.0)
    weight_ratio = out["abs_delta_sum"].fillna(0.0)
    out["change_intensity_score"] = ((count_ratio * 50.0) + (weight_ratio * 50.0)).clip(lower=0.0, upper=100.0)
    return out[[
        "model_code", "run_id", "week_end", "holdings_count", "new_count", "exit_count", "increase_count", "decrease_count",
        "event_count_total", "abs_delta_sum", "change_intensity_score"
    ]].copy()


def build_change_impact_weekly(change_log_df: pd.DataFrame, lifecycle_df: pd.DataFrame) -> pd.DataFrame:
    if change_log_df.empty or lifecycle_df.empty:
        return pd.DataFrame()
    changes = change_log_df.copy()
    changes["week_end"] = pd.to_datetime(changes["week_end"], errors="coerce")
    lifecycle = lifecycle_df.copy()
    lifecycle["first_seen_date"] = pd.to_datetime(lifecycle["first_seen_date"], errors="coerce")
    lifecycle["last_seen_date"] = pd.to_datetime(lifecycle["last_seen_date"], errors="coerce")
    lifecycle["entry_week_end"] = lifecycle["first_seen_date"].dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize() if pd.notna(p) else pd.NaT)
    lifecycle["exit_week_end"] = lifecycle["last_seen_date"].dt.to_period("W-FRI").apply(lambda p: p.end_time.normalize() if pd.notna(p) else pd.NaT)

    new_events = changes.loc[changes["change_type"] == "new"].merge(
        lifecycle[["model_code", "run_id", "ticker", "name", "asset_type", "entry_week_end", "episode_no", "is_current_episode", "holding_days_observed", "latest_return_since_entry", "first_seen_date", "last_seen_date"]],
        left_on=["model_code", "run_id", "ticker", "week_end"],
        right_on=["model_code", "run_id", "ticker", "entry_week_end"],
        how="left",
        suffixes=("", "_lc"),
    )
    new_events["event_type"] = "new"
    new_events["outcome_status"] = new_events["is_current_episode"].map({1: "active", 0: "closed"}).fillna("unknown")

    exit_events = changes.loc[changes["change_type"] == "exit"].merge(
        lifecycle[["model_code", "run_id", "ticker", "name", "asset_type", "exit_week_end", "episode_no", "is_current_episode", "holding_days_observed", "latest_return_since_entry", "first_seen_date", "last_seen_date"]],
        left_on=["model_code", "run_id", "ticker", "week_end"],
        right_on=["model_code", "run_id", "ticker", "exit_week_end"],
        how="left",
        suffixes=("", "_lc"),
    )
    exit_events["event_type"] = "exit"
    exit_events["outcome_status"] = "exited"

    out = pd.concat([new_events, exit_events], ignore_index=True, sort=False)
    if out.empty:
        return out
    out["name"] = out["name"].fillna(out.get("name_lc"))
    out["asset_type"] = out["asset_type"].fillna(out.get("asset_type_lc"))
    return out[[
        "model_code", "run_id", "week_end", "ticker", "name", "asset_type", "event_type", "delta_weight",
        "episode_no", "is_current_episode", "holding_days_observed", "latest_return_since_entry", "first_seen_date", "last_seen_date", "outcome_status"
    ]].rename(columns={
        "week_end": "event_week_end",
        "latest_return_since_entry": "return_since_entry_observed"
    }).copy()


def build_data_quality_checks(overview_df: pd.DataFrame, asset_mix_df: pd.DataFrame, change_log_df: pd.DataFrame, lifecycle_df: pd.DataFrame, quality_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    model_codes = sorted({str(x) for x in overview_df.get("model_code", pd.Series(dtype=str)).dropna().astype(str)})
    for model_code in model_codes:
        asset_rows = asset_mix_df.loc[asset_mix_df["model_code"] == model_code].copy()
        change_rows = change_log_df.loc[change_log_df["model_code"] == model_code].copy()
        lifecycle_rows = lifecycle_df.loc[lifecycle_df["model_code"] == model_code].copy()
        quality_rows = quality_df.loc[quality_df["model_code"] == model_code].copy()

        if not asset_rows.empty:
            gross_max = float(asset_rows["gross_weight_check"].max())
            gross_min = float(asset_rows["gross_weight_check"].min())
            status = "ok" if gross_min >= -1e-6 and gross_max <= 1.05 else "warn"
            rows.append({"model_code": model_code, "check_name": "asset_mix_gross_weight", "status": status, "metric_value": gross_max, "detail": f"gross_min={gross_min:.6f}, gross_max={gross_max:.6f}"})

        null_name_count = int(change_rows["name"].isna().sum()) if not change_rows.empty else 0
        rows.append({"model_code": model_code, "check_name": "change_log_null_name", "status": "ok" if null_name_count == 0 else "warn", "metric_value": null_name_count, "detail": f"null_name_rows={null_name_count}"})

        if not change_rows.empty:
            noisy_count = int((change_rows["delta_weight"].abs() < CHANGE_WEIGHT_EPS).sum())
            rows.append({"model_code": model_code, "check_name": "change_log_below_threshold", "status": "ok" if noisy_count == 0 else "warn", "metric_value": noisy_count, "detail": f"eps={CHANGE_WEIGHT_EPS}"})

        if not lifecycle_rows.empty:
            reentry_count = int((lifecycle_rows.get("reentry_count", pd.Series(dtype=int)).fillna(0) > 0).sum())
            rows.append({"model_code": model_code, "check_name": "lifecycle_reentries", "status": "ok", "metric_value": reentry_count, "detail": f"gap_rule_days={REENTRY_GAP_DAYS}"})

        if not quality_rows.empty:
            current_dd = quality_rows.sort_values("week_end")["drawdown_current"].iloc[-1]
            rows.append({"model_code": model_code, "check_name": "quality_current_drawdown", "status": "ok", "metric_value": float(current_dd) if pd.notna(current_dd) else None, "detail": "latest weekly drawdown"})

    return pd.DataFrame(rows)


def build_service_analytics(source: SourceDbs = SourceDbs()) -> dict[str, pd.DataFrame]:
    overview = build_model_run_overview(source)
    weekly = build_weekly_snapshot(source, overview)
    asset_mix = build_asset_mix_weekly(source, overview)
    asset_detail = build_asset_detail_weekly(source, overview)
    change_log = build_change_log_weekly(source, overview)
    change_activity = build_change_activity_weekly(change_log, weekly)
    lifecycle = build_holding_lifecycle(source, overview)
    change_impact = build_change_impact_weekly(change_log, lifecycle)
    structure = build_structure_metrics_weekly(source, overview)
    quality = build_quality_weekly(weekly, asset_mix, structure)
    quality_checks = build_data_quality_checks(overview, asset_mix, change_log, lifecycle, quality)
    return {
        "analytics_model_run_overview": overview,
        "analytics_model_weekly_snapshot": weekly,
        "analytics_model_asset_mix_weekly": asset_mix,
        "analytics_model_asset_detail_weekly": asset_detail,
        "analytics_model_change_log": change_log,
        "analytics_model_change_activity_weekly": change_activity,
        "analytics_holding_lifecycle": lifecycle,
        "analytics_model_change_impact_weekly": change_impact,
        "analytics_model_quality_weekly": quality,
        "analytics_data_quality_checks": quality_checks,
    }


def persist_service_analytics(source: SourceDbs = SourceDbs()) -> dict[str, int]:
    frames = build_service_analytics(source)
    source.target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(source.target)
    try:
        for table, df in frames.items():
            _write_df(conn, table, df)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()
    return {table: int(len(df)) for table, df in frames.items()}

