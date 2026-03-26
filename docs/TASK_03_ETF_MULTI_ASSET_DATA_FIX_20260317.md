# TASK 03. 멀티에셋 데이터 모델 고정
## (asset_type / instrument_master / etf_meta 표준화)

## 1. 작업 목적
TASK 03의 목적은 ETF 자산배분 백테스트를 바로 구현하는 것이 아니라,
그 전에 반드시 필요한 멀티에셋 공통 데이터 모델과 조회 규약을 고정하는 것이다.

즉, 주식과 ETF를 하나의 시스템 안에서 함께 다룰 수 있도록
공통 식별체계, 메타 저장 구조, 조회/필터 표준을 먼저 정리하는 단계다.

---

## 2. 작업 배경
- TASK 01에서 ETF 마스터 유니버스 생성, ETF 일봉 OHLCV 수집, `prices_daily` 적재, 최소 validate가 완료되었다.
- TASK 02에서 ETF 분류(rule + override), 코어 ETF 유니버스(core), ETF 메타(asset_class, group_key, currency_exposure, inverse/leverage, liquidity)가 구축되었다.
- 이제 다음 단계로 넘어가기 전에, 주식과 ETF를 공통적으로 식별하고 조회할 수 있는 멀티에셋 데이터 모델을 고정해야 한다.
- 이 작업이 완료되어야 TASK 04에서 ETF 자산배분 레이어 백테스트를 안정적으로 구현할 수 있다.

---

## 3. 핵심 원칙
1. `prices_daily` 스키마는 변경하지 않는다.
2. 자산 구분은 가격 테이블이 아니라 메타 계층에서 처리한다.
3. ETF는 여전히 주식 유니버스와 분리 관리하되, 공통 메타 모델에서는 함께 식별 가능해야 한다.
4. S2(펀더멘털 기반) 모델에는 ETF를 섞지 않는다.
5. 기존 주식 파이프라인을 깨지 않는다.
6. 이번 단계에서는 데이터 모델, 조회, 검증까지만 수행한다.
7. 자산배분 백테스트 로직은 다음 TASK로 넘긴다.

---

## 4. 작업 목표
이번 TASK 03의 목표는 아래와 같다.

1. 공통 자산 식별 메타 모델을 확정한다.
2. `asset_type` 기준으로 주식과 ETF를 일관되게 구분할 수 있게 한다.
3. `instrument_master`와 `etf_meta`의 역할을 명확히 분리한다.
4. 메타 upsert 로직을 구현한다.
5. 공통 조회/필터 함수 또는 repository 계층을 만든다.
6. validate 스크립트로 정합성을 검증한다.
7. TASK 04 자산배분 백테스트 입력 기반을 마련한다.

---

## 5. 설계 대상

### 5.1 공통 식별 필드
모든 자산은 최소 아래 식별 필드를 갖는다.

- `ticker`
- `name`
- `asset_type`
- `market`
- `is_active`
- `asof`

### 5.2 instrument_master
전체 자산의 공통 마스터 역할을 한다.

최소 컬럼:
- `ticker`
- `name`
- `asset_type`
- `market`
- `is_active`
- `first_seen`
- `last_seen`
- `asof`
- `source`

역할:
- STOCK / ETF 공통 식별
- 가격 테이블과 별개로 자산 정체성 관리
- 전략/유니버스/필터링의 1차 참조 마스터

### 5.3 etf_meta
ETF 전용 확장 메타 역할을 한다.

최소 컬럼:
- `ticker`
- `asset_class`
- `group_key`
- `currency_exposure`
- `is_inverse`
- `is_leveraged`
- `core_eligible`
- `liquidity_20d_value`
- `asof`
- `meta_source`
- `rule_version`

역할:
- ETF 전용 분류/속성 저장
- TASK 02 분류 결과 구조적 저장
- 향후 자산배분, 리스크오프, 헤지 바스켓 구성에 사용

---

## 6. 구현 범위

### 6.1 공통 메타 스키마 확정
권장 구조:
- `instrument_master`
- `etf_meta`

### 6.2 메타 upsert 로직 구현
- TASK 01의 ETF master 입력을 `instrument_master`에 upsert
- TASK 02의 ETF core/meta 결과를 `etf_meta`에 upsert
- 기존 주식 종목도 가능한 범위에서 `instrument_master`와 정합 유지

### 6.3 공통 조회/필터 함수 구현
예시:
- `get_instruments(asset_type=None, active_only=True)`
- `get_etf_core_universe(asof=None, group_key=None)`
- `get_price_universe(asset_type=None, tickers=None, start=None, end=None)`
- `filter_instruments_by_asset_class(...)`
- `filter_etf_by_group(...)`

### 6.4 멀티에셋 입력 표준 정의
향후 백테스트 엔진 입력에 사용할 표준 컬럼 세트를 정리한다.

최소 표준:
- `date`
- `ticker`
- `name`
- `asset_type`
- `market`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `value`

ETF 추가 메타:
- `asset_class`
- `group_key`
- `currency_exposure`
- `is_inverse`
- `is_leveraged`

### 6.5 validate 스크립트 구현
검증 항목:
- `instrument_master` 필수 컬럼 존재 여부
- ETF가 `asset_type="ETF"`로 정상 등록되었는지
- `etf_meta`와 `instrument_master`가 ticker 기준으로 정합한지
- `prices_daily`와 메타가 조인 가능한지
- 코어 ETF가 공통 조회 함수에서 정상 반환되는지
- 기존 주식 종목 조회가 깨지지 않았는지

---

## 7. 권장 구현 파일
- `src/metadata/instrument_master.py`
- `src/metadata/etf_meta_store.py`
- `src/repositories/instrument_repository.py`
- `src/repositories/price_repository.py`
- `src/utils/asset_filters.py`
- `scripts/validate_multiasset_model.py`

실제 프로젝트 구조에 따라 파일명은 조정 가능하되, 역할 분리는 유지한다.

---

## 8. 산출물
### 필수 산출물
1. `instrument_master` 저장 구조
2. `etf_meta` 저장 구조
3. 메타 upsert 로직
4. 공통 조회/필터 함수
5. `validate_multiasset_model.py`

### 선택 산출물
6. 메타 export CSV
- `instrument_master_{asof}.csv`
- `etf_meta_{asof}.csv`

---

## 9. 완료 기준 (Definition of Done)
아래를 모두 만족하면 완료로 본다.

1. ETF와 주식이 공통 메타 모델에서 식별된다.
2. `asset_type` 기준 필터링이 정상 동작한다.
3. ETF 전용 메타가 구조적으로 저장된다.
4. `prices_daily`와 메타를 조합한 멀티에셋 조회가 가능하다.
5. 기존 주식 파이프라인 회귀가 없다.
6. validate 스크립트가 통과한다.
7. TASK 04 자산배분 백테스트 입력 기반이 마련된다.

---

## 10. 이번 TASK에서 하지 않을 것
- ETF 자산배분 백테스트 로직
- 국면별 포트폴리오 규칙 엔진
- S4 / S5 / S6 모델 구현
- TR/분배금 반영
- ETF PDF 구성 수집
- 실시간 시세 처리
- 리포트 UI 작업

---

## 11. 다음 TASK
- TASK 04: ETF 자산배분 레이어 백테스트 엔진
  - 국면별 ETF 바스켓 사용
  - 방어 자산/헤지 자산 포함
  - 단순 규칙 기반 리스크온/리스크오프 배분부터 시작