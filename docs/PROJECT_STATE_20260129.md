# Quant Regime 프로젝트 대화 요약 (PROJECT_STATE)

> 기준일: 2026-01-29 (Asia/Seoul)  
> 목적: **레짐(regime) 기반 퀀트 투자 시스템**을 구축/검증하고, CAGR을 높이면서 MDD를 낮추는 방향으로 전략을 발전시키기 위한 데이터 파이프라인 및 백테스트 프레임을 정리.

---

## 1) 사용자가 궁극적으로 원하는 결과물

- **목표 지표**
  - CAGR(연복리수익률): 가능하면 **20% 이상**
  - MDD(최대낙폭): 가능하면 **-5% 수준**까지 낮추는 방향(현실적 제약은 인지)
- 단, **regime.db만으로는 전략공간이 너무 좁아 성능 개선이 제한적**이라는 판단에 따라,
  - **features.db (기술적 지표)**
  - **market.db (시장/거시 지표)**
  - (향후) 테마/업종/ETF/금현물 등 확장된 universe 및 메타데이터  
  를 추가해 **전략 백테스트의 유연성을 확보**하는 방향으로 합의.

---

## 2) 핵심 용어 정리(대화에서 혼선 있었던 부분)

- **regime (0~4)**: 시장 상태를 5개 그룹으로 나눈 값(예: 강한 상승~강한 하락 등)
- **horizon**: 레짐 산정에 쓰는 **관측 기간**
  - 3m(63d), 6m(126d), 1y(252d) 같이 “이만큼의 과거를 보고 점수/레짐을 계산”
- **forward return(예: fwd_21, fwd_63)**: 레짐의 ‘예측력’ 검증용으로 **미래 21일/63일 수익률**을 계산해 단조성(monotonicity)을 확인

---

## 3) DB/테이블 현황

### 3.1 price.db
- 테이블: `prices_daily`
- 컬럼: ticker, date, open/high/low/close, volume, value, source, created_at, updated_at
- 업데이트 스크립트(기존 활용):
  - `src/collectors/price/price_update_top200_daily.py` (Top200 갱신)
  - `src/collectors/price/price_update_daily.py` (시장 전체 갱신, 필요 시)

### 3.2 regime.db
- 테이블: `regime_history`
- build 모듈:
  - `python -m src.regime.build_regime_history ...`
- 2026-01-29 업데이트 후 요약(사용자 출력):
  - max(date)=2026-01-29
  - row counts:
    - 1y: 183,768
    - 6m: 208,714
    - 3m: 221,309

### 3.3 features.db (생성 완료)
- 스크립트: `src/features/build_features_db.py`
- 테이블: `features_daily`
- rows: 483,156 (end=2026-01-29 기준)
- 주요 컬럼:
  - 수익률: ret_1d, ret_21d, ret_63d, ret_126d, ret_252d
  - 이동평균: sma_20, sma_60, sma_120, sma_200
  - RSI/MACD: rsi_14, macd, macd_signal, macd_hist
  - 변동성/ATR: vol_21, vol_63, atr_14
  - 괴리: gap_sma200

### 3.4 market.db (생성 완료, 금리는 best-effort 실패 허용)
- 스크립트: `src/market/build_market_db.py`
- 테이블: `market_daily`
- 구성(생성된 컬럼 확인):
  - 지수: KOSPI/KOSDAQ/KOSPI200 OHLCV + ret_1d, sma_200, vol_21
  - 환율: usdkrw
  - risk_on_trend (시장 추세 기반 flag)
- 금리(ECOS snapshot) 시도는 HTTP 500 에러로 실패 → **향후 별도 보완**
- View:
  - `market_trading_daily`: 지수 close가 null이 아닌 거래일만 필터링

---

## 4) 파이프라인(일괄 업데이트) 구축

### update_all_dbs_daily.py
- 위치: `src/pipelines/update_all_dbs_daily.py`
- 기능(순서):
  1) price.db (Top200 incremental)
  2) regime.db (build_regime_history)
  3) features.db (build_features_db)
  4) market.db (build_market_db; 금리 best-effort)
  5) market_trading_daily view refresh
  6) 각 DB 최종 날짜/타입 검증 로그 출력

- 2026-01-29 업데이트 실행 결과(사용자 로그):
  - price 업데이트: 200종목 UPDATED, ticker당 saved=2 → 총 400행 저장
  - regime/features/market 모두 end=2026-01-29까지 반영됨
  - market 금리 fetch는 경고만 출력하고 계속 진행(성공)

---

## 5) 레짐 결측(1y/6m) 이슈와 결론

### 현상
- 2026-01-29 기준, date='2026-01-29'에서 ticker 커버리지:
  - 1y: 196 (200 중 4개 부족)
  - 6m: 199 (200 중 1개 부족)
  - 3m: 200 (완전)

### 원인(검증 스크립트 결과)
- 해당 종목은 상장/거래 시작이 늦어 **252거래일(1y) 또는 126거래일(6m) 히스토리가 부족**
- 예: 439260은 2025-08-01~ 121 rows로 6m도 부족, 3m만 가능

### 처리 방침(사용자 결정)
- “결측을 직전가 하드코딩으로 메우기” 대신,
- **결측이 있는 종목은 백테스트 universe에서 제외**로 결정

---

## 6) 백테스트(v1/v2/v3) 진행 요약

- v1: 기본 레짐 기반 선별/리밸런싱 실험
- v2: (주로) 옵션/필터/교차(1y + confirm 6m) 등 개선 시도
- v3: 추가 전략(단기필터/union/iv 등) 확장 시도했으나, 향후는 v1/v2 중심으로 정리하기로 합의

### 대표 실행 예(v2 교차)
```
python .\src\backtest\run_backtest_regime_v2.py `
  --horizon 1y `
  --confirm-horizon 6m `
  --top-n 40 `
  --spread-threshold 0.0 `
  --fee-bps 10 `
  --slippage-bps 10
```
- 출력 예:
  - CAGR 0.116053 / Sharpe 0.82536 / MDD -0.210896 (2013-10-14..2026-01-27)

### 생성된 결과 파일(예시)
- summary/equity/holdings CSV들이 `reports/backtest_regime/`에 누적 생성됨
- 사용자 업로드 파일 예:
  - `regime_bt_summary_3m_R2_M_20131014_20260127.csv`
  - `regime_bt_summary_6m_R2_M_20131014_20260127.csv`
  - `regime_bt_summary_1y_R2_M_20131014_20260127.csv`
  - `regime_bt_summary_1y_R2_M_top20_20131014_20260127.csv`
  - `regime_bt_summary_1y_C6m_R2_M_top40_thr0p0_top40_INTERSECT_20131014_20260127.csv`
  - `regime_bt_summary_1y_R2_M_top20_thr0p0_20131014_20260129.csv`
  - (v3 관련) `regime_bt_summary_1y_C6m_R2_M_top40_thr0p0_final40_ma200_...csv`

---

## 7) 발생했던 주요 오류와 해결

### 7.1 PowerShell 인라인 python 인자/따옴표 문제
- `python -c "..."`에서 `"distinct"` 등 문자열이 PowerShell에서 깨지는 현상 발생
- 해결:
  - `python --% -c "..."` 사용 또는
  - **파일로 스크립트를 분리**(tmp_check_missing.py 등)

### 7.2 update_all_dbs_daily.py unicodeescape 에러
- docstring 내부 `D:\Quant` 같은 백슬래시가 `\uXXXX`로 해석되면서 SyntaxError
- 해결: raw string(`r""" ... """`) 처리 및 백슬래시 이스케이프 정리

### 7.3 backtest v2의 argparse/옵션 불일치
- `--primary-horizon` 인자 미지원으로 “unrecognized arguments” 발생
- 방향:
  - 표준은 `--horizon`
  - 또는 `--primary-horizon` 별칭을 argparse에 추가하는 패치가 필요

### 7.4 sqlite3.InterfaceError (binding parameter unsupported type)
- tickers/params가 list가 아닌 타입(예: set/Series)로 전달될 때 발생 가능
- 해결 방향: tickers를 `list[str]`로 강제 + chunk query param 결합을 단순화

---

## 8) 다음 작업(합의된 우선순위)

1) **v1/v2만 기준으로 정리** (v3는 일단 보류)
2) backtest 코드 정리:
   - argparse 옵션(호환성) 정리: `--horizon` 중심, 필요 시 별칭 추가
   - “결측 종목 제외” 로직을 backtest universe 로딩/필터에 반영
3) 데이터 보강:
   - 이미 만든 features.db, market.db를 활용하여
   - 레짐 + 기술지표 + 시장상태를 조합한 “최종 종목 그룹” 생성 전략 설계
4) Universe 확장(향후):
   - KOSDAQ 포함, ETF/테마/금현물 등 추가 편입 가능하도록 파이프라인 설계

---

## 9) 실행 환경 메모
- Python: 3.10.11 (venv64)
- 실행 경로: `D:\Quant`
- 패키지: `requirements_freeze.txt` 참고(사용자 제공)

---
