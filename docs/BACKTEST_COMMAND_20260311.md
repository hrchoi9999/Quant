## One-Run Update + Backtest Command

### Recommended one-command orchestration

```powershell
cd D:\Quant
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py
```

### ETF-enabled daily orchestration

```powershell
cd D:\Quant
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py --include-etf
```

### Two-stage orchestration with QuantMarket market context

Use this flow when Quant models should consume same-asof QuantMarket market analysis/forecast mart.

```powershell
cd D:\Quant

# 1) Quant source data only: stock/ETF universe, prices, regime/fundamental/feature prep
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --data-refresh-only

# 2) Run QuantMarket market context mart for the same asof in the QM thread
#    Required QM handoff current path:
#    D:\QuantMarket\service_platform\quant_model_handoff\market_context\current

# 3) Daily-light Quant model/AI/publish stages only; this fails fast if QM 20d primary forecast is not ready for the same asof
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --model-run-only --pipeline-mode daily_light

# Optional research/full validation run. Use this intentionally, not as the default daily path.
.\venv64\Scripts\python.exe .\src\quant_service\run_daily_quant_pipeline.py --asof YYYY-MM-DD --include-etf --model-run-only --pipeline-mode research_full
```

### Notes

- Default flow: data refresh -> S2 backtest -> S3/S3 core2/S4/S5/S6 backtests (ETF models from 2023-06-08) -> Router/profile reports (from 2023-06-08) -> T-STOCK-V01 / T-ETF-V01 shadow refresh -> I-STOCK-STRONG-RSI-V01 shadow refresh -> ingest -> publish -> web snapshots -> admin new-entry tracker -> trading_sign current snapshots -> canonical public/admin current republish
- `--data-refresh-only`: runs only Quant data/universe/feature prep and stops before strategy/AI model execution. Use this before QM market analysis mart generation.
- `--model-run-only`: skips prep and runs strategy/AI/publish stages only after checking QM handoff readiness.
- `--pipeline-mode daily_light`: default. Runs operational current score/payload generation and skips heavy E-series/AI research validation jobs.
- `--pipeline-mode research_full`: runs the full E-series/AI validation bundle, including issuer distribution crawl, total-return checks, walk-forward policy tests, mode-switch/cost/turnover/stability checks, operational hardening, policy hierarchy, and full AI overlay policy-map backtests.
- QM readiness check requires `market_forecast_ai_calibrated_daily_current.csv` to contain `forecast_horizon=20d` rows for `ALL`, `KOSPI`, and `KOSDAQ` at the requested `--asof`, and the QM manifest `production_ready=true`.
- `--allow-stale-qm-market-context`: emergency override only. It allows model execution with stale QM context and should not be used for normal daily operation.
- `--include-etf`: build ETF universe latest alias from KRX OpenAPI, upsert `instrument_master`, and load ETF prices into `price.db` from KRX OpenAPI
- `--etf-start`: deprecated no-op for daily ETF refresh. ETF daily refresh now collects only the requested `--asof` through KRX OpenAPI.
- `--asof` omitted: local today date is used automatically
- Source fallback rule: if upstream universe/price artifact generation cannot resolve the requested `--asof` directly (for example, source API failure, delayed source update, or an actual non-trading day), the stock universe builder now tries `KRX OpenAPI -> pykrx -> Naver market-cap pages -> FinanceDataReader -> cache` before falling back to the latest compatible artifacts on or before the requested date
- KRX OpenAPI key source: `D:\Quant\config\KRX_API_Key.json` is the default key file. Keep this file local/private and do not print the key in logs.
- This means `S2`/`S3` stock outputs can still be published for the requested `asof`, while some source run files may still carry the most recent compatible trading-day end token in their filenames
- Default storage: `quant_service.db` + `quant_service_detail.db`
- Default mode rebuilds service web snapshots, admin new-entry tracker payload, and republishes canonical public/admin current files to GCS so the live website/admin tools can refresh without redeploy
- Internal service analytics DB, review CSV/Markdown, and admin preview bundles are disabled by default
- Add `--include-service-analytics` only if you intentionally want to rebuild internal admin preview analytics assets
- Default mode also runs `T-STOCK-V01` and `I-STOCK-STRONG-RSI-V01` shadow refresh, and if `--include-etf` is set it also runs `T-ETF-V01` shadow refresh using existing local research outputs
- Add `--skip-tseries-shadow` if you want to skip T-series shadow refresh during a run
- Add `--skip-iseries-shadow` if you want to skip I-series shadow refresh during a run
- Default mode also runs admin new-entry tracker generation/validation and `trading_sign` current snapshot generation/validation after web snapshots, before canonical remote publish
- Add `--skip-trading-sign` if you want to skip trading_sign generation during a run
- Default mode syncs dated generated CSV outputs into [generated_outputs.db](D:/Quant/data/db/generated_outputs.db) after remote publish and before cleanup
- Add `--skip-generated-csv-db-sync` if you want to skip generated CSV DB sync during a run
- Default mode also runs conservative generated-file cleanup after DB sync, archiving old dated outputs while protecting `current`, `latest`, and `manifest` files
- Add `--skip-generated-file-cleanup` if you want to skip generated-file archive cleanup during a run
- Add `--skip-remote-current-publish` only if you intentionally want to skip canonical GCS republish of current public snapshot files
- Google Sheets sync has been disabled. `redbot.co.kr` current/remote publish is now the canonical delivery path.

### Failure runbook

- `price/regime/fundamentals` update failure: check external market data access first, then verify [price.db](D:/Quant/data/db/price.db), [regime.db](D:/Quant/data/db/regime.db), [fundamentals.db](D:/Quant/data/db/fundamentals.db) max dates
- `KRX stock universe` source failure: [build_universe_krx.py](D:/Quant/src/collectors/universe/build_universe_krx.py) should fall back from `krx_openapi` to `pykrx`, Naver market-cap pages, FinanceDataReader, then cache. Confirm logs show `used_asof=<requested>, source=krx_openapi` before accepting a fresh OpenAPI result.
- `ETF universe` failure: rerun [build_universe_etf_krx.py](D:/Quant/src/collectors/universe/build_universe_etf_krx.py) and check [universe_etf_master_latest.csv](D:/Quant/data/universe/universe_etf_master_latest.csv)
- `ETF prices` failure: rerun [fetch_krx_openapi_daily_prices.py](D:/Quant/src/collectors/price/fetch_krx_openapi_daily_prices.py) with `--markets ETF` and check ETF rows in [price.db](D:/Quant/data/db/price.db) `prices_daily`. The old pykrx/FDR ETF collector is archived at [fetch_etf_prices_daily.py](D:/Quant/archive/legacy_scripts/20260418/src/collectors/prices/fetch_etf_prices_daily.py) and must not be used in routine operations.
- `S2` backtest failure: check latest files under [backtest_regime_refactor](D:/Quant/reports/backtest_regime_refactor) and confirm [universe_mix_top400_latest_fundready.csv](D:/Quant/data/universe/universe_mix_top400_latest_fundready.csv) exists
- `S3/S3 core2` failure: check [features_s3.db](D:/Quant/data/db_s3/features_s3.db) max dates and latest files under [backtest_s3_dev](D:/Quant/reports/backtest_s3_dev)
- `ingest` failure: rerun [ingest_backtest_results.py](D:/Quant/src/quant_service/ingest_backtest_results.py) with the same `--asof`; if the requested-date artifacts are unavailable it should resolve the latest compatible artifacts on or before the requested date
- `publish` failure: rerun [publish_backtest_results.py](D:/Quant/src/quant_service/publish_backtest_results.py) with the same `--asof`
- `trading_sign` failure: rerun [run_trading_sign_from_quant_pipeline.py](D:/Quant/scripts/run_trading_sign_from_quant_pipeline.py) and then [validate_trading_sign_snapshots.py](D:/Quant/scripts/validate_trading_sign_snapshots.py) with the same `--asof`; confirm [tradingsign_manifest.json](D:/Quant/trading_sign/service_platform/web/public_data/current/tradingsign_manifest.json) exists
- DB validation: check [quant_service.db](D:/Quant/data/db/quant_service.db) `run_runs`, `run_summary`, `pub_model_current` and [quant_service_detail.db](D:/Quant/data/db/quant_service_detail.db) `run_nav_daily`, `run_holdings_history`

### ETF P0 Commands

```powershell
# ETF universe build + latest alias
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\collectors\universe\build_universe_etf_krx.py --asof 2024-01-10 --update-latest --upsert-instrument-master

# ETF price load through KRX OpenAPI
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\collectors\price\fetch_krx_openapi_daily_prices.py --start 2024-01-10 --end 2024-01-10 --markets ETF --tickers-file D:\Quant\data\universe\universe_etf_master_latest.csv --ticker-col ticker

# ETF pipeline validate
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\validate_etf_pipeline.py --universe-csv D:\Quant\data\universe\universe_etf_master_latest.csv --start 2024-01-02 --end 2024-01-10
```
## S2 Model Backtest Command

```powershell
python -m src.backtest.run_backtest_v5 `
  --s2-refactor `
  --regime-db .\data\db\regime.db `
  --regime-table regime_history `
  --price-db .\data\db\price.db `
  --price-table prices_daily `
  --fundamentals-db .\data\db\fundamentals.db `
  --fundamentals-view s2_fund_scores_monthly `
  --universe-file .\data\universe\universe_mix_top400_latest_fundready.csv `
  --ticker-col ticker `
  --horizon 3m `
  --start 2013-10-14 `
  --end 2026-03-12 `
  --rebalance W `
  --weekly-anchor-weekday 2 `
  --weekly-holiday-shift prev `
  --good-regimes 4,3 `
  --top-n 30 `
  --sma-window 140 `
  --market-gate `
  --market-scope KOSPI `
  --market-sma-window 60 `
  --market-sma-mult 1.02 `
  --fee-bps 5 `
  --slippage-bps 5 `
  --outdir .\reports\backtest_regime_refactor
```

## S3 Model Backtest Command

```powershell
python .\src\experiments\run_s3_trend_hold_top20.py `
  --asof 2026-03-12 `
  --start 2013-10-14 `
  --end 2026-03-12 `
  --top-n 20 `
  --min-holdings 10 `
  --weekly-anchor-weekday 2
```

## S3 core2 Model Backtest Command

### 1. Refresh S3 price feature data

```powershell
python .\src\features\build_s3_price_features_daily.py --end 2026-03-12
```

### 2. Run S3 core2 backtest

```powershell
python .\src\experiments\run_s3_trend_hold_top20_CORE2_TIEBREAK_GATE_SWEEP.py `
  --start 2013-10-14 `
  --end 2026-03-12 `
  --top-n 20 `
  --min-holdings 10 `
  --tag testrun_0312 `
  --gate-enabled 1 `
  --gate-open-th 0.50 `
  --gate-close-th 0.46 `
  --gate-use-slope 1 `
  --gate-use-ma-stack 1
```




### Generated File Retention

- Policy doc: [GENERATED_FILE_RETENTION_POLICY_20260406.md](D:/Quant/docs/GENERATED_FILE_RETENTION_POLICY_20260406.md)
- Cleanup script: [cleanup_generated_files.py](D:/Quant/scripts/cleanup_generated_files.py)
- Archive root: `D:\Quant\archive\generated_retention`

### Generated CSV DB Sync

- Transition doc: [GENERATED_CSV_TO_DB_TRANSITION_20260410.md](D:/Quant/docs/GENERATED_CSV_TO_DB_TRANSITION_20260410.md)
- Sync script: [sync_generated_csv_to_db.py](D:/Quant/scripts/sync_generated_csv_to_db.py)
- DB: [generated_outputs.db](D:/Quant/data/db/generated_outputs.db)
