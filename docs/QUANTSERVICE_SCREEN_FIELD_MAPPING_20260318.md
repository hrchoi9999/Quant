# QuantService Screen Field Mapping

## Purpose
This document maps Quant user-facing snapshot fields to QuantService screens and components.
Use this together with `QUANT_TO_QUANTSERVICE_API_SPEC_20260318.md`.

## Snapshot Sources
- `user_model_catalog.json`
- `user_model_snapshot_report.json`
- `user_performance_summary.json`
- `user_recent_changes.json`
- `publish_manifest.json`

## 1. Home Screen
### Data source
- `/api/v1/user-models`
- optional: `/api/v1/performance/summary`
- optional: `/api/v1/publish-status`

### Component mapping
#### Hero section
- title: static copy
- subtitle: static copy from product positioning
- freshness badge: `publish_manifest.generated_at`
- asof badge: `publish_manifest.as_of_date`

#### User model cards
Repeat over `user_model_catalog.models[]`
- card id: `user_model_id`
- card title: `user_model_name`
- service profile badge: `service_profile`
- summary text: `summary`
- risk badge: `risk_label`
- reference usage text: `reference_usage_context`
- asset mix chips: `primary_asset_mix[]`
- active flag: `is_active`
- detail link param: `service_profile`

#### Headline performance strip
Join by `service_profile` using `user_performance_summary.models[]`
- card title: `user_model_name`
- CAGR: `performance_cards.cagr`
- MDD: `performance_cards.mdd`
- Sharpe: `performance_cards.sharpe`

## 2. Today Screen
### Data source
- `/api/v1/model-snapshots/today`
- optional: `/api/v1/publish-status`

### Page-level fields
- asof date: `as_of_date`
- generated at: `generated_at`
- market regime badge: `current_market_regime`

### Model snapshot sections
Repeat over `reports[]`
- section title: `user_model_name`
- profile badge: `service_profile`
- summary text: `summary_text`
- market view text: `market_view`
- risk label: `risk_level`
- disclaimer footer: `disclaimer_text`

#### Allocation block
Repeat over `allocation_items[]`
- asset group: `asset_group`
- security code: `security_code`
- display name: `display_name`
- weight: `target_weight`
- role text: `role_summary`
- source type: `source_type`

#### Model rationale
Repeat over `rationale_items[]`
- bullet text: each item

#### Performance summary block
- full CAGR: `performance_summary.headline_metrics.full_cagr`
- full MDD: `performance_summary.headline_metrics.full_mdd`
- full Sharpe: `performance_summary.headline_metrics.full_sharpe`
- detail table: `performance_summary.period_metrics[]`

#### Change block
Repeat over `change_log.increased_assets[]` and `change_log.decreased_assets[]`
- display name: `display_name`
- security code: `security_code`
- delta weight: `delta_weight`
- direction: `direction`
- reason text: `change_log.change_reason`

## 3. Performance Screen
### Data source
- `/api/v1/performance/summary`
- optional: `/api/v1/user-models`

### Comparison cards
Repeat over `models[]`
- title: `user_model_name`
- profile: `service_profile`
- risk label: `risk_label`
- CAGR: `performance_cards.cagr`
- MDD: `performance_cards.mdd`
- Sharpe: `performance_cards.sharpe`
- note: `note`

### Period comparison table
Repeat over `models[]`, then `period_table[]`
- row model: `user_model_name`
- row risk: `risk_label`
- period: `period`
- CAGR: `cagr`
- MDD: `mdd`
- Sharpe: `sharpe`

## 4. Changes Screen
### Data source
- `/api/v1/changes/recent`
- optional: `/api/v1/publish-status`

### Change cards
Repeat over `changes[]`
- title: `user_model_name`
- change type badge: `change_type`
- summary text: `summary`
- reason text: `reason_text`

#### Increase list
Repeat over `increase_items[]`
- display name: `display_name`
- security code: `security_code`
- delta weight: `delta_weight`

#### Decrease list
Repeat over `decrease_items[]`
- display name: `display_name`
- security code: `security_code`
- delta weight: `delta_weight`

## 5. Model Detail Screen
### Data source
- `/api/v1/model-snapshots/{service_profile}`
- optional: `/api/v1/performance/summary`

### Mapping
Use the same field structure as a single element of `reports[]` from `user_model_snapshot_report.json`.
Include `allocation_items[].security_code` beside each ??? when present.

## UI Formatting Rules
- Format decimal performance metrics as percentages in UI.
  - example: `0.3318 -> 33.18%`
- Keep raw decimal in data layer.
- Show friendly labels for `risk_label`.
- Do not show internal model names on default user pages.

## Empty And Error States
- If `reports[]` is empty, show stale-data or unavailable message.
- If `publish_manifest.as_of_date` is old, show stale badge.
- Do not derive missing sections from raw Quant files in QuantService.

## Compliance Naming Note

QuantService should treat the following as canonical user-facing keys and labels.

- file: `user_model_snapshot_report.json`
- keys:
  - `model_overview`
  - `model_portfolio`
  - `model_rationale`
  - `model_changes`
  - `current_model_label`
  - `summary_basis`
  - `reference_response`
- do not introduce `추천`, `개인 맞춤`, `매수 추천`, `매도 추천` wording on user screens

