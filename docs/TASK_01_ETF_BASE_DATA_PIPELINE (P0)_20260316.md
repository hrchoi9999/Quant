# TASK_01_ETF_BASE_DATA_PIPELINE (P0)

## 0) 배경/목표
현재 시스템은 주식(개별 종목) 중심으로 유니버스/가격DB/백테스트가 구성되어 있습니다.
추가 모델 개발(국면별 멀티에셋 포트폴리오)을 위해, ETF를 시스템에 반영할 **기본 데이터 기반**을 구축합니다.

P0 목표:
1) ETF 티커 마스터 유니버스 생성
2) ETF 일봉 OHLCV(+가능하면 NAV) 수집
3) price DB에 적재(주식과 동일 테이블 권장)
4) 최소 검증(누락/중복/휴장일 처리)

※ P0에서는 배당/분배금(TR), ETF 구성(PDF) 기반 노출 관리, 레버리지/인버스 분류 자동화는 후순위.

---

## 1) 범위(Scope)

### 포함(In-scope)
- ETF 유니버스 빌드 스크립트(상장 ETF 전체)
- ETF 가격(일봉) 수집 스크립트
- DB 스키마(메타 테이블 추가 또는 CSV 메타) 설계/구현
- upsert 기반 적재(중복 방지)
- 최소 검증 스크립트(행 수, 날짜 범위, 결측)

### 제외(Out-of-scope)
- 분배금/배당 TR 반영
- ETF 포트폴리오(PDF) 구성/비중 수집(추후 TASK)
- 인버스/레버리지 자동 판별(초기는 수동/룰 기반으로 별도 TASK)
- 공매도/선물/옵션 데이터

---

## 2) 데이터 소스/함수(고정)
PyKRX ETF API 사용을 기본으로 한다.
- stock.get_etf_ticker_list(YYYYMMDD)
- stock.get_etf_ticker_name(ticker)
- stock.get_etf_ohlcv_by_date(start, end, ticker)
- (옵션) stock.get_etf_ohlcv_by_ticker(YYYYMMDD)  # NAV 포함

날짜 포맷은 "YYYYMMDD"로 통일한다.

---

## 3) 산출물(Deliverables)

### 3.1 유니버스 파일
- data/universe/universe_etf_master_{asof}.csv
  - 컬럼(최소):
    - ticker (6자리 str)
    - name
    - asset_type = "ETF"
    - asof (YYYYMMDD)
    - is_active (1)
  - 컬럼(옵션/추후):
    - category (index/bond/commodity/fx/sector/inverse/leveraged 등)
    - is_inverse (0/1)
    - is_leveraged (0/1)

### 3.2 메타 DB(권장)
- data/db/instruments.db 또는 기존 DB에 테이블 추가(선택)
- 테이블: instrument_master
  - ticker TEXT PRIMARY KEY
  - name TEXT
  - asset_type TEXT  ("STOCK"|"ETF")
  - is_active INTEGER
  - list_date TEXT (옵션)
  - delist_date TEXT (옵션)
  - updated_at TEXT

※ 기존 prices_daily 테이블을 유지하고, 자산구분은 instrument_master로 처리하는 것을 권장.

### 3.3 ETF 가격 적재
- 대상 DB: data/db/price.db
- 대상 테이블: prices_daily (권장, 기존 주식 테이블과 동일)
- 최소 컬럼 가정:
  - date, ticker, open, high, low, close, volume, value
- ETF에서 NAV/기초지수 컬럼이 나오면:
  - 옵션 A: 별도 테이블 etf_extra_daily(date,ticker,nav,base_index)로 저장
  - 옵션 B: prices_daily에 nav/base_index 컬럼 추가(기존 코드 영향 있으므로 신중)

P0 권장: A(분리) 또는 우선 nav는 저장하지 않고 진행.

---

## 4) 구현 작업(Task Breakdown)

### 4.1 ETF 유니버스 빌더
- 스크립트: src/collectors/universe/build_universe_etf_krx.py
- 입력: asof(YYYYMMDD)
- 출력: universe_etf_master_{asof}.csv
- 동작:
  1) get_etf_ticker_list(asof)로 티커 수집
  2) 각 ticker에 대해 get_etf_ticker_name()으로 name 매핑
  3) CSV 저장
  4) instrument_master upsert(있으면)

### 4.2 ETF 가격 수집기(일봉)
- 스크립트: src/collectors/prices/fetch_etf_prices_daily.py
- 입력: start/end(YYYY-MM-DD 또는 YYYYMMDD), universe_etf_master CSV 경로
- 동작:
  1) ETF tickers 로드
  2) 각 ticker에 대해 get_etf_ohlcv_by_date(start, end, ticker) 호출
  3) 표준 컬럼으로 매핑 후 prices_daily upsert
  4) 휴장일/빈 DF 처리(스킵)
  5) 호출 속도 제한(예: sleep) 적용

### 4.3 검증 스크립트
- scripts/validate_etf_pipeline.py (또는 pytest)
- 검증 항목:
  - ETF universe ticker count > 0
  - price.db에 ETF ticker가 실제로 적재되었는지
  - 특정 기간에서 date 연속성(영업일 기준) 확인
  - 중복키(date,ticker) 없음

---

## 5) 완료 기준(Definition of Done)
- universe_etf_master_{asof}.csv 생성됨
- instrument_master(선택) 갱신됨
- 지정 기간 ETF 일봉이 prices_daily에 적재됨(주식과 동일 테이블이면 가장 좋음)
- validate 스크립트/테스트가 통과함
- 기존 주식 파이프라인이 깨지지 않음(회귀 테스트 최소 1개)

---

## 6) PR 분해(권장)
1) PR1: ETF 유니버스 빌더 + (선택) instrument_master
2) PR2: ETF 가격 수집/DB upsert + 최소 속도 제한
3) PR3: validate 스크립트 + 문서(RUNBOOK 업데이트)

---

## 7) Codex 작업지시(복붙용)