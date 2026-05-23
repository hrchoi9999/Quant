# AI Learning Model V01 데이터 현황 및 1차 개발 계획

## 목적

기존 S/T/I/C 모델을 대체하지 않고, 각 모델이 선정한 후보의 성공 가능성과 위험도를 보정하는 AI 학습 레이어를 만든다.

핵심 질문은 아래와 같다.

- 어떤 후보가 편입 후 1W/2W/1M 성과가 좋은가?
- 어떤 후보가 수익률은 좋아도 MDD가 큰 위험 후보인가?
- 어떤 모델/테마/시장국면 조합에서 실제 운영 성과가 좋아지는가?
- 기존 모델의 후보를 `AI_CONFIRM`, `AI_CAUTION`, `AI_WATCH` 같은 태그로 보정할 수 있는가?

## 기본 원칙

- AI는 1차적으로 기존 모델의 후보를 보정하는 overlay로 사용한다.
- 학습 feature는 반드시 편입 당시 알 수 있었던 사전 정보만 사용한다.
- label은 편입 이후 실제 시장 성과로 만든다.
- 실제 운영 성과와 백테스트 성과는 분리한다.
- 초기에는 shadow tracking으로 운영하고, 바로 포트폴리오 교체/비중 조정에 쓰지 않는다.

## 현재 데이터 보유 현황

| 데이터 유형 | 현재 상태 | 주요 위치 | 판단 |
|---|---|---|---|
| 가격/거래량 | 보유 | `price.db.prices_daily` | 1차 학습 핵심 feature 생성 가능 |
| 종목 메타/유니버스 | 보유 | `price.db.instrument_master`, `data/universe` | 사용 가능 |
| 업종/테마 분류 | 보유 | `security_classification.db`, `tseries_operational.db::ts_theme_labels` | 사용 가능, 보강 가능 |
| 펀더멘털 | 보유 | `fundamentals.db`, `dart_main.db` | PIT 방식 feature로 사용 가능 |
| S-series 산출값 | 보유 | `quant_service.db`, `quant_service_detail.db` | 사용 가능 |
| T-series 산출값 | 보유 | `tseries_operational.db` | 사용 가능 |
| I-series 산출값 | 보유 | `i_series_operational.db` | 사용 가능 |
| C-series 관계/순환 | 보유 | `cseries_relationship.db` | 좋은 추가 feature |
| 실제 운영 성과 label | 보유 | `admin_new_entry_tracker.json` | 1W/2W/1M/2M/3M label 사용 가능 |
| 시장 regime | 보유 | `regime.db`, `price.db.regime_history` | 사용 가능 |
| 시장 breadth | 부분 보유 | 가격 DB에서 산출 가능 | 전용 mart 필요 |
| 상대강도 | 부분 보유 | 가격/테마/지수로 산출 가능 | 전용 feature 생성 필요 |
| 수급 데이터 | 미흡 | 명확한 운영 DB 없음 | 추가 수집 필요 |
| 공매도/대차 | 미보유 | 운영 DB 없음 | 추가 수집 필요 |
| 뉴스/감성 | 미보유 | 운영 DB 없음 | 추가 수집 필요 |
| 공시 이벤트 | 부분 보유 | DART 재무제표 중심 | 이벤트성 공시/키워드 가공 필요 |
| 매크로 | 미흡 | 별도 운영 DB 약함 | 환율/금리/원자재 추가 필요 |
| ETF 구성/리밸런싱 | 부분 보유 | `etf_meta`, ETF classification | 미국 확장 고려 시 보강 필요 |

## 1차 개발 범위

1차는 현재 보유 데이터만으로 만든다.

추가 수집 없이 가능한 feature:

- 모델 정보: `model_code`, `scope`, `event_type`
- 편입 정보: `event_date`, `rank_no`, `score`, `score_basis`, `weight`, `candidate_bucket`
- 모델 중복 신호: 같은 종목이 같은 주차에 몇 개 모델에서 등장했는지
- 가격 feature: 5D/10D/20D/60D 수익률, 변동성, 거래대금, MDD, 신고가/저가 거리
- 상대강도 feature: 시장/업종/테마 대비 초과수익률
- 펀더멘털 feature: PIT 매출/영업이익/성장률/가속도
- 테마 feature: theme_bucket, theme 최근 수익률, theme rank, theme rotation score
- C-series feature: positive/negative 관계 수, stability_score, overlay score
- I-series feature: raw_score, rank_score, heat/reaccel/overheated 관련 tag
- 실제 성과 label: 편입 후 `1w`, `2w`, `1m`, `2m`, `3m` 수익률/MDD/Sharpe

## 1차 모델명

개발명:

- `AI-CANDIDATE-VALIDATION-V01`
- Korean name: `퀀트후보검증AI`
- Legacy alias: `AI-OVERLAY-V01`

세부 task:

- `AI-CANDIDATE-VALIDATION-V01-RET1M`: 1M 수익률 개선 후보 예측
- `AI-CANDIDATE-VALIDATION-V01-QUALITY1M`: 1M 수익률 + 낮은 MDD + 양호한 Sharpe 후보 예측
- `AI-CANDIDATE-VALIDATION-V01-RISK1M`: 1M 손실 또는 과대 MDD 위험 후보 예측

사용자/운영 표시명은 아직 공개하지 않는다.
초기에는 admin/internal shadow 모델로 관리한다.

## 학습 단위

학습 row는 “모델이 특정 날짜에 특정 종목을 선정한 이벤트”이다.

기본 key:

```text
scope
model_code 또는 service_profile
security_code
event_date
week_end
event_type
```

하나의 종목이 여러 모델에서 동시에 선정되면 row는 모델별로 유지한다.
대신 `model_overlap_count`, `overlap_model_codes` 같은 중복/컨센서스 feature를 추가한다.

## Label 설계

1차 label은 `1M` 중심으로 한다.

필수 label:

- `label_return_1m_positive`: `forward_returns["1m"] > 0`
- `label_return_1m_top`: 동일 주차 이벤트 중 1M 수익률 상위 30%
- `label_quality_1m`: 1M 수익률 양수 + 1M MDD가 과도하지 않음 + 1M Sharpe 양수
- `label_risk_1m`: 1M 수익률 음수 또는 1M MDD 과대

보조 label:

- `forward_return_1w`
- `forward_return_2w`
- `forward_return_1m`
- `forward_mdd_1m`
- `forward_sharpe_1m`

주의:

- label은 event_date 이후의 값이므로 학습 target으로만 사용한다.
- label 값을 같은 row의 feature로 넣으면 look-ahead bias가 된다.

## Feature Mart 설계

신규 DB:

```text
D:\Quant\data\db\ai_learning.db
```

권장 테이블:

```sql
ai_feature_events
ai_feature_values
ai_training_labels
ai_model_runs
ai_model_predictions
ai_shadow_summary
```

1차 구현은 단순화를 위해 wide table 하나로 시작해도 된다.

초기 table:

```text
ai_overlay_training_mart
```

주요 컬럼:

- identifiers: `scope`, `model_code`, `service_profile`, `ticker`, `name`, `event_date`, `week_end`
- event features: `event_type`, `rank_no`, `score`, `weight`, `candidate_bucket`
- price features: `ret_5d`, `ret_10d`, `ret_20d`, `ret_60d`, `vol_20d`, `mdd_20d`, `trading_value_20d`
- relative features: `rel_ret_vs_market_20d`, `rel_ret_vs_theme_20d`
- fundamental features: `revenue_growth`, `op_income_growth`, `fund_accel_score`
- c features: `c_positive_count`, `c_negative_count`, `c_stability_score`, `c_overlay_score`
- i features: `i_raw_score`, `i_rank_score`, `i_bucket`
- consensus features: `model_overlap_count`, `overlap_s_count`, `overlap_t_count`, `overlap_i_count`
- labels: `fwd_ret_1m`, `fwd_mdd_1m`, `fwd_sharpe_1m`, `label_quality_1m`, `label_risk_1m`

## 1차 모델 알고리즘

초기 모델은 tabular ML로 시작한다.

Baseline:

- Logistic Regression
- Gradient Boosting Classifier

후속 후보:

- Random Forest
- HistGradientBoosting
- LightGBM 또는 XGBoost는 의존성/운영 안정성 확인 후 도입

1차는 sklearn 내장 모델 중심으로 진행한다.

## 검증 방식

운영 시작 이후 데이터는 아직 짧으므로 두 가지를 분리한다.

1. historical reconstructed test
   - 과거 이벤트 재구성 row를 사용
   - 모델 구조와 feature 유효성 확인용
   - 실제 운영 성과로 오해하지 않도록 표시 분리

2. live-start actual test
   - live_start_date 이후 event만 사용
   - 현재는 표본이 적으므로 shadow tracking 중심
   - 시간이 지날수록 이 지표의 비중을 높인다.

검증 지표:

- AUC
- precision@topN
- top decile 평균 1M 수익률
- top decile 평균 1M MDD
- top decile 평균 1M Sharpe
- AI_CONFIRM vs AI_CAUTION 실제 성과 차이

## 산출물

1차 산출물:

- `reports/ai_overlay_v01/ai_overlay_training_mart_YYYYMMDD.parquet`
- `reports/ai_overlay_v01/ai_overlay_training_mart_YYYYMMDD.csv`
- `reports/ai_overlay_v01/ai_overlay_model_eval_YYYYMMDD.json`
- `reports/ai_overlay_v01/ai_overlay_model_eval_YYYYMMDD.md`
- `data/db/ai_learning.db`

운영 후보 산출물:

- `ai_model_predictions`
- `ai_shadow_summary`

향후 QS/admin 표시 후보:

- 후보별 `ai_score`
- `ai_tag`: `AI_CONFIRM`, `AI_WATCH`, `AI_CAUTION`
- `ai_reason`: 주요 feature 설명
- `ai_model_version`: `AI-CANDIDATE-VALIDATION-V01`
- `legacy_ai_model_version`: `AI-OVERLAY-V01`

## 1차 개발 순서

### Step 1. 학습 mart 생성기

목표:

- `admin_new_entry_tracker.json`의 event row를 기준으로 feature/label mart를 만든다.

입력:

- `admin_new_entry_tracker.json`
- `price.db`
- `security_classification.db`
- `fundamentals.db`
- `cseries_relationship.db`
- `tseries_operational.db`
- `i_series_operational.db`

출력:

- `ai_overlay_training_mart`
- row count / label coverage summary

### Step 2. baseline 학습

목표:

- Logistic Regression과 Gradient Boosting으로 1M quality/risk label 예측력을 확인한다.

출력:

- 모델별 AUC
- precision@topN
- feature importance
- AI_CONFIRM/AI_CAUTION 그룹별 실제 성과

### Step 3. shadow scoring

목표:

- 최신 후보 row에 AI score/tag를 붙인다.
- 실제 포트폴리오에는 반영하지 않는다.

출력:

- 최신 후보별 `ai_quality_score`
- `ai_risk_score`
- `ai_tag`
- `ai_reason`

### Step 4. 운영 연결

목표:

- daily pipeline의 admin current 생성 이후 AI scoring을 붙일 수 있게 준비한다.

초기 운영 순서:

```text
admin_new_entry_tracker 생성
AI feature mart 생성
AI shadow scoring
admin AI payload 생성
GCS publish
```

### Step 5. 추가 데이터 확장

1차 baseline이 의미 있으면 아래 순서로 추가 수집한다.

1. 시장 breadth 전용 mart
2. 수급 데이터
3. 공시 이벤트/뉴스 키워드
4. 매크로/환율/금리
5. ETF 구성/리밸런싱 데이터

## 초기 판단

지금 보유 데이터만으로도 `AI-CANDIDATE-VALIDATION-V01`의 1차 학습은 가능하다.

다만 실제 운영 label은 아직 기간이 짧으므로, 초기 성과 평가는 과거 재구성 label과 실제 운영 label을 분리해서 봐야 한다.

가장 먼저 할 일은 `ai_overlay_training_mart`를 만드는 것이다.
