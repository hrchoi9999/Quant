# Generated File Retention Policy

## Purpose

This policy separates Quant generated files into operational classes so we can reduce disk growth without damaging live web/current delivery or historical analysis that still needs to be read.

## File Classes

### 1. Current public handoff

Keep indefinitely.

Examples:
- `D:\Quant\service_platform\web\public_data\current`
- `D:\Quant\trading_sign\service_platform\web\public_data\current`

Rules:
- Never clean automatically.
- `current`, `latest`, and `manifest` files are protected.
- These are the source assets for web/QS/live handoff.

### 2. Operational history

Keep for a medium retention window, then archive.

Targets in the current cleanup step:
- `D:\Quant\reports\backtest_router`
- `D:\Quant\reports\model_compare`
- `D:\Quant\reports\backtest_s3_dev`
- `D:\Quant\reports\backtest_regime_refactor`
- `D:\Quant\reports\backtest_etf_allocation`
- `D:\Quant\reports\redbot_user_reports`

Rules:
- Dated generated files are archived after retention days.
- Files without date tokens are ignored.
- Current step uses archive move, not delete.

### 3. Rebuildable temp/intermediate outputs

Archive aggressively.

Targets in the current cleanup step:
- `D:\Quant\data\universe`
- `D:\Quant\reports\service_analytics_review`

Rules:
- Dated rebuildable files are archived on a short window.
- `latest`, `current`, `manifest` files are always protected.

### 4. Research outputs

Not touched automatically in this first pass.

Examples:
- `D:\Quant\reports\model_upgrade_research`

Rules:
- Managed manually or by a later dedicated archive policy.
- We avoid automatic moves here because these files are often used for ad hoc inspection.

### 5. Legacy pre-KRX evidence

Archive out of operational report paths after the KRX correction baseline is established.

Targets:
- `D:\Quant\reports\historical_rebase\precheck_20260417\before`
- `D:\Quant\reports\historical_rebase\krx_rebase_20260417\before`

Rules:
- Move to `D:\Quant\archive\legacy_pre_krx\YYYYMMDD\...`.
- Keep comparison summaries and clean diff CSVs in `reports\historical_rebase`.
- Leave a pointer README in the original report folder.
- Do not delete or rewrite `price.db`; legacy DB rows are replaced only through controlled KRX upsert/backfill.

Manual archive command:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\archive_pre_krx_legacy_outputs.py --asof 2026-04-18 --execute
```

## Initial Retention Windows

- `data\universe`: 30 days
- `reports\redbot_user_reports`: 45 days
- `reports\backtest_router`: 60 days
- `reports\model_compare`: 60 days
- `reports\backtest_s3_dev`: 60 days
- `reports\backtest_regime_refactor`: 60 days
- `reports\backtest_etf_allocation`: 60 days
- `reports\service_analytics_review`: 21 days

## Archive Location

Archived files are moved to:
- `D:\Quant\archive\generated_retention\YYYYMMDD\...`

Each cleanup run can also write:
- `cleanup_manifest.json`

## Daily Pipeline Integration

The daily pipeline now runs conservative generated-file cleanup by default after:
1. data refresh
2. backtests
3. ingest/publish
4. web snapshots
5. trading_sign
6. canonical current republish

Then it runs:
- `D:\Quant\scripts\cleanup_generated_files.py --asof <date> --execute --write-manifest`

Skip it explicitly with:
- `--skip-generated-file-cleanup`

## Safety Rules

- No cleanup in `public_data\current`
- No cleanup for files containing `latest`, `current`, or `manifest` in the filename
- No cleanup for files without an 8-digit date token in the stem
- Cleanup currently archives files rather than deleting them

## Operational Intent

This first version is intentionally conservative.

Goals:
- reduce clutter in `data\universe` and rebuildable report directories
- preserve current/public handoff assets
- preserve recent operational history
- avoid deleting research artifacts automatically
