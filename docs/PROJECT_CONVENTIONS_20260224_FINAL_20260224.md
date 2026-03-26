# PROJECT_CONVENTIONS_20260222

> 업데이트: 2026-02-23

## A. 실행 방식(Entrypoint) 단일화

1)  작업 디렉터리는 항상 D:`\Quant  `{=tex}
2)  백테스트 실행은 항상 모듈 실행(python -m)만 허용
    -   ✅ python -m src.backtest.run_backtest_v5 ...
    -   ❌ cd src`\backtest `{=tex}후 python run_backtest\_\*.py\
3)  코드 내부에서 subprocess로 파이썬 파일 직접 실행 금지
    -   ❌ subprocess.run(\["python", "run_backtest_s2_refactor_v1.py",
        ...\])
    -   ✅ import 후 main(args) 호출 방식 사용

## B. import 규칙 단일화

1)  src/backtest 내부 코드는 패키지 기준 import만 사용
    -   권장: from src.backtest.core.tickers import normalize_ticker\
2)  다음 패턴은 전면 금지
    -   ❌ from core.xxx import ...
    -   ❌ from outputs.xxx import ...
    -   ❌ sys.path.insert(...)\
3)  try/except ImportError로 dual-mode import는 임시 대응 외 금지

## C. 패키지 구조 강제

1)  다음 폴더에 **init**.py 존재 보장
    -   src/
    -   src/backtest/
    -   src/backtest/core/
    -   src/backtest/outputs/
    -   src/backtest/strategies/
2)  VSCode workspace root는 D:`\Quant로 `{=tex}고정

## D. 수정 시 준수 사항

1)  모든 파일에 버전 헤더 유지\
2)  변경 순서: 문서 수정 → 코드 수정 → 검증 커맨드 기록\
3)  새 대화창 시작 시 반드시 아래 파일 확인
    -   PROJECT_STATE
    -   PROJECT_CONVENTIONS
    -   TODO_REFACTOR

## E. 검증 커맨드 표준

1)  python -m py_compile ...
2)  python -c "import src.backtest...."
3)  python -m src.backtest.run_backtest_v5 ...


## S2 리밸런싱 규약 (Legacy Canonical Rule)

1. 리밸런싱 주기

    S2 전략은 --rebalance W 기준
    기준 요일: 수요일 (weekly-anchor-weekday=2)
    공휴일인 경우 holiday_shift='prev' 적용

2. 리밸런싱 날짜의 의미

    생성되는 날짜는 결정일 (Decision Date)
    해당 날짜 종가 기준으로 종목 선정

3. 실제 거래 반영 시점

    포트폴리오 변경은 다음 거래일 (T+1) 에 체결
    수익 계산도 익일부터 반영

### 3-1. 결정/체결/가격/비용 규약 확정 (2026-02-23)

- **Fundamentals as-of 매핑 기준:** `decision_date` 기준 (월간 데이터는 `decision_date` 이하의 최신 `fund_date`로 매핑)
- **Market Gate 판단 기준:** `decision_date`의 종가(close) 기준
- **체결(매수/매도) 가격 기준:** `execution_date(T+1)`의 종가(close) 기준
- **Fee/Slippage 적용 시점:** `execution_date(T+1)` 기준으로 비용 차감(체결일에 거래비용 반영)


4. Snapshot 날짜 규약

    --snapshot-date는 리밸런싱 날짜와 무관
    단순히 “백테스트 종료 기준일”
    파일명(stamp)에 포함되나, 리밸런싱 회차에 영향을 주지 않음

5. 비용 규약

    기본 검증 기준은 총 10bps
    fee_bps + slippage_bps = 10
    레거시 검증 시 항상 동일 조건 유지

6. 출력 스키마 기준

    holdings의 날짜 컬럼은 rebalance_date
    ledger의 거래 날짜는 trade_date
    trades_C는 buy_date / sell_date / return_pct 포함



    # TODO_REFACTOR_20260220_V1

## 완료된 항목

- 실행 안정화
- Fundamentals as-of 하드 고정
- Market proxy 계산 동치 1차 적용
- Selection CSV 정상화

---

## P1 (현재 진행)

1. Market scope 완전 동치 검증
2. 최초 divergence 재탐지
3. Holdings 기반 divergence 원인 수렴
4. Regression 자동 비교 스크립트 정비

---

## P2 (운영 전환 단계)

1. 레거시 러너 동결
2. run_backtest_v5 단일 엔트리 확정
3. Golden regression 자동화 체계 구축
4. 전략 확장 대비 회귀 테스트 구조화



# PROJECT_CONVENTIONS_20260224

> 업데이트: 2026-02-24

## 0. 기준(Definition of Done / Canonical)

- **리팩토링(refactor) 결과가 프로젝트의 기준(Canonical)입니다.**
- 레거시(legacy)는 과거 참고용이며, **레거시와의 수치 동치(parity) 달성은 더 이상 목표가 아닙니다.**
- 다만, 레거시에서 정리된 실행/거래/날짜 규약 중 **프로젝트 규약으로 채택된 항목은 유지**합니다.

## A. 실행 방식(Entrypoint) 단일화

1) 작업 디렉터리: `D:\Quant`
2) 백테스트 실행은 **모듈 실행**만 허용
   - ✅ `python -m src.backtest.run_backtest_v5 ...`
   - ❌ `cd src\backtest` 후 `python run_backtest_*.py ...`
3) 코드 내부에서 **subprocess로 파이썬 실행 금지**
   - ❌ `subprocess.run(["python", "..."])`
   - ✅ `import` 후 `main(argv)` 호출 방식

## B. import 규칙 단일화

1) `src/backtest` 내부 코드는 **패키지 기준 import만 사용**
   - 권장: `from src.backtest.core.tickers import normalize_ticker`
2) 다음 패턴은 전면 금지
   - ❌ `from core.xxx import ...`
   - ❌ `from outputs.xxx import ...`
   - ❌ `sys.path.insert(...)`
3) `try/except ImportError`로 dual-mode import는 임시 대응 외 금지

## C. 패키지 구조 강제

1) 다음 폴더에 `__init__.py` 존재 보장
   - `src/`
   - `src/backtest/`
   - `src/backtest/core/`
   - `src/backtest/outputs/`
   - `src/backtest/strategies/`
2) VSCode workspace root: `D:\Quant` 고정

## D. 수정/패치 규약

1) 모든 수정 파일은 상단에 **버전 헤더** 유지  
   - 예: `# <file>.py ver YYYY-MM-DD_NNN`
2) 변경 순서: **문서 수정 → 코드 수정 → 검증 커맨드 기록**
3) 새 대화창 시작 시 아래 파일 우선 확인
   - `PROJECT_STATE_*.md`
   - `PROJECT_CONVENTIONS_*.md`
   - `TODO_REFACTOR_*.md`

## E. 비용(수수료/슬리피지) 표준

- 프로젝트 표준은 **fee 5 bps + slippage 5 bps = 총 10 bps** 입니다.
- 실행 커맨드에서 명시하지 않으면, wrapper/runner는 기본값을 **5/5로 동작**하도록 유지합니다.

## F. 검증 커맨드 표준

1) `python -m py_compile <file1> <file2> ...`
2) 실제 실행
   - `python -m src.backtest.run_backtest_v5 ...`
3) 산출물 확인: snapshot/summary/ledger/trades(perf_windows 포함) 생성 여부 확인
---

# 2026-02-24 세션 종료 반영(추가/정정 로그)

> 원칙: 기존 내용을 삭제하지 않고, 변경은 **정정 표시**로 남깁니다.

## [정정] 레거시 동치(parity) 관련 목표
- (기존 문서/대화 일부에서) 레거시 결과를 Golden으로 두고 완전 동치를 목표로 했던 부분은,
  **2026-02-24부로 목표에서 제외**되었습니다.
- ~~레거시와의 수치 동치(parity) 달성은 목표~~ → **정정: Refactor를 Canonical로 확정(유지)**

## [추가] Google Sheet 업로드 규약(Refactor Canonical)
- Refactor 실행에서 `--gsheet-enable` 사용 시, 다음 탭(시트)이 업로드 대상입니다.
  - `{
    snapshot: <prefix>_snapshot,
    windows: <prefix>_windows,
    trades: <prefix>_trades,
    ledger: <prefix>_ledger,
    summary: <prefix>_summary
    }`

- 탭이 없으면 **자동 생성 후 업로드**합니다(탭명 안전 quoting 포함).

## [추가] Credential 경로 권장
- 서비스계정 JSON은 `D:\Quant\config\` 하위 보관을 기본으로 합니다.
- 실행 옵션 예:
  - `--gsheet-cred .\config\<service_account>.json`
