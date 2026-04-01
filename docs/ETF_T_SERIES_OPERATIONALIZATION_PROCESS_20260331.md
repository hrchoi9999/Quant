# ETF T-series Operationalization Process (2026-03-31)

## 목적
- ETF `T-series`를 연구용 모델에서 운영형 후보 생성 시스템으로 전환한다.
- 운영 전환은 한 번에 하지 않고 단계별로 진행한다.
- 현재 운영형 기준은 `PIT(point-in-time) backfill` 기반 `T-ETF-V01`이다.

## 운영 전환 5단계
1. 라벨/정확도 기준 고정
2. strict walk-forward 검증
3. 후보 등급화(`확정`, `근접`, `관찰`)
4. 리스크 필터 적용
5. 자동 리포트 + shadow tracking

## 현재 진행 상태
- 완료: 1단계 라벨/정확도 기준 고정
- 완료: 2단계 strict walk-forward 검증
- 완료: 3단계 후보 등급화
- 완료: 4단계 리스크 필터 적용
- 완료: 5단계 자동 리포트 + shadow tracking

## 1단계에서 고정한 항목
- universe:
  - 최신 운영 대상: `D:\Quant\data\universe\universe_etf_extended_200_20260331.csv`
  - backfill / validation 대상: `D:\Quant\data\universe\etf_pit_backfill\universe_etf_pit_monthly_201701_202603.csv`
- 신호 주기: 월간
- 정답지 bucket:
  - `ET3`
  - `ET10_ex_ET3`
  - `ET30_ex_ET10`
  - `ET50_ex_ET30`
  - `OUTSIDE`
- stage1 목표:
  - 현재 `OUTSIDE`, `ET50_ex_ET30`, `ET30_ex_ET10`에 있는 ETF가 다음 시점 `ET10_ex_ET3` 또는 `ET3`로 진입하는지
- stage2 목표:
  - 현재 `ET10_ex_ET3`에 있는 ETF가 다음 시점 `ET3`로 승격하는지

## 운영 전환 기준 지표
- 공통 1순위:
  - `precision`
  - `capture`
  - `lift`
- stage2 운영 참고:
  - historical `ET10 hit rate`
  - historical `ET3 hit rate`

## 현재 운영 baseline
- source:
  - strict walk-forward: `D:\Quant\reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_STRICT_WALKFORWARD`
  - tuning: `D:\Quant\reports\model_upgrade_research\20260401\ETF_T_SERIES_PIT_TUNING`
- `stage1 lower -> ET10`
  - validation: strict walk-forward + PIT retune
  - feature set: `momentum_trend`
  - selection: `top_ratio=0.08`
  - precision: `7.39%`
  - capture: `15.59%`
  - lift: `1.86x`
  - AUC: `0.5578`
- `stage2 ET10 -> ET3`
  - validation: tuned strict walk-forward
  - feature set: `vol_trend_compact`
  - confirmed threshold: `0.65`
  - near threshold: `0.60`
  - precision: `23.33%`
  - capture: `28.33%`
  - lift: `1.86x`
  - AUC: `0.5528`

## 현재 운영 후보 체계
- `confirmed`
  - stage1 통과 + tuned stage2 confirmed bucket
- `near`
  - stage1 통과 + tuned stage2 near bucket
- `observe`
  - stage1 통과, 하지만 confirmed/near까지는 승격되지 않은 관찰 후보

## 현재 리스크 필터 규칙
- 레버리지/인버스 ETF 허용
- 20일 평균 거래대금 `200억` 미만 제외
- 테마 cap 적용
  - gold: 1
  - securities: 1
  - energy_materials: 2
  - semiconductor: 2
  - broad_equity: 1
  - dividend_income: 1
  - auto: 1
  - silver: 1
  - esg: 1
  - other: 1

## 현재 리스크 필터 결과
- input total: `16`
- kept total: `3`
- kept confirmed: `1`
- kept near: `2`
- kept observe: `0`

## 자동 리포트 + shadow tracking 산출물
- operational dir:
  - `D:\Quant\reports\model_upgrade_research\20260401\ETF_T_SERIES_OPERATIONALIZATION_PIT`
- latest watchlist:
  - `etf_tseries_pit_latest_watchlist_2026-03-31.csv`
- latest watchlist summary:
  - `etf_tseries_pit_latest_watchlist_summary_20260401.csv`
- shadow tracking history:
  - `etf_tseries_pit_shadow_tracking_history_20260401.csv`
- shadow tracking historical summary:
  - `etf_tseries_pit_shadow_tracking_historical_summary_20260401.csv`

## 현재 운영형 최신 후보
- `confirmed`
  - `KODEX 인버스`
- `near`
  - `TIGER 2차전지소재Fn`
  - `TIGER 2차전지테마`

## shadow tracking 기준
- `historical_stage1`
  - candidates: `698`
  - unique ETFs: `147`
  - hit rate: `7.02%`
- `historical_stage2`
  - candidates: `69`
  - unique ETFs: `51`
  - hit rate: `17.39%`

## 해석 원칙
- 위 baseline은 운영 전환의 출발점이다.
- 이후 모든 ETF `T-series` 개선안은 이 baseline 대비 개선 여부로 판단한다.
- 연구용 수익률보다 `정확도` 개선을 우선한다.
- 운영 후보는 `confirmed -> near -> observe` 순으로 우선순위를 둔다.
- 리스크 필터 이후 후보군이 실제 운영형 watchlist가 된다.
- shadow tracking은 resolved historical picks와 pending latest picks를 같은 포맷으로 누적한다.

## 다음 단계
- 운영형 V1은 완성된 상태다.
- 다음 고도화는:
  - 리스크 필터 세분화
  - 그룹별 cap 재튜닝
  - monthly automation
  - 실제 ET10/ET3 후행 성과 누적 검증
