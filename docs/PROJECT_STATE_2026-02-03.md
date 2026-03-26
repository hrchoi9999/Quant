# PROJECT_STATE_2026-02-03 (퀀트투자 레짐 S2 백테스트 개발 일지)

- 작성일: 2026-02-03 (Asia/Seoul)
- 작업 범위: `S2` 레짐 기반 백테스트 스크립트(`run_backtest_regime_s2_v2.py`) 리팩토링/패치, 펀더멘털(as-of) 정합, 시장 게이트(market gate) 로직 튜닝, 결과 리포트(추가 CSV 2종) 생성

---

## 0) 오늘 작업 환경 요약

### 로컬 환경
- OS/경로: Windows, 프로젝트 루트 `D:\Quant`
- 가상환경: `venv64` (PowerShell에서 `(venv64)`)
- 실행 스크립트:
  - 백테스트: `D:\Quant\src\backtest\run_backtest_regime_s2_v2.py`
  - 분석/도구: `D:\Quant\tools\compare_summary_equity.py` 등
- 데이터/DB
  - 가격 DB: `.\data\db\price.db` / `prices_daily`
  - 레짐 DB: `.\data\db\regime.db` / `regime_history` (horizon=3m 사용)
  - 펀더멘털 DB: `.\data\db\fundamentals.db`
  - 펀더멘털 View: `vw_s2_top30_monthly` (월말 기준, rank 포함)
- 유니버스 파일(확정):  
  `.\data\universe\universe_mix_top400_20260129_fundready.csv`  
  (names=187, tickers=382로 로드됨)

### 출력 폴더
- 리포트 저장 경로: `D:\Quant\reports\backtest_regime\`

---

## 1) 핵심 의사결정/전략 파라미터(오늘 확정 또는 실험)

### 기본 설정(실행 로그 기준)
- strategy: `S2(v2)`
- rebalance: `W` (주간, week-end)
- horizon: `3m`
- good_regimes: `[4, 3]`
- top_n: `50` (TOP30→TOP50 확대)
- 종목 필터(개별 종목 SMA): `sma_window=140`, `require_above_sma=True`
- market gate(시장 게이트): `ON`
  - market_sma_window=140
  - entry_mult=1.050 (기본 진입 기준)
  - exit_mult=1.000 (오늘 튜닝: “SMA 터치 시 exit” 의미로 조정)
- 수수료/슬리피지: fee=10bps, slippage=10bps

> 참고: `market_gate`는 단순 “상승장에만 투자”가 아니라,  
> **entry/exit 멀티(히스테리시스)**를 두어 시장이 기준선 위/아래로 오갈 때 잦은 토글을 방지하는 구조로 정리함.  
> 오늘은 exit를 1.00으로 내려 “원래 의도(기준선 도달 시 현금화)”에 맞추려는 조정이 들어감.

---

## 2) 오늘의 주요 문제/원인/해결

### (A) `universe-file`에 와일드카드(`*.csv`) 사용 불가 문제
- 증상: `OSError: [Errno 22] Invalid argument: '.\\data\\universe\\universe_top382_*.csv'`
- 원인: `pd.read_csv()`는 와일드카드 문자열을 직접 처리하지 못함(글롭 처리 필요).
- 해결: 유니버스 파일을 명시적으로 지정하고, 최종적으로 아래 파일로 통일:
  - `universe_mix_top400_20260129_fundready.csv`

### (B) 주간 리밸런싱에서 펀더멘털 “월말 as-of” 정합 문제
- 배경: 펀더멘털 스코어/랭크는 월말 기준으로 생성되어 있음.
- 조치: 주간 리밸런싱에서도 **해당 주의 날짜를 “직전 월말”로 매핑**하여 펀더멘털을 사용하도록 “as-of 적용” 방향으로 정리.
- 결과: as-of 적용 여부에 따라 성능이 크게 달라짐 → 이후에도 “펀더멘털의 시간정합”은 최우선 체크 항목.

### (C) `from __future__ import annotations` 위치 오류
- 증상: `SyntaxError: from __future__ imports must occur at the beginning of the file`
- 원인: 버전 출력용 코드/변수가 `from __future__`보다 앞에 위치.
- 해결: `from __future__ import annotations`를 **파일 최상단(주석/Docstring 다음)**으로 이동.

### (D) 추가 리포트 생성 단계에서 NameError 2건
- 증상(로그):
  - `[WARN] trade snapshot build failed: name 'dates' is not defined`
  - `[WARN] perf windows report failed: name 'math' is not defined`
- 원인:
  - `dates` 변수가 main scope에 없음(이전 변수명/스코프 변경으로 누락)
  - `math` 모듈 import 누락
- 해결:
  - end_date 계산을 `equity_df['date']` 기반으로 변경
  - `import math` 추가
- 결과: `_014` 버전에서 WARN 제거, 추가 파일 정상 생성 확인.

---

## 3) 오늘 최종 정상 실행(확정 로그)

### 실행 명령(최종)
```powershell
python .\src\backtest\run_backtest_regime_s2_v2.py `
  --strategy S2 `
  --rebalance W `
  --horizon 3m `
  --universe-file .\data\universe\universe_mix_top400_20260129_fundready.csv `
  --ticker-col ticker `
  --price-db .\data\db\price.db `
  --price-table prices_daily `
  --regime-db .\data\db\regime.db `
  --regime-table regime_history `
  --fundamentals-db .\data\db\fundamentals.db `
  --fundamentals-view vw_s2_top30_monthly `
  --market-gate `
  --sma-window 140 `
  --market-sma-window 140 `
  --market-exit-mult 1.00
```

### 주요 로딩/상태 로그
- tickers=382
- price dates=3,020 | 2013-10-14..2026-01-29
- regime rows=742,964 | horizon=3m
- excluded tickers (end missing)=3 | 388210, 486990, 488900
- rebalance dates=641 (week-end)
- market_gate=ON | win=140 | entry=1.050 | exit=1.000

### 요약 성능(전체 기간)
- 기간: 2013-10-14 ~ 2026-01-29 (3020 trading days)
- CAGR: 0.102726
- Sharpe: 0.857337
- MDD: -0.269979
- Rebalance count: 641
- top_n: 50, sma_window: 140, market_gate: True

> 주의: “CAGR 10% 수준인데 MDD -27%”라서 목표(CAGR 20%, MDD -5%)와는 큰 갭이 있음.  
> 다만 오늘의 초점은 **리포트/계산/데이터 정합을 먼저 고정**하는 것이었음.

---

## 4) 오늘 생성된 산출물(파일)

### 기존 4종(항상 생성)
- `regime_bt_snapshot_{stamp}.csv`
- `regime_bt_summary_{stamp}.csv`
- `regime_bt_equity_{stamp}.csv`
- `regime_bt_holdings_{stamp}.csv`

### 오늘 추가로 생성되도록 패치한 2종(정상 생성 확인)
- **(1) 종목별 보유기간 수익률/거래 레코드**
  - `regime_bt_snapshot_{stamp}__trades.csv`
  - 목적: “보유 중이면 산출 시점 기준”, “매도면 매도 시점 기준” 수익률을 종목별로 기록/집계
- **(2) 최근 1/3/5년 CAGR/MDD + Gate ON/OFF 구간별 성과**
  - `regime_bt_perf_windows_{stamp}.csv`
  - 목적:
    - 최근 1y/3y/5y 윈도우 성과
    - gate ON/OFF 구간 분리 성과
    - (구현상) fullcurve/chain 방식으로도 계산될 수 있음

### stamp 예시(오늘 실행)
- `3m_S2_RBW_top50_GR43_SMA140_MG1_20131014_20260129`

따라서 생성된 추가 파일명 예:
- `regime_bt_snapshot_3m_S2_RBW_top50_GR43_SMA140_MG1_20131014_20260129__trades.csv`
- `regime_bt_perf_windows_3m_S2_RBW_top50_GR43_SMA140_MG1_20131014_20260129.csv`

---

## 5) “CAGR/MDD가 언제부터 언제까지 계산되는가?”에 대한 정리

- 기본 summary에 찍히는 CAGR/MDD는 **equity 커브 전체 기간(시작~끝)**을 기준으로 계산됨.
  - 시작: price 데이터의 첫 날짜(이 실행에서는 2013-10-14)
  - 끝: `--end`를 따로 주지 않으면 price DB의 마지막 날짜(이 실행에서는 2026-01-29)
- 오늘 추가한 perf_windows 리포트는 같은 equity에서 **최근 1/3/5년 윈도우**를 잘라 별도로 계산하도록 구현/패치됨.
- Gate ON/OFF 구간별 성과는 equity의 `market_ok`를 기준으로 구간을 분리하여 계산(“구간이 끊어질 수 있음”을 고려한 계산 방식 포함).

---

## 6) 내일 이어서 할 작업(우선순위)

### P0. 오늘 만든 2개 추가 CSV “내용 검증”
1) `regime_bt_perf_windows_*.csv`
   - 최근 1y/3y/5y 성과가 기대대로 나오나?
   - gate ON/OFF별 결과가 직관에 맞는가?
   - gate ON 구간이 너무 적으면(예: 특정 설정에서 gate_on_pct 낮음) 결과가 왜곡될 수 있음 → 해석 기준 정하기
2) `regime_bt_snapshot_*__trades.csv`
   - 종목별 거래(진입/청산) 레코드가 정상적으로 쌓이는가?
   - “보유기간 수익률” 정의가 요구사항과 일치하는가?
   - 주간 리밸런싱에서 월말 as-of 매핑이 거래 레코드/수익률에 어떤 영향을 주는가?

### P1. S2 전략의 “현금 비중 과다/투자일수 부족” 문제 진단
- 과거에 gate_on_pct가 매우 낮고(avg_cash_weight 매우 높게) 나타난 케이스가 있었음.
- 현재는 exit/entry 조정으로 성능이 바뀌는 것이 확인되었으므로,
  - **시장 게이트가 ‘진입 조건’인지 ‘위험회피 조건’인지 역할을 명확히 분리**
  - entry/exit 멀티 조합(예: entry=1.02, exit=1.00 등)을 소규모 스윕으로 시험
  - “시장 게이트 OFF에서도 최소 주식 비중 유지” 같은 정책 옵션 검토

### P2. 목표 기준에 맞는 튜닝/실험 설계
- 목표: CAGR 20%, MDD -5% (현실적으로 난이도 높음)
- 단기 목표: “S1 대비 S2가 유의미하게 개선되는 구간/조건” 찾기
- 후보 실험 축:
  1) top_n (20/30/50)와 min_holdings(예: 15) 정책 조합
  2) sma_window (140 고정 또는 주변값) + market_sma_window 분리(예: 개별=140, 시장=100 등)
  3) market gate 히스테리시스(entry/exit) 조합 스윕
  4) good_regimes 선택(예: [4,3] 외 옵션) — “레짐이 좋은데도 gate_off가 많아지는지” 점검

### P3. 리포트 고도화(분석 자동화)
- `__trades.csv` 기반으로:
  - 종목별 누적 기여도(Contribution)
  - 승률/손익비/평균 보유기간
  - 거래 횟수 및 turnover 지표
- 결과를 “다음날 의사결정용 1장 요약” 형태로 자동 생성(추후)

---

## 7) 오늘 최종 상태(결론)

- `run_backtest_regime_s2_v2.py` 패치 버전: **2026-02-03_014**
- 추가 산출물 2종(`__trades.csv`, `perf_windows.csv`)이 백테스트 실행 시 자동 생성되도록 **정상 동작 확인 완료**
- 다음 단계는 “코드/데이터 정합”이 아니라 **성과 해석과 튜닝/스윕 설계**로 넘어갈 준비가 됨

---

## 부록) 빠른 점검 명령(내일 재개 시 유용)

### (1) 버전/패치 포함 여부 확인
```powershell
python -c "import pathlib; t=pathlib.Path(r'D:\Quant\src\backtest\run_backtest_regime_s2_v2.py').read_text(encoding='utf-8'); print(t.splitlines()[0]); print('perf_windows' in t, '__trades' in t)"
```

### (2) 생성 파일 존재 여부 확인
```powershell
dir D:\Quant\reports\backtest_regime\*__trades.csv
dir D:\Quant\reports\backtest_regime\regime_bt_perf_windows_*.csv
```

### (3) summary vs equity 재계산 일치 확인(이미 통과했지만 재확인용)
```powershell
python .\tools\compare_summary_equity.py --equity .\reports\backtest_regime\regime_bt_equity_...csv --summary .\reports\backtest_regime\regime_bt_summary_...csv
```
