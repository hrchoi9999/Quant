# TASK 02. ETF 분류 + 코어 ETF 유니버스(core) + 메타 구축

## 0) 작업 배경 / 전제
- TASK_01 완료 상태:
  - ETF 마스터 유니버스 CSV 생성 완료
  - ETF 일봉 OHLCV 수집 완료
  - `price.db`의 `prices_daily`에 ETF 가격 upsert 적재 완료
  - `validate_etf_pipeline.py`로 최소 검증 완료
- 이번 TASK_02의 목적은 서비스 UI 작업이 아니라,
  **멀티에셋 확장을 위한 ETF 메타/분류 체계와 코어 ETF 유니버스(core) 구축**이다.
- ETF는 기존 주식 유니버스와 바로 섞지 않고 별도 유니버스로 관리한다.
- 가격 저장은 기존처럼 `prices_daily` 단일 테이블을 재사용하고,
  자산 구분은 `instrument_master` 또는 `etf_meta` 같은 메타 계층에서 처리한다.

---

## 1) 목적(Objective)
이번 TASK_02에서 반드시 달성해야 할 목표는 아래 5가지다.

1. `universe_etf_master_{asof}.csv`를 입력으로 받아 `universe_etf_core_{asof}.csv`를 생성한다.
2. ETF 분류 메타(자산군, 그룹, 통화노출, 인버스/레버리지 플래그)를 구축한다.
3. 최근 20영업일 평균 거래대금 기준으로 유동성 필터를 적용한다.
4. 자산군별 대표 ETF 바스켓(group coverage)을 확보한다.
5. validate 스크립트로 재현 가능하고 실패 조건이 명확한 파이프라인을 만든다.

---

## 2) P0 원칙 / 제약
아래는 반드시 지켜야 한다.

- 기존 주식 파이프라인을 깨지 말 것
- `prices_daily` 스키마 변경 금지
- ETF는 별도 유니버스로 시작할 것
- S2(펀더멘털 기반) 모델에는 ETF를 섞지 말 것
- 이번 단계에서는 OHLCV 기반 end-to-end만 완성할 것
- 아래 항목은 이번 TASK 범위에서 제외:
  - TR/분배금 반영
  - ETF PDF 구성 수집
  - 레버리지/인버스 정교 자동 분류 고도화
  - 직접 공매도 데이터
  - 선물/옵션 데이터

---

## 3) 입력(Input)
### 필수 입력
1. `data/universe/universe_etf_master_{asof}.csv`
2. `data/db/price.db` 의 `prices_daily`

### 전제
- `prices_daily`에는 TASK_01에서 적재한 ETF 일봉 데이터가 이미 존재한다고 가정한다.
- 거래대금은 `prices_daily.value`를 사용한다.

---

## 4) 산출물(Deliverables)
### 4.1 코어 ETF 유니버스 CSV (필수)
파일:
- `data/universe/universe_etf_core_{asof}.csv`

최소 컬럼:
- `ticker`
- `name`
- `asset_type` = `"ETF"`
- `asset_class`
- `group_key`
- `currency_exposure`
- `is_inverse`
- `is_leveraged`
- `liquidity_20d_value`
- `min_liquidity_pass`
- `asof`

### 4.2 ETF 메타 저장소 (필수, 둘 중 하나)
A안 권장:
- DB 테이블 `etf_meta`
- 또는 `instrument_master` 확장

B안:
- `data/universe/etf_meta_{asof}.csv`

### 4.3 규칙/오버라이드 파일 (필수)
- `data/universe/etf_classification_rules.yml`
- `data/universe/etf_meta_overrides.csv`

### 4.4 검증 스크립트 (필수)
- `scripts/validate_etf_core_universe.py`

---

## 5) 분류 체계(초기 고정)
### 5.1 asset_class
아래 값만 사용한다.
- `equity`
- `bond`
- `cash`
- `fx`
- `commodity`
- `hedge`

### 5.2 group_key
최소 커버리지가 필요한 그룹은 아래와 같다.
- `equity_kr_broad`
- `equity_kr_growth`  # 선택
- `bond_short`
- `bond_long`
- `fx_usd`
- `commodity_gold`
- `hedge_inverse_kr`

### 5.3 추가 메타 필드
아래 필드는 분류 결과에 반드시 포함한다.
- `currency_exposure`
- `is_inverse`
- `is_leveraged`

### 5.4 기본 정책
- 분류는 `rule -> override` 순서로 적용한다.
- override가 있으면 override가 최종 승리한다.
- 레버리지 ETF는 기본적으로 core에서 제외한다.
  - 필요하면 별도 group으로 격리할 수는 있으나 기본 core에는 넣지 않는다.
- 인버스 ETF는 `hedge_inverse_kr` 등 헤지 목적 그룹으로만 제한적으로 허용한다.

---

## 6) 유동성 기준
### 정의
- `liquidity_20d_value = 최근 20영업일 평균 거래대금(value)`

### 규칙
- `MIN_LIQUIDITY_20D` 이상인 종목만 core 후보로 인정한다.
- 최근 20영업일 데이터가 부족하거나 결측이면 core 제외한다.
- 예외 허용은 오직 `etf_meta_overrides.csv`로만 처리한다.
- 룰 자체를 느슨하게 바꾸는 방식은 금지한다.

---

## 7) 코어 선정 로직
입력:
- `universe_etf_master_{asof}.csv`
- `etf_classification_rules.yml`
- `etf_meta_overrides.csv`
- `prices_daily`

선정 절차:
1. master ETF 목록을 로드한다.
2. ETF name 기반 keyword/regex rule로
   - `asset_class`
   - `group_key`
   - `currency_exposure`
   - `is_inverse`
   - `is_leveraged`
   를 1차 부여한다.
3. `etf_meta_overrides.csv`가 있으면 override를 최종 적용한다.
4. `prices_daily.value`를 사용해 ticker별 `liquidity_20d_value`를 계산한다.
5. `MIN_LIQUIDITY_20D` 기준을 통과한 ETF만 core 후보로 남긴다.
6. `group_key`별 후보를 `liquidity_20d_value` 내림차순으로 정렬한다.
7. 각 `group_key`에서 `top_k`만 최종 core에 포함한다.
8. group별 최소 1개 이상이 없으면 validate 단계에서 실패 처리한다.

---

## 8) 구현 작업(Task Breakdown)
아래 파일 단위로 구현한다.

### 8.1 ETF 분류기
파일:
- `src/universe/etf_classifier.py`

역할:
- ETF name 기반 keyword/regex 룰 적용
- `etf_classification_rules.yml` 로드
- `etf_meta_overrides.csv` 적용
- 최종 메타 컬럼 생성

### 8.2 20일 유동성 계산
파일:
- `src/features/calc_liquidity_20d.py`

역할:
- `prices_daily`에서 ticker별 최근 20영업일 평균 거래대금 계산
- 결측/부족 데이터 처리
- threshold 통과 여부 산출

### 8.3 코어 유니버스 생성기
파일:
- `src/collectors/universe/build_universe_etf_core.py`

역할:
- master ETF + 분류 메타 + 유동성 결과를 결합
- `group_key`별 top_k 선정
- `universe_etf_core_{asof}.csv` 생성
- 필요 시 `etf_meta` DB 또는 CSV 저장

### 8.4 검증 스크립트
파일:
- `scripts/validate_etf_core_universe.py`

역할:
- core CSV 존재 확인
- 필수 컬럼 누락 여부 확인
- 메타 누락 확인
- 유동성 기준 통과 여부 확인
- 최소 가격 히스토리 확인
- `group_key` 커버리지 확인
- 실패 시 명확한 에러 메시지 출력

---

## 9) validate 체크 항목
validate는 최소 아래를 확인해야 한다.

1. `universe_etf_core_{asof}.csv`가 생성되었는가
2. 필수 컬럼이 모두 존재하는가
3. `asset_class`, `group_key`, `currency_exposure` 등 메타 누락이 없는가
4. `liquidity_20d_value`와 `min_liquidity_pass`가 정상 계산되었는가
5. 최근 N일 가격 히스토리가 최소 기준 이상 존재하는가
6. 최소 그룹 세트가 모두 커버되는가
   - `equity_kr_broad`
   - `bond_short`
   - `bond_long`
   - `fx_usd`
   - `commodity_gold`
   - `hedge_inverse_kr`
   - `equity_kr_growth`는 선택
7. 기존 주식 파이프라인에 회귀 문제가 없는가

---

## 10) 완료 기준(Definition of Done)
아래 조건을 모두 만족하면 완료다.

1. `universe_etf_core_{asof}.csv`가 생성된다.
2. ETF 메타 저장소(DB 또는 CSV)가 생성된다.
3. 분류 규칙 파일과 override 파일이 생성된다.
4. 20일 평균 거래대금 기준 필터가 동작한다.
5. group coverage가 충족된다.
6. `validate_etf_core_universe.py`가 통과한다.
7. 기존 주식 파이프라인과 `prices_daily` 스키마에 영향이 없다.

---

## 11) 이번 TASK에서 하지 않을 것
- TR/분배금 반영
- ETF PDF 구성 수집
- 정교한 ETF taxonomy 고도화
- 직접 공매도 로직
- ETF 자산배분 백테스트
- 국면 Router 연결
- S4/S5/S6 모델 구현

---

## 12) 다음 TASK 연결
TASK_02 완료 후 다음은 아래 순서로 간다.

- TASK_03: 멀티에셋 데이터 모델 고정
  - `asset_type`
  - `instrument_master / etf_meta`
  - 필터링 표준화
- TASK_04: ETF 자산배분 레이어 백테스트 엔진
- 이후: S4 / S5 / S6 신규 모델 + 국면 Router 연결