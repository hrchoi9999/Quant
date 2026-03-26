# PROJECT_STATE_2026-02-06.md
(작성일: 2026-02-06, KST)

> 목적: 오늘(2/6) 대화 시작 시점에서의 “해결 과제”와 실제로 처리/수정한 내용, 현재 상태(정합성/성능/업로드), 내일 해야 할 일을 한 문서에 정리합니다.  
> 프로젝트 경로 기준: `D:\Quant` (Windows, PowerShell, venv64)

---

## 0. 오늘 대화 시작 시점에서의 핵심 해결 과제(우선순위 순)

### A. Fundamentals 날짜 정합성(C안) 확정 및 파이프라인 반영
- 목표: **주가(가격) 데이터와 fundamentals 월말 기준 날짜가 일관되게 맞도록 정리**.
- 정책(C안으로 확정):
  - fundamentals의 “월말” 기준은 **캘린더 월말이 아니라 ‘거래 월말(trading month-end)’**로 통일.
  - `--end`가 월중일(예: 2026-02-06)이더라도 fundamentals는 **해당월 ‘거래 월말’까지만** 반영되도록 **스냅(snap)**.
  - 파이프라인에서 `fundamentals_end`가 `YYYY-MM-31`처럼 찍히더라도 실제 데이터는 **거래 월말(예: 2026-01-30)**에 정렬될 수 있음.

### B. build_fundamentals_monthly 뷰/테이블 충돌 및 DB lock 오류 해결
- 이슈1: `s2_fund_scores_monthly`가 VIEW가 아닌 TABLE로 존재 → `DROP VIEW` 실패
- 이슈2: `_cleanup_non_month_end_rows`에서 `ATTACH/DETACH` 사용 중 **pricedb locked** 발생
- 목표: incremental 실행이 매번 안정적으로 되게 하고, legacy 테이블/뷰 정리 로직을 견고화.

### C. Backtest v4(=run_backtest_regime_s2_v4.py) 버전관리/옵션/구글시트 업로드 복원
- 목표:
  - v3에서 되던 구글시트 업로드 기능을 v4에 정상 복원/활성화
  - **버전(파일 헤더/로그 출력/파일명) 혼란 제거**
  - SMA 필터 옵션, 시장 게이트 등 CLI 파라미터 정리
- 추가 목표(사용자 요청):
  - 성능평가 시 summary/perf_windows를 **표로 요약**
  - snapshot/trades 결과가 비는 문제(이전 v3 대비)를 파악/정리

### D. “장중 실행” 안전장치 + “주간 리밸런싱 기준일” 모델 정리 및 반영
- 사용자 요구:
  - 장중(한국시간 주식시장 거래 중) 실행 시 **당일 데이터로 백테스트가 돌면 위험** → 전 거래일까지로 스냅
  - 주간 리밸런싱 기준일은 **수요일(weekday=2)**, 휴장일이면 **이전 거래일(prev)**로 이동
  - “결정일/체결일 모델”은 추천 모델로 진행(결정일=기준일, 체결은 리밸런싱 로직 정의에 따름)

---

## 1. 오늘 실제로 진행/해결된 내용(타임라인 요약)

### 1) 파이프라인 실행 중 fundamentals 뷰/테이블 충돌 해결
- 파이프라인: `rebuild_mix_universe_and_refresh_dbs.py --update-latest`
- 증상:
  - `sqlite3.OperationalError: use DROP TABLE to delete table s2_fund_scores_monthly`
- 조치:
  - `build_fundamentals_monthly.py`에서 뷰 재생성 단계에 들어가기 전
    - 기존 `s2_fund_scores_monthly`가 테이블이면 **legacy로 rename** 처리 후 뷰 재생성
- 결과:
  - 단독 실행 시 아래 로그 확인:
    - `[CLEAN] renamed legacy table -> s2_fund_scores_monthly__legacy_...`
    - `[DONE] refreshed views ...`

### 2) fundamentals 날짜 정합성 검증 스크립트(check_fundamentals_latest.py)로 확인
- 확인 결과(사용자 출력):
  - `min_d=2017-02-28`, `max_d=2026-01-30`, `tickers=372`
  - `non_trading_month_end_dates = 0`
  - `[OK] All fundamentals dates are trading month-end dates.`
- 해석:
  - “캘린더 월말”이 아니라 “거래 월말”로 잘 정렬되어 있음(정책 C안 준수).
  - `non_calendar_month_end_rows`가 1116이라는 것은 **캘린더 월말(예: 2026-01-31)이 아닌 날짜들이 존재**한다는 의미이며, 이는 의도한 바(거래 월말)라서 문제 아님.

### 3) pricedb locked 오류(DETACH DATABASE locked) 발생 및 안정화
- 증상:
  - `sqlite3.OperationalError: database pricedb is locked`
- 추정 원인:
  - SQLite attach된 상태에서 커서/커넥션이 완전히 닫히기 전에 detach 시도하거나,
  - 동일 DB를 다른 프로세스/커넥션이 잡고 있는 상태에서 detach 시도.
- 조치(결과적으로):
  - 이후 재실행 시 `[INFO] no month_end_dates ...`로 정상 종료하며 뷰 리프레시 완료.
  - (추가 개선 필요: `ATTACH/DETACH` 구간에 `try/finally`로 close/detach 보장, `timeout`/`PRAGMA busy_timeout` 적용 검토)

### 4) backtest v4에서 구글시트 업로드 기능 복원 및 버전 혼란 정리
- 초기에 발생한 이슈들:
  - CLI: `--require-above-sma` 인식 불가 (argparse에 없음)
  - safe_intraday 코드가 main 밖에서 args 참조 → `NameError: args not defined`
  - 버전 불일치(파일 헤더 vs 출력 script_version vs 파일명)
  - gsheet 업로드 시 pandas Timestamp/np 타입 직렬화 문제
  - gsheet_uploader import 경로/심볼 불일치
- 해결 결과(최종 확인):
  - 실행 로그:
    - `[INFO] script_version=2026-02-06_010`
    - 결과 CSV 저장 모두 성공
    - `[GSHEET] created sheets: {'snapshot':..., 'trades':..., 'windows':...}`
  - 구글시트 업로드 “성공” 확인(사용자 확인)

### 5) safe_intraday 경고 수정
- 증상(구글시트 성공 후 남은 경고):
  - `[WARN] safe_intraday: failed ... (type object 'datetime.datetime' has no attribute 'datetime')`
- 원인:
  - `from datetime import datetime` 형태에서 `datetime.datetime.now()`를 호출하는 코드가 섞임
- 조치:
  - `now = datetime.now()`로 수정(버전 2026-02-06_010으로 통일)

---

## 2. 오늘 기준 “현재 상태” 점검

### 2.1 파이프라인 최신화 결과(2026-02-06 asof)
- Universe:
  - `universe_mix_top400_latest_fundready.csv` 생성/갱신
- Price:
  - `price_db_max_after=2026-02-06`까지 반영
- Regime:
  - `regime_history` 3m/6m/1y upsert 정상, `verify_no_blob PASSED`
- Fundamentals:
  - end 스냅: `2026-02-06 -> 2026-01-31` (표시는 캘린더 말일이지만 데이터는 거래 월말 정렬)
  - incremental에서 최신 월말 처리 후 “views refreshed” 정상

### 2.2 백테스트 실행(최종)
- 명령(사용자 실행 로그 기준):
  - S2 전략, horizon=3m
  - rebalance=W, weekly-anchor-weekday=2(수), holiday_shift=prev
  - top_n=30, good_regimes=4,3
  - SMA window=140 ON, market_gate ON(60, 1.02)
  - fee/slippage 각 5bps
  - gsheet-enable ON
- 핵심 로그:
  - `rebalance dates=642 (week-anchor: weekday=2, holiday_shift=prev)`
  - excluded tickers 2개(최종일 데이터 부족): `388210, 488900`
  - gsheet sheets 생성 완료

### 2.3 성능(요약)
- summary(전체기간): 
  - CAGR ≈ 10.88%
  - Sharpe ≈ 0.825
  - MDD ≈ -23.79%
  - rebalance_count=642
- perf_windows(1/2/3/5년): 
  - 최근 구간 성능이 장기보다 개선되는 패턴 확인(상세 수치는 CSV에서 산출)

> 주의: 이 백테스트는 “주간 리밸런싱 기반”이며, 일간 수익률/변동성 산출이 “일간 마크투마켓” 백테스트와 동일한 의미로 해석되지 않을 수 있음(정의상 그렇게 계산됨).

---

## 3. 오늘 생성/사용된 주요 파일 및 역할(상관관계 포함)

### 3.1 파이프라인/데이터 갱신
- `D:\Quant\src\pipelines\rebuild_mix_universe_and_refresh_dbs.py`
  - 역할: (1) KOSPI/KOSDAQ top200 생성 → (2) mix top400 생성 → (3) 가격 결손 백필 → (4) regime 갱신 → (5) fundamentals 갱신(뷰 포함) → (6) latest 심볼릭/복사
  - 산출물:
    - `data\universe\universe_mix_top400_YYYYMMDD*.csv`
    - `data\universe\*_latest*.csv`

- `D:\Quant\src\fundamentals\build_fundamentals_monthly.py`
  - 역할: DART annual 기반 + price 월말 기준으로 monthly factor 생성/업서트, `s2_fund_scores_monthly` 등 view 재생성
  - 핵심: “거래 월말(trading month-end)” 정렬 정책

### 3.2 백테스트 및 리포트
- `D:\Quant\src\backtest\run_backtest_regime_s2_v4.py`
  - 역할: Regime + Fundamentals + SMA/Market Gate를 결합한 포트폴리오 백테스트(S2)
  - 산출물(보고서 디렉토리):
    - `regime_bt_summary_*.csv`
    - `regime_bt_perf_windows_*.csv`
    - `regime_bt_equity_*.csv`
    - `regime_bt_holdings_*.csv`
    - `regime_bt_snapshot_*.csv`
    - `regime_bt_snapshot_*__trades.csv`

- `D:\Quant\src\utils\gsheet_uploader.py`
  - 역할: CSV/DF를 Google Sheets로 업로드(탭 생성/overwrite/append 등)

### 3.3 진단 스크립트(사용자 로컬)
- `D:\Quant\check_fundamentals_latest.py`
  - 역할: fundamentals 최신 테이블의 min/max, 월별 row 수, 뷰 존재여부, 월말 정합성 검증

---

## 4. 오늘 해결된 이슈 목록(체크리스트)

- [x] fundamentals 뷰/테이블 충돌(`DROP VIEW` 실패) → legacy rename 후 뷰 재생성
- [x] fundamentals “거래 월말” 정렬 확인(비거래월말 0)
- [x] v4에서 구글시트 업로드 정상화(탭 생성 및 업로드 성공)
- [x] safe_intraday datetime 참조 오류 수정(최종 010 버전에서 정상)
- [x] 주간 리밸런싱 기준일(수요일), 휴장 시 prev 이동 옵션 반영

---

## 5. 아직 남은 문제/개선 과제(내일 우선순위)

### P1. A/B/C(추가 요구사항) 반영: Trades 확장 리포트 + 업로드
사용자 요구(확정):
- A) trades 저장 범위를 “최근 N년 제한”이 아니라 **전기간/충분기간**으로 저장(기본값 조정)
- B) snapshot의 CASH 행 처리 개선(보기/정합성):
  - ticker도 `CASH`로 채워서 downstream(구글시트/분석) 편의성 향상
- C) **거래 요약 CSV** 생성:
  - 매수일, 매수가, 매도일, 매도가, 수익률(%) 포함
  - 일/주/월 단위로 “매수/매도 종목 리스트”도 뽑을 수 있게 “그룹핑 가능한” 형식 설계
  - 이 CSV도 **구글시트 탭으로 업로드**

> 오늘 세션 말미에 “C용 트레이드 CSV 생성 + 구글시트 업로드”를 반영한 수정본을 제공했으며, 내일 실제 적용/검증이 필요합니다.

### P2. safe_intraday 스냅 로그가 실제로 기대대로 동작하는지 “장중 테스트”
- 장중(15:30 이전) 실행 시:
  - `--end`가 당일이면 **전 거래일로 스냅**되어야 함
- 장마감 이후 실행 시:
  - 스냅 없이 정상 진행
- 필요: 장중에 1회 테스트 및 로그 확인

### P3. `pricedb locked` 재발 방지(근본)
- `build_fundamentals_monthly.py`의 `ATTACH/DETACH` 구간에
  - `busy_timeout` 또는 `timeout` 적용
  - `try/finally`로 detach 보장
  - 커넥션/커서 close 시점 정리
- 목표: 파이프라인 자동화 시 “간헐적 lock”으로 실패하지 않게 하기

### P4. 성능 리포트 표준화(요청사항)
- 앞으로 성능 평가 시:
  - `summary.csv` + `perf_windows.csv` 내용을 “표 형태”로 요약(1/2/3/5년 포함)
  - 필요 시 regime별/게이트별 분해 요약도 표준화

---

## 6. 내일 해야 할 일(실행 순서 추천)

1) **A/B/C 반영본 적용**
   - v4 파일과 gsheet_uploader 파일을 최신 수정본으로 교체
   - 버전/로그 출력이 일치하는지 먼저 확인

2) **백테스트 1회 실행(구글 업로드 포함)**
   - 목표: 기존 탭(snapshot/trades/windows) + 신규 탭(요약 trades C 등)까지 생성/업로드 확인

3) **산출된 신규 CSV 검증**
   - C 트레이드 CSV에서:
     - buy_date/buy_price/sell_date/sell_price/return_pct가 모두 채워지는지
     - 포지션이 없던 기간(리스크오프) 처리 방식이 일관적인지(NA/0 등)

4) (가능하면) **장중 safe_intraday 동작 테스트**
   - 15:30 이전에 실행하여 `end`가 전일로 스냅되는지 확인

5) `pricedb locked`가 재발하면
   - `build_fundamentals_monthly.py`의 lock 방지 패치(근본 해결) 진행

---

## 7. 참고: 오늘 사용한 대표 실행 명령(기록)

### 7.1 파이프라인
```powershell
cd D:\Quant\src\pipelines
python .\rebuild_mix_universe_and_refresh_dbs.py --update-latest
```

### 7.2 fundamentals 단독 incremental
```powershell
cd D:\Quant\src\fundamentals
python .\build_fundamentals_monthly.py --incremental `
  --dart-db D:\Quant\data\db\dart_main.db `
  --universe-file D:\Quant\data\universe\universe_mix_top400_20260206_fundready.csv `
  --ticker-col ticker `
  --price-db D:\Quant\data\db\price.db `
  --price-table prices_daily `
  --start 2017-02-08 `
  --end 2026-01-31 `
  --out-db D:\Quant\data\db\fundamentals.db `
  --out-table fundamentals_monthly_mix400_latest
```

### 7.3 백테스트(v4) + 구글 업로드
```powershell
cd D:\Quant\src\backtest
python .\run_backtest_regime_s2_v4.py `
  --regime-db ..\..\data\db\regime.db `
  --price-db ..\..\data\db\price.db `
  --fundamentals-db ..\..\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file ..\..\data\universe\universe_mix_top400_latest_fundready.csv `
  --ticker-col ticker `
  --horizon 3m `
  --start 2013-10-14 `
  --end 2026-02-06 `
  --rebalance W `
  --weekly-anchor-weekday 2 `
  --weekly-holiday-shift prev `
  --top-n 30 `
  --good-regimes 4,3 `
  --sma-window 140 `
  --market-gate `
  --market-sma-window 60 `
  --market-sma-mult 1.02 `
  --fee-bps 5 `
  --slippage-bps 5 `
  --gsheet-enable
```

구글 업로드 끄기:
```powershell
--no-gsheet-enable
```

---

## 8. 파일 버전관리 원칙(재확인)
- 모든 수정 파일의 첫 줄에:
  - `# <파일명> ver YYYY-MM-DD_###`
- 같은 날짜 내 수정 시 `_001, _002...` 순번 증가를 엄격하게 적용
- 로그 출력 버전(`script_version`)과 헤더 버전이 반드시 동일해야 함

---
