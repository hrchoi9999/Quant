# E-Series ETF Mode Switch Stability Check

- 기준일: 2026-05-12
- 대상: E-ETF-V01 mode switch + buffer 70
- 목적: stress 전환 규칙이 threshold 변화에 과민하지 않은지 검증

## 결과

| variant | stress dates | transitions | single flips | avg net 1M | risk adj | worst | compounded | avg turnover |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| loose | 14 | 7 | 2 | 2.58% | 1.07% | -3.43% | 82.29% | 43.46% |
| base | 13 | 9 | 4 | 2.50% | 0.98% | -3.43% | 78.73% | 44.42% |
| tight | 12 | 7 | 1 | 2.51% | 0.99% | -3.43% | 79.06% | 44.17% |

## 해석

- loose/base/tight 모두 worst 1M 손실은 동일하게 유지됐다.
- 성과와 turnover도 큰 차이가 없어, 전환 규칙 자체는 큰 틀에서 안정적이다.
- 다만 base 규칙은 single-month flip이 4회로 상대적으로 많다.
- tight 규칙은 성과 훼손 없이 flip이 1회로 줄어, 운영 안정성 관점에서 더 적합하다.

## 운영 판단

현재 shadow 후보는 `mode_switch_buffer_70` 유지가 적절하다.

다만 stress 판단 threshold는 현 base보다 한 단계 보수적인 tight rule을 함께 관찰 후보로 두는 것이 좋다. 다음 데이터 업데이트 후에도 tight가 비슷한 성과와 낮은 flip을 유지하면, mode switch의 기본 전환 규칙을 tight 쪽으로 조정하는 것을 검토한다.

운영 후보 구분:

- 현재 후보: `mode_switch_buffer_70_base`
- 추가 shadow 후보: `mode_switch_buffer_70_tight`
- 민감도 관찰 후보: `mode_switch_buffer_70_loose`

## 산출물

- `D:\Quant\scripts\run_e_series_etf_mode_switch_stability_check.py`
- `D:\Quant\reports\e_series_etf\e_series_etf_mode_switch_stability_check_current_holdings_20260512.csv`
- `D:\Quant\reports\e_series_etf\e_series_etf_mode_switch_stability_check_summary_20260512.csv`
- `D:\Quant\reports\e_series_etf\e_series_etf_mode_switch_stability_check_20260512.json`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_mode_switch_stability_check_current.json`
