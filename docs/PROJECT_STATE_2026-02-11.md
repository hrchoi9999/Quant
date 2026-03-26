# PROJECT_STATE.md (퀀트투자 시스템 리팩토링) — 2026-02-11

> 목적: **리팩토링을 안전하게 마무리하기 위한 상태/결정/산출물/이슈/다음 작업** 정리  
> 기준일: 2026-02-11 (KST)  
> 참고(어제 기준 상태): `PROJECT_STATE_2026-02-10.md` fileciteturn24file0

---

## 0) 오늘 결론 요약

- **P0(레거시 실행/산출물 풀세트) 안정화 완료**: 레거시 실행에서 **CSV 8종 풀세트 생성** 및 Google Sheet 업로드 정상 확인.
- **P1(리팩토링 엔진 실행) 진행**: 리팩토링 경로에서 발생하던 일련의 크래시/시그니처/의존성 문제를 단계적으로 해결하여
  - `--s2-refactor` 경로에서 **리팩토링 러너가 끝까지 실행되고 CSV 8종이 생성되는 상태**까지 도달.
- 다만 **P1의 핵심 목표(레거시 스키마/내용 동치)**는 아직 미완:
  - 리팩토링 산출물은 8종은 생성되지만, 일부 파일의 **컬럼이 “최소 스키마(minimal)”로 남아 레거시와 불일치**.
  - 즉, “fill(legacy schema filling)” 단계가 완전 적용되지 않았거나, 저장 대상이 filled bundle이 아니라 base/minimal bundle일 가능성이 높음.
- **중요 파라미터 고정**: `--market-sma-mult 1.02`(entry=1.02)는 앞으로 레거시/리팩토링 모두 동일하게 유지.

---

## 1) 개발 환경/전제(오늘 확인 포함)

- OS/경로: Windows / `D:\Quant`
- Python venv: `D:\Quant\venv64` (Python 3.10.11)
  - Google API 라이브러리의 **Python 3.10 지원 종료(2026-10-04)** FutureWarning 확인(즉시 조치 필요는 아님).
- DB(고정)
  - `..\..\data\db\regime.db`
  - `..\..\data\db\price.db`
  - `..\..\data\db\fundamentals.db`
- Universe(고정)
  - `..\..\data\universe\universe_mix_top400_20260129_fundready.csv`
- 비교 기준 Stamp(고정)
  - `3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206`

---

## 2) 시스템 구성(레거시 vs 리팩토링) — 파일 역할/상관관계

### 2.1 레거시 시스템(기준선)

- **엔트리/실행체**
  - `run_backtest_s2_v5.py`  
    - 기존(레거시) 백테스트 실행 스크립트(옵션/기본값 포함).  
- **출력(레거시 스키마)**
  - 8종 CSV가 레거시 스키마로 생성됨(아래 “산출물” 섹션 참고).
  - Google Sheet 업로드 기능이 작동(시트 생성 로그 확인).

> 레거시는 “정답(동치 기준)”이며, 리팩토링 결과는 반드시 레거시와 동치(내용/컬럼/정렬 규칙 포함)여야 함.

### 2.2 리팩토링 시스템(목표: 레거시 동치 + 구조화)

- **래퍼/라우터**
  - `run_backtest_v5.py`
    - `--s2-refactor`(리팩토링 경로)와 `--delegate-legacy`(레거시 위임) 라우팅을 제공하는 엔트리 래퍼.
    - 오늘 `--delegate-legacy` 인자 처리 문제가 있었고(레거시에서 인자 미인식), 래퍼 측에서 레거시 호출 시 인자를 제거/변환하도록 정리됨(작업 흐름 상).
- **리팩토링 러너(실행 본체)**
  - `run_backtest_s2_refactor_v1.py`
    - 리팩토링 엔진을 사용하여 백테스트 수행 → 출력 번들을 생성하고 CSV 저장/시트 업로드를 수행하는 역할.
- **핵심 모듈(구조화 레이어)**
  - `core/engine.py`
    - 백테스트 계산 엔진(리턴 스키마/호출 시그니처가 중요한 조정 포인트였음).
  - `strategies/base.py`, `strategies/s2.py`
    - 전략 공통 인터페이스/타입 및 S2 구현. 오늘 `Strategy` 심볼 import 문제 해결.
  - `outputs/csv_plugin.py`, `outputs/fill_bundle.py`
    - CSV 번들 저장 및 “레거시 스키마 채움(fill)” 처리.
    - 오늘 `holdings_df` 누락으로 fill 단계에서 런타임 에러가 발생했고, 이후 holdings_df 공급 경로를 보완.

---

## 3) 오늘 진행된 작업(타임라인 형태로 정리)

> 아래는 “오늘 실제로 발생한 문제 → 조치 → 결과” 흐름 기준입니다.

### 3.1 P0 관련: 레거시 실행/산출물(Golden/Regression 포함)

1) 레거시 결과를 Golden 폴더로 복사하는 과정에서 PowerShell 변수 치환/경로 문제 확인
   - `$G`가 폴더가 아니라 **파일로 생성**되어 Copy/dir가 꼬이는 상황 발생
   - 해결: `Rename-Item`으로 파일 백업 후, 동일 이름 디렉터리 재생성 → 복사 정상화
2) Golden Regression(`regression_s2_golden.py`)이 참조하는 필수 파일(`regime_bt_summary_<stamp>.csv` 등)이 Golden에 없어서 `FileNotFoundError` 발생
   - 해결: 레거시 산출물에서 summary/snapshot 등 필수 파일을 Golden으로 복사
3) 회귀 테스트 PASS 확인
   - 최종적으로 `regression_s2_golden.py` 실행 결과 **[PASS]** 확보

> 결론: P0은 “기준선 고정 + 회귀 테스트 PASS” 상태로 안정화.

### 3.2 P1 관련: 리팩토링 경로 크래시 제거(연쇄 이슈 해결)

리팩토링 러너(`run_backtest_s2_refactor_v1.py`)를 실제로 실행하면서 아래 이슈들이 순차적으로 발생했고, 각각 패치로 해결:

1) **ImportError**
   - `strategies.s2`에서 `from strategies.base import Strategy, RebalanceDecision` 시 `Strategy`를 찾지 못함
   - 조치: `strategies/base.py`에서 `Strategy`(및 관련 타입) 정의/노출 구조를 리팩토링 코드가 기대하는 형태로 정리
2) **TypeError: run_backtest() got an unexpected keyword argument 'ret_wide'**
   - 리팩토링 러너가 `core.engine.run_backtest`에 `ret_wide` 인자를 넘기는데 엔진 시그니처가 불일치
   - 조치: 엔진 시그니처를 “호환(compat)” 형태로 조정
3) **SyntaxError: non-default argument follows default argument**
   - 엔진 함수 정의에서 파라미터 기본값/비기본값 순서 오류
   - 조치: 함수 시그니처 순서 재정렬(문법 오류 제거)
4) **RuntimeError: fill_legacy_outputs requires holdings_df**
   - fill 단계가 레거시 스키마 생성에 `holdings_df`를 필요로 하나, 호출 시 제공되지 않음
   - 조치: holdings_df 생성/전달 경로를 보완(Guard 포함)

> 결론: 리팩토링 러너가 “끝까지 실행되며 CSV 8종 생성”까지 도달.

---

## 4) 산출물 상태(레거시 vs 리팩토링) — 오늘 확인된 핵심 차이

### 4.1 공통: 파일 개수(8종)는 동일하게 생성됨

- `regime_bt_equity_<stamp>.csv`
- `regime_bt_holdings_<stamp>.csv`
- `regime_bt_ledger_<stamp>.csv`
- `regime_bt_perf_windows_<stamp>.csv`
- `regime_bt_snapshot_<stamp>.csv`
- `regime_bt_snapshot_<stamp>__trades.csv`
- `regime_bt_summary_<stamp>.csv`
- `regime_bt_trades_C_<stamp>.csv`

### 4.2 핵심 문제: 리팩토링 CSV가 “최소 스키마”로 남아 있음

오늘 사용자가 직접 헤더를 덤프한 결과:

- **레거시 equity 헤더(예시)**  
  `date,port_ret,equity,market_ok,market_price,market_sma,market_entry_th,market_exit_th,n_holdings,...`
- **리팩토링 equity 헤더(예시)**  
  `date,equity,port_ret`  ← market gate 관련 컬럼이 없음

- **레거시 holdings 헤더(예시)**  
  `strategy,rebalance_date,fund_asof_date,ticker,weight,regime,regime_score,growth_score,score_rank,...,market_sma_mult,market_entry_mult,market_exit_mult`
- **리팩토링 holdings 헤더(예시)**  
  `rebalance_date,ticker,weight` ← 전략/팩터/시장게이트 정보가 없음

- trades/trades_c/ledger/summary도 리팩토링 쪽은 컬럼이 축약(최소 스키마).

#### 의미(진단)
- “8개 파일이 생성된다”는 것은 **저장 파이프라인은 돌아간다**는 뜻이지만,
- 레거시 동치 목표 관점에서는 **가장 중요한 단계(레거시 스키마 채움: fill)가 완전 적용되지 않은 상태**.
- 따라서 다음 단계는:
  1) `outputs/fill_bundle.py`가 생성하는 “filled bundle(레거시 스키마)”이 실제 저장에 사용되는지 확인
  2) 저장 대상이 base/minimal bundle로 고정되어 있으면 `run_backtest_s2_refactor_v1.py` 저장부 수정

---

## 5) 오늘 사용한(확정) 실행 커맨드 스냅샷

> 사용자의 요청으로, 앞으로는 `--market-sma-mult 1.02`를 레거시/리팩토링 모두 동일 적용.

### 5.1 레거시(위임) 실행 예시
```powershell
cd D:\Quant\src\backtest

$OUT_L="D:\Quant\reports\backtest_regime_refactor_legacy"

python .\run_backtest_v5.py `
  --s2-refactor `
  --delegate-legacy `
  --regime-db ..\..\data\db\regime.db `
  --regime-table regime_history `
  --price-db ..\..\data\db\price.db `
  --price-table prices_daily `
  --fundamentals-db ..\..\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file ..\..\data\universe\universe_mix_top400_20260129_fundready.csv `
  --ticker-col ticker `
  --horizon 3m `
  --start 2013-10-14 `
  --end 2026-02-06 `
  --rebalance W `
  --weekly-anchor-weekday 2 `
  --weekly-holiday-shift prev `
  --good-regimes 4,3 `
  --top-n 30 `
  --min-holdings 15 `
  --sma-window 140 `
  --require-above-sma `
  --market-gate `
  --market-scope KOSPI `
  --market-sma-window 60 `
  --market-sma-mult 1.02 `
  --market-exit-mult 1.00 `
  --exit-below-sma-weeks 2 `
  --fee-bps 5 `
  --slippage-bps 5 `
  --snapshot-date 2026-02-06 `
  --trades-lookback-years 6 `
  --outdir $OUT_L
```

### 5.2 리팩토링(엔진) 실행 예시
```powershell
cd D:\Quant\src\backtest

$OUT_R="D:\Quant\reports\backtest_regime_refactor_refactor"

python -m backtest.run_backtest_v5 --s2-refactor
  --s2-refactor `
  --regime-db ..\..\data\db\regime.db `
  --regime-table regime_history `
  --price-db ..\..\data\db\price.db `
  --price-table prices_daily `
  --fundamentals-db ..\..\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file ..\..\data\universe\universe_mix_top400_20260129_fundready.csv `
  --ticker-col ticker `
  --horizon 3m `
  --start 2013-10-14 `
  --end 2026-02-06 `
  --rebalance W `
  --weekly-anchor-weekday 2 `
  --weekly-holiday-shift prev `
  --good-regimes 4,3 `
  --top-n 30 `
  --min-holdings 15 `
  --sma-window 140 `
  --require-above-sma `
  --market-gate `
  --market-scope KOSPI `
  --market-sma-window 60 `
  --market-sma-mult 1.02 `
  --market-exit-mult 1.00 `
  --exit-below-sma-weeks 2 `
  --fee-bps 5 `
  --slippage-bps 5 `
  --snapshot-date 2026-02-06 `
  --trades-lookback-years 6 `
  --outdir $OUT_R
```

---

## 6) 오늘 확인된 “왜 진도가 안 나가는 것처럼 보였는가”의 기술적 원인(정리)

- 오늘의 반복/혼선은 “명령어/기능이 아니라 **상태 확인(레거시 vs 리팩토링 산출물 비교)** 과정이 길어진 것”이 본질.
- 리팩토링 경로는 실행이 한 번에 성공하지 않고, 아래처럼 **연쇄적으로 터지는 타입/시그니처/의존성 문제를 선행 제거**해야 했음:
  - ImportError → TypeError(ret_wide) → SyntaxError(signature order) → RuntimeError(holdings_df required)
- 이 단계들을 제거한 결과, 리팩토링은 “실행/저장”은 가능해졌지만,
  - 아직 “동치”의 핵심인 **레거시 스키마 채움(fill) 적용**이 완전하지 않아, 결과 비교에서 계속 “불일치”가 발생.

---

## 7) 리팩토링 전체 진행 상황표 (ID 1~10, 어제 양식/번호 유지) — 2026-02-11 기준 현행화

> 어제 파일의 ID 체계를 유지하되, **오늘 진행 내용을 반영**하여 상태를 업데이트했습니다. fileciteturn24file0

| ID | 작업 묶음 | 난이도 | 상태(오늘 기준) | 오늘 실제 한 일(구체) | 다음 해야 할 일(구체) |
|---:|---|:---:|---|---|---|
| 1 | Golden fixture 정리/배치 | ★★☆☆☆ | Done | (추가 이슈) Golden 경로가 파일로 생성되어 복사 실패 → 파일 백업 후 디렉터리 재생성 | Golden 경로 생성/검증을 스크립트화(실수 방지) |
| 2 | Regression 크래시 제거 | ★★★☆☆ | Done | `FileNotFoundError` 원인(필수 파일 미복사) 해결 후 PASS 재확인 | 비교 범위(예: `__trades`) 포함 여부 점검/확장 |
| 3 | Snapshot 정보컬럼(name) 정책 | ★★☆☆☆ | Done | 레거시/리팩토링 헤더 덤프로 컬럼 불일치 지점 가시화 | “표시용 컬럼”과 “동치용 컬럼” 분리 규칙 문서화 |
| 4 | 레거시 위임 실행/CSV 풀세트 산출 | ★★★☆☆ | Done | `--delegate-legacy` 실행으로 8종 CSV + GSheet 생성 확인 | 레거시 호출 인터페이스/옵션 정합성 고정 |
| 5 | fee/slippage parity(5/5) | ★★★☆☆ | Done | 오늘도 동일 값으로 실행 확인 | 숨은 기본값(예: rounding/close alignment) 동치 점검 |
| 6 | RBW golden 갱신 + PASS | ★★★★☆ | Done | Golden 경로 문제 해결 후 PASS 유지 | Golden 갱신/백업 자동화(옵션) |
| 7 | refactor 엔진 parity 포팅 시작 | ★★★★★ | In Progress | 리팩토링 러너 크래시 연쇄 해결 → “실행 + 8종 CSV 생성”까지 도달 | **핵심**: fill_bundle 적용/저장 대상 수정 → 레거시 스키마/내용 동치 달성 |
| 8 | RBM fixture 추가 | ★★☆☆☆ | Pending | (오늘은 RBW 집중) | RBM 실행 stamp 생성 → golden 추가 |
| 9 | RBM golden PASS | ★★★★☆ | Pending | - | RBM 회귀 PASS |
| 10 | 표준 커맨드/문서화 | ★★☆☆☆ | In Progress | 레거시/리팩토링 실행 커맨드 정리, market-sma-mult=1.02 고정 | “운영용 표준 커맨드 2종(RBW/RBM)” 확정본 문서화 |

---

## 8) 내일(또는 다음 세션) 최우선 작업(“동치 마무리” 실행 계획)

### 8.1 P1 동치의 핵심: “filled bundle 저장” 강제

- 목표: 리팩토링 결과의 8종 CSV가 레거시와 동일한 컬럼/형태로 저장되도록
  - `run_backtest_s2_refactor_v1.py`의 저장부에서
    - base/minimal bundle이 아니라
    - `fill_legacy_outputs(...)`가 만든 **filled bundle**을 저장하도록 확정해야 함.

### 8.2 확인 절차(짧고 확실하게)

1) 동일 stamp로 레거시/리팩토링 각각 실행(시장 entry=1.02 유지)
2) 각 CSV의 헤더 1줄 비교(사용자가 오늘 수행한 헤더 덤프 방식 그대로)
3) 불일치 파일부터 fill 단계 입력(holdings_df, market meta, fundamentals meta 등) 보강
4) `diff_s2_outputs`(3-3)로 내용 비교까지 확장

---

## 9) 오늘 변경/패치된 파일 목록(요약)

> 오늘은 “리팩토링 실행 크래시 제거”와 “fill 입력(holdings_df) 보강”이 중심이었음.

- `core/engine.py` : 시그니처/호환(ret_wide) 관련 조정, 문법 오류 수정
- `strategies/base.py` : `Strategy` 심볼 노출/정의 정리(ImportError 해결)
- `strategies/s2.py` : base 인터페이스에 맞춘 import/구성 조정
- `outputs/fill_bundle.py` : holdings_df 요구사항 관련 처리(런타임 에러 대응)
- (래퍼) `run_backtest_v5.py` : 레거시 위임/리팩토링 라우팅 관련 정리(운영 관점에서 중요)

---

## Appendix) 오늘 기준 “정리된 사실” 3줄

1) 레거시는 8종 CSV가 레거시 스키마로 안정 생성된다.  
2) 리팩토링도 8종 CSV 생성까지는 성공했으나, 일부는 최소 스키마로 남아 동치가 깨져 있다.  
3) 다음 1-step은 “filled bundle 저장 강제”이며, 이게 해결되면 P1 동치 마무리로 급격히 수렴한다.

