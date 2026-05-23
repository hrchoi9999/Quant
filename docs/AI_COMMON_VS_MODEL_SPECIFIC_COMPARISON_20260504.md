# AI Common vs Model-Specific Comparison - 2026-05-04

## Purpose

공통 `AI-OVERLAY-V01` 태그와 모델별 전용 AI 태그가 같은 종목에 대해 어떤 차이를 보이는지 비교한다.

이 비교는 reconstructed shadow 기준이며, 실제 live-only 성과는 별도 tracker로 누적한다.

## Artifacts

- Script: `D:\Quant\scripts\compare_ai_common_vs_model_specific.py`
- Detail: `D:\Quant\reports\ai_overlay_v01\ai_common_vs_model_specific_detail_20260504.csv`
- Summary: `D:\Quant\reports\ai_overlay_v01\ai_common_vs_model_specific_summary_20260504.csv`
- Matrix: `D:\Quant\reports\ai_overlay_v01\ai_common_vs_model_specific_matrix_20260504.csv`
- Report: `D:\Quant\reports\ai_overlay_v01\ai_common_vs_model_specific_20260504.md`

## Decision Matrix

| common \ model | MS_CONFIRM | MS_FALLBACK | MS_OBSERVE | MS_RISK |
|---|---:|---:|---:|---:|
| `COMMON_CONFIRM` | 98 | 95 | 63 | 9 |
| `COMMON_OBSERVE` | 300 | 172 | 1803 | 158 |
| `COMMON_RISK` | 8 | 7 | 13 | 10 |

## 1M Performance

### Common AI

| common bucket | rows | samples | avg_return | win_rate |
|---|---:|---:|---:|---:|
| `COMMON_CONFIRM` | 265 | 210 | 8.67% | 74.76% |
| `COMMON_OBSERVE` | 2433 | 2151 | 4.26% | 51.42% |
| `COMMON_RISK` | 38 | 25 | -1.50% | 36.00% |

### Model-Specific AI

| model bucket | rows | samples | avg_return | win_rate |
|---|---:|---:|---:|---:|
| `MS_CONFIRM` | 406 | 338 | 15.02% | 87.87% |
| `MS_FALLBACK` | 274 | 159 | 6.50% | 70.44% |
| `MS_OBSERVE` | 1879 | 1734 | 3.25% | 47.98% |
| `MS_RISK` | 177 | 155 | -5.17% | 20.00% |

### Combination

| bucket | rows | samples | avg_return | win_rate |
|---|---:|---:|---:|---:|
| `model_only_confirm` | 308 | 267 | 15.40% | 88.76% |
| `both_confirm` | 98 | 71 | 13.60% | 84.51% |
| `common_only_confirm` | 167 | 139 | 6.16% | 69.78% |
| `both_observe_or_neutral` | 1803 | 1677 | 3.13% | 47.59% |
| `model_only_risk` | 158 | 139 | -5.29% | 18.70% |
| `both_risk` | 10 | 9 | -15.21% | 11.11% |

## Interpretation

모델별 AI는 공통 AI보다 더 강한 분리력을 보였다.

Key points:

- `MS_CONFIRM`은 공통 `COMMON_CONFIRM`보다 1M 평균수익률과 승률이 높다.
- `model_only_confirm`은 공통 AI가 관찰 또는 위험으로 본 종목 중 모델별 AI가 확인한 후보이며, 1M 평균 `15.40%`, 승률 `88.76%`로 가장 강했다.
- `common_only_confirm`은 1M 평균 `6.16%`로 나쁘지는 않지만, 모델별 AI 확인 후보보다 약했다.
- `MS_RISK`와 `both_risk`는 실제로 낮은 성과를 보여 위험 태그로 의미가 있다.

## Operating Conclusion

공통 AI는 전체 시장 공통 필터로 유지한다.

모델별 AI는 각 모델의 후보를 재정렬하거나 위험 후보를 표시하는 보조층으로 운영한다.

Suggested usage:

- `both_confirm`: 강한 확인 후보
- `model_only_confirm`: 모델별 AI가 새로 살린 후보, 우선 관찰
- `common_only_confirm`: 공통 AI는 좋게 보지만 해당 모델 기준 확신은 약한 후보
- `model_only_risk` / `both_risk`: 위험 검토 후보

Live-only tracker가 충분히 쌓이기 전까지 실제 종목 교체 로직에는 반영하지 않는다.
