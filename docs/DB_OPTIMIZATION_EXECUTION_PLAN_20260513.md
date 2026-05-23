# Quant DB Optimization Execution Plan

## Scope

This plan covers DB optimization order requested on 2026-05-13:

1. I-series DB optimization first
2. `generated_outputs.db` optimization second
3. `model_research.db` repeated-storage refactor third
4. Decide archive/move/VACUUM execution only after the above reviews

No archive, move, delete, table drop, or VACUUM has been executed yet.

## Source Reports

- `D:\Quant\reports\db_audit\I_SERIES_DB_OPTIMIZATION_PLAN_20260513_141330.md`
- `D:\Quant\reports\db_audit\GENERATED_OUTPUTS_DB_OPTIMIZATION_PLAN_20260513_141512.md`
- `D:\Quant\reports\db_audit\MODEL_RESEARCH_DB_OPTIMIZATION_PLAN_20260513_141901.md`
- `D:\Quant\reports\db_audit\QUANT_DB_TABLE_RETENTION_AUDIT_20260513_140134.md`

## 1. I-series DB Optimization

Current finding:

- I-series DB count reviewed: 49
- Total size: 15,949.85 MB
- Hot keep: 3 DBs / 783.50 MB
- Archive candidates: 46 DBs / 15,166.36 MB
- Main issue: experiment variant DBs repeatedly store the same base panels:
  - `i_stock_v01_features_daily`
  - `i_stock_v01_signals_weekly`
  - `i_stock_v01_regime_daily`

Hot keep DBs:

- `D:\Quant\data\db\i_series_research_strong_rsi_raw_top30_s65.db`
- `D:\Quant\data\db\i_series_research.db`
- `D:\Quant\data\db\i_series_operational.db`

Recommended execution after explicit approval:

1. Create `D:\Quant\data\db\archive\i_series_variants_20260513\`.
2. Move the 46 archive candidate DBs listed in `i_series_db_optimization_manifest_20260513_141330.csv`.
3. Keep reports under `D:\Quant\reports\i_series_stock_v01\` as experiment records.
4. Do not VACUUM I-series hot DBs now; expected gain is small.
5. Later refactor I-series scripts so variant runs store result/meta tables only, while base panels are canonicalized.

## 2. generated_outputs.db Optimization

Current finding:

- DB size: 450.94 MB
- Latest asof: 2026-05-12
- Asof snapshots: 24
- Proposed retention: latest 3 asof snapshots
- Keep asof dates:
  - 2026-05-12
  - 2026-05-11
  - 2026-05-08
- Archive/prune candidates:
  - 21 older asof dates
  - 1,846 artifact files
  - 919,224 stored artifact rows

Recommended execution after explicit approval:

1. Create backup copy of `D:\Quant\data\db\generated_outputs.db`.
2. Delete archive-asof linked rows from `generated_artifact_rows`.
3. Delete archive-asof rows from `generated_artifact_files`.
4. Run `VACUUM` on `generated_outputs.db`.
5. Keep future default retention at latest 3 asof snapshots.

## 3. model_research.db Repeated Storage

Current finding:

- DB size: 1,424.27 MB
- Table count: 75
- Total rows: 8,261,355
- Main issue: `universe_top_*_candidates` tables repeat the same base universe panel.
- `universe_top_*` candidate tables:
  - 9 tables
  - 6,616,534 rows
  - estimated repeated rows: 5,846,603

Primary duplicate review:

- `s3_two_stage_validation_selected`
  - 18,980 rows
  - duplicate extra rows: 4,380
  - likely true duplicate on `model_code, horizon, signal_date, ticker`

Recommended execution after explicit approval:

1. Do not drop `universe_top_*` tables immediately because existing scripts reference them.
2. Add a consolidated long-form table:
   - one base candidate table
   - bucket metadata columns such as `bucket_label`, `lower_threshold`, `upper_threshold`, `bucket_flag`, `bucket_rank`
3. Update dependent scripts to read from the consolidated table or compatibility views.
4. Fix/dedupe `s3_two_stage_validation_selected` write path.
5. After dependency migration, archive/drop repeated tables and run `VACUUM`.
6. Treat legacy ETF T-series research tables as archive candidates only after the ETF AI mart fully replaces them.

## Approval Gate

Before any destructive or path-moving operation:

1. Confirm latest pipeline still succeeds with current hot DB set.
2. Confirm QS/admin current payloads do not read archived DBs directly.
3. Create timestamped backups for DBs that will be pruned or vacuumed.
4. Verify target archive paths are under `D:\Quant\data\db\archive\`.
5. Execute archive/move/prune/VACUUM one group at a time.
6. Re-run DB inventory audit and pipeline smoke checks.

## Recommended Next Action

Start with I-series archive move after approval, because it has the largest immediate hot-folder reduction and lowest operational risk.
