# QS 작업요청서: AI 학습 모델 / E-series Shadow 웹 반영

- 요청일: 2026-05-14
- 요청 시스템: Quant
- 대상 시스템: QuantService(QS)
- 작업 범위: QS admin 화면 표시 개선
- 원칙: Quant thread는 QS 코드를 직접 수정하지 않고, QS가 가져갈 current payload와 표시 가이드를 제공한다.

## 1. 작업 목적

QS admin 화면에서 AI 학습 모델과 E-series ETF shadow 관찰 내용을 사용자가 이해할 수 있게 표시해 주세요.

현재 사용자는 각 AI 모델이 무엇을 의미하는지, 어떤 지표를 우선 봐야 하는지 알기 어렵습니다.  
이번 작업은 아래 내용을 화면에 반영하는 것이 목적입니다.

- 각 AI 학습 모델의 역할/목적/기대효과 표시
- shadow tracking 상태와 실제 운영 미반영 상태 명확화
- 전략모델별 AI overlay 효과 확인
- E-series ETF 전용 AI 트랙을 주식 AI overlay와 분리 표시
- null 또는 아직 관찰기간 미도래 값은 `0%`가 아니라 `N/A`로 표시
- AUC보다 수익률 관련 지표를 우선 표시

## 2. 핵심 데이터 경로

QS는 아래 Quant current payload를 읽으면 됩니다.

### 2-1. AI 학습 모델 페이지

Primary:

`D:\Quant\service_platform\web\admin_data\current\ai_learning_models_current.json`

이 파일에 이번에 설명용 metadata를 보강했습니다.

주요 추가 필드:

- `web_display_metadata`
- `field_display_guide`
- `page_display_contract`
- `models[].display_metadata`
- `models[].payloads`
- `policy.optimization_priority`
- `policy.promotion_rule`

### 2-2. 내부용 모델 페이지: 전략모델별 AI overlay shadow

Primary:

`D:\Quant\service_platform\web\admin_data\current\internal_models_ai_overlay_shadow_current.json`

보조:

`D:\Quant\service_platform\web\admin_data\current\ai_learning_overlay_monitor_current.json`

표시 목적:

- 전략모델별 baseline vs AI overlay shadow 성과 비교
- model별 적용 policy map
- family별 성과 요약
- AI overlay가 실제 운영 반영 전 shadow 상태임을 표시

### 2-3. ETF/E-series 관찰 페이지 또는 AI 학습 모델 내 ETF 섹션

Primary:

`D:\Quant\service_platform\web\admin_data\current\etf_ai_shadow_portfolio_current.json`

E-series 상세 current payload:

- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_sleeve_selection_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_sleeve_portfolio_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_selection_policy_walk_forward_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_tail_risk_policy_walk_forward_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_mode_switch_policy_walk_forward_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_mode_switch_holdings_compare_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_mode_switch_cost_adjusted_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_mode_switch_turnover_buffer_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_mode_switch_stability_check_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_operational_hardening_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_operational_policy_hierarchy_current.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_total_return_adjustment_current.json`

## 3. AI 학습 모델별 표시 설명

`ai_learning_models_current.json`의 `web_display_metadata` 또는 `models[].display_metadata`를 우선 사용해 주세요.

표시 대상 모델:

| model_code | 한글명 | 화면 설명 |
|---|---|---|
| AI-CANDIDATE-VALIDATION-V01 | 퀀트후보검증AI | 전략모델이 뽑은 후보 종목이 실제로 유지/성과를 낼 가능성이 있는지 검증하는 shadow AI |
| AI-GROWTH-VALUATION-V01 | 주가수준평가AI | 성장성, 가격 위치, 모멘텀, 리스크를 함께 보고 현재 주가수준이 매력적인지 평가하는 AI |
| AI-DOWNSIDE-RISK-V01 | 하락위험예측AI | 다음 1개월에 시장 대비 크게 부진하거나 큰 낙폭을 보일 위험을 예측하는 AI |
| AI-CANDIDATE-RANK-DELTA-V01 | 후보순위조정AI | 다음 리밸런싱에서 편출/승격/강등 가능성을 예측하는 AI |
| AI-THEME-PERSISTENCE-V01 | 테마지속성AI | 현재 강한 테마가 앞으로도 유지될지, 약화될지 판단하는 테마 단위 AI |
| E-ETF-V01 | ETF전용 E시리즈AI | ETF 전용 데이터와 시장국면을 이용해 ETF sleeve와 shadow portfolio를 구성하는 별도 AI 트랙 |

## 4. 화면 표시 가이드

### 4-1. 지표 우선순위

수익률 지표를 가장 위에 배치해 주세요.

권장 순서:

1. 평균 1개월 수익률: `avg_1m_ret`, `top30_avg_1m_return`
2. 누적 검증 수익률: `compounded_validation_return`
3. baseline 대비 개선폭: `*_delta`, `excess_return`
4. 승률: `win_rate`
5. 손실위험: `mdd`, `worst_return`, `risk_tag`
6. 보조 정확도: `auc`, `Rank IC`

### 4-2. 상태 표시

아래 상태는 실제 추천 반영 전 관찰 상태로 표시해 주세요.

- `shadow_observation`
- `shadow_hardening_candidate`
- `admin_only`
- `live_recommendation_applied: false`

화면 문구 예:

`현재 모델은 운영 반영 전 shadow 관찰 단계입니다. 실제 추천/매매 로직에는 아직 적용되지 않습니다.`

### 4-3. N/A 표시 규칙

아래 값은 `0%`로 표시하지 말고 `N/A`로 표시해 주세요.

- null
- NaN
- unavailable
- 아직 관찰기간이 지나지 않아 1W/2W/1M 성과가 없는 값

특히 기준일과 성과일이 같으면 1W/2W/1M 성과가 `N/A`인 것이 정상입니다.

## 5. 페이지별 요청사항

### 5-1. AI 학습 모델 페이지

Primary payload:

`ai_learning_models_current.json`

요청:

- 모델별 카드 상단에 `display_metadata.short_name`, `plain_description` 표시
- `purpose`, `expected_effect`를 펼침 영역 또는 tooltip으로 표시
- `primary_metrics`를 지표 섹션의 우선순위로 사용
- `payloads[]`를 활용해 상세 JSON 소스 확인 가능하게 구성
- ETF/E-series는 별도 섹션으로 분리

### 5-2. 내부용 모델 페이지

Primary payload:

`internal_models_ai_overlay_shadow_current.json`

요청:

- 전략모델별 baseline vs AI overlay shadow 성과 비교
- `policy_map`을 모델별 추천 overlay 정책으로 표시
- `live_recommendation_applied=false`를 명확히 표시
- 평균수익률/누적수익률/baseline 대비 개선폭을 AUC보다 먼저 표시

### 5-3. ETF/E-series 섹션

Primary payload:

`etf_ai_shadow_portfolio_current.json`

요청:

- 현재 ETF AI decision 표시:
  - `current_decision.regime_mode`
  - `selected_role`
  - `selected_template`
  - `selected_role_prob`
  - `selected_template_prob`
- E-series policy hierarchy 표시:
  - `active_primary_shadow_policy`
  - `active_shadow_challenger_policy`
  - `return_basis`
- mode switch / turnover buffer / risk cap / hardening 결과를 요약 표시
- ETF는 주식용 S/T/I/C AI overlay와 다른 별도 트랙임을 표시

## 6. 검증 포인트

QS 반영 후 아래를 확인해 주세요.

- `ai_learning_models_current.json` 기준 모델 6개가 모두 표시되는지
- 각 모델 카드에 설명/목적/기대효과가 표시되는지
- null/NaN 값이 0%가 아니라 N/A로 표시되는지
- shadow 상태가 실제 운영 반영처럼 보이지 않는지
- 내부용 모델 페이지에서 strategy baseline vs AI overlay shadow 비교가 보이는지
- ETF/E-series가 주식용 AI와 분리되어 보이는지
- E-series 관련 current payload 상세 링크 또는 상세 섹션이 누락되지 않았는지
- `as_of_date=2026-05-13`으로 표시되는지

## 7. Quant 쪽 준비 상태

Quant 쪽 로컬 current payload는 준비되었습니다.

최근 갱신 기준:

- 기준일: `2026-05-13`
- 시장 데이터 업데이트 없이 기존 5월 13일 데이터 기준으로 모델/AI/web current payload 재생성 완료
- QM 시장전망 handoff 20d ridge calibration feature 반영 완료
- `ai_learning_models_current.json` 설명 metadata 보강 완료

