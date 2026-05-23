# E-Series ETF Operational Policy Hierarchy

- 기준일: 2026-05-12
- 전략 모델: E-ETF-V01 / ETF전용 E시리즈AI
- 운영 단계: admin-only shadow tracking

## 운영 Hierarchy

| Level | Layer | Policy | Status |
| ---: | --- | --- | --- |
| 0 | Return basis | `price_return_fallback` | active input |
| 1 | Sleeve selection AI | `AI-E-ETF-SLEEVE-SELECTION-V01` | active model |
| 2 | Base portfolio policy | `hybrid_b50_ai50_top3_role` | base reference |
| 3 | Mode switch reference | `mode_switch_stress_tail_asset` | reference overlay |
| 4 | Execution control | `mode_switch_buffer_70_base` | primary shadow candidate |
| 5 | Stability challenger | `mode_switch_buffer_70_tight` | shadow challenger |
| 6 | Sensitivity only | `mode_switch_buffer_70_loose` | observation only |

## 핵심 정의

- 현재 기준 후보는 `mode_switch_buffer_70_base`다.
- `mode_switch_buffer_70_tight`는 바로 대체하지 않고 shadow challenger로 병행 관찰한다.
- `mode_switch_buffer_70_loose`는 성과 민감도 확인용이며 운영 승격 후보가 아니다.
- ETF 분배금 원천이 아직 없으므로 현재 return basis는 `price_return_fallback`이다.
- 분배금 원천 확보 후에는 total-return 기준으로 전체 hierarchy를 재검증한다.

## 승격 조건

- 최소 4~8주 shadow tracking 후 판단
- tight가 base 대비 single-month flip을 낮게 유지
- tight가 base 대비 worst 1M return을 악화시키지 않음
- turnover와 skipped periods가 과도하게 악화되지 않음
- total-return 기준 재검증에서도 우위 유지

## 산출물

- `D:\Quant\scripts\build_e_series_etf_operational_policy_hierarchy.py`
- `D:\Quant\reports\e_series_etf\e_series_etf_operational_policy_hierarchy_20260512.json`
- `D:\Quant\reports\e_series_etf\e_series_etf_operational_policy_hierarchy_20260512.md`
- `D:\Quant\service_platform\web\admin_data\current\e_series_etf_operational_policy_hierarchy_current.json`

