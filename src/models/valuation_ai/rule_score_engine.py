# rule_score_engine.py ver 2026-05-06_001
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .config import STATE_THRESHOLDS


def _pct(series: pd.Series, ascending: bool = True) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    ranked = values.rank(pct=True, method="average", ascending=ascending)
    return ranked.fillna(0.5).clip(0, 1) * 100.0


def _state(score: float, risk_score: float) -> str:
    if score >= STATE_THRESHOLDS["UNDERVALUED"] and risk_score < 70:
        return "UNDERVALUED"
    if score >= STATE_THRESHOLDS["FAIR"]:
        return "FAIR"
    if score >= STATE_THRESHOLDS["OVERHEATED"]:
        return "OVERHEATED"
    return "AVOID"


def _reason_codes(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    if row.get("growth_quality_score", 0) >= 70:
        reasons.append("GROWTH_QUALITY_HIGH")
    if row.get("valuation_safety_score", 0) >= 70:
        reasons.append("PRICE_BURDEN_RELATIVELY_LOW")
    if row.get("valuation_safety_score", 0) < 35:
        reasons.append("PRICE_BURDEN_HIGH")
    if row.get("implied_growth_pressure", 0) >= 0.75:
        reasons.append("IMPLIED_GROWTH_PRESSURE_HIGH")
    if row.get("valuation_growth_gap", 0) <= -0.25:
        reasons.append("GROWTH_SUPPORTS_PRICE_LEVEL")
    if row.get("revision_momentum_score", 0) >= 65:
        reasons.append("GROWTH_ACCELERATION_POSITIVE")
    if row.get("downside_risk_score", 0) >= 70:
        reasons.append("DOWNSIDE_RISK_HIGH")
    if row.get("expected_return_score", 0) >= 70:
        reasons.append("EXPECTED_RETURN_MODEL_POSITIVE")
    if not reasons:
        reasons.append("MIXED_SIGNAL")
    return reasons


def build_rule_scores(features: pd.DataFrame, predicted_excess_return: pd.Series | None = None) -> pd.DataFrame:
    out = features.copy()
    if predicted_excess_return is None:
        predicted_excess_return = pd.Series(index=out.index, dtype=float)
    out["predicted_excess_return_12m"] = pd.to_numeric(predicted_excess_return, errors="coerce")

    scored_parts = []
    for _, frame in out.groupby("asof_date", sort=False):
        frame = frame.copy()
        growth_raw = (
            pd.to_numeric(frame.get("pit_growth_score"), errors="coerce").fillna(0)
            + pd.to_numeric(frame.get("annual_revenue_yoy"), errors="coerce").fillna(0) * 5
            + pd.to_numeric(frame.get("annual_op_income_yoy"), errors="coerce").fillna(0) * 5
            + pd.to_numeric(frame.get("q_revenue_yoy_delta_1q"), errors="coerce").fillna(0)
            + pd.to_numeric(frame.get("q_op_income_yoy_delta_1q"), errors="coerce").fillna(0)
        )
        frame["growth_quality_score"] = _pct(growth_raw, ascending=True)

        # Proxy for valuation burden until true PER/PBR/EV data is added.
        high_price_position = pd.to_numeric(frame.get("price_percentile_3y"), errors="coerce").fillna(0.5)
        momentum_heat = pd.to_numeric(frame.get("ret_12m"), errors="coerce").fillna(0)
        growth_support = frame["growth_quality_score"] / 100.0
        frame["current_valuation_percentile"] = (high_price_position.clip(0, 1) * 100.0).round(3)
        frame["implied_growth_pressure"] = (high_price_position + momentum_heat.clip(lower=0)).round(6)
        frame["valuation_growth_gap"] = (frame["implied_growth_pressure"] - growth_support).round(6)
        valuation_pressure = frame["valuation_growth_gap"]
        frame["valuation_safety_score"] = _pct(-valuation_pressure, ascending=True)

        accel = (
            pd.to_numeric(frame.get("price_acceleration"), errors="coerce").fillna(0)
            + pd.to_numeric(frame.get("q_revenue_yoy_delta_1q"), errors="coerce").fillna(0) * 0.02
            + pd.to_numeric(frame.get("q_op_income_yoy_delta_1q"), errors="coerce").fillna(0) * 0.02
        )
        frame["revision_momentum_score"] = _pct(accel, ascending=True)

        risk_raw = (
            pd.to_numeric(frame.get("vol_60d"), errors="coerce").fillna(0)
            + (-pd.to_numeric(frame.get("mdd_6m"), errors="coerce").fillna(0)).clip(lower=0)
            + pd.to_numeric(frame.get("distance_sma_140"), errors="coerce").fillna(0).clip(lower=0)
        )
        frame["downside_risk_score"] = _pct(risk_raw, ascending=True)
        frame["downside_safety_score"] = 100.0 - frame["downside_risk_score"]

        pred = pd.to_numeric(frame["predicted_excess_return_12m"], errors="coerce")
        if pred.notna().sum() >= 5:
            frame["expected_return_score"] = _pct(pred, ascending=True)
        else:
            frame["expected_return_score"] = _pct(pd.to_numeric(frame.get("excess_ret_3m_sector"), errors="coerce"), ascending=True)

        frame["valuation_ai_score"] = (
            0.35 * frame["expected_return_score"]
            + 0.25 * frame["valuation_safety_score"]
            + 0.20 * frame["growth_quality_score"]
            + 0.10 * frame["revision_momentum_score"]
            + 0.10 * frame["downside_safety_score"]
        ).clip(0, 100)
        frame["confidence_score"] = (
            0.45 * pd.to_numeric(frame.get("coverage_score"), errors="coerce").fillna(0.5).clip(0, 1)
            + 0.35 * (pd.to_numeric(frame.get("trading_value_20d"), errors="coerce").notna().astype(float))
            + 0.20 * (pred.notna().astype(float))
        ).clip(0, 1)
        frame["valuation_state"] = [
            _state(float(score), float(risk))
            for score, risk in zip(frame["valuation_ai_score"], frame["downside_risk_score"])
        ]
        frame["reason_codes"] = [json.dumps(_reason_codes(row), ensure_ascii=False) for _, row in frame.iterrows()]
        scored_parts.append(frame)
    return pd.concat(scored_parts, ignore_index=True).replace([np.inf, -np.inf], np.nan)


def state_from_score(score: float, downside_risk_score: float) -> str:
    return _state(score, downside_risk_score)
