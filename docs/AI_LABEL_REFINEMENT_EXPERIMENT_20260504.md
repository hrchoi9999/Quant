# AI Label Refinement Experiment - 2026-05-04

## Purpose

Test whether more precise stock-level labels improve `AI-OVERLAY-V01`.

Unit of learning:

- `model + ticker + event_date`

Feature set:

- `kiwoom_dart`

## Labels Tested

| label | positive rate | meaning |
|---|---:|---|
| `label_quality_1m_current` | 49.90% | 1M return positive, MDD better than -15%, Sharpe positive when available |
| `label_quality_1m_loose` | 50.02% | 1M return positive, MDD better than -20% |
| `label_quality_1m_balanced` | 40.32% | 1M return at least 3%, MDD better than -15%, Sharpe positive |
| `label_quality_1m_strict` | 34.45% | 1M return at least 5%, MDD better than -10%, Sharpe above 0.3 |
| `label_bad_1m_strict` | 39.16% | 1M return below -3%, MDD worse than -15%, or Sharpe below -0.3 |

## Results

| label | model | auc | top30 1M return | top30 win rate |
|---|---:|---:|---:|---:|
| `label_quality_1m_current` | logistic | 0.495 | 6.45% | 53.33% |
| `label_quality_1m_current` | gb | 0.521 | 6.42% | 83.33% |
| `label_quality_1m_loose` | logistic | 0.497 | 6.45% | 53.33% |
| `label_quality_1m_loose` | gb | 0.521 | 6.42% | 83.33% |
| `label_quality_1m_balanced` | logistic | 0.503 | 8.30% | 56.67% |
| `label_quality_1m_balanced` | gb | 0.526 | 0.38% | 33.33% |
| `label_quality_1m_strict` | logistic | 0.519 | 8.17% | 50.00% |
| `label_quality_1m_strict` | gb | 0.540 | 9.60% | 60.00% |
| `label_bad_1m_strict` | logistic | 0.519 | 16.78% | 66.67% |
| `label_bad_1m_strict` | gb | 0.541 | 9.77% | 50.00% |

## Interpretation

The stricter labels look more informative than the current loose quality label.

Key takeaways:

- Current/loose quality labels preserve high win rate but have weaker AUC.
- Strict quality label improves AUC and top30 average return.
- Strict bad label has the best AUC, but its direct top30 interpretation is different because it models bad-event probability.

Recommended next step:

- Keep `label_quality_1m_current` for conservative confirmation tags.
- Add `label_quality_1m_strict` as a high-conviction upside tag.
- Add `label_bad_1m_strict` as an avoid/risk tag, but score it inversely for candidate selection.

Do not promote this to production yet.
Use it as the next shadow scoring design.

## Artifacts

- `D:\Quant\scripts\run_ai_label_refinement_experiment.py`
- `D:\Quant\reports\ai_overlay_v01\ai_label_refinement_eval_20260504.md`
- `D:\Quant\reports\ai_overlay_v01\ai_label_refinement_eval_20260504.csv`
- `D:\Quant\reports\ai_overlay_v01\ai_label_refinement_summary_20260504.csv`
