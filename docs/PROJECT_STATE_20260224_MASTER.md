# PROJECT_STATE_20260212_MASTER (퀀트투자 백테스트 리팩토링 종합본)

> 기준일: 2026-02-12 (KST)  
> 범위: 2026-02-09 ~ 2026-02-12 동안 작성된 PROJECT_STATE 문서 전부를 **누락 없이 통합** + 최신 이슈/결정 반영  
> 목표: 이 문서 하나만 보고도 **(1) 지금까지 무엇을 했는지, (2) 현재 무엇이 문제인지, (3) 다음에 무엇을 하면 되는지** 즉시 파악 가능

---

## 0) 프로젝트 목적 / 동치 기준

목표는 **레거시 S2 백테스트**와 **리팩토링 S2 백테스트**가 **완전 동치(또는 허용오차 내 거의 동일)** 가 되도록 만드는 것입니다.

동치 기준(필수):

- `summary` (TOTAL / 1Y / 2Y / 3Y / 5Y: CAGR/MDD/Sharpe 등)
- `equity curve`
- `snapshot` (보유 종목 30 + CASH)  ← **현재 최대 이슈**
- `ledger` / `trades_C`
- `perf_windows` / `summary`

---

## 1) 작업 환경 / 고정 전제

- 프로젝트 루트: `D:\Quant`
- venv: `D:\Quant\venv64` (Python 3.10.x)
- DB/Universe는 리팩토링 동안 **고정(업데이트 금지)**  
  - `data\db\regime.db` / table: `regime_history`
  - `data\db\price.db` / table: `prices_daily`
  - `data\db\fundamentals.db` / view: `s2_fund_scores_monthly`
  - `data\universe\universe_mix_top400_20260129_fundready.csv` / ticker col: `ticker`

---

## 2) 골든(Golden) 정책 / 기준 stamp

- **레거시 실행 결과가 정답(Golden)**
- 리팩토링 산출물은 Golden과 **동일 결과를 재현**해야 함.
- 대표 stamp (RBW / 3m / S2 / top30 / good_regimes=4,3 / SMA140 / MG1 / EX2):
  - `3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206`
- Golden Regression: **PASS** 상태를 확보해둔 것이 핵심 자산.

---

## 3) 실행 커맨드(확정본)

### 3.1 레거시(REAL) 실행: Golden 생성/검증 기준선
- 레거시 러너: `run_backtest_s2_v5.py` (또는 동일 동작의 v4 계열)

### 3.2 리팩토링 실행(목표): 레거시 동치 달성 대상
- 리팩토링 러너: `run_backtest_v5.py --s2-refactor` 또는 `run_backtest_s2_refactor_v1.py`

> **중요**: 2026-02-12 기준, 리팩토링 러너들은 “import 경로(패키지/스크립트 혼재)” 문제로 인해 실행 방식이 흔들리며 장애가 반복됨.  
> 이 문제는 “단일 실행 규칙”으로 정리해야 한다(아래 6장 참조).

---

## 4) 산출물 풀세트(8종) 기준

레거시에서 정상 생성이 확인된 CSV 풀세트(8종):

- `equity`
- `holdings`
- `snapshot`
- `ledger`
- `trades`
- `trades_c`
- `perf_windows`
- `summary`

리팩토링에서도 **파일 개수 자체는 8종 동일하게 생성되는 상태까지는 도달**했으나,
- 일부는 “최소 스키마(minimal)”로 남아 레거시와 불일치
- 특히 2026-02-12에는 snapshot 자체가 **CASH 1줄만 남는** 치명 이슈가 핵심

---

## 5) 리팩토링 전체 진행 상황표(통합본: ID 1~10 유지)

진행상황표 2026. 2. 11 버전

| ID | 작업 묶음                    |  난이도  | 상태              | 실제 한 일(요약)                                | 다음 해야 할 일(요약)                              |
| -: | ------------------------ | :---: | --------------- | ----------------------------------------- | ------------------------------------------ |
|  1 | Golden fixture 정리/배치     | ★★☆☆☆ | Done            | 기존 레거시 산출물(snap/summary) 기반 fixture 경로 정리 | RBM fixture 추가 시 동일 패턴 적용                  |
|  2 | Regression 크래시 제거        | ★★★☆☆ | Done            | regression_s2_golden.py 비교 로직/타입/정렬 오류 패치 | 비교 항목 확장 시 재점검                             |
|  3 | Snapshot 정보컬럼(name) 정책   | ★★☆☆☆ | Done            | 표시용 컬럼 mismatch가 회귀를 깨지 않도록 정책 정립(무시)     | 적용 여부 지속 확인                                |
|  4 | 레거시 위임 실행/CSV 풀세트 산출     | ★★★☆☆ | Done            | run_backtest_v5.py로 8종 CSV 생성 확인          | refactor 엔진 직실행도 8종 동일 생성되게                |
|  5 | fee/slippage parity(5/5) | ★★★☆☆ | Done            | fee/slippage 5/5로 동일화                     | 숨은 기본값 동치 점검                               |
|  6 | RBW golden 갱신 + PASS     | ★★★★☆ | Done            | Golden 갱신 후 회귀 PASS 확보                    | (선택) trades 복사 패턴 정리                       |
|  7 | refactor 엔진 parity 포팅 시작 | ★★★★★ | **In-Progress** | (현재) refactor 경로 실행 중 시그니처/호환성 이슈 수정 중    | **레거시 위임 제거** + CSV 컬럼/내용 동치화 + 회귀 PASS 유지 |
|  8 | RBM fixture 추가           | ★★☆☆☆ | Pending         | -                                         | 월말(M) stamp로 golden 생성/배치                  |
|  9 | RBM golden PASS          | ★★★★☆ | Pending         | -                                         | RBM regression PASS                        |
| 10 | 표준 커맨드/문서화               | ★★☆☆☆ | Pending         | -                                         | 표준 실행 커맨드/옵션 문서+체크리스트 고정                   |




> 2026-02-10/11 문서에서 정의한 ID 체계를 유지하고, 2026-02-12 이슈(스냅샷/티커/임포트 혼재)를 반영해 상태를 최신화했습니다.

| ID | 작업 묶음 | 난이도 | 상태(2026-02-12) | 지금까지 실제 한 일(핵심) | 남은 핵심 |
|---:|---|:---:|---|---|---|
| 1 | Golden fixture 정리/배치 | ★★☆☆☆ | Done | 레거시 산출물을 Golden으로 고정, 경로/백업 정리 | Golden 생성/백업을 스크립트화(실수 방지) |
| 2 | Regression 크래시 제거 | ★★★☆☆ | Done | regression 비교 로직 안정화, PASS 확보 | 비교 범위(추가 파일) 확장 시 재점검 |
| 3 | Snapshot 정보컬럼(name) 정책 | ★★☆☆☆ | Done | 표시용 컬럼 불일치가 회귀를 깨지 않도록 정책 정립 | “표시용 vs 동치용 컬럼” 문서화 고도화 |
| 4 | 레거시 위임 실행/CSV 풀세트 산출 | ★★★☆☆ | Done | 레거시로 8종 CSV + GSheet 업로드 정상 | 리팩토링 산출물로 전환(레거시 위임 제거) |
| 5 | fee/slippage parity(5/5) | ★★★☆☆ | Done | fee=5bps / slippage=5bps 동치 고정 | 숨은 기본값(정렬/라운딩/정합) 점검 |
| 6 | RBW golden 갱신 + PASS | ★★★★☆ | Done | RBW golden 갱신 후 PASS 유지 | (선택) `__trades` 등 추가 fixture 관리 |
| 7 | refactor 엔진 parity 포팅 | ★★★★★ | In Progress | 리팩토링 러너가 끝까지 실행 + 8종 CSV 생성 수준까지 도달(과거) | **filled bundle 적용/저장 강제 + 스키마/내용 동치** |
| 8 | RBM fixture 추가 | ★★☆☆☆ | Pending | RBW 집중으로 보류 | RBM stamp 생성 및 golden 추가 |
| 9 | RBM golden PASS | ★★★★☆ | Pending | - | RBM 회귀 PASS |
| 10 | 표준 커맨드/문서화 | ★★☆☆☆ | In Progress | 커맨드/고정 파라미터 정리(예: market-sma-mult=1.02 유지) | **단일 실행 규칙 + import 규칙**을 문서/코드로 강제 |

## 진행 상황표 (업데이트: 2026-02-19)

| 단계 | 목표 | 상태 | 증거/메모 | 다음 액션 |
|---|---|---:|---|---|
| P0 | 리팩토링 파이프라인 실행 안정화 | 완료 | 8종 CSV 생성, 스모크 테스트 통과 | P1 동치검증으로 이동 |
| P1-조건정렬 | 레거시 vs 리팩토링 실행조건 완전 고정 | 진행중 | 주간 642 확인, 비용 10bps 통일 방향 | universe/옵션/snapshot 정책 최종 고정 |
| P1-동치검증 | 성능/곡선/거래 동치 확인 | 진행중 | 동일 주간 642에서도 차이 관측 | divergence 날짜/리밸런스에서 원인 로그 비교 |
| P1-출력동치 | CSV 스키마/날짜 규약 정합 | 진행중 | date/rebalance_date/asof_date 분리 필요 | 출력 규약 문서화 및 컬럼 고정 |
| P2 | 레거시 러너 deprecate & refactor만 운영 | 대기 | P1 완료 후 | run_backtest_v5 단일 엔트리로 정리 |






---

## 6) 2026-02-12 핵심 이슈: “snapshot이 CASH 1줄만 나옴” (전략 실패 아님)

### 6.1 관측된 증상(확정)
- holdings는 정상:
  - holdings 총 row ≈ 8,982
  - 마지막 리밸런스(예): 2026-02-04
  - 해당 리밸런스에서 non-cash 종목 30개 존재
- snapshot은 비정상:
  - 결과 row 수가 1 (CASH만 존재)

### 6.2 원인(최유력/사실 기반)
snapshot은 가격을 조회하기 위해 다음을 수행:

```
close_wide.loc[snapshot_date, ticker]
```

여기서 ticker 자료형/포맷 불일치로 전부 KeyError가 발생 → 종목이 모두 drop → CASH-only가 됨.

- holdings ticker: `'065350'` (6자리 문자열)
- close_wide columns: `65350`(int) 또는 `'65350'` (zfill 미적용)

즉 **ticker ↔ close_wide 컬럼 매칭 실패**가 snapshot만 터지게 만든다.

### 6.3 지금까지의 패치 시도(요약)
- fill_bundle: snapshot carry-forward 제거 등
- legacy_reports: ticker resolver 강화(zfill/strip/'A' 제거/numeric equivalence 등)
- A안(전역 표준화): ticker는 문자열 6자리로 통일하자는 방향
  - `core/tickers.py` 신규 생성 (ticker 정규화 공통 모듈)
  - `core/data.py`, `core/engine.py`, `fill_bundle.py`, `legacy_reports.py` 등에서 ticker 정규화 경로 도입

### 6.4 “그런데 왜 더 꼬였나?” (2026-02-12의 2차 문제)
티커 정규화 자체는 **문제 해결 방향이 맞음**.  
하지만 동시에 아래가 섞이며 “임포트/실행 방식 혼재”가 발생:

- `python file.py` 실행(스크립트 실행) vs `python -m package.module` 실행(패키지 실행)
- `from core...` / `from outputs...` / `from src.backtest...` / 상대 import(`from .core...`) 혼재
- 일부 파일에서 sys.path 조작을 통해 임시로 돌아가게 만든 “dual-mode” 패치가 누적

그 결과:
- `attempted relative import with no known parent package`
- `attempted relative import beyond top-level package`
- `ModuleNotFoundError: No module named 'core'`
같은 오류가 반복적으로 발생.

---

## 7) 오늘 기준 결론(냉정한 상태)

- **전략 로직 자체가 실패한 것이 아니라**, “output(snapshot) 단계의 ticker 매칭”이 실패 중.
- 이 이슈를 해결하려면:
  1) **close_wide.columns를 생성하는 순간부터 ticker를 문자열 6자리로 강제**해야 하고,
  2) 동시에 프로젝트 전체를 **단일 import/실행 방식으로 정리**해야 함(dual-mode 제거).

---

## 8) 다음에 해야 할 작업(요약)

아래는 TODO 문서(V2)에 상세화되어 있음:

1) 실행 방식 “한 가지”로 고정(패키지 실행) + 모든 import를 `src.backtest...`로 통일  
2) `close_wide.columns` dtype/샘플 확인 후, `core/data.py`에서 pivot 결과 컬럼을 **항상 zfill(6)** 적용  
3) snapshot 생성 직전에 디버그 로그 3줄 추가(컬럼 샘플/매칭 실패 건수) → 원인 즉시 확정  
4) snapshot row=31(30+cash) 복구되면, 그 다음 perf_windows / ledger / trades_c 동치로 진행  

---

## 9) 참고: 2026-02-09~12 문서 출처(통합 원본)

- `PROJECT_STATE_2026-02-09.md`
- `PROJECT_STATE_2026-02-10.md`
- `PROJECT_STATE_2026-02-11.md`
- `PROJECT_STATE_REFACTOR_S2_2026-02-12.md`
- `Quant_Backtest_Refactor_Project_State_20260212_Last.md`
- `PROJECT_STATE_20260212_V1.md`



# PROJECT_STATE_20260220_MASTER

## 기준일: 2026-02-23

---

## 1. 이번 세션 진행 내용

### 1) Fundamentals As-Of 규약 하드 고정
- rebalance_date 기준 직전 월말(prev month-end)로 fund_asof_date 강제
- exact date 없으면 <= fund_asof_date 중 최신 사용
- holdings에 fund_asof_date 명시 기록
- force_exit 미정의 오류 수정

### 2) Market Gate Proxy 동치 1차 수정
- pct_change(fill_method=None) 제거
- 레거시와 동일하게 pct_change() 기본 동작 사용
- market_price / market_sma 계산 구조 레거시 기준 정렬

### 3) Selection CSV 정상화
- selection_df 생성 확인
- 저장 로직 연결 수정
- CSV 정상 생성 확인

---

## 2. 현재 남은 핵심 과제

1. Market scope 완전 동치 검증
2. 최초 divergence 날짜 재탐지
3. divergence 원인 1개 요인으로 수렴
4. regression 자동화 강화

---

## 3. 현재 단계 요약

- P0 실행 안정화 완료
- A 이슈(fund as-of) 완료
- Market proxy 1차 동치 완료
- Selection 인프라 확보

→ 현재 P1(동치 수렴 단계) 진행 중

### 백테스트 실행 명령

python -m src.backtest.run_backtest_v5 `
  --s2-refactor `
  --regime-db .\data\db\regime.db `
  --regime-table regime_history `
  --price-db .\data\db\price.db `
  --price-table prices_daily `
  --fundamentals-db .\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file .\data\universe\universe_mix_top400_latest_fundready.csv `
  --ticker-col ticker `
  --horizon 3m `
  --start 2013-10-14 `
  --end 2026-03-11 `
  --rebalance W `
  --weekly-anchor-weekday 2 `
  --weekly-holiday-shift prev `
  --good-regimes 4,3 `
  --top-n 30 `
  --sma-window 140 `
  --market-gate `
  --market-scope KOSPI `
  --market-sma-window 60 `
  --market-sma-mult 1.02 `
  --fee-bps 5 `
  --slippage-bps 5 `
  --outdir .\reports\backtest_regime_refactor `
  --gsheet-enable `
  --gsheet-cred .\config\quant-485814-0df3dc750a8d.json `
  --gsheet-id "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs" `
  --gsheet-tab S2_snapshot `
  --gsheet-mode overwrite `
  --gsheet-ledger `
  --gsheet-prefix S2




# PROJECT_STATE_20260224.md

## 1. 프로젝트 개요

-   프로젝트명: Quant Regime S2 Refactor
-   루트 경로: D:`\Quant`{=tex}
-   목적:
    -   레거시 S2 백테스트 엔진을 구조적으로 리팩토링
    -   모듈화된 구조(core / strategies / outputs)
    -   Golden Snapshot 기반 회귀 검증
    -   장기적으로는 레거시 완전 폐기

------------------------------------------------------------------------

## 2. 현재 시스템 구조

### 실행 구조

run_backtest_v5.py (wrapper) └── run_backtest_s2_refactor_v1.py (실제
refactor 엔진) ├── core.data ├── core.engine ├── strategies.s2 └──
outputs (csv 생성)

------------------------------------------------------------------------

## 3. 데이터 상태 (2026-02-24 기준)

### price.db

-   max_date: 2026-02-23
-   rows: 1,862,025
-   정상 업데이트 완료

### regime.db

-   horizon별 저장 정상
-   3m 기준 정상 동작

### fundamentals.db

-   max_date: 2026-01-30
-   monthly mix view 정상

------------------------------------------------------------------------

## 4. Refactor 엔진 상태

### 정상 동작 확인

-   compileall 통과
-   refactor 단독 실행 가능
-   CSV 생성 정상
    -   snapshot
    -   windows
    -   trades
    -   ledger
    -   summary
    -   equity
    -   holdings

### 성능 예시 (sanity run)

-   CAGR: 12.59%
-   Sharpe: 1.58
-   MDD: -3.5%
-   rebalance_count: 39
-   SMA filter, market gate 정상 반영

------------------------------------------------------------------------

## 5. 레거시 vs 리팩토링 상태

  항목                  상태
  --------------------- -------------------------
  전략 로직             유사하나 완전 동치 아님
  리밸런싱              주간 정상
  SMA 필터              정상
  market gate           정상
  Google Sheet 업로드   미동작

------------------------------------------------------------------------

## 6. Google Sheet 기능 상태

### 레거시

-   snapshot
-   windows
-   trades
-   ledger
-   summary → gsheet_plugin 통해 업로드 정상

### 리팩토링

-   CSV 생성은 정상
-   argparse에 gsheet 옵션 없음
-   upload 호출부 없음
-   wrapper → refactor 인자 전달은 되나 refactor가 인식 못함

즉:

리팩토링 엔진에 gsheet 기능이 아직 완전히 복원되지 않음

------------------------------------------------------------------------

## 7. 반복 에러 원인 분석

이번 세션에서 발생한 주요 문제 유형:

1.  패치 파일 경로 불일치
2.  서로 다른 버전 파일 혼재
3.  함수 시그니처 변경 후 호출부 미수정
4.  argparse 옵션 미정의
5.  들여쓰기/블록 파손
6.  data.py 구조 손상

핵심 원인:

"부분 패치 누적"으로 파일 간 버전 불일치 발생

------------------------------------------------------------------------

## 8. 현재 결론

-   리팩토링 엔진 자체는 안정권
-   CSV 기반 성능 분석 가능
-   Google Sheet 업로드 기능만 미완성
-   레거시는 더 이상 기준으로 사용하지 않기로 결정



(끝)


---

## 2026-02-24 변경 사항(대화 반영)

- CONVENTIONS 업데이트: **레거시 parity는 더 이상 목표가 아니며, refactor를 canonical로 확정**.
- 시급 이슈 반영:
  - gsheet 업로드 함수명 불일치 수정(호환 wrapper 및 호출명 정리).
  - run_backtest_v5 wrapper의 subprocess delegate 제거(규약 준수: import + main(argv)).
  - fee/slippage 기본값을 프로젝트 표준 **5/5(총 10bps)** 로 통일.
