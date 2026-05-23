from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_etf_role_allocation_ai_v01_experiment import (
    LABEL_CONFIGS,
    MARKET_FEATURES,
    MODEL_CODE as ROLE_MODEL_CODE,
    REPORT_DIR,
    ROLES,
    RULE_WEIGHTS,
    SELECTION_SCORE_MODES,
    add_labels,
    apply_regime_mapping,
    build_role_sleeves,
    _evaluate_policy as _evaluate_role_policy,
    _fit_role_model,
    _load_or_build_mart,
    _normalize_weights,
    _policy_summary as _role_policy_summary,
)
from scripts.run_etf_role_weight_template_ai_v01_experiment import (
    TEMPLATE_MODEL_CODE,
    TEMPLATES,
    build_template_panel,
    _evaluate_policy as _evaluate_template_policy,
    _fit as _fit_template_model,
    _summary as _template_policy_summary,
)

ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
DOC_PATH = ROOT / r"docs\AI_ETF_SHADOW_PORTFOLIO_20260511.md"
STRATEGY_FAMILY = "E"
STRATEGY_MODEL_CODE = "E-ETF-V01"
STRATEGY_MODEL_NAME_KO = "ETF전용 E시리즈AI"
PORTFOLIO_MODEL_CODE = "AI-E-ETF-PORTFOLIO-V01"
PORTFOLIO_MODEL_NAME_KO = "E시리즈 ETF포트폴리오AI"
LEGACY_PORTFOLIO_MODEL_CODE = "AI-ETF-SHADOW-PORTFOLIO-V01"
ROLE_MODEL_NAME_KO = "ETF역할배분AI"
TEMPLATE_MODEL_NAME_KO = "ETF비중템플릿AI"
ROLE_GATE = "no_watch_plus"
TEMPLATE_GATE = "aum_p20"
HOLDING_LIMIT = 60
FALLBACK_PRIMARY_E_SERIES_VARIANT = "hybrid_b50_ai50_top3_role"


def _safe_float(value: Any, digits: int = 6) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if df.empty:
        return []
    use = df.head(limit) if limit is not None else df
    return json.loads(use.replace({np.nan: None}).to_json(orient="records", force_ascii=False, date_format="iso"))


def _pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.2f}%"


def _template_by_id(template_id: str) -> dict[str, Any]:
    for template in TEMPLATES:
        if template["template_id"] == template_id:
            return template
    raise KeyError(template_id)


def _mode_default_template_id(mode: str) -> str:
    return {"risk_on": "ON_CORE_GROWTH", "neutral": "NEUTRAL_BALANCED", "risk_off": "OFF_DEFENSIVE"}.get(str(mode), "NEUTRAL_BALANCED")


def _split_items(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _split_names(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def _load_primary_e_series_sleeve(asof: str) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    token = asof.replace("-", "")
    payload_path = ROOT / r"service_platform\web\admin_data\current\e_series_etf_sleeve_portfolio_current.json"
    holdings_path = REPORT_DIR.parent / "e_series_etf" / f"e_series_etf_sleeve_portfolio_current_holdings_{token}.csv"
    payload: dict[str, Any] | None = None
    if payload_path.exists():
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not holdings_path.exists():
        return pd.DataFrame(), payload

    primary_variant = FALLBACK_PRIMARY_E_SERIES_VARIANT
    if payload:
        rows = payload.get("best_ai_policy") or []
        if rows and rows[0].get("policy"):
            primary_variant = str(rows[0]["policy"])

    holdings = pd.read_csv(holdings_path, dtype={"ticker": str}, low_memory=False)
    holdings["ticker"] = holdings["ticker"].astype(str).str.zfill(6)
    holdings = holdings[holdings["policy"].astype(str).eq(primary_variant)].copy()
    if holdings.empty:
        return pd.DataFrame(), payload
    out = pd.DataFrame(
        {
            "variant": holdings["policy"],
            "source": "e_series_sleeve_hybrid",
            "signal_date": holdings["signal_date"],
            "regime_mode": holdings["e_market_mode"],
            "role_key": holdings["e_series_role"],
            "role_weight": pd.to_numeric(holdings["e_mode_role_weight"], errors="coerce"),
            "ticker": holdings["ticker"],
            "name": holdings["name"],
            "holding_weight": pd.to_numeric(holdings["policy_weight"], errors="coerce"),
            "sleeve_selection_score": pd.to_numeric(holdings["sleeve_selection_prob"], errors="coerce"),
            "sleeve_premium_discount": pd.to_numeric(holdings.get("etf_metric_premium_discount"), errors="coerce"),
            "sleeve_aum_log": pd.to_numeric(holdings.get("etf_metric_aum_log"), errors="coerce"),
            "sleeve_daily_tracking_gap_pct": pd.to_numeric(holdings.get("etf_metric_daily_tracking_gap_pct"), errors="coerce"),
            "e_baseline_selection_score": pd.to_numeric(holdings.get("e_baseline_selection_score"), errors="coerce"),
            "e_hybrid_b50_ai50_score": pd.to_numeric(holdings.get("e_hybrid_b50_ai50_score"), errors="coerce"),
            "e_quality_score": pd.to_numeric(holdings.get("e_quality_score"), errors="coerce"),
            "e_momentum_score": pd.to_numeric(holdings.get("e_momentum_score"), errors="coerce"),
            "e_risk_control_score": pd.to_numeric(holdings.get("e_risk_control_score"), errors="coerce"),
        }
    )
    out["portfolio_weight_sum"] = out.groupby("variant")["holding_weight"].transform("sum")
    return out, payload


def _primary_e_series_summary_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    rows = payload.get("best_ai_policy") or []
    if not rows:
        return None
    row = dict(rows[0])
    return {
        "variant": row.get("policy", FALLBACK_PRIMARY_E_SERIES_VARIANT),
        "policy_label": row.get("policy_label"),
        "source_policy": "e_series_sleeve_hybrid",
        "observations": row.get("periods"),
        "avg_1m_ret": row.get("avg_1m_ret"),
        "median_1m_ret": row.get("median_1m_ret"),
        "win_rate": row.get("win_rate"),
        "avg_1m_mdd": row.get("avg_1m_mdd_proxy"),
        "avg_1m_risk_adj": row.get("avg_1m_risk_adj"),
        "worst_1m_ret": row.get("worst_1m_ret"),
        "compounded_validation_return": row.get("compounded_validation_return"),
        "baseline_avg_1m_ret": row.get("baseline_avg_1m_ret"),
        "avg_1m_ret_delta": row.get("avg_1m_ret_delta"),
        "baseline_win_rate": row.get("baseline_win_rate"),
        "win_rate_delta": row.get("win_rate_delta"),
        "baseline_avg_1m_risk_adj": row.get("baseline_avg_1m_risk_adj"),
        "avg_1m_risk_adj_delta": row.get("avg_1m_risk_adj_delta"),
        "baseline_compounded_validation_return": row.get("baseline_compounded_validation_return"),
        "compounded_validation_return_delta": row.get("compounded_validation_return_delta"),
    }


def _holdings_from_role_rows(
    role_rows: pd.DataFrame,
    role_weights: dict[str, float],
    variant: str,
    source: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    role_map = role_rows.set_index("role_key")
    for role in ROLES:
        role_weight = float(role_weights.get(role, 0.0) or 0.0)
        if role_weight <= 0 or role not in role_map.index:
            continue
        row = role_map.loc[role]
        tickers = _split_items(row.get("tickers"))
        names = _split_names(row.get("names"))
        if not tickers:
            continue
        holding_weight = role_weight / len(tickers)
        for i, ticker in enumerate(tickers):
            rows.append(
                {
                    "variant": variant,
                    "source": source,
                    "signal_date": row.get("signal_date"),
                    "regime_mode": row.get("regime_mode"),
                    "role_key": role,
                    "role_weight": round(role_weight, 8),
                    "ticker": str(ticker).zfill(6),
                    "name": names[i] if i < len(names) else None,
                    "holding_weight": round(holding_weight, 8),
                    "sleeve_selection_score": _safe_float(row.get("sleeve_selection_score")),
                    "sleeve_premium_discount": _safe_float(row.get("sleeve_premium_discount")),
                    "sleeve_aum_log": _safe_float(row.get("sleeve_aum_log")),
                    "sleeve_daily_tracking_gap_pct": _safe_float(row.get("sleeve_daily_tracking_gap_pct")),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["portfolio_weight_sum"] = out.groupby("variant")["holding_weight"].transform("sum")
    return out.sort_values(["variant", "role_key", "holding_weight", "ticker"], ascending=[True, True, False, True])


def _summarize_policy_returns(frame: pd.DataFrame, variant: str, source_policy: str) -> dict[str, Any]:
    if frame.empty:
        return {
            "variant": variant,
            "source_policy": source_policy,
            "observations": 0,
        }
    vals = pd.to_numeric(frame["fwd_ret_1m"], errors="coerce").dropna()
    risk = pd.to_numeric(frame["risk_adj_1m"], errors="coerce").dropna()
    mdd = pd.to_numeric(frame["path_mdd_1m"], errors="coerce").dropna()
    cumulative = None if vals.empty else float((1.0 + vals).prod() - 1.0)
    return {
        "variant": variant,
        "source_policy": source_policy,
        "observations": int(len(vals)),
        "avg_1m_ret": _safe_float(vals.mean() if not vals.empty else None),
        "median_1m_ret": _safe_float(vals.median() if not vals.empty else None),
        "win_rate": _safe_float((vals > 0).mean() if not vals.empty else None),
        "avg_1m_mdd": _safe_float(mdd.mean() if not mdd.empty else None),
        "avg_1m_risk_adj": _safe_float(risk.mean() if not risk.empty else None),
        "worst_1m_ret": _safe_float(vals.min() if not vals.empty else None),
        "compounded_validation_return": _safe_float(cumulative),
    }


def _summarize_template_policy_returns(frame: pd.DataFrame, variant: str, source_policy: str) -> dict[str, Any]:
    if frame.empty:
        return {"variant": variant, "source_policy": source_policy, "observations": 0}
    renamed = frame.rename(
        columns={
            "portfolio_fwd_ret_1m": "fwd_ret_1m",
            "portfolio_path_mdd_1m": "path_mdd_1m",
            "portfolio_risk_adj_1m": "risk_adj_1m",
        }
    )
    return _summarize_policy_returns(renamed, variant, source_policy)


def _train_role_and_score_current(
    mart: pd.DataFrame,
    train_end: str,
    valid_start: str,
    asof: str,
    top_n: int,
    regime_map: str,
    selection_mode: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    mapped = apply_regime_mapping(mart, regime_map)
    train_sleeves = add_labels(build_role_sleeves(mapped, top_n=top_n, selection_mode=selection_mode, quality_gate=ROLE_GATE))
    label_cfg = LABEL_CONFIGS["horizon_v2_top1"]
    label = label_cfg["column"]
    prob_col = label_cfg["prob_column"]
    score_col = label_cfg["score_column"]
    labeled = train_sleeves[train_sleeves[label].notna() & train_sleeves[score_col].notna()].copy()
    train = labeled[labeled["signal_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["signal_date"] >= pd.Timestamp(valid_start)) & (labeled["signal_date"] <= pd.Timestamp(asof))].copy()
    model = _fit_role_model(train, label)
    valid = valid.copy()
    valid[prob_col] = model.predict_proba(valid)[:, 1]
    auc = roc_auc_score(valid[label].astype(int), valid[prob_col])
    current_sleeves = build_role_sleeves(
        mapped,
        top_n=top_n,
        selection_mode=selection_mode,
        quality_gate=ROLE_GATE,
        require_forward=False,
    )
    current_date = current_sleeves["signal_date"].max()
    current = current_sleeves[current_sleeves["signal_date"].eq(current_date)].copy()
    current[prob_col] = model.predict_proba(current)[:, 1] if not current.empty else np.nan
    policy_returns = pd.concat(
        [
            _evaluate_role_policy(valid, policy, prob_column=prob_col, oracle_score_column=score_col, learned=None)
            for policy in ["ai_top1_role", "rule_mode_weight", "oracle_best_role"]
        ],
        ignore_index=True,
    )
    diagnostics = {
        "auc": _safe_float(auc),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "valid_dates": int(valid["signal_date"].nunique()),
        "current_signal_date": pd.Timestamp(current_date).strftime("%Y-%m-%d") if pd.notna(current_date) else None,
        "top_pick_label_rate": _safe_float(
            valid.sort_values(["signal_date", prob_col], ascending=[True, False]).groupby("signal_date").head(1)[label].mean()
        ),
    }
    return train_sleeves, current, policy_returns, diagnostics


def _train_template_and_score_current(
    mart: pd.DataFrame,
    train_end: str,
    valid_start: str,
    asof: str,
    top_n: int,
    regime_map: str,
    selection_mode: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    mapped = apply_regime_mapping(mart, regime_map)
    train_sleeves = add_labels(build_role_sleeves(mapped, top_n=top_n, selection_mode=selection_mode, quality_gate=TEMPLATE_GATE))
    panel = build_template_panel(train_sleeves)
    train = panel[panel["signal_date"] <= pd.Timestamp(train_end)].copy()
    valid = panel[(panel["signal_date"] >= pd.Timestamp(valid_start)) & (panel["signal_date"] <= pd.Timestamp(asof))].copy()
    model = _fit_template_model(train, "label_best_template")
    valid = valid.copy()
    valid["ai_prob_best_template"] = model.predict_proba(valid)[:, 1]
    auc = roc_auc_score(valid["label_best_template"], valid["ai_prob_best_template"])
    current_sleeves = add_labels(
        build_role_sleeves(
            mapped,
            top_n=top_n,
            selection_mode=selection_mode,
            quality_gate=TEMPLATE_GATE,
            require_forward=False,
        )
    )
    current_date = current_sleeves["signal_date"].max()
    current_sleeves = current_sleeves[current_sleeves["signal_date"].eq(current_date)].copy()
    current_panel = build_template_panel(current_sleeves)
    current_panel["ai_prob_best_template"] = model.predict_proba(current_panel)[:, 1] if not current_panel.empty else np.nan
    policies = pd.concat(
        [
            _evaluate_template_policy(valid, "ai_top1_template"),
            _evaluate_template_policy(valid, "mode_default_template"),
            _evaluate_template_policy(valid, "oracle_best_template"),
        ],
        ignore_index=True,
    )
    diagnostics = {
        "auc": _safe_float(auc),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "valid_dates": int(valid["signal_date"].nunique()),
        "current_signal_date": pd.Timestamp(current_date).strftime("%Y-%m-%d") if pd.notna(current_date) else None,
        "top_pick_hit_rate": _safe_float(
            valid.sort_values(["signal_date", "ai_prob_best_template"], ascending=[True, False])
            .groupby("signal_date")
            .head(1)["label_best_template"]
            .mean()
        ),
    }
    return train_sleeves, current_sleeves, current_panel, policies, diagnostics


def build_shadow_portfolio(
    asof: str,
    train_end: str,
    valid_start: str,
    top_n: int,
    regime_map: str,
    selection_mode: str,
    rebuild_mart: bool = False,
) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    mart = _load_or_build_mart(asof, rebuild_mart)

    role_sleeves, current_role, role_policy_returns, role_diag = _train_role_and_score_current(
        mart, train_end, valid_start, asof, top_n, regime_map, selection_mode
    )
    template_sleeves, current_template_sleeves, current_templates, template_policy_returns, template_diag = _train_template_and_score_current(
        mart, train_end, valid_start, asof, top_n, regime_map, selection_mode
    )

    role_prob_col = LABEL_CONFIGS["horizon_v2_top1"]["prob_column"]
    selected_role = current_role.sort_values(role_prob_col, ascending=False).head(1)
    selected_role_key = str(selected_role.iloc[0]["role_key"]) if not selected_role.empty else None
    role_weights = {selected_role_key: 1.0} if selected_role_key else {}
    role_holdings = _holdings_from_role_rows(current_role, role_weights, "role_ai_no_watch_plus_top1", "role_ai")

    selected_template = current_templates.sort_values("ai_prob_best_template", ascending=False).head(1)
    selected_template_id = str(selected_template.iloc[0]["template_id"]) if not selected_template.empty else "NEUTRAL_BALANCED"
    selected_template_spec = _template_by_id(selected_template_id)
    available_roles = set(current_template_sleeves["role_key"].astype(str))
    template_weights = _normalize_weights(selected_template_spec["weights"], available_roles)
    template_holdings = _holdings_from_role_rows(current_template_sleeves, template_weights, "template_ai_aum_p20_top1", "template_ai")

    mode = str(current_template_sleeves["regime_mode"].iloc[0]) if not current_template_sleeves.empty else "neutral"
    default_template_id = _mode_default_template_id(mode)
    default_weights = _normalize_weights(_template_by_id(default_template_id)["weights"], available_roles)
    default_holdings = _holdings_from_role_rows(current_template_sleeves, default_weights, "mode_default_aum_p20", "mode_default")

    primary_sleeve_holdings, primary_sleeve_payload = _load_primary_e_series_sleeve(asof)
    primary_sleeve_summary = _primary_e_series_summary_row(primary_sleeve_payload)
    holding_parts = [primary_sleeve_holdings, role_holdings, template_holdings, default_holdings]
    current_holdings = pd.concat([part for part in holding_parts if not part.empty], ignore_index=True)
    if not current_holdings.empty:
        current_holdings["as_of_date"] = asof
        current_holdings["strategy_family"] = STRATEGY_FAMILY
        current_holdings["strategy_model_code"] = STRATEGY_MODEL_CODE
        current_holdings["model_code"] = STRATEGY_MODEL_CODE
        current_holdings["ai_portfolio_model_code"] = PORTFOLIO_MODEL_CODE

    role_policy_summary = _role_policy_summary(role_policy_returns)
    template_policy_summary = _template_policy_summary(template_policy_returns)
    summary_rows = [
        row
        for row in [primary_sleeve_summary]
        if row is not None
    ]
    summary_rows.extend(
        [
            _summarize_policy_returns(
                role_policy_returns[role_policy_returns["policy"].eq("ai_top1_role")],
                "role_ai_no_watch_plus_top1",
                "ai_top1_role",
            ),
            _summarize_template_policy_returns(
                template_policy_returns[template_policy_returns["policy"].eq("ai_top1_template")],
                "template_ai_aum_p20_top1",
                "ai_top1_template",
            ),
            _summarize_template_policy_returns(
                template_policy_returns[template_policy_returns["policy"].eq("mode_default_template")],
                "mode_default_aum_p20",
                "mode_default_template",
            ),
        ]
    )
    backtest_summary = pd.DataFrame(summary_rows)
    primary_shadow_variant = (
        str(primary_sleeve_summary.get("variant"))
        if primary_sleeve_summary and primary_sleeve_summary.get("variant")
        else FALLBACK_PRIMARY_E_SERIES_VARIANT
    )
    primary_shadow_label = (
        str(primary_sleeve_summary.get("policy_label"))
        if primary_sleeve_summary and primary_sleeve_summary.get("policy_label")
        else "Latest best E-series hybrid Top3 per role"
    )

    current_role_path = REPORT_DIR / f"etf_ai_shadow_current_role_scores_{token}.csv"
    current_template_path = REPORT_DIR / f"etf_ai_shadow_current_template_scores_{token}.csv"
    holdings_path = REPORT_DIR / f"etf_ai_shadow_portfolio_holdings_{token}.csv"
    backtest_path = REPORT_DIR / f"etf_ai_shadow_portfolio_backtest_{token}.csv"
    report_json_path = REPORT_DIR / f"etf_ai_shadow_portfolio_{token}.json"
    report_md_path = REPORT_DIR / f"etf_ai_shadow_portfolio_{token}.md"
    current_json_path = ADMIN_CURRENT_DIR / "etf_ai_shadow_portfolio_current.json"

    current_role.to_csv(current_role_path, index=False, encoding="utf-8-sig")
    current_templates.to_csv(current_template_path, index=False, encoding="utf-8-sig")
    current_holdings.to_csv(holdings_path, index=False, encoding="utf-8-sig")
    backtest_summary.to_csv(backtest_path, index=False, encoding="utf-8-sig")

    payload = {
        "source_name": "etf_ai_shadow_portfolio_current",
        "schema_version": "1.1",
        "visibility": "admin_only",
        "strategy_family": STRATEGY_FAMILY,
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "strategy_model_name_ko": STRATEGY_MODEL_NAME_KO,
        "model_code": STRATEGY_MODEL_CODE,
        "model_name_ko": STRATEGY_MODEL_NAME_KO,
        "ai_portfolio_model_code": PORTFOLIO_MODEL_CODE,
        "ai_portfolio_model_name_ko": PORTFOLIO_MODEL_NAME_KO,
        "legacy_model_code": LEGACY_PORTFOLIO_MODEL_CODE,
        "model_role": "etf_e_series_ai_strategy",
        "status": "shadow_observation",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "timezone": "Asia/Seoul",
        "learning_architecture": {
            "design_principle": "E series is an ETF-only strategy model whose base design includes AI learning, not a post-hoc stock-style overlay.",
            "source_data_scope": "ETF-only market, liquidity, product, tracking-quality, role-sleeve, and QuantMarket context data.",
            "stages": [
                {
                    "stage": 1,
                    "code": "market_mode",
                    "name_ko": "ETF시장모드AI",
                    "output": "risk_on / neutral / risk_off probabilities",
                },
                {
                    "stage": 2,
                    "code": "role_allocation",
                    "name_ko": ROLE_MODEL_NAME_KO,
                    "output": "relative attractiveness by ETF role sleeve",
                },
                {
                    "stage": 3,
                    "code": "role_weight_template",
                    "name_ko": TEMPLATE_MODEL_NAME_KO,
                    "output": "role weight template selection",
                },
                {
                    "stage": 4,
                    "code": "portfolio_construction",
                    "name_ko": PORTFOLIO_MODEL_NAME_KO,
                    "output": "admin-only E-series ETF shadow portfolio",
                },
            ],
        },
        "component_models": [
            {
                "model_code": ROLE_MODEL_CODE,
                "e_series_model_code": "AI-E-ETF-ROLE-ALLOCATION-V01",
                "model_name_ko": ROLE_MODEL_NAME_KO,
                "role": "role_selection",
                "quality_gate": ROLE_GATE,
                "evaluation": role_diag,
            },
            {
                "model_code": TEMPLATE_MODEL_CODE,
                "e_series_model_code": "AI-E-ETF-ROLE-WEIGHT-TEMPLATE-V01",
                "model_name_ko": TEMPLATE_MODEL_NAME_KO,
                "role": "role_weight_template_selection",
                "quality_gate": TEMPLATE_GATE,
                "evaluation": template_diag,
            },
        ],
        "policy": {
            "operating_stage": "admin_only_shadow",
            "public_recommendation_use": "disabled",
            "primary_shadow_variant": primary_shadow_variant,
            "primary_shadow_policy_label": primary_shadow_label,
            "primary_shadow_source": "AI-E-ETF-SLEEVE-SELECTION-V01 + E-series baseline score",
            "role_gate": ROLE_GATE,
            "template_gate": TEMPLATE_GATE,
            "tail_risk_guard_candidates": ["tracking_gap_p90", "quality_combo"],
        },
        "configuration": {
            "top_n_per_role": top_n,
            "regime_map": regime_map,
            "selection_mode": selection_mode,
            "selection_mode_description": SELECTION_SCORE_MODES.get(selection_mode),
            "train_end": train_end,
            "valid_start": valid_start,
        },
        "current_decision": {
            "role_signal_date": role_diag["current_signal_date"],
            "template_signal_date": template_diag["current_signal_date"],
            "regime_mode": mode,
            "selected_role": selected_role_key,
            "selected_role_prob": _safe_float(selected_role.iloc[0][role_prob_col]) if not selected_role.empty else None,
            "selected_template": selected_template_id,
            "selected_template_prob": _safe_float(selected_template.iloc[0]["ai_prob_best_template"]) if not selected_template.empty else None,
            "mode_default_template": default_template_id,
        },
        "backtest_summary": _records(backtest_summary),
        "primary_sleeve_policy_summary": _records(pd.DataFrame([primary_sleeve_summary]).dropna(how="all"))
        if primary_sleeve_summary
        else [],
        "role_policy_summary": _records(role_policy_summary),
        "template_policy_summary": _records(template_policy_summary),
        "current_holdings": _records(current_holdings, HOLDING_LIMIT),
        "current_role_scores": _records(
            current_role.sort_values(role_prob_col, ascending=False)[
                [
                    "signal_date",
                    "regime_mode",
                    "role_key",
                    role_prob_col,
                    "sleeve_count",
                    "tickers",
                    "names",
                    "sleeve_premium_discount",
                    "sleeve_aum_log",
                    "sleeve_daily_tracking_gap_pct",
                ]
            ]
        ),
        "current_template_scores": _records(
            current_templates.sort_values("ai_prob_best_template", ascending=False)[
                [
                    "signal_date",
                    "regime_mode",
                    "template_id",
                    "preferred_mode",
                    "ai_prob_best_template",
                    *[f"w_{role}" for role in ROLES],
                ]
            ]
        ),
        "outputs": {
            "current_role_scores_csv": str(current_role_path),
            "current_template_scores_csv": str(current_template_path),
            "current_holdings_csv": str(holdings_path),
            "backtest_summary_csv": str(backtest_path),
            "report_json": str(report_json_path),
            "report_md": str(report_md_path),
            "admin_current_json": str(current_json_path),
            "doc": str(DOC_PATH),
        },
    }

    report_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    current_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report_md_path, payload, backtest_summary)
    _write_markdown(DOC_PATH, payload, backtest_summary)
    return payload


def _write_markdown(path: Path, payload: dict[str, Any], backtest: pd.DataFrame) -> None:
    current = payload["current_decision"]
    lines = [
        "# E Series ETF AI Shadow Portfolio",
        "",
        "## 목적",
        "",
        "`E-ETF-V01`을 ETF 전용 E series 전략모델로 정의하고, 기본 설계 단계부터 AI 학습 구조를 내장해 admin-only shadow portfolio로 관찰한다.",
        "",
        "## 구성",
        "",
        f"- strategy model: `{payload['strategy_model_code']}` ({payload['strategy_model_name_ko']})",
        f"- AI portfolio model: `{payload['ai_portfolio_model_code']}` ({payload['ai_portfolio_model_name_ko']})",
        f"- legacy alias: `{payload['legacy_model_code']}`",
        f"- role model: `{ROLE_MODEL_CODE}` ({ROLE_MODEL_NAME_KO}), quality gate `{ROLE_GATE}`",
        f"- template model: `{TEMPLATE_MODEL_CODE}` ({TEMPLATE_MODEL_NAME_KO}), quality gate `{TEMPLATE_GATE}`",
        f"- as-of: `{payload['as_of_date']}`",
        f"- role signal date: `{current['role_signal_date']}`",
        f"- template signal date: `{current['template_signal_date']}`",
        f"- regime mode: `{current['regime_mode']}`",
        f"- selected role: `{current['selected_role']}`",
        f"- selected template: `{current['selected_template']}`",
        f"- primary shadow variant: `{payload['policy']['primary_shadow_variant']}`",
        "",
        "## Backtest Summary",
        "",
        "| variant | observations | avg 1M ret | win rate | avg MDD | avg risk adj | worst 1M | compounded |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in backtest.to_dict("records"):
        lines.append(
            f"| `{row['variant']}` | {int(row.get('observations') or 0)} | {_pct(row.get('avg_1m_ret'))} | "
            f"{_pct(row.get('win_rate'))} | {_pct(row.get('avg_1m_mdd'))} | {_pct(row.get('avg_1m_risk_adj'))} | "
            f"{_pct(row.get('worst_1m_ret'))} | {_pct(row.get('compounded_validation_return'))} |"
        )
    lines.extend(
        [
            "",
            "## 운영 판단",
            "",
            "- 현재 단계는 admin-only shadow 관찰이다.",
            "- public 추천/배분 반영은 최소 4~8주 live shadow 성과를 본 뒤 판단한다.",
            "- `template_ai_aum_p20_top1`을 주 관찰 variant로 둔다.",
            "- `role_ai_no_watch_plus_top1`은 역할 판단 보조 지표로 관찰한다.",
            "",
            "## Outputs",
            "",
            f"- `{payload['outputs']['admin_current_json']}`",
            f"- `{payload['outputs']['current_holdings_csv']}`",
            f"- `{payload['outputs']['backtest_summary_csv']}`",
            f"- `{payload['outputs']['report_json']}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ETF AI shadow portfolio and admin payload.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--regime-map", default="score_diff")
    parser.add_argument("--selection-mode", default="risk_adjusted")
    parser.add_argument("--rebuild-mart", action="store_true")
    args = parser.parse_args()
    payload = build_shadow_portfolio(
        asof=args.asof,
        train_end=args.train_end,
        valid_start=args.valid_start,
        top_n=args.top_n,
        regime_map=args.regime_map,
        selection_mode=args.selection_mode,
        rebuild_mart=args.rebuild_mart,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "model_code": payload["model_code"],
                "as_of_date": payload["as_of_date"],
                "current_decision": payload["current_decision"],
                "backtest_summary": payload["backtest_summary"],
                "out": payload["outputs"]["admin_current_json"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
