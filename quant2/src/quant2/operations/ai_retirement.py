"""Permanent Quant 1.0 AI retirement; historical readers remain independent."""
from __future__ import annotations

import json
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "config/quant1_ai_retirement.json"
SCHEMA_VERSION = "quant1_ai_retirement_v1"
RETIRED_MODEL_IDS = frozenset({
    "AI-CANDIDATE-VALIDATION-V01", "AI-OVERLAY-V01", "AI-GROWTH-VALUATION-V01",
    "AI-DOWNSIDE-RISK-V01", "AI-CANDIDATE-RANK-DELTA-V01", "AI-THEME-PERSISTENCE-V01",
    "AI-MODEL-SELECTION-V01", "E-ETF-V01", "AI-E-ETF-PORTFOLIO-V01",
    "AI-ETF-SHADOW-PORTFOLIO-V01", "AI-ETF-ROLE-ALLOCATION-V01",
    "AI-E-ETF-ROLE-ALLOCATION-V01", "AI-ETF-ROLE-WEIGHT-TEMPLATE-V01",
    "AI-E-ETF-ROLE-WEIGHT-TEMPLATE-V01", "AI-E-ETF-SLEEVE-SELECTION-V01",
    "T-STOCK-V01", "T-ETF-V01",
})
RETIRED_OBJECT_PREFIXES = (
    "ai_learning_", "ai_shadow_", "valuation_ai_", "downside_risk_ai_",
    "candidate_rank_delta_ai_", "theme_persistence_ai_", "etf_ai_shadow_",
    "internal_models_ai_overlay_", "quantservice_tseries_discovery",
    "e_series_etf_sleeve_", "e_series_etf_mode_switch_",
    "e_series_etf_operational_", "e_series_etf_selection_policy_",
    "e_series_etf_tail_risk_",
)


class RetiredModelError(ValueError):
    """An obsolete model or current-output path was requested."""


def load() -> dict:
    """Missing, disabled or narrowed policy cannot silently revive an AI model."""
    body = json.loads(CONTRACT_PATH.read_bytes())
    ids = body.get("retired_model_ids")
    if (body.get("schema_version") != SCHEMA_VERSION or body.get("status") != "retired"
            or body.get("current_ai_outputs_allowed") is not False
            or body.get("historical_records_preserved") is not True
            or not isinstance(ids, list) or any(not isinstance(x, str) for x in ids)
            or len(ids) != len(set(ids)) or set(ids) != RETIRED_MODEL_IDS):
        raise ValueError("Invalid Quant 1.0 AI retirement contract")
    return body


def is_retired_model(code: str) -> bool:
    normalized = str(code).upper().replace("T_STOCK_V01", "T-STOCK-V01").replace(
        "T_ETF_V01", "T-ETF-V01"
    )
    return any(normalized == model or normalized.startswith(model + "-")
               or normalized.startswith(model + "_") for model in RETIRED_MODEL_IDS)


def require_model_active(code: str) -> None:
    if is_retired_model(code):
        load()
        raise RetiredModelError(f"Quant 1.0 AI retired: {code}; historical records preserved")


def is_retired_object(name: str) -> bool:
    basename = str(name).replace("\\", "/").rsplit("/", 1)[-1].lower()
    return basename.startswith(RETIRED_OBJECT_PREFIXES)


def require_current_object(name: str) -> None:
    if is_retired_object(name):
        load()
        raise RetiredModelError(f"Quant 1.0 AI current output retired: {name}")


def portfolio_lifecycle() -> dict:
    load()
    return {"schema_version": SCHEMA_VERSION, "status": "retired",
            "retired_model_ids": ["T-STOCK-V01", "T-ETF-V01"],
            "current_ai_outputs_allowed": False, "historical_records_preserved": True}
