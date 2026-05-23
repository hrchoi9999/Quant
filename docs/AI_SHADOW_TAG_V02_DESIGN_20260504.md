# AI Shadow Tag V02 Design - 2026-05-04

## Purpose

Replace the single AI shadow tag with multiple interpretable shadow tags.

This is still shadow-only and must not be treated as a live trading rule.

## New Probabilities

Each row is still:

- `model + ticker + event_date`

New probability columns:

- `ai_short_confirm_prob`
  - label: `label_positive_1m`
  - meaning: short-term 1M positive-return confirmation
- `ai_medium_quality_prob`
  - label: `label_quality_2m`
  - meaning: medium-term 2M quality candidate
- `ai_long_quality_prob`
  - label: `label_quality_3m`
  - meaning: longer 3M quality candidate
- `ai_upside_strict_prob`
  - label: `label_quality_1m_strict`
  - meaning: high-conviction upside candidate
- `ai_risk_strict_prob`
  - label: `label_bad_1m_strict`
  - meaning: strict risk/avoid candidate

## New Tags

`ai_shadow_tags` can contain multiple comma-separated tags:

- `SHORT_CONFIRM`
- `MEDIUM_QUALITY`
- `LONG_QUALITY`
- `UPSIDE_STRICT`
- `RISK_AVOID`
- `OBSERVE`

Default threshold:

- probability `>= 0.60`

## Decision Layer

`ai_shadow_decision` is a compact decision-style summary:

- `AI_HIGH_CONVICTION`
  - `UPSIDE_STRICT` and `MEDIUM_QUALITY`
- `AI_CONFIRM`
  - `SHORT_CONFIRM`
- `AI_RISK_REVIEW`
  - `RISK_AVOID`
- `AI_OBSERVE`
  - no strong tag

## Output

Main shadow file:

- `D:\Quant\reports\ai_overlay_v01\ai_overlay_shadow_scores_20260504.csv`

DB table:

- `D:\Quant\data\db\ai_learning.db::ai_shadow_scores`

## Current Distribution

Rows:

- `2,736`

Decision counts:

| scope | decision | count |
|---|---|---:|
| internal | `AI_CONFIRM` | 183 |
| internal | `AI_HIGH_CONVICTION` | 4 |
| internal | `AI_OBSERVE` | 2,251 |
| internal | `AI_RISK_REVIEW` | 28 |
| tseries | `AI_CONFIRM` | 55 |
| tseries | `AI_HIGH_CONVICTION` | 9 |
| tseries | `AI_OBSERVE` | 96 |
| tseries | `AI_RISK_REVIEW` | 3 |
| user | `AI_CONFIRM` | 14 |
| user | `AI_OBSERVE` | 86 |
| user | `AI_RISK_REVIEW` | 7 |

Top tag combinations:

| tags | count |
|---|---:|
| `OBSERVE` | 2,373 |
| `SHORT_CONFIRM` | 186 |
| `RISK_AVOID` | 37 |
| `SHORT_CONFIRM,MEDIUM_QUALITY` | 26 |
| `MEDIUM_QUALITY` | 24 |
| `SHORT_CONFIRM,MEDIUM_QUALITY,LONG_QUALITY` | 20 |
| `LONG_QUALITY` | 18 |
| `MEDIUM_QUALITY,LONG_QUALITY` | 14 |
| `SHORT_CONFIRM,LONG_QUALITY` | 11 |
| `UPSIDE_STRICT,SHORT_CONFIRM,MEDIUM_QUALITY,LONG_QUALITY` | 8 |

## Interpretation

This design separates three different questions:

1. Is the candidate likely to work in the short term?
2. Is the candidate a medium/long quality candidate?
3. Is the candidate risky enough to review or avoid?

Recommended use:

- Do not replace S/T/I model selection yet.
- Display or analyze as a shadow overlay.
- Track forward performance by each AI tag from this point onward.

## Next Step

Add an AI shadow performance tracker:

- by `ai_shadow_tags`
- by `ai_shadow_decision`
- by scope/model
- horizons: `1W`, `2W`, `1M`, `2M`, `3M`
