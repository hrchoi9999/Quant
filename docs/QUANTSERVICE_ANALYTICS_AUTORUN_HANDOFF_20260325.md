# QuantService Analytics Autorun Handoff

## Status

Internal admin analytics preview data is no longer included in the default daily Quant orchestration.
This preview bundle production is suspended unless there is an explicit one-off rebuild request.

## What Changed

- [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py) no longer rebuilds internal analytics preview assets by default.
- The pipeline now requires an explicit opt-in flag:
  - `--include-service-analytics`
- The old compatibility flag remains available, but preview generation is already skipped by default:
  - `--skip-service-analytics`

## Suspended Internal Preview Paths

The following preview outputs are no longer part of the default daily batch:
- [p1_bundle](D:/Quant/reports/service_analytics_review/20260325/p1_bundle)
- [p2_bundle](D:/Quant/reports/service_analytics_review/20260325/p2_bundle)
- [p3_bundle](D:/Quant/reports/service_analytics_review/20260325/p3_bundle)
- [p4_bundle](D:/Quant/reports/service_analytics_review/20260325/p4_bundle)
- [p5_bundle](D:/Quant/reports/service_analytics_review/20260325/p5_bundle)

## Operational Meaning For QuantService

- QuantService public pages and APIs are unaffected.
- Public current snapshots, market briefing current, and T-series Discovery current remain in the standard pipeline.
- Admin preview data should only be rebuilt when a separate internal request explicitly asks for it.

## Safety Rules

- Treat all analytics bundle JSON as internal admin preview only.
- Do not merge admin preview assets into current public snapshot or API payloads.
- Respect `meta.internal_preview_only=true` and `meta.web_publish_enabled=false`.
