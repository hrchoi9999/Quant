# AI Horizon Label Experiment - 2026-05-04

## Purpose

Test period-specific labels for `AI-OVERLAY-V01`.

Important perspective split:

- Backtest/reconstructed labels are used for model training.
- Actual live labels are separately counted only for operating validation.
- Current live samples are still too small for 2M/3M live learning.

Feature set:

- `kiwoom_dart`

## Live vs Reconstructed Coverage

| label | reconstructed rows | reconstructed positive rate | live rows | live positive rate |
|---|---:|---:|---:|---:|
| `label_positive_1w` | 20,604 | 48.52% | 180 | 60.00% |
| `label_quality_1w` | 20,604 | 41.67% | 180 | 56.11% |
| `label_positive_2w` | 20,506 | 49.52% | 121 | 70.25% |
| `label_quality_2w` | 20,506 | 42.49% | 121 | 67.77% |
| `label_positive_1m` | 20,427 | 50.10% | 89 | 76.40% |
| `label_quality_1m` | 20,427 | 40.50% | 89 | 73.03% |
| `label_positive_2m` | 20,207 | 51.47% | 0 | N/A |
| `label_quality_2m` | 20,207 | 40.15% | 0 | N/A |
| `label_positive_3m` | 20,055 | 52.58% | 0 | N/A |
| `label_quality_3m` | 20,055 | 39.89% | 0 | N/A |

## GB Results

| label | AUC | top30 1M return | top30 win rate |
|---|---:|---:|---:|
| `label_positive_1w` | 0.510 | 0.49% | 60.00% |
| `label_quality_1w` | 0.511 | 3.10% | 46.67% |
| `label_positive_2w` | 0.530 | 3.72% | 60.00% |
| `label_quality_2w` | 0.516 | 20.45% | 60.00% |
| `label_positive_1m` | 0.519 | 6.42% | 83.33% |
| `label_quality_1m` | 0.528 | 0.38% | 33.33% |
| `label_positive_2m` | 0.532 | 4.99% | 76.67% |
| `label_quality_2m` | 0.533 | 7.09% | 63.33% |
| `label_positive_3m` | 0.520 | 8.76% | 76.67% |
| `label_quality_3m` | 0.529 | 10.90% | 63.33% |

## Interpretation

The most learnable horizon appears to be the 2M quality label.

Observations:

- 1W labels are weak and noisy.
- 2W quality has very high top30 1M return but lower AUC, so it may be unstable.
- 1M positive keeps the best win-rate profile.
- 2M quality has the best AUC and reasonable top30 return.
- 3M quality has good return but live validation is unavailable.

Recommended next shadow design:

- Short-term confirmation tag: `label_positive_1m`
- Medium-term quality tag: `label_quality_2m`
- High-return experimental tag: `label_quality_3m`

Do not use 2M/3M as live-validated claims yet.
They are currently backtest/reconstructed learning signals only.

## Artifacts

- `D:\Quant\scripts\run_ai_horizon_label_experiment.py`
- `D:\Quant\reports\ai_overlay_v01\ai_horizon_label_eval_20260504.md`
- `D:\Quant\reports\ai_overlay_v01\ai_horizon_label_eval_20260504.csv`
- `D:\Quant\reports\ai_overlay_v01\ai_horizon_label_summary_20260504.csv`
