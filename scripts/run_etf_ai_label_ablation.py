from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quant_market.market_handoff import context_dir, market_context_frame

QM_CONTEXT_DIR = context_dir()
PRICE_DB = ROOT / r"data\db\price.db"
REPORT_DIR = ROOT / r"reports\etf_ai_role_allocation_v01"
MODEL_CODE = "AI-ETF-ROLE-ALLOCATION-V01"
RANDOM_STATE = 42
DISTRIBUTION_CSV_CANDIDATES = [
    ROOT / r"data\etf_distributions.csv",
    ROOT / r"data\universe\etf_distributions.csv",
]
DISTRIBUTION_TABLE_CANDIDATES = (
    "etf_distributions",
    "etf_distribution_events",
    "etf_dividends",
    "etf_cash_distributions",
)

KEY_COLUMNS = {
    "signal_date",
    "feature_date",
    "ticker",
    "name",
    "end_date_1w",
    "end_date_2w",
    "end_date_1m",
    "end_date_3M",
    "end_date_6M",
    "end_date_1Y",
}
LABEL_PREFIXES = ("label_", "fwd_", "path_mdd_", "risk_adj_", "distribution_", "total_return_")
BASE_MARKET_PREFIXES = ("qm_market_", "qm_risk_", "qm_flow_")
ROLE_INTERACTION_PREFIXES = ("ri_",)
ETF_METRIC_PREFIXES = ("etf_metric_",)

LABEL_SPECS = [
    {"label": "label_tactical_1w_pos", "kind": "timing", "description": "1W forward return > 0"},
    {"label": "label_tactical_2w_pos", "kind": "timing", "description": "2W forward return > 0"},
    {"label": "label_tactical_1m_pos", "kind": "timing", "description": "1M forward return > 0"},
    {"label": "label_drawdown_safe_1m", "kind": "risk", "description": "1M return >= 0 and path MDD >= -5%"},
    {"label": "label_role_top30_1m_risk_adj", "kind": "role_allocation", "description": "Top 30% role/date risk-adjusted 1M ETF"},
    {"label": "label_role_top30_3m_risk_adj", "kind": "role_allocation", "description": "Top 30% role/date risk-adjusted 3M ETF"},
]


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return _safe_float(value)
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict("records")]


def _as_bool_int(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.astype(int)
    text = series.astype(str).str.lower()
    return text.isin({"1", "true", "yes", "y"}).astype(int)


def _feature_panel_path(asof: str) -> Path:
    token = asof.replace("-", "")
    return (
        ROOT
        / "reports"
        / "model_upgrade_research"
        / token
        / "ETF_T_SERIES_PIT_BACKFILL_V1"
        / "etf_tseries_pit_feature_panel.csv"
    )


def _read_panel(asof: str) -> pd.DataFrame:
    path = _feature_panel_path(asof)
    if not path.exists():
        raise SystemExit(f"missing ETF PIT feature panel: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in ("signal_date", "feature_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df[df["signal_date"].notna() & df["ticker"].notna()].copy()
    for col in ("is_inverse", "is_leveraged"):
        if col in df.columns:
            df[col] = _as_bool_int(df[col])
    return df


def _first_existing(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _normalize_distribution_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "distribution_date", "distribution_amount"])
    columns = set(frame.columns)
    date_col = _first_existing(
        columns,
        ("ex_date", "distribution_date", "base_date", "record_date", "pay_date", "date"),
    )
    amount_col = _first_existing(
        columns,
        (
            "distribution_amount",
            "distribution",
            "cash_distribution",
            "dividend_amount",
            "dividend",
            "dist_amount",
            "amount",
            "per_share_distribution",
        ),
    )
    if "ticker" not in columns or date_col is None or amount_col is None:
        return pd.DataFrame(columns=["ticker", "distribution_date", "distribution_amount"])
    out = frame[["ticker", date_col, amount_col]].rename(
        columns={date_col: "distribution_date", amount_col: "distribution_amount"}
    )
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["distribution_date"] = pd.to_datetime(out["distribution_date"], errors="coerce")
    out["distribution_amount"] = pd.to_numeric(out["distribution_amount"], errors="coerce")
    out = out.dropna(subset=["ticker", "distribution_date", "distribution_amount"])
    return out[out["distribution_amount"].gt(0)].copy()


def _load_distribution_events(tickers: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    ticker_set = set(str(ticker).zfill(6) for ticker in tickers)
    for path in DISTRIBUTION_CSV_CANDIDATES:
        if path.exists():
            frame = _normalize_distribution_frame(pd.read_csv(path, dtype={"ticker": str}, low_memory=False))
            frames.append(frame[frame["ticker"].isin(ticker_set)])
    if PRICE_DB.exists():
        with sqlite3.connect(PRICE_DB) as con:
            tables = {
                row[0]
                for row in con.execute("select name from sqlite_master where type='table'")
            }
            for table in DISTRIBUTION_TABLE_CANDIDATES:
                if table not in tables:
                    continue
                info = pd.read_sql_query(f"pragma table_info({table})", con)
                cols = set(info["name"].astype(str))
                date_col = _first_existing(
                    cols,
                    ("ex_date", "distribution_date", "base_date", "record_date", "pay_date", "date"),
                )
                amount_col = _first_existing(
                    cols,
                    (
                        "distribution_amount",
                        "distribution",
                        "cash_distribution",
                        "dividend_amount",
                        "dividend",
                        "dist_amount",
                        "amount",
                        "per_share_distribution",
                    ),
                )
                if "ticker" not in cols or date_col is None or amount_col is None:
                    continue
                placeholders = ",".join("?" for _ in tickers)
                query = f"""
                    select ticker, {date_col} as distribution_date, {amount_col} as distribution_amount
                    from {table}
                    where ticker in ({placeholders})
                """
                frames.append(_normalize_distribution_frame(pd.read_sql_query(query, con, params=tickers)))
    if not frames:
        return pd.DataFrame(columns=["ticker", "distribution_date", "distribution_amount"])
    out = pd.concat(frames, ignore_index=True).drop_duplicates(["ticker", "distribution_date", "distribution_amount"])
    return out.sort_values(["ticker", "distribution_date"])


def _add_distribution_adjusted_returns(px: pd.DataFrame, distributions: pd.DataFrame) -> pd.DataFrame:
    out = px.copy()
    for horizon in ("1w", "2w", "1m"):
        out[f"fwd_ret_price_{horizon}"] = out[f"fwd_ret_{horizon}"]
        out[f"path_mdd_price_{horizon}"] = out[f"path_mdd_{horizon}"]
        out[f"distribution_sum_{horizon}"] = 0.0
        out[f"total_return_adjustment_{horizon}"] = 0.0
        out[f"total_return_source_{horizon}"] = "price_only"
        out[f"fwd_ret_total_{horizon}"] = out[f"fwd_ret_{horizon}"]
    if distributions.empty:
        return out

    dist_map = {
        ticker: group.sort_values("distribution_date")
        for ticker, group in distributions.groupby("ticker", dropna=False)
    }
    for ticker, dist in dist_map.items():
        idx = out["ticker"].eq(ticker)
        if not idx.any():
            continue
        dates = out.loc[idx, "date"]
        close = out.loc[idx, "close"].replace(0, np.nan)
        for horizon in ("1w", "2w", "1m"):
            end_dates = out.loc[idx, f"end_date_{horizon}"]
            sums = []
            for start_dt, end_dt in zip(dates, end_dates):
                if pd.isna(start_dt) or pd.isna(end_dt):
                    sums.append(np.nan)
                    continue
                mask = dist["distribution_date"].gt(start_dt) & dist["distribution_date"].le(end_dt)
                sums.append(float(dist.loc[mask, "distribution_amount"].sum()))
            distribution_sum = pd.Series(sums, index=dates.index)
            out.loc[idx, f"distribution_sum_{horizon}"] = distribution_sum
            out.loc[idx, f"total_return_adjustment_{horizon}"] = distribution_sum / close
            out.loc[idx, f"fwd_ret_total_{horizon}"] = out.loc[idx, f"fwd_ret_price_{horizon}"] + out.loc[
                idx, f"total_return_adjustment_{horizon}"
            ]
            out.loc[idx & out[f"distribution_sum_{horizon}"].fillna(0).gt(0), f"total_return_source_{horizon}"] = "distribution_adjusted"
    for horizon in ("1w", "2w", "1m"):
        out[f"fwd_ret_total_{horizon}"] = out[f"fwd_ret_total_{horizon}"].fillna(out[f"fwd_ret_price_{horizon}"])
        out[f"fwd_ret_{horizon}"] = out[f"fwd_ret_total_{horizon}"]
    return out


def _load_price_forward(tickers: list[str]) -> pd.DataFrame:
    if not PRICE_DB.exists():
        raise SystemExit(f"missing price DB: {PRICE_DB}")
    placeholders = ",".join("?" for _ in tickers)
    query = f"""
        select ticker, date, close
        from prices_daily
        where ticker in ({placeholders})
        order by ticker, date
    """
    with sqlite3.connect(PRICE_DB) as con:
        px = pd.read_sql_query(query, con, params=tickers)
    px["ticker"] = px["ticker"].astype(str).str.zfill(6)
    px["date"] = pd.to_datetime(px["date"], errors="coerce")
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    px = px.dropna(subset=["ticker", "date", "close"]).sort_values(["ticker", "date"]).copy()
    group = px.groupby("ticker", group_keys=False)
    for steps, horizon in [(5, "1w"), (10, "2w"), (20, "1m")]:
        px[f"fwd_close_{horizon}"] = group["close"].shift(-steps)
        px[f"end_date_{horizon}"] = group["date"].shift(-steps)
        px[f"fwd_ret_{horizon}"] = px[f"fwd_close_{horizon}"] / px["close"] - 1.0
        px[f"path_mdd_{horizon}"] = group["close"].transform(
            lambda s: s.iloc[::-1].shift(1).rolling(steps, min_periods=1).min().iloc[::-1]
        ) / px["close"] - 1.0
    px = _add_distribution_adjusted_returns(px, _load_distribution_events(tickers))
    keep = ["ticker", "date"]
    for horizon in ("1w", "2w", "1m"):
        keep.extend(
            [
                f"fwd_ret_{horizon}",
                f"fwd_ret_price_{horizon}",
                f"fwd_ret_total_{horizon}",
                f"path_mdd_{horizon}",
                f"path_mdd_price_{horizon}",
                f"distribution_sum_{horizon}",
                f"total_return_adjustment_{horizon}",
                f"total_return_source_{horizon}",
                f"end_date_{horizon}",
            ]
        )
    return px[keep].rename(columns={"date": "signal_date"})


def _load_etf_daily_metrics(tickers: list[str]) -> pd.DataFrame:
    if not PRICE_DB.exists():
        return pd.DataFrame(columns=["ticker", "signal_date"])
    placeholders = ",".join("?" for _ in tickers)
    query = f"""
        select
            ticker,
            date,
            nav,
            premium_discount,
            premium_discount_abs,
            premium_discount_quality_flag,
            aum,
            aum_log,
            mcap,
            list_shares,
            underlying_index_name,
            underlying_index_level,
            underlying_index_return_pct,
            etf_return_pct
            ,daily_tracking_gap_pct
            ,daily_tracking_gap_abs_pct
        from etf_daily_metrics
        where ticker in ({placeholders})
    """
    try:
        with sqlite3.connect(PRICE_DB) as con:
            metrics = pd.read_sql_query(query, con, params=tickers)
    except Exception:
        return pd.DataFrame(columns=["ticker", "signal_date"])
    if metrics.empty:
        return pd.DataFrame(columns=["ticker", "signal_date"])
    metrics["ticker"] = metrics["ticker"].astype(str).str.zfill(6)
    metrics["signal_date"] = pd.to_datetime(metrics["date"], errors="coerce")
    numeric_cols = [
        "nav",
        "premium_discount",
        "premium_discount_abs",
        "aum",
        "aum_log",
        "mcap",
        "mcap_to_aum",
        "list_shares",
        "underlying_index_level",
        "underlying_index_return_pct",
        "etf_return_pct",
        "daily_tracking_gap_pct",
        "daily_tracking_gap_abs_pct",
    ]
    for col in numeric_cols:
        if col in metrics.columns:
            metrics[col] = pd.to_numeric(metrics[col], errors="coerce")
    if "aum_log" not in metrics.columns:
        metrics["aum_log"] = np.log1p(metrics["aum"].clip(lower=0))
    if "mcap_to_aum" not in metrics.columns:
        metrics["mcap_to_aum"] = metrics["mcap"] / metrics["aum"].replace(0, np.nan)
    if "daily_tracking_gap_pct" not in metrics.columns:
        metrics["daily_tracking_gap_pct"] = metrics["etf_return_pct"] - metrics["underlying_index_return_pct"]
    if "daily_tracking_gap_abs_pct" not in metrics.columns:
        metrics["daily_tracking_gap_abs_pct"] = metrics["daily_tracking_gap_pct"].abs()
    metrics = metrics.drop(columns=["date"], errors="ignore")
    rename = {
        col: f"etf_metric_{col}"
        for col in metrics.columns
        if col not in {"ticker", "signal_date"}
    }
    return metrics.rename(columns=rename)


def _prefix_context(df: pd.DataFrame, prefix: str, keys: set[str]) -> pd.DataFrame:
    metadata = {"schema_version", "feature_version", "generated_at", "source_quality", "flow_source_start_date"}
    out = df.drop(columns=[col for col in metadata if col in df.columns], errors="ignore").copy()
    rename = {col: f"{prefix}{col}" for col in out.columns if col not in keys}
    return out.rename(columns=rename)


def _read_contexts() -> pd.DataFrame:
    handoff = market_context_frame(scope="ALL", date_col="signal_date", prefix="qm_market_")
    if not handoff.empty:
        handoff["signal_date"] = pd.to_datetime(handoff["signal_date"], errors="coerce")
        handoff = handoff[handoff["signal_date"].notna()].copy()
        alias_map = {
            "qm_market_market_stress_score": "qm_risk_market_stress_score",
            "qm_market_drawdown_pressure_score": "qm_risk_drawdown_pressure_score",
            "qm_market_crash_warning_flag": "qm_risk_crash_warning_flag",
        }
        for src, dst in alias_map.items():
            if src in handoff.columns and dst not in handoff.columns:
                handoff[dst] = handoff[src]
        return handoff.sort_values("signal_date").drop_duplicates("signal_date", keep="last")

    frames: list[pd.DataFrame] = []
    market_path = QM_CONTEXT_DIR / "market_context_daily_current.csv"
    if market_path.exists():
        market = pd.read_csv(market_path, low_memory=False)
        market["signal_date"] = pd.to_datetime(market["asof_date"], errors="coerce")
        if "market_scope" in market.columns:
            market = market[market["market_scope"].astype(str).eq("ALL")].copy()
        market = market.drop(columns=["asof_date", "market_scope"], errors="ignore")
        frames.append(_prefix_context(market, "qm_market_", {"signal_date"}))

    risk_path = QM_CONTEXT_DIR / "risk_context_daily_current.csv"
    if risk_path.exists():
        risk = pd.read_csv(risk_path, low_memory=False)
        risk["signal_date"] = pd.to_datetime(risk["asof_date"], errors="coerce")
        risk = risk.drop(columns=["asof_date"], errors="ignore")
        frames.append(_prefix_context(risk, "qm_risk_", {"signal_date"}))

    flow_path = QM_CONTEXT_DIR / "flow_context_daily_current.csv"
    if flow_path.exists():
        flow = pd.read_csv(flow_path, low_memory=False)
        flow["signal_date"] = pd.to_datetime(flow["asof_date"], errors="coerce")
        if "market_scope" in flow.columns:
            flow = flow[flow["market_scope"].astype(str).eq("ALL")].copy()
        flow = flow.drop(columns=["asof_date", "market_scope"], errors="ignore")
        frames.append(_prefix_context(flow, "qm_flow_", {"signal_date"}))

    if not frames:
        return pd.DataFrame(columns=["signal_date"])
    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="signal_date", how="outer")
    return out.sort_values("signal_date").drop_duplicates("signal_date", keep="last")


def _derive_role(row: pd.Series) -> str:
    group = str(row.get("group_key") or row.get("expanded_group") or "").lower()
    asset = str(row.get("asset_class") or "").lower()
    inverse = int(row.get("is_inverse") or 0)
    leveraged = int(row.get("is_leveraged") or 0)
    if inverse:
        return "TACTICAL_HEDGE"
    if leveraged:
        return "TACTICAL_LEVERAGE"
    if asset in {"bond", "fx", "commodity", "hedge"} or group in {"bond_long", "bond_short", "fx_usd", "commodity_gold", "hedge_inverse_kr"}:
        return "DEFENSIVE_HEDGE"
    if group == "equity_kr_broad":
        return "CORE_BETA"
    if "growth" in group or "sector" in group:
        return "SECTOR_THEME"
    return "STYLE_FACTOR"


def _derive_regime_mode(df: pd.DataFrame) -> pd.Series:
    risk_on = pd.to_numeric(df.get("qm_market_risk_on_score"), errors="coerce").fillna(0.0)
    risk_off = pd.to_numeric(df.get("qm_market_risk_off_score"), errors="coerce").fillna(0.0)
    state = pd.to_numeric(df.get("qm_market_market_state_score"), errors="coerce").fillna(0.0)
    return np.select(
        [(risk_on >= 1.0) & (risk_on >= risk_off) & (state >= 0), (risk_off >= 1.0) & (risk_off > risk_on)],
        ["risk_on", "risk_off"],
        default="neutral",
    )


def _add_role_interactions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    roles = {
        "core_beta": out["role_key_derived"].eq("CORE_BETA").astype(int),
        "sector_theme": out["role_key_derived"].eq("SECTOR_THEME").astype(int),
        "defensive": out["role_key_derived"].eq("DEFENSIVE_HEDGE").astype(int),
        "tactical_hedge": out["role_key_derived"].eq("TACTICAL_HEDGE").astype(int),
        "tactical_leverage": out["role_key_derived"].eq("TACTICAL_LEVERAGE").astype(int),
    }
    drivers = [
        "qm_market_risk_on_score",
        "qm_market_risk_off_score",
        "qm_market_trend_score",
        "qm_market_breadth_score",
        "qm_market_market_vol_20d",
        "qm_market_market_mdd_3m",
        "qm_risk_market_stress_score",
        "qm_risk_drawdown_pressure_score",
        "qm_risk_usdkrw_ret_1m",
        "qm_risk_gold_proxy_ret_1m",
        "qm_risk_bond_proxy_ret_1m",
    ]
    for driver in drivers:
        if driver not in out.columns:
            continue
        values = pd.to_numeric(out[driver], errors="coerce")
        for role_name, role_flag in roles.items():
            out[f"ri_{role_name}_x_{driver}"] = role_flag * values
    return out


def _add_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for horizon in ("1w", "2w", "1m"):
        ret = pd.to_numeric(out[f"fwd_ret_{horizon}"], errors="coerce")
        mdd = pd.to_numeric(out[f"path_mdd_{horizon}"], errors="coerce")
        out[f"label_tactical_{horizon}_pos"] = np.where(ret.notna(), (ret > 0).astype(int), np.nan)
        out[f"risk_adj_{horizon}"] = ret + 0.5 * mdd.fillna(0.0)
    out["label_drawdown_safe_1m"] = np.where(
        out["fwd_ret_1m"].notna() & out["path_mdd_1m"].notna(),
        ((out["fwd_ret_1m"] >= 0.0) & (out["path_mdd_1m"] >= -0.05)).astype(int),
        np.nan,
    )
    out["risk_adj_3M"] = pd.to_numeric(out["fwd_ret_3M"], errors="coerce") + 0.5 * pd.to_numeric(
        out["path_mdd_3M"], errors="coerce"
    ).fillna(0.0)

    for horizon, score_col, label_col in [
        ("1m", "risk_adj_1m", "label_role_top30_1m_risk_adj"),
        ("3M", "risk_adj_3M", "label_role_top30_3m_risk_adj"),
    ]:
        score = pd.to_numeric(out[score_col], errors="coerce")
        group_cols = ["signal_date", "role_key_derived"]
        valid = score.notna()
        pct = out.loc[valid].groupby(group_cols)[score_col].rank(pct=True, ascending=False, method="first")
        out[label_col] = np.nan
        out.loc[valid, label_col] = (pct <= 0.30).astype(int)
    return out


def build_mart(asof: str) -> pd.DataFrame:
    panel = _read_panel(asof)
    tickers = sorted(panel["ticker"].unique().tolist())
    price_fwd = _load_price_forward(tickers)
    mart = panel.merge(price_fwd, on=["ticker", "signal_date"], how="left")
    etf_metrics = _load_etf_daily_metrics(tickers)
    if not etf_metrics.empty:
        mart = mart.merge(etf_metrics, on=["ticker", "signal_date"], how="left")
    contexts = _read_contexts()
    if not contexts.empty:
        mart = mart.merge(contexts, on="signal_date", how="left")
    mart["role_key_derived"] = mart.apply(_derive_role, axis=1)
    mart["regime_mode"] = _derive_regime_mode(mart)
    mart = _add_role_interactions(mart)
    mart = _add_labels(mart)
    return mart


def _feature_columns(df: pd.DataFrame, feature_mode: str) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    mode = str(feature_mode).upper()
    for col in df.columns:
        if col in KEY_COLUMNS or col.startswith(LABEL_PREFIXES):
            continue
        if col.startswith(BASE_MARKET_PREFIXES) and mode == "ETF_NATIVE":
            continue
        if col.startswith(ROLE_INTERACTION_PREFIXES) and mode != "ROLE_INTERACTION":
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _split(df: pd.DataFrame, label: str, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[label].notna()].copy()
    train = labeled[labeled["signal_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["signal_date"] >= pd.Timestamp(valid_start)) & (labeled["signal_date"] <= pd.Timestamp(valid_end))].copy()
    return train, valid


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ],
        remainder="drop",
    )


def _fit(train: pd.DataFrame, label: str, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    max_date = train["signal_date"].max()
    cutoff = max_date - pd.DateOffset(years=2)
    weight = np.ones(len(train), dtype=float)
    weight[train["signal_date"].ge(cutoff).to_numpy()] = 2.0
    pipe.fit(train, train[label].astype(int), model__sample_weight=weight)
    return pipe


def _evaluate(df: pd.DataFrame, spec: dict[str, str], feature_mode: str, train_end: str, valid_start: str, valid_end: str) -> dict[str, Any]:
    label = spec["label"]
    train, valid = _split(df, label, train_end, valid_start, valid_end)
    numeric, categorical = _feature_columns(train, feature_mode)
    row: dict[str, Any] = {
        **spec,
        "feature_mode": feature_mode,
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "train_positive_rate": _safe_float(train[label].mean()) if not train.empty else None,
        "valid_positive_rate": _safe_float(valid[label].mean()) if not valid.empty else None,
        "numeric_features": len(numeric),
        "categorical_features": len(categorical),
        "status": "ok",
    }
    if train.empty or valid.empty or train[label].nunique() < 2 or valid[label].nunique() < 2:
        row.update({"status": "skipped", "reason": "insufficient_rows_or_one_class"})
        return row
    model = _fit(train, label, numeric, categorical)
    prob = model.predict_proba(valid)[:, 1]
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    row.update(
        {
            "auc": _safe_float(roc_auc_score(valid[label].astype(int), prob)),
            "top30_label_rate": _safe_float(top[label].mean()),
            "bottom30_label_rate": _safe_float(bottom[label].mean()),
            "top30_fwd_ret_1m": _safe_float(top["fwd_ret_1m"].mean()),
            "bottom30_fwd_ret_1m": _safe_float(bottom["fwd_ret_1m"].mean()),
            "top30_path_mdd_1m": _safe_float(top["path_mdd_1m"].mean()),
            "bottom30_path_mdd_1m": _safe_float(bottom["path_mdd_1m"].mean()),
            "top30_risk_adj_1m": _safe_float(top["risk_adj_1m"].mean()),
            "bottom30_risk_adj_1m": _safe_float(bottom["risk_adj_1m"].mean()),
        }
    )
    return row


def run_ablation(asof: str, train_end: str, valid_start: str, feature_modes: list[str] | None = None) -> dict[str, Any]:
    mart = build_mart(asof)
    token = asof.replace("-", "")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    mart_path = REPORT_DIR / f"etf_ai_market_context_mart_{token}.csv"
    result_csv = REPORT_DIR / f"etf_ai_label_ablation_{token}.csv"
    result_json = REPORT_DIR / f"etf_ai_label_ablation_{token}.json"
    result_md = REPORT_DIR / f"etf_ai_label_ablation_{token}.md"
    mart.to_csv(mart_path, index=False, encoding="utf-8-sig")

    modes = feature_modes or ["ETF_NATIVE", "MARKET_CONTEXT", "ROLE_INTERACTION"]
    rows = []
    for mode in modes:
        rows.extend(_evaluate(mart, spec, mode, train_end, valid_start, asof) for spec in LABEL_SPECS)
    result = pd.DataFrame(rows).sort_values(["auc", "top30_label_rate"], ascending=False, na_position="last")
    result.to_csv(result_csv, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "etf_ai_label_ablation",
        "model_code": MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "market_context_rule": "ETF PIT feature panel + QM market/risk/flow context + role interaction features",
        "mart_rows": int(len(mart)),
        "signal_dates": int(mart["signal_date"].nunique()),
        "role_counts": _records(mart["role_key_derived"].value_counts().rename_axis("role_key").reset_index(name="count")),
        "results": result.replace({np.nan: None}).to_dict(orient="records"),
        "outputs": {"mart_csv": str(mart_path), "csv": str(result_csv), "json": str(result_json), "md": str(result_md)},
    }
    result_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result_md.write_text(
        "\n".join(
            [
                f"# ETF AI Label Ablation - {asof}",
                "",
                f"- Model code: `{MODEL_CODE}`",
                f"- Mart rows: {len(mart):,}",
                f"- Signal dates: {mart['signal_date'].nunique():,}",
                "",
                "## Results",
                "",
                "| feature_mode | label | kind | AUC | top30_label | bottom30_label | top30_1m_ret | bottom30_1m_ret |",
                "|---|---|---|---:|---:|---:|---:|---:|",
                *[
                    "| {feature_mode} | {label} | {kind} | {auc} | {top30_label_rate} | {bottom30_label_rate} | {top30_fwd_ret_1m} | {bottom30_fwd_ret_1m} |".format(
                        **{key: "" if pd.isna(value) else value for key, value in row.items()}
                    )
                    for row in result.to_dict(orient="records")
                ],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ETF AI market-context mart and run label ablation.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--feature-modes", nargs="*", default=None)
    args = parser.parse_args()
    payload = run_ablation(args.asof, args.train_end, args.valid_start, args.feature_modes)
    print(
        json.dumps(
            {
                "status": "ok",
                "model_code": MODEL_CODE,
                "as_of_date": args.asof,
                "best": payload["results"][0] if payload["results"] else {},
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
