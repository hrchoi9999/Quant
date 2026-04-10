# Generated CSV to DB Transition

## Purpose

This is the first step in moving dated operational CSV outputs away from being long-term source-of-truth files.

The goal is not to remove CSV generation immediately. Instead, the pipeline now copies dated generated CSV contents into a queryable SQLite database, then CSV files can be treated as export/debug artifacts and archived by retention policy.

## Database

- `D:\Quant\data\db\generated_outputs.db`

## Tables

### `generated_artifact_files`

One row per synced CSV artifact.

Key fields:
- `rel_path`
- `asof_date`
- `artifact_group`
- `artifact_kind`
- `file_size`
- `sha256`
- `row_count`
- `column_json`
- `synced_at`

### `generated_artifact_rows`

One row per CSV row.

Fields:
- `artifact_id`
- `row_no`
- `row_json`

Rows are stored as JSON to support heterogeneous CSV schemas while keeping one operational storage layer.

## Synced Roots

Current first-pass roots:
- `D:\Quant\data\universe`
- `D:\Quant\reports\backtest_router`
- `D:\Quant\reports\model_compare`
- `D:\Quant\reports\backtest_s3_dev`
- `D:\Quant\reports\backtest_regime_refactor`
- `D:\Quant\reports\backtest_etf_allocation`
- `D:\Quant\reports\redbot_user_reports`

Protected files:
- `latest`
- `current`
- `manifest`

## Daily Pipeline Integration

The daily pipeline runs CSV-to-DB sync after canonical current publish and before generated-file cleanup.

Default command:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\sync_generated_csv_to_db.py --asof <YYYY-MM-DD>
```

Skip with:

```powershell
--skip-generated-csv-db-sync
```

## Manual Commands

Sync one date:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\sync_generated_csv_to_db.py --asof 2026-04-10
```

Backfill all dated CSV artifacts:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\sync_generated_csv_to_db.py --all
```

## Current Scope

This first pass provides a DB-backed archive/query layer for generated CSVs.

It does not yet remove CSV writers from model scripts. That should be done gradually after readers are migrated to DB queries or JSON current exports.

## Next Migration Step

For high-value recurring outputs, replace generic `row_json` storage with typed tables:
- universe history
- router summary/equity/weights
- model compare summary/periods/yearly
- S2/S3 holdings/nav
- ETF allocation weights/summary

Until then, the generic DB layer allows us to archive dated CSV files safely while retaining queryable historical contents.
