# E-Series ETF Taxonomy V2

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 목적: 6개 역할 sleeve를 유지하되 ETF 전용 세부분류를 추가해 향후 feature 보강, 비중학습, 신규 ETF review에 활용

## 추가 분류 축

기존 `e_series_role`은 그대로 유지한다.

- `e_region_bucket`: KR, US, CHINA, JAPAN, INDIA, VIETNAM, EUROPE, GLOBAL
- `e_asset_bucket`: EQUITY_KR, EQUITY_US, BOND_SHORT, BOND_LONG, BOND_CORE, CASH_RATE, FX_USD, COMMODITY_GOLD, REIT_INFRA, MULTI_ASSET, HEDGE_INVERSE 등
- `e_strategy_bucket`: BROAD_BETA, SECTOR_THEME, STYLE_FACTOR, DIVIDEND_INCOME, COVERED_CALL, LOW_VOL, VALUE, GROWTH, BOND_DURATION, CASH_RATE, FX_USD, COMMODITY, LEVERAGED_TACTICAL, INVERSE_HEDGE
- `e_theme_bucket`: SEMICONDUCTOR, SECONDARY_BATTERY_EV, AI_TECH, AUTO_MOBILITY, BIO_HEALTHCARE, FINANCIAL, DEFENSE_AEROSPACE, ENERGY_INFRA, CONSUMER_MEDIA, REIT_REAL_ESTATE 등
- `e_product_structure`: PLAIN, ACTIVE, SYNTHETIC, HEDGED, COVERED_CALL, TDF, LEVERAGED, INVERSE 조합

## 산출물

- `D:\Quant\reports\e_series_etf\e_series_etf_role_taxonomy_20260512.csv`
- `D:\Quant\reports\e_series_etf\e_series_etf_role_taxonomy_summary_20260512.csv`
- `D:\Quant\reports\e_series_etf\e_series_etf_role_taxonomy_detail_summary_20260512.csv`
- `D:\Quant\reports\e_series_etf\e_series_etf_mart_v2_20260512.csv`

## 2026-05-12 Role Summary

| role | ETF count | review count | avg taxonomy confidence |
|---|---:|---:|---:|
| CORE_BETA | 146 | 0 | 0.8449 |
| SECTOR_THEME | 338 | 3 | 0.8407 |
| STYLE_FACTOR | 101 | 38 | 0.5524 |
| DEFENSIVE | 134 | 0 | 0.9328 |
| INCOME | 121 | 0 | 0.9023 |
| CASH_LIKE | 34 | 0 | 0.9265 |

## 해석

이번 작업은 단순히 AUC를 올리기 위한 작업이 아니라 ETF 모델의 해상도를 높이는 기반 작업이다.
특히 `STYLE_FACTOR`의 review count가 높은데, 이는 실제로 액티브/테마/스타일 경계가 애매한 ETF가 많기 때문이다.

따라서 남은 review 대상은 자동 제외가 아니라 다음 단계에서 다음 방식으로 활용한다.

- 신규 ETF 편입 시 자동 review queue
- role sleeve 안에서 세부 asset/strategy 노출 한도 설정
- 비중학습 모델에서 asset bucket별 상한/하한 제약
- ETF 전용 feature 보강 시 분류별 feature interaction 생성

## 학습 영향

세부분류 컬럼은 E-series mart v2와 Sleeve Selection AI categorical feature에 반영했다.
이후 ETF 전용 feature 보강까지 반영한 2026-05-12 재학습 결과:

- Sleeve Selection AI AUC: 0.6784
- Top3 label rate: 44.4444%
- Top3 average 1M risk-adjusted: -0.1331%

포트폴리오 backtest 기준 대표 정책은 `hybrid_b50_ai50_top3_role`이다.

- baseline 평균 1M 수익률: 1.8874%
- hybrid 평균 1M 수익률: 2.1633%
- baseline 누적 검증 수익률: 63.1838%
- hybrid 누적 검증 수익률: 74.8877%
