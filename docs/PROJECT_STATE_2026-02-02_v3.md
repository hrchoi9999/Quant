# Quant 프로젝트 상태 정리 (S1/S2 · Regime 백테스트) — 2026-02-02 (KST)

> 목적: 내일(새 대화창) 이어서 작업할 때 혼란이 없도록, **오늘 진행된 내용/결론/미해결 이슈/다음 액션**을 최대한 상세히 정리합니다.  
> 작업 경로(사용자 PC): `D:\Quant` (Windows + PowerShell, venv64, Python 3.10.11)

---

## 0) 오늘의 큰 흐름 요약

1. **유니버스 CSV 4개**(mix_top400 계열) 존재 확인 및 “어떤 파일을 백테스트에 쓸지” 논의 시작
2. **regime.db의 `regime` 타입(BLOB 문제)**는 이미 해결되어 **INTEGER로 저장됨**을 확인
3. **S2 전략**을 S1 백테스트 스크립트(기존 v2)를 기반으로 새로 만들고 실행
4. 실행 중 발생한 오류들(duplicate labels, normalize_ticker 누락, MDD=0 등)을 단계별로 수정
5. 성과가 나쁘거나 이상하게 나오는 원인을 추적하다가,
   - **fundamentals_monthly_mix400_20260129 테이블의 중복 구조/결측치/score clumping(상한값 뭉침)** 문제를 발견
6. **중복 제거(dedup) 테이블 생성**까지 완료
7. 그러나 dedup 이후에도 **growth_score가 특정 값(예: 156.00, 280.75 등)으로 과도하게 뭉치고, YoY 컬럼 결측이 매우 큼**이 확인됨
8. “개선방안 확정 전에는 코드 수정 중단” 합의 → **SQL/검증부터** 진행하기로 방향 전환

---

## 1) 사용된/생성된 핵심 파일 목록

### 1-1. 유니버스 CSV (오늘 확인된 4개)
- `universe_mix_top400_20260129.csv`
- `universe_mix_top400_20260129_priceready.csv`
- `universe_mix_top400_20260129_fundready.csv`
- `universe_mix_top400_20260129_dartready.csv`

> 논점: “ready”의 의미가 서로 다름(가격/펀더/다트 기준으로 데이터 준비가 된 종목만 포함하는지)  
> 실제 백테스트(S2) 실행에는 `fundready`를 사용함:
- 사용 예: `.\data\universe\universe_mix_top400_20260129_fundready.csv`
- 로딩 로그상 tickers=382, name_col=name (names=187)

### 1-2. DB 파일
- `D:\Quant\data\db\price.db` (table: `prices_daily`)
- `D:\Quant\data\db\regime.db` (table: `regime_history`)
- `D:\Quant\data\db\fundamentals.db` (table: `fundamentals_monthly_mix400_20260129`, dedup 테이블 생성됨)
- `D:\Quant\data\db\dart_main.db` (상장사/종목 매핑 및 DART 기반 테이블들)

### 1-3. 백테스트 스크립트 (S2)
- 사용자 측 최종 파일명: `D:\Quant\src\backtest\run_backtest_regime_s2_v1.py`
- 중간에 patched 파일들이 여러 번 생성됨(샌드박스/임시): `_patched4 ~ _patched7` 등  
  (핵심: 사용자 PC에서 실제 실행한 것은 최종 `run_backtest_regime_s2_v1.py`)

### 1-4. 백테스트 결과 산출물(예시)
- `D:\Quant\reports\backtest_regime\...summary....csv`
- `D:\Quant\reports\backtest_regime\...equity....csv`
- `D:\Quant\reports\backtest_regime\...holdings....csv`
- `D:\Quant\reports\backtest_regime\...snapshot....csv`  
  ※ snapshot에 종목명(name) 포함 요청이 있었고, 코드에 반영하는 수정이 진행됨(최종 반영 여부는 내일 파일 확인 필요)

---

## 2) 핵심 확인 사항 (확정된 사실)

### 2-1. regime_history의 `regime` 컬럼 타입
사용자 로그로 확인:
- `select typeof(regime), count(*) from regime_history group by typeof(regime)` → `integer 2182846`
- `check_regime_db_types.py` 결과:
  - `[typeof(regime)] [('integer', 2182846)]`
  - `[distinct regime by horizon] [('1y', 5), ('3m', 5), ('6m', 5)]`
  - sample rows에서 `regime` 값이 1~5 정수로 확인

✅ 결론: **regime BLOB 문제는 현재 해결된 상태(정수형)**

### 2-2. 유니버스-가격-레짐 말단일(end) 매칭에서 제외된 종목
S2 실행 로그에서:
- `[INFO] excluded tickers (missing price/regime at end): n=3 | 388210, 486990, 488900`

✅ 결론: **end date(2026-01-29) 기준 price/regime가 부족한 종목 3개는 제외된 채 진행**

---

## 3) S2 전략/백테스트 구현 및 실행 파라미터(오늘 기준)

### 3-1. S2 전략 개요(오늘 대화에서 정리된 범위)
- Regime 필터: 기본 horizon `3m`, good regimes = `[4, 3]` (상승/우호 국면)
- Universe: mix_top400 (KOSPI+KOSDAQ 혼합), 실제 로딩 tickers=382
- 펀더멘털 스코어: `growth_score` (w_rev=0.5, w_op=0.5로 설정)
  - 내부적으로 revenue_yoy, op_income_yoy도 컬럼으로 읽음
- 가격 필터: 개별 종목 `SMA120` 이상만 매수 후보(기본 require_above_sma=True)
- 리밸런싱:
  - 초기 월(M) → 이후 주(W)로 변경하여 테스트
- **추가 안전장치(시장 게이트)**:
  - KOSPI 지수(또는 KOSPI scope 자산)의 SMA120 대비 **1.05배 이하로 급락** 시 **100% CASH**
  - args: `--market-gate --market-scope KOSPI --market-sma-window 120 --market-sma-mult 1.05`

### 3-2. 실행 커맨드(사용자 최종 실행)
```powershell
python .\src\backtest\run_backtest_regime_s2_v1.py `
  --strategy S2 `
  --universe-file .\data\universe\universe_mix_top400_20260129_fundready.csv `
  --ticker-col ticker `
  --price-db .\data\db\price.db `
  --price-table prices_daily `
  --regime-db .\data\db\regime.db `
  --regime-table regime_history `
  --fundamentals-db .\data\db\fundamentals.db `
  --fundamentals-table fundamentals_monthly_mix400_20260129 `
  --start 2017-03-01 `
  --end 2026-01-29 `
  --top-n 50 `
  --sma-window 120 `
  --rebalance W `
  --market-gate `
  --market-scope KOSPI `
  --market-sma-window 120 `
  --market-sma-mult 1.05
