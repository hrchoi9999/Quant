# E-Series ETF Stress Rule Recalibration

## Summary

- 기준일: 2026-05-12
- 대상: E-ETF-V01 mode switch policy
- 목적: ETF mode switch에서 사용하는 `stress` 판정이 너무 넓게 잡히는 문제 수정

## 문제

기존 stress 판정은 `qm_risk_market_stress_score >= 0.65`를 사용했다.
하지만 QuantMarket stress score는 0~1 스케일이 아니라 대략 0~3 스케일이었다.

그 결과 2024-03-29 이후 walk-forward 평가일 26개가 모두 stress로 분류됐다.

## 보정 Rule

Stress는 일반 risk-off와 분리해 급성 위험 구간으로만 좁혔다.

Stress 조건:

- `qm_risk_crash_warning_flag >= 0.5`
- 또는 `qm_risk_market_stress_score >= 2.5`
- 또는 `qm_risk_market_stress_score >= 2.0` and `qm_risk_drawdown_pressure_score >= 2.5`
- 또는 `qm_market_risk_off_score >= 2.5` and `qm_market_market_mdd_3m <= -0.12`

일반 `risk_off` 모드는 별도 전환 기준으로 유지한다.

## 판정 결과

Walk-forward 평가일 26개 기준:

- 기존 stress days: 26
- 보정 후 stress days: 13
- risk-off days: 15

Mode/stress 조합:

| market mode | non-stress | stress |
|---|---:|---:|
| neutral | 4 | 1 |
| risk_on | 5 | 1 |
| risk_off | 4 | 11 |

## Mode Switch 결과

보정 후 best policy는 `mode_switch_stress_tail_asset`이다.

| policy | avg 1M ret | win rate | avg 1M risk adj | avg MDD proxy | worst 1M | compounded |
|---|---:|---:|---:|---:|---:|---:|
| mode_switch_stress_tail_asset | 2.3854% | 61.5385% | 0.9465% | -2.8778% | -3.3538% | 77.9428% |
| mode_switch_riskoff_tail_asset | 2.3098% | 57.6923% | 0.8770% | -2.8655% | -3.3538% | 74.7558% |
| hybrid_b50_ai50_top3_role | 2.1174% | 57.6923% | 0.4684% | -3.2981% | -7.4980% | 65.6200% |
| baseline_top3_role | 1.8252% | 57.6923% | 0.2320% | -3.1865% | -7.6366% | 54.7330% |

## 운영 해석

현재 대표 성장형 shadow policy는 `hybrid_b50_ai50_top3_role`로 유지한다.
다만 stress 재보정 후에는 `mode_switch_stress_tail_asset`가 신규 대표 후보로 가장 강하다.

다음 pipeline 이후에도 같은 방향이면 E-ETF-V01 대표 shadow policy 승격을 검토한다.
