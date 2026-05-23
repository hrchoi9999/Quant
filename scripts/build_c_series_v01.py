from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
QS_DB = ROOT / r"data\db\quant_service.db"
TS_DB = ROOT / r"data\db\tseries_operational.db"
CLASS_DB = ROOT / r"data\db\security_classification.db"
C_DB = ROOT / r"data\db\cseries_relationship.db"
SCHEMA = ROOT / r"src\quant_service\schema_cseries_relationship.sql"
STOCK_UNIVERSE = ROOT / r"data\universe\universe_mix_top400_latest.csv"
ETF_UNIVERSE = ROOT / r"data\universe\universe_etf_master_latest.csv"
REPORT_DIR = ROOT / r"reports\c_series"

MODEL_CODE = "C-REL-V01"
REL_TH = 0.35
LOOKBACK_DAYS = 380
PERSISTENCE_LOOKBACK = 120
PERSISTENCE_WINDOW = 60
MIN_CORR_OBS = 30
TOP_POS_NEG_PER_SOURCE = 10
TOP_NEUTRAL_PER_SOURCE = 3


def _normalize_ticker(value: Any) -> str:
    return str(value).strip().zfill(6)


def _as_float(value: Any) -> float | None:
    if isinstance(value, pd.Series):
        value = value.dropna().iloc[0] if not value.dropna().empty else None
    if value is None or pd.isna(value):
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _corr_value(mat: pd.DataFrame | None, source_id: str, target_id: str) -> float | None:
    if mat is None or source_id not in mat.index or target_id not in mat.columns:
        return None
    return _as_float(mat.loc[source_id, target_id])


def _relation_type(corr: float | None) -> str:
    if corr is None or pd.isna(corr):
        return "Neutral"
    if corr >= REL_TH:
        return "Positive"
    if corr <= -REL_TH:
        return "Negative"
    return "Neutral"


def _direction_sign(relation_type: str) -> int:
    if relation_type == "Positive":
        return 1
    if relation_type == "Negative":
        return -1
    return 0


def _liquidity_score(value: float | None) -> float:
    if value is None or pd.isna(value) or value <= 0:
        return 0.4
    # 20bn KRW reaches about 1.0, but do not make low-liquidity names zero.
    return max(0.25, min(1.0, math.log10(value + 1.0) / math.log10(20_000_000_000.0)))


def _last_valid(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return _as_float(clean.iloc[-1])


def _connect_cdb() -> sqlite3.Connection:
    con = sqlite3.connect(str(C_DB))
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _ensure_column(con, "c_model_overlay_scores", "market_beta_support_score", "REAL")
    _ensure_column(con, "c_model_overlay_scores", "top_market_beta_proxy", "TEXT")
    _ensure_column(con, "c_shadow_tracking", "top_market_beta_proxy", "TEXT")
    return con


def _ensure_column(con: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _price_max_date() -> str:
    with sqlite3.connect(str(PRICE_DB)) as con:
        row = con.execute("SELECT MAX(date) FROM prices_daily").fetchone()
    if not row or not row[0]:
        raise RuntimeError("prices_daily has no max(date)")
    return str(row[0])


def _load_universe(asof: str) -> pd.DataFrame:
    if CLASS_DB.exists():
        with sqlite3.connect(str(CLASS_DB)) as con:
            classified = pd.read_sql_query(
                """
                SELECT ticker, name, asset_type, market, theme_bucket, theme_name_kr
                FROM security_classification_master
                WHERE asof_date = ?
                  AND is_active = 1
                """,
                con,
                params=[asof],
                dtype={"ticker": str},
            )
        if not classified.empty:
            classified["ticker"] = classified["ticker"].map(_normalize_ticker)
            with sqlite3.connect(str(PRICE_DB)) as con:
                etf_meta = pd.read_sql_query(
                    "SELECT ticker, liquidity_20d_value FROM etf_meta",
                    con,
                    dtype={"ticker": str},
                )
            etf_meta["ticker"] = etf_meta["ticker"].map(_normalize_ticker)
            classified = classified.merge(etf_meta, on="ticker", how="left")
            return classified.drop_duplicates("ticker", keep="first")[
                ["ticker", "name", "asset_type", "market", "theme_bucket", "theme_name_kr", "liquidity_20d_value"]
            ].copy()

    stock = pd.read_csv(STOCK_UNIVERSE, dtype={"ticker": str})
    stock["ticker"] = stock["ticker"].map(_normalize_ticker)
    stock["asset_type"] = "STOCK"
    stock["market"] = stock.get("market", "STOCK")

    etf = pd.read_csv(ETF_UNIVERSE, dtype={"ticker": str})
    etf["ticker"] = etf["ticker"].map(_normalize_ticker)
    etf = etf.loc[etf.get("is_active", 1).astype(int) == 1].copy()
    etf["asset_type"] = "ETF"
    etf["market"] = "ETF"

    base = pd.concat(
        [
            stock[["ticker", "name", "asset_type", "market"]],
            etf[["ticker", "name", "asset_type", "market"]],
        ],
        ignore_index=True,
    ).drop_duplicates("ticker", keep="first")

    with sqlite3.connect(str(PRICE_DB)) as con:
        inst = pd.read_sql_query(
            "SELECT ticker, name, asset_type, market FROM instrument_master",
            con,
            dtype={"ticker": str},
        )
        etf_meta = pd.read_sql_query(
            "SELECT ticker, asset_class, group_key, is_inverse, is_leveraged, liquidity_20d_value FROM etf_meta",
            con,
            dtype={"ticker": str},
        )
    inst["ticker"] = inst["ticker"].map(_normalize_ticker)
    etf_meta["ticker"] = etf_meta["ticker"].map(_normalize_ticker)

    base = base.merge(inst.rename(columns={"name": "inst_name", "asset_type": "inst_asset_type", "market": "inst_market"}), on="ticker", how="left")
    base["name"] = base["name"].fillna(base["inst_name"])
    base["market"] = base["market"].fillna(base["inst_market"])
    base = base.merge(etf_meta, on="ticker", how="left")

    with sqlite3.connect(str(TS_DB)) as con:
        labels = pd.read_sql_query(
            """
            SELECT ticker, theme_bucket, theme_name_kr, asof_date
            FROM ts_theme_labels
            WHERE asof_date <= ?
            """,
            con,
            params=[asof],
            dtype={"ticker": str},
        )
    if not labels.empty:
        labels["ticker"] = labels["ticker"].map(_normalize_ticker)
        labels = labels.sort_values(["ticker", "asof_date"]).drop_duplicates("ticker", keep="last")
        base = base.merge(labels[["ticker", "theme_bucket", "theme_name_kr"]], on="ticker", how="left")
    else:
        base["theme_bucket"] = None
        base["theme_name_kr"] = None

    is_etf = base["asset_type"].eq("ETF")
    etf_theme = base["group_key"].fillna(base["asset_class"]).fillna("etf_other")
    base.loc[is_etf, "theme_bucket"] = etf_theme[is_etf]
    base.loc[is_etf, "theme_name_kr"] = base.loc[is_etf, "theme_bucket"]

    stock_fallback = "stock_" + base["market"].fillna("unknown").str.lower()
    base["theme_bucket"] = base["theme_bucket"].fillna(stock_fallback)
    base["theme_name_kr"] = base["theme_name_kr"].fillna(base["theme_bucket"])
    return base.drop_duplicates("ticker", keep="first")[["ticker", "name", "asset_type", "market", "theme_bucket", "theme_name_kr", "liquidity_20d_value"]].copy()


def _load_price_panel(tickers: list[str], asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(PRICE_DB)) as con:
        dates = pd.read_sql_query(
            """
            SELECT DISTINCT date
            FROM prices_daily
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT ?
            """,
            con,
            params=[asof, LOOKBACK_DAYS],
        )["date"].tolist()
        if not dates:
            raise RuntimeError("No price dates for C-series")
        min_date = min(dates)
        placeholders = ",".join(["?"] * len(tickers))
        prices = pd.read_sql_query(
            f"""
            SELECT ticker, date, close, volume, value
            FROM prices_daily
            WHERE date BETWEEN ? AND ?
              AND ticker IN ({placeholders})
              AND close IS NOT NULL
            """,
            con,
            params=[min_date, asof, *tickers],
            dtype={"ticker": str},
        )
    prices["ticker"] = prices["ticker"].map(_normalize_ticker)
    prices["date"] = pd.to_datetime(prices["date"])
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce")
    prices["value"] = pd.to_numeric(prices["value"], errors="coerce")
    prices["value"] = prices["value"].fillna(prices["close"] * prices["volume"])
    return prices.dropna(subset=["close"])


def _pairwise_corr(x: pd.DataFrame, y: pd.DataFrame, window: int, min_obs: int = MIN_CORR_OBS) -> pd.DataFrame:
    xs = x.tail(window)
    ys = y.tail(window)
    xs, ys = xs.align(ys, join="inner", axis=0)
    x_arr = xs.to_numpy(dtype=float)
    y_arr = ys.to_numpy(dtype=float)
    x_mask = ~np.isnan(x_arr)
    y_mask = ~np.isnan(y_arr)
    x0 = np.nan_to_num(x_arr, nan=0.0)
    y0 = np.nan_to_num(y_arr, nan=0.0)
    mx = x_mask.astype(float)
    my = y_mask.astype(float)
    n = mx.T @ my
    sum_x = x0.T @ my
    sum_y = mx.T @ y0
    sum_xy = x0.T @ y0
    sum_x2 = (x0 * x0).T @ my
    sum_y2 = mx.T @ (y0 * y0)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov_num = sum_xy - (sum_x * sum_y / n)
        var_x = sum_x2 - (sum_x * sum_x / n)
        var_y = sum_y2 - (sum_y * sum_y / n)
        corr = cov_num / np.sqrt(var_x * var_y)
    corr[n < min_obs] = np.nan
    corr = np.clip(corr, -1.0, 1.0)
    return pd.DataFrame(corr, index=xs.columns, columns=ys.columns)


def _compute_persistence(src: pd.Series, tgt: pd.Series, current_relation: str) -> tuple[int, float, int, float]:
    joined = pd.concat([src, tgt], axis=1).dropna().tail(PERSISTENCE_LOOKBACK + PERSISTENCE_WINDOW + 10)
    if len(joined) < PERSISTENCE_WINDOW + 5:
        return 0, 0.0, 0, 0.0
    rolling = joined.iloc[:, 0].rolling(PERSISTENCE_WINDOW).corr(joined.iloc[:, 1]).dropna().tail(PERSISTENCE_LOOKBACK)
    if rolling.empty:
        return 0, 0.0, 0, 0.0
    labels = rolling.map(_relation_type)
    current = current_relation
    persistence_days = 0
    for label in reversed(labels.tolist()):
        if label == current:
            persistence_days += 1
        else:
            break
    persistence_ratio = float((labels == current).mean())
    sign = labels.map(_direction_sign)
    nz = sign.loc[sign != 0]
    break_count = int((nz != nz.shift(1)).sum() - 1) if len(nz) > 1 else 0
    break_count = max(0, break_count)
    stability = 1.0 - min(1.0, float(rolling.std(skipna=True) or 0.0))
    return persistence_days, round(persistence_ratio, 6), break_count, round(stability, 6)


def _direction_consistency(row: pd.Series, relation_type: str) -> float:
    sign = _direction_sign(relation_type)
    if sign == 0:
        values = [row.get("corr_20d"), row.get("corr_60d"), row.get("corr_120d")]
        return float(sum(abs(v or 0.0) < REL_TH for v in values) / len(values))
    values = [row.get("corr_20d"), row.get("corr_60d"), row.get("corr_120d")]
    valid = [v for v in values if v is not None and not pd.isna(v)]
    if not valid:
        return 0.0
    return float(sum((v * sign) > 0 for v in valid) / len(valid))


def _rank_select(corr60: pd.DataFrame, source_type: str, target_type: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for source_id, row in corr60.iterrows():
        valid = row.dropna()
        if valid.empty:
            continue
        pos = valid.loc[valid >= REL_TH].sort_values(ascending=False).head(TOP_POS_NEG_PER_SOURCE)
        neg = valid.loc[valid <= -REL_TH].sort_values(ascending=True).head(TOP_POS_NEG_PER_SOURCE)
        neutral = valid.loc[valid.abs() < REL_TH].abs().sort_values(ascending=True).head(TOP_NEUTRAL_PER_SOURCE)
        selected = set(pos.index) | set(neg.index) | set(neutral.index)
        pos_rank = {ticker: idx + 1 for idx, ticker in enumerate(pos.index)}
        neg_rank = {ticker: idx + 1 for idx, ticker in enumerate(neg.index)}
        for target_id in selected:
            records.append(
                {
                    "source_type": source_type,
                    "source_id": source_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "rank_positive": pos_rank.get(target_id),
                    "rank_negative": neg_rank.get(target_id),
                }
            )
    return pd.DataFrame(records)


def _build_edges(asof: str, meta: pd.DataFrame, returns: pd.DataFrame, theme_returns: pd.DataFrame) -> pd.DataFrame:
    stocks = meta.loc[meta["asset_type"] == "STOCK", "ticker"].tolist()
    etfs = meta.loc[meta["asset_type"] == "ETF", "ticker"].tolist()
    assets = meta["ticker"].tolist()
    themes = theme_returns.columns.tolist()
    name_map = dict(zip(meta["ticker"], meta["name"]))
    theme_name_map = {theme: theme for theme in themes}

    matrices: dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame, str, str]] = {
        ("asset", "etf"): (returns[stocks], returns[etfs], "asset", "etf"),
        ("asset", "theme"): (returns[assets], theme_returns, "asset", "theme"),
        ("theme", "theme"): (theme_returns, theme_returns, "theme", "theme"),
    }

    edge_frames: list[pd.DataFrame] = []
    corr_cache: dict[tuple[str, str, int], pd.DataFrame] = {}
    for key, (src_returns, tgt_returns, source_type, target_type) in matrices.items():
        corr60 = _pairwise_corr(src_returns, tgt_returns, 60)
        if source_type == target_type:
            for col in corr60.columns:
                if col in corr60.index:
                    corr60.loc[col, col] = np.nan
        corr_cache[(source_type, target_type, 60)] = corr60
        selected = _rank_select(corr60, source_type, target_type)
        if selected.empty:
            continue
        for window in (20, 120, 252):
            corr_cache[(source_type, target_type, window)] = _pairwise_corr(src_returns, tgt_returns, window)
        edge_frames.append(selected)

    if not edge_frames:
        return pd.DataFrame()
    edges = pd.concat(edge_frames, ignore_index=True).drop_duplicates(["source_type", "source_id", "target_type", "target_id"])

    rows: list[dict[str, Any]] = []
    return_lookup = {"asset": returns, "etf": returns, "theme": theme_returns}
    for edge in edges.itertuples(index=False):
        source_type = str(edge.source_type)
        target_type = str(edge.target_type)
        source_id = str(edge.source_id)
        target_id = str(edge.target_id)
        corr_values = {}
        for window in (20, 60, 120, 252):
            mat = corr_cache.get((source_type, target_type, window))
            corr_values[f"corr_{window}d"] = _corr_value(mat, source_id, target_id)
        relation = _relation_type(corr_values["corr_60d"])
        direction = _direction_consistency(pd.Series(corr_values), relation)
        src_series = return_lookup[source_type][source_id]
        tgt_series = return_lookup[target_type][target_id]
        persistence_days, persistence_ratio, break_count, stability = _compute_persistence(src_series, tgt_series, relation)
        strength = abs(corr_values["corr_60d"] or 0.0)
        persistence_score = max(0.0, min(1.0, (0.45 * persistence_ratio) + (0.35 * min(1.0, persistence_days / 60.0)) + (0.20 * max(0.0, 1.0 - break_count / 8.0))))
        source_liq = meta.loc[meta["ticker"] == source_id, "liquidity_20d_value"]
        target_liq = meta.loc[meta["ticker"] == target_id, "liquidity_20d_value"]
        liq_score = min(
            _liquidity_score(source_liq.iloc[0] if len(source_liq) else None),
            _liquidity_score(target_liq.iloc[0] if len(target_liq) else None),
        )
        confidence = strength * direction * persistence_score * stability * liq_score
        source_name = name_map.get(source_id) if source_type in {"asset", "etf"} else theme_name_map.get(source_id, source_id)
        target_name = name_map.get(target_id) if target_type in {"asset", "etf"} else theme_name_map.get(target_id, target_id)
        rows.append(
            {
                "asof_date": asof,
                "source_type": source_type,
                "source_id": source_id,
                "source_name": source_name,
                "target_type": target_type,
                "target_id": target_id,
                "target_name": target_name,
                "relation_type": relation,
                **corr_values,
                "direction_consistency": round(direction, 6),
                "persistence_days": persistence_days,
                "persistence_ratio_120d": persistence_ratio,
                "break_count_120d": break_count,
                "stability_score": stability,
                "relationship_strength_score": round(strength, 6),
                "relationship_persistence_score": round(persistence_score, 6),
                "relationship_confidence_score": round(confidence, 6),
                "liquidity_score": round(liq_score, 6),
                "rank_positive": edge.rank_positive,
                "rank_negative": edge.rank_negative,
            }
        )
    return pd.DataFrame(rows)


def _latest_s_holdings(asof: str) -> pd.DataFrame:
    with sqlite3.connect(str(QS_DB)) as con:
        df = pd.read_sql_query(
            """
            SELECT h.model_code, h.asof_date, h.ticker, h.weight, h.score, h.rank_no
            FROM pub_model_current_holdings h
            JOIN pub_model_current c
              ON c.model_code = h.model_code
             AND c.data_asof = h.asof_date
            WHERE h.asof_date <= ?
            """,
            con,
            params=[asof],
            dtype={"ticker": str},
        )
    if df.empty:
        return df
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    df = df.sort_values(["model_code", "asof_date", "rank_no"]).drop_duplicates(["model_code", "ticker"], keep="last")
    df["scope"] = "S"
    df["base_bucket"] = df["rank_no"].map(lambda x: f"rank_{int(x)}" if pd.notna(x) else None)
    return df.rename(columns={"model_code": "base_model_code", "score": "base_score"})


def _latest_t_candidates(asof: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    with sqlite3.connect(str(TS_DB)) as con:
        for table, bucket_col in [("ts_candidates_latest", "candidate_bucket"), ("ts_rolling_watchlist_latest", "watch_status")]:
            df = pd.read_sql_query(
                f"""
                SELECT *
                FROM {table}
                WHERE asof_date <= ?
                """,
                con,
                params=[asof],
                dtype={"ticker": str},
            )
            if df.empty:
                continue
            df["ticker"] = df["ticker"].map(_normalize_ticker)
            latest_dates = df.groupby("model_code")["asof_date"].max().to_dict()
            df = df.loc[df.apply(lambda r: r["asof_date"] == latest_dates.get(r["model_code"]), axis=1)].copy()
            df["scope"] = "T"
            df["base_model_code"] = df["model_code"]
            df["base_bucket"] = df[bucket_col]
            df["base_score"] = pd.to_numeric(df.get("stage2_prob"), errors="coerce").fillna(pd.to_numeric(df.get("stage1_prob"), errors="coerce"))
            frames.append(df[["scope", "base_model_code", "asof_date", "ticker", "name", "base_bucket", "base_score"]])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(["scope", "base_model_code", "ticker"], keep="first")


def _build_overlay(asof: str, meta: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    s = _latest_s_holdings(asof)
    t = _latest_t_candidates(asof)
    candidates = pd.concat(
        [
            s[["scope", "base_model_code", "asof_date", "ticker", "base_bucket", "base_score"]] if not s.empty else pd.DataFrame(),
            t[["scope", "base_model_code", "asof_date", "ticker", "base_bucket", "base_score"]] if not t.empty else pd.DataFrame(),
        ],
        ignore_index=True,
    )
    if candidates.empty:
        return pd.DataFrame()
    name_map = dict(zip(meta["ticker"], meta["name"]))
    theme_map = dict(zip(meta["ticker"], meta["theme_bucket"]))
    non_thematic_positive_buckets = {
        "equity_kr_broad",
        "equity_us",
        "equity_global",
        "bond_cash",
        "commodity_fx",
        "multi_asset_allocation",
        "inverse_leverage",
        "etf_other",
    }
    market_beta_buckets = {"equity_kr_broad", "equity_us", "equity_global"}
    edge_map = {ticker: frame for ticker, frame in edges.loc[edges["source_type"] == "asset"].groupby("source_id")}
    rows: list[dict[str, Any]] = []
    for item in candidates.itertuples(index=False):
        ticker = _normalize_ticker(item.ticker)
        frame = edge_map.get(ticker, pd.DataFrame())
        positive = frame.loc[frame["relation_type"] == "Positive"].sort_values("relationship_confidence_score", ascending=False) if not frame.empty else pd.DataFrame()
        negative = frame.loc[frame["relation_type"] == "Negative"].sort_values("relationship_confidence_score", ascending=False) if not frame.empty else pd.DataFrame()
        pos_etf = positive.loc[positive["target_type"] == "etf"] if not positive.empty else pd.DataFrame()
        neg_etf = negative.loc[negative["target_type"] == "etf"] if not negative.empty else pd.DataFrame()
        pos_theme = positive.loc[positive["target_type"] == "theme"] if not positive.empty else pd.DataFrame()
        if not pos_etf.empty:
            pos_etf = pos_etf.copy()
            pos_etf["target_theme_bucket"] = pos_etf["target_id"].map(theme_map)
        if not neg_etf.empty:
            neg_etf = neg_etf.copy()
            neg_etf["target_theme_bucket"] = neg_etf["target_id"].map(theme_map)
        thematic_pos_etf = pos_etf.loc[~pos_etf["target_theme_bucket"].isin(non_thematic_positive_buckets)] if not pos_etf.empty else pd.DataFrame()
        broad_pos_etf = pos_etf.loc[pos_etf["target_theme_bucket"].isin(market_beta_buckets)] if not pos_etf.empty else pd.DataFrame()
        etf_support = float(thematic_pos_etf["relationship_confidence_score"].head(3).mean()) if not thematic_pos_etf.empty else 0.0
        broad_support = float(broad_pos_etf["relationship_confidence_score"].head(3).mean()) if not broad_pos_etf.empty else 0.0
        theme_support = float(pos_theme["relationship_confidence_score"].head(3).mean()) if not pos_theme.empty else 0.0
        hedge_risk = float(neg_etf["relationship_confidence_score"].abs().head(3).mean()) if not neg_etf.empty else 0.0
        pos_count = int((positive["relationship_confidence_score"].abs() >= 0.05).sum()) if not positive.empty else 0
        neg_count = int((negative["relationship_confidence_score"].abs() >= 0.05).sum()) if not negative.empty else 0
        concentration = min(1.0, max(0.0, pos_count / 20.0))
        overlay = max(0.0, min(1.0, (0.45 * etf_support) + (0.25 * theme_support) + (0.10 * broad_support) + (0.20 * concentration) - (0.15 * hedge_risk)))
        top_pos_frame = thematic_pos_etf
        top_neg_frame = neg_etf
        top_pos = None if top_pos_frame.empty else f"{top_pos_frame.iloc[0]['target_id']} {top_pos_frame.iloc[0]['target_name']}"
        top_market = None if broad_pos_etf.empty else f"{broad_pos_etf.iloc[0]['target_id']} {broad_pos_etf.iloc[0]['target_name']}"
        top_neg = None if top_neg_frame.empty else f"{top_neg_frame.iloc[0]['target_id']} {top_neg_frame.iloc[0]['target_name']}"
        avg_persist = positive["relationship_persistence_score"].head(5).mean() if not positive.empty else 0.0
        if overlay >= 0.20 and avg_persist >= 0.55:
            status = "supported"
        elif hedge_risk >= 0.20:
            status = "hedge_risk"
        elif overlay >= 0.10:
            status = "watch"
        else:
            status = "neutral"
        rows.append(
            {
                "asof_date": asof,
                "scope": item.scope,
                "base_model_code": item.base_model_code,
                "ticker": ticker,
                "name": name_map.get(ticker, ticker),
                "base_bucket": item.base_bucket,
                "base_score": _as_float(item.base_score),
                "positive_relation_count": pos_count,
                "negative_relation_count": neg_count,
                "theme_support_score": round(theme_support, 6),
                "etf_support_score": round(etf_support, 6),
                "market_beta_support_score": round(broad_support, 6),
                "hedge_risk_score": round(hedge_risk, 6),
                "cluster_concentration_score": round(concentration, 6),
                "c_overlay_score": round(overlay, 6),
                "final_adjusted_score": round((_as_float(item.base_score) or 0.0) + overlay, 6),
                "top_positive_etf": top_pos,
                "top_market_beta_proxy": top_market,
                "top_negative_etf": top_neg,
                "relationship_status": status,
                "notes": "C-REL-V01 shadow overlay; does not change holdings.",
            }
        )
    return pd.DataFrame(rows)


def _write_table(con: sqlite3.Connection, table: str, df: pd.DataFrame, asof: str) -> None:
    con.execute(f"DELETE FROM {table} WHERE asof_date = ?", (asof,))
    if not df.empty:
        df.to_sql(table, con, if_exists="append", index=False)
    con.commit()


def _write_summary(asof: str, meta: pd.DataFrame, edges: pd.DataFrame, overlay: pd.DataFrame) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    summary = {
        "asof_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "asset_count": int(len(meta)),
        "stock_count": int((meta["asset_type"] == "STOCK").sum()),
        "etf_count": int((meta["asset_type"] == "ETF").sum()),
        "edge_count": int(len(edges)),
        "edge_relation_counts": edges["relation_type"].value_counts().to_dict() if not edges.empty else {},
        "overlay_count": int(len(overlay)),
        "overlay_scope_counts": overlay["scope"].value_counts().to_dict() if not overlay.empty else {},
    }
    (REPORT_DIR / f"c_series_v01_summary_{token}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    top_edges = edges.sort_values("relationship_confidence_score", ascending=False).head(15) if not edges.empty else pd.DataFrame()
    top_overlay = overlay.sort_values("c_overlay_score", ascending=False).head(20) if not overlay.empty else pd.DataFrame()
    top_edges.to_csv(REPORT_DIR / f"c_series_v01_top_edges_{token}.csv", index=False, encoding="utf-8-sig")
    top_overlay.to_csv(REPORT_DIR / f"c_series_v01_top_overlay_{token}.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# C-series V01 Analysis Summary",
        "",
        f"- asof_date: {asof}",
        f"- asset_count: {summary['asset_count']}",
        f"- stock_count: {summary['stock_count']}",
        f"- etf_count: {summary['etf_count']}",
        f"- edge_count: {summary['edge_count']}",
        f"- overlay_count: {summary['overlay_count']}",
        f"- edge_relation_counts: {summary['edge_relation_counts']}",
        "",
        "## Top Relationship Edges",
        "",
    ]
    for row in top_edges.itertuples(index=False):
        lines.append(
            f"- {row.source_name} -> {row.target_name}: {row.relation_type}, corr60={row.corr_60d}, persistence={row.persistence_days}d, confidence={row.relationship_confidence_score}"
        )
    lines += ["", "## Top S/T Overlay Scores", ""]
    for row in top_overlay.itertuples(index=False):
        lines.append(
            f"- {row.scope}/{row.base_model_code} {row.name}({row.ticker}): overlay={row.c_overlay_score}, status={row.relationship_status}, thematic_pos={row.top_positive_etf}, market_beta={row.top_market_beta_proxy}, neg={row.top_negative_etf}"
        )
    (REPORT_DIR / f"c_series_v01_summary_{token}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build C-series relationship V01 mart, edges, and S/T overlay scores.")
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD. Defaults to price.db max(date).")
    args = ap.parse_args()
    asof = args.asof or _price_max_date()
    started = datetime.now().isoformat(timespec="seconds")
    run_id = f"{MODEL_CODE}:{asof}:relationship_refresh"

    meta = _load_universe(asof)
    prices = _load_price_panel(meta["ticker"].tolist(), asof)
    close = prices.pivot_table(index="date", columns="ticker", values="close", aggfunc="last").sort_index()
    volume = prices.pivot_table(index="date", columns="ticker", values="volume", aggfunc="last").sort_index()
    value = prices.pivot_table(index="date", columns="ticker", values="value", aggfunc="last").sort_index()
    returns = close.pct_change(fill_method=None)

    last_date = close.index.max().strftime("%Y-%m-%d")
    latest_close = close.ffill().iloc[-1]
    latest_volume = volume.ffill().iloc[-1]
    latest_value = value.ffill().iloc[-1]
    # Stock and ETF feeds can have different latest dates. Use each ticker's
    # latest valid observation instead of dropping whole asset classes.
    daily = returns.apply(_last_valid)
    weekly = close.apply(lambda s: _last_valid(s.dropna().pct_change(5, fill_method=None)))
    monthly = close.apply(lambda s: _last_valid(s.dropna().pct_change(21, fill_method=None)))
    vol20 = returns.rolling(20).std().apply(_last_valid)
    liq20 = value.rolling(20).mean().apply(_last_valid)
    valid_obs = returns.tail(LOOKBACK_DAYS).notna().sum()

    mart = meta.copy()
    mart["asof_date"] = asof
    mart["close"] = mart["ticker"].map(latest_close)
    mart["volume"] = mart["ticker"].map(latest_volume)
    mart["trading_value"] = mart["ticker"].map(latest_value)
    mart["daily_return"] = mart["ticker"].map(daily)
    mart["weekly_return"] = mart["ticker"].map(weekly)
    mart["monthly_return"] = mart["ticker"].map(monthly)
    mart["vol_20d"] = mart["ticker"].map(vol20)
    mart["liquidity_20d_value"] = mart["ticker"].map(liq20).fillna(mart["liquidity_20d_value"])
    mart["data_quality_flag"] = np.where(
        mart["ticker"].map(valid_obs).fillna(0) >= MIN_CORR_OBS,
        "ok",
        "insufficient_return_history",
    )
    mart = mart[
        [
            "asof_date", "ticker", "name", "asset_type", "market", "theme_bucket", "theme_name_kr", "close",
            "volume", "trading_value", "daily_return", "weekly_return", "monthly_return", "vol_20d",
            "liquidity_20d_value", "data_quality_flag",
        ]
    ]

    theme_members = meta.set_index("ticker")["theme_bucket"].to_dict()
    theme_returns = returns.rename(columns=theme_members).T.groupby(level=0).mean().T
    theme_latest = mart.groupby("theme_bucket", as_index=False).agg(
        member_count=("ticker", "count"),
        avg_daily_return=("daily_return", "mean"),
        avg_weekly_return=("weekly_return", "mean"),
        median_weekly_return=("weekly_return", "median"),
        positive_ratio=("weekly_return", lambda s: float((s > 0).mean())),
        negative_ratio=("weekly_return", lambda s: float((s < 0).mean())),
        dispersion_score=("weekly_return", "std"),
        liquidity_sum=("liquidity_20d_value", "sum"),
    )
    theme_latest.insert(0, "asof_date", asof)

    valid_return_cols = mart.loc[mart["data_quality_flag"] == "ok", "ticker"].tolist()
    returns_for_edges = returns[valid_return_cols]
    meta_for_edges = meta.loc[meta["ticker"].isin(valid_return_cols)].copy()
    meta_for_edges = meta_for_edges.merge(mart[["ticker", "liquidity_20d_value"]], on="ticker", how="left", suffixes=("", "_mart"))
    meta_for_edges["liquidity_20d_value"] = meta_for_edges["liquidity_20d_value_mart"].fillna(meta_for_edges["liquidity_20d_value"])
    meta_for_edges = meta_for_edges.drop(columns=["liquidity_20d_value_mart"])
    edges = _build_edges(asof, meta_for_edges, returns_for_edges, theme_returns)
    overlay = _build_overlay(asof, meta_for_edges, edges)
    shadow = overlay[
        [
            "asof_date", "scope", "base_model_code", "ticker", "name", "base_bucket", "c_overlay_score",
            "relationship_status", "top_positive_etf", "top_market_beta_proxy", "top_negative_etf",
        ]
    ].copy() if not overlay.empty else pd.DataFrame()

    con = _connect_cdb()
    try:
        con.execute("DELETE FROM c_runs WHERE run_id = ?", (run_id,))
        con.execute(
            """
            INSERT INTO c_runs (
              run_id, asof_date, model_code, run_type, status, input_price_max_date,
              stock_universe_count, etf_universe_count, started_at, finished_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                asof,
                MODEL_CODE,
                "relationship_refresh",
                "success",
                last_date,
                int((meta["asset_type"] == "STOCK").sum()),
                int((meta["asset_type"] == "ETF").sum()),
                started,
                datetime.now().isoformat(timespec="seconds"),
                "C-REL-V01 baseline relationship layer. Shadow only; does not change S/T holdings.",
            ),
        )
        _write_table(con, "c_return_series", mart, asof)
        _write_table(con, "c_theme_return_series", theme_latest, asof)
        _write_table(con, "c_relationship_edges", edges, asof)
        _write_table(con, "c_model_overlay_scores", overlay, asof)
        _write_table(con, "c_shadow_tracking", shadow, asof)
    finally:
        con.close()

    _write_summary(asof, meta, edges, overlay)
    print(
        json.dumps(
            {
                "db": str(C_DB),
                "asof": asof,
                "assets": len(meta),
                "return_rows": len(mart),
                "theme_rows": len(theme_latest),
                "edge_rows": len(edges),
                "overlay_rows": len(overlay),
                "report_dir": str(REPORT_DIR),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
