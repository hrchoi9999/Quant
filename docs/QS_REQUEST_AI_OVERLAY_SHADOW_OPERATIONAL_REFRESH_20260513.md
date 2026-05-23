# QS 작업요청서: AI Overlay Shadow Tracking 운영 반영

- 작성일: 2026-05-13
- 요청 주체: Quant thread
- 대상 thread: QuantService(QS)
- 관련 화면: admin `내부용 모델`, admin `AI 학습 모델`
- 상태: admin-only shadow observation

## 요청 목적

Quant에서 AI overlay shadow tracking refresh를 운영 루틴에 연결했습니다.

QS에서는 Quant가 제공하는 current payload를 읽어 admin 화면에서 아래 내용을 확인할 수 있게 반영해 주세요.

- 전략모델 baseline 대비 AI overlay 적용 시 성과 변화
- 전략모델별 mapped AI overlay policy
- AI 학습 모델 페이지에서 overlay 효과 모니터링 요약
- shadow 관찰 단계이며 실제 추천 반영 전이라는 상태

## Quant 제공 current payload

QS는 아래 current payload만 우선 참조하면 됩니다.

```text
D:\Quant\service_platform\web\admin_data\current\internal_models_ai_overlay_shadow_current.json
D:\Quant\service_platform\web\admin_data\current\ai_learning_overlay_monitor_current.json
```

현재 기준일:

```text
as_of_date: 2026-05-12
status: shadow_observation
live_recommendation_applied: false
```

## 내부용 모델 페이지 요청

admin `내부용 모델` 페이지에서 각 전략모델별로 `AI Overlay Shadow` 섹션을 보여 주세요.

참조 payload:

```text
internal_models_ai_overlay_shadow_current.json
```

표시 항목:

| 항목 | payload field | 설명 |
| --- | --- | --- |
| mapped policy | `model_summary[].mapped_policy` | 전략모델별 적용 예정 AI overlay 정책 |
| policy label | `model_summary[].mapped_policy_label_ko` | 사용자 표시용 한글 정책명 |
| baseline avg return | `baseline_avg_period_return` | 기존 전략모델 평균 period return |
| overlay avg return | `avg_period_return` | AI overlay 적용 후 평균 period return |
| return delta | `avg_return_delta` / `return_delta_pctp` | baseline 대비 수익률 변화 |
| baseline win rate | `baseline_win_rate` | 기존 전략모델 승률 |
| overlay win rate | `win_rate` | overlay 적용 후 승률 |
| win rate delta | `win_rate_delta` / `win_rate_delta_pctp` | 승률 변화 |
| baseline MDD | `baseline_nav_mdd` | 기존 전략모델 MDD |
| overlay MDD | `nav_mdd` | overlay 적용 후 MDD |
| MDD delta | `nav_mdd_delta` / `mdd_delta_pctp` | MDD 변화 |
| result label | `overlay_result_label_ko` | 수익/리스크 개선 여부 요약 |

권장 표시:

- 각 전략모델 row에 간단 badge: `mapped_policy_label_ko`, `overlay_result_label_ko`
- 상세 영역에는 baseline vs overlay 비교 table
- `S3_CORE2`는 caution note 표시

주의 문구:

```text
AI Overlay Shadow는 실제 추천에 반영된 결과가 아니라, 기존 전략모델 후보에 AI 보정 rule을 적용했을 때의 연구용 비교 결과입니다.
```

## AI 학습 모델 페이지 요청

admin `AI 학습 모델` 페이지에 `AI Overlay 효과 모니터링` 섹션을 추가해 주세요.

참조 payload:

```text
ai_learning_overlay_monitor_current.json
```

표시 항목:

- component models:
  - `AI-DOWNSIDE-RISK-V01` / `하락위험예측AI`
  - `AI-GROWTH-VALUATION-V01` / `주가수준평가AI`
  - `AI-CANDIDATE-RANK-DELTA-V01` / `후보순위조정AI`
- `overlay_policy_map_summary.family_summary`
- `overlay_policy_map_summary.model_summary`
- `combo_ablation_summary.best_by_family`
- `combo_ablation_summary.best_by_model`

사용자 해석 가이드:

```text
이 섹션은 개별 AI 모델 자체 성능이 아니라, 기존 전략모델에 AI overlay를 붙였을 때 baseline 대비 성과가 개선되는지를 보는 shadow monitoring 영역입니다.
```

## N/A 처리 원칙

- null, NaN, 빈 값은 `0%`가 아니라 `N/A`로 표시해 주세요.
- 계산 불가능한 delta도 `N/A`로 표시해 주세요.
- period 수가 부족한 모델은 `관찰 부족` 상태로 표시해 주세요.

## 운영 원칙

- public 추천/종목/비중에는 반영하지 않습니다.
- admin-only 관찰용입니다.
- 최소 4~8주 shadow tracking 후 실제 운영 적용 여부를 별도 판단합니다.
- Quant thread는 QS 코드를 직접 수정하지 않고 current payload만 제공합니다.

## 검증 요청

- `내부용 모델` 페이지에서 전략모델별 baseline vs AI overlay 비교가 보이는지 확인
- `AI 학습 모델` 페이지에서 overlay 효과 모니터링 섹션이 보이는지 확인
- `live_recommendation_applied=false` 상태가 명확히 표시되는지 확인
- null 값이 0%로 오표시되지 않는지 확인
- public 화면에는 노출되지 않는지 확인
