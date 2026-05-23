# E-Series ETF Mode Switch Cost Adjusted Backtest

## Summary

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 목적: mode switch 정책이 거래비용/회전율 차감 후에도 유효한지 확인
- 스크립트: `D:\Quant\scripts\run_e_series_etf_mode_switch_cost_adjusted.py`
- 기본 비용 가정: one-way turnover당 10bp

## Method

- 각 평가일의 ETF별 weight를 이전 평가일 weight와 비교해 one-way turnover를 계산했다.
- 첫 평가일은 초기 진입 비용을 포함한다.
- net return = gross return - one_way_turnover * cost_rate

## 10bp Cost Result

Best net policy: `mode_switch_stress_tail_asset`

| 항목 | 값 |
|---|---:|
| avg gross 1M return | 2.4808% |
| avg net 1M return | 2.4107% |
| net win rate | 64.0000% |
| avg net 1M risk-adjusted | 0.9143% |
| worst net 1M return | -3.4338% |
| avg one-way turnover | 70.5128% |
| max one-way turnover | 93.3333% |
| avg transaction cost | 0.0705% |
| compounded gross return | 77.9428% |
| compounded net return | 74.9172% |

Baseline 대비:

| 항목 | 차이 |
|---|---:|
| avg net 1M return | +0.5790%p |
| net win rate | +4.0000%p |
| avg net 1M risk-adjusted | +0.7396%p |
| worst net 1M return | +4.2794%p |
| compounded net return | +22.6969%p |

## Cost Sensitivity

`mode_switch_stress_tail_asset`는 5bp, 10bp, 20bp, 30bp 모두 best net policy를 유지했다.

| cost bps | avg net 1M ret | avg net risk adj | worst net 1M | compounded net | baseline delta |
|---:|---:|---:|---:|---:|---:|
| 5 | 2.4458% | 0.9493% | -3.3938% | 76.4247% | +22.9529%p |
| 10 | 2.4107% | 0.9143% | -3.4338% | 74.9172% | +22.6969%p |
| 20 | 2.3406% | 0.8441% | -3.5138% | 71.9418% | +22.1956%p |
| 30 | 2.2704% | 0.7740% | -3.5938% | 69.0131% | +21.7025%p |

## Interpretation

거래비용을 보수적으로 30bp까지 올려도 mode switch 정책의 우위가 유지됐다.
다만 avg one-way turnover가 약 70%로 높기 때문에, 실제 운영 전에는 다음 보강이 필요하다.

- turnover cap 적용 실험
- 기존 holdings와 겹치는 종목은 유지하는 buffer rule
- 신규 편입 threshold 강화
- 매월 전환이 아니라 stress 전환 시에만 rebalance하는 운영 규칙 검토

## Operating View

현재까지의 판단:

- 대표 성장형: `hybrid_b50_ai50_top3_role`
- 신규 대표 후보: `mode_switch_stress_tail_asset`
- 비용 차감 후에도 신규 후보의 우위 유지
- 다음 보완 과제는 turnover cap / rebalance buffer 적용
