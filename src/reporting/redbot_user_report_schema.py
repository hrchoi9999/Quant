from __future__ import annotations

from typing import Any

REQUIRED_TOP_LEVEL = [
    "header",
    "executive_summary",
    "market_diagnosis",
    "model_overview",
    "model_metadata",
    "model_portfolio",
    "model_rationale",
    "risk_guide",
    "recent_performance",
    "model_changes",
    "disclaimer",
    "compliance_metadata",
    "internal_metadata",
]

REQUIRED_SECTION_FIELDS = {
    "header": ["report_title", "generated_at", "user_model_name", "service_profile", "report_version"],
    "executive_summary": ["current_model_label", "market_view", "summary_basis", "risk_level"],
    "market_diagnosis": ["current_regime", "regime_summary", "reference_response"],
    "model_overview": ["model_name", "model_character", "model_profile_label", "core_role"],
    "model_metadata": ["model_display_name", "model_family_name", "model_public_type", "model_brief_type", "model_portfolio_type", "model_one_line_desc", "model_scope_desc", "model_profile_desc", "model_role_desc", "performance_subject_name", "performance_subject_type", "portfolio_generation_basis", "change_subject_name", "change_basis_desc", "change_reason_desc"],
    "risk_guide": ["risk_level", "expected_drawdown_note", "reference_usage_context", "reference_holding_period"],
    "recent_performance": ["headline_metrics", "period_metrics", "performance_subject_name", "performance_subject_type", "portfolio_generation_basis"],
    "model_changes": ["increased_assets", "decreased_assets", "change_subject_name", "change_basis", "change_reason_desc"],
    "disclaimer": ["investment_risk", "past_performance", "informational_purpose", "final_decision"],
    "compliance_metadata": [
        "content_class",
        "public_same_for_all_users",
        "non_personalized",
        "is_personalized_advice",
        "is_one_to_one_advisory",
        "is_actual_trade_instruction",
        "actual_investment_result",
        "backtest_result",
        "disclaimer_required",
        "data_basis",
        "model_version",
        "calculation_version",
        "asof_date",
        "rebalance_frequency",
        "fee_bps",
        "slippage_bps",
        "benchmark_name",
        "backtest_start_date",
        "backtest_end_date",
        "universe_definition",
        "data_source_summary",
    ],
    "internal_metadata": ["source_models", "generated_from_files", "user_visible_internal_models"],
}

PORTFOLIO_FIELDS = ["security_code", "asset_group", "display_name", "target_weight", "role_summary", "source_type"]


def validate_report_dict(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in report:
            errors.append(f"missing top-level section: {key}")
    if errors:
        return errors

    for section_name, fields in REQUIRED_SECTION_FIELDS.items():
        section = report.get(section_name)
        if not isinstance(section, dict):
            errors.append(f"section {section_name} must be an object")
            continue
        for field in fields:
            if field not in section:
                errors.append(f"section {section_name} missing field: {field}")

    portfolio = report.get("model_portfolio")
    if not isinstance(portfolio, list) or not portfolio:
        errors.append("model_portfolio must be a non-empty list")
    else:
        for idx, item in enumerate(portfolio):
            if not isinstance(item, dict):
                errors.append(f"model_portfolio[{idx}] must be an object")
                continue
            for field in PORTFOLIO_FIELDS:
                if field not in item:
                    errors.append(f"model_portfolio[{idx}] missing field: {field}")

    why_items = report.get("model_rationale")
    if not isinstance(why_items, list) or not why_items:
        errors.append("model_rationale must be a non-empty list")

    visible_flag = report.get("internal_metadata", {}).get("user_visible_internal_models")
    if visible_flag not in (False, True):
        errors.append("internal_metadata.user_visible_internal_models must be boolean")

    compliance = report.get("compliance_metadata", {})
    for field in ["is_personalized_advice", "is_one_to_one_advisory", "is_actual_trade_instruction"]:
        if compliance.get(field) not in (False, True):
            errors.append(f"compliance_metadata.{field} must be boolean")

    return errors
