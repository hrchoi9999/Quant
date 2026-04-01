## T-series Query Layer

### Purpose

- Read the latest operational `T-series` outputs directly from [D:\Quant\data\db\tseries_operational.db](D:/Quant/data/db/tseries_operational.db)
- Return one consistent snapshot per model:
  - latest `asof_date`
  - model meta
  - threshold profile
  - latest run info
  - latest candidates by bucket
  - shadow tracking summary

### Reader module

- [D:\Quant\src\quant_service\read_tseries_operational.py](D:/Quant/src/quant_service/read_tseries_operational.py)

Main functions:
- `connect()`
- `load_model_meta()`
- `load_current_profile()`
- `load_latest_candidates()`
- `load_shadow_summary()`
- `load_run_meta()`
- `build_snapshot()`

### CLI

- [D:\Quant\scripts\query_tseries_operational.py](D:/Quant/scripts/query_tseries_operational.py)

Example:

```powershell
cd D:\Quant
.\venv64\Scripts\python.exe .\scripts\query_tseries_operational.py --model-code T-STOCK-V01
.\venv64\Scripts\python.exe .\scripts\query_tseries_operational.py --model-code T-ETF-V01
```

### Output shape

- `model_code`
- `asof_date`
- `meta`
- `profile`
- `run`
- `bucket_counts`
- `top_by_bucket`
- `shadow_summary`

### Intended usage

- internal ops check
- pipeline post-run verification
- later QS/web publish adapter
