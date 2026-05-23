from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Quant")
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
OPERATION_TIERS_PATH = ROOT / r"config\ai_model_operational_tiers.json"


MODEL_DISPLAY_METADATA: dict[str, dict[str, Any]] = {
    "AI-CANDIDATE-VALIDATION-V01": {
        "short_name": "퀀트후보검증AI",
        "plain_description": "전략모델이 뽑은 후보 종목이 실제로 유지/성과를 낼 가능성이 있는지 검증하는 shadow AI입니다.",
        "purpose": "S/T/I/C 및 사용자 모델 후보의 품질을 보조 검증한다.",
        "expected_effect": "후보 편입/유지 판단의 실패율을 낮추고 최종 포트폴리오 수익률 개선 후보를 찾는다.",
        "primary_metrics": ["top30_avg_1m_return", "top30_win_rate", "live_shadow_return", "model_specific_tag"],
        "display_note": "모델별 confirm/risk/review tag를 보여주되, 실제 추천 적용이 아니라 shadow 관찰임을 표시한다.",
    },
    "AI-GROWTH-VALUATION-V01": {
        "short_name": "주가수준평가AI",
        "plain_description": "성장성, 가격 위치, 모멘텀, 리스크를 함께 보고 현재 주가수준이 매력적인지 평가하는 AI입니다.",
        "purpose": "후보 종목의 가격 부담 또는 상대 매력도를 판단한다.",
        "expected_effect": "고평가 후보의 비중을 낮추고 기대수익률이 높은 후보를 우선 관찰한다.",
        "primary_metrics": ["Rank IC", "TopN return", "TopN excess return", "shadow horizon return"],
        "display_note": "champion/challenger/risk overlay를 분리해서 표시한다.",
    },
    "AI-DOWNSIDE-RISK-V01": {
        "short_name": "하락위험예측AI",
        "plain_description": "후보 종목이 다음 1개월에 시장 대비 크게 부진하거나 큰 낙폭을 보일 위험을 예측하는 AI입니다.",
        "purpose": "매수 후보의 위험 경고와 보유 후보의 주의 tag를 제공한다.",
        "expected_effect": "큰 손실 가능성이 높은 후보를 줄여 누적수익률과 MDD를 개선한다.",
        "primary_metrics": ["auc", "risk_tag return", "risk_exit_watch hit", "MDD avoidance"],
        "display_note": "risk_exit_watch, risk_caution, risk_watch, risk_clear를 색상 tag로 구분한다.",
    },
    "AI-CANDIDATE-RANK-DELTA-V01": {
        "short_name": "후보순위조정AI",
        "plain_description": "다음 리밸런싱에서 후보가 편출될지, 잔류 후보의 순위가 올라갈지/내려갈지 예측하는 AI입니다.",
        "purpose": "기존 전략모델 후보의 순위 조정과 편출 위험 판단을 보조한다.",
        "expected_effect": "전략모델 baseline 대비 더 높은 수익률을 기대할 수 있는 후보 재정렬 정책을 찾는다.",
        "primary_metrics": ["top30_avg_1m_return", "drop_rate", "rank_delta_score", "policy_map return"],
        "display_note": "drop 예측과 retained rank-change 예측은 별도 섹션으로 보여준다.",
    },
    "AI-THEME-PERSISTENCE-V01": {
        "short_name": "테마지속성AI",
        "plain_description": "현재 강한 테마가 앞으로도 유지될지, 약화될지 판단하는 테마 단위 AI입니다.",
        "purpose": "테마/섹터 후보의 지속성, 회전, 약화 위험을 평가한다.",
        "expected_effect": "강한 테마는 유지하고 약화 테마 노출은 줄여 테마형 후보의 수익률을 개선한다.",
        "primary_metrics": ["theme_continue_auc", "theme_fade_auc", "theme_persistence_score", "tag return"],
        "display_note": "종목이 아니라 테마 bucket 기준 모델임을 명확히 표시한다.",
    },
    "E-ETF-V01": {
        "short_name": "ETF전용 E시리즈AI",
        "plain_description": "ETF 전용 데이터와 시장국면을 이용해 역할별 ETF sleeve와 최종 shadow 포트폴리오를 구성하는 AI 트랙입니다.",
        "purpose": "ETF를 주식과 분리된 별도 전략모델로 운영하고 시장국면별 포트폴리오 역할 배분을 검증한다.",
        "expected_effect": "ETF 포트폴리오의 총수익률, 시장 대응력, 손실 방어력을 개선한다.",
        "primary_metrics": ["avg_1m_ret", "compounded_validation_return", "net_return", "turnover", "risk_cap effect"],
        "display_note": "E-series는 ETF 전용 별도 트랙이며 주식용 S/T/I/C AI overlay와 분리해서 보여준다.",
    },
}

FIELD_DISPLAY_GUIDE = {
    "as_of_date": "산출 기준일입니다.",
    "status": "현재 payload 또는 모델 관찰 상태입니다. shadow_observation은 운영 반영 전 관찰 상태입니다.",
    "auc": "분류 정확도 보조지표입니다. 단독 승격 기준이 아니며 수익률 지표를 우선합니다.",
    "top30_avg_1m_return": "AI가 높게 평가한 상위 후보의 1개월 평균 수익률입니다.",
    "avg_1m_ret": "해당 정책 또는 포트폴리오의 1개월 평균 수익률입니다.",
    "compounded_validation_return": "검증 구간 누적 복리 수익률입니다.",
    "win_rate": "평가 기간 중 수익이 플러스인 비율입니다.",
    "mdd": "최대 낙폭 또는 낙폭 proxy입니다.",
    "risk_tag": "하락위험예측AI가 부여한 위험 경고 tag입니다.",
    "null": "값이 없거나 아직 성과 관찰 기간이 도래하지 않은 경우 0%가 아니라 N/A로 표시합니다.",
}

PAGE_DISPLAY_CONTRACT = {
    "target_pages": [
        {
            "page": "AI 학습 모델",
            "purpose": "AI 학습 모델별 역할, 상태, shadow 성과, 주요 payload 링크를 보여준다.",
            "primary_payload": "ai_learning_models_current.json",
        },
        {
            "page": "내부용 모델",
            "purpose": "전략모델별 baseline 대비 AI overlay shadow 정책의 성과를 보여준다.",
            "primary_payload": "internal_models_ai_overlay_shadow_current.json",
        },
        {
            "page": "ETF/E-series 관찰",
            "purpose": "ETF 전용 E-series AI, sleeve, mode switch, operational hardening 상태를 보여준다.",
            "primary_payload": "etf_ai_shadow_portfolio_current.json",
        },
    ],
    "display_rules": [
        "모든 null, NaN, unavailable 값은 0%가 아니라 N/A로 표시한다.",
        "AUC보다 수익률 지표를 우선 배치한다.",
        "shadow_observation 또는 admin_only 상태는 실제 추천 반영 전 관찰 상태로 표시한다.",
        "ETF/E-series는 주식용 AI overlay와 별도 트랙으로 표시한다.",
        "기준일(as_of_date)과 성과일이 같아 아직 1W/2W/1M 성과가 없으면 N/A가 정상이다.",
    ],
    "priority_metrics": [
        "avg_1m_ret",
        "top30_avg_1m_return",
        "compounded_validation_return",
        "excess_return",
        "win_rate",
        "mdd/worst_return",
        "auc",
    ],
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _operation_tiers() -> dict[str, Any]:
    return _read_json(OPERATION_TIERS_PATH)


def _model_payload(name: str, path: Path, exists: bool) -> dict[str, Any]:
    return {"name": name, "path": str(path), "available": exists}


def _candidate_validation() -> dict[str, Any]:
    path = ADMIN_CURRENT_DIR / "ai_shadow_observation.json"
    payload = _read_json(path)
    live_summary = payload.get("live_summary") or {}
    return {
        "model_code": payload.get("model_code") or "AI-CANDIDATE-VALIDATION-V01",
        "model_name_ko": payload.get("model_name_ko") or "퀀트후보검증AI",
        "model_role": "candidate_validation_shadow",
        "status": live_summary.get("status") or ("available" if payload else "missing"),
        "as_of_date": payload.get("as_of_date"),
        "summary": {
            "trained_models": len(((payload.get("model_specific_training") or {}).get("trained_models") or [])),
            "fallback_models": len(((payload.get("model_specific_training") or {}).get("fallback_models") or [])),
            "horizon_status": live_summary.get("horizon_status") or [],
        },
        "payloads": [_model_payload("ai_shadow_observation", path, bool(payload))],
    }


def _valuation_ai() -> dict[str, Any]:
    current_path = ADMIN_CURRENT_DIR / "valuation_ai_challenger_current.json"
    perf_path = ADMIN_CURRENT_DIR / "valuation_ai_challenger_shadow_performance.json"
    monitor_path = ADMIN_CURRENT_DIR / "valuation_ai_shadow_monitor.json"
    current = _read_json(current_path)
    perf = _read_json(perf_path)
    monitor = _read_json(monitor_path)
    candidates = current.get("candidates") or []
    return {
        "model_code": current.get("model_code") or perf.get("model_code") or monitor.get("model_code") or "AI-GROWTH-VALUATION-V01",
        "model_name_ko": current.get("model_name_ko") or perf.get("model_name_ko") or monitor.get("model_name_ko") or "주가수준평가AI",
        "model_role": "valuation_reference_challenger_shadow",
        "status": "available" if current else "missing",
        "as_of_date": current.get("as_of_date") or perf.get("source_as_of_date"),
        "performance_asof_date": perf.get("performance_asof_date"),
        "summary": {
            "candidate_count": len(candidates),
            "monitor_status": monitor.get("status"),
            "horizons": perf.get("horizons") or [],
        },
        "payloads": [
            _model_payload("valuation_ai_challenger_current", current_path, bool(current)),
            _model_payload("valuation_ai_challenger_shadow_performance", perf_path, bool(perf)),
            _model_payload("valuation_ai_shadow_monitor", monitor_path, bool(monitor)),
        ],
    }


def _downside_risk_ai() -> dict[str, Any]:
    current_path = ADMIN_CURRENT_DIR / "downside_risk_ai_current.json"
    tracker_path = ADMIN_CURRENT_DIR / "downside_risk_ai_shadow_tracker.json"
    current = _read_json(current_path)
    tracker = _read_json(tracker_path)
    evaluation = current.get("evaluation") or {}
    return {
        "model_code": current.get("model_code") or tracker.get("model_code") or "AI-DOWNSIDE-RISK-V01",
        "model_name_ko": current.get("model_name_ko") or tracker.get("model_name_ko") or "하락위험예측AI",
        "model_role": "downside_risk_overlay_shadow",
        "status": "available" if current else "missing",
        "as_of_date": current.get("as_of_date"),
        "performance_asof_date": tracker.get("performance_asof_date"),
        "summary": {
            "auc": evaluation.get("auc"),
            "train_rows": evaluation.get("train_rows"),
            "valid_rows": evaluation.get("valid_rows"),
            "tag_counts": current.get("tag_counts") or [],
            "tracker_roles": tracker.get("tracker_roles") or [],
            "horizons": tracker.get("horizons") or [],
        },
        "payloads": [
            _model_payload("downside_risk_ai_current", current_path, bool(current)),
            _model_payload("downside_risk_ai_shadow_tracker", tracker_path, bool(tracker)),
        ],
    }


def _candidate_rank_delta_ai() -> dict[str, Any]:
    current_path = ADMIN_CURRENT_DIR / "candidate_rank_delta_ai_current.json"
    current = _read_json(current_path)
    evaluation = current.get("evaluation") or []
    return {
        "model_code": current.get("model_code") or "AI-CANDIDATE-RANK-DELTA-V01",
        "model_name_ko": current.get("model_name_ko") or "후보순위조정AI",
        "model_role": "candidate_rank_delta_shadow",
        "status": "available" if current else "missing",
        "as_of_date": current.get("as_of_date"),
        "summary": {
            "model_structure": current.get("model_structure"),
            "evaluation": evaluation,
            "decision_counts": current.get("decision_counts") or [],
            "target": current.get("target") or {},
            "thresholds": current.get("thresholds") or {},
            "top_drop_count": len(current.get("top_drop_candidates") or []),
            "top_upgrade_count": len(current.get("top_upgrade_candidates") or []),
            "top_downgrade_count": len(current.get("top_downgrade_candidates") or []),
        },
        "payloads": [_model_payload("candidate_rank_delta_ai_current", current_path, bool(current))],
    }


def _theme_persistence_ai() -> dict[str, Any]:
    current_path = ADMIN_CURRENT_DIR / "theme_persistence_ai_current.json"
    current = _read_json(current_path)
    return {
        "model_code": current.get("model_code") or "AI-THEME-PERSISTENCE-V01",
        "model_name_ko": current.get("model_name_ko") or "테마지속성AI",
        "model_role": "theme_persistence_shadow",
        "status": "available" if current else "missing",
        "as_of_date": current.get("as_of_date"),
        "summary": {
            "evaluation": current.get("evaluation") or [],
            "tag_counts": current.get("tag_counts") or [],
            "target": current.get("target") or {},
            "thresholds": current.get("thresholds") or {},
            "top_persistent_count": len(current.get("top_persistent_themes") or []),
            "top_fade_risk_count": len(current.get("top_fade_risk_themes") or []),
        },
        "payloads": [_model_payload("theme_persistence_ai_current", current_path, bool(current))],
    }


def _etf_ai_shadow_portfolio() -> dict[str, Any]:
    current_path = ADMIN_CURRENT_DIR / "etf_ai_shadow_portfolio_current.json"
    e_series_paths = [
        ADMIN_CURRENT_DIR / "e_series_etf_sleeve_selection_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_sleeve_portfolio_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_selection_policy_walk_forward_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_tail_risk_policy_walk_forward_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_policy_walk_forward_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_holdings_compare_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_cost_adjusted_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_turnover_buffer_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_mode_switch_stability_check_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_operational_hardening_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_operational_policy_hierarchy_current.json",
        ADMIN_CURRENT_DIR / "e_series_etf_total_return_adjustment_current.json",
    ]
    current = _read_json(current_path)
    component_models = current.get("component_models") or []
    backtest = current.get("backtest_summary") or []
    decision = current.get("current_decision") or {}
    return {
        "model_code": current.get("model_code") or "AI-ETF-SHADOW-PORTFOLIO-V01",
        "model_name_ko": current.get("model_name_ko") or "ETF전용포트폴리오AI",
        "model_role": "etf_shadow_portfolio",
        "status": current.get("status") or ("available" if current else "missing"),
        "as_of_date": current.get("as_of_date"),
        "summary": {
            "component_models": component_models,
            "current_decision": decision,
            "primary_shadow_variant": ((current.get("policy") or {}).get("primary_shadow_variant")),
            "backtest_summary": backtest,
            "current_holding_count": len(current.get("current_holdings") or []),
        },
        "payloads": [
            _model_payload("etf_ai_shadow_portfolio_current", current_path, bool(current)),
            *[
                _model_payload(path.stem, path, path.exists())
                for path in e_series_paths
            ],
        ],
    }


def build_payload(asof: str | None = None) -> dict[str, Any]:
    operation_tiers = _operation_tiers()
    models = [
        _candidate_validation(),
        _valuation_ai(),
        _downside_risk_ai(),
        _candidate_rank_delta_ai(),
        _theme_persistence_ai(),
        _etf_ai_shadow_portfolio(),
    ]
    dates = [m.get("as_of_date") for m in models if m.get("as_of_date")]
    payload = {
        "source_name": "ai_learning_models_current",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "as_of_date": asof or (max(dates) if dates else None),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "description": "QS admin AI 학습 모델 페이지용 통합 payload. 개별 모델 payload의 위치와 핵심 관찰 지표를 제공한다.",
        "web_display_metadata": MODEL_DISPLAY_METADATA,
        "field_display_guide": FIELD_DISPLAY_GUIDE,
        "page_display_contract": PAGE_DISPLAY_CONTRACT,
        "operation_tiers": operation_tiers,
        "models": models,
        "policy": {
            "default_visibility": "admin_only",
            "public_recommendation_use": "disabled_until_live_shadow_validation",
            "new_ai_model_rule": "새 AI 학습 모델은 개별 current payload와 이 통합 payload에 함께 등록한다.",
            "optimization_priority": "return_first",
            "promotion_rule": "AUC/IC 개선만으로 승격하지 않고 baseline 대비 수익률 개선이 확인될 때만 운영 후보로 검토한다.",
        },
    }
    for model in payload["models"]:
        metadata = MODEL_DISPLAY_METADATA.get(model["model_code"], {})
        if metadata:
            model["display_metadata"] = metadata
        tier = (operation_tiers.get("models") or {}).get(model["model_code"])
        if tier:
            model["operation_tier"] = tier
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build consolidated admin payload for AI learning models.")
    parser.add_argument("--asof")
    parser.add_argument("--out", default=str(ADMIN_CURRENT_DIR / "ai_learning_models_current.json"))
    args = parser.parse_args()
    payload = build_payload(args.asof)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "out": str(out), "model_count": len(payload["models"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
