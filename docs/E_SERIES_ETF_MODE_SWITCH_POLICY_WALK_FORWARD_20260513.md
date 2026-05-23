# E-Series ETF Mode Switch Policy Walk-Forward

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 목적: 성장형 ETF selection과 tail-risk 방어형 ETF selection을 시장모드에 따라 전환하는 규칙 검증
- 스크립트: `D:\Quant\scripts\run_e_series_etf_mode_switch_policy_walk_forward.py`

## Tested Rules

- `hybrid_b50_ai50_top3_role`: 대표 성장형 고정 정책
- `wf_tail_asset_policy`: tail-risk asset bucket adaptive 정책
- `mode_switch_riskoff_tail_asset`: normal 구간은 hybrid 50/50, risk-off 구간은 tail asset policy
- `mode_switch_riskoff_quality_guard`: normal 구간은 hybrid 50/50, risk-off 구간은 quality guard
- `mode_switch_riskoff_tail_role_asset`: normal 구간은 hybrid 50/50, risk-off 구간은 tail role+asset policy

## Walk-Forward Setup

- 과거 365일로 tail-risk policy map 선택
- 평가일 직전 31일 제외
- 평가일 수: 26
- risk-off 평가일 수: 15
- stress 판정일 수: 13

stress 판정은 0~3 스케일의 QM stress score를 반영해 재보정했다.
기존 threshold 0.65는 너무 낮아 전체 평가일을 stress로 분류했기 때문에, 급성 위험 조건 중심으로 좁혔다.

Stress rule:

- crash warning flag >= 0.5
- 또는 market stress score >= 2.5
- 또는 market stress score >= 2.0 and drawdown pressure score >= 2.5
- 또는 risk-off score >= 2.5 and market 3M MDD <= -12%

## Result

| policy | avg 1M ret | win rate | avg 1M risk adj | avg MDD proxy | worst 1M | compounded |
|---|---:|---:|---:|---:|---:|---:|
| mode_switch_stress_tail_asset | 2.3854% | 61.5385% | 0.9465% | -2.8778% | -3.3538% | 77.9428% |
| mode_switch_riskoff_tail_asset | 2.3098% | 57.6923% | 0.8770% | -2.8655% | -3.3538% | 74.7558% |
| mode_switch_riskoff_quality_guard | 2.1711% | 61.5385% | 0.6650% | -3.0122% | -3.3538% | 68.7843% |
| mode_switch_riskoff_tail_role_asset | 2.1492% | 57.6923% | 0.6609% | -2.9767% | -3.3538% | 67.6863% |
| wf_tail_asset_policy | 2.0414% | 57.6923% | 0.5911% | -2.9005% | -3.1640% | 64.5265% |
| hybrid_b50_ai50_top3_role | 2.1174% | 57.6923% | 0.4684% | -3.2981% | -7.4980% | 65.6200% |
| baseline_top3_role | 1.8252% | 57.6923% | 0.2320% | -3.1865% | -7.6366% | 54.7330% |

## Interpretation

stress 재보정 후 `mode_switch_stress_tail_asset`가 현재까지 가장 균형이 좋다.
`mode_switch_riskoff_tail_asset`도 여전히 강하지만, stress 기반 전환이 수익률과 risk-adjusted에서 더 좋았다.

Baseline 대비:

- 평균 1M 수익률: +0.5602%p
- 평균 1M risk-adjusted: +0.7145%p
- avg MDD proxy: +0.3210%p 개선
- worst 1M return: +4.2828%p 개선
- 누적 검증 수익률: +23.2098%p

Hybrid 50/50 대비:

- 평균 1M 수익률: +0.2680%p
- 평균 1M risk-adjusted: +0.4781%p
- avg MDD proxy: +0.4203%p 개선
- worst 1M return: +4.1442%p 개선
- 누적 검증 수익률: +12.3228%p

## Operating View

현 단계 판단:

- 기존 대표 성장형: `hybrid_b50_ai50_top3_role`
- 신규 대표 후보: `mode_switch_stress_tail_asset`
- 구조:
  - risk-on / neutral: `hybrid_b50_ai50_top3_role`
  - stress: `wf_tail_asset_policy`
  - non-stress risk-off: 일단 `hybrid_b50_ai50_top3_role` 유지, 별도 후보로 `mode_switch_riskoff_tail_asset` 병행 관찰

아직 public 추천에는 반영하지 않는다.
다음 pipeline 이후에도 같은 방향성이 유지되면 E-ETF-V01의 대표 shadow policy를 `mode_switch_stress_tail_asset`로 승격 검토한다.

## Next Step

- stress 판정 기준 재보정
- risk-off 전환 규칙을 4~8주 shadow tracking
- 현재 E-ETF-V01 current portfolio에서 risk-off일 때 실제 holdings가 어떻게 바뀌는지 비교 payload 추가
