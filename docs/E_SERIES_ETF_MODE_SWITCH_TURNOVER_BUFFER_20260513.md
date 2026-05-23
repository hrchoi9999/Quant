# E-Series ETF Mode Switch Turnover Cap / Rebalance Buffer Test

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01
- 대상 정책: mode_switch_stress_tail_asset
- 거래비용 가정: one-way turnover 10 bps
- 목적: mode switch 정책의 높은 회전율을 turnover cap 또는 rebalance buffer로 낮출 수 있는지 검증

## 결론

현재 결과에서는 단순 turnover cap보다 rebalance buffer가 더 적합하다.

- `mode_switch_buffer_70`이 가장 우수했다.
- 평균 turnover는 full mode switch의 70.51%에서 44.42%로 낮아졌다.
- 26개 평가월 중 12개 월에서 리밸런싱을 건너뛰었다.
- 평균 net 1M 수익률, risk-adjusted 수익률, compounded net return이 모두 full mode switch보다 높았다.
- worst net 1M return은 full mode switch와 동일했다.

## 주요 결과

| policy | avg net 1M | net risk adj | worst net | compounded net | avg turnover | skipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mode_switch_buffer_70 | 2.50% | 0.98% | -3.43% | 78.73% | 44.42% | 12 |
| mode_switch_buffer_50 | 2.42% | 0.90% | -3.43% | 75.47% | 65.71% | 5 |
| mode_switch_full | 2.41% | 0.91% | -3.43% | 74.92% | 70.51% | 0 |
| mode_switch_cap_90 | 2.41% | 0.90% | -3.62% | 74.83% | 70.24% | 0 |
| mode_switch_cap_80 | 2.38% | 0.84% | -4.71% | 73.44% | 68.54% | 0 |
| mode_switch_cap_70 | 2.28% | 0.71% | -5.80% | 69.54% | 63.95% | 0 |
| mode_switch_cap_50 | 2.17% | 0.59% | -7.47% | 65.38% | 49.60% | 0 |
| mode_switch_cap_30 | 2.17% | 0.60% | -8.48% | 64.91% | 30.77% | 0 |

## 해석

Turnover cap은 목표 포트폴리오로 이동하는 속도를 강제로 늦춘다. 이 방식은 회전율은 낮추지만, stress/risk-off 구간에서 방어 포트폴리오로 전환하는 힘도 같이 약해져 worst return이 나빠졌다.

Rebalance buffer는 목표 변화가 충분히 크지 않을 때만 리밸런싱을 건너뛴다. `buffer_70`은 작은 변경을 무시하고 큰 regime change만 반영하는 구조가 되어, 거래비용과 불필요한 교체를 줄이면서 성과를 유지했다.

## 운영 후보

1. 기본 후보: `mode_switch_buffer_70`
2. 보수 후보: `mode_switch_buffer_50`
3. 관찰 기준: full mode switch 대비 net return, worst return, avg turnover, skipped periods

현재 단계에서는 `mode_switch_buffer_70`을 shadow portfolio 운영 후보로 올리고, 다음 데이터 업데이트 이후 동일 우위가 유지되는지 관찰하는 것이 적절하다.

## 산출물

- `D:\Quant\scripts\run_e_series_etf_mode_switch_turnover_buffer.py`
- `D:\Quant\reports\e_series_etf\e_series_etf_mode_switch_turnover_buffer_summary_20260512.csv`
- `D:\Quant\reports\e_series_etf\e_series_etf_mode_switch_turnover_buffer_20260512.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_mode_switch_turnover_buffer_current.json`

