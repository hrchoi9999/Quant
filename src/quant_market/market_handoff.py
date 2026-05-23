from __future__ import annotations

from pathlib import Path

import pandas as pd


HANDOFF_CONTEXT_DIR = Path(r"D:\QuantMarket\service_platform\quant_model_handoff\market_context\current")
LEGACY_CONTEXT_DIR = Path(r"D:\QuantMarket\service_platform\ai_training\market_context\current")

PRIMARY_FORECAST_FILE = "market_forecast_ai_calibrated_daily_current.csv"
MARKET_MODEL_INPUT_FILE = "market_model_input_daily_current.csv"
THEME_CONTEXT_FILE = "theme_context_daily_quant_bucket_current.csv"

RECOMMENDED_HORIZON = "20d"

MARKET_HANDOFF_NUMERIC_COLUMNS = [
    "predicted_forward_return",
    "calibrated_forecast_score",
    "calibration_confidence_score",
    "training_sample_count",
    "baseline_market_forecast_score",
    "market_forecast_score",
    "expected_volatility_score",
    "drawdown_risk_score",
    "upside_participation_score",
    "confidence_score",
    "market_state_score",
    "trend_score",
    "breadth_score",
    "risk_score",
    "risk_on_score",
    "risk_off_score",
    "global_risk_on_score",
    "external_macro_pressure_score",
    "external_asset_risk_on_score",
    "korea_proxy_momentum_score",
    "market_state_score_delta_5d",
    "market_state_score_delta_20d",
    "market_forecast_score_acceleration_5d",
    "calibrated_forecast_score_delta_5d",
    "calibrated_forecast_score_delta_20d",
    "transition_count_20d",
    "regime_stability_score",
    "overall_feature_coverage_ratio",
    "market_stress_score",
    "drawdown_pressure_score",
    "crash_warning_flag",
    "foreign_net_buy_ratio",
    "institution_net_buy_ratio",
    "flow_concentration_score",
    "smart_money_score",
    "flow_context_available",
    "flow_coverage_flag",
]

MARKET_HANDOFF_CATEGORICAL_COLUMNS = [
    "calibrated_forecast_label",
    "baseline_market_forecast_label",
    "market_forecast_label",
    "risk_regime_label",
    "market_state_label",
    "volatility_regime_label",
    "coverage_quality_label",
]


def context_dir() -> Path:
    return HANDOFF_CONTEXT_DIR if HANDOFF_CONTEXT_DIR.exists() else LEGACY_CONTEXT_DIR


def read_current_csv(file_name: str, *, parse_dates: list[str] | None = None) -> pd.DataFrame:
    path = context_dir() / file_name
    if not path.exists():
        legacy_path = LEGACY_CONTEXT_DIR / file_name
        if not legacy_path.exists():
            return pd.DataFrame()
        path = legacy_path
    df = pd.read_csv(path, low_memory=False)
    for col in parse_dates or []:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_market_model_input(horizon: str = RECOMMENDED_HORIZON) -> pd.DataFrame:
    df = read_current_csv(MARKET_MODEL_INPUT_FILE, parse_dates=["asof_date"])
    if df.empty:
        df = read_current_csv("market_context_daily_current.csv", parse_dates=["asof_date"])
    if df.empty:
        return df
    if "forecast_horizon" in df.columns:
        df = df[df["forecast_horizon"].astype(str).eq(horizon)].copy()
    if "market_scope" not in df.columns:
        df["market_scope"] = "ALL"
    primary = load_primary_forecast(horizon)
    if not primary.empty:
        fill_cols = [
            "predicted_forward_return",
            "calibrated_forecast_score",
            "calibrated_forecast_label",
            "calibration_confidence_score",
            "training_sample_count",
            "baseline_market_forecast_score",
            "baseline_market_forecast_label",
        ]
        source_cols = ["asof_date", "market_scope", *[col for col in fill_cols if col in primary.columns]]
        merged = df.merge(
            primary[source_cols].rename(columns={col: f"{col}__primary" for col in fill_cols if col in primary.columns}),
            on=["asof_date", "market_scope"],
            how="left",
        )
        for col in fill_cols:
            primary_col = f"{col}__primary"
            if primary_col not in merged.columns:
                continue
            if col in merged.columns:
                merged[col] = merged[primary_col].where(merged[primary_col].notna(), merged[col])
            else:
                merged[col] = merged[primary_col]
        df = merged.drop(columns=[c for c in merged.columns if c.endswith("__primary")], errors="ignore")
    return df.sort_values(["market_scope", "asof_date"]).drop_duplicates(["market_scope", "asof_date"], keep="last")


def load_primary_forecast(horizon: str = RECOMMENDED_HORIZON) -> pd.DataFrame:
    df = read_current_csv(PRIMARY_FORECAST_FILE, parse_dates=["asof_date"])
    if df.empty:
        return df
    if "forecast_horizon" in df.columns:
        df = df[df["forecast_horizon"].astype(str).eq(horizon)].copy()
    if "market_scope" not in df.columns:
        df["market_scope"] = "ALL"
    return df.sort_values(["market_scope", "asof_date"]).drop_duplicates(["market_scope", "asof_date"], keep="last")


def market_context_frame(
    *,
    horizon: str = RECOMMENDED_HORIZON,
    scope: str | None = None,
    date_col: str = "asof_date",
    prefix: str = "qm_market_",
) -> pd.DataFrame:
    df = load_market_model_input(horizon)
    if df.empty:
        return pd.DataFrame(columns=[date_col])
    if scope is not None:
        df = df[df["market_scope"].astype(str).eq(scope)].copy()
    keep = ["asof_date", "market_scope"]
    keep += [col for col in MARKET_HANDOFF_NUMERIC_COLUMNS + MARKET_HANDOFF_CATEGORICAL_COLUMNS if col in df.columns]
    out = df[[col for col in keep if col in df.columns]].copy()
    out = out.rename(columns={"asof_date": date_col})
    rename = {col: f"{prefix}{col}" for col in out.columns if col not in {date_col, "market_scope"}}
    return out.rename(columns=rename)


def attach_market_forecast_features(
    frame: pd.DataFrame,
    *,
    date_col: str,
    market_col: str | None = None,
    horizon: str = RECOMMENDED_HORIZON,
    prefix: str = "qmf_20d_",
    include_all_scope: bool = True,
) -> pd.DataFrame:
    if frame.empty or date_col not in frame.columns:
        return frame
    context = market_context_frame(horizon=horizon, scope=None, date_col=date_col, prefix=prefix)
    if context.empty:
        return frame
    out = frame.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    context[date_col] = pd.to_datetime(context[date_col], errors="coerce")
    if market_col and market_col in out.columns:
        out["_qm_market_scope_join"] = out[market_col].where(out[market_col].isin(["KOSPI", "KOSDAQ"]), "ALL")
    else:
        out["_qm_market_scope_join"] = "ALL"

    scoped = context.rename(columns={"market_scope": "_qm_market_scope_join"})
    out = out.merge(scoped, on=[date_col, "_qm_market_scope_join"], how="left")

    if include_all_scope:
        all_context = context[context["market_scope"].astype(str).eq("ALL")].drop(columns=["market_scope"], errors="ignore")
        all_context = all_context.rename(
            columns={col: f"{prefix}all_{col.removeprefix(prefix)}" for col in all_context.columns if col != date_col}
        )
        out = out.merge(all_context, on=date_col, how="left")
    return out.drop(columns=["_qm_market_scope_join"], errors="ignore")
