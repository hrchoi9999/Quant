# PROJECT_STATE.md (2026-02-09) — S2 결과 재현(골든) 확정 + 리팩토링(전략 분리) 전환점 정리

- 프로젝트 루트: `D:\Quant`
- 작업 폴더(현재): `D:\Quant\src\backtest`
- 목적(오늘):  
  1) S2 백테스트 결과/CSV/Google Sheet 출력이 “항상 동일하게 재현”되는지 확인  
  2) 데이터/유니버스/DB 업데이트 파이프라인이 당일(asof)까지 정상 갱신되는지 점검  
  3) `run_backtest_*` 단일 거대 스크립트를 **전략/엔진/리포팅/구글시트**로 분리하는 리팩토링 착수

---

## 0) 오늘 시작 시점의 과제(P0/P1/P2) 및 합의된 진행 순서

### 합의된 순서
- **P0 3개 → P1(ledger) → (P2는 후순위) → 리팩토링**  
- P2는 급하지 않으므로 “나중에” 처리.

### 골든(정답) 기준
- **기존 레거시 실행 결과(`run_backtest_s2_v5.py` 계열)가 정답(golden)**  
- 리팩토링 산출물(`run_backtest_v5.py` 계열)은 **골든과 동일 결과를 재현**해야 함.

---

## 1) 오늘 진행 사항(실행/검증 로그 기반)

### 1-1. 레거시 S2 실행 결과 정상 확인 (CSV/GSHEET/요약)
- 실행: `run_backtest_s2_v5.py` (또는 동일 동작의 v4 계열)  
- 주요 로그(정상 징후):
  - `rebalance dates=642`
  - `strategy=S2(v2) ... market_gate=ON ... exit_below_sma_weeks=2`
  - CSV 다수 생성: `ledger/snapshot/trades/windows/summary/equity/holdings`
  - Google Sheet 생성/업로드: `snapshot/trades/windows/trades_c/ledger`

- 요약지표(대표 실행 예):  
  - CAGR 약 **0.109**  
  - MDD 약 **-0.24**  
  - Sharpe 약 **0.825**
- 결론: **레거시 S2 파이프(결과/리포트/시트 업로드)는 안정적으로 동작**.

---

### 1-2. Google Sheet “시트가 안 보인다” 이슈 해결
- 실제 원인: snapshot 시트가 “앞쪽에 분리되어 있어서” 사용자가 못 찾음  
- 해결: Google Sheet에서 숨김 시트 확인 방법 안내 후, 사용자가 snapshot 시트 존재 확인.

---

### 1-3. 파이프라인(일일 업데이트) 실행 점검: `rebuild_mix_universe_and_refresh_dbs.py`
- asof=2026-02-09로 실행됨.
- 관찰된 포인트:
  - price_backfill이 2026-02-02~2026-02-09 범위로 400종목 tail backfill 수행(총 2400 row).
  - regime build는 10년치(2016-02-10~2026-02-09) upsert 수행.
  - fundamentals_end는 **2026-02-09 → 2026-01-31로 스냅** (월말 기준).
  - 경고(WARN):
    - `fs_annual 누락 tickers=28 (filtered out for fundamentals)`  
      → 해당 종목들은 fundready 유니버스에서 제외되어 400 → 372로 감소.

- 결론:
  - “당일(asof)까지 price/regime는 갱신”되고,
  - “fundamentals는 월말 스냅 규칙에 따라 1/31까지 갱신”되는 구조가 맞음.
  - 다만 `fs_annual` 누락 종목의 근본 원인(데이터 ETL/상장사 매핑 등)은 후속 과제.

---

## 2) 리팩토링 착수: 왜 필요했고, 오늘 어디까지 왔나

### 2-1. 문제 인식(왜 리팩토링이 필요한가)
- S2에서 S3/S4/S5…로 전략 다변화 예정.
- 지금 구조는 `run_backtest_*` 단일 파일에:
  - 데이터 로딩/캘린더/전략/백테스트 엔진/리포팅/GSHEET 업로드가 혼재
- 이 상태로 전략을 늘리면:
  - 코드 복잡도 급증
  - 버그 추적/재현 어려움
  - 전략간 공통 로직 중복 및 규약 불일치 발생

### 2-2. 리팩토링 기준(오늘 합의된 원칙)
1) **runner는 전략번호와 독립**:  
   - `run_backtest_***.py` (전략명 결합) 대신  
   - `run_backtest_v***.py` (러너 버전) 형태로 유지
2) **전략은 `strategies/`로 분리**:  
   - S2/S3/S4는 파일 단위로 추가 가능
3) **엔진(core)은 공통 규약만 담당**:  
   - 리밸런싱 적용 구간, 비용, 포트폴리오 추적, 산출물 생성 규칙
4) **리포팅/GSHEET는 플러그인화**:  
   - CSV 저장/구글시트 업로드를 엔진/전략과 분리
5) **리스크 관리**:  
   - 1차 리팩토링 완료 후 기능 이동(예: gsheet_uploader 이동)은 추후 단계로

### 2-3. 오늘 리팩토링 진행 상황(현 상태의 핵심)
- `run_backtest_v5.py` + `core/engine.py` + `strategies/s2.py` 구조를 만들었으나,
  - 초기에는 import/시그니처/np 누락 등 다수 런타임 에러가 발생했고 여러 차례 fix zip을 반복.
- 현재 “동작은 되는 상태”까지 왔으나,
  - 리팩토링 S2 엔진 결과가 **골든(S2 v2)과 불일치**하여
  - 원인 분석 결과:
    - `strategies/s2.py`가 placeholder 수준(핵심 로직 미이관)
    - `core/engine.py`가 minimal 엔진(리밸런스 window 규약/market gate/펀더멘털 asof/SMA/EX2 등 불완전)
- 따라서 “골든 재현 확보”를 위해 FIX8 단계에서
  - **레거시 S2 로직을 호출하는 우회 경로**를 넣었고,
  - 그 결과 로그가 `S2(v2)` 포맷으로 출력되어 사용자가 “기능분리 안 된 것 같다”고 확인.

---

## 3) 현재 상태 요약(냉정한 진단)

### 3-1. 잘 된 것(확정)
- 레거시 S2(`run_backtest_s2_v5.py` 계열)는:
  - 결과(요약지표) 재현 OK
  - CSV 생성 OK
  - Google Sheet 업로드 OK
- 일일 파이프라인(`rebuild_mix_universe_and_refresh_dbs.py`)은:
  - price/regime는 asof까지 갱신 OK
  - fundamentals는 월말 스냅 규칙 OK
  - fs_annual 누락 종목 경고는 “데이터 품질/커버리지 이슈”로 확인됨

### 3-2. 아직 안 된 것(핵심 리스크)
- 리팩토링 버전(`run_backtest_v5.py` + core/strategies)은
  - **S2 골든 결과를 재현하지 못함**
  - FIX8(레거시 호출)은 “정확도”만 확보한 임시방편으로,
    - 기능 분리/전략 추가 확장성은 아직 미완성
- 따라서 다음 단계는:
  - **레거시 호출 제거**
  - **S2 로직을 core/strategies로 실제 이관**
  - **골든과 1:1 결과 일치**까지 맞추는 것

---

## 4) 내일 해야 할 일(우선순위 포함)

### P0 (최우선) — “리팩토링 S2 골든 재현” 달성
목표: 동일 옵션으로 실행했을 때 **equity 시계열 및 summary(CAGR/MDD/Sharpe)가 골든과 일치**.

1) **리밸런스 적용 규약(window)부터 동일화**
   - 레거시 `backtest_s2_v2()`에서:
     - rb_date 이후 구간(`dates[start_idx+1: ...]`)에 수익률 적용
   - 리팩토링 `core/engine.py`에서도 동일 규약으로 적용

2) **S2 핵심 규칙 이관(placeholder 제거)**
   - `strategies/s2.py`에 아래를 “그대로” 옮김:
     - 펀더멘털 as-of 매핑 + top-n 산출
     - 종목 SMA 필터(Require Above SMA)
     - EX2: 보유종목 SMA 아래 2주 연속 시 제외
     - Market Gate 히스테리시스(entry/exit)
     - min_holdings 만족을 위한 완화(cascade)

3) **비용/턴오버 처리 타이밍 동일화**
   - turnover 산식 및 적용 시점(리밸런스 시점) 정렬

4) **검증 스크립트/체크리스트 자동화**
   - equity 최종값/중간 몇 지점 체크
   - rebalance_count=642 동일 여부
   - holdings 특정 날짜 2~3개 샘플 비교

---

### P1 (중요) — 리포팅/GSHEET를 “리팩토링 엔진 산출물”로 교체
목표: 레거시 호출 없이도
- CSV(`regime_bt_*`) 생성
- gsheet 시트 생성/overwrite 동작
- snapshot 시트 컬럼/정렬 규약 유지

---

### P2 (후순위)
- pandas groupby.apply FutureWarning 제거(옵션 include_groups 등)
- gsheet_uploader 위치 이동(현 단계에서는 보류; 1차 안정화 후)
- fs_annual 누락 tickers 원인 파악 및 fundamentals 커버리지 개선

---

## 5) 급한 과제(리스크 관점)
1) **리팩토링 결과가 골든과 다르면, S3/S4 비교 자체가 무의미**
   - 최우선은 S2 재현(테스트 기준선 확보)
2) **레거시 호출(FIX8) 의존은 “기능 분리 실패”로 이어짐**
   - 임시방편 단계는 끝내고, 내일은 반드시 placeholder 제거 후 이관해야 함
3) **데이터 파이프라인 경고(fs_annual 누락 28종목)는 장기적으로 전략 성능/유니버스 안정성을 흔들 수 있음**
   - 단기: 워닝 유지 + 로그 저장
   - 중기: DART ETL/상장사 매핑/테이블 커버리지 개선

---

## 6) 현재 파일/폴더 맵(내일 작업 재개용)

### 레거시(골든)
- `D:\Quant\src\backtest\run_backtest_s2_v5.py`  (S2 정답 기준)
- `D:\Quant\src\backtest\run_backtest_regime_s2_v4.py` (유사 계열)

### 리팩토링(진행 중)
- `D:\Quant\src\backtest\run_backtest_v5.py` (러너)
- `D:\Quant\src\backtest\core\engine.py` (공통 엔진)
- `D:\Quant\src\backtest\strategies\s2.py` (S2 전략; 현재 placeholder 제거 필요)
- (리포팅/GSHEET 플러그인) `csv_plugin.py`, `gsheet_plugin.py` 등 (현 위치는 zip/배포물 기준)

### 파이프라인(일일 갱신)
- `D:\Quant\src\pipelines\rebuild_mix_universe_and_refresh_dbs.py`

### 산출물
- `D:\Quant\src\backtest\reports\backtest_regime\regime_bt_*.csv`
- Google Sheet 시트명 패턴: `S2_YYYYMMDD_###_{snapshot|trades|windows|trades_c|ledger}`

---

## 7) 내일 시작 체크리스트(바로 실행)
1) 레거시 골든 1회 실행하여 결과/CSV/시트 생성 확인
2) 리팩토링 `run_backtest_v5.py --strategy S2` 실행
3) equity 최종값/중간값 비교 → 불일치면
   - window 규약 → market gate → fundamentals as-of → SMA/EX2 → 비용 순으로 디버그
