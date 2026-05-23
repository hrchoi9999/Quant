# AI-OVERLAY-V01 1차 실행 결과

## 기준

- asof_date: `2026-05-04`
- model_code: `AI-CANDIDATE-VALIDATION-V01`
- Korean name: `퀀트후보검증AI`
- legacy alias: `AI-OVERLAY-V01`
- 목적: 기존 S/T/I/user 모델 후보에 AI shadow scoring 부여
- 운영 반영 여부: 미반영, shadow only

## 생성 산출물

- DB: `D:\Quant\data\db\ai_learning.db`
- 학습 mart table: `ai_overlay_training_mart`
- shadow score table: `ai_shadow_scores`
- 평가 table: `ai_model_eval`
- report dir: `D:\Quant\reports\ai_overlay_v01`
- 평가 리포트:
  - `D:\Quant\reports\ai_overlay_v01\ai_overlay_model_eval_20260504.md`
  - `D:\Quant\reports\ai_overlay_v01\ai_overlay_model_eval_20260504.json`

## 데이터 규모

| 항목 | 건수 |
|---|---:|
| 전체 mart rows | 20,819 |
| 1M label rows | 20,427 |
| 실제 운영 이후 rows | 322 |
| shadow scoring rows | 2,736 |

## 학습 모델

1차 baseline:

- Logistic Regression
- Gradient Boosting

학습 target:

- `label_quality_1m`
- `label_risk_1m`

## 평가 결과

| label | model | train | test | AUC | top30 1M return | top30 win rate |
|---|---:|---:|---:|---:|---:|---:|
| quality_1m | logistic | 15,663 | 4,764 | 0.502 | 0.82% | 60.00% |
| quality_1m | gradient boosting | 15,663 | 4,764 | 0.533 | 4.90% | 76.67% |
| risk_1m | logistic | 15,663 | 4,764 | 0.504 | 7.25% | 50.00% |
| risk_1m | gradient boosting | 15,663 | 4,764 | 0.528 | 14.64% | 60.00% |

## 1차 판단

- Logistic Regression은 거의 기준선 수준이다.
- Gradient Boosting이 상대적으로 낫지만 AUC는 아직 낮다.
- quality 모델은 top30 기준 성과 차이가 일부 보인다.
- risk 모델은 아직 해석 안정성이 부족하다.
- 실제 운영 label은 아직 322건뿐이라 운영 의사결정에 반영하기에는 이르다.

## Shadow tag 분포

| scope | AI_CONFIRM | AI_WATCH | AI_CAUTION |
|---|---:|---:|---:|
| internal | 103 | 2,288 | 75 |
| tseries | 58 | 101 | 4 |
| user | 3 | 86 | 18 |

## 다음 단계

1. `AI_CONFIRM`, `AI_WATCH`, `AI_CAUTION`별 실제 1W/2W/1M 성과를 지속 추적한다.
2. risk label 정의를 보강한다.
3. 현재는 과거 재구성 label 중심이므로, 실제 운영 label만 따로 분리한 평가표를 계속 누적한다.
4. 2~3개월 shadow tracking 후 기존 모델 점수 보정 또는 challenger 모델 생성 여부를 판단한다.
