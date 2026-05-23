# ETF 역할 비중 Template AI V01 실험

## 목적

ETF 역할별 sleeve를 만든 뒤, 시장 상황에 따라 어떤 역할 비중 template이 유리한지 학습한다.

## 기준 조합

- role model: `AI-ETF-ROLE-ALLOCATION-V01`
- template model: `AI-ETF-ROLE-WEIGHT-TEMPLATE-V01`
- sleeve topN: `3`
- regime mapping: `score_diff`
- selection mode: `risk_adjusted`
- quality gate: `strict_quality` (Keep only normal premium flags with stronger AUM/tracking-gap filters)

## 결과

- AUC(best template): `0.833215`
- top-pick hit rate: `0.444444`

| policy | avg 1M ret | hit rate | avg 1M MDD | avg risk adj | avg objective | worst 1M ret |
|---|---:|---:|---:|---:|---:|---:|
| `oracle_best_template` | 4.30% | 70.37% | -2.39% | 3.10% | 8.88% | -14.77% |
| `ai_top1_template` | 3.12% | 66.67% | -2.95% | 1.64% | 5.29% | -14.77% |
| `mode_default_template` | 2.37% | 51.85% | -2.07% | 1.34% | 4.20% | -4.85% |
| `ai_prob_weighted_template` | 2.09% | 59.26% | -2.68% | 0.75% | 2.31% | -10.07% |

## 현재 판단

이 실험은 ETF AI가 역할 선택을 넘어 역할 비중 template을 선택할 수 있는지 보는 1차 baseline이다.
다음 단계에서는 template 후보군을 더 촘촘히 만들고, 시장 모드별 template pool을 분리해 검증한다.

## Outputs

- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_weight_template_panel_20260508_top3_score_diff_risk_adjusted_strict_quality_template.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_weight_template_scored_20260508_top3_score_diff_risk_adjusted_strict_quality_template.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_weight_template_policy_summary_20260508_top3_score_diff_risk_adjusted_strict_quality_template.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_weight_template_experiment_20260508_top3_score_diff_risk_adjusted_strict_quality_template.json`
