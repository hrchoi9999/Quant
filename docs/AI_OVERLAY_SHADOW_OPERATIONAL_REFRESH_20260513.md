# AI Overlay Shadow Tracking Operational Refresh

- date: 2026-05-13
- status: operationalized
- scope: Quant-side data and payload generation only

## Purpose

AI overlay shadow tracking is now handled as an operational refresh step.
The step rebuilds strategy-model overlay backtests, validates the outputs, and refreshes the web current payloads used by QS.

## Current Wrapper

- script: `D:\Quant\scripts\run_ai_overlay_shadow_operational_refresh.py`
- command:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_ai_overlay_shadow_operational_refresh.py --asof YYYY-MM-DD
```

## Refresh Sequence

1. `run_downside_risk_ai_weekly_overlay_backtest.py`
2. `run_valuation_ai_weekly_overlay_backtest.py`
3. `run_candidate_rank_delta_weekly_overlay_backtest.py`
4. `run_ai_overlay_combo_strategy_backtest.py`
5. `run_ai_overlay_policy_map_backtest.py`
6. `build_ai_overlay_policy_map_current_payload.py`

## Daily Pipeline Integration

`D:\Quant\src\quant_service\run_daily_quant_pipeline.py` now calls the wrapper inside the `ai_overlay` command group.
It is skipped only when `--skip-ai-overlay` is passed.

## QS Handoff Payloads

- `D:\Quant\service_platform\web\admin_data\current\internal_models_ai_overlay_shadow_current.json`
- `D:\Quant\service_platform\web\admin_data\current\ai_learning_overlay_monitor_current.json`

These files remain admin-only shadow observation payloads.
They do not mean AI overlay has been applied to live recommendations.
