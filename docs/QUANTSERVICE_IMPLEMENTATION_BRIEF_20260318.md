# QuantService Implementation Brief

## Goal
Build QuantService screens using Quant-generated user-facing payloads without recalculating model logic.

## Scope
This brief is for QuantService developers.
Use Quant snapshots as mock API first, then replace with real HTTP API later.

## Available Inputs
### Snapshot files
- `D:\Quant\service_platform\web\public_data\current\user_model_catalog.json`
- `D:\Quant\service_platform\web\public_data\current\user_recommendation_report.json`
- `D:\Quant\service_platform\web\public_data\current\user_performance_summary.json`
- `D:\Quant\service_platform\web\public_data\current\user_recent_changes.json`
- `D:\Quant\service_platform\web\public_data\current\publish_manifest.json`

### Contract docs
- `D:\Quant\docs\QUANT_TO_QUANTSERVICE_API_SPEC_20260318.md`
- `D:\Quant\docs\QUANTSERVICE_SCREEN_FIELD_MAPPING_20260318.md`
- `D:\Quant\docs\REDBOT_WEB_COPY_GUIDE.md`
- `D:\Quant\docs\REDBOT_SCREEN_STRUCTURE.md`

## What To Build In QuantService
### 1. Home screen
- 4 user model cards
- short summary and risk badge
- headline performance strip
- CTA to today/performance/changes

### 2. Today screen
- recommendation report layout
- market diagnosis
- recommended allocation
- rationale bullets
- performance summary
- recent changes
- disclaimer

### 3. Performance screen
- compare 4 user models only
- use user-facing names only
- show CAGR/MDD/Sharpe and period table

### 4. Changes screen
- show change summary by user model
- emphasize increase/decrease items
- explain why allocation changed

## What Not To Build In QuantService
- no backtest logic
- no router logic
- no recomputation of performance metrics
- no direct join to Quant raw DBs for user pages
- no direct exposure of `S2/S3/S4/S5/S6/Router`

## Integration Strategy
### Phase 1
- Read local snapshot JSON as mock API
- Build UI and typed client interfaces around those payloads

### Phase 2
- Replace local snapshot reader with HTTP API client
- Keep response shapes unchanged as much as possible

## Suggested Frontend Types
### UserModelCard
- `user_model_id: string`
- `user_model_name: string`
- `service_profile: string`
- `summary: string`
- `risk_label: string`
- `target_user_type: string`
- `primary_asset_mix: string[]`
- `is_active: boolean`

### RecommendationReport
- `user_model_name: string`
- `service_profile: string`
- `summary_text: string`
- `market_view: string`
- `allocation_items: AllocationItem[]`
- `rationale_items: string[]`
- `risk_level: string`
- `performance_summary: PerformanceSummary`
- `change_log: ChangeLog`
- `disclaimer_text: string`

### AllocationItem
- `security_code: string | null`
  - 6-digit string for stock/ETF rows
  - `null` only for cash-like residual rows
- `asset_group: string`
- `display_name: string`
- `target_weight: number`
- `role_summary: string`
- `source_type: string`

### ChangeItem
- `display_name: string`
- `security_code: string | null`
- `delta_weight: number`
- `direction: "increase" | "decrease"`

## Developer Checklist
- load UTF-8 payload safely
- create typed model layer from snapshot structure
- implement stale-data badge using `publish_manifest`
- support graceful empty/error states
- hide internal model names by default
- format numeric metrics in UI only

## Recommended Task Order
1. Create local API adapter using snapshot files
2. Implement Home screen
3. Implement Today screen
4. Implement Performance screen
5. Implement Changes screen
6. Add stale-data and loading states
7. Replace snapshot adapter with HTTP API later

## Notes
- Current terminal preview may show Korean text garbled because of console encoding.
- Treat stored files as UTF-8 source of truth.
- If payload text quality needs correction, request Quant-side payload cleanup rather than patching copy ad hoc in UI.
