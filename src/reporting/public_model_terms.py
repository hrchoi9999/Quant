from __future__ import annotations

from typing import Any

MODEL_FAMILY_NAME = "멀티애셋 데이터 기반 퀀트투자 모델"
MODEL_PUBLIC_TYPE = "공개 기준 기반 퀀트투자 모델"
MODEL_BRIEF_TYPE = "주간 브리핑용 퀀트투자 모델"
MODEL_PORTFOLIO_TYPE = "모델 포트폴리오를 산출하는 퀀트투자 모델"
MODEL_SCOPE_DESC = "개별 맞춤형이 아닌 동일 기준의 공개형 모델 정보입니다."
PERFORMANCE_SUBJECT_TYPE = "공개 기준 기반 퀀트투자 모델의 백테스트 성과"
PORTFOLIO_GENERATION_BASIS = "모델 포트폴리오를 산출하는 퀀트투자 모델 규칙 적용 결과"
CHANGE_BASIS_DESC = "주간 기준일 기준으로 모델 포트폴리오 산출 결과가 변경되었습니다."
CHANGE_REASON_DESC = "시장 상태와 공개 규칙 변화에 따라 퀀트투자 모델의 자산 비중이 조정되었습니다."

PUBLIC_MODEL_ONE_LINE_MAP = {
    "stable": "방어자산과 현금성 비중을 함께 활용하는 멀티애셋 데이터 기반 퀀트투자 모델",
    "balanced": "주식과 ETF를 함께 사용하는 공개 기준 기반 퀀트투자 모델",
    "growth": "추세와 모멘텀 데이터를 적극 반영하는 멀티애셋 데이터 기반 퀀트투자 모델",
    "auto": "시장 상태에 따라 자산 비중 구조를 조정하는 주간 브리핑용 퀀트투자 모델",
}

PUBLIC_MODEL_DESC_MAP = {
    "stable": "변동성 완화와 자산 방어를 우선하는 모델 포트폴리오를 산출하는 퀀트투자 모델",
    "balanced": "수익성과 안정성의 균형을 목표로 모델 포트폴리오를 산출하는 퀀트투자 모델",
    "growth": "성장 지향 모델 포트폴리오를 산출하는 퀀트투자 모델",
    "auto": "시장 국면 변화에 따라 모델 포트폴리오를 산출하는 퀀트투자 모델",
}

QUANT_MODEL_TERM_MAP = {
    "stable": {
        "model_display_name": "안정형 퀀트투자 모델",
        "model_profile_desc": "방어자산과 현금성 비중을 함께 활용하는 구조를 참고하려는 이용자",
        "model_role_desc": "변동성 완화와 자산 방어를 우선하는 모델 포트폴리오를 산출합니다.",
    },
    "balanced": {
        "model_display_name": "균형형 퀀트투자 모델",
        "model_profile_desc": "주식과 ETF를 함께 활용한 균형 구성을 참고하려는 이용자",
        "model_role_desc": "수익성과 안정성의 균형을 목표로 모델 포트폴리오를 산출합니다.",
    },
    "growth": {
        "model_display_name": "성장형 퀀트투자 모델",
        "model_profile_desc": "성장 지향 자산 구성과 추세 민감도를 참고하려는 이용자",
        "model_role_desc": "추세와 모멘텀을 적극 반영해 성장 지향 모델 포트폴리오를 산출합니다.",
    },
    "auto": {
        "model_display_name": "자동전환형 퀀트투자 모델",
        "model_profile_desc": "시장 상태 변화에 따라 조정되는 공개 모델 구성을 참고하려는 이용자",
        "model_role_desc": "시장 국면 변화에 따라 자산 비중 구조를 조정하는 모델 포트폴리오를 산출합니다.",
    },
}


def build_public_model_metadata(service_profile: str) -> dict[str, Any]:
    profile_meta = QUANT_MODEL_TERM_MAP[service_profile]
    return {
        "model_display_name": profile_meta["model_display_name"],
        "model_family_name": MODEL_FAMILY_NAME,
        "model_public_type": MODEL_PUBLIC_TYPE,
        "model_brief_type": MODEL_BRIEF_TYPE,
        "model_portfolio_type": MODEL_PORTFOLIO_TYPE,
        "model_one_line_desc": PUBLIC_MODEL_ONE_LINE_MAP[service_profile],
        "model_scope_desc": MODEL_SCOPE_DESC,
        "model_profile_desc": profile_meta["model_profile_desc"],
        "model_role_desc": profile_meta["model_role_desc"],
        "performance_subject_name": profile_meta["model_display_name"],
        "performance_subject_type": PERFORMANCE_SUBJECT_TYPE,
        "portfolio_generation_basis": PORTFOLIO_GENERATION_BASIS,
        "change_subject_name": profile_meta["model_display_name"],
        "change_basis_desc": CHANGE_BASIS_DESC,
        "change_reason_desc": CHANGE_REASON_DESC,
    }
