# ETF T-series Model V1 (2026-03-31)

## 정의
- 내부 코드명: `ETF T-series`
- 방법론: `transition-based discovery model`
- 한글명: `전이형 발굴 모델`

## 목적
- ETF core universe 안에서 향후 상위 성과 그룹(`ETF-T3`, `ETF-T10`)에 들어갈 가능성이 높은 ETF를 찾기
- 기존 ETF allocation 모델(`S4`, `S5`, `S6`)과 병행 비교 가능한 정답지/발굴 모델 만들기

## 입력 universe
- 파일: `D:\Quant\data\universe\universe_etf_core_20260325.csv`
- 크기: 20 ETFs
- 주기: 월간 trade date 기준

## 정답지(ETF-T%)
- 실제 ETF 가격 데이터 기반
- 각 signal_date마다 미래 `3M`, `6M`, `1Y`의
  - forward return
  - path MDD
  를 합성한 `future_quality`로 랭킹
- exclusive bucket:
  - `ET3`
  - `ET10_ex_ET3`
  - `ET30_ex_ET10`
  - `ET50_ex_ET30`
  - `OUTSIDE`

## 모델 구조
- 로지스틱 회귀 사용
- horizon별 2개 목표 라벨
  - `ET10`: `ET3` 또는 `ET10_ex_ET3`
  - `ET3`: `ET3`
- 사용 feature
  - price momentum: `ret_20d`, `ret_60d`, `ret_120d`, `ret_240d`
  - risk/vol: `vol_20d`, `vol_60d`, `dd_60d`, `dd_120d`
  - trend: `dist_ma20`, `dist_ma60`, `dist_ma120`, `ma20_ma60_gap`, `ma60_ma120_gap`
  - oscillator: `rsi20`
  - meta: `asset_class`, `group_key`, `currency_exposure`, `is_inverse`, `is_leveraged`, `liquidity_20d_value`

## 산출물
- 폴더: `D:\Quant\reports\model_upgrade_research\20260331\ETF_T_SERIES_V1`
- 핵심 파일
  - `etf_tseries_feature_panel.csv`
  - `etf_tseries_bucket_panel.csv`
  - `etf_tseries_model_summary.csv`
  - `etf_tseries_vs_s456_accuracy.csv`
  - `etf_tseries_latest_full_rank_2026-03-26.csv`
  - `etf_tseries_predicted_top3_2026-03-26.csv`
  - `etf_tseries_predicted_top10_2026-03-26.csv`
  - `etf_tseries_predicted_top30_2026-03-26.csv`
  - `etf_tseries_predicted_top50_2026-03-26.csv`

## 현재 해석
- ETF T-series V1은 생성 완료
- 다만 현재 검증 수치는 강하지 않아서, 완성 모델보다 연구용 baseline으로 보는 것이 적절함
- 다음 단계는
  - ETF 그룹별 전이 특성 분석
  - S4/S5/S6와의 교집합/차이 분석
  - 라벨 재정의 또는 feature 보강
  으로 이어가는 것이 좋음
