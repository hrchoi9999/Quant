# PROJECT_STATE_REFACTOR_S2_2026-02-12 (KST)
> 작성일시: 2026-02-12 (KST)  
> 목적: **새 대화창에서 리팩토링 작업을 즉시 재개**할 수 있도록, 지난 대화에서 수행/패치/이슈/다음 액션을 **전체 리팩토링 작업 순서**에 맞춰 정리

---

## 0) 작업 환경 (고정 전제)
- OS/쉘: Windows + PowerShell
- Python venv: `D:\Quant\venv64`
- 프로젝트 루트: `D:\Quant`
- DB/데이터(현 시점 동결):
  - `D:\Quant\data\db\regime.db`
  - `D:\Quant\data\db\price.db`
  - `D:\Quant\data\db\fundamentals.db`
  - Universe CSV: `D:\Quant\data\universe\universe_mix_top400_20260205_fundready.csv`
  - **데이터 기준일(동결): 2026-02-06**
    - 리팩토링 완료 전까지 데이터 업데이트 중단하기로 합의(동치 검증을 위해)

---

## 1) 목표 정의 (동치 리팩토링 원칙)
### 1차 목표 (P1)
- **레거시 S2 전략을 리팩토링 시스템에서 “동치(Equivalence)”로 재현**
- 동치 기준:
  - 동일 입력 데이터(동결된 DB/Universe)
  - 동일 옵션(리밸런싱/게이트/수수료/슬리피지/필터 등)
  - 동일 산출물(CSV 구조/컬럼/값) 또는 **비교 가능한 형태로 변환 후 값 동일**
  - golden regression 테스트로 PASS

### 2차 목표 (P2)
- 레거시 전략의 잠재 버그/문제점을 분석 후 **S2-1(개선 전략)**로 분리하여 개선
- 단, P1 동치가 선행되어야 레거시 품질 평가가 가능

---

## 2) 디렉토리/산출물 구조 (리포트 & 비교 대상)
### 리팩토링 산출물 (현재 주 사용)
- outdir: `D:\Quant\reports\backtest_regime_refactor`
- 생성 CSV 패턴(예):
  - `regime_bt_equity_{stamp}.csv`
  - `regime_bt_summary_{stamp}.csv`
  - `regime_bt_holdings_{stamp}.csv`
  - `regime_bt_snapshot_{stamp}.csv`
  - `regime_bt_snapshot_{stamp}__trades.csv`
  - `regime_bt_trades_C_{stamp}.csv`
  - `regime_bt_ledger_{stamp}.csv`
  - `regime_bt_perf_windows_{stamp}.csv` (1y/2y/3y/5y 포함)

### “진짜 레거시(REAL)” 기준 산출물 위치(중요)
- 레거시 시스템이 2026-02-09에 생성한 실제 CSV:
  - `D:\Quant\src\backtest\outputs\backtest_regime`
  - 여기 있는 파일을 **레거시 진실원본(Ground Truth)**로 삼음
  - 예: `regime_bt_summary_..._20260206.csv` 의 LastWriteTime이 2026-02-09 17:48대

### Golden regression 폴더 이슈(경로 혼동 정리)
- 처음에는 `D:\Quant\reports\backtest_regime_golden`을 사용하려 했으나 **폴더가 존재하지 않아 오류**
- 실제 사용된 골든 폴더:
  - `D:\Quant\reports\backtest_regime_refactor_golden`
- 사용자가 `backtest_regime_refactor_golden__bak_20260211`로 백업 후
  - `Copy-Item "$cur\*${stamp}*.csv" $gold -Force`
  - golden을 **리팩토링 결과로 덮어쓰고** regression PASS 처리

> 의미: regression PASS는 “리팩토링 결과가 골든과 일치”를 의미할 뿐,  
> 골든 자체가 레거시 진실원본인지 여부는 별개.  
> 따라서 P1 동치 기준선은 “REAL 레거시 출력”으로 재정립 필요.

---

## 3) 핵심 실행 명령 (현재 안정화된 형태)
### (A) 리팩토링 S2 실행
```powershell
cd D:\Quant
$C="D:\Quant\reports\backtest_regime_refactor"
python .\src\backtest\run_backtest_s2_refactor_v1.py `
  --regime-db .\data\db\regime.db `
  --price-db .\data\db\price.db `
  --fundamentals-db .\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file .\data\universe\universe_mix_top400_20260205_fundready.csv `
  --ticker-col ticker `
  --start 2013-10-14 `
  --end 2026-02-06 `
  --horizon 3m `
  --rebalance W `
  --weekly-anchor-weekday 2 `
  --weekly-holiday-shift prev `
  --good-regimes 4,3 `
  --top-n 30 `
  --min-holdings 30 `
  --sma-window 140 `
  --require-above-sma `
  --market-gate `
  --market-sma-window 60 `
  --market-sma-mult 1.02 `
  --market-exit-mult 1.00 `
  --exit-below-sma-weeks 2 `
  --fee-bps 5 `
  --slippage-bps 5 `
  --snapshot-date 2026-02-06 `
  --outdir $C
```

### (B) 리팩토링 vs REAL 레거시 성능 비교 (summary)
```powershell
$stamp="3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206"
$legacy_real="D:\Quant\src\backtest\outputs\backtest_regime"
$ref="D:\Quant\reports\backtest_regime_refactor"

$L = Import-Csv "$legacy_real\regime_bt_summary_${stamp}.csv"
$R = Import-Csv "$ref\regime_bt_summary_${stamp}.csv"

"=== LEGACY (REAL) ==="; $L | Select cagr,sharpe,mdd,avg_daily_ret,vol_daily,rebalance_count | Format-List
"=== REFACTOR ===";      $R | Select cagr,sharpe,mdd,avg_daily_ret,vol_daily,rebalance_count | Format-List
```

### (C) 리밸런싱 날짜 확인 (수요일/휴일 전일)
- 레거시 원칙: 매주 수요일(휴일이면 전일) 리밸런싱 의사결정, **매수는 익일**
```powershell
$C="D:\Quant\reports\backtest_regime_refactor"
$stamp="3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206"
(Import-Csv "$C\regime_bt_holdings_${stamp}.csv" | ? { $_.rebalance_date -eq "2026-02-04" }).Count
(Import-Csv "$C\regime_bt_holdings_${stamp}.csv" | ? { $_.rebalance_date -eq "2026-02-06" }).Count
```

---

## 4) 파일 간 상관관계(리팩토링 구조)
### 엔트리 스크립트
- `src/backtest/run_backtest_s2_refactor_v1.py`
  - argparse로 옵션 수집
  - 전략 객체 생성(S2)
  - 코어 엔진 호출
  - 결과 번들 저장 + (레거시 호환) 출력 보정/채움(fill)

### 코어 엔진
- `src/backtest/core/engine.py`
  - 백테스트 루프/리밸런스 타이밍 처리
  - Strategy.decide() 호출 → RebalanceDecision(weights, meta)
  - 수익률/보유/현금/게이트 등 상태 업데이트
  - 일별 equity 시계열 출력 생성

### 전략
- `src/backtest/strategies/s2.py`
  - 레거시 S2(v2)와 동일한 종목 선정/필터/게이트/비중 산정 목표
  - 초기에 import 경로 오류(`from strategies...`)가 있었고, `src.backtest...` 체계로 수정

### 출력/호환 레이어
- `src/backtest/outputs/fill_bundle.py`
  - 엔진 출력(리팩토링 포맷)을 **레거시 산출물 포맷(CSV 컬럼/구조)**에 맞추기 위한 변환/보정 로직
- `src/backtest/outputs/legacy_reports.py`
  - snapshot/ledger 등 레거시 리포트를 생성하는 유틸 함수들
  - 최근 오류의 중심(특히 `rebalance_date` 컬럼, snapshot 구성 로직)

### 테스트(골든 리그레션)
- `src/backtest/tests/regression_s2_golden.py`
  - `--stamp`, `--golden-dir`, `--current-dir` 필요
  - 초기에는 args에 `sync_golden`이 없어서 AttributeError 발생 → 패치로 해결
  - 지금은 golden 폴더 자체가 “레거시=골든”인지, “리팩토링=골든”인지 정책 결정 필요

---

## 5) S2 전략 로직(요약) & 데이터 출처
> 아래는 “동치 구현을 위한 체크리스트” 관점 요약입니다.  
> 정확한 세부는 `run_backtest_s2_v5.py`, `run_backtest_regime_s2_v4.py`, `strategies/s2.py`를 기준으로 계속 맞추는 중.

### 입력 데이터/출처
- 가격: `price.db` (일봉 테이블, 예: `prices_daily`)
- 레짐: `regime.db` (날짜별 regime 정수코드)
- 펀더멘털 스코어: `fundamentals.db`의 월별 뷰
  - `--fundamentals-view s2_fund_scores_monthly`
  - (가정) 월말/월초 기준으로 `asof`를 정하고 해당월 스코어로 후보군 생성
- 유니버스: `universe_mix_top400_20260205_fundready.csv`
  - ticker 컬럼: `ticker`
  - fundready: 펀더멘털 결측 최소화된 종목군

### 의사결정/필터 구성 요소
- 리밸런싱: 주간(W), 앵커 weekday=2 (수요일), 휴일이면 전일(prev)
- regime 필터: `good_regimes = [4, 3]` (리스크온)
- 종목 선정:
  - 펀더멘털 score_rank 기반 상위(top_n=30) (오름차순 rank)
  - 최소 보유 종목수 `min_holdings=30` (미달 시 캐시/대체 로직 필요)
- SMA 필터:
  - 개별 종목 SMA(140) 위 조건(require-above-sma)
- 마켓 게이트:
  - KOSPI(or ALL) 시장지수 가격 vs 시장 SMA(60)
  - entry threshold = market_sma * market_sma_mult (1.02)
  - exit threshold = market_sma * market_exit_mult (1.00)
  - gate가 off이면 현금 비중 확대/전량 현금 등(레거시 동치 필요)
- 거래비용:
  - fee_bps=5, slippage_bps=5

### “수요일 리밸런스 vs 실제 매수일(익일)” 규칙 (중요)
- 레거시 원칙(사용자 인지):  
  - rebalance_date = 매주 수요일(휴일이면 전일) “결정일”  
  - buy_date = 익일(다음 거래일) “체결일”
- 리팩토링에서도 snapshot/ledger/트레이드 구성 시 이 규칙을 일관되게 반영해야 함

---

## 6) 이번 대화에서 발생/해결된 주요 이슈 타임라인(요약)
### 6.1 CLI 옵션 불일치
- 초기 에러: unrecognized arguments
  - `--rebalance-weekday`, `--holiday-shift`, `--strategy`, `--slip-bps`, `--enable-exit-below-sma` 등
- 해결:
  - 리팩토링 스크립트 argparse를 현재 옵션셋에 맞춤
  - good-regimes 입력도 `4 3` → `4,3` 형태로 정리(파서 일관화)

### 6.2 regression_s2_golden.py 인자/옵션 버그
- `args.sync_golden` AttributeError 발생
- 해결:
  - regression 스크립트에 해당 옵션/기본값 처리 패치

### 6.3 summary 컬럼 불일치
- `market_exit_mult` 컬럼이 golden에 없고 current에 생김 → extra_cols
- 처리:
  - golden을 current로 덮어써 PASS
  - 그러나 golden 정책(레거시 vs 리팩토링 기준선) 확정 필요

### 6.4 가장 큰 이슈: “CASH만 남는 snapshot” / n_holdings=0 문제
- 증상:
  - equity에서는 n_holdings>0 이 0으로 나오거나, snapshot이 CASH 1줄만 생성
  - 이후 일부 패치로 equity는 정상(보유 30)로 회복되었지만 snapshot은 여전히 CASH
- 원인 가설(강력):
  - snapshot 생성 로직이 **snapshot_date를 rebalance_date로 오인**
  - holdings_df에서 `rebalance_date == snapshot_date`로 필터 → 2/6에 해당 holdings가 없으니 CASH만 남음
- 관측 증거:
  - holdings에는 `rebalance_date=2026-02-04` 행이 존재(Count 31)
  - `rebalance_date=2026-02-06` 행은 0
  - snapshot은 2026-02-06이고 CASH 1줄

### 6.5 legacy_reports.py rebalance_date 컬럼 오류
- `KeyError: 'rebalance_date'` → snapshot/ledger 빌드 시 holdings_df에 rebalance_date 없다고 판단
- 원인:
  - holdings_df 컬럼명/생성 위치가 불일치하거나, fill_bundle에서 넘기는 DF가 다른 DF인 경우
- 최근 에러:
  - `ValueError: holdings_df must contain 'rebalance_date' column` (legacy_reports.py build_rebalance_ledger)

---

## 7) 패치된 파일들 목록 (이번 대화에서 적용/제공된 것)
> 일부는 사용자가 로컬에 이미 적용/테스트했고, 일부는 추가 적용 필요.  
> 버전 주석은 파일 상단에 `ver yyyy-mm-dd_xxx` 형태로 유지.

### 전략/엔진/런처 계열
- `src/backtest/strategies/s2.py`
  - NameError(weights 미정의) 수정
  - import 경로 문제 수정 (`from strategies...` → `from src.backtest...` 계열)
  - 결과적으로 `python -c "import src.backtest.strategies.s2 as s; print(s.__file__)..."` 성공

- `src/backtest/run_backtest_s2_refactor_v1.py`
  - 옵션 파싱/호환 보정 (good-regimes 등)
  - 출력 생성/채움(fill) 경로 정리

- `src/backtest/core/engine.py`
  - 일부 증상(보유 0) 관련 보정 시도(상태/결정 전달 등)

### 출력/레거시 호환 계열
- `src/backtest/outputs/fill_bundle.py`
  - summary에 `market_exit_mult`가 비어있던 문제를 채우는 보정 패치(1.00 반영)
- `src/backtest/outputs/legacy_reports.py`
  - snapshot 생성 시 `rebalance_date` 컬럼 전제 때문에 발생한 KeyError/ValueError에 대한 패치 시도
  - **현재도 rebalance_date 관련 오류가 재발**하여 추가 수정 필요

### “새로 제안된(아직 로컬 적용 여부 미확인) 핵심 패치”
- `legacy_reports.py`의 snapshot 로직을 아래 규칙으로 수정 필요:
  - decision_dt = max(rebalance_date <= snapshot_date)
  - exec_dt = next_trading_day(decision_dt)
  - snapshot은 snapshot_date(as-of) 기준 last_price 계산 + buy_date=exec_dt 반영
  - 이 부분이 동치에 결정적

---

## 8) 현재 ‘패치 이슈’ (해결되지 않은 핵심)
### 이슈 #1: snapshot이 CASH 1줄만 나오는 문제(최우선)
- 현상:
  - equity 마지막 행은 holdings=30, cash_weight=0.0인데
  - snapshot은 CASH 1.0만 존재
- 예상 원인:
  - snapshot 생성 함수가 holdings_df를 잘못 필터(= snapshot_date와 동일한 rebalance_date를 요구)
  - 또는 fill_bundle에서 snapshot 빌드에 넘기는 holdings_df가 “실제 holdings가 아닌 다른 DF”
- 해결 방향:
  1) snapshot 생성 함수에서 **decision_dt(<=asof) 선택**
  2) buy_date는 익일(다음 거래일)로 설정
  3) snapshot의 last_price는 asof 가격으로 평가
  4) fill_bundle가 snapshot 함수에 넘기는 DF가 올바른지 확인

### 이슈 #2: legacy_reports.py가 holdings_df에 rebalance_date 없다고 보는 문제
- 발생 에러:
  - `ValueError: holdings_df must contain 'rebalance_date' column`
- 현실 데이터:
  - 사용자가 확인한 `regime_bt_holdings_*.csv`는 `rebalance_date` 컬럼이 존재하고 값도 정상(2/4)
- 가능 원인:
  - legacy_reports.py에 전달되는 holdings_df는 CSV에서 읽은 holdings가 아니라 다른 DF
  - 컬럼명 변환 과정에서 rebalance_date가 date로 바뀌거나 drop됨
- 해결 방향:
  - `fill_bundle.py`에서 `build_snapshot_last_portfolio()`, `build_rebalance_ledger()` 호출 직전에
    - `print(holdings_df.columns)` 또는 로깅으로 컬럼 확인(임시)
  - 전달 DF를 “holdings CSV”와 동일한 스키마로 통일

### 이슈 #3: 동치 기준선(레거시 vs 골든) 정책 확정
- 현 상태:
  - golden은 사용자가 리팩토링 결과로 덮어써 PASS
- 권장:
  - P1 기간에는 “REAL 레거시 출력 폴더”를 golden으로 삼는 방식으로 회귀테스트 체계 재정립
  - 예) `--golden-dir D:\Quant\src\backtest\outputs\backtest_regime`

---

## 9) 앞으로 해야 할 작업(우선순위/체크리스트)
### P1-1 (최우선): snapshot 동치 복구
- 목표: snapshot에 최소 30개 종목 + (필요시) CASH가 표시되어야 함
- 해야 할 일:
  1) `legacy_reports.py`의 snapshot 빌드 함수(예: `build_snapshot_last_portfolio`) 수정
     - decision_dt/exec_dt 규칙 반영
  2) `fill_bundle.py`에서 snapshot 함수에 넘기는 DF 확인/정정
  3) 결과 검증:
     - `Measure-Object Count`가 1이 아니어야 함
     - buy_date가 decision_dt 다음 거래일인지 확인

### P1-2: ledger/trades_C 등 레거시 호환 리포트 동치 검증
- 목표: 레거시 산출물과 동일한 컬럼/값(또는 허용 가능한 변환 후 동일)
- 체크:
  - `regime_bt_trades_C`의 buy/sell 날짜 정합성(“결정일 vs 체결일”)
  - `regime_bt_ledger`가 “리밸런싱 이벤트”를 동일하게 기록

### P1-3: summary/equity/holdings의 최종 동치
- REAL 레거시와 수치 비교
  - equity tail(마지막 5일), 전체 시계열 샘플링 비교
  - summary: CAGR/Sharpe/MDD 등 일치 목표
- 불일치 시:
  - 첫 divergence 날짜를 찾는 디버그 스크립트 작성(날짜별 equity diff)

### P1-4: Golden regression 체계 확정(레거시=golden)
- `regression_s2_golden.py`의 기본 golden 경로를 REAL 레거시 출력으로 설정하거나
- 테스트 실행 시 golden-dir을 명시하여 운영

### P2(후순위): 2017년 이후 주간 리밸런싱 “룰 변경” 여부 확인
- 사용자가 기억하는 “2017년부터 주간 리밸런싱”이 레거시에 실제 존재하면,
  - 리팩토링에서도 기간별 정책 분기가 필요
- 확인 방법:
  - 레거시 스크립트(`run_backtest_regime_s2_v4.py`, `run_backtest_s2_v5.py`)에서
    - 2017 기준 분기 코드 존재 여부 확인

---

## 10) 빠른 진단용 원-라이너(다음 대화에서 바로 사용)
### (1) holdings 마지막 rebalance_date가 2026-02-04인지
```powershell
$C="D:\Quant\reports\backtest_regime_refactor"
$stamp="3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206"
Import-Csv "$C\regime_bt_holdings_${stamp}.csv" | % {$_.rebalance_date} | sort -Unique | select -Last 10
```

### (2) snapshot이 CASH만인지
```powershell
Import-Csv "$C\regime_bt_snapshot_${stamp}.csv" | measure | select Count
Import-Csv "$C\regime_bt_snapshot_${stamp}.csv" | select -First 20 | ft
```

### (3) REAL 레거시 vs 리팩토링 summary 비교
```powershell
$legacy_real="D:\Quant\src\backtest\outputs\backtest_regime"
$ref="D:\Quant\reports\backtest_regime_refactor"
$L = Import-Csv "$legacy_real\regime_bt_summary_${stamp}.csv"
$R = Import-Csv "$ref\regime_bt_summary_${stamp}.csv"
$L | select cagr,sharpe,mdd | fl
$R | select cagr,sharpe,mdd | fl
```

---

## 11) 진행상황표 (KST 기준)
| 단계 | 목표/작업 | 상태 | 근거/메모 | 다음 액션 |
|---|---|---|---|---|
| P0 | 실행/CLI 옵션 정리 | ✅ 완료 | argparse unrecognized args 해결, good-regimes 입력 정리 | 유지 |
| P0 | regression_s2_golden 인자 버그 | ✅ 완료 | `sync_golden` AttributeError 패치 | 유지 |
| P0 | summary 컬럼(market_exit_mult) 채움 | ✅ 완료(형식) | current에 market_exit_mult 생성/채움 | 레거시/골든 정책 확정 필요 |
| P1 | 엔진에서 S2 실행/보유 생성 | ✅ 완료(부분) | n_holdings>0 행 1298 등 정상 구간 확인됨 | 최종 동치 검증 |
| P1 | **snapshot 동치(종목 보유 표기)** | ❌ 미완료(핵심 이슈) | snapshot이 CASH 1줄만 나오는 케이스 반복 | legacy_reports/ fill_bundle snapshot 로직 수정 |
| P1 | ledger/trades_C 동치 | ⏳ 대기 | legacy_reports에서 rebalance_date 오류 재발 | holdings_df 전달 스키마 확정 후 진행 |
| P1 | REAL 레거시 출력과 성능 동치 | ⏳ 대기 | REAL summary 대비 refactor 수치 불일치 발생했었음 | snapshot/ledger 정리 후 본격 비교 |
| P1 | “레거시=골든” 회귀체계 확정 | ⏳ 보류 | 현재는 refactor 결과로 golden 덮어씀 | REAL 폴더를 golden 기준선으로 재설정 |
| P2 | 레거시(2017~) 정책 분기 확인 | ⏳ 보류 | 사용자의 기억: 2017부터 주간 리밸런싱/윈도우 평가 | 레거시 코드에서 분기 존재 여부 확인 |
