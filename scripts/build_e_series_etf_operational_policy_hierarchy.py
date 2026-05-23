from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(r"D:\Quant")
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
REPORT_DIR = ROOT / r"reports\e_series_etf"

STRATEGY_MODEL_CODE = "E-ETF-V01"
STRATEGY_MODEL_NAME_KO = "ETF전용 E시리즈AI"
SLEEVE_MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"
PORTFOLIO_MODEL_CODE = "AI-E-ETF-PORTFOLIO-V01"


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _safe_float(value: Any, digits: int = 6) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), digits)
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
    use = df.head(limit) if limit is not None else df
    return [{key: _json_value(value) for key, value in row.items()} for row in use.to_dict("records")]


def _load_current(name: str) -> dict[str, Any]:
    path = ADMIN_CURRENT_DIR / name
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def _first(payload: dict[str, Any], key: str) -> dict[str, Any]:
    rows = payload.get(key) or []
    return rows[0] if rows else {}


def _summary_by_policy(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("summary") or payload.get("portfolio_summary") or []
    return {str(row.get("policy")): row for row in rows if row.get("policy")}


def _current_holdings_summary(stability: dict[str, Any]) -> pd.DataFrame:
    rows = stability.get("current_holdings") or []
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if frame.empty or "policy" not in frame.columns:
        return pd.DataFrame()
    frame["policy_weight"] = pd.to_numeric(frame.get("policy_weight"), errors="coerce").fillna(0.0)
    out = (
        frame.groupby(["policy", "candidate_type"], dropna=False)
        .agg(
            holdings=("ticker", "nunique"),
            weight_sum=("policy_weight", "sum"),
            roles=("e_series_role", lambda x: ",".join(sorted(set(str(v) for v in x.dropna())))),
        )
        .reset_index()
    )
    return out.sort_values(["candidate_type", "policy"])


def build_hierarchy(asof: str) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)

    sleeve = _load_current("e_series_etf_sleeve_selection_current.json")
    portfolio = _load_current("e_series_etf_sleeve_portfolio_current.json")
    mode_switch = _load_current("e_series_etf_mode_switch_policy_walk_forward_current.json")
    turnover = _load_current("e_series_etf_mode_switch_turnover_buffer_current.json")
    stability = _load_current("e_series_etf_mode_switch_stability_check_current.json")
    total_return = _load_current("e_series_etf_total_return_adjustment_current.json")
    issuer_distribution = _load_current("e_series_etf_issuer_distributions_current.json")
    hardening = _load_current("e_series_etf_operational_hardening_current.json")

    best_sleeve_policy = _first(portfolio, "best_ai_policy")
    best_buffer_policy = _first(turnover, "best_buffer_policy")
    stability_map = _summary_by_policy(stability)
    base_policy = stability_map.get("mode_switch_buffer_70_base", {})
    tight_policy = stability_map.get("mode_switch_buffer_70_tight", {})
    loose_policy = stability_map.get("mode_switch_buffer_70_loose", {})
    total_return_source = total_return.get("source_status") or {}
    adjustment_rows = sum(int(row.get("adjusted_rows") or 0) for row in total_return.get("summary") or [])
    issuer_rows = int(issuer_distribution.get("inserted_rows") or 0)
    if total_return_source.get("has_distribution_source") and adjustment_rows > 0:
        return_basis = "partial_total_return_issuer_provider_expanded"
    elif total_return_source.get("has_distribution_source"):
        return_basis = "distribution_source_ready"
    else:
        return_basis = "price_return_fallback"

    hierarchy = [
        {
            "level": 0,
            "layer": "return_basis",
            "policy_code": return_basis,
            "status": "active_input",
            "description_ko": "ETF forward return label의 기준 수익률",
            "decision_rule": "issuer/KRX/CSV 분배금 원천이 있으면 total return, 없으면 price return fallback",
            "evidence": {
                "has_distribution_source": total_return_source.get("has_distribution_source"),
                "issuer_distribution_rows": issuer_rows,
                "adjusted_rows": adjustment_rows,
                "date_quality": issuer_distribution.get("date_quality"),
                "adjustment_summary": total_return.get("summary"),
            },
        },
        {
            "level": 1,
            "layer": "sleeve_selection_ai",
            "policy_code": SLEEVE_MODEL_CODE,
            "status": "active_model",
            "description_ko": "역할별 ETF 후보 점수화 AI",
            "decision_rule": "role별 top3 risk-adjusted 1M label을 학습",
            "evidence": {
                "model_version": sleeve.get("model_version"),
                "auc": sleeve.get("auc"),
                "top_stats": sleeve.get("top_stats"),
            },
        },
        {
            "level": 2,
            "layer": "base_portfolio_policy",
            "policy_code": best_sleeve_policy.get("policy", "hybrid_b50_ai50_top3_role"),
            "status": "base_reference",
            "description_ko": "정상 국면에서 쓰는 기본 ETF 역할 포트폴리오",
            "decision_rule": "baseline 50% + AI 50% hybrid, role별 top3",
            "evidence": best_sleeve_policy,
        },
        {
            "level": 3,
            "layer": "mode_switch_reference",
            "policy_code": "mode_switch_stress_tail_asset",
            "status": "reference_overlay",
            "description_ko": "stress 국면에서 tail asset 정책으로 전환하는 참조 overlay",
            "decision_rule": "normal은 hybrid, stress는 tail asset",
            "evidence": {
                "best_policy": _first(mode_switch, "best_portfolio_policy"),
                "stress_dates": mode_switch.get("stress_dates"),
                "risk_off_dates": mode_switch.get("risk_off_dates"),
            },
        },
        {
            "level": 4,
            "layer": "execution_control",
            "policy_code": "mode_switch_buffer_70_base",
            "status": "primary_shadow_candidate",
            "description_ko": "현재 운영 관찰의 기준 후보",
            "decision_rule": "목표 turnover가 70% 미만이면 리밸런싱 생략",
            "evidence": {
                "turnover_buffer_best": best_buffer_policy,
                "stability": base_policy,
            },
        },
        {
            "level": 5,
            "layer": "stability_challenger",
            "policy_code": "mode_switch_buffer_70_tight",
            "status": "shadow_challenger",
            "description_ko": "더 보수적인 stress threshold 후보",
            "decision_rule": "base보다 전환 flip이 낮고 성과 훼손이 작으면 승격 검토",
            "evidence": tight_policy,
        },
        {
            "level": 6,
            "layer": "sensitivity_only",
            "policy_code": "mode_switch_buffer_70_loose",
            "status": "observation_only",
            "description_ko": "민감도 관찰용 후보",
            "decision_rule": "성과 비교에는 사용하되 운영 승격 후보는 아님",
            "evidence": loose_policy,
        },
        {
            "level": 7,
            "layer": "operational_hardening",
            "policy_code": "gate_role_label_hysteresis_risk_cap_shadow",
            "status": "shadow_hardening_candidate",
            "description_ko": "유동성/괴리율 gate, role별 label, hysteresis, portfolio risk cap 보강 후보",
            "decision_rule": "다음 업데이트 후 재현성 확인 전까지 운영 기본값은 대체하지 않음",
            "evidence": hardening.get("recommendation", {}),
        },
    ]

    holdings_summary = _current_holdings_summary(stability)
    governance = {
        "operation_phase": "shadow_tracking",
        "public_recommendation_allowed": False,
        "admin_display_allowed": True,
        "promotion_rule": [
            "최소 4~8주 shadow tracking 후 판단",
            "tight가 base 대비 single-month flip을 낮게 유지",
            "tight가 base 대비 worst 1M return을 악화시키지 않음",
            "turnover와 skipped periods가 과도하게 악화되지 않음",
            "분배금 원천 도입 후 total-return 기준에서도 결과 재확인",
            "operational hardening 후보는 다음 데이터 업데이트 후 재검증",
        ],
        "blockers": [
            "KODEX 분배금은 pilot 원천이며 TIGER/ACE/SOL 등 provider 확장 전까지는 partial total-return 기준",
            "ETF 전용 E-series는 기존 T-ETF와 별도 트랙",
            "QS/QM 코드는 Quant thread에서 직접 수정하지 않음",
        ],
    }

    token = _token(asof)
    json_path = REPORT_DIR / f"e_series_etf_operational_policy_hierarchy_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_operational_policy_hierarchy_{token}.md"
    holdings_summary_path = REPORT_DIR / f"e_series_etf_operational_policy_hierarchy_holdings_{token}.csv"
    admin_path = ADMIN_CURRENT_DIR / "e_series_etf_operational_policy_hierarchy_current.json"
    holdings_summary.to_csv(holdings_summary_path, index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok",
        "source_name": "e_series_etf_operational_policy_hierarchy",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "strategy_model_name_ko": STRATEGY_MODEL_NAME_KO,
        "sleeve_model_code": SLEEVE_MODEL_CODE,
        "portfolio_model_code": PORTFOLIO_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_primary_shadow_policy": "mode_switch_buffer_70_base",
        "active_shadow_challenger_policy": "mode_switch_buffer_70_tight",
        "return_basis": return_basis,
        "hierarchy": hierarchy,
        "governance": governance,
        "current_holdings_summary": _records(holdings_summary),
        "outputs": {
            "json": str(json_path),
            "markdown": str(md_path),
            "holdings_summary_csv": str(holdings_summary_path),
            "admin_current_json": str(admin_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    admin_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload)
    return payload


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# E-Series ETF Operational Policy Hierarchy",
        "",
        f"- 기준일: `{payload['as_of_date']}`",
        f"- 전략 모델: `{payload['strategy_model_code']}`",
        f"- 운영 단계: `{payload['governance']['operation_phase']}`",
        f"- primary shadow: `{payload['active_primary_shadow_policy']}`",
        f"- shadow challenger: `{payload['active_shadow_challenger_policy']}`",
        f"- return basis: `{payload['return_basis']}`",
        "",
        "## Hierarchy",
        "",
        "| level | layer | policy | status | decision rule |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for row in payload["hierarchy"]:
        lines.append(
            f"| {row['level']} | `{row['layer']}` | `{row['policy_code']}` | `{row['status']}` | {row['decision_rule']} |"
        )
    lines.extend(
        [
            "",
            "## 운영 원칙",
            "",
            "- 현재 E-series ETF는 public 추천 모델이 아니라 admin-only shadow 관찰 대상이다.",
            "- `mode_switch_buffer_70_base`를 기준 후보로 유지한다.",
            "- `mode_switch_buffer_70_tight`는 안정성 challenger로 병행 관찰한다.",
            "- `mode_switch_buffer_70_loose`는 민감도 관찰용으로만 둔다.",
            "- 분배금 원천이 확보되면 total-return 기준으로 재검증한다.",
            "",
            "## 승격 조건",
            "",
        ]
    )
    for item in payload["governance"]["promotion_rule"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 산출물", ""])
    for key, value in payload["outputs"].items():
        lines.append(f"- `{key}`: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build E-series ETF operational policy hierarchy.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    payload = build_hierarchy(str(args.asof))
    print(
        json.dumps(
            {
                "status": payload["status"],
                "as_of_date": payload["as_of_date"],
                "active_primary_shadow_policy": payload["active_primary_shadow_policy"],
                "active_shadow_challenger_policy": payload["active_shadow_challenger_policy"],
                "return_basis": payload["return_basis"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
