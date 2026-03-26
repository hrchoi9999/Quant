# Daily Quant Batch Checklist

## Run Command

```powershell
cd D:\Quant
.env64\Scripts\python.exe .\src\quant_service
un_daily_quant_pipeline.py --include-etf --model-gsheet
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

- `stable / balanced / growth` ???? ??? ???? ?? ??? ??.
- `auto`? ?? ??? ???? `balanced`? ?? ? ??.
- ETF core? ??? S4/S5/S6? ???? ???.
- KRX universe? cache source? ??? ?? ???, ?? DB ????? ?? ???? ???? ??.
- ? snapshot validate? ??? ???? ??.

## Recovery Order

1. ETF core ??: [build_universe_etf_core.py](D:/Quant/src/collectors/universe/build_universe_etf_core.py)
2. ETF/stock data mismatch: [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py) ???
3. DB ?? ??: [ingest_backtest_results.py](D:/Quant/src/quant_service/ingest_backtest_results.py) -> [publish_backtest_results.py](D:/Quant/src/quant_service/publish_backtest_results.py)
4. Web payload ??: [build_user_facing_snapshots.py](D:/Quant/service_platform/publishers/build_user_facing_snapshots.py) -> [validate_redbot_web_snapshots.py](D:/Quant/scripts/validate_redbot_web_snapshots.py)
5. Sheets ??: [sync_model_holdings_gsheet.py](D:/Quant/src/quant_service/sync_model_holdings_gsheet.py), [sync_etf_model_holdings_gsheet.py](D:/Quant/src/quant_service/sync_etf_model_holdings_gsheet.py)
6. Internal analytics ??: [build_service_analytics.py](D:/Quant/scripts/build_service_analytics.py) -> [validate_service_analytics.py](D:/Quant/scripts/validate_service_analytics.py) -> P1/P2/P3 bundle rebuild


6. Internal admin analytics preview
- [service_analytics.db](D:/Quant/data/db/service_analytics.db) latest build
- [p1_bundle](D:/Quant/reports/service_analytics_review/20260325/p1_bundle) refreshed
- [p2_bundle](D:/Quant/reports/service_analytics_review/20260325/p2_bundle) refreshed
- [p3_bundle](D:/Quant/reports/service_analytics_review/20260325/p3_bundle) refreshed
- internal preview only: do not publish to public web until approved

