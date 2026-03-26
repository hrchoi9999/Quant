# PROJECT_STATE.md (2026-02-07) — 백테스트/CSV/구글시트 Output 안정화 + 리팩토링 설계 메모

- 프로젝트: `D:\Quant` / Regime 기반 백테스트 (S2 v2)
- 작업일: 2026-02-07
- 목적: (1) Output(CSV/Google Sheet) 요구사항 반영 및 안정화 (2) 리밸런싱 기반 주문원장(ledger) 생성 (3) 향후 확장 가능한 구조적 리팩토링 방향 수립

---

## 0. 오늘 대화 시작 시점의 “할 일” 목록(요청사항 원문 기반)

### A. Output(표/CSV/GSHEET) 관련
1) **대화창 표(A안) 포맷으로 성능 지표 표시**
2) **snapshot CSV/시트에 종목별 `market(KOSPI/KOSDAQ)` 표시**
3) **snapshot 시트: 보여지는 컬럼 순서는 유지, `return` 기준 내림차순 정렬하여 저장**
4) **구글시트 업로드가 실행마다 시트 폭증하지 않도록 “overwrite 모드” 옵션 제공**
5) **CSV 저장 전반 검토(누락/정렬/컬럼/호출 인자 불일치 등 안정성)**

### B. 리밸런싱 이벤트 기반 내역(주문원장/ledger) 관련
6) 리밸런싱 시점별로 **신규 매수/매도(청산)** 이벤트를 한 행 단위로 정리한 **별도 CSV/별도 시트** 생성
   - 요청 컬럼(요지):
     - `rebalance_date`
     - BUY: `buy_date, ticker, name, market, price, qty(=1), amount`
     - SELL: `first_buy_date(최초), ticker, name, market, sell_price, qty(=1), pnl`
7) 위 ledger도 **구글시트에 업로드**되게 하기
8) 향후 실거래 염두: snapshot/trades에 끼워 넣기 vs 별도 파일 의견(→ **별도 파일**이 적합)

### C. 실행 명령/옵션 안정화 및 구조화
9) 자주 쓰는 실행 옵션을 안정화하고, 최종적으로 **하나의 파일만 실행**해도 백테스트+출력이 자동 수행되게 구성
10) `run_backtest_regime_s2_v4.py` 파일이 너무 커져서 기능 분리 필요
11) 파일이 많아졌을 때 “수정 시 여러 파일 수정” 문제까지 완화하는 리팩토링 설계 필요

---

## 1. 오늘 실제로 “수정/반영된 내용” (결과 로그/업로드 파일 기반)

> 아래는 사용자가 공유한 최종 실행 로그(버전 `2026-02-07_018`) 및 생성된 CSV 목록을 기준으로 정리합니다.

### 1.1 백테스트 정상 수행 확인
- `script_version=2026-02-07_018`
- universe: names=371 / tickers=371
- price dates: 3,026 (2013-10-14..2026-02-06)
- regime rows: 724,367 (horizon=3m)
- excluded tickers: 2 (388210, 488900)
- rebalance dates: 642 (W, weekday=2, holiday_shift=prev)
- strategy: S2(v2)
  - good_regimes=[4,3]
  - top_n=30
  - sma_window=140, require_above_sma=True
  - fundamentals_view=s2_fund_scores_monthly, fundamentals_asof=True
  - market_gate=True, market_sma_window=60, market_sma_mult=1.02
  - exit_below_sma_weeks=2, enable_exit_below_sma=True
- SUMMARY(콘솔 1-row):
  - CAGR=0.108815
  - Sharpe=0.824805
  - MDD=-0.237913
  - avg_daily_ret=0.000459
  - vol_daily=0.008844
  - fee_bps=5, slippage_bps=5
  - rebalance_count=642

### 1.2 CSV 생성(로컬 저장) — 최종 목록
아래 파일들이 저장됨:
- `regime_bt_ledger_3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206.csv`
- `regime_bt_snapshot_3m_S2_RBW_top30_GR43_SMA140_MG1_EX2_20131014_20260206.csv`
- `regime_bt_snapshot_...__trades.csv`
- `regime_bt_trades_C_...csv`
- `regime_bt_perf_windows_...csv`
- `regime_bt_summary_...csv`
- `regime_bt_equity_...csv`
- `regime_bt_holdings_...csv`

### 1.3 구글시트 업로드 — overwrite 모드 + ledger 포함 성공
- 실행 옵션: `--gsheet-enable --gsheet-mode overwrite --gsheet-ledger`
- 결과: 생성된 시트(예시)
  - `snapshot`: `S2_20260206_001_snapshot`
  - `trades`: `S2_20260206_001_trades`
  - `windows`: `S2_20260206_001_windows`
  - `trades_c`: `S2_20260206_001_trades_c`
  - `ledger`: `S2_20260206_001_ledger`

### 1.4 시장 구분(market) 컬럼 반영 상태
- 사용자 확인:
  - “구글시트에도 시장 표시가 잘 되어 있네. KOSDAQ 종목이 적은 거지 안 나오는 건 아니네.”
- 결론: market attach 로직은 최종 결과물(구글시트)에서 정상 반영된 것으로 확인.

### 1.5 snapshot 정렬 요구사항 반영 상태
- 사용자 확인:
  - “구글시트 상에서 snapshot은 잘 소트된 상태로 보여지는데…”
- 결론: snapshot은 **return 내림차순 정렬**이 구글시트에 반영됨.
  (CSV는 아래 “추가 점검” 체크리스트에 포함)

### 1.6 리밸런싱 이벤트 기반 ledger 생성 반영
- 로그에서 ledger 저장이 확인됨:
  - `[SAVE] ... regime_bt_ledger_...csv`
- 구글시트에도 ledger 시트 생성 확인:
  - `ledger`: `S2_20260206_001_ledger`
- 결론: ledger “별도 파일/시트” 방향이 구현되어 결과가 생성/업로드까지 완료됨.

---

## 2. 오늘 발생했던 주요 오류/이슈와 해결 히스토리(요약)

### 2.1 NameError 류 (univ_df/universe_df/market_map/trades_c_df)
- 증상:
  - `NameError: name 'univ_df' is not defined`
  - `NameError: name 'universe_df' is not defined`
  - `NameError: name 'market_map' is not defined`
  - Pylance: `"trades_c_df"이(가) 정의되지 않았습니다.`
- 원인(패턴):
  - 정의 위치/스코프 불일치, 조건 분기에서만 생성되는 변수를 아래에서 참조
- 조치:
  - market_map은 “universe 로딩 직후”에 확정 생성하도록 배치
  - trades_c_df는 항상 선언되도록(없으면 빈 DF) 처리하거나, 참조를 조건부로 변경
- 최종 상태:
  - 실행은 성공했으나, 정적 분석 경고(trades_c_df)는 다음 작업에서 제거 권장

### 2.2 IndentationError / 들여쓰기 오류 다발
- 증상:
  - `IndentationError: unexpected indent`
  - Pylance: 들여쓰기 관련 오류 다수
- 원인:
  - 대형 단일 파일에 기능을 삽입하는 과정에서 블록 레벨이 흔들림
- 최종 상태:
  - 실행은 정상 통과

### 2.3 gsheet_uploader 호출 시그니처 불일치
- 증상:
  - `upload_frames_new_sheets() got multiple values for argument 'cfg'`
  - `upload_snapshot_bundle() got an unexpected keyword argument 'stamp'`
  - `upload_snapshot_bundle() missing required keyword-only arguments: 'prefix', 'date_yyyymmdd', and 'seq'`
- 원인:
  - 호출부(run_backtest)와 피호출부(gsheet_uploader) 사이 인자 계약이 흔들림
- 최종 상태:
  - 최종 실행에서는 구글시트 업로드 성공(시트 생성 로그 확인)

---

## 3. 추가로 “점검/보완” 해야 할 사항(우선순위)

### P0 (안정성/계약 고정)
1) **gsheet_uploader 함수 시그니처/계약 확정**
   - stamp/prefix/date/seq/run_id 중 무엇이 공식 파라미터인지 하나로 고정
2) **Pylance 경고 제거(trades_c_df 등)**
   - 분기에서만 생기는 변수를 “항상 선언”하거나, 참조를 조건부로 제한
3) **CSV snapshot도 return desc 정렬 확실히 적용되는지 자동 검증**
   - 저장 직전/직후 assert/log로 확인

### P1 (기능 완성도)
4) **ledger 스키마/정확성 검증**
   - first_buy_date 규칙(최초) / pnl 계산(1주 기준) / 향후 FIFO 확장 로드맵
5) **구글시트 overwrite 정책 확정**
   - “동일 sheet key 재사용” 규칙을 명확히 해야 시트 폭증을 구조적으로 막음

### P2 (기술부채/호환성)
6) pandas FutureWarning 대응(groupby.apply)
   - `include_groups=False` 등으로 향후 호환성 확보

---

## 4. 운영 원칙: “수정 요청 시 파일 업로드” 권장 규칙

- 핵심 파일은 **항상 PC 최신본 업로드가 안전**합니다.
- 특히 `run_backtest_regime_s2_v4.py`, `gsheet_uploader.py`는 수정마다 업로드 권장.
- ChatGPT는 업로드된 파일 기준으로만 패치 → “구버전 패치” 사고를 구조적으로 예방.

---

## 5. 리팩토링 방향(상세) — 내일 작업 이어가기용

### 5.1 현재 구조의 한계
1) run_backtest 단일 파일 과대 → 스코프/들여쓰기 오류 빈발
2) 출력 요구사항이 분산 → 정렬/컬럼/시트명 규칙이 흩어짐
3) 호출 인자 계약이 흔들림 → gsheet 관련 오류 반복
4) 옵션 폭발 → 커맨드라인 길이/복잡도 증가
5) 파일이 늘면 수정도 분산(“파일 수”보다 “변경 포인트 분산”이 본질)

### 5.2 핵심 원칙(SSOT + Contract + Plugin)
1) **단일 엔트리포인트**: `run.py` 하나 실행
2) **데이터 계약 고정**: `BacktestResult(bundle)`로 결과를 묶어 출력 계층에 전달
3) **정렬/컬럼 규칙 SSOT**: `schemas.py`에서 중앙 관리 (CSV/GSHEET 모두 동일 transform)
4) **Output 플러그인화**: CSV 저장, GSheet 업로드를 독립 플러그인으로
5) **Naming 단일화**: prefix/date/seq/stamp/run_id를 `naming.py`에서 한 번만 생성

### 5.3 제안 디렉토리 구조(초안)


 src/
app/
run.py
config_loader.py
pipeline.py
contracts.py

backtest/
engine.py
strategy_s2.py
rebalance.py
portfolio.py
ledger.py
market.py
metrics.py
io_readers.py
naming.py

outputs/
base.py
registry.py
csv_plugin.py
gsheet_plugin.py
gsheet_client.py
transforms.py

schemas.py
configs/
s2_weekly.yaml



### 5.4 단계별 실행 계획(내일 진행 순서)
1) **Contract 먼저 고정**: run_backtest → BacktestResult 리턴
2) **Naming 통합**: run_id 단일 생성, output은 run_id만 받기
3) **schemas 도입**: snapshot 정렬(return desc), 컬럼순서, market attach 정책 중앙화
4) **Output 플러그인화**: CSV/GSheet 분리 + overwrite 정책은 gsheet_plugin에서만
5) **run.py + YAML config**: 긴 옵션은 yaml로 이동, CLI는 최소 override만

### 5.5 “파일 많아져서 여러 파일 수정” 문제 해법
- 변경 유형별 수정 위치를 강제하여 수정 포인트를 수렴:
  - 출력/정렬/컬럼: `schemas.py`
  - 구글시트 정책: `outputs/gsheet_plugin.py` + `configs/*.yaml`
  - 파일/시트명 규칙: `backtest/naming.py`
  - ledger 로직: `backtest/ledger.py`
  - 전략 로직: `backtest/strategy_s2.py`

---

## 6. 내일 체크리스트(초단기)
1) CSV snapshot 정렬(return desc) 자동 검증 추가
2) trades_c_df Pylance 경고 제거(선언 보장)
3) gsheet_uploader 인자 계약을 run_id 중심으로 고정(시그니처 흔들림 방지)
4) contracts/schemas/naming/out plugin 뼈대부터 만들고 기존 코드 이동

---

## 7. 최종 실행 명령(재현용)
```powershell
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
  --gsheet-enable `
  --gsheet-mode overwrite `
  --gsheet-ledger


8. 환경/경고 메모

Google API Core: Python 3.10.11은 2026-10-04 이후 지원 중단 예정 → 장기적으로 3.11+ 권장

pandas FutureWarning(groupby.apply): 차후 include_groups=False 등으로 대응 권장

내일 시작하실 때는, 위 **6. 내일 체크리스트(초단기)** 그대로 진행하시면 맥락 안 끊기고 이어집니다.
::contentReference[oaicite:0]{index=0}

끝.