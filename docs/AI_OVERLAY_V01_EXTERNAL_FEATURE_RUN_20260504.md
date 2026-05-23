# AI Overlay V01 External Feature Run - 2026-05-04

## Purpose

Rebuild `AI-OVERLAY-V01` after adding temporary Naver investor-flow features and OpenDART disclosure-event features.

## Inputs

- Admin event payload: `D:\Quant\service_platform\web\admin_data\current\admin_new_entry_tracker.json`
- Price DB: `D:\Quant\data\db\price.db`
- External feature DB: `D:\Quant\data\db\ai_feature_ext.db`

External feature sources:

- Naver Finance temporary investor flow
  - foreign net volume/value
  - institution net volume/value
  - net-buy days and streaks
  - foreign holding rate
- OpenDART official disclosure events
  - 30d/90d event counts
  - major event / earnings / ownership / market-watch counts
  - days since last event
  - last event category

## Command

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\build_ai_overlay_v01.py --asof 2026-05-04
```

## Output

- DB: `D:\Quant\data\db\ai_learning.db`
- Training mart: `D:\Quant\reports\ai_overlay_v01\ai_overlay_training_mart_20260504.csv`
- Shadow scores: `D:\Quant\reports\ai_overlay_v01\ai_overlay_shadow_scores_20260504.csv`
- Evaluation: `D:\Quant\reports\ai_overlay_v01\ai_overlay_model_eval_20260504.md`

## Result Summary

- mart rows: `20,819`
- 1M label rows: `20,427`
- live rows: `322`
- shadow rows: `2,736`
- Naver feature rows with at least one non-null Naver feature: `721`
- DART rows with prior disclosure-event recency: `9`
- rows since first Naver date `2026-02-03`: `777`

Evaluation:

| label | model | train | test | auc | top30 1M return | top30 win rate |
|---|---:|---:|---:|---:|---:|---:|
| label_quality_1m | logistic | 15663 | 4764 | 0.503 | 1.05% | 60.00% |
| label_quality_1m | gb | 15663 | 4764 | 0.533 | 4.90% | 76.67% |
| label_risk_1m | logistic | 15663 | 4764 | 0.505 | 6.05% | 46.67% |
| label_risk_1m | gb | 15663 | 4764 | 0.529 | 15.66% | 63.33% |

Shadow tags:

- internal / AI_CONFIRM: `103`
- internal / AI_WATCH: `2,289`
- internal / AI_CAUTION: `74`
- tseries / AI_CONFIRM: `58`
- tseries / AI_WATCH: `100`
- tseries / AI_CAUTION: `5`
- user / AI_CONFIRM: `3`
- user / AI_WATCH: `86`
- user / AI_CAUTION: `18`

## Interpretation

The external features are now included in the training mart, but they should still be treated as shadow features.

Reason:

- Naver investor-flow data only covers recent 2026 history.
- The current chronological train/test split is mostly pre-2026, so the external-flow features do not yet have enough labeled history to materially improve the historical AI model.
- DART event coverage is currently sparse in this event mart.

Operating decision:

- Keep `AI-OVERLAY-V01` in shadow mode.
- Use external features for monitoring and future learning.
- Replace or validate Naver flow with Kiwoom flow when Kiwoom API access is available.
