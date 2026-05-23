# C-series Relationship Model Design

작성일: 2026-04-23

## 1. 목적

C-series는 주식, ETF, 테마 간 가격 움직임의 관계를 분석해서 기존 S-series, T-series 모델을 보정하고, 장기적으로 독립 투자모델로 확장하기 위한 관계 기반 모델이다.

핵심 질문은 다음과 같다.

- 어떤 종목과 ETF가 지속적으로 같이 움직이는가?
- 어떤 종목과 ETF가 지속적으로 반대로 움직이는가?
- 어떤 관계는 일시적 잡음이고, 어떤 관계는 투자에 쓸 수 있을 만큼 오래 유지되는가?
- 기존 S/T 후보가 시장 관계망 안에서 확신도가 높은 후보인가, 아니면 고립된 후보인가?

따라서 C-series는 단순 상관계수 모델이 아니라 `관계 강도`, `관계 방향`, `관계 지속성`, `관계 변화`를 함께 관리하는 모델로 설계한다.

## 2. 모델 명칭

개발용 명칭은 `C-series`를 사용한다.

1차 운영 후보명은 다음과 같이 둔다.

- `C-REL-V01`: 통계 기반 관계 분석 baseline
- `C-STOCK-V01`: 주식 후보 보정용 관계 점수 모델
- `C-ETF-V01`: ETF 관계/헤지 후보 분석 모델
- `C-REL-ML-V01`: 관계 지속 확률을 학습하는 ML 확장 모델

1단계에서는 독립 투자모델이 아니라 `C-REL-V01` 관계 레이어를 먼저 만든다.

## 3. 관계 분류

관계는 수익률 기준으로 세 그룹으로 분류한다.

- `Positive`: 같은 방향으로 움직이는 관계
- `Negative`: 반대 방향으로 움직이는 관계
- `Neutral`: 통계적으로 의미 있거나 안정적인 관계가 약한 상태

기본 수익률 기준은 다음과 같이 나눈다.

- `daily_return`: 전일 대비 종가 수익률
- `weekly_return`: 5거래일 또는 전주 종가 대비 수익률
- `monthly_return`: 21거래일 수익률

1단계 운영 기준은 `weekly_return`, `rolling 60d/120d correlation`을 중심으로 두고, `daily_return`은 단기 변화 감지용 보조 변수로 사용한다.

## 4. 지속성 핵심 변수

C-series에서 가장 중요한 변수는 관계 지속성이다. 단기 상관관계는 뉴스성 잡음일 수 있으므로, 관계가 얼마나 오래 유지되는지 별도 점수로 관리한다.

핵심 변수는 다음과 같다.

- `corr_20d`: 최근 20거래일 상관계수
- `corr_60d`: 최근 60거래일 상관계수
- `corr_120d`: 최근 120거래일 상관계수
- `corr_252d`: 최근 252거래일 상관계수
- `relation_type`: Positive, Negative, Neutral
- `direction_consistency`: 20d, 60d, 120d 방향 일치 여부
- `persistence_days`: 같은 관계 방향이 유지된 연속 거래일 수
- `persistence_ratio_120d`: 최근 120거래일 중 같은 관계로 분류된 비율
- `break_count_120d`: 최근 120거래일 중 관계 방향이 바뀐 횟수
- `stability_score`: rolling correlation 변동성이 낮을수록 높은 점수
- `relationship_strength_score`: 상관계수 절댓값 기반 점수
- `relationship_persistence_score`: 방향 일관성, 지속일수, break count 기반 점수
- `relationship_confidence_score`: 강도, 지속성, 유동성, 데이터 품질을 결합한 최종 신뢰도

1단계에서는 다음 산식을 baseline으로 둔다.

```text
relationship_confidence_score
= abs(corr_60d)
  * direction_consistency
  * persistence_ratio_120d
  * stability_score
  * liquidity_score
```

이 산식은 고정하지 않고, 1단계 검증 이후 성과 기반으로 조정한다.

## 5. AI 알고리즘 적용 방향

### 5.1 1단계: 통계 기반 baseline

1단계는 AI 모델보다 설명 가능한 통계 기반 relationship layer를 우선 만든다.

사용 방법:

- rolling correlation
- persistence score
- stability score
- 종목별 Positive/Negative Top-N 관계 추출
- 테마별 관계 heatmap 생성

이 단계는 해석 가능성과 데이터 검증이 핵심이다.

### 5.2 2단계: 그래프 모델

종목과 ETF를 node로 보고 관계를 edge로 저장한다.

적용 가능 알고리즘:

- community detection
- centrality
- PageRank
- spectral clustering
- graph embedding

활용 목적:

- 실제 시장 수급 기준 테마 군집 발견
- 동일 cluster 과밀 투자 방지
- 테마 대표 ETF 또는 중심 종목 탐색
- 테마 확산 경로 분석

### 5.3 3단계: Lead-Lag 모델

ETF가 먼저 움직이고 개별 종목이 따라오는지, 대형주가 먼저 움직이고 중소형주가 따라오는지 분석한다.

적용 가능 알고리즘:

- lagged correlation
- cross-correlation
- Granger causality
- lagged return regression

활용 목적:

- 선행 ETF 기반 후행 종목 후보 가점
- 테마 확산 초기 감지
- S/T 후보의 진입 타이밍 보정

### 5.4 4단계: ML 기반 관계 지속 확률

Gradient Boosting 또는 Random Forest로 관계 지속 확률을 학습한다.

학습 목표 예시:

- 다음 1주 동안 현재 관계가 유지되는가?
- 다음 1개월 동안 Positive 관계가 강화되는가?
- 관계 기반 가점이 붙은 S/T 후보가 초과수익을 내는가?

입력 변수 예시:

- `corr_20d`, `corr_60d`, `corr_120d`
- `persistence_days`
- `persistence_ratio_120d`
- `break_count_120d`
- `stability_score`
- `lead_lag_score`
- `theme_overlap`
- `volume_co_movement`
- `regime_state`

## 6. 1단계 개발 방향

1단계 목표는 독립 매수모델을 만드는 것이 아니라, 기존 Quant 시스템에 붙일 수 있는 `Correlation Relationship Layer`를 구축하는 것이다.

1단계 산출물은 다음 세 가지다.

- 종목/ETF/테마별 수익률 데이터마트
- 관계 edge DB
- S/T 모델 후보에 붙일 관계 보정 점수

## 7. DB 구성 방향

### 7.1 신규 DB를 만드는 것이 좋은 이유

C-series는 기존 `price.db`, `quant_service.db`, `tseries_operational.db`를 직접 수정하지 않는 별도 DB로 시작하는 것이 좋다.

권장 DB:

```text
D:\Quant\data\db\cseries_relationship.db
```

신규 DB가 좋은 이유는 다음과 같다.

- 기존 S/T 운영 DB를 건드리지 않아 운영 리스크가 낮다.
- 상관관계 edge 데이터는 조합 수가 많아 별도 관리가 적합하다.
- 연구용 threshold와 운영용 threshold를 분리하기 쉽다.
- 나중에 QS/web에 공개할 payload를 별도로 만들기 쉽다.
- 실패하거나 모델을 폐기해도 기존 DB에 영향이 없다.

### 7.2 입력 DB

1단계 입력은 기존 DB와 CSV를 읽기 전용으로 사용한다.

- `D:\Quant\data\db\price.db`
- `prices_daily`: 종가, 거래량, 거래대금
- `instrument_master`: 종목명, 자산유형
- `etf_meta`: ETF 메타 정보
- `D:\Quant\data\universe\universe_mix_top400_latest.csv`
- `D:\Quant\data\universe\universe_etf_master_latest.csv`
- `D:\Quant\data\db\tseries_operational.db`
- `ts_theme_labels`: T-series 내부 테마 라벨
- `ts_candidates_latest`: T-series 최신 후보
- `D:\Quant\data\db\quant_service.db`
- `pub_model_current_holdings`: S-series current holdings

### 7.3 신규 테이블 초안

#### `c_runs`

C-series 실행 이력을 저장한다.

```text
run_id
asof_date
model_code
run_type
status
input_price_max_date
stock_universe_count
etf_universe_count
started_at
finished_at
notes
```

#### `c_return_series`

종목별 수익률 데이터마트다.

```text
asof_date
ticker
name
asset_type
theme_bucket
close
volume
trading_value
daily_return
weekly_return
monthly_return
vol_20d
liquidity_20d_value
data_quality_flag
```

#### `c_theme_return_series`

테마별 평균 수익률과 확산도를 저장한다.

```text
asof_date
theme_bucket
member_count
avg_daily_return
avg_weekly_return
median_weekly_return
positive_ratio
negative_ratio
dispersion_score
liquidity_sum
```

#### `c_relationship_edges`

종목/ETF/테마 간 관계 edge를 저장한다.

```text
asof_date
source_type
source_id
target_type
target_id
relation_type
corr_20d
corr_60d
corr_120d
corr_252d
direction_consistency
persistence_days
persistence_ratio_120d
break_count_120d
stability_score
relationship_strength_score
relationship_persistence_score
relationship_confidence_score
liquidity_score
rank_positive
rank_negative
created_at
```

#### `c_model_overlay_scores`

기존 S/T 후보에 붙이는 보정 점수다.

```text
asof_date
base_model_code
ticker
base_bucket
base_score
positive_relation_count
negative_relation_count
theme_support_score
etf_support_score
hedge_risk_score
cluster_concentration_score
c_overlay_score
final_adjusted_score
notes
```

## 8. 1단계 계산 범위

1단계에서는 모든 종목 조합을 전부 저장하지 않는다. 조합 폭발을 막기 위해 다음 범위로 제한한다.

- 주식 universe: `universe_mix_top400_latest`
- ETF universe: `universe_etf_master_latest` 중 거래대금/가격 데이터가 충분한 ETF
- 관계 계산 1차 대상:
  - stock-to-ETF
  - stock-to-theme
  - ETF-to-theme
  - theme-to-theme
- stock-to-stock은 1단계에서는 같은 테마 내부 Top-N만 제한적으로 계산한다.

1단계 저장 기준:

- 종목별 Positive Top 20
- 종목별 Negative Top 20
- 테마별 Positive Top 20
- 테마별 Negative Top 20
- confidence score가 낮은 Neutral 관계는 요약 통계만 저장하고 edge 저장은 최소화한다.

## 9. 기존 S/T 모델 적용 방향

### 9.1 S-series 적용

S-series는 이미 시장 상황별 포트폴리오 모델이므로 C-series를 보조 레이어로 붙인다.

적용 효과:

- 같은 cluster에 종목이 과도하게 몰리는지 확인
- S3/S3_CORE2 성장형 후보가 관련 ETF/테마와 동조 중인지 확인
- S2/S6 방어형 모델에서 Negative 관계 기반 hedge 후보 탐색
- 사용자용 stable/balanced/growth 모델의 종목 중복 문제를 관계 cluster 기준으로 완화

1단계에서는 실제 종목 교체보다 다음 지표를 먼저 붙인다.

- `theme_support_score`: 관련 테마가 같이 강한지
- `etf_support_score`: 관련 ETF가 같은 방향인지
- `cluster_concentration_score`: 같은 관계망에 너무 몰렸는지
- `hedge_risk_score`: 반대 관계 ETF가 강하게 움직이는지

기대 효과:

- 단순 성과 중심 S 모델에 시장 관계 설명력을 추가한다.
- 성장형 모델의 후보 확신도를 더 잘 설명할 수 있다.
- 안정형/균형형 포트폴리오의 편중 리스크를 줄일 수 있다.

### 9.2 T-series 적용

T-series는 잠재 후보 발굴 모델이므로 C-series와 궁합이 좋다.

적용 효과:

- T-STOCK 후보가 관련 ETF/테마의 Positive 흐름 안에 있는지 확인
- T-ETF 후보와 주식 테마 간 관계를 확인
- 신규 발굴 후보가 테마 확산 초기인지, 고립된 단독 움직임인지 구분
- watchlist 후보를 `관계 강화`, `관계 유지`, `관계 약화`로 설명 가능

1단계에서는 T 후보를 교체하지 않고 다음 보조 정보를 붙인다.

- `relationship_status`: strengthening, stable, weakening, broken
- `related_etf_top_positive`
- `related_etf_top_negative`
- `theme_relation_score`
- `persistence_days`
- `relationship_confidence_score`

기대 효과:

- T-series 후보가 적게 나오는 시기에도 후보의 질을 설명할 수 있다.
- 후보가 많이 바뀌는 시기에는 실제 관계망 변화인지 데이터 잡음인지 구분할 수 있다.
- 신규 편입 종목 페이지에서 관계 기반 설명을 추가할 수 있다.

## 10. 1단계 구현 스크립트 제안

1단계 구현 파일은 다음처럼 나누는 것이 좋다.

```text
scripts/build_c_series_return_mart.py
scripts/build_c_series_relationship_edges.py
scripts/build_c_series_overlay_scores.py
scripts/validate_c_series_relationship_db.py
src/quant_service/schema_cseries_relationship.sql
```

각 스크립트 역할은 다음과 같다.

- `build_c_series_return_mart.py`: 가격 DB와 universe를 읽어 수익률 mart 생성
- `build_c_series_relationship_edges.py`: rolling correlation과 persistence score 계산
- `build_c_series_overlay_scores.py`: S/T current 후보에 C overlay score 부여
- `validate_c_series_relationship_db.py`: 결측, coverage, edge count, 최신성 검증
- `schema_cseries_relationship.sql`: 신규 DB schema 정의

## 11. 1단계 검증 방법

1단계에서는 성과 검증보다 데이터/관계 검증을 먼저 한다.

필수 검증:

- 가격 데이터 coverage
- 주식/ETF universe coverage
- 상관관계 계산 가능 종목 수
- 종목별 edge count
- Positive/Negative/Neutral 비율
- persistence score 분포
- 특정 테마의 관계망이 직관과 맞는지 샘플 검토
- S/T 후보에 overlay score가 정상 부여되는지 확인

성과 검증:

- C overlay score 상위 S/T 후보와 하위 S/T 후보의 1주/1개월 성과 비교
- Positive ETF support가 있는 후보와 없는 후보의 성과 비교
- 관계 지속성이 높은 후보와 낮은 후보의 drawdown 비교
- cluster concentration을 낮춘 포트폴리오의 변동성 변화 확인

## 12. 1단계 완료 기준

1단계 완료 기준은 다음과 같다.

- `cseries_relationship.db` 생성
- stock/ETF/theme return mart 생성
- stock-to-ETF, stock-to-theme, theme-to-theme 관계 edge 생성
- Positive/Negative/Neutral 분류 결과 저장
- persistence score 저장
- S-series current holdings에 overlay score 부여
- T-series latest/watchlist 후보에 overlay score 부여
- validation report 생성
- 1차 샘플 리포트 작성

## 13. 운영 반영 원칙

1단계에서는 웹 공개 또는 실제 포트폴리오 변경에 바로 반영하지 않는다.

운영 반영 순서는 다음과 같다.

1. research DB 생성
2. S/T 후보에 overlay score만 부여
3. 4~8주간 shadow tracking
4. 성과 비교
5. 모델 설명/리스크 관리 지표로 QS admin에 제한 노출
6. 효과 확인 후 사용자용 모델 설명 또는 종목 가중치 보정에 반영

## 14. 결론

C-series 1단계는 독립 투자모델이 아니라 시장 관계망을 수치화하는 기반 레이어로 개발한다.

가장 중요한 판단 기준은 다음과 같다.

- 관계가 강한가?
- 관계가 지속되는가?
- 관계가 최근 강화되고 있는가?
- 기존 S/T 후보를 더 잘 설명하거나 걸러주는가?

1단계가 안정적으로 작동하면 C-series는 기존 모델의 설명력, 리스크 관리, 종목 중복 완화, 테마 확산 감지에 사용할 수 있다. 이후 성과 검증을 거쳐 독립형 `C-REL-V01` 또는 ML 기반 `C-REL-ML-V01`로 확장한다.
