# AI-GROWTH-VALUATION-V01 Challenger Shadow Web Payload - 2026-05-06

## 목적

`AI-GROWTH-VALUATION-V01`의 기준 모델은 유지하되, QuantMarket context ablation 결과가 좋았던 challenger/risk overlay를 웹에서 관찰할 수 있도록 admin current payload를 생성했다.

## 운영 구조

| 역할 | feature set | 사용 방식 |
|---|---|---|
| Champion/reference | `LOCAL_MARKET` | 기존 기준 모델. 직접 교체하지 않음 |
| Challenger | `QM_MARKET_THEME` | `AI-GROWTH-VALUATION-V01-QM-THEME` 후보. 4~8주 shadow 성과 추적 |
| Risk overlay | `QM_MARKET_RISK` | 별도 매수 모델이 아니라 caution/risk tag로 사용 |

## 생성된 모델 파일

- `D:\Quant\data\models\valuation_ai\AI-GROWTH-VALUATION-V01-QM-MARKET-THEME-20260504-001.joblib`
- `D:\Quant\data\models\valuation_ai\AI-GROWTH-VALUATION-V01-QM-MARKET-RISK-20260504-001.joblib`

## 웹 제공 current payload

### 1. Challenger Current

경로:

- `D:\Quant\service_platform\web\admin_data\current\valuation_ai_challenger_current.json`

용도:

- 최신 S/T/I/user 후보에 대해 champion, challenger, risk overlay를 나란히 표시
- 후보별 승격/강등 여부 확인
- risk tag 확인

주요 top-level 필드:

- `source_name`
- `schema_version`
- `visibility`
- `model_code`
- `as_of_date`
- `generated_at`
- `champion`
- `challenger`
- `risk_overlay`
- `summary_by_model`
- `state_counts`
- `candidates`

후보 row 주요 필드:

- `scope`
- `model_code`
- `security_code`
- `display_name`
- `rank_no`
- `score`
- `score_basis`
- `weight`
- `candidate_bucket`
- `champion_state`
- `champion_score`
- `challenger_state`
- `challenger_score`
- `challenger_score_delta`
- `challenger_change_label`
- `risk_state`
- `risk_score`
- `risk_tag`
- `qm_market_state_label`
- `qm_quantmarket_theme_bucket`
- `qm_theme_momentum_score`
- `qm_theme_rotation_score`
- `qm_theme_mapping_confidence`
- `qm_risk_score`
- `qm_market_stress_score`

### 2. Challenger Shadow Performance

경로:

- `D:\Quant\service_platform\web\admin_data\current\valuation_ai_challenger_shadow_performance.json`

용도:

- challenger/risk tag별 실제 운영 이후 수익률 추적
- 모델별, 태그별, 상태별 1W/2W/1M/2M/3M/6M/1Y 성과 표시

주요 top-level 필드:

- `source_name`
- `schema_version`
- `visibility`
- `model_code`
- `source_as_of_date`
- `performance_asof_date`
- `generated_at`
- `metric_basis`
- `horizons`
- `summary`
- `detail`

성과 필드:

- `live_current_return`
- `live_current_mdd`
- `live_current_sharpe`
- `live_ret_1w`
- `live_ret_2w`
- `live_ret_1m`
- `live_ret_2m`
- `live_ret_3m`
- `live_ret_6m`
- `live_ret_1y`
- 각 horizon별 `mdd`, `sharpe`, `available`, `trading_days_seen`

## 현재 생성 결과

기준일:

- `as_of_date = 2026-05-04`

생성 결과:

- challenger current 후보 row: `348`
- summary_by_model row: `14`
- shadow performance detail row: `348`
- shadow performance summary row: `232`

초기 생성일에는 `source_as_of_date`와 `performance_asof_date`가 같아 1W/2W/1M 성과는 아직 대부분 `null`이다.
향후 거래일이 누적되면 같은 tracker가 horizon별 성과를 채운다.

## Pipeline 반영

`D:\Quant\src\pipelines\rebuild_growth_valuation_ai_pipeline.py`에 다음 단계가 추가됐다.

1. `build_valuation_ai_challenger_current.py`
2. `build_valuation_ai_challenger_shadow_tracker.py`

따라서 valuation AI pipeline 재실행 시 웹 제공 admin current payload도 함께 갱신된다.

## QS 연동 메모

QS에서는 우선 admin-only 화면에서 다음 방식으로 노출하는 것이 적절하다.

- 기존 champion state/score 유지
- `QM-THEME challenger` state/score 및 승격/강등 태그 표시
- `QM-RISK`는 별도 추천 모델이 아니라 `risk_tag`로 표시
- shadow 성과는 `valuation_ai_challenger_shadow_performance.json`의 `summary/detail`을 사용
- 성과 값이 `null`이면 `N/A`로 표시
