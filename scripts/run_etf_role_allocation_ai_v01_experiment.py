from __future__ import annotations

import argparse
import json
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

from scripts.run_etf_ai_label_ablation import build_mart

REPORT_DIR = ROOT / r"reports\etf_ai_role_allocation_v01"
DOC_PATH = ROOT / r"docs\AI_ETF_ROLE_ALLOCATION_V01_EXPERIMENT_20260511.md"
MODEL_CODE = "AI-ETF-ROLE-ALLOCATION-V01"
ROLES = [
    "CORE_BETA",
    "SECTOR_THEME",
    "STYLE_FACTOR",
    "DEFENSIVE_HEDGE",
    "TACTICAL_HEDGE",
    "TACTICAL_LEVERAGE",
]
RANDOM_STATE = 42
REGIME_MAPS = {
    "score_default": "Existing score rule: risk_on_score/risk_off_score with market_state_score gate",
    "label_vol": "Market state label with stress volatility override",
    "score_diff": "Risk-on/risk-off score spread with state fallback",
    "strict": "Risk-on only in clean uptrend; stress/downside quickly becomes risk_off",
    "state_only": "Market state label only, no volatility override",
}
SELECTION_SCORE_MODES = {
    "balanced": "Current balanced momentum/risk/liquidity ETF rank score",
    "momentum": "Momentum-heavy score using 20D/60D/120D returns and moving-average gap",
    "risk_adjusted": "Risk-adjusted score with stronger volatility and drawdown penalty",
    "liquidity_quality": "Liquidity and stability focused score",
    "role_aware": "Role-specific score: offensive momentum, defensive stability, hedge short-term tactical",
}
QUALITY_GATE_CONFIGS = {
    "none": "No ETF quality filter",
    "no_wide_extreme": "Exclude ETFs with wide/extreme NAV premium-discount flags",
    "no_watch_plus": "Exclude ETFs with watch/wide/extreme NAV premium-discount flags",
    "aum_p20": "Exclude ETFs below the per-date 20th percentile AUM",
    "tracking_gap_p90": "Exclude ETFs above the per-date 90th percentile tracking-gap absolute value",
    "quality_combo": "Exclude wide/extreme premium flags, low AUM, and large tracking-gap ETFs",
    "strict_quality": "Keep only normal premium flags with stronger AUM/tracking-gap filters",
}
LABEL_CONFIGS = {
    "top1": {
        "column": "label_top_role_1m",
        "prob_column": "ai_prob_top1_role",
        "score_column": "sleeve_risk_adj_1m",
        "description": "1M risk-adjusted return best role",
    },
    "top2": {
        "column": "label_top2_role_1m",
        "prob_column": "ai_prob_top2_role",
        "score_column": "sleeve_risk_adj_1m",
        "description": "1M risk-adjusted return top 2 role",
    },
    "positive": {
        "column": "label_positive_risk_adj_1m",
        "prob_column": "ai_prob_positive_role",
        "score_column": "sleeve_risk_adj_1m",
        "description": "1M risk-adjusted return > 0",
    },
    "horizon_v1_top1": {
        "column": "label_horizon_v1_top_role",
        "prob_column": "ai_prob_horizon_v1_top_role",
        "score_column": "role_objective_score_v1",
        "description": "Role-specific horizon V1 best role",
    },
    "horizon_v1_positive": {
        "column": "label_horizon_v1_positive",
        "prob_column": "ai_prob_horizon_v1_positive",
        "score_column": "role_objective_score_v1",
        "description": "Role-specific horizon V1 objective > 0",
    },
    "horizon_v2_top1": {
        "column": "label_horizon_v2_top_role",
        "prob_column": "ai_prob_horizon_v2_top_role",
        "score_column": "role_objective_score_v2",
        "description": "Role-specific horizon V2 best role",
    },
}

MARKET_FEATURES = [
    "qm_market_market_state_score",
    "qm_market_trend_score",
    "qm_market_breadth_score",
    "qm_market_risk_score",
    "qm_market_defensive_flow_score",
    "qm_market_kospi_ret_1m",
    "qm_market_kospi_ret_3m",
    "qm_market_kosdaq_ret_1m",
    "qm_market_kosdaq_ret_3m",
    "qm_market_market_vol_20d",
    "qm_market_market_mdd_3m",
    "qm_market_market_breadth_ret_pos_1m",
    "qm_market_market_breadth_above_sma20",
    "qm_market_market_breadth_above_sma60",
    "qm_market_market_breadth_above_sma120",
    "qm_market_new_high_ratio_20d",
    "qm_market_new_low_ratio_20d",
    "qm_market_trading_value_expansion_ratio",
    "qm_market_risk_on_score",
    "qm_market_risk_off_score",
    "qm_risk_usdkrw_ret_1m",
    "qm_risk_gold_proxy_ret_1m",
    "qm_risk_bond_proxy_ret_1m",
    "qm_risk_inverse_etf_ret_1m",
    "qm_risk_defensive_asset_strength_score",
    "qm_risk_market_stress_score",
    "qm_risk_drawdown_pressure_score",
    "qm_risk_crash_warning_flag",
    "qm_flow_foreign_net_buy_ratio",
    "qm_flow_institution_net_buy_ratio",
    "qm_flow_retail_net_buy_ratio",
    "qm_flow_foreign_buying_breadth",
    "qm_flow_institution_buying_breadth",
    "qm_flow_flow_concentration_score",
    "qm_flow_smart_money_score",
    "qm_flow_flow_context_available",
]

ROLE_FEATURES = [
    "sleeve_selection_score",
    "sleeve_ret_20d",
    "sleeve_ret_60d",
    "sleeve_ret_120d",
    "sleeve_vol_20d",
    "sleeve_vol_60d",
    "sleeve_dd_60d",
    "sleeve_dist_ma20",
    "sleeve_dist_ma60",
    "sleeve_rsi20",
    "sleeve_liquidity_log",
    "sleeve_premium_discount",
    "sleeve_aum_log",
    "sleeve_mcap_to_aum",
    "sleeve_daily_tracking_gap_pct",
    "sleeve_count",
]

RULE_WEIGHTS = {
    "risk_on": {
        "CORE_BETA": 0.30,
        "SECTOR_THEME": 0.30,
        "STYLE_FACTOR": 0.20,
        "DEFENSIVE_HEDGE": 0.10,
        "TACTICAL_HEDGE": 0.00,
        "TACTICAL_LEVERAGE": 0.10,
    },
    "neutral": {
        "CORE_BETA": 0.30,
        "SECTOR_THEME": 0.15,
        "STYLE_FACTOR": 0.25,
        "DEFENSIVE_HEDGE": 0.25,
        "TACTICAL_HEDGE": 0.05,
        "TACTICAL_LEVERAGE": 0.00,
    },
    "risk_off": {
        "CORE_BETA": 0.10,
        "SECTOR_THEME": 0.05,
        "STYLE_FACTOR": 0.10,
        "DEFENSIVE_HEDGE": 0.50,
        "TACTICAL_HEDGE": 0.25,
        "TACTICAL_LEVERAGE": 0.00,
    },
}


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.replace({np.nan: None}).to_json(orient="records", force_ascii=False))


def _normalize(group: pd.Series) -> pd.Series:
    values = pd.to_numeric(group, errors="coerce")
    if values.notna().sum() < 2:
        return pd.Series(np.zeros(len(values)), index=values.index)
    std = values.std(ddof=0)
    if not std or pd.isna(std):
        return pd.Series(np.zeros(len(values)), index=values.index)
    return (values - values.mean()) / std


def _role_rank_score(df: pd.DataFrame, selection_mode: str) -> pd.Series:
    if selection_mode not in SELECTION_SCORE_MODES:
        raise SystemExit(f"unknown selection mode: {selection_mode}")
    by_date = df.groupby("signal_date", group_keys=False)
    ret_20 = by_date["ret_20d"].transform(_normalize)
    ret_60 = by_date["ret_60d"].transform(_normalize)
    ret_120 = by_date["ret_120d"].transform(_normalize)
    ma_gap = by_date["dist_ma60"].transform(_normalize)
    ma20_gap = by_date["dist_ma20"].transform(_normalize)
    vol = by_date["vol_60d"].transform(_normalize)
    vol20 = by_date["vol_20d"].transform(_normalize)
    dd = by_date["dd_60d"].transform(_normalize)
    rsi = by_date["rsi20"].transform(_normalize)
    liquidity = by_date["liquidity_20d_value"].transform(lambda s: _normalize(np.log1p(pd.to_numeric(s, errors="coerce").clip(lower=0))))
    balanced = 0.25 * ret_20 + 0.30 * ret_60 + 0.20 * ret_120 + 0.10 * ma_gap + 0.10 * liquidity - 0.15 * vol + 0.10 * dd
    if selection_mode == "balanced":
        return balanced
    if selection_mode == "momentum":
        return 0.35 * ret_20 + 0.30 * ret_60 + 0.20 * ret_120 + 0.15 * ma_gap - 0.05 * vol
    if selection_mode == "risk_adjusted":
        return 0.20 * ret_20 + 0.25 * ret_60 + 0.15 * ret_120 + 0.15 * liquidity - 0.25 * vol - 0.15 * vol20 + 0.20 * dd
    if selection_mode == "liquidity_quality":
        return 0.35 * liquidity + 0.20 * ret_60 + 0.15 * ret_120 - 0.20 * vol + 0.20 * dd + 0.10 * ma_gap

    offensive = df["role_key"].isin(["CORE_BETA", "SECTOR_THEME", "STYLE_FACTOR"])
    defensive = df["role_key"].isin(["DEFENSIVE_HEDGE"])
    hedge = df["role_key"].isin(["TACTICAL_HEDGE"])
    leverage = df["role_key"].isin(["TACTICAL_LEVERAGE"])
    out = balanced.copy()
    out.loc[offensive] = (0.30 * ret_20 + 0.30 * ret_60 + 0.20 * ret_120 + 0.15 * ma_gap + 0.10 * liquidity - 0.10 * vol).loc[offensive]
    out.loc[defensive] = (0.30 * liquidity - 0.25 * vol + 0.25 * dd + 0.10 * ret_60 + 0.10 * ma20_gap).loc[defensive]
    out.loc[hedge] = (-0.25 * ret_20 + 0.25 * ma20_gap + 0.20 * rsi + 0.20 * liquidity - 0.10 * vol20).loc[hedge]
    out.loc[leverage] = (0.45 * ret_20 + 0.25 * ma20_gap + 0.15 * rsi + 0.15 * liquidity - 0.20 * vol20).loc[leverage]
    return out


def _load_or_build_mart(asof: str, rebuild: bool) -> pd.DataFrame:
    token = asof.replace("-", "")
    mart_path = REPORT_DIR / f"etf_ai_market_context_mart_{token}.csv"
    if mart_path.exists() and not rebuild:
        df = pd.read_csv(mart_path, dtype={"ticker": str}, low_memory=False)
        for col in ("signal_date", "feature_date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    mart = build_mart(asof)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    mart.to_csv(mart_path, index=False, encoding="utf-8-sig")
    return mart


def _text_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([""] * len(df), index=df.index)
    return df[col].fillna("").astype(str).str.lower()


def _num_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.zeros(len(df)), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def _ensure_qm_label_aliases(df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "qm_market_market_state_label": ["qm_market_state_label"],
        "qm_risk_volatility_regime_label": ["qm_market_volatility_regime_label", "qm_volatility_regime_label"],
    }
    for canonical, candidates in aliases.items():
        if canonical in df.columns:
            continue
        for candidate in candidates:
            if candidate in df.columns:
                df[canonical] = df[candidate]
                break
    return df


def _date_quantile(series: pd.Series, q: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() < 5:
        return pd.Series([np.nan] * len(values), index=values.index)
    return pd.Series([values.quantile(q)] * len(values), index=values.index)


def apply_quality_gate(df: pd.DataFrame, quality_gate: str) -> pd.DataFrame:
    if quality_gate not in QUALITY_GATE_CONFIGS:
        raise SystemExit(f"unknown quality gate: {quality_gate}")
    out = df.copy()
    if quality_gate == "none":
        out["quality_gate"] = quality_gate
        return out

    flag = out.get("etf_metric_premium_discount_quality_flag")
    if flag is None:
        flag = pd.Series(["missing"] * len(out), index=out.index)
    flag = flag.fillna("missing").astype(str).str.lower()

    aum = pd.to_numeric(out.get("etf_metric_aum"), errors="coerce")
    gap = pd.to_numeric(out.get("etf_metric_daily_tracking_gap_abs_pct"), errors="coerce")
    aum_p20 = out.groupby("signal_date")["etf_metric_aum"].transform(lambda s: _date_quantile(s, 0.20))
    aum_p30 = out.groupby("signal_date")["etf_metric_aum"].transform(lambda s: _date_quantile(s, 0.30))
    gap_p90 = out.groupby("signal_date")["etf_metric_daily_tracking_gap_abs_pct"].transform(lambda s: _date_quantile(s, 0.90))
    gap_p80 = out.groupby("signal_date")["etf_metric_daily_tracking_gap_abs_pct"].transform(lambda s: _date_quantile(s, 0.80))

    keep = pd.Series(True, index=out.index)
    if quality_gate == "no_wide_extreme":
        keep &= ~flag.isin(["wide", "extreme"])
    elif quality_gate == "no_watch_plus":
        keep &= ~flag.isin(["watch", "wide", "extreme"])
    elif quality_gate == "aum_p20":
        keep &= aum.isna() | aum_p20.isna() | aum.ge(aum_p20)
    elif quality_gate == "tracking_gap_p90":
        keep &= gap.isna() | gap_p90.isna() | gap.le(gap_p90)
    elif quality_gate == "quality_combo":
        keep &= ~flag.isin(["wide", "extreme"])
        keep &= aum.isna() | aum_p20.isna() | aum.ge(aum_p20)
        keep &= gap.isna() | gap_p90.isna() | gap.le(gap_p90)
    elif quality_gate == "strict_quality":
        keep &= flag.eq("normal")
        keep &= aum.isna() | aum_p30.isna() | aum.ge(aum_p30)
        keep &= gap.isna() | gap_p80.isna() | gap.le(gap_p80)

    out = out[keep].copy()
    out["quality_gate"] = quality_gate
    return out


def apply_regime_mapping(mart: pd.DataFrame, regime_map: str) -> pd.DataFrame:
    if regime_map not in REGIME_MAPS:
        raise SystemExit(f"unknown regime map: {regime_map}")
    out = mart.copy()
    out = _ensure_qm_label_aliases(out)
    risk_on = _num_col(out, "qm_market_risk_on_score")
    risk_off = _num_col(out, "qm_market_risk_off_score")
    state_score = _num_col(out, "qm_market_market_state_score")
    trend = _num_col(out, "qm_market_trend_score")
    stress = _num_col(out, "qm_risk_market_stress_score")
    crash = _num_col(out, "qm_risk_crash_warning_flag")
    state_label = _text_col(out, "qm_market_market_state_label")
    vol_label = _text_col(out, "qm_risk_volatility_regime_label")

    if regime_map == "score_default":
        mode = np.select(
            [(risk_on >= 1.0) & (risk_on >= risk_off) & (state_score >= 0), (risk_off >= 1.0) & (risk_off > risk_on)],
            ["risk_on", "risk_off"],
            default="neutral",
        )
    elif regime_map == "label_vol":
        mode = np.select(
            [
                vol_label.eq("stress") | crash.ge(1) | state_label.isin(["down", "strong_down"]),
                state_label.isin(["strong_up", "up"]) & ~vol_label.isin(["high", "stress"]),
            ],
            ["risk_off", "risk_on"],
            default="neutral",
        )
    elif regime_map == "score_diff":
        spread = risk_on - risk_off
        mode = np.select(
            [
                (spread >= 0.5) | ((state_score >= 0.5) & risk_off.lt(1.0)),
                (spread <= -0.5) | (state_score <= -0.5) | vol_label.eq("stress") | stress.ge(2.5),
            ],
            ["risk_on", "risk_off"],
            default="neutral",
        )
    elif regime_map == "strict":
        mode = np.select(
            [
                (risk_on >= 1.0) & (state_score >= 0.5) & (trend > 0) & risk_off.lt(1.0) & ~vol_label.isin(["high", "stress"]),
                (risk_off >= 1.0) | (state_score <= -0.25) | vol_label.eq("stress") | crash.ge(1) | stress.ge(2.5),
            ],
            ["risk_on", "risk_off"],
            default="neutral",
        )
    else:
        mode = np.select(
            [state_label.isin(["strong_up", "up"]), state_label.isin(["down", "strong_down"])],
            ["risk_on", "risk_off"],
            default="neutral",
        )
    out["regime_mode"] = mode
    out["regime_map"] = regime_map
    return out


def build_role_sleeves(
    mart: pd.DataFrame,
    top_n: int,
    selection_mode: str,
    quality_gate: str = "none",
    require_forward: bool = True,
) -> pd.DataFrame:
    df = mart.copy()
    df = _ensure_qm_label_aliases(df)
    df["role_key"] = df.get("role_key", df["role_key_derived"]).fillna(df["role_key_derived"])
    df["role_key"] = df["role_key"].where(df["role_key"].isin(ROLES), df["role_key_derived"])
    for col in [
        "liquidity_20d_value",
        "ret_20d",
        "ret_60d",
        "ret_120d",
        "vol_20d",
        "vol_60d",
        "dd_60d",
        "dist_ma20",
        "dist_ma60",
        "rsi20",
        "fwd_ret_1m",
        "path_mdd_1m",
        "risk_adj_1m",
        "fwd_ret_1w",
        "path_mdd_1w",
        "risk_adj_1w",
        "fwd_ret_2w",
        "path_mdd_2w",
        "risk_adj_2w",
        "fwd_ret_3M",
        "path_mdd_3M",
        "risk_adj_3M",
        "etf_metric_nav",
        "etf_metric_premium_discount",
        "etf_metric_aum",
        "etf_metric_aum_log",
        "etf_metric_mcap",
        "etf_metric_mcap_to_aum",
        "etf_metric_underlying_index_level",
        "etf_metric_underlying_index_return_pct",
        "etf_metric_etf_return_pct",
        "etf_metric_daily_tracking_gap_pct",
        "etf_metric_daily_tracking_gap_abs_pct",
    ]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "etf_metric_premium_discount_quality_flag" not in df.columns:
        df["etf_metric_premium_discount_quality_flag"] = "missing"
    df = apply_quality_gate(df, quality_gate)
    df["selection_score"] = _role_rank_score(df, selection_mode)
    df = df[df["role_key"].isin(ROLES)].copy()
    if require_forward:
        df = df[df["fwd_ret_1m"].notna()].copy()
    df = df.sort_values(["signal_date", "role_key", "selection_score"], ascending=[True, True, False])
    top = df.groupby(["signal_date", "role_key"], group_keys=False).head(top_n).copy()
    agg = (
        top.groupby(["signal_date", "role_key"], dropna=False)
        .agg(
            regime_mode=("regime_mode", "first"),
            market_state_label=("qm_market_market_state_label", "first"),
            volatility_regime_label=("qm_risk_volatility_regime_label", "first"),
            sleeve_count=("ticker", "count"),
            sleeve_selection_score=("selection_score", "mean"),
            sleeve_ret_20d=("ret_20d", "mean"),
            sleeve_ret_60d=("ret_60d", "mean"),
            sleeve_ret_120d=("ret_120d", "mean"),
            sleeve_vol_20d=("vol_20d", "mean"),
            sleeve_vol_60d=("vol_60d", "mean"),
            sleeve_dd_60d=("dd_60d", "mean"),
            sleeve_dist_ma20=("dist_ma20", "mean"),
            sleeve_dist_ma60=("dist_ma60", "mean"),
            sleeve_rsi20=("rsi20", "mean"),
            sleeve_liquidity=("liquidity_20d_value", "mean"),
            sleeve_premium_discount=("etf_metric_premium_discount", "mean"),
            sleeve_aum_log=("etf_metric_aum_log", "mean"),
            sleeve_mcap_to_aum=("etf_metric_mcap_to_aum", "mean"),
            sleeve_daily_tracking_gap_pct=("etf_metric_daily_tracking_gap_pct", "mean"),
            sleeve_fwd_ret_1w=("fwd_ret_1w", "mean"),
            sleeve_path_mdd_1w=("path_mdd_1w", "mean"),
            sleeve_risk_adj_1w=("risk_adj_1w", "mean"),
            sleeve_fwd_ret_2w=("fwd_ret_2w", "mean"),
            sleeve_path_mdd_2w=("path_mdd_2w", "mean"),
            sleeve_risk_adj_2w=("risk_adj_2w", "mean"),
            sleeve_fwd_ret_1m=("fwd_ret_1m", "mean"),
            sleeve_path_mdd_1m=("path_mdd_1m", "mean"),
            sleeve_risk_adj_1m=("risk_adj_1m", "mean"),
            sleeve_fwd_ret_3M=("fwd_ret_3M", "mean"),
            sleeve_path_mdd_3M=("path_mdd_3M", "mean"),
            sleeve_risk_adj_3M=("risk_adj_3M", "mean"),
            tickers=("ticker", lambda s: ",".join(s.astype(str).str.zfill(6))),
            names=("name", lambda s: " | ".join(s.astype(str))),
        )
        .reset_index()
    )
    agg["sleeve_liquidity_log"] = np.log1p(pd.to_numeric(agg["sleeve_liquidity"], errors="coerce").clip(lower=0))
    context_cols = [col for col in MARKET_FEATURES if col in df.columns]
    context = df[["signal_date", *context_cols]].drop_duplicates("signal_date", keep="last")
    return agg.merge(context, on="signal_date", how="left")


def add_labels(sleeves: pd.DataFrame) -> pd.DataFrame:
    out = sleeves.copy()
    out["role_rank_risk_adj_1m"] = out.groupby("signal_date")["sleeve_risk_adj_1m"].rank(ascending=False, method="first")
    out["label_top_role_1m"] = (out["role_rank_risk_adj_1m"] == 1).astype(int)
    out["label_top2_role_1m"] = (out["role_rank_risk_adj_1m"] <= 2).astype(int)
    out["label_positive_risk_adj_1m"] = (out["sleeve_risk_adj_1m"] > 0).astype(int)

    offensive = out["role_key"].isin(["CORE_BETA", "SECTOR_THEME", "STYLE_FACTOR"])
    defensive = out["role_key"].isin(["DEFENSIVE_HEDGE", "TACTICAL_HEDGE"])
    leverage = out["role_key"].eq("TACTICAL_LEVERAGE")

    out["role_objective_score_v1"] = np.nan
    out.loc[offensive, "role_objective_score_v1"] = out.loc[offensive, "sleeve_risk_adj_1m"]
    out.loc[defensive, "role_objective_score_v1"] = (
        pd.to_numeric(out.loc[defensive, "sleeve_fwd_ret_1m"], errors="coerce")
        + pd.to_numeric(out.loc[defensive, "sleeve_path_mdd_1m"], errors="coerce")
    )
    out.loc[leverage, "role_objective_score_v1"] = out.loc[leverage, "sleeve_risk_adj_2w"]

    out["role_objective_score_v2"] = np.nan
    out.loc[offensive, "role_objective_score_v2"] = out.loc[offensive, "sleeve_risk_adj_3M"]
    out.loc[defensive, "role_objective_score_v2"] = (
        pd.to_numeric(out.loc[defensive, "sleeve_fwd_ret_1m"], errors="coerce")
        + pd.to_numeric(out.loc[defensive, "sleeve_path_mdd_1m"], errors="coerce")
    )
    out.loc[leverage, "role_objective_score_v2"] = out.loc[leverage, "sleeve_risk_adj_2w"]

    for version in ("v1", "v2"):
        score_col = f"role_objective_score_{version}"
        valid = out[score_col].notna()
        rank_col = f"role_rank_horizon_{version}"
        label_col = f"label_horizon_{version}_top_role"
        out[rank_col] = np.nan
        out.loc[valid, rank_col] = out.loc[valid].groupby("signal_date")[score_col].rank(ascending=False, method="first")
        out[label_col] = np.nan
        out.loc[valid, label_col] = (out.loc[valid, rank_col] == 1).astype(int)
    out["label_horizon_v1_positive"] = np.where(
        out["role_objective_score_v1"].notna(),
        (out["role_objective_score_v1"] > 0).astype(int),
        np.nan,
    )
    return out


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric = [col for col in [*MARKET_FEATURES, *ROLE_FEATURES] if col in df.columns and df[col].notna().any()]
    categorical = ["role_key", "regime_mode", "market_state_label", "volatility_regime_label"]
    categorical = [col for col in categorical if col in df.columns]
    return numeric, categorical


def _fit_role_model(train: pd.DataFrame, label: str) -> Pipeline:
    numeric, categorical = _feature_columns(train)
    prep = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ],
        remainder="drop",
    )
    model = GradientBoostingClassifier(n_estimators=160, learning_rate=0.04, max_depth=2, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", prep), ("model", model)])
    max_date = train["signal_date"].max()
    weight = np.ones(len(train), dtype=float)
    weight[train["signal_date"].ge(max_date - pd.DateOffset(years=2)).to_numpy()] = 2.0
    pipe.fit(train, train[label].astype(int), model__sample_weight=weight)
    return pipe


def _normalize_weights(weights: dict[str, float], available_roles: set[str]) -> dict[str, float]:
    clipped = {role: max(0.0, float(weights.get(role, 0.0))) for role in ROLES if role in available_roles}
    total = sum(clipped.values())
    if total <= 0:
        n = max(1, len(available_roles))
        return {role: (1.0 / n if role in available_roles else 0.0) for role in ROLES}
    return {role: value / total for role, value in clipped.items()}


def _learned_weights(train: pd.DataFrame) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for mode, part in train.groupby("regime_mode"):
        means = part.groupby("role_key")["sleeve_risk_adj_1m"].mean().reindex(ROLES)
        centered = means - means.min(skipna=True)
        raw = {role: float(value) if pd.notna(value) else 0.0 for role, value in centered.items()}
        result[str(mode)] = _normalize_weights(raw, set(part["role_key"]))
    return result


def _evaluate_policy(
    scored: pd.DataFrame,
    policy: str,
    prob_column: str,
    oracle_score_column: str,
    learned: dict[str, dict[str, float]] | None = None,
) -> pd.DataFrame:
    rows = []
    for date, part in scored.groupby("signal_date"):
        available = set(part["role_key"])
        mode = str(part["regime_mode"].iloc[0])
        role_map = part.set_index("role_key")
        if policy == "equal_role":
            weights = {role: 1.0 / len(available) for role in available}
        elif policy == "rule_mode_weight":
            weights = _normalize_weights(RULE_WEIGHTS.get(mode, {}), available)
        elif policy == "learned_mode_weight":
            weights = _normalize_weights((learned or {}).get(mode, {}), available)
        elif policy == "ai_top1_role":
            chosen = str(part.sort_values(prob_column, ascending=False).iloc[0]["role_key"])
            weights = {chosen: 1.0}
        elif policy == "ai_top2_equal":
            chosen_roles = part.sort_values(prob_column, ascending=False).head(2)["role_key"].astype(str).tolist()
            weights = {role: 1.0 / len(chosen_roles) for role in chosen_roles}
        elif policy == "ai_prob_weight":
            raw = part.set_index("role_key")[prob_column].clip(lower=0).to_dict()
            weights = _normalize_weights(raw, available)
        elif policy == "oracle_best_role":
            chosen = str(part.sort_values(oracle_score_column, ascending=False).iloc[0]["role_key"])
            weights = {chosen: 1.0}
        else:
            raise ValueError(f"unknown policy: {policy}")

        ret = 0.0
        mdd = 0.0
        risk_adj = 0.0
        exposures = {}
        for role, weight in weights.items():
            if role not in role_map.index:
                continue
            row = role_map.loc[role]
            ret += weight * float(row["sleeve_fwd_ret_1m"])
            mdd += weight * float(row["sleeve_path_mdd_1m"])
            risk_adj += weight * float(row["sleeve_risk_adj_1m"])
            exposures[f"w_{role}"] = weight
        rows.append(
            {
                "signal_date": date,
                "policy": policy,
                "regime_mode": mode,
                "fwd_ret_1m": ret,
                "path_mdd_1m": mdd,
                "risk_adj_1m": risk_adj,
                "hit_1m": int(ret > 0),
                **{f"w_{role}": exposures.get(f"w_{role}", 0.0) for role in ROLES},
            }
        )
    return pd.DataFrame(rows)


def _policy_summary(policy_returns: pd.DataFrame) -> pd.DataFrame:
    return (
        policy_returns.groupby("policy")
        .agg(
            rows=("signal_date", "count"),
            avg_1m_ret=("fwd_ret_1m", "mean"),
            hit_rate=("hit_1m", "mean"),
            avg_1m_mdd=("path_mdd_1m", "mean"),
            avg_1m_risk_adj=("risk_adj_1m", "mean"),
            worst_1m_ret=("fwd_ret_1m", "min"),
            avg_core_beta=("w_CORE_BETA", "mean"),
            avg_sector_theme=("w_SECTOR_THEME", "mean"),
            avg_style_factor=("w_STYLE_FACTOR", "mean"),
            avg_defensive=("w_DEFENSIVE_HEDGE", "mean"),
            avg_tactical_hedge=("w_TACTICAL_HEDGE", "mean"),
            avg_tactical_leverage=("w_TACTICAL_LEVERAGE", "mean"),
        )
        .reset_index()
        .sort_values("avg_1m_risk_adj", ascending=False)
    )


def run_experiment(
    asof: str,
    train_end: str,
    valid_start: str,
    top_n: int,
    label_key: str,
    regime_map: str,
    selection_mode: str,
    quality_gate: str,
    rebuild_mart: bool,
) -> dict[str, Any]:
    if label_key not in LABEL_CONFIGS:
        raise SystemExit(f"unknown label: {label_key}")
    label_cfg = LABEL_CONFIGS[label_key]
    target_label = label_cfg["column"]
    prob_column = label_cfg["prob_column"]
    score_column = label_cfg["score_column"]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    suffix = f"{token}_top{top_n}_{label_key}_{regime_map}_{selection_mode}_{quality_gate}"
    mart = apply_regime_mapping(_load_or_build_mart(asof, rebuild_mart), regime_map)
    sleeves = add_labels(build_role_sleeves(mart, top_n=top_n, selection_mode=selection_mode, quality_gate=quality_gate))
    sleeves_path = REPORT_DIR / f"etf_role_sleeves_{suffix}.csv"
    scored_path = REPORT_DIR / f"etf_role_ai_scored_{suffix}.csv"
    policy_path = REPORT_DIR / f"etf_role_allocation_policy_returns_{suffix}.csv"
    summary_path = REPORT_DIR / f"etf_role_allocation_policy_summary_{suffix}.csv"
    result_json = REPORT_DIR / f"etf_role_allocation_experiment_{suffix}.json"
    result_md = REPORT_DIR / f"etf_role_allocation_experiment_{suffix}.md"
    sleeves.to_csv(sleeves_path, index=False, encoding="utf-8-sig")

    labeled = sleeves[sleeves[target_label].notna() & sleeves[score_column].notna()].copy()
    train = labeled[labeled["signal_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["signal_date"] >= pd.Timestamp(valid_start)) & (labeled["signal_date"] <= pd.Timestamp(asof))].copy()
    if train.empty or valid.empty or train[target_label].nunique() < 2 or valid[target_label].nunique() < 2:
        raise SystemExit(f"insufficient rows or one-class target for label={label_key}")
    model = _fit_role_model(train, target_label)
    valid = valid.copy()
    valid[prob_column] = model.predict_proba(valid)[:, 1]
    valid.to_csv(scored_path, index=False, encoding="utf-8-sig")

    auc = roc_auc_score(valid[target_label].astype(int), valid[prob_column])
    top_pred = valid.sort_values(["signal_date", prob_column], ascending=[True, False]).groupby("signal_date").head(1)
    learned = _learned_weights(train)
    policy_frames = [
        _evaluate_policy(valid, policy, prob_column=prob_column, oracle_score_column=score_column, learned=learned)
        for policy in [
            "equal_role",
            "rule_mode_weight",
            "learned_mode_weight",
            "ai_top1_role",
            "ai_top2_equal",
            "ai_prob_weight",
            "oracle_best_role",
        ]
    ]
    policy_returns = pd.concat(policy_frames, ignore_index=True)
    policy_summary = _policy_summary(policy_returns)
    policy_returns.to_csv(policy_path, index=False, encoding="utf-8-sig")
    policy_summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    latest = valid[valid["signal_date"].eq(valid["signal_date"].max())].copy()
    latest_roles = latest.sort_values(prob_column, ascending=False)[
        [
            "signal_date",
            "regime_mode",
            "market_state_label",
            "volatility_regime_label",
            "role_key",
            prob_column,
            score_column,
            "sleeve_fwd_ret_1m",
            "sleeve_path_mdd_1m",
            "sleeve_risk_adj_1m",
            "tickers",
            "names",
        ]
    ]
    diagnostics = {
        "source_name": "etf_role_allocation_ai_v01_experiment",
        "model_code": MODEL_CODE,
        "as_of_date": asof,
        "label_key": label_key,
        "label_column": target_label,
        "label_description": label_cfg["description"],
        "regime_map": regime_map,
        "regime_map_description": REGIME_MAPS[regime_map],
        "selection_mode": selection_mode,
        "selection_mode_description": SELECTION_SCORE_MODES[selection_mode],
        "quality_gate": quality_gate,
        "quality_gate_description": QUALITY_GATE_CONFIGS[quality_gate],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "top_n_per_role": top_n,
        "train_end": train_end,
        "valid_start": valid_start,
        "mart_rows": int(len(mart)),
        "sleeve_rows": int(len(sleeves)),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "valid_dates": int(valid["signal_date"].nunique()),
        "auc": _safe_float(auc),
        "top_pick_label_rate": _safe_float(top_pred[target_label].mean()),
        "regime_counts": _records(sleeves[["signal_date", "regime_mode"]].drop_duplicates()["regime_mode"].value_counts().rename_axis("regime_mode").reset_index(name="count")),
        "role_counts": _records(sleeves["role_key"].value_counts().rename_axis("role_key").reset_index(name="count")),
        "learned_mode_weights": learned,
        "policy_summary": _records(policy_summary),
        "latest_role_scores": _records(latest_roles),
        "outputs": {
            "sleeves_csv": str(sleeves_path),
            "scored_csv": str(scored_path),
            "policy_returns_csv": str(policy_path),
            "policy_summary_csv": str(summary_path),
            "json": str(result_json),
            "md": str(result_md),
            "doc": str(DOC_PATH),
        },
    }
    result_json.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(result_md, diagnostics, policy_summary, latest_roles)
    _write_doc(diagnostics, policy_summary)
    return diagnostics


def _fmt_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.2f}%"


def _write_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame, latest: pd.DataFrame) -> None:
    lines = [
        f"# ETF Role Allocation AI V01 Experiment - {payload['as_of_date']}",
        "",
        f"- Model code: `{MODEL_CODE}`",
        f"- Train end: `{payload['train_end']}`",
        f"- Valid start: `{payload['valid_start']}`",
        f"- Sleeve rows: {payload['sleeve_rows']:,}",
        f"- Label: `{payload['label_key']}` ({payload['label_description']})",
        f"- Regime map: `{payload['regime_map']}` ({payload['regime_map_description']})",
        f"- Selection mode: `{payload['selection_mode']}` ({payload['selection_mode_description']})",
        f"- Quality gate: `{payload['quality_gate']}` ({payload['quality_gate_description']})",
        f"- AUC: {payload['auc']}",
        f"- Top pick label rate: {payload['top_pick_label_rate']}",
        "",
        "## Policy Summary",
        "",
        "| policy | avg 1M ret | hit rate | avg 1M MDD | avg risk adj | worst 1M ret |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        lines.append(
            f"| `{row['policy']}` | {_fmt_pct(row['avg_1m_ret'])} | {_fmt_pct(row['hit_rate'])} | "
            f"{_fmt_pct(row['avg_1m_mdd'])} | {_fmt_pct(row['avg_1m_risk_adj'])} | {_fmt_pct(row['worst_1m_ret'])} |"
        )
    lines.extend(["", "## Latest Role Scores", "", "| role | AI prob | tickers |", "|---|---:|---|"])
    for row in latest.to_dict("records"):
        prob_cols = [col for col in row.keys() if str(col).startswith("ai_prob_")]
        prob = float(row[prob_cols[0]]) if prob_cols else float("nan")
        lines.append(f"| `{row['role_key']}` | {prob:.4f} | {row['tickers']} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is the first experiment that treats ETF investing as role allocation, not single ETF picking.",
            "- `oracle_best_role` is an upper bound, not an investable policy.",
            "- If AI policies beat equal/rule policies on risk-adjusted return, the role-allocation AI track is worth extending.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_doc(payload: dict[str, Any], summary: pd.DataFrame) -> None:
    best = summary.iloc[0].to_dict() if not summary.empty else {}
    lines = [
        "# ETF 역할배분AI V01 1차 실험",
        "",
        "## 목적",
        "",
        "ETF를 개별 종목 선별 문제가 아니라 `6개 역할 포트폴리오`와 `3개 시장 모드`의 배분 문제로 재정의한다.",
        "",
        "## 구조",
        "",
        "- ETF별 feature와 forward return으로 역할별 sleeve를 구성한다.",
        "- 역할은 `CORE_BETA`, `SECTOR_THEME`, `STYLE_FACTOR`, `DEFENSIVE_HEDGE`, `TACTICAL_HEDGE`, `TACTICAL_LEVERAGE`로 둔다.",
        "- 시장 모드는 `risk_on`, `neutral`, `risk_off`로 둔다.",
        "- AI는 각 날짜/역할 조합이 다음 1개월 risk-adjusted return 기준 최상위 역할이 될 확률을 학습한다.",
        "",
        "## 핵심 결과",
        "",
        f"- 기준일: `{payload['as_of_date']}`",
        f"- Label: `{payload['label_key']}` ({payload['label_description']})",
        f"- Regime map: `{payload['regime_map']}` ({payload['regime_map_description']})",
        f"- Selection mode: `{payload['selection_mode']}` ({payload['selection_mode_description']})",
        f"- Quality gate: `{payload['quality_gate']}` ({payload['quality_gate_description']})",
        f"- AUC: `{payload['auc']}`",
        f"- Top pick label rate: `{payload['top_pick_label_rate']}`",
        f"- 최상위 정책: `{best.get('policy', '')}`",
        f"- 최상위 정책 평균 1M risk-adjusted return: `{_fmt_pct(best.get('avg_1m_risk_adj'))}`",
        "",
        "## 정책 비교",
        "",
        "| policy | avg 1M ret | hit rate | avg 1M MDD | avg risk adj |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary.to_dict("records"):
        lines.append(
            f"| `{row['policy']}` | {_fmt_pct(row['avg_1m_ret'])} | {_fmt_pct(row['hit_rate'])} | "
            f"{_fmt_pct(row['avg_1m_mdd'])} | {_fmt_pct(row['avg_1m_risk_adj'])} |"
        )
    lines.extend(
        [
            "",
            "## 현재 판단",
            "",
            "이번 실험은 ETF AI의 방향을 `시장국면별 역할 배분 모델`로 잡기 위한 1차 baseline이다.",
            "다음 단계에서는 역할 sleeve 구성 점수, 역할별 horizon, 그리고 시장 모드 mapping을 추가로 ablation한다.",
            "",
            "## Outputs",
            "",
            f"- `{payload['outputs']['sleeves_csv']}`",
            f"- `{payload['outputs']['scored_csv']}`",
            f"- `{payload['outputs']['policy_summary_csv']}`",
            f"- `{payload['outputs']['json']}`",
            f"- `{payload['outputs']['md']}`",
        ]
    )
    DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF role-allocation AI V01 experiment.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--label", default="top1", choices=sorted(LABEL_CONFIGS))
    parser.add_argument("--regime-map", default="score_default", choices=sorted(REGIME_MAPS))
    parser.add_argument("--selection-mode", default="balanced", choices=sorted(SELECTION_SCORE_MODES))
    parser.add_argument("--quality-gate", default="none", choices=sorted(QUALITY_GATE_CONFIGS))
    parser.add_argument("--rebuild-mart", action="store_true")
    args = parser.parse_args()
    result = run_experiment(
        args.asof,
        args.train_end,
        args.valid_start,
        args.top_n,
        args.label,
        args.regime_map,
        args.selection_mode,
        args.quality_gate,
        args.rebuild_mart,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "model_code": MODEL_CODE,
                "as_of_date": args.asof,
                "label": args.label,
                "regime_map": args.regime_map,
                "selection_mode": args.selection_mode,
                "quality_gate": args.quality_gate,
                "auc": result["auc"],
                "top_pick_label_rate": result["top_pick_label_rate"],
                "best_policy": result["policy_summary"][0] if result["policy_summary"] else {},
                "outputs": result["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
