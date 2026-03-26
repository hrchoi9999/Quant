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

### Notes

- Default flow: data refresh -> S2 backtest -> S3/S3 core2/S4/S5/S6 backtests (ETF models from 2023-06-08) -> Router/profile reports (from 2023-06-08) -> ingest -> publish -> web snapshots -> internal service analytics/review bundles
- `--include-etf`: build ETF universe latest alias, upsert `instrument_master`, and incrementally load ETF prices into `price.db`
- `--etf-start`: first-load fallback start date for ETFs. Default is `2013-10-14`
- `--asof` omitted: local today date is used automatically
- Default storage: `quant_service.db` + `quant_service_detail.db`
- Default mode rebuilds service web snapshots, but does not upload to Google Sheets
- Default mode also rebuilds internal service analytics DB, review CSV/Markdown, and P1/P2/P3 admin preview bundles
- Add `--skip-service-analytics` if you want to skip internal analytics generation during a run
- Add `--model-gsheet` to upload S2/S3/S3 core2 published holdings and S4/S5/S6 ETF model snapshots to Google Sheets
- Add `--s2-gsheet` if you also want the original S2 backtest bundle uploaded during the S2 run

### Failure runbook

- `price/regime/fundamentals` update failure: check external market data access first, then verify [price.db](D:/Quant/data/db/price.db), [regime.db](D:/Quant/data/db/regime.db), [fundamentals.db](D:/Quant/data/db/fundamentals.db) max dates
- `ETF universe` failure: rerun [build_universe_etf_krx.py](D:/Quant/src/collectors/universe/build_universe_etf_krx.py) and check [universe_etf_master_latest.csv](D:/Quant/data/universe/universe_etf_master_latest.csv)
- `ETF prices` failure: rerun [fetch_etf_prices_daily.py](D:/Quant/src/collectors/prices/fetch_etf_prices_daily.py) and check ETF rows in [price.db](D:/Quant/data/db/price.db) `prices_daily`
- `S2` backtest failure: check latest files under [backtest_regime_refactor](D:/Quant/reports/backtest_regime_refactor) and confirm [universe_mix_top400_latest_fundready.csv](D:/Quant/data/universe/universe_mix_top400_latest_fundready.csv) exists
- `S3/S3 core2` failure: check [features_s3.db](D:/Quant/data/db_s3/features_s3.db) max dates and latest files under [backtest_s3_dev](D:/Quant/reports/backtest_s3_dev)
- `ingest` failure: rerun [ingest_backtest_results.py](D:/Quant/src/quant_service/ingest_backtest_results.py) with the same `--asof`
- `publish` failure: rerun [publish_backtest_results.py](D:/Quant/src/quant_service/publish_backtest_results.py) with the same `--asof`
- DB validation: check [quant_service.db](D:/Quant/data/db/quant_service.db) `run_runs`, `run_summary`, `pub_model_current` and [quant_service_detail.db](D:/Quant/data/db/quant_service_detail.db) `run_nav_daily`, `run_holdings_history`

### ETF P0 Commands

```powershell
# ETF universe build + latest alias
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\collectors\universe\build_universe_etf_krx.py --asof 2024-01-10 --update-latest --upsert-instrument-master

# ETF price load
D:\Quant\venv64\Scripts\python.exe D:\Quant\src\collectors\prices\fetch_etf_prices_daily.py --universe-csv D:\Quant\data\universe\universe_etf_master_latest.csv --start 2013-10-14 --end 2024-01-10

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
  --outdir .\reports\backtest_regime_refactor `
  --gsheet-enable `
  --gsheet-cred .\config\quant-485814-0df3dc750a8d.json `
  --gsheet-id "1HAiebouwL6d_ikBd5l6M3t7OO2Zg8bz3uS0aOPwXfXs" `
  --gsheet-tab S2_snapshot `
  --gsheet-mode overwrite `
  --gsheet-ledger `
  --gsheet-prefix S2
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


