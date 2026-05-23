# E-Series ETF Feature Enrichment

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 목적: ETF 전용 mart v2에 유동성, 추적품질, 상품구조, 분류별 상대점수 feature를 추가

## 추가 Feature 그룹

### Tradeability

- `e_liquidity_value_log`
- `e_liquidity_pct_in_role`
- `e_liquidity_pct_in_asset`
- `e_aum_pct_in_role`
- `e_aum_pct_in_asset`
- `e_tradeability_score`

### Category Relative Momentum

- `e_momentum_pct_in_role`
- `e_momentum_pct_in_asset`
- `e_momentum_pct_in_theme`
- `e_ret_60d_mean_role`
- `e_ret_60d_mean_asset`
- `e_ret_60d_mean_theme`
- `e_excess_ret_60d_vs_role`
- `e_excess_ret_60d_vs_asset`
- `e_excess_ret_60d_vs_theme`

### Role Relative Risk

- `e_vol_pct_in_role`
- `e_dd_pct_in_role`
- `e_risk_control_score_in_role`

### ETF Integrity

- `e_premium_abs_pct_in_role`
- `e_tracking_gap_abs_pct_in_role`
- `e_tracking_quality_score_in_role`
- `e_product_structure_score`
- `e_etf_integrity_score`

### Market Mode Alignment

- `e_mode_asset_alignment_score`

## Mart Impact

- 이전 mart columns: 202
- feature 보강 후 mart columns: 226
- 신규 ETF 전용 feature: 22개
- Sleeve Selection AI feature 수:
  - numeric: 68
  - categorical: 11

## 2026-05-12 Training Impact

| 항목 | Taxonomy V2 | Feature Enriched |
|---|---:|---:|
| Sleeve Selection AI AUC | 0.6622 | 0.6784 |
| Top3 label rate | 53.0864% | 44.4444% |
| Top3 avg 1M risk-adjusted | 0.3402% | -0.1331% |

단순 Top3 hit-rate는 낮아졌지만, portfolio backtest에서는 hybrid 정책의 baseline 대비 개선폭이 확대됐다.

## Portfolio Backtest

대표 정책: `hybrid_b50_ai50_top3_role`

| 항목 | Baseline | Hybrid 50/50 | 차이 |
|---|---:|---:|---:|
| 평균 1M 수익률 | 1.8874% | 2.1633% | +0.2759%p |
| 승률 | 60.7143% | 60.7143% | +0.0000%p |
| 평균 1M risk-adjusted | 0.3721% | 0.5993% | +0.2272%p |
| worst 1M return | -7.6366% | -7.4980% | +0.1386%p |
| 누적 검증 수익률 | 63.1838% | 74.8877% | +11.7039%p |

## 해석

이번 feature 보강은 ETF 모델이 단순 수익률 순위가 아니라 같은 역할군/자산군 안에서 거래 가능성, AUM, 괴리율, 추적오차, 상품구조 리스크를 함께 보도록 만든 작업이다.

다음 단계에서는 이 feature들을 활용해 role별 또는 asset bucket별로 다른 selection policy를 적용하는 ablation을 진행하는 것이 적절하다.
