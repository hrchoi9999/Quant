# AI-GROWTH-VALUATION-V01 QuantMarket Context Training Analysis - 2026-05-06

## Purpose

Test whether the additional QuantMarket AI training mart improves `AI-GROWTH-VALUATION-V01`.

Newly consumed QuantMarket inputs:

- `market_context_daily_current.csv`
- `theme_context_daily_quant_bucket_current.csv`
- `risk_context_daily_current.csv`
- `flow_context_daily_current.csv`

Joined feature groups:

- Market state and breadth
- Quant theme proxy momentum and rotation
- Risk and defensive asset pressure
- Recent flow context coverage fields

## Coverage Check

Feature rows:

- Total: `38,512`
- QuantMarket feature columns added: `44`
- `qm_market_state_score` coverage: `38,512 / 38,512`
- `qm_theme_momentum_score` coverage: `37,903 / 38,512`
- `qm_theme_mapping_confidence` coverage: `37,903 / 38,512`
- `qm_market_stress_score` coverage: `38,512 / 38,512`
- `qm_flow_context_available` coverage: `38,512 / 38,512`

Note:

- Flow context is structurally present from 2017, but actual flow values are mostly unavailable before 2026-03-26.
- Theme features are proxy-based and should be interpreted with `qm_theme_mapping_confidence`.

## Validation Comparison

| Metric | Market-context only | Full QuantMarket context | Change |
|---|---:|---:|---:|
| Validation Rank IC | 0.186 | 0.174 | -0.012 |
| Validation IC | 0.187 | 0.175 | -0.012 |
| Top30 excess 12M | 80.68% | 75.75% | -4.93%p |
| Top30 return 12M | 126.01% | 129.76% | +3.75%p |
| Top-bottom spread 12M | 86.58% | 82.39% | -4.19%p |
| Top30 win rate | 76.67% | 76.67% | 0.00%p |

Interpretation:

- Full QuantMarket context did not improve whole-universe ranking quality.
- It did improve the absolute return of top 30 candidates in validation.
- This suggests the new data is more useful for top-candidate selection than for full cross-sectional ordering.

## Top-N Portfolio Proxy Comparison

| Window | Market-context only CAGR | Full QM CAGR | Market-context only Sharpe | Full QM Sharpe |
|---|---:|---:|---:|---:|
| FULL | 35.33% | 36.32% | 1.267 | 1.288 |
| 1Y | 42.90% | 50.06% | 2.038 | 2.098 |
| 2Y | 49.87% | 53.52% | 2.137 | 2.313 |
| 3Y | 33.09% | 36.13% | 1.307 | 1.392 |
| 5Y | 51.39% | 54.04% | 1.754 | 1.834 |

Interpretation:

- Top-N portfolio proxy improved across all windows.
- This is the strongest evidence that QuantMarket context is useful.
- The model may be learning better timing and theme/risk context for high-ranked candidates, even if full ranking IC is slightly lower.

## Classification AUC

| Label | AUC |
|---|---:|
| `label_outperform` | 0.639 |
| `label_underperform` | 0.574 |
| `label_overheated` | 0.443 |
| `label_value_creation` | 0.727 |

Interpretation:

- Outperform and value-creation labels remain useful.
- Overheated classification got worse and should not be used as a strong standalone classifier yet.
- For overheated risk, keep rule score and live shadow tracking rather than relying on the classifier.

## Current Overlay After Full QM Context

Latest S/T/I/user candidate overlay:

- `UNDERVALUED`: `1`
- `FAIR`: `39`
- `OVERHEATED`: `98`
- `AVOID`: `162`
- `OUT_OF_SCOPE_OR_MISSING`: `48`

The only current model candidate marked `UNDERVALUED`:

- `015760` 한국전력, `T-STOCK-V01`

## Recommendation

Use the full QuantMarket context as the current experimental model, but do not conclude it is strictly superior yet.

Operational interpretation:

- For top-N selection and challenger tests, full QM context is promising.
- For whole-universe rank stability, market-context-only remains slightly cleaner.
- For now, keep both result sets conceptually separated:
  - `AI-GROWTH-VALUATION-V01-QM`: full QuantMarket context experimental path
  - `AI-GROWTH-VALUATION-V01-MKT`: market-context-only reference path

Next experiments:

1. Run ablation tests by feature group: market only, market+risk, market+theme, market+theme+risk, full.
2. Test low-confidence theme mapping exclusion or down-weighting.
3. Train a top-N optimized variant instead of using only Rank IC as the main criterion.
4. Continue live shadow tracking by valuation state and market state.
