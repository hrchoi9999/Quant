# Quant 프로젝트 진행상태 요약 (2026-02-02)

## 1) 현재 상황 요약
- 목표: **KOSPI Top187 + KOSDAQ Top200 → MixTop400 유니버스 구성** 후,  
  **가격(price.db) + DART(fs_annual) + fundamentals_monthly**를 파이프라인으로 한 번에 갱신.
- 파이프라인 스크립트:
  - `D:\Quant\src\pipelines\rebuild_mix_universe_and_refresh_dbs.py`

## 2) 유니버스 생성 결과
### KOSDAQ Top200 생성
- 실행:
  - `python D:\Quant\src\utils\build_universe_kosdaq_top100.py --date 2026-01-29 --topn 200 --out D:\Quant\data\universe\universe_top200_kosdaq_20260129.csv`
- 결과:
  - `universe_top200_kosdaq_20260129.csv` (rows=200)

### MixTop400 생성 (실제 387개)
- 실행:
  - `python D:\Quant\src\utils\build_universe_mix_top250.py --kospi-file D:\Quant\data\universe\universe_top200_kospi_20260127_fund187.csv --kosdaq-file D:\Quant\data\universe\universe_top200_kosdaq_20260129.csv --ticker-col ticker --target-size 400 --out-file D:\Quant\data\universe\universe_mix_top400_20260129.csv`
- 결과:
  - Mix는 **KOSPI 187 + KOSDAQ 200 = 387개**로 상한(availability limit) 때문에 400을 못 채움.
  - `universe_mix_top400_20260129.csv` (rows=387)

## 3) 가격 DB 갱신 (price.db)
- 파이프라인이 `2026-01-29` 기준으로 가격 미존재 티커를 점검함.
- 누락 종목:
  - `000090` 이 `2026-01-29` 종가가 없음 → `price_backfill.py`로 백필 시도했으나 저장 0건.
- 처리:
  - priceready 유니버스에서 `000090` 자동 제외됨.
- 결과 파일:
  - `universe_mix_top400_20260129_priceready.csv` (before=387 → after=386)

## 4) DART(fs_annual) 갱신
### 매핑 누락 4개
- `dim_corp_listed` 매핑 누락 tickers=4
  - `476830, 478340, 490470, 491000`
- 처리:
  - 파이프라인이 **dartready 유니버스를 KOSDAQ만 추려서** 195개로 축소:
    - `universe_mix_top400_20260129_dartready.csv` (before=386 → after=195)

### DART 수집 결과가 "saved=0, skipped=1950"인 의미
- 실행 로그:
  - `universe_rows=195 ... only_missing=True`
  - `[DONE] done=0 saved=0 skipped=1950 fail=0`
- 의미:
  - **195개 티커 × 10개 연도(2015~2024) = 1950건**을 처리 대상으로 보는데,
  - 이미 DB(`dart_main.db::fs_annual`)에 있어서 **추가로 저장할 것이 없어서 전부 skipped** 된 것입니다.
  - 즉, **실패가 아니라 “이미 채워져 있어서 할 게 없었다”** 입니다.

## 5) fundamentals_monthly 생성
- fundready 유니버스 생성:
  - `fs_annual 누락 4개(위 매핑 누락 4개)`는 fundamentals 단계에서도 제외됨
  - `universe_mix_top400_20260129_fundready.csv` (before=386 → after=382)

- 실행:
  - `python D:\Quant\src\fundamentals\build_fundamentals_monthly.py --dart-db D:\Quant\data\db\dart_main.db --universe-file D:\Quant\data\universe\universe_mix_top400_20260129_fundready.csv --ticker-col ticker --price-db D:\Quant\data\db\price.db --price-table prices_daily --start 2017-02-08 --end 2026-01-29 --out-db D:\Quant\data\db\fundamentals.db --out-table fundamentals_monthly_mix400_20260129`
- 결과:
  - `fundamentals.db::fundamentals_monthly_mix400_20260129`
  - `tickers=382`, `monthly rows=37,177`, dates=2017-02-28..2026-01-29

## 6) 지금 발생한 “에러”의 본질
### (A) DART_API_KEY가 PowerShell 세션에 안 잡힘
- 확인 결과:
  - Python에서 `os.getenv('DART_API_KEY')`는 MISSING
  - PowerShell에서는 User 환경변수에 저장되어 있음:
    - `[Environment]::GetEnvironmentVariable("DART_API_KEY","User")` → 값 출력됨
- 이유:
  - `setx`는 **레지스트리에 저장만** 하고, **현재 열린 PowerShell/VSCode 터미널 세션에는 즉시 반영되지 않습니다.**
- 해결(둘 중 하나):
  1) **터미널(또는 VSCode) 재시작**
  2) 현재 세션에만 즉시 주입:
     - `$env:DART_API_KEY = [Environment]::GetEnvironmentVariable("DART_API_KEY","User")`

### (B) python -c에서 따옴표 깨짐(SyntaxError)
- 증상:
  - `sqlite3.connect(rD:\Quant\...)` 처럼 문자열 따옴표가 사라진 상태로 Python에 전달되어 SyntaxError
- 해결:
  - PowerShell에서는 **바깥을 큰따옴표(")로**, 경로/SQL은 **작은따옴표(')** 로 통일하는 방식이 가장 안전합니다.

## 7) 검증용 1줄 명령 (PowerShell 안전 버전)
### 7.1 DART_API_KEY 확인
- `python -c "import os; print('DART_API_KEY=', 'SET' if os.getenv('DART_API_KEY') else 'MISSING')"`

### 7.2 fs_annual 커버리지 확인
- `python -c "import sqlite3,pandas as pd; c=sqlite3.connect(r'D:\\Quant\\data\\db\\dart_main.db'); q='select min(bsns_year) min_y, max(bsns_year) max_y, count(*) rows, count(distinct stock_code) tickers from fs_annual where bsns_year between 2015 and 2024'; print(pd.read_sql_query(q,c).to_string(index=False))"`

### 7.3 fundamentals_monthly_mix400_20260129 범위 확인
- `python -c "import sqlite3,pandas as pd; c=sqlite3.connect(r'D:\\Quant\\data\\db\\fundamentals.db'); q='select min(date) min_d, max(date) max_d, count(*) rows, count(distinct ticker) tickers from fundamentals_monthly_mix400_20260129'; print(pd.read_sql_query(q,c).to_string(index=False))"`

## 8) 파이프라인에 반영된 “4개 종목” 처리 정책
- `476830, 478340, 490470, 491000`은 `dart_main.db`의 `dim_corp_listed`에 매핑이 없어 DART 수집 불가
- 파이프라인은 이 4개를:
  - dartready 단계에서 제외
  - fundready 단계에서도 제외
- 따라서 MixTop400(386 priceready) 대비:
  - DART 단계는 KOSDAQ 195개만 수행
  - fundamentals 단계는 382개로 수행

## 9) 다음 실행(권장)
1) 터미널 재시작 또는 세션 주입:
   - `$env:DART_API_KEY = [Environment]::GetEnvironmentVariable("DART_API_KEY","User")`
2) 파이프라인 재실행:
   - `python .\src\pipelines\rebuild_mix_universe_and_refresh_dbs.py --asof 2026-01-29 --kosdaq-topn 200 --mix-size 400 --dart-enable --fund-enable`

---

## 10) 추가 확인 결과 (사용자 최종 확인 로그 반영)
아래 3개 확인 명령이 **정상 동작**했고, 핵심 지표가 기대 범위로 나왔습니다.

### 10.1 DART_API_KEY: SET
- 실행:
  - `python -c "import os; print('DART_API_KEY=', 'SET' if os.getenv('DART_API_KEY') else 'MISSING')"`
- 결과:
  - `DART_API_KEY= SET`

> 결론: `setx`로 저장된 User 환경변수가 **현재 PowerShell/VSCode 세션에 정상 반영된 상태**입니다.

### 10.2 dart_main.db::fs_annual 커버리지
- 실행:
  - `python -c "import sqlite3,pandas as pd; c=sqlite3.connect(r'D:\\Quant\\data\\db\\dart_main.db'); q='select min(bsns_year) min_y, max(bsns_year) max_y, count(*) rows, count(distinct stock_code) tickers from fs_annual where bsns_year between 2015 and 2024'; print(pd.read_sql_query(q,c).to_string(index=False))"`
- 결과:
  - `min_y=2015, max_y=2024, rows=4914, tickers=562`

> 해석: `fs_annual`에 **2015~2024 연도 범위가 존재**하며, **서로 다른 stock_code 562개**가 들어 있습니다.

### 10.3 fundamentals.db::fundamentals_monthly_mix400_20260129 범위
- 실행:
  - `python -c "import sqlite3,pandas as pd; c=sqlite3.connect(r'D:\\Quant\\data\\db\\fundamentals.db'); q='select min(date) min_d, max(date) max_d, count(*) rows, count(distinct ticker) tickers from fundamentals_monthly_mix400_20260129'; print(pd.read_sql_query(q,c).to_string(index=False))"`
- 결과:
  - `min_d=2017-02-28, max_d=2026-01-29, rows=37177, tickers=382`

> 해석: mix400 파이프라인에서 **fundready(382 tickers)** 기준으로 월말 스냅샷이 정상 생성되었습니다.

### 10.4 이번까지 결론
- 파이프라인 자체는 **정상 완료**했고,
- 이전에 겪었던 오류는
  1) `DART_API_KEY`가 현재 세션에 미반영(터미널 재시작/세션 주입 필요)
  2) PowerShell에서 `python -c` 사용 시 따옴표/이스케이프 처리 문제
  였는데, **현재는 둘 다 해소된 상태**로 보입니다.

### 10.2 dart_main.db::fs_annual 집계 OK
- 실행:
  - `python -c "import sqlite3,pandas as pd; c=sqlite3.connect(r'D:\\Quant\\data\\db\\dart_main.db'); q='select min(bsns_year) min_y, max(bsns_year) max_y, count(*) rows, count(distinct stock_code) tickers from fs_annual where bsns_year between 2015 and 2024'; print(pd.read_sql_query(q,c).to_string(index=False))"`
- 결과:
  - `min_y=2015, max_y=2024, rows=4914, tickers=562`

> 해석: **2015~2024 구간 기준**, `fs_annual`에 562개 종목의 연간 재무요약이 존재합니다.

### 10.3 fundamentals.db::fundamentals_monthly_mix400_20260129 집계 OK
- 실행:
  - `python -c "import sqlite3,pandas as pd; c=sqlite3.connect(r'D:\\Quant\\data\\db\\fundamentals.db'); q='select min(date) min_d, max(date) max_d, count(*) rows, count(distinct ticker) tickers from fundamentals_monthly_mix400_20260129'; print(pd.read_sql_query(q,c).to_string(index=False))"`
- 결과:
  - `min_d=2017-02-28, max_d=2026-01-29, rows=37177, tickers=382`

> 해석: MixTop400(가격/재무 준비된 유니버스 기반)에서 **382개 종목**에 대해 월말 기준 펀더멘털 월간 피처가 생성되었습니다.

### 10.4 직전 이슈의 원인/정리
- `DART_API_KEY= MISSING`이 뜨던 것은 **(1) setx 후 세션 미반영**, 그리고 일부는 **PowerShell에서 작은따옴표/백슬래시 조합으로 `python -c` 문자열이 깨진 것**이 원인이었습니다.
- 현재는 `DART_API_KEY= SET`으로 확인되므로, 이후 파이프라인에서 DART 수집 단계가 **환경변수 경고 없이** 동작해야 합니다.

---

## 다음 단계(제안)
- S2 전략(펀더멘털 기반 성장주 발굴)용으로:
  1) `fundamentals_monthly_mix400_20260129`를 입력으로 **랭킹/필터링 로직(S2)** 설계
  2) 월 1회 리밸런싱 규칙에 맞춘 백테스트 스크립트 추가(`run_backtest_regime_v2.py`와 유사한 CLI/리포트 체계 유지)
  3) 초기에는 `매출(revenue)`/`영업이익(op_income)` **절대규모 + 성장률(yoY/CAGR)** 조합으로 스코어링

  - `rows=4,914, tickers=562`

> 결론: KOSDAQ 포함 확장 후 `fs_annual`에 2015~2024 구간 데이터가 **562개 종목**에 대해 존재합니다.

### 10.3 fundamentals.db::fundamentals_monthly_mix400_20260129 집계 OK
- 실행:
  - `python -c "import sqlite3,pandas as pd; c=sqlite3.connect(r'D:\\Quant\\data\\db\\fundamentals.db'); q='select min(date) min_d, max(date) max_d, count(*) rows, count(distinct ticker) tickers from fundamentals_monthly_mix400_20260129'; print(pd.read_sql_query(q,c).to_string(index=False))"`
- 결과:
  - `min_d=2017-02-28, max_d=2026-01-29, rows=37,177, tickers=382`

> 결론: mix400 파이프라인에서 fundamentals_monthly 테이블이 **382개 티커** 기준으로 월말(108개 리밸런싱 날짜) 구간이 정상 생성되었습니다.

### 10.4 (원인 정리) 이전 에러가 발생했던 이유
- `DART_API_KEY= MISSING`으로 보였던 시점은 **환경변수 저장(setx) 직후, 동일 세션에 반영이 안 된 상태**였을 가능성이 큽니다.
  - 해결: PowerShell/VSCode 재시작 또는 현재 세션에서 `$env:DART_API_KEY=...`로 즉시 반영.
- `python -c '...'`에서 `rD:\Quant...` 형태의 문법 오류는 **PowerShell 단일 따옴표/이스케이프 처리 때문에 raw string 앞의 따옴표가 깨진 것**이 원인.
  - 해결: 지금처럼 PowerShell에서는 `python -c "..."`(바깥 큰따옴표) + 내부는 작은따옴표를 섞는 방식으로 실행.

---

## 11) 다음 단계 제안 (S2 전략 개발 흐름)
이제 데이터/유니버스/월말 fundamentals_monthly가 준비되었으므로, S2는 아래 순서로 들어가면 됩니다.
1) **S2 스코어 정의**: (매출/영업이익) 규모 + 성장률(예: YoY) + 안정성(마진, 부채, FCF 등) 조합
2) **월 1회 리밸런싱 규칙**: top60 선정, 동일가중/스코어가중, 이탈 규칙(스코어 하락/유동성/리스크오프 등)
3) **백테스트 러너(run_backtest_regime_v2 기반) 확장**: S2 옵션 추가(팩터 컬럼 선택, 필터 파라미터, 로깅/스냅샷/구글시트 업로드)

129'; print(pd.read_sql_query(q,c).to_string(index=False))"`
- 결과:
  - `min_d=2017-02-28, max_d=2026-01-29, rows=37,177, tickers=382`

> 결론: MixTop400 기준으로 fundamentals_monthly 테이블이 **108개월(2017-02~2026-01)** 범위로 정상 생성되었고, **ticker 382개**가 포함되어 있습니다.

### 10.4 직전 오류의 원인 요약
- `DART_API_KEY= MISSING`으로 보이던 것은 **User 환경변수(setx) 저장 후, 현재 세션에 아직 반영되지 않은 상태**에서 확인했기 때문입니다.
- `python -c '...'` 형태에서 발생한 `SyntaxError: invalid syntax`는 **PowerShell에서 작은따옴표/따옴표 조합이 꼬이면서** `r"D:\\..."`가 `rD:\\...`로 깨져서 생긴 문제였습니다.
  - 해결: PowerShell에서는 가급적 `python -c "..."`(바깥 큰따옴표)로 통일하거나, 별도 `.py` 스크립트로 분리.

yntax`는 PowerShell에서 **작은따옴표/큰따옴표 혼용**, 그리고 `r"D:\\..."` 형태가 깨지면서 `rD:\...`로 해석되어 발생했습니다.
  - 해결: PowerShell에서는 아래처럼 **바깥은 큰따옴표(" ")**로, 내부 SQL 문자열은 작은따옴표(' ')로 두는 방식이 안전합니다.

