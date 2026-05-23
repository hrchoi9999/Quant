# AI-MODEL-SELECTION-V01 Experiment - 2026-05-11

## 모델 정의

| 항목 | 값 |
|---|---|
| model_code | `AI-MODEL-SELECTION-V01` |
| 한글명 | `모델선택AI` |
| 목적 | 현재 시장/후보 상태에서 어떤 전략 모델을 더 신뢰할지 판단 |
| 현재 상태 | baseline experiment |
| ETF 처리 | 제외. ETF 모델 선택은 ETF 전용 AI 트랙에서 별도 개발 |

## Baseline Test

기준일:

- `2026-05-08`

입력:

- `D:\Quant\reports\ai_overlay_v01\ai_overlay_training_mart_20260508.csv`
- `D:\QuantMarket\service_platform\ai_training\market_context\current\market_context_daily_current.csv`

학습 단위:

- `event_date + scope_key + model_id`

Target:

- 같은 `event_date` 내에서 다음 1개월 후보 평균 수익률이 상위 1/3에 드는 모델
- label: `label_model_top_tercile_1m`

Feature:

- 모델별 후보 수
- 후보 rank/score/weight 평균
- 최근 후보 수익률, 변동성, MDD, 거래대금 평균
- 성장성/테마지원/수급/DART feature 평균
- 모델별 과거 4회/8회 trailing return, win rate
- QM market context
- `scope_key`, `model_id`, `model_family`

## Result

| metric | value |
|---|---:|
| train rows | 1,617 |
| valid rows | 616 |
| valid positive rate | 0.269481 |
| AUC | 0.531988 |
| top30 label rate | 0.233333 |
| bottom30 label rate | 0.266667 |
| top30 future return 1M | 0.055532 |
| bottom30 future return 1M | 0.065640 |

현재 score 상위 모델:

| rank | scope | model | score |
|---:|---|---|---:|
| 1 | `tseries` | `T-STOCK-V01` | 0.745367 |
| 2 | `user` | `balanced` | 0.424253 |
| 3 | `user` | `stable` | 0.424253 |
| 4 | `internal` | `S3_ACCEL_V01` | 0.346263 |
| 5 | `user` | `growth` | 0.303737 |

## 판단

현재 baseline은 운영 반영하기 어렵다.

이유:

- AUC가 0.531988로 낮다.
- top30 label rate가 bottom30보다 낮다.
- 단순 next 1M 평균수익률 top-tercile label은 모델 선택 문제를 충분히 설명하지 못한다.

## 다음 개선 방향

1. Label 변경
   - 단순 평균수익률 대신 risk-adjusted score 사용
   - 예: `avg_return - downside_penalty`, `return / volatility`, `return + mdd`

2. 모델군별 분리
   - S/T/I/user를 한 번에 비교하지 말고, 모델군별 우수 모델을 먼저 예측
   - 이후 meta layer에서 통합

3. 국면별 분리
   - risk_on / neutral / risk_off 구간별 모델 선택 성능을 따로 측정

4. 후보 overlap/테마 분산도 강화
   - 후보군이 특정 테마에 몰렸는지
   - 후보 중복도가 높은지
   - AI risk/valuation/rank score 평균이 좋은지

5. Horizon 차등화
   - S-series는 1M
   - T-series는 1W~2W
   - I/C-series는 1M~3M 등 모델 목적별 horizon을 다르게 적용

## Outputs

- `D:\Quant\scripts\run_model_selection_ai_v01_experiment.py`
- `D:\Quant\reports\model_selection_ai_v01\model_selection_ai_experiment_20260508.csv`
- `D:\Quant\reports\model_selection_ai_v01\model_selection_ai_current_scores_20260508.csv`
- `D:\Quant\reports\model_selection_ai_v01\model_selection_ai_experiment_20260508.json`
- `D:\Quant\reports\model_selection_ai_v01\model_selection_ai_experiment_20260508.md`
- `D:\Quant\data\models\model_selection_ai\AI-MODEL-SELECTION-V01_20260508_001.joblib`

## Operating Rule

`모델선택AI`는 아직 shadow 이전의 research 단계다.

현재 결과는 QS/web 또는 운영 모델 선택에 반영하지 않는다.
