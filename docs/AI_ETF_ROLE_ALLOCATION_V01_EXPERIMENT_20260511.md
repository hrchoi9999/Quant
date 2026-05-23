# ETF 역할배분AI V01 1차 실험

## 목적

ETF를 개별 종목 선별 문제가 아니라 `6개 역할 포트폴리오`와 `3개 시장 모드`의 배분 문제로 재정의한다.

## 구조

- ETF별 feature와 forward return으로 역할별 sleeve를 구성한다.
- 역할은 `CORE_BETA`, `SECTOR_THEME`, `STYLE_FACTOR`, `DEFENSIVE_HEDGE`, `TACTICAL_HEDGE`, `TACTICAL_LEVERAGE`로 둔다.
- 시장 모드는 `risk_on`, `neutral`, `risk_off`로 둔다.
- AI는 각 날짜/역할 조합이 다음 1개월 risk-adjusted return 기준 최상위 역할이 될 확률을 학습한다.

## 핵심 결과

- 기준일: `2026-05-08`
- Label: `horizon_v2_top1` (Role-specific horizon V2 best role)
- Regime map: `score_diff` (Risk-on/risk-off score spread with state fallback)
- Selection mode: `risk_adjusted` (Risk-adjusted score with stronger volatility and drawdown penalty)
- Quality gate: `strict_quality` (Keep only normal premium flags with stronger AUM/tracking-gap filters)
- AUC: `0.416236`
- Top pick label rate: `0.148148`
- 최상위 정책: `oracle_best_role`
- 최상위 정책 평균 1M risk-adjusted return: `3.76%`

## 정책 비교

| policy | avg 1M ret | hit rate | avg 1M MDD | avg risk adj |
|---|---:|---:|---:|---:|
| `oracle_best_role` | 4.95% | 77.78% | -2.38% | 3.76% |
| `learned_mode_weight` | 2.17% | 51.85% | -2.18% | 1.08% |
| `rule_mode_weight` | 1.99% | 44.44% | -2.29% | 0.85% |
| `equal_role` | 1.49% | 51.85% | -3.27% | -0.14% |
| `ai_prob_weight` | 1.17% | 48.15% | -3.64% | -0.65% |
| `ai_top2_equal` | 0.49% | 40.74% | -4.11% | -1.57% |
| `ai_top1_role` | 0.05% | 44.44% | -3.53% | -1.72% |

## 현재 판단

이번 실험은 ETF AI의 방향을 `시장국면별 역할 배분 모델`로 잡기 위한 1차 baseline이다.
다음 단계에서는 역할 sleeve 구성 점수, 역할별 horizon, 그리고 시장 모드 mapping을 추가로 ablation한다.

## Outputs

- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_sleeves_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted_strict_quality.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_ai_scored_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted_strict_quality.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_allocation_policy_summary_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted_strict_quality.csv`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_allocation_experiment_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted_strict_quality.json`
- `D:\Quant\reports\etf_ai_role_allocation_v01\etf_role_allocation_experiment_20260508_top3_horizon_v2_top1_score_diff_risk_adjusted_strict_quality.md`
