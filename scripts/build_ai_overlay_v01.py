from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quant_market.market_handoff import (
    MARKET_HANDOFF_CATEGORICAL_COLUMNS,
    MARKET_HANDOFF_NUMERIC_COLUMNS,
    attach_market_forecast_features,
)

DEFAULT_ADMIN_PAYLOAD = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"
PRICE_DB = ROOT / r"data\db\price.db"
FUNDAMENTALS_DB = ROOT / r"data\db\fundamentals.db"
CLASSIFICATION_DB = ROOT / r"data\db\security_classification.db"
CSERIES_DB = ROOT / r"data\db\cseries_relationship.db"
AI_FEATURE_EXT_DB = ROOT / r"data\db\ai_feature_ext.db"
OUT_DB = ROOT / r"data\db\ai_learning.db"
OUT_DIR = ROOT / r"reports\ai_overlay_v01"

MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
MODEL_NAME_KO = "퀀트후보검증AI"
LEGACY_MODEL_CODE = "AI-OVERLAY-V01"
RANDOM_STATE = 42
MIN_MODEL_SPECIFIC_LABEL_ROWS = 200

NAVER_FEATURES = [
    "naver_foreign_net_volume_5d",
    "naver_foreign_net_volume_20d",
    "naver_foreign_net_value_5d",
    "naver_foreign_net_value_20d",
    "naver_foreign_net_buy_days_20d",
    "naver_foreign_net_buy_streak",
    "naver_institution_net_volume_5d",
    "naver_institution_net_volume_20d",
    "naver_institution_net_value_5d",
    "naver_institution_net_value_20d",
    "naver_institution_net_buy_days_20d",
    "naver_institution_net_buy_streak",
    "naver_foreign_holding_rate",
]

KIWOOM_FEATURES = [
    "kiwoom_foreign_net_volume_5d",
    "kiwoom_foreign_net_volume_20d",
    "kiwoom_foreign_net_value_5d",
    "kiwoom_foreign_net_value_20d",
    "kiwoom_foreign_net_buy_days_20d",
    "kiwoom_foreign_net_buy_streak",
    "kiwoom_institution_net_volume_5d",
    "kiwoom_institution_net_volume_20d",
    "kiwoom_institution_net_value_5d",
    "kiwoom_institution_net_value_20d",
    "kiwoom_institution_net_buy_days_20d",
    "kiwoom_institution_net_buy_streak",
]

DART_NUMERIC_FEATURES = [
    "dart_events_30d",
    "dart_events_90d",
    "dart_major_events_90d",
    "dart_earnings_events_90d",
    "dart_ownership_events_90d",
    "dart_market_watch_events_90d",
    "dart_days_since_last_event",
]

DART_CATEGORICAL_FEATURES = ["dart_last_event_category"]
QM_FORECAST_NUMERIC_FEATURES = [
    f"qmf_20d_{col}" for col in MARKET_HANDOFF_NUMERIC_COLUMNS
] + [
    f"qmf_20d_all_{col}" for col in MARKET_HANDOFF_NUMERIC_COLUMNS
]
QM_FORECAST_CATEGORICAL_FEATURES = [
    f"qmf_20d_{col}" for col in MARKET_HANDOFF_CATEGORICAL_COLUMNS
] + [
    f"qmf_20d_all_{col}" for col in MARKET_HANDOFF_CATEGORICAL_COLUMNS
]

NUMERIC_FEATURES = [
    "rank_no",
    "score",
    "weight",
    "stage1_prob",
    "stage2_prob",
    "universe_rank_no",
    "universe_rank_score",
    "display_score",
    "model_overlap_count",
    "overlap_user_count",
    "overlap_internal_count",
    "overlap_tseries_count",
    "ret_5d",
    "ret_10d",
    "ret_20d",
    "ret_60d",
    "vol_20d",
    "mdd_20d",
    "trading_value_20d",
    "annual_revenue_yoy",
    "annual_op_income_yoy",
    "half_revenue_yoy",
    "half_op_income_yoy",
    "q_revenue_yoy",
    "q_op_income_yoy",
    "q_revenue_yoy_delta_1q",
    "q_op_income_yoy_delta_1q",
    "pit_growth_score",
    "c_overlay_score",
    "positive_relation_count",
    "negative_relation_count",
    "theme_support_score",
    "etf_support_score",
    "hedge_risk_score",
    "cluster_concentration_score",
    *NAVER_FEATURES,
    *KIWOOM_FEATURES,
    *DART_NUMERIC_FEATURES,
    *QM_FORECAST_NUMERIC_FEATURES,
]

CATEGORICAL_FEATURES = [
    "scope_key",
    "model_id",
    "event_type",
    "score_basis",
    "candidate_bucket",
    "asset_group",
    "asset_type",
    "market",
    "sector_bucket",
    "theme_bucket",
    "relationship_status",
    *DART_CATEGORICAL_FEATURES,
    *QM_FORECAST_CATEGORICAL_FEATURES,
]


@dataclass(frozen=True)
class PricePoint:
    date: pd.Timestamp
    close: float
    volume: float | None
    value: float | None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _norm_ticker(value: Any) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(6) if digits else None


def _load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _live_start_map(payload: dict[str, Any]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    summary = payload.get("actual_live_performance_summary") or {}
    for row in summary.get("user_models") or []:
        if row.get("service_profile"):
            out[("user", str(row["service_profile"]))] = str(row.get("live_start_date"))
    for row in summary.get("internal_models") or []:
        if row.get("model_code"):
            out[("internal", str(row["model_code"]))] = str(row.get("live_start_date"))
    for row in summary.get("tseries_models") or []:
        if row.get("model_code"):
            out[("tseries", str(row["model_code"]))] = str(row.get("live_start_date"))
    return out


def _flatten_events(payload: dict[str, Any]) -> pd.DataFrame:
    live_starts = _live_start_map(payload)
    records: list[dict[str, Any]] = []
    for scope_key in ("user_models", "internal_models", "tseries_models"):
        for row in payload.get(scope_key) or []:
            scope = str(row.get("scope") or scope_key.replace("_models", ""))
            model_id = str(row.get("service_profile") or row.get("model_code") or row.get("model_key") or "")
            ticker = _norm_ticker(row.get("security_code"))
            if not ticker or not row.get("event_date") or not model_id:
                continue
            fwd = row.get("forward_returns") or {}
            risk = row.get("forward_risk_metrics") or {}
            risk_1m = risk.get("1m") or {}
            live_start = live_starts.get((scope, model_id))
            is_live = bool(live_start and str(row.get("event_date")) >= live_start)
            rec = {
                "scope_key": scope,
                "model_id": model_id,
                "ticker": ticker,
                "name": row.get("display_name"),
                "event_date": str(row.get("event_date")),
                "week_end": str(row.get("week_end") or row.get("event_date")),
                "event_type": row.get("event_type"),
                "score_basis": row.get("score_basis"),
                "candidate_bucket": row.get("candidate_bucket") or row.get("to_bucket"),
                "asset_group": row.get("asset_group"),
                "rank_no": _safe_float(row.get("rank_no") or row.get("weekly_rank_no")),
                "score": _safe_float(row.get("score") or row.get("weekly_score")),
                "weight": _safe_float(row.get("weight") or row.get("weekly_weight")),
                "stage1_prob": _safe_float(row.get("stage1_prob")),
                "stage2_prob": _safe_float(row.get("stage2_prob")),
                "universe_rank_no": _safe_float(row.get("universe_rank_no")),
                "universe_rank_score": _safe_float(row.get("universe_rank_score")),
                "display_score": _safe_float(row.get("display_score")),
                "is_current": int(bool(row.get("is_current"))),
                "live_start_date": live_start,
                "is_live_event": int(is_live),
                "fwd_ret_1w": _safe_float(fwd.get("1w")),
                "fwd_ret_2w": _safe_float(fwd.get("2w")),
                "fwd_ret_1m": _safe_float(fwd.get("1m")),
                "fwd_ret_2m": _safe_float(fwd.get("2m")),
                "fwd_ret_3m": _safe_float(fwd.get("3m")),
                "fwd_mdd_1m": _safe_float(risk_1m.get("mdd")),
                "fwd_sharpe_1m": _safe_float(risk_1m.get("sharpe")),
            }
            records.append(rec)
    df = pd.DataFrame(records)
    if df.empty:
        return df
    overlap = (
        df.groupby(["week_end", "ticker"], as_index=False)
        .agg(
            model_overlap_count=("model_id", "nunique"),
            overlap_user_count=("scope_key", lambda s: int((s == "user").sum())),
            overlap_internal_count=("scope_key", lambda s: int((s == "internal").sum())),
            overlap_tseries_count=("scope_key", lambda s: int((s == "tseries").sum())),
        )
    )
    return df.merge(overlap, on=["week_end", "ticker"], how="left")


def _load_price_points(tickers: list[str], asof: str) -> dict[str, list[PricePoint]]:
    if not tickers or not PRICE_DB.exists():
        return {}
    placeholders = ",".join(["?"] * len(tickers))
    with sqlite3.connect(str(PRICE_DB)) as con:
        df = pd.read_sql_query(
            f"""
            SELECT ticker, date, close, volume, value
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date <= ?
              AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            con,
            params=[*tickers, asof],
        )
    if df.empty:
        return {}
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce")
    df["value"] = pd.to_numeric(df.get("value"), errors="coerce")
    out: dict[str, list[PricePoint]] = {}
    for ticker, frame in df.dropna(subset=["close"]).groupby("ticker"):
        out[str(ticker)] = [
            PricePoint(
                date=row.date,
                close=float(row.close),
                volume=_safe_float(row.volume),
                value=_safe_float(row.value),
            )
            for row in frame.itertuples()
        ]
    return out


def _price_features(points: list[PricePoint], event_date: str) -> dict[str, float | None]:
    out = {
        "ret_5d": None,
        "ret_10d": None,
        "ret_20d": None,
        "ret_60d": None,
        "vol_20d": None,
        "mdd_20d": None,
        "trading_value_20d": None,
    }
    if not points:
        return out
    event_ts = pd.Timestamp(event_date)
    idx = next((i for i, p in enumerate(points) if p.date >= event_ts), None)
    if idx is None:
        return out
    closes = [p.close for p in points]
    close0 = closes[idx]
    for days in (5, 10, 20, 60):
        prev_idx = idx - days
        if prev_idx >= 0 and closes[prev_idx] > 0:
            out[f"ret_{days}d"] = round(close0 / closes[prev_idx] - 1.0, 6)
    start = max(0, idx - 20)
    segment = pd.Series(closes[start : idx + 1], dtype="float64")
    rets = segment.pct_change().dropna()
    if not rets.empty:
        out["vol_20d"] = round(float(rets.std(ddof=0)), 6)
    if len(segment) >= 2:
        peak = segment.cummax()
        out["mdd_20d"] = round(float((segment / peak - 1.0).min()), 6)
    values = [_safe_float(p.value) for p in points[start : idx + 1]]
    values = [v for v in values if v is not None]
    if values:
        out["trading_value_20d"] = round(float(np.mean(values)), 3)
    return out


def _attach_price_features(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    points = _load_price_points(sorted(df["ticker"].dropna().unique().tolist()), asof)
    rows = [_price_features(points.get(str(row.ticker), []), str(row.event_date)) for row in df.itertuples()]
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def _latest_by_date(db_path: Path, table: str, date_col: str, asof: str, columns: list[str]) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame(columns=columns)
    with sqlite3.connect(str(db_path)) as con:
        try:
            df = pd.read_sql_query(
                f"SELECT {', '.join(columns)} FROM {table} WHERE {date_col} <= ?",
                con,
                params=[asof],
            )
        except Exception:
            return pd.DataFrame(columns=columns)
    if df.empty or "ticker" not in df.columns:
        return pd.DataFrame(columns=columns)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df.sort_values(["ticker", date_col]).drop_duplicates("ticker", keep="last")


def _attach_static_features(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    class_cols = [
        "asof_date",
        "ticker",
        "asset_type",
        "market",
        "sector_bucket",
        "theme_bucket",
        "confidence_score",
    ]
    cls = _latest_by_date(CLASSIFICATION_DB, "security_classification_master", "asof_date", asof, class_cols)
    if not cls.empty:
        df = df.merge(cls.drop(columns=["asof_date"]), on="ticker", how="left")

    fund_cols = [
        "date",
        "ticker",
        "annual_revenue_yoy",
        "annual_op_income_yoy",
        "half_revenue_yoy",
        "half_op_income_yoy",
        "q_revenue_yoy",
        "q_op_income_yoy",
        "q_revenue_yoy_delta_1q",
        "q_op_income_yoy_delta_1q",
        "pit_growth_score",
    ]
    fund = _latest_by_date(FUNDAMENTALS_DB, "fundamentals_pit_qh_mix400_latest", "date", asof, fund_cols)
    if not fund.empty:
        df = df.merge(fund.drop(columns=["date"]), on="ticker", how="left")

    c_cols = [
        "asof_date",
        "base_model_code",
        "ticker",
        "positive_relation_count",
        "negative_relation_count",
        "theme_support_score",
        "etf_support_score",
        "hedge_risk_score",
        "cluster_concentration_score",
        "c_overlay_score",
        "relationship_status",
    ]
    c = _latest_by_date(CSERIES_DB, "c_model_overlay_scores", "asof_date", asof, c_cols)
    if not c.empty:
        c = c.sort_values(["ticker", "c_overlay_score"], ascending=[True, False]).drop_duplicates("ticker", keep="first")
        df = df.merge(c.drop(columns=["asof_date", "base_model_code"]), on="ticker", how="left")
    return df


def _load_kiwoom_flow_data(tickers: list[str], asof: str) -> pd.DataFrame:
    if not tickers or not AI_FEATURE_EXT_DB.exists():
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    with sqlite3.connect(str(AI_FEATURE_EXT_DB)) as con:
        try:
            flows = pd.read_sql_query(
                f"""
                SELECT date, ticker, investor, net_volume, net_value
                FROM investor_flows_daily
                WHERE ticker IN ({placeholders})
                  AND date <= ?
                  AND source = 'kiwoom_rest_ka10059'
                ORDER BY ticker, investor, date
                """,
                con,
                params=[*tickers, asof],
            )
        except Exception:
            return pd.DataFrame()
    if not flows.empty:
        flows["ticker"] = flows["ticker"].astype(str).str.zfill(6)
        flows["date"] = pd.to_datetime(flows["date"], errors="coerce")
        flows["net_volume"] = pd.to_numeric(flows["net_volume"], errors="coerce")
        flows["net_value"] = pd.to_numeric(flows["net_value"], errors="coerce")
    return flows.dropna(subset=["date"])


def _net_buy_streak(values: pd.Series) -> int | None:
    if values.empty:
        return None
    streak = 0
    for value in reversed(values.tolist()):
        if pd.notna(value) and float(value) > 0:
            streak += 1
        else:
            break
    return streak


def _kiwoom_flow_features(
    flows_by_key: dict[tuple[str, str], pd.DataFrame],
    ticker: str,
    event_date: str,
) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {
        "kiwoom_foreign_net_volume_5d": None,
        "kiwoom_foreign_net_volume_20d": None,
        "kiwoom_foreign_net_value_5d": None,
        "kiwoom_foreign_net_value_20d": None,
        "kiwoom_foreign_net_buy_days_20d": None,
        "kiwoom_foreign_net_buy_streak": None,
        "kiwoom_institution_net_volume_5d": None,
        "kiwoom_institution_net_volume_20d": None,
        "kiwoom_institution_net_value_5d": None,
        "kiwoom_institution_net_value_20d": None,
        "kiwoom_institution_net_buy_days_20d": None,
        "kiwoom_institution_net_buy_streak": None,
    }
    event_ts = pd.Timestamp(event_date)
    investor_prefix = {"외국인": "kiwoom_foreign", "기관합계": "kiwoom_institution"}
    for investor, prefix in investor_prefix.items():
        frame = flows_by_key.get((ticker, investor))
        if frame is None or frame.empty:
            continue
        hist = frame[frame["date"] <= event_ts].tail(20)
        if hist.empty:
            continue
        out[f"{prefix}_net_volume_5d"] = round(float(hist.tail(5)["net_volume"].sum()), 3)
        out[f"{prefix}_net_volume_20d"] = round(float(hist["net_volume"].sum()), 3)
        out[f"{prefix}_net_value_5d"] = round(float(hist.tail(5)["net_value"].sum()), 3)
        out[f"{prefix}_net_value_20d"] = round(float(hist["net_value"].sum()), 3)
        out[f"{prefix}_net_buy_days_20d"] = int((hist["net_volume"] > 0).sum())
        out[f"{prefix}_net_buy_streak"] = _net_buy_streak(hist["net_volume"])
    return out


def _load_dart_events(tickers: list[str], asof: str) -> pd.DataFrame:
    if not tickers or not AI_FEATURE_EXT_DB.exists():
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    with sqlite3.connect(str(AI_FEATURE_EXT_DB)) as con:
        try:
            events = pd.read_sql_query(
                f"""
                SELECT event_date, ticker, event_category
                FROM dart_disclosure_events
                WHERE ticker IN ({placeholders})
                  AND event_date <= ?
                ORDER BY ticker, event_date
                """,
                con,
                params=[*tickers, asof],
            )
        except Exception:
            return pd.DataFrame()
    if events.empty:
        return events
    events["ticker"] = events["ticker"].astype(str).str.zfill(6)
    events["event_date"] = pd.to_datetime(events["event_date"], errors="coerce")
    return events.dropna(subset=["event_date"])


def _dart_features(events_by_ticker: dict[str, pd.DataFrame], ticker: str, event_date: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "dart_events_30d": 0,
        "dart_events_90d": 0,
        "dart_major_events_90d": 0,
        "dart_earnings_events_90d": 0,
        "dart_ownership_events_90d": 0,
        "dart_market_watch_events_90d": 0,
        "dart_days_since_last_event": None,
        "dart_last_event_category": None,
    }
    frame = events_by_ticker.get(ticker)
    if frame is None or frame.empty:
        return out
    event_ts = pd.Timestamp(event_date)
    hist = frame[frame["event_date"] <= event_ts].copy()
    if hist.empty:
        return out
    last = hist.sort_values("event_date").tail(1).iloc[0]
    out["dart_days_since_last_event"] = int((event_ts - last["event_date"]).days)
    out["dart_last_event_category"] = last.get("event_category")
    recent_30 = hist[hist["event_date"] >= event_ts - pd.Timedelta(days=30)]
    recent_90 = hist[hist["event_date"] >= event_ts - pd.Timedelta(days=90)]
    out["dart_events_30d"] = int(len(recent_30))
    out["dart_events_90d"] = int(len(recent_90))
    if not recent_90.empty:
        counts = recent_90["event_category"].value_counts()
        out["dart_major_events_90d"] = int(counts.get("major_event", 0))
        out["dart_earnings_events_90d"] = int(counts.get("earnings_guidance", 0))
        out["dart_ownership_events_90d"] = int(counts.get("ownership", 0))
        out["dart_market_watch_events_90d"] = int(counts.get("market_watch", 0))
    return out


def _attach_external_features(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    tickers = sorted(df["ticker"].dropna().unique().tolist())
    flows = _load_kiwoom_flow_data(tickers, asof)
    flow_groups = {(str(ticker), str(investor)): frame for (ticker, investor), frame in flows.groupby(["ticker", "investor"])} if not flows.empty else {}
    dart = _load_dart_events(tickers, asof)
    dart_groups = {str(ticker): frame for ticker, frame in dart.groupby("ticker")} if not dart.empty else {}
    rows = []
    for row in df.itertuples():
        features = {}
        ticker = str(row.ticker)
        event_date = str(row.event_date)
        features.update(_kiwoom_flow_features(flow_groups, ticker, event_date))
        features.update(_dart_features(dart_groups, ticker, event_date))
        rows.append(features)
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def _add_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["has_1m_label"] = out["fwd_ret_1m"].notna().astype(int)
    out["label_return_1m_positive"] = np.where(out["fwd_ret_1m"].notna(), (out["fwd_ret_1m"] > 0).astype(int), np.nan)
    out["label_risk_1m"] = np.where(
        out["fwd_ret_1m"].notna(),
        ((out["fwd_ret_1m"] < 0) | (out["fwd_mdd_1m"].fillna(0) <= -0.15)).astype(int),
        np.nan,
    )
    out["label_quality_1m"] = np.where(
        out["fwd_ret_1m"].notna(),
        (
            (out["fwd_ret_1m"] > 0)
            & (out["fwd_mdd_1m"].isna() | (out["fwd_mdd_1m"] > -0.15))
            & (out["fwd_sharpe_1m"].isna() | (out["fwd_sharpe_1m"] > 0))
        ).astype(int),
        np.nan,
    )
    out["label_positive_1m"] = np.where(out["fwd_ret_1m"].notna(), (out["fwd_ret_1m"] > 0).astype(int), np.nan)
    out["label_quality_2m"] = np.where(out["fwd_ret_2m"].notna(), (out["fwd_ret_2m"] >= 0.05).astype(int), np.nan)
    out["label_quality_3m"] = np.where(out["fwd_ret_3m"].notna(), (out["fwd_ret_3m"] >= 0.07).astype(int), np.nan)
    out["label_quality_1m_strict"] = np.where(
        out["fwd_ret_1m"].notna(),
        (
            (out["fwd_ret_1m"] >= 0.05)
            & (out["fwd_mdd_1m"].isna() | (out["fwd_mdd_1m"] > -0.10))
            & (out["fwd_sharpe_1m"].isna() | (out["fwd_sharpe_1m"] > 0.3))
        ).astype(int),
        np.nan,
    )
    out["label_bad_1m_strict"] = np.where(
        out["fwd_ret_1m"].notna(),
        (
            (out["fwd_ret_1m"] <= -0.03)
            | (out["fwd_mdd_1m"].fillna(0) <= -0.15)
            | (out["fwd_sharpe_1m"].fillna(0) < -0.3)
        ).astype(int),
        np.nan,
    )
    return out


def _feature_columns_for_set(feature_set: str) -> tuple[list[str], list[str]]:
    exclude_numeric: set[str] = set()
    exclude_categorical: set[str] = set()
    if feature_set not in {"base", "kiwoom", "dart", "kiwoom_dart", "all"}:
        raise ValueError(f"unsupported feature_set: {feature_set}")
    if feature_set in {"base", "dart"}:
        exclude_numeric.update(KIWOOM_FEATURES)
    if feature_set in {"base", "kiwoom"}:
        exclude_numeric.update(DART_NUMERIC_FEATURES)
        exclude_categorical.update(DART_CATEGORICAL_FEATURES)
    exclude_numeric.update(NAVER_FEATURES)
    numeric = [col for col in NUMERIC_FEATURES if col not in exclude_numeric]
    categorical = [col for col in CATEGORICAL_FEATURES if col not in exclude_categorical]
    return numeric, categorical


def _preprocessor(df: pd.DataFrame, feature_set: str) -> ColumnTransformer:
    numeric_features, categorical_features = _feature_columns_for_set(feature_set)
    num_cols = [col for col in numeric_features if col in df.columns and df[col].notna().any()]
    cat_cols = [col for col in categorical_features if col in df.columns and df[col].notna().any()]
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), num_cols),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), cat_cols),
        ]
    )


def _fit_model(df: pd.DataFrame, label_col: str, model_kind: str, feature_set: str) -> tuple[Pipeline | None, dict[str, Any], pd.DataFrame]:
    train = df[df[label_col].notna()].copy()
    train = train.sort_values("event_date")
    if train.empty or train[label_col].nunique() < 2:
        return None, {"status": "skipped", "reason": "insufficient_label_classes", "label": label_col}, pd.DataFrame()
    dates = sorted(train["event_date"].unique().tolist())
    cut = dates[max(1, int(len(dates) * 0.75)) - 1]
    train_df = train[train["event_date"] <= cut].copy()
    test_df = train[train["event_date"] > cut].copy()
    if train_df[label_col].nunique() < 2 or test_df.empty or test_df[label_col].nunique() < 2:
        train_df = train.iloc[: max(2, int(len(train) * 0.75))].copy()
        test_df = train.iloc[max(2, int(len(train) * 0.75)) :].copy()
    if train_df[label_col].nunique() < 2:
        return None, {"status": "skipped", "reason": "insufficient_train_classes", "label": label_col}, pd.DataFrame()

    if model_kind == "logistic":
        clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_STATE)
    elif model_kind == "gb":
        clf = GradientBoostingClassifier(random_state=RANDOM_STATE, n_estimators=120, learning_rate=0.05, max_depth=3)
    else:
        raise ValueError(model_kind)

    pipe = Pipeline([("prep", _preprocessor(train_df, feature_set)), ("clf", clf)])
    pipe.fit(train_df, train_df[label_col].astype(int))
    pred = pd.DataFrame()
    auc = None
    if not test_df.empty:
        prob = pipe.predict_proba(test_df)[:, 1]
        pred = test_df[["scope_key", "model_id", "ticker", "name", "event_date", "week_end", label_col, "fwd_ret_1m", "fwd_mdd_1m", "fwd_sharpe_1m"]].copy()
        pred["pred_prob"] = prob
        if test_df[label_col].nunique() >= 2:
            auc = float(roc_auc_score(test_df[label_col].astype(int), prob))
    eval_payload = {
        "status": "ok",
        "label": label_col,
        "model_kind": model_kind,
        "feature_set": feature_set,
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "positive_rate_train": float(train_df[label_col].mean()),
        "positive_rate_test": None if test_df.empty else float(test_df[label_col].mean()),
        "auc": None if auc is None else round(auc, 6),
        "cut_date": str(cut),
    }
    if not pred.empty:
        top = pred.sort_values("pred_prob", ascending=False).head(min(30, len(pred)))
        eval_payload["top30_avg_1m_return"] = None if top["fwd_ret_1m"].dropna().empty else round(float(top["fwd_ret_1m"].mean()), 6)
        eval_payload["top30_win_rate"] = None if top["fwd_ret_1m"].dropna().empty else round(float((top["fwd_ret_1m"] > 0).mean()), 6)
    return pipe, eval_payload, pred


def _score_shadow(
    df: pd.DataFrame,
    quality_model: Pipeline | None,
    risk_model: Pipeline | None,
    asof: str,
    extra_models: dict[str, Pipeline | None] | None = None,
) -> pd.DataFrame:
    asof_ts = pd.Timestamp(asof)
    recent = df[
        (pd.to_datetime(df["event_date"], errors="coerce") >= asof_ts - pd.Timedelta(days=21))
        | (df["is_current"].fillna(0).astype(int) == 1)
    ].copy()
    if recent.empty:
        return recent
    recent["ai_quality_prob"] = np.nan
    recent["ai_risk_prob"] = np.nan
    extra_models = extra_models or {}
    if quality_model is not None:
        recent["ai_quality_prob"] = quality_model.predict_proba(recent)[:, 1]
    if risk_model is not None:
        recent["ai_risk_prob"] = risk_model.predict_proba(recent)[:, 1]
    prob_cols = {
        "short_confirm": "ai_short_confirm_prob",
        "medium_quality": "ai_medium_quality_prob",
        "long_quality": "ai_long_quality_prob",
        "upside_strict": "ai_upside_strict_prob",
        "risk_strict": "ai_risk_strict_prob",
    }
    for key, col in prob_cols.items():
        recent[col] = np.nan
        model = extra_models.get(key)
        if model is not None:
            recent[col] = model.predict_proba(recent)[:, 1]

    def tag(row: pd.Series) -> str:
        q = row.get("ai_quality_prob")
        r = row.get("ai_risk_prob")
        if pd.notna(r) and r >= 0.60:
            return "AI_CAUTION"
        if pd.notna(q) and q >= 0.60 and (pd.isna(r) or r < 0.45):
            return "AI_CONFIRM"
        return "AI_WATCH"

    recent["ai_tag"] = recent.apply(tag, axis=1)

    def multi_tags(row: pd.Series) -> str:
        tags: list[str] = []
        if pd.notna(row.get("ai_risk_strict_prob")) and row.get("ai_risk_strict_prob") >= 0.60:
            tags.append("RISK_AVOID")
        if pd.notna(row.get("ai_upside_strict_prob")) and row.get("ai_upside_strict_prob") >= 0.60:
            tags.append("UPSIDE_STRICT")
        if pd.notna(row.get("ai_short_confirm_prob")) and row.get("ai_short_confirm_prob") >= 0.60:
            tags.append("SHORT_CONFIRM")
        if pd.notna(row.get("ai_medium_quality_prob")) and row.get("ai_medium_quality_prob") >= 0.60:
            tags.append("MEDIUM_QUALITY")
        if pd.notna(row.get("ai_long_quality_prob")) and row.get("ai_long_quality_prob") >= 0.60:
            tags.append("LONG_QUALITY")
        if not tags:
            tags.append("OBSERVE")
        return ",".join(tags)

    def shadow_decision(row: pd.Series) -> str:
        if "RISK_AVOID" in str(row.get("ai_shadow_tags")):
            return "AI_RISK_REVIEW"
        if "UPSIDE_STRICT" in str(row.get("ai_shadow_tags")) and "MEDIUM_QUALITY" in str(row.get("ai_shadow_tags")):
            return "AI_HIGH_CONVICTION"
        if "SHORT_CONFIRM" in str(row.get("ai_shadow_tags")):
            return "AI_CONFIRM"
        return "AI_OBSERVE"

    recent["ai_shadow_tags"] = recent.apply(multi_tags, axis=1)
    recent["ai_shadow_decision"] = recent.apply(shadow_decision, axis=1)
    recent["ai_model_code"] = MODEL_CODE
    recent["ai_model_name_ko"] = MODEL_NAME_KO
    recent["ai_model_legacy_code"] = LEGACY_MODEL_CODE
    recent["scored_at"] = datetime.now().isoformat(timespec="seconds")
    keep = [
        "ai_model_code",
        "ai_model_name_ko",
        "ai_model_legacy_code",
        "scope_key",
        "model_id",
        "ticker",
        "name",
        "event_date",
        "week_end",
        "event_type",
        "rank_no",
        "score",
        "weight",
        "ai_quality_prob",
        "ai_risk_prob",
        "ai_short_confirm_prob",
        "ai_medium_quality_prob",
        "ai_long_quality_prob",
        "ai_upside_strict_prob",
        "ai_risk_strict_prob",
        "ai_model_specific_quality_prob",
        "ai_model_specific_risk_prob",
        "ai_tag",
        "ai_shadow_tags",
        "ai_shadow_decision",
        "ai_model_specific_tag",
        "is_current",
        "scored_at",
    ]
    return recent[[col for col in keep if col in recent.columns]].sort_values(["event_date", "scope_key", "model_id", "ai_tag", "ticker"])


def _fit_model_specific_models(df: pd.DataFrame, feature_set: str) -> tuple[dict[tuple[str, str], dict[str, Pipeline | None]], list[dict[str, Any]]]:
    models: dict[tuple[str, str], dict[str, Pipeline | None]] = {}
    evals: list[dict[str, Any]] = []
    for (scope_key, model_id), frame in df.groupby(["scope_key", "model_id"]):
        label_rows = frame["label_quality_1m"].dropna()
        base_eval = {
            "training_scope": "model_specific",
            "scope_key": scope_key,
            "model_id": model_id,
            "feature_set": feature_set,
            "model_kind": "gb",
        }
        if len(label_rows) < MIN_MODEL_SPECIFIC_LABEL_ROWS or label_rows.nunique() < 2:
            evals.append(
                {
                    **base_eval,
                    "status": "skipped",
                    "reason": "insufficient_model_specific_labels",
                    "label": "label_quality_1m",
                    "label_rows": int(len(label_rows)),
                }
            )
            continue

        quality_model, quality_eval, _ = _fit_model(frame, "label_quality_1m", "gb", feature_set)
        quality_eval.update(base_eval)
        quality_eval["label_rows"] = int(len(label_rows))
        evals.append(quality_eval)

        risk_label_rows = frame["label_bad_1m_strict"].dropna()
        risk_model: Pipeline | None = None
        if len(risk_label_rows) >= MIN_MODEL_SPECIFIC_LABEL_ROWS and risk_label_rows.nunique() >= 2:
            risk_model, risk_eval, _ = _fit_model(frame, "label_bad_1m_strict", "gb", feature_set)
            risk_eval.update(base_eval)
            risk_eval["label_rows"] = int(len(risk_label_rows))
            evals.append(risk_eval)
        else:
            evals.append(
                {
                    **base_eval,
                    "status": "skipped",
                    "reason": "insufficient_model_specific_risk_labels",
                    "label": "label_bad_1m_strict",
                    "label_rows": int(len(risk_label_rows)),
                }
            )

        if quality_model is not None or risk_model is not None:
            models[(str(scope_key), str(model_id))] = {
                "quality": quality_model,
                "risk": risk_model,
            }
    return models, evals


def _apply_model_specific_scores(
    shadow: pd.DataFrame,
    mart: pd.DataFrame,
    model_specific_models: dict[tuple[str, str], dict[str, Pipeline | None]],
) -> pd.DataFrame:
    if shadow.empty:
        return shadow
    out = shadow.copy()
    out["ai_model_specific_quality_prob"] = np.nan
    out["ai_model_specific_risk_prob"] = np.nan
    key_cols = ["scope_key", "model_id", "ticker", "event_date", "week_end"]
    feature_frame = mart.merge(
        out[key_cols].drop_duplicates(),
        on=key_cols,
        how="inner",
    )
    if feature_frame.empty:
        out["ai_model_specific_tag"] = "MS_FALLBACK_COMMON"
        return out

    scored_parts = []
    for (scope_key, model_id), frame in feature_frame.groupby(["scope_key", "model_id"]):
        model_bundle = model_specific_models.get((str(scope_key), str(model_id)))
        part = frame[key_cols].copy()
        part["ai_model_specific_quality_prob"] = np.nan
        part["ai_model_specific_risk_prob"] = np.nan
        if model_bundle:
            quality_model = model_bundle.get("quality")
            risk_model = model_bundle.get("risk")
            if quality_model is not None:
                part["ai_model_specific_quality_prob"] = quality_model.predict_proba(frame)[:, 1]
            if risk_model is not None:
                part["ai_model_specific_risk_prob"] = risk_model.predict_proba(frame)[:, 1]
        scored_parts.append(part)

    scored = pd.concat(scored_parts, ignore_index=True) if scored_parts else pd.DataFrame()
    if not scored.empty:
        out = out.drop(columns=["ai_model_specific_quality_prob", "ai_model_specific_risk_prob"], errors="ignore").merge(
            scored,
            on=key_cols,
            how="left",
        )

    def model_specific_tag(row: pd.Series) -> str:
        quality = row.get("ai_model_specific_quality_prob")
        risk = row.get("ai_model_specific_risk_prob")
        if pd.isna(quality) and pd.isna(risk):
            return "MS_FALLBACK_COMMON"
        if pd.notna(risk) and risk >= 0.60:
            return "MS_RISK_REVIEW"
        if pd.notna(quality) and quality >= 0.60 and (pd.isna(risk) or risk < 0.45):
            return "MS_CONFIRM"
        return "MS_OBSERVE"

    out["ai_model_specific_tag"] = out.apply(model_specific_tag, axis=1)
    return out


def _write_outputs(mart: pd.DataFrame, shadow: pd.DataFrame, evals: list[dict[str, Any]], asof: str, feature_set: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DB.parent.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    suffix = "" if feature_set == "kiwoom_dart" else f"_{feature_set}"
    mart_path = OUT_DIR / f"ai_overlay_training_mart_{token}{suffix}.csv"
    shadow_path = OUT_DIR / f"ai_overlay_shadow_scores_{token}{suffix}.csv"
    eval_json_path = OUT_DIR / f"ai_overlay_model_eval_{token}{suffix}.json"
    eval_md_path = OUT_DIR / f"ai_overlay_model_eval_{token}{suffix}.md"
    mart.to_csv(mart_path, index=False, encoding="utf-8-sig")
    shadow.to_csv(shadow_path, index=False, encoding="utf-8-sig")
    with sqlite3.connect(str(OUT_DB)) as con:
        mart.to_sql("ai_overlay_training_mart", con, if_exists="replace", index=False)
        shadow.to_sql("ai_shadow_scores", con, if_exists="replace", index=False)
        pd.DataFrame(evals).to_sql("ai_model_eval", con, if_exists="replace", index=False)
    payload = {
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "legacy_model_code": LEGACY_MODEL_CODE,
        "asof_date": asof,
        "feature_set": feature_set,
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d",
        "optimization_priority": "return_first",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mart_rows": int(len(mart)),
        "label_1m_rows": int(mart["has_1m_label"].sum()) if "has_1m_label" in mart else 0,
        "live_rows": int(mart["is_live_event"].sum()) if "is_live_event" in mart else 0,
        "shadow_rows": int(len(shadow)),
        "evaluations": evals,
        "outputs": {
            "db": str(OUT_DB),
            "mart_csv": str(mart_path),
            "shadow_csv": str(shadow_path),
            "eval_json": str(eval_json_path),
        },
    }
    eval_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# {MODEL_CODE} evaluation",
        "",
        f"- asof_date: {asof}",
        f"- feature_set: {feature_set}",
        f"- mart_rows: {payload['mart_rows']}",
        f"- 1M label rows: {payload['label_1m_rows']}",
        f"- live rows: {payload['live_rows']}",
        f"- shadow rows: {payload['shadow_rows']}",
        "",
        "| feature set | label | model | train | test | auc | top30 1M return | top30 win rate |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in evals:
        lines.append(
            "| {feature_set} | {label} | {model_kind} | {train_rows} | {test_rows} | {auc} | {top} | {win} |".format(
                feature_set=item.get("feature_set", feature_set),
                label=item.get("label"),
                model_kind=item.get("model_kind"),
                train_rows=item.get("train_rows", "-"),
                test_rows=item.get("test_rows", "-"),
                auc="-" if item.get("auc") is None else f"{item['auc']:.3f}",
                top="-" if item.get("top30_avg_1m_return") is None else f"{item['top30_avg_1m_return']:.2%}",
                win="-" if item.get("top30_win_rate") is None else f"{item['top30_win_rate']:.2%}",
            )
        )
    lines.extend(
        [
            "",
            "## Shadow tag counts",
            "",
        ]
    )
    if shadow.empty:
        lines.append("- no shadow rows")
    else:
        counts = shadow.groupby(["scope_key", "ai_tag"], as_index=False).size().sort_values(["scope_key", "ai_tag"])
        for row in counts.itertuples(index=False):
            lines.append(f"- {row.scope_key} / {row.ai_tag}: {int(row.size)}")
        if "ai_model_specific_tag" in shadow.columns:
            lines.extend(["", "## Model-specific tag counts", ""])
            ms_counts = (
                shadow.groupby(["scope_key", "model_id", "ai_model_specific_tag"], as_index=False)
                .size()
                .sort_values(["scope_key", "model_id", "ai_model_specific_tag"])
            )
            for row in ms_counts.itertuples(index=False):
                lines.append(f"- {row.scope_key} / {row.model_id} / {row.ai_model_specific_tag}: {int(row.size)}")
    eval_md_path.write_text("\n".join(lines), encoding="utf-8")


def build_ai_overlay(asof: str, payload_path: Path, feature_set: str = "kiwoom_dart") -> dict[str, Any]:
    payload = _load_payload(payload_path)
    mart = _flatten_events(payload)
    if mart.empty:
        raise SystemExit("no event rows")
    mart = _attach_price_features(mart, asof)
    mart = _attach_static_features(mart, asof)
    mart = _attach_external_features(mart, asof)
    mart = attach_market_forecast_features(mart, date_col="event_date", market_col="market", prefix="qmf_20d_")
    mart = _add_labels(mart)

    evals: list[dict[str, Any]] = []
    quality_model: Pipeline | None = None
    risk_model: Pipeline | None = None
    extra_models: dict[str, Pipeline | None] = {
        "short_confirm": None,
        "medium_quality": None,
        "long_quality": None,
        "upside_strict": None,
        "risk_strict": None,
    }
    for label_col in ("label_quality_1m", "label_risk_1m"):
        for kind in ("logistic", "gb"):
            model, eval_payload, _pred = _fit_model(mart, label_col, kind, feature_set)
            evals.append(eval_payload)
            if label_col == "label_quality_1m" and kind == "gb" and model is not None:
                quality_model = model
            if label_col == "label_risk_1m" and kind == "gb" and model is not None:
                risk_model = model
    shadow_label_map = {
        "short_confirm": "label_positive_1m",
        "medium_quality": "label_quality_2m",
        "long_quality": "label_quality_3m",
        "upside_strict": "label_quality_1m_strict",
        "risk_strict": "label_bad_1m_strict",
    }
    for model_key, label_col in shadow_label_map.items():
        model, eval_payload, _pred = _fit_model(mart, label_col, "gb", feature_set)
        eval_payload["shadow_model_key"] = model_key
        evals.append(eval_payload)
        extra_models[model_key] = model
    shadow = _score_shadow(mart, quality_model, risk_model, asof, extra_models)
    model_specific_models, model_specific_evals = _fit_model_specific_models(mart, feature_set)
    evals.extend(model_specific_evals)
    shadow = _apply_model_specific_scores(shadow, mart, model_specific_models)
    _write_outputs(mart, shadow, evals, asof, feature_set)
    return {
        "status": "ok",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "legacy_model_code": LEGACY_MODEL_CODE,
        "asof_date": asof,
        "feature_set": feature_set,
        "mart_rows": int(len(mart)),
        "label_1m_rows": int(mart["has_1m_label"].sum()),
        "live_rows": int(mart["is_live_event"].sum()),
        "shadow_rows": int(len(shadow)),
        "out_db": str(OUT_DB),
        "out_dir": str(OUT_DIR),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI overlay V01 training mart and shadow scores.")
    parser.add_argument("--asof", required=True, help="YYYY-MM-DD")
    parser.add_argument("--admin-payload", default=str(DEFAULT_ADMIN_PAYLOAD))
    parser.add_argument("--feature-set", default="kiwoom_dart", choices=["base", "kiwoom", "dart", "kiwoom_dart", "all"])
    args = parser.parse_args()
    result = build_ai_overlay(args.asof, Path(args.admin_payload), args.feature_set)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
