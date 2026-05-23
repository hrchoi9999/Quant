from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_e_series_etf_role_taxonomy import STANDARD_ROLES, build_taxonomy
from scripts.run_etf_ai_label_ablation import build_mart


REPORT_DIR = ROOT / r"reports\e_series_etf"
STRATEGY_MODEL_CODE = "E-ETF-V01"

MODE_ROLE_WEIGHTS = {
    "risk_on": {
        "CORE_BETA": 0.30,
        "SECTOR_THEME": 0.30,
        "STYLE_FACTOR": 0.25,
        "DEFENSIVE": 0.05,
        "INCOME": 0.05,
        "CASH_LIKE": 0.05,
    },
    "neutral": {
        "CORE_BETA": 0.25,
        "SECTOR_THEME": 0.15,
        "STYLE_FACTOR": 0.20,
        "DEFENSIVE": 0.15,
        "INCOME": 0.15,
        "CASH_LIKE": 0.10,
    },
    "risk_off": {
        "CORE_BETA": 0.05,
        "SECTOR_THEME": 0.05,
        "STYLE_FACTOR": 0.10,
        "DEFENSIVE": 0.30,
        "INCOME": 0.25,
        "CASH_LIKE": 0.25,
    },
}


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _json_value(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if pd.isna(value):
            return None
        return round(float(value), 8)
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict("records")]


def _rank_pct(frame: pd.DataFrame, col: str, group_col: str = "signal_date", ascending: bool = True) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    values = pd.to_numeric(frame[col], errors="coerce")
    return values.groupby(frame[group_col]).rank(pct=True, ascending=ascending)


def _rank_pct_by(frame: pd.DataFrame, col: str, group_cols: list[str], ascending: bool = True) -> pd.Series:
    if col not in frame.columns or any(group_col not in frame.columns for group_col in group_cols):
        return pd.Series(np.nan, index=frame.index)
    values = pd.to_numeric(frame[col], errors="coerce")
    keys = [frame[group_col].fillna("UNKNOWN").astype(str) for group_col in group_cols]
    return values.groupby(keys).rank(pct=True, ascending=ascending)


def _group_mean_by(frame: pd.DataFrame, col: str, group_cols: list[str]) -> pd.Series:
    if col not in frame.columns or any(group_col not in frame.columns for group_col in group_cols):
        return pd.Series(np.nan, index=frame.index)
    values = pd.to_numeric(frame[col], errors="coerce")
    keys = [frame[group_col].fillna("UNKNOWN").astype(str) for group_col in group_cols]
    return values.groupby(keys).transform("mean")


def _derive_market_mode(frame: pd.DataFrame) -> pd.Series:
    if "regime_mode" in frame.columns:
        mode = frame["regime_mode"].fillna("").astype(str)
        clean = mode.where(mode.isin(["risk_on", "neutral", "risk_off"]), "")
    else:
        clean = pd.Series([""] * len(frame), index=frame.index)

    risk_on = pd.to_numeric(frame.get("qm_market_risk_on_score"), errors="coerce")
    risk_off = pd.to_numeric(frame.get("qm_market_risk_off_score"), errors="coerce")
    state = pd.to_numeric(frame.get("qm_market_market_state_score"), errors="coerce")
    stress = pd.to_numeric(frame.get("qm_risk_market_stress_score"), errors="coerce")

    inferred = np.select(
        [
            risk_off.fillna(0).sub(risk_on.fillna(0)).ge(0.18) | stress.fillna(0).ge(0.65),
            risk_on.fillna(0).sub(risk_off.fillna(0)).ge(0.18) & state.fillna(0).ge(0.45),
        ],
        ["risk_off", "risk_on"],
        default="neutral",
    )
    return clean.mask(clean.eq(""), inferred)


def _role_weight(row: pd.Series) -> float:
    mode = str(row.get("e_market_mode") or "neutral")
    role = str(row.get("e_series_role") or "STYLE_FACTOR")
    return float(MODE_ROLE_WEIGHTS.get(mode, MODE_ROLE_WEIGHTS["neutral"]).get(role, 0.0))


def _add_scores(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["e_liquidity_value_log"] = np.log1p(pd.to_numeric(out.get("liquidity_20d_value"), errors="coerce").clip(lower=0))
    out["e_liquidity_pct"] = _rank_pct(out, "liquidity_20d_value", ascending=True)
    if out["e_liquidity_pct"].isna().all() and "etf_metric_aum" in out.columns:
        out["e_liquidity_pct"] = _rank_pct(out, "etf_metric_aum", ascending=True)
    out["e_aum_pct"] = _rank_pct(out, "etf_metric_aum", ascending=True)
    out["e_liquidity_pct_in_role"] = _rank_pct_by(out, "liquidity_20d_value", ["signal_date", "e_series_role"], ascending=True)
    out["e_liquidity_pct_in_asset"] = _rank_pct_by(out, "liquidity_20d_value", ["signal_date", "e_asset_bucket"], ascending=True)
    out["e_aum_pct_in_role"] = _rank_pct_by(out, "etf_metric_aum", ["signal_date", "e_series_role"], ascending=True)
    out["e_aum_pct_in_asset"] = _rank_pct_by(out, "etf_metric_aum", ["signal_date", "e_asset_bucket"], ascending=True)
    out["e_tradeability_score"] = (
        out["e_liquidity_pct_in_role"].fillna(out["e_liquidity_pct"]).fillna(0.5) * 0.55
        + out["e_aum_pct_in_role"].fillna(out["e_aum_pct"]).fillna(0.5) * 0.45
    )
    out["e_momentum_score"] = (
        _rank_pct(out, "ret_20d", ascending=True).fillna(0.5) * 0.25
        + _rank_pct(out, "ret_60d", ascending=True).fillna(0.5) * 0.35
        + _rank_pct(out, "ret_120d", ascending=True).fillna(0.5) * 0.25
        + _rank_pct(out, "ret_240d", ascending=True).fillna(0.5) * 0.15
    )
    out["e_momentum_pct_in_role"] = _rank_pct_by(out, "ret_60d", ["signal_date", "e_series_role"], ascending=True)
    out["e_momentum_pct_in_asset"] = _rank_pct_by(out, "ret_60d", ["signal_date", "e_asset_bucket"], ascending=True)
    out["e_momentum_pct_in_theme"] = _rank_pct_by(out, "ret_60d", ["signal_date", "e_theme_bucket"], ascending=True)
    out["e_ret_60d_mean_role"] = _group_mean_by(out, "ret_60d", ["signal_date", "e_series_role"])
    out["e_ret_60d_mean_asset"] = _group_mean_by(out, "ret_60d", ["signal_date", "e_asset_bucket"])
    out["e_ret_60d_mean_theme"] = _group_mean_by(out, "ret_60d", ["signal_date", "e_theme_bucket"])
    out["e_excess_ret_60d_vs_role"] = pd.to_numeric(out.get("ret_60d"), errors="coerce") - out["e_ret_60d_mean_role"]
    out["e_excess_ret_60d_vs_asset"] = pd.to_numeric(out.get("ret_60d"), errors="coerce") - out["e_ret_60d_mean_asset"]
    out["e_excess_ret_60d_vs_theme"] = pd.to_numeric(out.get("ret_60d"), errors="coerce") - out["e_ret_60d_mean_theme"]
    vol_rank = _rank_pct(out, "vol_60d", ascending=True).fillna(0.5)
    dd_rank = _rank_pct(out, "dd_120d", ascending=True).fillna(0.5)
    out["e_vol_pct_in_role"] = _rank_pct_by(out, "vol_60d", ["signal_date", "e_series_role"], ascending=True)
    out["e_dd_pct_in_role"] = _rank_pct_by(out, "dd_120d", ["signal_date", "e_series_role"], ascending=True)
    out["e_risk_control_score"] = (1.0 - vol_rank) * 0.45 + dd_rank * 0.55
    out["e_risk_control_score_in_role"] = (
        (1.0 - out["e_vol_pct_in_role"].fillna(0.5)) * 0.45 + out["e_dd_pct_in_role"].fillna(0.5) * 0.55
    )
    premium_abs = pd.to_numeric(out.get("etf_metric_premium_discount_abs"), errors="coerce").fillna(0)
    tracking_abs = pd.to_numeric(out.get("etf_metric_daily_tracking_gap_abs_pct"), errors="coerce").fillna(0)
    out["e_premium_abs_pct_in_role"] = _rank_pct_by(
        out, "etf_metric_premium_discount_abs", ["signal_date", "e_series_role"], ascending=True
    )
    out["e_tracking_gap_abs_pct_in_role"] = _rank_pct_by(
        out, "etf_metric_daily_tracking_gap_abs_pct", ["signal_date", "e_series_role"], ascending=True
    )
    out["e_tracking_quality_score"] = (1.0 - premium_abs.clip(0, 2.0) / 2.0) * 0.55 + (
        1.0 - tracking_abs.clip(0, 3.0) / 3.0
    ) * 0.45
    out["e_tracking_quality_score_in_role"] = (
        (1.0 - out["e_premium_abs_pct_in_role"].fillna(0.5)) * 0.50
        + (1.0 - out["e_tracking_gap_abs_pct_in_role"].fillna(0.5)) * 0.50
    )
    leverage_penalty = np.where(out.get("is_leveraged", False).astype(str).str.lower().isin(["1", "true"]), 0.12, 0.0)
    inverse_penalty = np.where(out.get("is_inverse", False).astype(str).str.lower().isin(["1", "true"]), 0.08, 0.0)
    synthetic_penalty = np.where(out.get("e_is_synthetic", False).astype(str).str.lower().isin(["1", "true"]), 0.03, 0.0)
    review_penalty = np.where(out.get("e_taxonomy_review_flag", "OK").astype(str).eq("OK"), 0.0, 0.05)
    out["e_product_structure_score"] = (
        1.0
        - leverage_penalty
        - inverse_penalty
        - synthetic_penalty
        - review_penalty
    ).clip(0, 1)
    out["e_etf_integrity_score"] = (
        out["e_tracking_quality_score_in_role"].fillna(out["e_tracking_quality_score"]).fillna(0.5) * 0.45
        + out["e_product_structure_score"].fillna(0.8) * 0.25
        + pd.to_numeric(out.get("e_taxonomy_confidence"), errors="coerce").fillna(0.65).clip(0, 1) * 0.30
    )
    out["e_mode_asset_alignment_score"] = np.select(
        [
            out["e_market_mode"].eq("risk_on") & out["e_asset_bucket"].astype(str).str.startswith("EQUITY"),
            out["e_market_mode"].eq("risk_on") & out["e_strategy_bucket"].isin(["LEVERAGED_TACTICAL", "SECTOR_THEME", "GROWTH"]),
            out["e_market_mode"].eq("risk_off") & out["e_asset_bucket"].isin(["CASH_RATE", "BOND_SHORT", "BOND_CORE", "BOND_LONG", "FX_USD", "COMMODITY_GOLD"]),
            out["e_market_mode"].eq("risk_off") & out["e_strategy_bucket"].isin(["INVERSE_HEDGE", "CASH_RATE", "BOND_DURATION"]),
            out["e_market_mode"].eq("neutral") & out["e_strategy_bucket"].isin(["BROAD_BETA", "DIVIDEND_INCOME", "COVERED_CALL", "STYLE_FACTOR"]),
        ],
        [0.85, 0.80, 0.90, 0.75, 0.80],
        default=0.55,
    )
    out["e_quality_score"] = (
        out["e_tradeability_score"].fillna(0.5) * 0.35
        + out["e_etf_integrity_score"].fillna(0.5) * 0.30
        + out["e_risk_control_score_in_role"].fillna(out["e_risk_control_score"]).fillna(0.5) * 0.20
        + out["e_mode_asset_alignment_score"].fillna(0.55) * 0.15
    ).clip(0, 1)
    out["e_mode_role_weight"] = out.apply(_role_weight, axis=1)
    out["e_baseline_selection_score"] = (
        out["e_mode_role_weight"] * 0.35
        + out["e_momentum_score"].fillna(0.5) * 0.20
        + out["e_momentum_pct_in_role"].fillna(0.5) * 0.10
        + out["e_risk_control_score"].fillna(0.5) * 0.15
        + out["e_quality_score"].fillna(0.5) * 0.20
    )
    out["e_baseline_rank_in_role"] = out.groupby(["signal_date", "e_series_role"])["e_baseline_selection_score"].rank(
        method="first", ascending=False
    )
    out["e_baseline_rank_overall"] = out.groupby("signal_date")["e_baseline_selection_score"].rank(
        method="first", ascending=False
    )
    return out


def _add_labels(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    fwd_1m = pd.to_numeric(out.get("fwd_ret_1m"), errors="coerce")
    mdd_1m = pd.to_numeric(out.get("path_mdd_1m"), errors="coerce")
    risk_adj_1m = pd.to_numeric(out.get("risk_adj_1m"), errors="coerce")
    if risk_adj_1m.isna().all():
        risk_adj_1m = fwd_1m + mdd_1m.fillna(0) * 0.5
        out["risk_adj_1m"] = risk_adj_1m

    out["e_label_1m_positive"] = np.where(fwd_1m.notna(), (fwd_1m > 0).astype(int), np.nan)
    out["e_label_1m_drawdown_safe"] = np.where(
        fwd_1m.notna() & mdd_1m.notna(), ((fwd_1m >= 0) & (mdd_1m >= -0.05)).astype(int), np.nan
    )
    rank_role = risk_adj_1m.groupby([out["signal_date"], out["e_series_role"]]).rank(method="first", ascending=False)
    count_role = risk_adj_1m.groupby([out["signal_date"], out["e_series_role"]]).transform("count")
    out["e_label_role_top1_1m_risk_adj"] = np.where(risk_adj_1m.notna(), (rank_role <= 1).astype(int), np.nan)
    out["e_label_role_top3_1m_risk_adj"] = np.where(risk_adj_1m.notna(), (rank_role <= 3).astype(int), np.nan)
    out["e_label_role_top20pct_1m_risk_adj"] = np.where(
        risk_adj_1m.notna(), (rank_role <= np.ceil(count_role * 0.20)).astype(int), np.nan
    )
    rank_all = risk_adj_1m.groupby(out["signal_date"]).rank(method="first", ascending=False)
    count_all = risk_adj_1m.groupby(out["signal_date"]).transform("count")
    out["e_label_overall_top5_1m_risk_adj"] = np.where(risk_adj_1m.notna(), (rank_all <= 5).astype(int), np.nan)
    out["e_label_overall_top10pct_1m_risk_adj"] = np.where(
        risk_adj_1m.notna(), (rank_all <= np.ceil(count_all * 0.10)).astype(int), np.nan
    )
    return out


def build_e_series_mart_v2(asof: str, rebuild_taxonomy: bool = False) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    taxonomy_payload = build_taxonomy(asof) if rebuild_taxonomy else None
    taxonomy_path = REPORT_DIR / f"e_series_etf_role_taxonomy_{token}.csv"
    if not taxonomy_path.exists():
        taxonomy_payload = build_taxonomy(asof)
    taxonomy = pd.read_csv(taxonomy_path, dtype={"ticker": str}, low_memory=False)
    taxonomy["ticker"] = taxonomy["ticker"].astype(str).str.zfill(6)

    mart = build_mart(asof)
    mart["ticker"] = mart["ticker"].astype(str).str.zfill(6)
    for col in ["signal_date", "feature_date"]:
        if col in mart.columns:
            mart[col] = pd.to_datetime(mart[col], errors="coerce").dt.strftime("%Y-%m-%d")

    taxonomy_cols = [
        "ticker",
        "raw_role_key",
        "e_series_role",
        "role_confidence",
        "role_reason",
        "e_region_bucket",
        "e_asset_bucket",
        "e_strategy_bucket",
        "e_theme_bucket",
        "e_product_structure",
        "e_is_active_strategy",
        "e_is_synthetic",
        "e_is_currency_hedged",
        "e_is_covered_call",
        "e_is_tdf",
        "e_taxonomy_confidence",
        "e_taxonomy_review_flag",
        "is_active",
    ]
    mart = mart.drop(columns=[c for c in taxonomy_cols if c in mart.columns and c != "ticker"], errors="ignore")
    mart = mart.merge(taxonomy[taxonomy_cols], on="ticker", how="left")
    mart["e_series_role"] = mart["e_series_role"].fillna("STYLE_FACTOR")
    mart["e_region_bucket"] = mart["e_region_bucket"].fillna("KR")
    mart["e_asset_bucket"] = mart["e_asset_bucket"].fillna("OTHER")
    mart["e_strategy_bucket"] = mart["e_strategy_bucket"].fillna("OTHER")
    mart["e_theme_bucket"] = mart["e_theme_bucket"].fillna("NONE")
    mart["e_product_structure"] = mart["e_product_structure"].fillna("PLAIN")
    mart["e_taxonomy_review_flag"] = mart["e_taxonomy_review_flag"].fillna("UNKNOWN_DETAIL_BUCKET")
    mart["e_market_mode"] = _derive_market_mode(mart)
    mart["strategy_family"] = "E"
    mart["strategy_model_code"] = STRATEGY_MODEL_CODE

    mart = _add_scores(mart)
    mart = _add_labels(mart)

    mart_path = REPORT_DIR / f"e_series_etf_mart_v2_{token}.csv"
    sample_path = REPORT_DIR / f"e_series_etf_mart_v2_current_sample_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_mart_v2_{token}.json"
    mart.to_csv(mart_path, index=False, encoding="utf-8-sig")
    current = mart[mart["signal_date"].eq(asof)].sort_values("e_baseline_selection_score", ascending=False)
    current.head(100).to_csv(sample_path, index=False, encoding="utf-8-sig")

    role_summary = (
        mart.groupby("e_series_role", dropna=False)
        .agg(
            rows=("ticker", "size"),
            tickers=("ticker", "nunique"),
            avg_quality_score=("e_quality_score", "mean"),
            avg_baseline_score=("e_baseline_selection_score", "mean"),
            label_top3_rate=("e_label_role_top3_1m_risk_adj", "mean"),
        )
        .reset_index()
    )
    mode_summary = (
        mart.groupby("e_market_mode", dropna=False)
        .agg(
            rows=("ticker", "size"),
            dates=("signal_date", "nunique"),
            avg_baseline_score=("e_baseline_selection_score", "mean"),
            positive_1m_rate=("e_label_1m_positive", "mean"),
        )
        .reset_index()
    )
    payload = {
        "status": "ok",
        "source_name": "e_series_etf_mart_v2",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d",
        "optimization_priority": "return_first_with_role_risk_controls",
        "rows": int(len(mart)),
        "tickers": int(mart["ticker"].nunique()),
        "signal_dates": int(mart["signal_date"].nunique()),
        "columns": int(len(mart.columns)),
        "standard_roles": STANDARD_ROLES,
        "role_summary": _records(role_summary),
        "mode_summary": _records(mode_summary),
        "taxonomy_rebuilt": bool(taxonomy_payload is not None),
        "outputs": {
            "mart_csv": str(mart_path),
            "current_sample_csv": str(sample_path),
            "taxonomy_csv": str(taxonomy_path),
            "json": str(json_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build E-series ETF AI mart v2.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--rebuild-taxonomy", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_e_series_mart_v2(str(args.asof), bool(args.rebuild_taxonomy)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
