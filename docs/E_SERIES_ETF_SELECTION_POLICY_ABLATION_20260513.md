# E-Series ETF Selection Policy Ablation

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 목적: 역할군/자산군별로 ETF selection policy를 다르게 적용했을 때 성과가 개선되는지 확인
- 실험 스크립트: `D:\Quant\scripts\run_e_series_etf_selection_policy_ablation.py`

## 후보 정책

- `baseline_top3_role`: E-series baseline score 역할군별 Top3
- `hybrid_b70_ai30_top3_role`: baseline 70% + AI 30% 역할군별 Top3
- `hybrid_b50_ai50_top3_role`: baseline 50% + AI 50% 역할군별 Top3
- `ai_quality_guard_top3_role`: AI + ETF quality/risk guard 역할군별 Top3
- `ai_top3_role`: AI score 역할군별 Top3

## Portfolio-Level Result

| policy | avg 1M ret | win rate | avg 1M risk adj | worst 1M | compounded |
|---|---:|---:|---:|---:|---:|
| role_asset_adaptive_best_policy | 2.7752% | 67.8571% | 1.1447% | -4.2512% | 107.0340% |
| asset_adaptive_best_policy | 2.7225% | 71.4286% | 0.9910% | -3.8576% | 104.8804% |
| role_adaptive_best_policy | 2.3091% | 64.2857% | 0.8807% | -7.1724% | 82.8772% |
| hybrid_b50_ai50_top3_role | 2.1633% | 60.7143% | 0.5993% | -7.4980% | 74.8877% |
| baseline_top3_role | 1.8874% | 60.7143% | 0.3721% | -7.6366% | 63.1838% |

## Best Policy By Role

| role | best policy | avg 1M ret | avg 1M risk adj |
|---|---|---:|---:|
| CASH_LIKE | baseline_top3_role | 0.1655% | 0.1237% |
| CORE_BETA | hybrid_b70_ai30_top3_role | 4.9736% | 3.3055% |
| DEFENSIVE | hybrid_b50_ai50_top3_role | 1.3644% | 0.5484% |
| INCOME | baseline_top3_role | 1.3876% | -0.0559% |
| SECTOR_THEME | ai_top3_role | 4.1907% | 2.0160% |
| STYLE_FACTOR | baseline_top3_role | 3.8953% | 1.0347% |

## Best Policy By Asset Bucket

주요 asset bucket 기준:

| asset bucket | best policy | avg 1M ret | avg 1M risk adj |
|---|---|---:|---:|
| EQUITY_KR | hybrid_b70_ai30_top3_role | 5.9592% | 3.5549% |
| EQUITY_US | ai_quality_guard_top3_role | 2.4827% | 0.7427% |
| COMMODITY_GOLD | hybrid_b50_ai50_top3_role | 3.8004% | 2.6678% |
| MULTI_ASSET | hybrid_b70_ai30_top3_role | 3.1214% | 2.7354% |
| BOND_CORE | ai_top3_role | 1.6020% | 1.2121% |
| CASH_RATE | ai_top3_role | 0.2191% | 0.2109% |

## Interpretation

역할군과 자산군에 따라 유리한 selection policy가 다르게 나타났다.

- CORE_BETA와 국내주식형은 baseline 비중이 큰 hybrid 70/30이 유리했다.
- SECTOR_THEME는 AI score 단독 Top3가 가장 좋았다.
- DEFENSIVE와 금/인버스 성격은 hybrid 50/50이 안정적이었다.
- CASH_LIKE, INCOME, STYLE_FACTOR는 baseline이 아직 더 안정적이었다.
- 미국주식형은 AI 단독보다 quality guard가 더 적합했다.

## Caution

`role_asset_adaptive_best_policy`는 같은 validation 구간에서 best policy를 고른 in-sample ablation이다.
따라서 운영 정책으로 바로 승격하지 말고 walk-forward 방식으로 재검증해야 한다.

## Next Step

다음 단계는 adaptive policy를 walk-forward 구조로 바꾸는 것이다.
예를 들어 과거 6~12개월 데이터로 role/asset별 best policy를 선택하고, 다음 1개월에만 적용해 성과를 검증한다.
