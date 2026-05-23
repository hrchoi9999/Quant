# QS 작업요청서: 내부용 모델 페이지 AI Overlay Shadow 표시

- 작성일: 2026-05-12
- 요청 주체: Quant thread
- 대상 thread: QuantService(QS)
- 관련 화면: admin `내부용 모델`
- 목적: 기존 전략모델별 baseline 성과와 `전략모델 + AI overlay` 성과를 같은 화면에서 비교 관찰

## 배경

Quant에서 주식 전략모델에 대해 AI overlay policy map 백테스트를 완료했습니다.

AI 모델은 독립 추천모델이 아니라 기존 전략모델의 후보/비중을 보정하는 overlay입니다.

따라서 내부용 모델 페이지에서는 각 전략모델 기준으로 아래 비교가 보여야 합니다.

- 기존 전략모델 baseline
- 전략모델 + AI overlay policy map
- baseline 대비 수익률, 승률, MDD 변화

## Quant 산출물

QS에서 우선 참조할 current payload는 아래입니다.

- `D:\Quant\service_platform\web\admin_data\current\internal_models_ai_overlay_shadow_current.json`

보조 산출물은 아래입니다.

- `D:\Quant\reports\ai_overlay_backtest\AI_OVERLAY_POLICY_MAP_BACKTEST_20260511.md`
- `D:\Quant\reports\ai_overlay_backtest\ai_overlay_policy_map_vs_baseline_by_model_20260511.csv`
- `D:\Quant\reports\ai_overlay_backtest\ai_overlay_policy_map_vs_baseline_by_family_20260511.csv`
- `D:\Quant\reports\ai_overlay_backtest\ai_overlay_policy_map_holdings_20260511.csv`
- `D:\Quant\reports\ai_overlay_backtest\ai_overlay_policy_map_periods_20260511.csv`

## 화면 요구사항

내부용 모델 페이지에서 각 전략모델 row 또는 상세 영역에 `AI Overlay Shadow` 섹션을 추가해 주세요.

표시 항목:

| 항목 | 설명 |
| --- | --- |
| baseline avg return | 기존 전략모델 평균 period return |
| AI overlay avg return | policy map 적용 후 평균 period return |
| return delta | AI overlay - baseline |
| baseline win rate | 기존 전략모델 승률 |
| AI overlay win rate | policy map 적용 후 승률 |
| win rate delta | AI overlay - baseline |
| baseline MDD | 기존 전략모델 NAV MDD |
| AI overlay MDD | policy map 적용 후 NAV MDD |
| MDD delta | AI overlay - baseline |
| mapped policy | 해당 전략모델에 적용된 AI overlay 정책 |

## 현재 policy map

| 전략모델 | 적용 정책 |
| --- | --- |
| S2 | `valuation_tilt_renorm` |
| S2_PIT_V01 | `rank_delta_tilt_renorm` |
| S3 | `combo_equal_renorm` |
| S3_CORE2 | `combo_equal_renorm`, 단 MDD 악화로 보수 rule 필요 |
| S3_ACCEL_V01 | `risk_tilt_renorm` |
| I-STOCK-STRONG-RSI-V01 | `combo_equal_renorm` |
| T-STOCK-V01 | `combo_equal_renorm` |
| user stable | `rank_delta_tilt_renorm` |
| user balanced | `rank_delta_tilt_renorm` |
| user growth | `combo_equal_renorm` |

## UI 해석 가이드

사용자가 혼동하지 않도록 아래 문구를 화면에 짧게 표시해 주세요.

> AI Overlay Shadow는 실제 추천에 반영된 결과가 아니라, 기존 전략모델 후보에 AI 보정 rule을 적용했을 때의 연구용 비교 결과입니다.

특히 `S3_CORE2`는 수익률 개선폭은 크지만 MDD가 악화된 케이스이므로 아래와 같이 표시해 주세요.

> S3_CORE2는 수익 개선 가능성은 있으나 MDD 악화가 확인되어 보수 rule 추가 검증 중입니다.

## N/A 처리

- S4/S5/S6처럼 유효 period 성과가 없는 항목은 `0%`가 아니라 `N/A`로 표시해 주세요.
- null, NaN, 빈 문자열은 모두 `N/A`로 표시해 주세요.
- delta 계산이 불가능한 경우도 `N/A`로 표시해 주세요.

## 기대 결과

내부용 모델 페이지에서 사용자가 다음을 바로 확인할 수 있어야 합니다.

- 이 전략모델에 AI overlay를 붙였을 때 성과가 좋아졌는지
- 수익률 개선이 MDD 악화를 동반했는지
- 해당 전략모델에는 어떤 AI overlay policy가 배정되었는지
- 아직 shadow 관찰 단계인지 여부
