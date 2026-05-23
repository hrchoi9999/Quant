# build_features.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from src.quant_market.market_handoff import load_market_model_input

from .common import norm_ticker, now_ts, read_sql, write_table
from .config import (
    CLASSIFICATION_DB,
    DEFAULT_UNIVERSE,
    FEATURE_TABLE,
    FUNDAMENTALS_DB,
    MARKET_CONTEXT_MONTHLY_TABLE,
    OUT_DB,
    PRICE_DB,
    QUANTMARKET_CONTEXT_DIR,
    REPORT_DIR,
)


def _load_universe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ticker": str})
    df["ticker"] = df["ticker"].map(norm_ticker)
    return df.dropna(subset=["ticker"]).drop_duplicates("ticker")


def _load_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    placeholders = ",".join(["?"] * len(tickers))
    # Need lookback for 12M returns and long moving averages.
    start_ts = (pd.Timestamp(start) - pd.Timedelta(days=520)).strftime("%Y-%m-%d")
    sql = f"""
        SELECT ticker, date, close, volume, value
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date BETWEEN ? AND ?
          AND close IS NOT NULL
        ORDER BY ticker, date
    """
    df = read_sql(PRICE_DB, sql, [*tickers, start_ts, end], parse_dates=["date"])
    if df.empty:
        raise SystemExit("no prices loaded for valuation AI features")
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in ["close", "volume", "value"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["date", "close"])


def _rolling_mdd(close: pd.Series, window: int) -> pd.Series:
    peak = close.rolling(window, min_periods=max(5, window // 4)).max()
    dd = close / peak - 1.0
    return dd.rolling(window, min_periods=max(5, window // 4)).min()


def _price_features(prices: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ticker, g in prices.groupby("ticker", sort=False):
        g = g.sort_values("date").copy()
        close = g["close"]
        ret_20 = close.pct_change(20)
        ret_60 = close.pct_change(60)
        ret_126 = close.pct_change(126)
        ret_252 = close.pct_change(252)
        g["ret_1m"] = ret_20
        g["ret_3m"] = ret_60
        g["ret_6m"] = ret_126
        g["ret_12m"] = ret_252
        g["vol_20d"] = close.pct_change().rolling(20, min_periods=10).std()
        g["vol_60d"] = close.pct_change().rolling(60, min_periods=20).std()
        g["mdd_3m"] = _rolling_mdd(close, 60)
        g["mdd_6m"] = _rolling_mdd(close, 126)
        for window in (60, 140, 200):
            sma = close.rolling(window, min_periods=max(20, window // 3)).mean()
            g[f"distance_sma_{window}"] = close / sma - 1.0
        g["trading_value_20d"] = g["value"].rolling(20, min_periods=5).mean()
        g["price_acceleration"] = ret_20 - ret_60
        rolling_min = close.rolling(756, min_periods=126).min()
        rolling_max = close.rolling(756, min_periods=126).max()
        g["price_percentile_3y"] = (close - rolling_min) / (rolling_max - rolling_min)
        frames.append(g)
    daily = pd.concat(frames, ignore_index=True)
    daily = daily[(daily["date"] >= pd.Timestamp(start)) & (daily["date"] <= pd.Timestamp(end))].copy()
    daily["month"] = daily["date"].dt.to_period("M").astype(str)
    monthly = daily.sort_values(["ticker", "date"]).groupby(["ticker", "month"], as_index=False).tail(1).copy()
    monthly["asof_date"] = monthly["date"].dt.strftime("%Y-%m-%d")
    return monthly


def _load_fundamentals() -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    with sqlite3.connect(str(FUNDAMENTALS_DB)) as con:
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type IN ('table','view')", con)["name"].tolist()
        if "s2_fund_scores_monthly" in tables:
            legacy = pd.read_sql_query("SELECT * FROM s2_fund_scores_monthly", con)
            legacy = legacy.rename(
                columns={
                    "date": "fund_date",
                    "revenue_yoy": "annual_revenue_yoy",
                    "op_income_yoy": "annual_op_income_yoy",
                }
            )
            legacy["ticker"] = legacy["ticker"].astype(str).str.zfill(6)
            legacy["pit_growth_score"] = pd.to_numeric(legacy.get("growth_score"), errors="coerce")
            legacy["coverage_score"] = pd.to_numeric(legacy.get("valid_fund"), errors="coerce")
            parts.append(legacy)
        if "s2_fund_scores_pit_monthly" in tables:
            pit = pd.read_sql_query("SELECT * FROM s2_fund_scores_pit_monthly", con)
            pit = pit.rename(columns={"date": "fund_date"})
            pit["ticker"] = pit["ticker"].astype(str).str.zfill(6)
            parts.append(pit)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True, sort=False)
    out["fund_date"] = pd.to_datetime(out["fund_date"], errors="coerce")
    out["month"] = out["fund_date"].dt.to_period("M").astype(str)
    keep = [
        "month",
        "ticker",
        "annual_revenue_yoy",
        "annual_op_income_yoy",
        "half_revenue_yoy",
        "half_op_income_yoy",
        "q_revenue_yoy",
        "q_op_income_yoy",
        "q_revenue_yoy_delta_1q",
        "q_op_income_yoy_delta_1q",
        "coverage_score",
        "pit_growth_score",
    ]
    out = out[[col for col in keep if col in out.columns]].copy()
    out["_coverage_sort"] = pd.to_numeric(out.get("coverage_score"), errors="coerce").fillna(0)
    out = out.sort_values(["month", "ticker", "_coverage_sort"]).drop_duplicates(["month", "ticker"], keep="last")
    return out.drop(columns=["_coverage_sort"], errors="ignore")


def _load_classification() -> pd.DataFrame:
    if not CLASSIFICATION_DB.exists():
        return pd.DataFrame(columns=["ticker", "market", "sector_bucket", "theme_bucket"])
    df = read_sql(
        CLASSIFICATION_DB,
        """
        SELECT ticker, market, sector_bucket, theme_bucket
        FROM security_classification_master
        WHERE is_active = 1
        """,
    )
    if df.empty:
        return pd.DataFrame(columns=["ticker", "market", "sector_bucket", "theme_bucket"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df.drop_duplicates("ticker", keep="last")


def _load_market_context() -> pd.DataFrame:
    if not OUT_DB.exists():
        return pd.DataFrame()
    try:
        context = read_sql(
            OUT_DB,
            f"SELECT * FROM {MARKET_CONTEXT_MONTHLY_TABLE}",
        )
    except Exception:
        return pd.DataFrame()
    if context.empty:
        return context
    context["market_scope"] = context["market_scope"].fillna("ALL")
    return context.drop_duplicates(["month", "market_scope"], keep="last")


def _read_quantmarket_current_csv(file_name: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    path = QUANTMARKET_CONTEXT_DIR / file_name
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, low_memory=False)
    for col in parse_dates or []:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _daily_to_monthly_tail(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if df.empty or "asof_date" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["asof_date"] = pd.to_datetime(out["asof_date"], errors="coerce")
    out = out.dropna(subset=["asof_date"])
    out["month"] = out["asof_date"].dt.to_period("M").astype(str)
    return out.sort_values([*group_cols, "asof_date"]).groupby([*group_cols, "month"], as_index=False).tail(1).copy()


def _load_quantmarket_monthly_context() -> dict[str, pd.DataFrame]:
    market = load_market_model_input("20d")
    if market.empty:
        market = _read_quantmarket_current_csv("market_context_daily_current.csv", ["asof_date"])
    theme = _read_quantmarket_current_csv("theme_context_daily_quant_bucket_current.csv", ["asof_date"])
    risk = _read_quantmarket_current_csv("risk_context_daily_current.csv", ["asof_date"])
    flow = _read_quantmarket_current_csv("flow_context_daily_current.csv", ["asof_date"])

    if not market.empty:
        market = _daily_to_monthly_tail(market, ["market_scope"])
        market_cols = [
            "month",
            "market_scope",
            "market_state_label",
            "market_state_score",
            "trend_score",
            "breadth_score",
            "risk_score",
            "defensive_flow_score",
            "kospi_ret_1m",
            "kospi_ret_3m",
            "kosdaq_ret_1m",
            "kosdaq_ret_3m",
            "market_breadth_above_sma20",
            "new_high_ratio_20d",
            "new_low_ratio_20d",
            "trading_value_expansion_ratio",
            "risk_on_score",
            "risk_off_score",
            "predicted_forward_return",
            "calibrated_forecast_score",
            "calibrated_forecast_label",
            "calibration_confidence_score",
            "training_sample_count",
            "baseline_market_forecast_score",
            "market_forecast_score",
            "expected_volatility_score",
            "drawdown_risk_score",
            "upside_participation_score",
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
            "coverage_quality_label",
        ]
        market = market[[col for col in market_cols if col in market.columns]].rename(
            columns={
                "market_state_label": "qm_market_state_label",
                "market_state_score": "qm_market_state_score",
                "trend_score": "qm_trend_score",
                "breadth_score": "qm_breadth_score",
                "risk_score": "qm_risk_score",
                "defensive_flow_score": "qm_defensive_flow_score",
                "kospi_ret_1m": "qm_kospi_ret_1m",
                "kospi_ret_3m": "qm_kospi_ret_3m",
                "kosdaq_ret_1m": "qm_kosdaq_ret_1m",
                "kosdaq_ret_3m": "qm_kosdaq_ret_3m",
                "market_breadth_above_sma20": "qm_market_breadth_above_sma20",
                "new_high_ratio_20d": "qm_new_high_ratio_20d",
                "new_low_ratio_20d": "qm_new_low_ratio_20d",
                "trading_value_expansion_ratio": "qm_trading_value_expansion_ratio",
                "risk_on_score": "qm_risk_on_score",
                "risk_off_score": "qm_risk_off_score",
                "predicted_forward_return": "qm_forecast_20d_predicted_forward_return",
                "calibrated_forecast_score": "qm_forecast_20d_score",
                "calibrated_forecast_label": "qm_forecast_20d_label",
                "calibration_confidence_score": "qm_forecast_20d_confidence",
                "training_sample_count": "qm_forecast_20d_training_sample_count",
                "baseline_market_forecast_score": "qm_forecast_20d_baseline_score",
                "market_forecast_score": "qm_forecast_20d_market_forecast_score",
                "expected_volatility_score": "qm_forecast_20d_expected_volatility_score",
                "drawdown_risk_score": "qm_forecast_20d_drawdown_risk_score",
                "upside_participation_score": "qm_forecast_20d_upside_participation_score",
                "global_risk_on_score": "qm_forecast_20d_global_risk_on_score",
                "external_macro_pressure_score": "qm_forecast_20d_external_macro_pressure_score",
                "external_asset_risk_on_score": "qm_forecast_20d_external_asset_risk_on_score",
                "korea_proxy_momentum_score": "qm_forecast_20d_korea_proxy_momentum_score",
                "market_state_score_delta_5d": "qm_forecast_20d_market_state_delta_5d",
                "market_state_score_delta_20d": "qm_forecast_20d_market_state_delta_20d",
                "market_forecast_score_acceleration_5d": "qm_forecast_20d_score_acceleration_5d",
                "calibrated_forecast_score_delta_5d": "qm_forecast_20d_score_delta_5d",
                "calibrated_forecast_score_delta_20d": "qm_forecast_20d_score_delta_20d",
                "transition_count_20d": "qm_forecast_20d_transition_count_20d",
                "regime_stability_score": "qm_forecast_20d_regime_stability_score",
                "overall_feature_coverage_ratio": "qm_forecast_20d_coverage_ratio",
                "coverage_quality_label": "qm_forecast_20d_coverage_quality_label",
            }
        )

    if not theme.empty:
        theme = _daily_to_monthly_tail(theme, ["quant_theme_bucket"])
        theme_cols = [
            "month",
            "quant_theme_bucket",
            "quantmarket_theme_bucket",
            "theme_ret_1w",
            "theme_ret_1m",
            "theme_ret_3m",
            "theme_momentum_score",
            "theme_rotation_score",
            "theme_persistence_days",
            "theme_breadth_positive_ratio",
            "theme_above_sma60_ratio",
            "theme_trading_value_expansion_ratio",
            "theme_concentration_score",
            "leading_theme_rank",
            "mapping_confidence",
        ]
        theme = theme[[col for col in theme_cols if col in theme.columns]].rename(
            columns={
                "quant_theme_bucket": "theme_bucket",
                "quantmarket_theme_bucket": "qm_quantmarket_theme_bucket",
                "theme_ret_1w": "qm_theme_ret_1w",
                "theme_ret_1m": "qm_theme_ret_1m",
                "theme_ret_3m": "qm_theme_ret_3m",
                "theme_momentum_score": "qm_theme_momentum_score",
                "theme_rotation_score": "qm_theme_rotation_score",
                "theme_persistence_days": "qm_theme_persistence_days",
                "theme_breadth_positive_ratio": "qm_theme_breadth_positive_ratio",
                "theme_above_sma60_ratio": "qm_theme_above_sma60_ratio",
                "theme_trading_value_expansion_ratio": "qm_theme_trading_value_expansion_ratio",
                "theme_concentration_score": "qm_theme_concentration_score",
                "leading_theme_rank": "qm_leading_theme_rank",
                "mapping_confidence": "qm_theme_mapping_confidence",
            }
        )

    if not risk.empty:
        risk = _daily_to_monthly_tail(risk, [])
        risk_cols = [
            "month",
            "usdkrw_ret_1m",
            "gold_proxy_ret_1m",
            "bond_proxy_ret_1m",
            "inverse_etf_ret_1m",
            "defensive_asset_strength_score",
            "market_stress_score",
            "drawdown_pressure_score",
            "crash_warning_flag",
            "volatility_regime_label",
        ]
        risk = risk[[col for col in risk_cols if col in risk.columns]].rename(
            columns={
                "usdkrw_ret_1m": "qm_usdkrw_ret_1m",
                "gold_proxy_ret_1m": "qm_gold_proxy_ret_1m",
                "bond_proxy_ret_1m": "qm_bond_proxy_ret_1m",
                "inverse_etf_ret_1m": "qm_inverse_etf_ret_1m",
                "defensive_asset_strength_score": "qm_defensive_asset_strength_score",
                "market_stress_score": "qm_market_stress_score",
                "drawdown_pressure_score": "qm_drawdown_pressure_score",
                "crash_warning_flag": "qm_crash_warning_flag",
                "volatility_regime_label": "qm_volatility_regime_label",
            }
        )

    if not flow.empty:
        flow = _daily_to_monthly_tail(flow, ["market_scope"])
        flow_cols = [
            "month",
            "market_scope",
            "foreign_net_buy_ratio",
            "institution_net_buy_ratio",
            "flow_concentration_score",
            "smart_money_score",
            "flow_context_available",
            "flow_coverage_flag",
        ]
        flow = flow[[col for col in flow_cols if col in flow.columns]].rename(
            columns={
                "foreign_net_buy_ratio": "qm_foreign_net_buy_ratio",
                "institution_net_buy_ratio": "qm_institution_net_buy_ratio",
                "flow_concentration_score": "qm_flow_concentration_score",
                "smart_money_score": "qm_smart_money_score",
                "flow_context_available": "qm_flow_context_available",
                "flow_coverage_flag": "qm_flow_coverage_flag",
            }
        )
    return {"market": market, "theme": theme, "risk": risk, "flow": flow}


def _merge_quantmarket_context(out: pd.DataFrame) -> pd.DataFrame:
    context = _load_quantmarket_monthly_context()
    market = context.get("market", pd.DataFrame())
    if not market.empty:
        out = out.merge(market, on=["month", "market_scope"], how="left")
        all_market = market[market["market_scope"] == "ALL"].drop(columns=["market_scope"], errors="ignore")
        all_market = all_market.add_suffix("_all").rename(columns={"month_all": "month"})
        out = out.merge(all_market, on="month", how="left")
        for col in [c for c in market.columns if c not in ["month", "market_scope"]]:
            all_col = f"{col}_all"
            if col in out.columns and all_col in out.columns:
                out[col] = out[col].fillna(out[all_col])
            elif all_col in out.columns:
                out[col] = out[all_col]
        out = out.drop(columns=[c for c in out.columns if c.endswith("_all")], errors="ignore")

    theme = context.get("theme", pd.DataFrame())
    if not theme.empty:
        out = out.merge(theme, on=["month", "theme_bucket"], how="left")

    risk = context.get("risk", pd.DataFrame())
    if not risk.empty:
        out = out.merge(risk, on="month", how="left")

    flow = context.get("flow", pd.DataFrame())
    if not flow.empty:
        out = out.merge(flow, on=["month", "market_scope"], how="left")
        all_flow = flow[flow["market_scope"] == "ALL"].drop(columns=["market_scope"], errors="ignore")
        all_flow = all_flow.add_suffix("_all").rename(columns={"month_all": "month"})
        out = out.merge(all_flow, on="month", how="left")
        for col in [c for c in flow.columns if c not in ["month", "market_scope"]]:
            all_col = f"{col}_all"
            if col in out.columns and all_col in out.columns:
                out[col] = out[col].fillna(out[all_col])
            elif all_col in out.columns:
                out[col] = out[all_col]
        out = out.drop(columns=[c for c in out.columns if c.endswith("_all")], errors="ignore")

    for col in ["qm_market_state_label", "qm_volatility_regime_label", "qm_quantmarket_theme_bucket"]:
        if col not in out.columns:
            out[col] = "unknown"
        else:
            out[col] = out[col].fillna("unknown")
    for col in ["qm_flow_context_available", "qm_flow_coverage_flag"]:
        if col not in out.columns:
            out[col] = 0
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    return out


def build_features(universe: Path, start: str, end: str, out_db: Path = OUT_DB) -> pd.DataFrame:
    uni = _load_universe(universe)
    tickers = sorted(uni["ticker"].dropna().unique().tolist())
    price_monthly = _price_features(_load_prices(tickers, start, end), start, end)
    cls = _load_classification()
    fund = _load_fundamentals()
    market_context = _load_market_context()

    out = price_monthly.merge(uni[["ticker", "name", "market"]], on="ticker", how="left", suffixes=("", "_universe"))
    if not cls.empty:
        out = out.merge(cls, on="ticker", how="left", suffixes=("", "_cls"))
        out["market"] = out["market"].fillna(out.get("market_cls"))
    if not fund.empty:
        out = out.merge(fund, on=["month", "ticker"], how="left")

    out["sector_bucket"] = out["sector_bucket"].fillna("unknown")
    out["theme_bucket"] = out["theme_bucket"].fillna("unknown")
    out["market"] = out["market"].fillna("unknown")
    out["market_scope"] = np.where(out["market"].isin(["KOSPI", "KOSDAQ"]), out["market"], "ALL")
    if not market_context.empty:
        context_cols = [
            "month",
            "market_scope",
            "market_ret_1m",
            "market_ret_3m",
            "market_ret_6m",
            "market_vol_20d",
            "market_mdd_3m",
            "market_breadth_ret_pos_1m",
            "market_breadth_above_sma60",
            "market_breadth_above_sma120",
            "market_regime_score",
            "market_regime",
            "market_regime_bullish_pct",
            "market_regime_bearish_pct",
            "market_regime_neutral_pct",
            "market_regime_label",
            "market_context_available",
        ]
        keep_context = [col for col in context_cols if col in market_context.columns]
        out = out.merge(market_context[keep_context], on=["month", "market_scope"], how="left")
        missing_context = out["market_context_available"].isna() if "market_context_available" in out.columns else pd.Series(True, index=out.index)
        if missing_context.any():
            all_context = market_context[market_context["market_scope"] == "ALL"][keep_context].drop(columns=["market_scope"], errors="ignore")
            all_context = all_context.add_suffix("_all").rename(columns={"month_all": "month"})
            out = out.merge(all_context, on="month", how="left")
            for col in [c for c in context_cols if c not in ["month", "market_scope"]]:
                all_col = f"{col}_all"
                if col in out.columns and all_col in out.columns:
                    out[col] = out[col].fillna(out[all_col])
                elif all_col in out.columns:
                    out[col] = out[all_col]
            out = out.drop(columns=[c for c in out.columns if c.endswith("_all")], errors="ignore")
    if "market_context_available" not in out.columns:
        out["market_context_available"] = 0
    else:
        out["market_context_available"] = pd.to_numeric(out["market_context_available"], errors="coerce").fillna(0)
    if "market_regime_label" not in out.columns:
        out["market_regime_label"] = "unknown"
    else:
        out["market_regime_label"] = out["market_regime_label"].fillna("unknown")
    out = _merge_quantmarket_context(out)

    sector_stats = (
        out.groupby(["asof_date", "sector_bucket"], as_index=False)
        .agg(
            sector_sales_growth_median=("annual_revenue_yoy", "median"),
            sector_op_growth_median=("annual_op_income_yoy", "median"),
            sector_price_momentum_3m=("ret_3m", "median"),
            sector_price_momentum_12m=("ret_12m", "median"),
        )
    )
    out = out.merge(sector_stats, on=["asof_date", "sector_bucket"], how="left")
    out["excess_ret_3m_sector"] = out["ret_3m"] - out["sector_price_momentum_3m"]
    out["created_at"] = now_ts()

    columns = [
        "asof_date",
        "month",
        "ticker",
        "name",
        "market",
        "sector_bucket",
        "theme_bucket",
        "close",
        "ret_1m",
        "ret_3m",
        "ret_6m",
        "ret_12m",
        "excess_ret_3m_sector",
        "vol_20d",
        "vol_60d",
        "mdd_3m",
        "mdd_6m",
        "distance_sma_60",
        "distance_sma_140",
        "distance_sma_200",
        "trading_value_20d",
        "price_acceleration",
        "price_percentile_3y",
        "annual_revenue_yoy",
        "annual_op_income_yoy",
        "half_revenue_yoy",
        "half_op_income_yoy",
        "q_revenue_yoy",
        "q_op_income_yoy",
        "q_revenue_yoy_delta_1q",
        "q_op_income_yoy_delta_1q",
        "pit_growth_score",
        "coverage_score",
        "sector_sales_growth_median",
        "sector_op_growth_median",
        "sector_price_momentum_3m",
        "sector_price_momentum_12m",
        "market_regime",
        "market_regime_label",
        "market_ret_1m",
        "market_ret_3m",
        "market_ret_6m",
        "market_vol_20d",
        "market_mdd_3m",
        "market_breadth_ret_pos_1m",
        "market_breadth_above_sma60",
        "market_breadth_above_sma120",
        "market_regime_score",
        "market_regime_bullish_pct",
        "market_regime_bearish_pct",
        "market_regime_neutral_pct",
        "market_context_available",
        "qm_market_state_label",
        "qm_market_state_score",
        "qm_trend_score",
        "qm_breadth_score",
        "qm_risk_score",
        "qm_defensive_flow_score",
        "qm_kospi_ret_1m",
        "qm_kospi_ret_3m",
        "qm_kosdaq_ret_1m",
        "qm_kosdaq_ret_3m",
        "qm_market_breadth_above_sma20",
        "qm_new_high_ratio_20d",
        "qm_new_low_ratio_20d",
        "qm_trading_value_expansion_ratio",
        "qm_risk_on_score",
        "qm_risk_off_score",
        "qm_quantmarket_theme_bucket",
        "qm_theme_ret_1w",
        "qm_theme_ret_1m",
        "qm_theme_ret_3m",
        "qm_theme_momentum_score",
        "qm_theme_rotation_score",
        "qm_theme_persistence_days",
        "qm_theme_breadth_positive_ratio",
        "qm_theme_above_sma60_ratio",
        "qm_theme_trading_value_expansion_ratio",
        "qm_theme_concentration_score",
        "qm_leading_theme_rank",
        "qm_theme_mapping_confidence",
        "qm_usdkrw_ret_1m",
        "qm_gold_proxy_ret_1m",
        "qm_bond_proxy_ret_1m",
        "qm_inverse_etf_ret_1m",
        "qm_defensive_asset_strength_score",
        "qm_market_stress_score",
        "qm_drawdown_pressure_score",
        "qm_crash_warning_flag",
        "qm_volatility_regime_label",
        "qm_foreign_net_buy_ratio",
        "qm_institution_net_buy_ratio",
        "qm_flow_concentration_score",
        "qm_smart_money_score",
        "qm_flow_context_available",
        "qm_flow_coverage_flag",
        "created_at",
    ]
    out = out[[col for col in columns if col in out.columns]].replace([np.inf, -np.inf], np.nan)
    write_table(out_db, FEATURE_TABLE, out)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(REPORT_DIR / f"valuation_features_{end.replace('-', '')}.csv", index=False, encoding="utf-8-sig")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build monthly features for AI-GROWTH-VALUATION-V01.")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--start", default="2017-01-01")
    parser.add_argument("--end", required=True)
    parser.add_argument("--out-db", default=str(OUT_DB))
    args = parser.parse_args()
    df = build_features(Path(args.universe), args.start, args.end, Path(args.out_db))
    print({"status": "ok", "rows": int(len(df)), "start": args.start, "end": args.end, "out_db": args.out_db})


if __name__ == "__main__":
    main()
