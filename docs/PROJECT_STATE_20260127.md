# PROJECT_STATE.md
> 생성일: 2026-01-28 (Asia/Seoul)  
> 목적: 현 대화창에서 발생한 이슈/결론/다음 작업을 **한 파일로 고정**하여, 새 대화창에서도 동일 맥락으로 이어가기 위함.

---

## 0) 한 줄 요약
- **KRX Universe(Top200) 생성 파이프라인은 동작**했고, **regime.db 초기화/스키마 확정 후 레짐 히스토리 612,601건 적재까지 성공**했습니다.  
- 다만, 이후 **regime 컬럼이 BLOB으로 저장되는 문제**와 pandas `stack(future_stack=True)` 옵션/NaN int casting 문제 등으로 스크립트가 여러 차례 흔들렸습니다.  
- PowerShell에서 `python -c` 문자열 quoting 문제가 반복적으로 발생했습니다.

---

## 1) 현재 폴더/구성
- 프로젝트 루트: `D:\Quant`
- Universe 스크립트: `src\collectors\universe\build_universe_krx.py`
- 가격 업데이트: `src\collectors\price\price_update_top200_daily.py`
- Regime 관련: `src\regime\`
  - `build_regime_history.py` (여러 patched/fixed 버전 생성/적용)
  - `regime_score.py`
  - `init_regime_db.py`
  - `inspect_regime_db.py`
  - `check_regime_db_types.py` (타입 확인용)
  - `check_price_db_coverage.py`

---

## 2) Universe(Top200) 문제와 결론
### 2.1 문제 인지
- `universe_krx_kospi_20251230` 파일에는 시총(mcap)이 없고, 일부 파일에만 존재.
- Top200 유지가 “마스터 생성 시점에 시총 포함”이 가장 깔끔.

### 2.2 소스 문제
- `pykrx`가 특정 시점(예: 2025-12-30, 2026-01-27)에 대해 ticker_list가 비거나 최근 60일 empty 이슈 발생.
- `FinanceDataReader`(FDR)도 KRX endpoint 차단(Access Denied) 사례가 있었으나,
  - 최종적으로는 `source=auto`에서 `pykrx 실패 -> fdr fallback` 경로로 universe 생성 성공.

### 2.3 최종 성공 로그(요약)
```powershell
python src\collectors\universe\build_universe_krx.py `
  --market KOSPI --asof 20260127 --source auto --topn 200 `
  --price-db "D:\Quant\data\db\price.db" --active-lag-days 7

[DONE] universe_krx_kospi_20260127.csv (n=926)
[INFO] active-filter(price.db) applied: before=926, after=565, cutoff=2026-01-20
[DONE] universe_krx_kospi_20260127_active.csv (n=565)
[DONE] universe_top200_kospi_20260127.csv (n=200)
```

---

## 3) Price Update(Top200) 상태
### 3.1 실행 로그(요약)
```powershell
python src\collectors\price\price_update_top200_daily.py `
  --universe-file "D:\Quant\data\universe\universe_top200_kospi_20260127.csv" `
  --ticker-col ticker `
  --db "D:\Quant\data\db\price.db" `
  --db-max-lag-days 7 `
  --quarantine-empty

[WARN] active_tickers(pykrx) 실패 ...
[INFO] active source=db_lag(7d) (active_tickers=200)
[INFO] active-filter applied: before=200, after=200, inactive=0
[DONE] total_saved_rows=0, updated=0, skip=200, empty=0, fail=0
```

### 3.2 의미
- `SKIP`은 **DB에 이미 최신(또는 max-lag 조건) 데이터가 있어 업데이트할 것이 없을 때** 흔히 나옵니다.
- 즉, “에러”라기보다는 “이미 반영된 상태”일 가능성이 큼.
- 다만 실제로 DB에 최근 종가가 존재하는지 샘플 쿼리로 확인 권장.

---

## 4) Regime 단계: 핵심 이슈/조치/현재 상태
### 4.1 처음 막힌 문제: `ModuleNotFoundError: No module named 'src'`
- `python src\regime\build_regime_history.py ...` 형태로 실행하면
  - 현재 작업 디렉터리/모듈 경로에 따라 `src` import가 실패할 수 있음.
- 해결 방향: **모듈 실행 방식으로 고정**
```powershell
cd D:\Quant
python -m src.regime.build_regime_history ...
```

### 4.2 DB 스키마 문제(중요): `regime.db`가 0 bytes
- `inspect_regime_db.py` 결과:
  - `regime.db size = 0 bytes`, `sqlite_master objects = []`
  - 즉, 파일은 있으나 **테이블이 전혀 없는 빈 DB 파일**.

#### 조치
1) 기존 빈 DB 백업 이름 변경:
```powershell
cd D:\Quant\data\db
Rename-Item .\regime.db .\regime.db.empty_20260127 -Force
```
2) DB 초기화:
```powershell
cd D:\Quant
python src\regime\init_regime_db.py
```
3) 스키마 확인:
```powershell
python src\regime\inspect_regime_db.py
```

#### 확인된 regime_history 스키마(확정)
- DB: `D:\Quant\data\db\regime.db`
- 테이블: `regime_history`
- 컬럼:
  - `date TEXT NOT NULL`
  - `ticker TEXT NOT NULL`
  - `horizon TEXT NOT NULL`  (예: '1y','6m','3m')
  - `score REAL`
  - `regime INTEGER`  (0..4)
  - `created_at TEXT DEFAULT datetime('now')`
  - `updated_at TEXT DEFAULT datetime('now')`
  - `PRIMARY KEY (date, ticker, horizon)`

### 4.3 성공적인 Backfill 실행(5년치, 200종목)
```powershell
python -m src.regime.build_regime_history `
  --universe-file "D:\Quant\data\universe\universe_top200_kospi_20260127.csv" `
  --ticker-col ticker `
  --price-db "D:\Quant\data\db\price.db" `
  --price-table prices_daily `
  --years 5 `
  --end 2026-01-27
```

#### 성공 로그(핵심)
- prices loaded: dates=1226, tickers_in_wide=200
- horizon별 rows:
  - 1y(252d): 183,376
  - 6m(126d): 208,316
  - 3m(63d): 220,909
- total rows: 612,601
- upsert 완료: 612,601 rows
- 검증:
```powershell
python -c "import sqlite3; con=sqlite3.connect(r'D:\Quant\data\db\regime.db'); cur=con.cursor(); print(cur.execute('select count(*) from regime_history').fetchone()); con.close()"
(612601,)
```

### 4.4 남은 문제 1: `regime` 타입이 BLOB으로 저장됨
- `check_regime_db_types.py` 결과:
  - `[typeof(regime)] [('blob', 612601)]`
  - 즉, regime 값이 INTEGER가 아니라 **바이너리 형태로 저장**되고 있음.
- 샘플 row에서 regime 값이 `b'\x00\x00...` 처럼 보임.

#### 현재 판단(원인 가설)
- upsert 시점에 `regime`가 numpy scalar/ndarray 형태로 들어가면서 sqlite가 BLOB로 저장한 가능성이 큼.
- 해결 방향(옵션 A 선택): **삽입 전에 regime을 “파이썬 int”로 강제 캐스팅**해서 executemany에 전달.

### 4.5 남은 문제 2: pandas stack 경고/에러
- FutureWarning: stack 구현 변경 예고.
- 실제 에러:
  - `dropna must be unspecified with future_stack=True`
  - `IntCastingNaNError: Cannot convert NA/inf to integer`

#### 해결 방향(정리)
- `future_stack=True`를 쓰면 `dropna` 인자를 함께 쓰지 말 것.
- regime를 int로 변환하기 전에 NaN 제거/마스킹 필요.

---

## 5) PowerShell에서 반복된 문제(정리)
### 5.1 `copy /Y ...` 실패
- PowerShell의 `copy`는 alias로 `Copy-Item`이며 `/Y` 같은 CMD 옵션을 그대로 못 씁니다.
- 올바른 방식:
```powershell
Copy-Item -Path .\build_regime_history_patched.py -Destination .\build_regime_history.py -Force
```

### 5.2 `python -c "..."`에서 SQL 문자열이 깨짐
- 큰따옴표/이스케이프가 섞이면 PowerShell이 중간을 토큰으로 해석해서
  - `regime : 'regime' 용어가 ...` 같은 “cmdlet 인식” 에러가 나옴.
- 회피 방법(권장):
  1) `python --% -c "..."` (PowerShell parsing 우회)
  2) 또는 아예 `.py` 파일로 만들어 실행(이번에 inspect/check 스크립트처럼)

---

## 6) 현재까지의 결론(객관적 상태)
✅ 된 것
- Universe 생성(Top200) + mcap 포함 + active-filter(가격DB 기반) 적용 동작 확인.
- regime.db를 **정상 스키마로 초기화**하고,
- Top200 × (1y/6m/3m) × 기간에 대해 **612,601건 backfill 적재 성공**.

⚠️ 아직 남은 것
- `regime` 컬럼이 BLOB으로 저장되는 문제를 **완전히 해결(정수형 저장)**해야 함.
- pandas stack 관련 코드 안정화(버전 의존성 최소화).
- “전이 분석 리포트” 및 “RSI/MACD 결합”, “백테스트 전략 플러그인” 단계로 진행.

---

## 7) 다음 작업(우선순위)
1) **regime 저장 타입 문제 해결(최우선)**
   - build_regime_history에서 upsert 직전에 `int(regime)`로 강제 변환해 튜플 생성.
   - 기존 DB를 백업 후 재생성/재적재(필요 시).
   - 검증: `select typeof(regime), count(*) ...` 결과가 `integer`로 나와야 함.

2) 레짐 표준 규격 확정(1y/6m/3m 공통 5단계)
   - 0/1/2/3/4의 의미(하락~강상승)를 명확히 매핑.

3) 전이 분석 리포트
   - (보합/하락 → 상승/강상승) 이벤트 정의
   - 빈도/성공률/기대수익 기반 랭킹

4) technical_indicators 결합(RSI/MACD)
5) backtest_engine 유지 + 전략 모듈 신규 추가

---

## 8) “마지막으로 확정된 성공 커맨드” 모음
### Universe
```powershell
python src\collectors\universe\build_universe_krx.py `
  --market KOSPI --asof 20260127 --source auto --topn 200 `
  --price-db "D:\Quant\data\db\price.db" --active-lag-days 7
```

### Regime DB init/inspect
```powershell
python src\regime\init_regime_db.py
python src\regime\inspect_regime_db.py
```

### Regime backfill
```powershell
python -m src.regime.build_regime_history `
  --universe-file "D:\Quant\data\universe\universe_top200_kospi_20260127.csv" `
  --ticker-col ticker `
  --price-db "D:\Quant\data\db\price.db" `
  --price-table prices_daily `
  --years 5 `
  --end 2026-01-27
```

### Count check
```powershell
python -c "import sqlite3; con=sqlite3.connect(r'D:\Quant\data\db\regime.db'); cur=con.cursor(); print(cur.execute('select count(*) from regime_history').fetchone()); con.close()"
```

---

## 9) 사용자 요구/제약(재확인)
- “암호화폐 얘기 섞지 말 것”(퀀트/주식 시스템 맥락 유지)
- “직설적으로, 돌려 말하지 말 것”
- 대화창이 느려져 프로젝트 진행이 어렵다는 우려 → **상태를 md로 고정하고 새 창에서도 이어가기**를 선호.

---
