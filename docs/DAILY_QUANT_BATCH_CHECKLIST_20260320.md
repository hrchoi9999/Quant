# Daily Quant Batch Checklist

## Run Command

```powershell
cd D:\Quant
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py --include-etf
```

For a full regime rebuild after a price DB rebase, universe rule change, or model research reset:

```powershell
cd D:\Quant
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py --include-etf --full-regime-rebuild
```

## Operating Rule

- Do not publish public current from an evening batch if ETF same-day coverage is incomplete.
- The canonical public/admin/trading-sign publish must be based on the latest date where both stock and ETF inputs are complete.
- Use a two-step operating policy:
  - `evening provisional internal check`
    - Purpose: internal-only sanity check after market close.
    - Allowed interpretation scope: mainly stock-driven internal models such as `S2`, `S3`, `S3_CORE2`, `T-STOCK-V01`.
    - Do not treat this as final user-facing output.
    - Do not overwrite remote current used by `redbot.co.kr`.
  - `next-morning final operational batch`
    - Purpose: final run after verifying stock + ETF completeness for the previous trading date.
    - Required scope: `S2`, `S3`, `S3_CORE2`, `S4`, `S5`, `S6`, `T-STOCK-V01`, `T-ETF-V01`, user models, and `trading_sign`.
    - Only this final batch may republish canonical current to GCS and update the website.
- Reference policy: [BATCH_OPERATION_POLICY_20260423.md](D:/Quant/docs/BATCH_OPERATION_POLICY_20260423.md)

## Must Check

1. Raw data update
- [price.db](D:/Quant/data/db/price.db) `prices_daily` max(date)
- [regime.db](D:/Quant/data/db/regime.db) `regime_history` max(date)
- [features_s3.db](D:/Quant/data/db_s3/features_s3.db) `s3_price_features_daily` max(date)
- ETF rows and latest date in [price.db](D:/Quant/data/db/price.db)
- Confirm [build_universe_krx.py](D:/Quant/src/collectors/universe/build_universe_krx.py) uses `krx_openapi` first. If KRX OpenAPI fails or returns no rows, it should fall back to `pykrx`, then Naver, then FinanceDataReader, then cache.
- Confirm ETF universe generation logs `source=krx_openapi_etf_daily`; routine ETF universe and ETF price collection should not call pykrx.
- Confirm the local KRX OpenAPI key file exists at `D:\Quant\config\KRX_API_Key.json`; never print the key in logs.
- For data-quality audit, use [audit_krx_price_integrity.py](D:/Quant/scripts/audit_krx_price_integrity.py). Daily runs should audit the latest trading day; historical validation should proceed in 3-month blocks per [KRX_OPENAPI_DATA_QUALITY_AND_FEATURE_PLAN_20260417.md](D:/Quant/docs/KRX_OPENAPI_DATA_QUALITY_AND_FEATURE_PLAN_20260417.md).

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
- [admin_new_entry_tracker.json](D:/Quant/service_platform/web/admin_data/current/admin_new_entry_tracker.json)
- [tradingsign_manifest.json](D:/Quant/trading_sign/service_platform/web/public_data/current/tradingsign_manifest.json)
- [tradingsign_overview.json](D:/Quant/trading_sign/service_platform/web/public_data/current/tradingsign_overview.json)
- [tradingsign_model_detail.json](D:/Quant/trading_sign/service_platform/web/public_data/current/tradingsign_model_detail.json)

5. Pre-publish contract gate
- Run [validate_daily_pipeline_contract.py](D:/Quant/scripts/validate_daily_pipeline_contract.py) before canonical GCS publish.
- Required pass condition:
  - market data DB freshness matches the operating `asof`
  - `price.db` has no duplicate `(ticker,date)` rows for `asof`
  - stock/ETF universe price coverage is complete enough for model operation
  - `quant_service.db` has completed and current-published rows for `S2`, `S3`, `S3_CORE2`, `S4`, `S5`, `S6`
  - T-series DB has one current threshold profile per model/profile
  - public/admin/trading_sign current payload dates match `asof`
- The daily pipeline now runs this contract gate automatically after web/admin/trading_sign validation and before remote current publish.
- If `etf_universe_price_coverage` fails for same-day `asof`, treat the batch as provisional/internal and keep the canonical public publish on the last complete common date.

6. Operational efficiency mode
- Daily stock regime refresh defaults to an operational recent-window update (`--regime-years 2`) instead of a 10-year rebuild.
- Use `--full-regime-rebuild` only for DB rebase, universe methodology changes, or model research resets.
- T-ETF PIT universe refresh reuses cached historical monthly PIT rows and recalculates only the current month by default.
- Use [run_t_etf_v01_operational_refresh.py](D:/Quant/scripts/run_t_etf_v01_operational_refresh.py) with `--full-rebuild` only when ETF classification rules, liquidity rules, or PIT universe methodology changed.
- Independent model backtests run with bounded parallel workers by default (`--model-workers 4`).
- Daily admin new-entry validation uses recent-event quick mode by default; use `--full-validation` for weekly/monthly full coverage checks.

7. Remote current / website handoff
- canonical GCS current publish completed
- `redbot.co.kr` live API returns latest `as_of_date`

## Quick Sanity Rules

- `stable / balanced / growth` profiles should all publish without missing holdings.
- ETF core aliases should be present before S4/S5/S6 publish.
- KRX universe and cache sources should be aligned before publish.
- Stock universe fallback order is `KRX OpenAPI -> pykrx -> Naver -> FinanceDataReader -> cache`; cache should be last, not the first non-OpenAPI fallback.
- ETF universe and ETF price collection are KRX OpenAPI-only in the default pipeline. The archived pykrx/FDR ETF collector is retained only under [legacy_scripts](D:/Quant/archive/legacy_scripts/20260418) for emergency comparison or historical reproduction.
- Web snapshot validation must pass before handoff.
- Admin new-entry tracker validation must pass before admin handoff.
- trading_sign snapshot validation must pass before canonical current republish.
- Daily pipeline contract validation must pass before canonical current republish.
- Evening provisional runs are allowed for internal review, but they must not replace canonical public current unless stock and ETF completeness both pass.

## Recovery Order

1. ETF core issue: [build_universe_etf_core.py](D:/Quant/src/collectors/universe/build_universe_etf_core.py)
2. ETF/stock data mismatch: rerun [run_daily_quant_pipeline.py](D:/Quant/src/quant_service/run_daily_quant_pipeline.py)
3. DB publish issue: [ingest_backtest_results.py](D:/Quant/src/quant_service/ingest_backtest_results.py) -> [publish_backtest_results.py](D:/Quant/src/quant_service/publish_backtest_results.py)
4. Web payload issue: [build_user_facing_snapshots.py](D:/Quant/service_platform/publishers/build_user_facing_snapshots.py) -> [validate_redbot_web_snapshots.py](D:/Quant/scripts/validate_redbot_web_snapshots.py)
5. trading_sign issue: [run_trading_sign_from_quant_pipeline.py](D:/Quant/scripts/run_trading_sign_from_quant_pipeline.py) -> [validate_trading_sign_snapshots.py](D:/Quant/scripts/validate_trading_sign_snapshots.py)
6. Pipeline contract issue: inspect [daily_pipeline_contract_<asof>.json](D:/Quant/reports/data_quality/pipeline_contract) and fix the failing upstream stage before publish.
7. Google Sheets sync is disabled. Do not use legacy gsheet sync scripts.
8. Internal analytics preview assets are disabled by default; rebuild them only when explicitly requested with `--include-service-analytics`

## Internal Admin Preview Bundles

- `service_analytics_review` preview bundles (`p1_bundle` ~ `p5_bundle`) are no longer part of the default daily pipeline.
- Public current snapshots, market briefing current, and T-series Discovery current remain part of the default pipeline.
- Only use `--include-service-analytics` when a separate internal admin preview rebuild is explicitly requested.
