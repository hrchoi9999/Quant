# QuantService Analytics P1 Improvements Handoff

## Summary

Quant service analytics preview data was improved in three areas:

1. `change_log` names are now backfilled more reliably for exit rows and historical rows.
2. `date_context` metadata was added to P1/P2/P3 preview payloads.
3. `S3 / S3_CORE2` asset-mix handling remains normalized in preview outputs and now sits on top of refreshed analytics data.

## What Changed In Payloads

### P1
- [today_model_info_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/today_model_info_20260325.json)
- [model_changes_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_changes_20260325.json)
- [model_compare_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p1_bundle/model_compare_20260325.json)

Added field:
- `date_context`

### P2
- [portfolio_structure_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/portfolio_structure_20260325.json)
- [holding_lifecycle_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p2_bundle/holding_lifecycle_20260325.json)

Added field:
- `date_context`

### P3
- [model_quality_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/model_quality_20260325.json)
- [weekly_briefing_20260325.json](D:/Quant/reports/service_analytics_review/20260325/p3_bundle/weekly_briefing_20260325.json)

Added field:
- `date_context`

## date_context Meaning

- `asof_date`: Quant batch 기준일
- `signal_date`: 모델 산출 기준일
- `snapshot_date`: 실제 holdings snapshot 날짜 (P1 only)
- `effective_date`: 현재 admin preview 해석 기준일
- `week_end`: 주간 버킷 종료일
- `asset_mix_week_end` or `quality_week_end`: 해당 페이지용 주간 기준일

## Operational Guidance For QS

- Existing rendering can continue without using `date_context`.
- If QS wants clearer labels on admin pages, it can optionally expose:
  - `signal_date`
  - `effective_date`
  - `week_end`
- `model_changes.items[].name` null cases should now be greatly reduced.

## Safety

- Still internal preview only.
- Do not connect these payloads to public web until approved.
