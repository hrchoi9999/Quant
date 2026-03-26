# Quant 투자 시스템 개발 진행상황 (2026-02-05)

> 목적: `rebuild_mix_universe_and_refresh_dbs.py` **한 번 실행으로**  
> 1) 유니버스 CSV 생성/갱신, 2) `price.db` 백필(backfill), 3) `regime.db` 생성/갱신, 4) `fundamentals.db` 월단위 테이블 생성/갱신, 5) `*_latest.csv` 별칭 갱신까지 **일괄 수행**하도록 파이프라인을 정리/패치했습니다.

---

## 1. 오늘 실행 결과 점검 (사용자 로그 기준)

### 1) 유니버스 생성
- KOSPI Top200 / KOSDAQ Top200 생성: 정상
  - `universe_top200_kospi_20260205.csv (n=200)`
  - `universe_top200_kosdaq_20260205.csv (n=200)`
- Mix 400 생성: 정상
  - `universe_mix_top400_20260205.csv (rows=400)`

### 2) price.db 업데이트(백필)
- `missing_end=0 (tail=0 + new=0)`  
  → **오늘(2026-02-05) 기준으로 유니버스 400개 모두 가격 DB에 꼬리결측이 없음**(정상)
- `priceready`도 원본과 동일하게 복사됨(정상)
  - `universe_mix_top400_20260205_priceready.csv`

### 3) regime.db 생성/갱신
- `src.regime.build_regime_history` 실행 성공
- `verify_no_blob: PASSED`
- 총 upsert ~ 2,186,245 rows (정상)

### 4) fundamentals 월단위 생성/갱신
- `fs_annual 누락 tickers=27` → fundready에서 제외(정상 동작)
- `fundamentals_end snapped: 2026-02-05 -> 2026-01-31`  
  → **월말 스냅 적용이 정상적으로 동작**
- 다만 아래 메시지가 중요:
  - `out_table exists. max(date)=2026-02-05 (incremental enabled)`
  - `--end 2026-01-31`로 실행했는데 테이블의 max(date)가 2026-02-05로 이미 더 큼
  - 그 결과 `no month_end_dates to process`로 종료

✅ 결론: **전체 파이프라인은 실패 없이 끝까지 정상 실행**되었습니다.  
⚠️ 단, **fundamentals 테이블에 2026-02-05 같은 “월말이 아닌 날짜”가 이미 들어가 있는 상태**라서, 이번 실행에서는 월말 스냅(end=2026-01-31) 기준으로 추가 작업이 “없음”으로 판단된 상황입니다. (데이터 정합성 이슈로 별도 정리 필요)

### 5) latest 별칭 파일 생성/갱신
- 다음 파일들이 생성/갱신됨(정상):
  - `universe_top200_kospi_latest.csv`
  - `universe_top200_kosdaq_latest.csv`
  - `universe_mix_top400_latest.csv`
  - `universe_mix_top400_latest_priceready.csv`
  - `universe_mix_top400_latest_fundready.csv`
- `Final universe used`가 **fundready로 출력됨**(요구사항 반영 완료)

---

## 2. 오늘 처리한 핵심 작업들(요약)

### A. 유니버스 생성 구조를 “200+200=400”으로 고정
- KOSPI 200 + KOSDAQ 200 → Mix 400
- 날짜가 파일명에 포함되더라도, `--update-latest`로 “latest 별칭”을 생성하여 **백테스트/파이프라인에서 날짜를 고정하지 않아도 되게** 구성

### B. price.db 백필 정책 확정 (중복 다운로드 최소화)
- **신규 종목(기존 rows=0): 전체 구간 다운로드**
- **기존 종목: 꼬리결측(tail missing)만 최근 N일(기본 7일) 백필**
- “중간 결측”은 이번 범위에서 제외(월/분기 주기로 별도 도구로 처리)

### C. regime.db를 파이프라인에 포함
- 파이프라인에서 `python -m src.regime.build_regime_history ...` 호출
- 기존 regime_history 스키마가 구버전일 때 발생했던
  `no column named ret` 문제를 피하기 위해 **스키마 보강(ALTER TABLE)** 로직을 추가

### D. fundamentals 월단위 생성도 파이프라인에 포함 (단, DART 수집은 제외)
- DART API로 직접 수집하는 게 아니라 **로컬 `dart_main.db`를 읽어** 월단위 feature 테이블 생성
- `fs_annual`에 없는 티커는 fundready에서 자동 제외

---

## 3. 현재 파이프라인/백테스트에서 “알고 있어야 할 파일들”

### 3.1 파이프라인(핵심)
- **`D:\Quant\src\pipelines\rebuild_mix_universe_and_refresh_dbs.py`**
  - “한 번 실행”으로 아래를 수행:
    1) 유니버스 생성(KOSPI/KOSDAQ topN + mix)
    2) price 백필 + priceready 생성
    3) regime_history 생성/갱신(regime.db)
    4) fundready 생성 + fundamentals_monthly 테이블 갱신(fundamentals.db)
    5) `*_latest.csv` 별칭 갱신

### 3.2 유니버스 생성기
- `src/collectors/universe/build_universe_krx.py`
  - market(KOSPI/KOSDAQ)별 마스터/TopN CSV 생성
- `src/collectors/universe/build_universe_mix_200_200.py`
  - KOSPI topN + KOSDAQ topN을 합쳐 mix CSV 생성(400)

### 3.3 가격 백필
- `src/collectors/price/price_backfill.py`
  - `--tickers`, `--start`, `--end`로 지정 구간 가격을 DB에 upsert

### 3.4 레짐 생성
- `src/regime/build_regime_history.py` (모듈 실행: `python -m src.regime.build_regime_history`)
  - `price.db(prices_daily)`와 `universe(priceready)`를 읽어
  - `regime.db(regime_history)`를 생성/갱신

### 3.5 펀더멘털 월단위 생성
- `src/fundamentals/build_fundamentals_monthly.py`
  - `dart_main.db`(fs_annual 등) + `price.db`를 읽어
  - `fundamentals.db`에 월단위 테이블 생성/갱신

### 3.6 백테스트(수정 예정)
- 현재: `run_backtest_regime_s2_v3.py`
- 앞으로: **`run_backtest_regime_s2_v4.py`로 신규 생성/수정 예정**
  - 목표: “latest 별칭”을 기본 사용(파일명 날짜 의존 제거)
  - 추천: 유니버스는 `universe_mix_top400_latest_fundready.csv` 사용(일관성)

---

## 4. 파일 간 상관관계(데이터 플로우)

1) **유니버스 생성**
   - build_universe_krx.py → top200 csv (KOSPI/KOSDAQ)
   - build_universe_mix_200_200.py → mix400 csv

2) **가격 DB 최신화**
   - price_backfill.py → price.db(prices_daily)
   - priceready csv 생성(가격 tail 결측 제거)

3) **레짐 DB 생성**
   - build_regime_history.py
   - 입력: price.db + priceready universe
   - 출력: regime.db(regime_history)

4) **펀더멘털 DB 생성**
   - build_fundamentals_monthly.py
   - 입력: dart_main.db + price.db + fundready universe
   - 출력: fundamentals.db(fundamentals_monthly_mix400_YYYYMMDD)

5) **백테스트**
   - (예정) run_backtest_regime_s2_v4.py
   - 입력: price.db + regime.db + fundamentals.db + latest_fundready universe

---

## 5. 남아있는 이슈 / 다음 해야 할 작업(중요도 순)

### (1) fundamentals 테이블 날짜 정합성(월말 스냅과 충돌)
현재 실행 로그에서:
- 파이프라인은 `--end 2026-01-31`로 스냅해서 전달했는데
- 기존 테이블의 `max(date)=2026-02-05`로 더 큼 → “할 작업 없음”으로 종료

**의미**
- 과거 실행에서 `fundamentals_monthly_mix400_20260205` 테이블에
  “월말이 아닌 날짜(2026-02-05)” 행이 들어갔을 가능성이 큼

**내일 할 일(권장)**
- 선택지 A(안전/명확): 매일 테이블을 새로 만들기(테이블명 날짜 포함 유지) + 최신 테이블만 백테스트가 사용
- 선택지 B(정합성 유지): 해당 테이블에서 “월말이 아닌 날짜”를 제거하거나, 월말만 남기도록 정리 후 incremental 유지
- 선택지 C(운영 편의): `fundamentals_monthly_mix400_latest` 같은 고정 테이블로 만들고, 내부는 월말만 유지

> 다음 대화에서, 위 선택지 중 하나로 고정하고 파이프라인/백테스트를 통일하는 게 좋습니다.

### (2) 백테스트 파일 v4로 정리
- `run_backtest_regime_s2_v4.py`를 만들고 아래를 반영
  - 유니버스: `universe_mix_top400_latest_fundready.csv`
  - regime DB: `regime.db::regime_history` (또는 스크립트 인자 표준화)
  - fundamentals: **월말 데이터만 사용하도록 end/date 처리 방식 명확화**
  - “end/asof 자동설정”은 파이프라인이 최신화 해주는 구조로 단순화(백테스트는 latest를 그냥 사용)

### (3) “시장 미마감/데이터 미반영” 안전장치
- 오늘은 last_available_date가 2026-02-05로 잡혔지만,
  장중에는 데이터 소스에 따라 **당일 데이터가 비어 있을 수 있음**
- 이미 파이프라인에서 `effective_end=min(price_target_end, price_db_max_after)`로 안전장치 개념이 들어가 있으나,
  향후 “당일 데이터가 불완전”한 소스에서의 안정성을 위해
  - `last_available_date` 함수(도구)와
  - `price_db_max_after`를 조합하는 방식으로 더 강하게 만들 여지가 있음

---

## 6. 오늘 사용한 대표 실행 명령(재현용)

### 6.1 파이프라인(최종)
```powershell
(venv64) PS D:\Quant\src\pipelines> python .\rebuild_mix_universe_and_refresh_dbs.py --update-latest
```

### 6.2 DB 상태 확인(파이썬 원라이너 예시)
```powershell
python -c "import sqlite3,pandas as pd; con=sqlite3.connect(r'D:\Quant\data\db\price.db'); print(pd.read_sql_query('select min(date) mn, max(date) mx, count(*) rows from prices_daily', con).to_string(index=False))"
python -c "import sqlite3,pandas as pd; con=sqlite3.connect(r'D:\Quant\data\db\regime.db'); print(pd.read_sql_query('select min(date) mn, max(date) mx, count(distinct ticker) tickers, count(*) rows from regime_history', con).to_string(index=False))"
python -c "import sqlite3,pandas as pd; con=sqlite3.connect(r'D:\Quant\data\db\fundamentals.db'); print(pd.read_sql_query('select min(date) mn, max(date) mx, count(distinct ticker) tickers, count(*) rows from fundamentals_monthly_mix400_20260205', con).to_string(index=False))"
```

---

## 7. 내일 새 대화창에서 바로 이어갈 “To-Do 체크리스트”

1) **fundamentals 테이블 정합성 확정**
   - 테이블에 들어간 “비월말(예: 2026-02-05)” 행의 존재/원인 확인
   - 운영 정책(A/B/C) 중 1개를 고정
   - 파이프라인/백테스트가 동일 정책을 따르게 수정

2) **`run_backtest_regime_s2_v4.py` 생성/정리**
   - 기본 입력을 latest 별칭 파일/DB로 고정
   - 월단위/주단위 백테스트 비교를 위한 출력 포맷(표)도 고려

3) (선택) “당일 장중 실행 안전장치” 강화
   - price_end 산정 로직을 더 엄격히(데이터 미마감 시 자동으로 전일로 떨어지게)

---

## 8. 결론(오늘 상태)

- **유니버스/가격/레짐**: 최신화가 정상적으로 이루어졌고, `*_latest.csv`도 정상 생성되었습니다.
- **펀더멘털**: 월말 스냅 로직은 정상 적용되었으나, 기존 테이블의 max(date)가 더 커서 “이번 실행에서 갱신할 것이 없음”으로 판단된 상태입니다.  
  → **내일은 fundamentals 테이블 날짜 정합성(월말만 유지) 정책을 확정하고 정리하는 것이 최우선**입니다.
