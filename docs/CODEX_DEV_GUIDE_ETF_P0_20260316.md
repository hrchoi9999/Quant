# CODEX_DEV_GUIDE_ETF_P0 (ETF 반영 P0 개발 기본방향)

## 0) 목적
주식 전용 퀀트 시스템을 깨지 않고, ETF를 시스템에 반영하기 위한 P0(최소 기능) 데이터 기반을 구축한다.

P0 범위의 최종 목표는 다음 3가지다.
1) ETF 마스터 유니버스(CSV) 생성
2) ETF 일봉 OHLCV 수집
3) 기존 price DB에 적재(주식과 동일 파이프라인에서 재사용 가능하게)

※ P0에서는 분배금/TR, ETF 구성(PDF), 레버리지/인버스 자동분류, 선물/옵션/공매도 데이터는 제외한다.

---

## 1) 핵심 원칙(반드시 준수)
1) 기존 주식 유니버스/가격DB/백테스트 시스템은 최대한 수정하지 않는다(회귀 리스크 최소화).
2) ETF는 “주식 유니버스에 섞어서 시작”하지 않는다.
   - ETF는 별도 유니버스 파일로 시작하고, 멀티에셋 결합은 추후 단계에서 한다.
3) 가격 DB는 가능하면 단일 테이블(prices_daily)에 통합 적재한다.
   - 주식/ETF 구분은 별도 메타(instrument_master)에서 해결한다.
4) 펀더멘털 기반 종목선정(S2 등)에 ETF를 섞지 않는다.
   - ETF는 “자산배분/헤지 모델” 또는 “멀티에셋 레이어”에서 사용한다.
5) P0는 “end-to-end 파이프라인이 돌고 검증되는 상태”가 KPI다.

---

## 2) 데이터 소스(고정)
- PyKRX ETF API 사용(일봉 OHLCV)
- 날짜 포맷 표준:
  - asof: YYYYMMDD (예: 20260311)
  - start/end: YYYY-MM-DD 또는 YYYYMMDD 중 택1(프로젝트 컨벤션에 맞춰 고정)

---

## 3) 디렉토리/파일 규약(권장)
- 유니버스 출력:
  - data/universe/universe_etf_master_{asof}.csv
- 수집 스크립트:
  - src/collectors/universe/build_universe_etf_krx.py
  - src/collectors/prices/fetch_etf_prices_daily.py
- 검증 스크립트:
  - scripts/validate_etf_pipeline.py
- (선택) 메타 DB:
  - data/db/instruments.db 또는 기존 DB에 테이블 추가

---

## 4) DB 설계(P0 권장안)
### 4.1 instrument_master(메타)
- 목적: 주식/ETF 구분 및 기본 속성 관리
- 테이블: instrument_master
  - ticker TEXT PRIMARY KEY
  - name TEXT
  - asset_type TEXT  ("STOCK"|"ETF")
  - is_active INTEGER
  - updated_at TEXT

### 4.2 prices_daily(기존 테이블 재사용 권장)
- date, ticker, open, high, low, close, volume, value
- ETF도 동일 컬럼으로 적재한다.
- NAV/기초지수 컬럼은 P0에서 강제하지 않는다.
  - 필요 시 P1에서 etf_extra_daily 같은 별도 테이블로 추가한다.

---

## 5) 실행 흐름(End-to-End)
1) build_universe_etf_krx.py
   - asof 기준 ETF tickers + name 수집
   - universe_etf_master_{asof}.csv 생성
   - (선택) instrument_master upsert

2) fetch_etf_prices_daily.py
   - ETF 유니버스 CSV 로드
   - start/end 구간 일봉 수집
   - prices_daily upsert 적재
   - 휴장일/빈 DF 방어
   - 호출 속도 제한(sleep) 적용

3) validate_etf_pipeline.py
   - ETF 유니버스 생성 확인(티커 수 > 0)
   - prices_daily에 ETF 데이터 적재 확인
   - (date,ticker) 중복키 없음 확인
   - 날짜 범위(min/max) 확인

---

## 6) 금지사항(중요)
- 분배금/TR 반영(후순위)
- ETF 구성(PDF) 수집(후순위)
- 레버리지/인버스 자동분류(후순위)
- 기존 주식 파이프라인을 깨는 스키마 변경(특히 prices_daily 컬럼 변경은 신중)

---

## 7) Done(완료 기준)
- universe_etf_master_{asof}.csv 생성 완료
- 지정 기간 ETF 일봉이 prices_daily에 적재 완료
- validate 스크립트 통과
- 기존 주식 수집/백테스트가 깨지지 않음(최소 회귀 확인)

---

## 8) 다음 단계(TASK_02 예고)
- ETF “코어 리스트” 선정(유동성/중복노출/자산군)
- ETF 분류(category/inverse/leveraged) 부여(수동→반자동)
- 멀티에셋 레이어(국면별 자산배분) 백테스트 프레임워크 추가