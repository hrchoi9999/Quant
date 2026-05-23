# AI Model-Specific Learning V01 - 2026-05-06

## Purpose

정식 모델명 `AI-CANDIDATE-VALIDATION-V01` 위에 모델별 전용 학습층을 추가한다.

기존 산출물과 일부 코드에서 쓰는 `AI-OVERLAY-V01`은 legacy alias다. 한글명은 `퀀트후보검증AI`로 관리한다.

목표는 전체 모델에 공통으로 적용되는 AI tag와 별도로, 각 모델의 종목 선정 성격에 맞는 보조 점수와 위험 태그를 제공하는 것이다.

## Scope

Implemented in:

- `D:\Quant\scripts\build_ai_overlay_v01.py`
- `D:\Quant\scripts\build_ai_shadow_performance_tracker.py`
- `D:\Quant\scripts\build_ai_live_shadow_tracker.py`
- `D:\Quant\src\quant_service\run_daily_quant_pipeline.py`

Outputs:

- `D:\Quant\reports\ai_overlay_v01\ai_overlay_shadow_scores_20260504.csv`
- `D:\Quant\reports\ai_overlay_v01\ai_shadow_performance_tracker_20260504.csv`
- `D:\Quant\data\db\ai_learning.db`

## Training Rule

Model-specific training is attempted by `(scope_key, model_id)`.

Minimum label rows:

- `MIN_MODEL_SPECIFIC_LABEL_ROWS = 200`

Labels:

- quality model: `label_quality_1m`
- risk model: `label_bad_1m_strict`

Model:

- Gradient Boosting classifier

Fallback:

- If a model has insufficient labels, the row receives `MS_FALLBACK_COMMON`.
- Common AI overlay scores remain available for all rows.

## New Shadow Columns

Added to `ai_overlay_shadow_scores`:

- `ai_model_specific_quality_prob`
- `ai_model_specific_risk_prob`
- `ai_model_specific_tag`

Tags:

- `MS_CONFIRM`: model-specific quality probability is high and risk is not high
- `MS_RISK_REVIEW`: model-specific risk probability is high
- `MS_OBSERVE`: model-specific model exists but signal is not decisive
- `MS_FALLBACK_COMMON`: insufficient model-specific training data

## 2026-05-04 Training Coverage

Model-specific training succeeded for:

- `internal / I-STOCK-STRONG-RSI-V01`
- `internal / S2`
- `internal / S2_PIT_V01`
- `internal / S3`
- `internal / S3_ACCEL_V01`
- `internal / S3_CORE2`
- `tseries / T-STOCK-V01`
- `tseries / T-ETF-V01`

Fallback due to insufficient labels:

- `user / stable`
- `user / balanced`
- `user / growth`
- `internal / S4`
- `internal / S5`
- `internal / S6`

## Reconstructed Shadow Result

2026-05-04 reconstructed tracker, 1M horizon:

| tag | sample_count | avg_return | win_rate |
|---|---:|---:|---:|
| `MS_CONFIRM` | 338 | 15.02% | 87.87% |
| `MS_FALLBACK_COMMON` | 159 | 6.50% | 70.44% |
| `MS_OBSERVE` | 1,734 | 3.25% | 47.98% |
| `MS_RISK_REVIEW` | 155 | -5.17% | 20.00% |

Interpretation:

- Model-specific tags separate candidate quality better than a flat common tag in reconstructed history.
- `MS_CONFIRM` is a strong shadow confirmation tag.
- `MS_RISK_REVIEW` is a useful caution or exclusion-review tag.
- This is not yet live-only evidence.

## Live Tracking

Live-only tracking now includes `model_specific_tag` grouping.

Current baseline:

- First shadow score date: `2026-05-04`
- First live performance date: `2026-05-04`
- Live sample counts are currently `0` because no forward trading-day horizon has elapsed.

Expected live validation:

- `1w`: after 5 trading days
- `2w`: after 10 trading days
- `1m`: after 21 trading days

## Operating Guidance

Do not replace existing S/T/I model logic yet.

Use model-specific AI as:

- confirmation tag: `MS_CONFIRM`
- caution tag: `MS_RISK_REVIEW`
- monitoring tag: `MS_OBSERVE`
- fallback marker: `MS_FALLBACK_COMMON`

Promotion to actual model filter requires live-only validation.
