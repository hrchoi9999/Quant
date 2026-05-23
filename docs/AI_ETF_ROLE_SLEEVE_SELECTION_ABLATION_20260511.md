# ETF Role Sleeve Selection Score Ablation

## 목적

ETF 역할 포트폴리오 안에서 어떤 ETF를 대표 sleeve로 선택할지 비교한다.

기준 조합은 직전 best baseline으로 고정했다.

- model_code: `AI-ETF-ROLE-ALLOCATION-V01`
- sleeve size: `top3`
- label: `horizon_v2_top1`
- regime mapping: `score_diff`
- 검증 구간: `2024-01-01` ~ `2026-05-08`

## Selection Mode 후보

| selection_mode | 의미 |
|---|---|
| `balanced` | 기존 balanced momentum/risk/liquidity 점수 |
| `momentum` | 20D/60D/120D momentum 중심 |
| `risk_adjusted` | 변동성/낙폭 penalty를 강하게 반영 |
| `liquidity_quality` | 유동성/안정성 중심 |
| `role_aware` | 역할별 score 차등 적용. 공격은 momentum, 방어는 안정성, hedge는 전술성 |

## 결과

| selection_mode | AUC | top-pick label rate | AI top1 1M ret | AI top1 risk adj | rule risk adj | worst 1M ret |
|---|---:|---:|---:|---:|---:|---:|
| `risk_adjusted` | 0.543034 | 25.93% | 5.34% | 3.29% | 0.26% | -11.52% |
| `balanced` | 0.711817 | 48.15% | 4.01% | 1.84% | 0.04% | -35.13% |
| `role_aware` | 0.615344 | 33.33% | 3.31% | 1.29% | -0.31% | -9.10% |
| `liquidity_quality` | 0.583598 | 33.33% | 1.90% | -0.32% | -0.82% | -14.75% |
| `momentum` | 0.530335 | 37.04% | 2.15% | -0.46% | -0.62% | -21.03% |

## 해석

1. AUC 기준으로는 `balanced`가 가장 좋다.
   - AUC: `0.711817`
   - top-pick label rate: `48.15%`
   - 하지만 worst 1M return이 `-35.13%`로 크다.

2. 실제 AI top1 운용 성과 기준으로는 `risk_adjusted`가 가장 좋다.
   - AI top1 1M return: `5.34%`
   - AI top1 risk-adjusted return: `3.29%`
   - worst 1M return: `-11.52%`
   - rule risk-adjusted return `0.26%` 대비 우수하다.

3. `role_aware`는 안정적 보조 후보이다.
   - AUC와 운용 성과가 중간 이상이고 worst loss도 작다.
   - 다만 현 버전은 hand-crafted rule이 거칠어 추가 개선 여지가 있다.

4. 단순 momentum은 부적합하다.
   - ETF 역할배분에서는 momentum만 강하게 주면 하락 리스크가 커지고 risk-adjusted 성과가 약해진다.

## 현재 판단

ETF 역할 sleeve selection baseline은 `risk_adjusted`로 두는 것이 좋다.

단, 모델 판별력 자체는 `balanced`가 더 높으므로 다음 단계에서는 두 축을 분리해서 관리한다.

- 학습/분류 reference: `balanced`
- 운용 후보 baseline: `risk_adjusted`
- 보조 challenger: `role_aware`

현재 운용 후보 조합:

- sleeve size: `top3`
- label: `horizon_v2_top1`
- regime mapping: `score_diff`
- selection mode: `risk_adjusted`

## Outputs

- `D:\Quant\scripts\run_etf_role_allocation_ai_v01_experiment.py`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_allocation_experiment_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted.json`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_allocation_policy_summary_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_ai_scored_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted.csv`
