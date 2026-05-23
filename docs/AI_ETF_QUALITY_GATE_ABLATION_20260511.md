# ETF Quality Gate Ablation

## 목적

ETF 전용 NAV/AUM/괴리율/tracking gap 데이터를 raw feature로 직접 넣는 대신, sleeve 후보를 거르는 quality gate로 썼을 때 성능이 개선되는지 검증한다.

## 기준 조합

- role model: `AI-ETF-ROLE-ALLOCATION-V01`
- template model: `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01`
- as-of: `2026-05-08`
- train end: `2023-12-31`
- valid start: `2024-01-01`
- top N: `3`
- label: `horizon_v2_top1`
- regime map: `score_diff`
- selection mode: `risk_adjusted`

## 결과

| gate | role AUC | AI role risk adj | AI role worst | template AUC | AI template risk adj | AI template worst |
|---|---:|---:|---:|---:|---:|---:|
| `none` | 0.511817 | -3.54% | -35.13% | 0.851117 | 2.09% | -19.13% |
| `no_wide_extreme` | 0.585185 | 0.27% | -35.13% | 0.849699 | 1.94% | -19.13% |
| `no_watch_plus` | 0.605467 | 2.43% | -35.13% | 0.846863 | 1.61% | -19.13% |
| `aum_p20` | 0.504409 | -0.84% | -17.77% | 0.910138 | 2.35% | -15.42% |
| `tracking_gap_p90` | 0.644676 | 1.35% | -15.49% | 0.793513 | 1.92% | -18.21% |
| `quality_combo` | 0.655634 | -0.17% | -15.49% | 0.838710 | 1.49% | -15.42% |
| `strict_quality` | 0.416236 | -1.72% | -18.83% | 0.833215 | 1.64% | -14.77% |

## 판단

- 역할 선택 AUC만 보면 `quality_combo`가 가장 높다.
  - role AUC: `0.655634`
  - 다만 AI top1 role의 평균 risk-adjusted return은 음수라 운영 후보로는 부적합하다.
- 역할 선택 기준 best gate: `no_watch_plus`
  - AI role avg risk adj: `2.43%`
  - AI role worst 1M: `-35.13%`
- 비중 템플릿 기준 best gate: `aum_p20`
  - AI template avg risk adj: `2.35%`
  - AI template worst 1M: `-15.42%`

## 운영 판단

- `no_watch_plus`는 역할 선택 AI를 회복시키는 데 가장 효과적이다.
  - raw metric 직접 투입 baseline의 AI role risk adj `-3.54%`를 `2.43%`까지 끌어올렸다.
  - 단, worst 1M `-35.13%`가 남아 있어 단독 운영 기준으로는 tail risk guard가 필요하다.
- `aum_p20`은 비중 템플릿 AI에 가장 적합하다.
  - template AUC `0.910138`
  - AI template risk adj `2.35%`
  - worst 1M `-15.42%`
- 현 시점 ETF quality gate 운영 후보는 아래처럼 나누는 것이 적절하다.
  - 역할 선택 AI: `no_watch_plus` shadow 관찰
  - 비중 템플릿 AI: `aum_p20` shadow 관찰
  - tail-risk 방어 실험: `tracking_gap_p90` 또는 `quality_combo`를 보조 guard로 재검증

## Gate 정의

- `none`: No ETF quality filter
- `no_wide_extreme`: Exclude ETFs with wide/extreme NAV premium-discount flags
- `no_watch_plus`: Exclude ETFs with watch/wide/extreme NAV premium-discount flags
- `aum_p20`: Exclude ETFs below the per-date 20th percentile AUM
- `tracking_gap_p90`: Exclude ETFs above the per-date 90th percentile tracking-gap absolute value
- `quality_combo`: Exclude wide/extreme premium flags, low AUM, and large tracking-gap ETFs
- `strict_quality`: Keep only normal premium flags with stronger AUM/tracking-gap filters

## Outputs

- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_quality_gate_ablation_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_quality_gate_ablation_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted.json`
