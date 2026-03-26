# QuantService Analytics Autorun Handoff

## Summary

Internal admin analytics preview data is now included in the daily Quant orchestration.
This does **not** publish anything to the public web payload. It only refreshes internal preview outputs used by admin-side development.

## What Changed

- [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py) now rebuilds:
  - `service_analytics.db`
  - analytics review markdown/csv outputs
  - P1 bundle preview JSON
  - P2 bundle preview JSON
  - P3 bundle preview JSON
- New skip flag:
  - `--skip-service-analytics`

## Refreshed Internal Preview Paths

- [p1_bundle](D:/Quant/reports/service_analytics_review/20260325/p1_bundle)
- [p2_bundle](D:/Quant/reports/service_analytics_review/20260325/p2_bundle)
- [p3_bundle](D:/Quant/reports/service_analytics_review/20260325/p3_bundle)

## Operational Meaning For QuantService

- QuantService admin pages no longer need a separate manual request just to refresh preview JSON after a standard daily Quant batch.
- These files are still preview-only.
- Do not connect them to public routes until explicit approval.

## Safety Rules

- Treat all analytics bundle JSON as internal admin preview.
- Do not merge into current public snapshot/API.
- Respect `meta.internal_preview_only=true` and `meta.web_publish_enabled=false`.
