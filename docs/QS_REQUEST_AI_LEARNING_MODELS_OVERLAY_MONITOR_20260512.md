# QS 작업요청서: AI 학습 모델 페이지 Overlay Monitoring 표시

- 작성일: 2026-05-12
- 요청 주체: Quant thread
- 대상 thread: QuantService(QS)
- 관련 화면: admin `AI 학습 모델`
- 목적: AI 학습모델별 독립 성능뿐 아니라, 기존 전략모델에 overlay로 적용했을 때의 효과를 관찰

## 배경

현재 AI 학습모델은 크게 두 용도로 나뉩니다.

1. AI 모델 자체의 학습 성능 관찰
   - AUC
   - tag/state별 실제 성과
   - shadow tracking

2. 기존 전략모델에 overlay로 붙였을 때의 incremental lift 관찰
   - baseline 대비 평균 수익률 변화
   - baseline 대비 승률 변화
   - baseline 대비 MDD 변화

이번 요청은 `AI 학습 모델` 페이지에 2번 관점을 추가하기 위한 것입니다.

## 대상 AI 모델

우선 아래 주식 overlay AI 모델을 표시 대상으로 해 주세요.

| model_code | 한글명 | 역할 |
| --- | --- | --- |
| AI-DOWNSIDE-RISK-V01 | 하락위험예측AI | 하락위험 tag 기반 비중 축소/caution |
| AI-GROWTH-VALUATION-V01 | 주가수준평가AI | valuation state 기반 비중 tilt |
| AI-CANDIDATE-RANK-DELTA-V01 | 후보순위조정AI | 다음 리밸런싱 순위 변화 기반 비중/rank 조정 |

ETF 모델은 별도 트랙으로 아래 항목을 유지해 주세요.

| model_code | 한글명 | 역할 |
| --- | --- | --- |
| AI-ETF-SHADOW-PORTFOLIO-V01 | ETF전용포트폴리오AI | ETF role/template 기반 shadow portfolio |
| AI-ETF-ROLE-ALLOCATION-V01 | ETF역할배분AI | 시장국면별 ETF 역할 선택 |
| AI-ETF-ROLE-WEIGHT-TEMPLATE-V01 | ETF비중템플릿AI | ETF 역할 포트폴리오 비중 템플릿 선택 |

## Quant 산출물

QS에서 우선 참조할 current payload는 아래입니다.

- `D:\Quant\service_platform\web\admin_data\current\ai_learning_overlay_monitor_current.json`
- 기존 AI 모델 목록 payload: `D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json`

AI overlay 조합/정책맵 결과:

- `D:\Quant\reports\ai_overlay_backtest\AI_OVERLAY_COMBO_STRATEGY_BACKTEST_20260511.md`
- `D:\Quant\reports\ai_overlay_backtest\AI_OVERLAY_POLICY_MAP_BACKTEST_20260511.md`
- `D:\Quant\reports\ai_overlay_backtest\ai_overlay_policy_map_vs_baseline_by_model_20260511.csv`
- `D:\Quant\reports\ai_overlay_backtest\ai_overlay_policy_map_vs_baseline_by_family_20260511.csv`

개별 AI 백테스트 결과:

- `D:\Quant\reports\ai_overlay_backtest\DOWNSIDE_RISK_AI_WEEKLY_OVERLAY_BACKTEST_20260511.md`
- `D:\Quant\reports\ai_overlay_backtest\VALUATION_AI_WEEKLY_OVERLAY_BACKTEST_20260511.md`
- `D:\Quant\reports\ai_overlay_backtest\CANDIDATE_RANK_DELTA_AI_WEEKLY_OVERLAY_BACKTEST_20260511.md`

ETF AI 결과:

- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_ai_shadow_portfolio_20260511.md`
- `D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json`

## 화면 요구사항

AI 학습 모델 페이지에 아래 섹션을 추가해 주세요.

### 1. AI 모델별 역할 요약

각 모델 카드 또는 상세 영역에 아래 항목을 표시해 주세요.

- 모델명
- 한글명
- 역할
- 적용 대상
- 현재 상태: `shadow_observation`
- 운영 반영 여부: `not_applied_to_live_recommendation`

### 2. Overlay 효과 요약

AI 모델 단독 성능뿐 아니라 policy map 기준의 전체 효과를 표시해 주세요.

권장 표시:

| 구분 | baseline avg return | AI overlay avg return | return delta | baseline MDD | AI overlay MDD | MDD delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| I | 값 | 값 | 값 | 값 | 값 | 값 |
| S | 값 | 값 | 값 | 값 | 값 | 값 |
| T | 값 | 값 | 값 | 값 | 값 | 값 |
| USER | 값 | 값 | 값 | 값 | 값 | 값 |

### 3. 모델별 적용 정책

전략모델별로 어떤 AI overlay가 배정되었는지 표시해 주세요.

예:

- S2: 주가수준평가AI 중심
- S2_PIT_V01: 후보순위조정AI 중심
- S3: 3개 AI 조합
- S3_CORE2: 3개 AI 조합, risk cap 추가 검증 필요
- S3_ACCEL_V01: 하락위험예측AI 중심
- I-STOCK: 3개 AI 조합
- T-STOCK: 3개 AI 조합

### 4. Shadow tracking 시작일

아래 기준을 표시해 주세요.

- 기준 데이터: 2026-05-11 종가
- shadow tracking 시작: 2026-05-12
- 의미: 실제 추천 반영이 아니라 baseline 대비 AI overlay 성과를 병행 관찰

## 사용자 설명 문구

AI 학습 모델 페이지 상단 또는 도움말 영역에 아래 문구를 넣어 주세요.

> AI 학습모델은 현재 실제 추천을 직접 대체하지 않습니다. 기존 전략모델이 만든 후보에 AI overlay를 적용했을 때 baseline 대비 성과가 개선되는지 shadow tracking으로 관찰하는 단계입니다.

ETF 섹션에는 아래 문구를 넣어 주세요.

> ETF전용포트폴리오AI는 주식 전략모델 overlay와 별도 트랙입니다. ETF는 역할 포트폴리오와 시장국면별 비중 템플릿을 결합해 별도 shadow portfolio로 관찰합니다.

## N/A 처리

- 성과 측정 기간이 아직 도래하지 않은 1W/2W/1M 값은 `N/A`로 표시해 주세요.
- null 값을 `0%`로 표시하지 말아 주세요.
- 샘플 수가 부족한 모델은 `N/A` 또는 `관찰 부족`으로 표시해 주세요.

## 기대 결과

AI 학습 모델 페이지에서 사용자가 다음을 이해할 수 있어야 합니다.

- 각 AI 모델이 무엇을 판단하는 모델인지
- 현재 실제 추천에 반영된 것이 아니라 shadow 관찰 단계라는 점
- 어떤 전략모델에 어떤 AI overlay가 붙는지
- baseline 대비 AI overlay가 수익률과 리스크를 얼마나 개선했는지
- ETF AI는 주식 overlay와 다른 별도 트랙이라는 점
