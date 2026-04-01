# Daily Quant Batch Checklist

## Run Command

```powershell
cd D:\Quant
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py --include-etf --model-gsheet
```

## Must Check

1. Raw data update
- [price.db](D:/Quant/data/db/price.db) `prices_daily` max(date)
- [regime.db](D:/Quant/data/db/regime.db) `regime_history` max(date)
- [features_s3.db](D:/Quant/data/db_s3/features_s3.db) `s3_price_features_daily` max(date)
- ETF rows and latest date in [price.db](D:/Quant/data/db/price.db)

2. Model outputs
- S2: [backtest_regime_refactor](D:/Quant/reports/backtest_regime_refactor)
- S3/S3 core2: [backtest_s3_dev](D:/Quant/reports/backtest_s3_dev)
- S4/S5/S6: [backtest_etf_allocation](D:/Quant/reports/backtest_etf_allocation)
- Router: [backtest_router](D:/Quant/reports/backtest_router)
- Comparison: [model_compare](D:/Quant/reports/model_compare)

3. DB publish
- [quant_service.db](D:/Quant/data/db/quant_service.db) `run_runs`
- [quant_service.db](D:/Quant/data/db/quant_service.db) `pub_model_current`
- [quant_service.db](D:/Quant/data/db/quant_service.db) `pub_model_performance`
- [quant_service_detail.db](D:/Quant/data/db/quant_service_detail.db) `run_nav_daily`

4. Web service payload
- [user_model_catalog.json](D:/Quant/service_platform/web/public_data/current/user_model_catalog.json)
- [user_model_snapshot_report.json](D:/Quant/service_platform/web/public_data/current/user_model_snapshot_report.json)
- [user_performance_summary.json](D:/Quant/service_platform/web/public_data/current/user_performance_summary.json)
- [user_recent_changes.json](D:/Quant/service_platform/web/public_data/current/user_recent_changes.json)
- [publish_manifest.json](D:/Quant/service_platform/web/public_data/current/publish_manifest.json)

5. Google Sheets
- `S2_snapshot`
- `S3_snapshot`
- `S3_CORE2_snapshot`
- `S4_snapshot`
- `S5_snapshot`
- `S6_snapshot`

## Quick Sanity Rules

- `stable / balanced / growth` profiles should all publish without missing holdings.
- `auto` should resolve to one of the supported service profiles.
- ETF core aliases should be present before S4/S5/S6 publish.
- KRX universe and cache sources should be aligned before publish.
- Web snapshot validation must pass before handoff.

## Recovery Order

1. ETF core issue: [build_universe_etf_core.py](D:/Quant/src/collectors/universe/build_universe_etf_core.py)
2. ETF/stock data mismatch: rerun [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py)
3. DB publish issue: [ingest_backtest_results.py](D:/Quant/src/quant_service/ingest_backtest_results.py) -> [publish_backtest_results.py](D:/Quant/src/quant_service/publish_backtest_results.py)
4. Web payload issue: [build_user_facing_snapshots.py](D:/Quant/service_platform/publishers/build_user_facing_snapshots.py) -> [validate_redbot_web_snapshots.py](D:/Quant/scripts/validate_redbot_web_snapshots.py)
5. Sheets issue: [sync_model_holdings_gsheet.py](D:/Quant/src/quant_service/sync_model_holdings_gsheet.py), [sync_etf_model_holdings_gsheet.py](D:/Quant/src/quant_service/sync_etf_model_holdings_gsheet.py)
6. Internal analytics preview assets are disabled by default; rebuild them only when explicitly requested with `--include-service-analytics`

## Internal Admin Preview Bundles

- `service_analytics_review` preview bundles (`p1_bundle` ~ `p5_bundle`) are no longer part of the default daily pipeline.
- Public current snapshots, market briefing current, and T-series Discovery current remain part of the default pipeline.
- Only use `--include-service-analytics` when a separate internal admin preview rebuild is explicitly requested.
