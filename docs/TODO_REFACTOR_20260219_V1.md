# TODO_REFACTOR_20260212_V2 (리팩토링 다음 작업: 최신 종합본 기반)

> 기준일: 2026-02-12 (KST)  
> 목적: `PROJECT_STATE_20260212_MASTER.md`의 결론/현상/원인에 근거해, 다음 세션에서 **바로 실행 가능한 체크리스트**로 재정리

---

## A. 최우선(P0): “실행 방식/임포트 방식”을 한 가지로 고정

### A1) 단일 실행 규칙
- **반드시 프로젝트 루트에서** 실행: `cd D:\Quant`
- **반드시 모듈 실행** 사용:
  - 예) `python -m src.backtest.run_backtest_v5 ...`
  - 예) `python -m src.backtest.run_backtest_s2_refactor_v1 ...`
- 금지:
  - `python .\src\backtest\run_backtest_s2_refactor_v1.py` (스크립트 실행)
  - `sys.path.insert(...)`로 임시 실행

### A2) 단일 import 규칙(코드 수정 범위)
- `src/backtest/**.py` 전체에서 import는 아래 한 가지만 허용:
  - `from src.backtest.core...`
  - `from src.backtest.outputs...`
  - `from src.backtest.strategies...`
- 금지:
  - `from core...`, `from outputs...`
  - 상대 import(`from .core...`, `from ..core...`)는 프로젝트 정책상 사용하지 않도록 고정(혼란 방지)

> 작업 대상(최소):  
> `src/backtest/run_backtest_s2_refactor_v1.py`, `src/backtest/run_backtest_v5.py`,  
> `src/backtest/core/data.py`, `src/backtest/core/engine.py`,  
> `src/backtest/outputs/fill_bundle.py`, `src/backtest/outputs/legacy_reports.py`  
> + 에러가 뜨는 모듈부터 순차 확장

---

## B. 최우선(P0): snapshot CASH-only 문제 해결(본질)

### B1) 원인 확정용 1회 진단(로그 추가)
`snapshot` 생성 직전에 아래 3가지를 1회만 출력(또는 로그 파일로 기록):
1) `type(close_wide.columns[0])`  
2) `list(close_wide.columns[:10])` (샘플 10개)  
3) 마지막 리밸런스일 holdings tickers 샘플 10개

### B2) 근본 해결(권장)
- `core/data.py::load_prices_wide()` (또는 pivot을 수행하는 함수)에서:
  - pivot 결과 컬럼(티커)을 **항상 문자열 6자리(zfill)** 로 변환해 반환
- 같은 원칙을 universe ticker, holdings ticker에도 적용(이미 `core/tickers.py` 도입 방향이 맞음)

> 성공 판정: snapshot CSV row 수가 **31(=30종목+cash)** 로 회복

---

## C. P1: filled bundle 저장 강제(스키마/내용 동치)

snapshot이 정상화되면 다음 단계:

1) `fill_bundle.fill_legacy_outputs(...)`가 반환하는 “filled” 데이터를  
   실제로 저장/업로드 대상으로 사용하고 있는지 점검
2) 리팩토링 산출물 8종 CSV의 헤더를 레거시와 비교
3) 레거시와 다른 컬럼은:
   - 정책적으로 “비교 제외”할지
   - “동일 컬럼으로 생성”할지
   를 결정하고 문서화

---

## D. 회귀(Regression) 체크 시나리오(권장 순서)

1) import/compile 스모크
   - `python -m py_compile .\src\backtest\core\data.py`
   - `python -m py_compile .\src\backtest\core\engine.py`
   - `python -m py_compile .\src\backtest\outputs\fill_bundle.py`
   - `python -m py_compile .\src\backtest\run_backtest_s2_refactor_v1.py`

2) “모듈 import 스모크”
   - `python -c "import src.backtest.outputs.fill_bundle as m; print(m.__file__)"`
   - `python -c "import src.backtest.run_backtest_s2_refactor_v1 as m; print(m.__file__)"`
   - `python -c "import src.backtest.core.data as m; print(m.__file__)"`

3) 리팩토링 실행(대표 stamp)
   - `python -m src.backtest.run_backtest_v5 --s2-refactor ... (대표 커맨드)`

4) 결과 비교(우선순위)
   - snapshot(row=31) → summary → perf_windows → ledger/trades_c

---

## E. 다음 세션에서 “바로 끝내야 하는 것” 3개

1) import/실행 방식 통일(dual-mode 제거)  
2) `close_wide.columns`를 6자리 문자열로 강제하여 snapshot 복구  
3) snapshot이 복구되면 filled bundle 저장 강제 → 레거시 동치 수렴 시작

(끝)
---

# TODO_REFACTOR_20260219_V1 (업데이트: 2026-02-19)

## P0 (즉시 처리: 0~1일)
1. **동치 검증 커맨드 1개 확정**
   - 레거시(v4)와 리팩토링(v5)이 동일하게 사용해야 하는 항목
     - universe 파일(동일 파일)
     - start/end/horizon/good_regimes/top_n/sma_window/market gate 관련 옵션
     - fee_bps/slippage_bps(총 10bps)
     - snapshot 정책(as-of를 레거시처럼 둘지, 리팩토링 운영정책으로 둘지)
2. **비교 자동화 스크립트(단발성) 작성**
   - 입력: 레거시 outdir, 리팩토링 outdir, stamp
   - 출력:
     - (A안) FULL/1Y/2Y/3Y/5Y 성능표(동일 산식)
     - equity divergence 최초 날짜 및 이후 누적 오차
     - holdings divergence 최초 리밸런스 날짜 및 종목/비중 diff
3. **divergence 1개 날짜 고정 디버깅**
   - 최초 divergence 리밸런스 날짜에서 다음을 양쪽 모두 출력
     - 후보군(universe intersection)
     - fundamentals as-of date
     - 종목별 점수/랭크(상위 50)
     - SMA 통과 여부(require_above_sma)
     - market gate ON/OFF 판단 결과
   - 목표: “왜 종목 구성이 바뀌는지” 원인을 1개 요인으로 수렴

## P1 (동치 달성: 1~3일)
4. **fundamentals as-of 규약 동치**
   - 월말 기준일 산출 규칙(예: rebalance_date → 직전 분기/월말) 명문화 및 코드 일치
5. **SMA/체결 시점 오프셋 동치**
   - 결정일 기준으로 SMA를 평가하는지, 체결일 기준인지 동치화
6. **출력 규약(날짜 3분리) 확정 및 컬럼 고정**
   - holdings: rebalance_date
   - ledger/trades: trade_date (체결일)
   - snapshot/summary: asof_date (평가 기준일)
   - (운영정책) asof_date=실행일 유지 가능(단, parity 테스트는 별도 모드로)

## P2 (운영 전환: 3~7일)
7. **레거시 러너 제거/동결**
   - run_backtest_regime_s2_v4.py는 “참조용 고정”으로 두고 신규 기능 추가 금지
8. **run_backtest_v5 단일 엔트리로 표준화**
   - 옵션/도움말/예제 커맨드 문서화
9. **회귀 테스트(golden) 구축**
   - 특정 stamp 1~2개를 고정하여 CI/로컬에서 parity 체크 가능하도록 스크립트화
