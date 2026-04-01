# T-STOCK-V01 Operationalization Process (2026-03-31)

## 목적
- 주식 `T-series`를 연구용 모델에서 운영형 후보 생성 시스템으로 전환한다.
- 운영 전환은 한 번에 하지 않고 단계별로 진행한다.
- 현재 문서는 `2017 backfill` 이후 재조정된 운영 기준을 반영한다.

## 운영 전환 5단계
1. 라벨/정확도 기준 고정
2. strict walk-forward 검증
3. 후보 등급화(`confirmed`, `near`, `observe`)
4. 리스크 필터 적용
5. 자동 리포트 + shadow tracking

## 현재 진행 상태
- 완료: 1단계 라벨/정확도 기준 고정
- 완료: 2단계 strict walk-forward 검증
- 완료: 3단계 후보 등급화
- 완료: 4단계 리스크 필터 적용
- 완료: 5단계 자동 리포트 + shadow tracking
- 현재 상태: 운영형 V1 ready
- 데이터 수집/원천 DB 갱신 자동화는 별도 단계로 남겨둔다.

## 모델 코드
- 운영 모델: `T-STOCK-V01`
- 1단계: `T-STOCK-V01-S1`
- 2단계: `T-STOCK-V01-S2`

## 적용 범위
- universe: 주식 core universe (현재 약 400종목)
- 신호 주기: 주간
- 운영 DB 이력 범위: `2017-10-18 ~ 2025-11-26`
- 최신 watchlist 기준일: `2026-03-26`

## 정답지 bucket
- `T3`
- `T10_ex_T3`
- `T30_ex_T10`
- `T50_ex_T30`
- `OUTSIDE`

## stage 목표
- `stage1`
  - 현재 `OUTSIDE`, `T50_ex_T30`, `T30_ex_T10`에 있는 종목이 `T10_ex_T3` 이상으로 진입할 가능성을 찾는다.
- `stage2`
  - 현재 `T10_ex_T3`에 있는 종목이 `T3`로 승격할 가능성을 찾는다.

## 운영 전환 기준 지표
- 공통 1순위
  - `precision`
  - `capture`
  - `lift`
- 운영 참고
  - historical `T10 hit rate`
  - historical `T3 hit rate`

## strict walk-forward baseline
- stage1 lower -> T10
  - precision: `2.81%`
  - capture: `14.58%`
  - lift: `1.25x`
  - base rate: `2.19%`
- stage2 T10 -> T3 within stage1
  - precision: `0.21%`
  - capture: `38.64%`
  - lift: `1.29x`
  - base rate: `0.16%`

## 현재 운영 threshold profile
- `stage1 >= 0.52`
- `stage2 confirmed >= 0.525`
- `stage2 near >= 0.52`

## 후보 등급화 결과 (리스크 필터 전)
- stage1 total: `12`
- confirmed: `6`
- near: `3`
- observe: `3`

### confirmed
- `대우건설`
- `기가비스`
- `성호전자`
- `삼표시멘트`
- `현대ADM`
- `현대바이오`

### near
- `보성파워텍`
- `선익시스템`
- `한화솔루션`

### observe
- `씨어스테크놀로지`
- `알지노믹스`
- `메지온`

## 내부 테마 라벨링
- labels file: `D:\Quant\data\labels	_stock_v01_theme_labels_20260331.csv`
- label source: `internal_rule_v2`
- label scope: `t_stock_v01_operational_candidates`
- 현재 라벨 분포
  - `biotech_healthcare`: 4
  - `construction_materials`: 2
  - `energy_utility_infra`: 2
  - `medtech_platform`: 1
  - `semiconductor_tech`: 3

## 리스크 필터 규칙
- market cap floor: `300,000,000,000 KRW`
- same-theme cap 적용
- 현재 theme caps
  - `defense_aero`: 2
  - `semiconductor_tech`: 3
  - `construction_materials`: 2
  - `biotech_healthcare`: 2
  - `energy_utility_infra`: 2
  - `medtech_platform`: 1
  - `consumer_brand`: 1
  - `general_largecap`: 1
  - `other`: 1

## 리스크 필터 결과 (최신 운영형 watchlist)
- input total: `12`
- kept total: `10`
- kept confirmed: `6`
- kept near: `3`
- kept observe: `1`
- excluded total: `2`
- excluded mcap floor: `0`

### latest watchlist
#### confirmed
- `대우건설`
- `기가비스`
- `성호전자`
- `삼표시멘트`
- `현대ADM`
- `현대바이오`

#### near
- `보성파워텍`
- `선익시스템`
- `한화솔루션`

#### observe
- `씨어스테크놀로지`

## shadow tracking 결과
- confirmed
  - obs `1946`
  - `T10 hit 70.71%`
  - `T3 hit 21.84%`
- near
  - obs `536`
  - `T10 hit 71.08%`
  - `T3 hit 17.72%`
- observe
  - obs `11213`
  - `T10 hit 6.73%`
  - `T3 hit 1.45%`

## 해석
- `confirmed`는 현재 운영형 최우선 후보군이다.
- `near`는 `T10 hit`가 높고 `T3 hit`도 충분히 의미가 있어 실질적인 2순위 후보군으로 본다.
- `observe`는 폭넓은 감시용 후보군으로 해석한다.
- backfill 이후 기준에서는 `confirmed + near`가 운영 핵심 watchlist다.

## 주요 산출물
- strict walk-forward overall: `t_stock_v01_strict_walkforward_overall_20260331.csv`
- candidate summary: `t_stock_v01_operational_candidate_summary_20260331.csv`
- risk filter summary: `t_stock_v01_risk_filter_summary_20260331.csv`
- latest watchlist: `t_stock_v01_latest_watchlist_2026-03-26.csv`
- shadow tracking overall: `t_stock_v01_shadow_tracking_historical_summary_20260331.csv`
- shadow tracking by horizon: `t_stock_v01_shadow_tracking_historical_summary_by_horizon_20260331.csv`
- refresh script: `D:\Quant\scriptsun_t_stock_v01_operational_refresh.py`

## 다음 단계
- 데이터 backfill/원천 DB 갱신 자동화 연결
- 주간 운영 refresh 자동화
- 후보 성과 누적 검증 후 threshold 재조정
