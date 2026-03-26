# Quant To QuantService API Spec

## Purpose
This document defines the recommended service contract between `Quant` and `QuantService`.
It is intended to be used directly during QuantService backend/frontend development.

## Direction
- `Quant` is the single source of truth for model outputs and service-ready payloads.
- `QuantService` should consume service-facing payloads only.
- `QuantService` should not recalculate model logic, performance, or router decisions.
- Preferred flow:
  - `Quant raw DBs -> Quant model pipeline -> quant_service.db/pub_* -> user-facing snapshots/API -> QuantService UI`

## Source Of Truth
### Internal source
- `D:\Quant\data\db\quant_service.db`
- `D:\Quant\data\db\quant_service_detail.db`

### User-facing snapshot source
- `D:\Quant\service_platform\web\public_data\current\user_model_catalog.json`
- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`
- `D:\Quant\service_platform\web\public_data\current\user_performance_summary.json`
- `D:\Quant\service_platform\web\public_data\current\user_recent_changes.json`
- `D:\Quant\service_platform\web\public_data\current\publish_manifest.json`

## Recommended API Endpoints
### 1. GET /api/v1/user-models
Purpose:
- home page model cards
- model selector

Primary source:
- `user_model_catalog.json`

Response shape:
```json
{
  "as_of_date": "2026-03-18",
  "models": [
    {
      "user_model_id": "user_1",
      "user_model_name": "???",
      "service_profile": "stable",
      "summary": "...",
      "risk_label": "low",
      "reference_usage_context": "...",
      "compliance_metadata": {"is_personalized_advice": false},
      "primary_asset_mix": ["bond", "fx_usd", "commodity_gold"],
      "is_active": true
    }
  ]
}
```

### 2. GET /api/v1/model-snapshots/today
Purpose:
- today page main payload
- model snapshot header and report sections

Primary source:
- `user_model_snapshot_report.json`

Response shape:
```json
{
  "as_of_date": "2026-03-18",
  "generated_at": "2026-03-18T21:42:03",
  "current_market_regime": "neutral",
  "reports": [
    {
      "user_model_name": "???",
      "service_profile": "balanced",
      "summary_text": "...",
      "market_view": "?? ??",
      "allocation_items": [
        {
          "security_code": "005930",
          "asset_group": "stock",
          "display_name": "????",
          "target_weight": 0.12,
          "role_summary": "?? ??/?? ??",
          "source_type": "stock"
        }
      ],
      "rationale_items": [],
      "risk_level": "??",
      "performance_summary": {},
      "change_log": {
        "increased_assets": [
          {
            "display_name": "KODEX 200",
            "security_code": "069500",
            "delta_weight": 0.025,
            "direction": "increase"
          }
        ],
        "decreased_assets": [],
        "change_basis": "공개 규칙 기반 산출 결과에 따라 구성이 갱신되었습니다."
      },
      "disclaimer_text": "..."
    }
  ]
}
```

### 3. GET /api/v1/model-snapshots/{service_profile}
Purpose:
- single user model detailed page
- direct entry from model card

Allowed values:
- `stable`
- `balanced`
- `growth`
- `auto`

Primary source:
- `user_model_snapshot_report.json`

Key naming note:
- use `model_overview`, `model_portfolio`, `model_rationale`, `model_changes` as canonical keys
- treat legacy recommendation-style keys as deprecated

Behavior:
- Filter one report object from `reports[]`

Allocation item contract:
- `security_code`: 6-digit string for stocks/ETFs, nullable only for cash-like residual rows
- QuantService should render `display_name (security_code)` when `security_code` is present

### 4. GET /api/v1/performance/summary
Purpose:
- performance comparison page
- model comparison cards/table

Primary source:
- `user_performance_summary.json`

Response shape:
```json
{
  "as_of_date": "2026-03-18",
  "models": [
    {
      "user_model_name": "???",
      "service_profile": "growth",
      "risk_label": "high",
      "performance_cards": {
        "cagr": 0.3545,
        "mdd": -0.1438,
        "sharpe": 1.7998
      },
      "period_table": [],
      "note": "..."
    }
  ]
}
```

### 5. GET /api/v1/changes/recent
Purpose:
- changes page
- recent model snapshot and allocation changes

Primary source:
- `user_recent_changes.json`

Response shape:
```json
{
  "as_of_date": "2026-03-18",
  "changes": [
    {
      "user_model_name": "?????",
      "change_type": "rebalanced",
      "summary": "...",
      "increase_items": [],
      "decrease_items": [],
      "reason_text": "..."
    }
  ]
}
```

### 6. GET /api/v1/publish-status
Purpose:
- stale data warning
- footer/meta display
- operational badge in admin view

Primary source:
- `publish_manifest.json`

Response shape:
```json
{
  "as_of_date": "2026-03-18",
  "generated_at": "2026-03-18T21:42:03",
  "files": [
    "user_model_catalog.json",
    "user_model_snapshot_report.json"
  ],
  "channel": "user-facing",
  "version": "v1"
}
```

## Screen To Endpoint Mapping
| Screen | Required endpoint | Optional endpoint | Notes |
|---|---|---|---|
| `home` | `/api/v1/user-models` | `/api/v1/performance/summary`, `/api/v1/publish-status` | 4 model cards + headline performance |
| `today` | `/api/v1/model-snapshots/today` | `/api/v1/publish-status` | main public model snapshot report |
| `performance` | `/api/v1/performance/summary` | `/api/v1/user-models` | compare 4 user models only |
| `changes` | `/api/v1/changes/recent` | `/api/v1/publish-status` | user-facing change summaries |
| model detail | `/api/v1/model-snapshots/{service_profile}` | `/api/v1/performance/summary` | per-model public snapshot detail |

## Field Rules
### Encoding
- JSON files and API responses must be UTF-8.
- QuantService should assume UTF-8 and avoid cp949 fallback unless explicitly needed.

### Naming
- User-facing endpoints must expose user model names.
- Internal model ids must not appear on default user screens.

### Nullability
- Missing optional values should be `null`, not omitted, once API is finalized.
- In current snapshot phase, some optional fields may be absent; QuantService should handle this defensively.

### Numbers
- Performance metrics are decimals, not percent strings.
- UI should format them for display.
  - Example: `0.3545 -> 35.45%`

## Fallback Rules
### Preferred order
1. user-facing snapshots
2. `pub_*` tables in `quant_service.db`
3. no fallback to raw model outputs on user pages

### If snapshot is missing
- show stale-data message
- use last successful `publish_manifest.json` if available
- do not reconstruct from raw `S2/S3/S4/S5/S6` files inside QuantService

## Ownership Boundary
### Quant owns
- model logic
- backtest logic
- publish logic
- user-facing payload generation
- performance calculation
- model snapshot change logic
- copy source fields

### QuantService owns
- API client or API gateway integration
- view rendering
- entitlement-based depth control
- loading/empty/error states
- layout, interaction, and design system decisions

## What QuantService Must Not Do
- recalculate CAGR/MDD/Sharpe
- infer internal model routing
- join raw DB tables directly for user pages
- derive model snapshot changes from holdings on the frontend
- expose `S2/S3/S4/S5/S6/Router` by default

## Current Status
### Already prepared in Quant
- `quant_service.db` publish layer
- Redbot user report schema and renderer
- user-facing web snapshots
- minimal `service_platform` scaffold

### Not yet finalized
- HTTP API server implementation
- entitlement-specific response trimming
- admin/debug dual-mode API
- stale-data policy refinement

## Recommended Next Order
1. Freeze snapshot field names
2. Fix UTF-8 output quality end-to-end
3. Confirm QuantService screen requirements
4. Implement real HTTP API adapter
5. Connect QuantService UI to API

## Notes For QuantService Team
- Treat current snapshot files as the first stable mock API.
- Start UI binding against these payloads first.
- When HTTP API is introduced later, keep the response shape identical as much as possible.
