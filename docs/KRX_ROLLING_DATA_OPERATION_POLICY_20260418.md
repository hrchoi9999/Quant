# KRX Rolling Data Operation Policy

## Purpose

KRX OpenAPI is the official source for Korean stock and ETF daily price data, but it still needs our own operating checks.

The S2 2026-03-31 case showed that a corrected price database can change a model from full stock exposure to full cash. Therefore, the Quant pipeline must treat data quality as a first-class model component:

1. collect KRX data,
2. compare it with `price.db`,
3. log any difference,
4. upsert only through controlled backfill,
5. rerun model-impact checks when differences are material.

This policy covers stock and ETF daily OHLCV data used by S-series, T-series, user portfolios, and trading-sign generation.

## Source Of Truth

- Official source: KRX OpenAPI
- API key file: `D:\Quant\config\KRX_API_Key.json`
- Production price DB: `D:\Quant\data\db\price.db`
- Data quality DB: `D:\Quant\data\db\data_quality.db`
- Audit reports: `D:\Quant\reports\data_quality\krx_price_audit`
- Backfill reports: `D:\Quant\reports\data_quality\krx_price_backfill`
- Cycle plans: `D:\Quant\reports\data_quality\krx_operation_cycle`

Never print the KRX API key in logs, docs, reports, or handoff messages.

## Operating Cadence

| Cadence | Default window | Default operation | Purpose |
|---|---:|---|---|
| Daily | latest 14 calendar days | audit | Catch missing rows, recent KRX corrections, and collection glitches. |
| Weekly | latest 93 calendar days | backfill dry-run | Re-download recent 3 months and review old/new differences before upsert. |
| Monthly | latest 366 calendar days | backfill dry-run | Reconcile recent 1 year, especially data used by recent backtests and performance pages. |
| Quarterly | previous full year | backfill dry-run | Revalidate older backtest history with low API pressure. |
| Custom | user-specified | audit or backfill | Ad-hoc investigation or remediation. |

The default mode is intentionally conservative:

- plan-only unless `--execute` is provided,
- backfill dry-run unless `--apply` is provided,
- universe-limited by default,
- KRX missing rows never delete existing DB rows.

## Batch Timing Policy

KRX stock and ETF same-day availability do not behave the same way in practice.

- Stock same-day rows are often available on the evening of the trading day.
- ETF same-day rows can be delayed and may still be incomplete on the same evening.

Because of that, Quant daily operation uses a two-step timing policy:

1. `evening provisional internal batch`
   - run after market close,
   - allow internal review of stock-driven models,
   - do not update canonical public current,
   - treat results as provisional when ETF same-day coverage is incomplete.

2. `next-morning final operational batch`
   - rerun after checking that stock and ETF data are both complete for the previous trading date,
   - regenerate all models and downstream payloads on the same common `asof`,
   - publish to GCS and website only from this final batch.

This means the publish `asof` is not simply “today if stock exists.” It is the latest date where stock and ETF operating inputs are both complete enough to satisfy the pipeline contract.

## Default Universes

Stock cycle:

- markets: `KOSPI,KOSDAQ`
- ticker file: `D:\Quant\data\universe\universe_mix_top400_latest_fundready.csv`

ETF cycle:

- markets: `ETF`
- ticker file: `D:\Quant\data\universe\universe_etf_master_latest.csv`

These defaults keep KRX API pressure bounded and align the validation target with the investable model universe.

## Safety Gates

Run order should be:

1. `plan-only`
2. `--execute` dry-run
3. review generated report directory
4. if differences are expected and acceptable, rerun with `--execute --apply`
5. rerun affected model outputs only when data changes are material

Material data changes include:

- any price mismatch on model-held tickers,
- large missing row counts,
- universe classification issues,
- changes that alter S2 cash weight, S3/S3_CORE2 holdings, S4/S5/S6 allocations, T-series buckets, or trading-sign outputs.

## Routine Refresh vs Data Rebase

Do not interpret every model change as a normal daily data-refresh effect.

Classify each run into one of these run types before reviewing model changes:

| Run type | Definition | Interpretation |
|---|---|---|
| `routine_refresh` | Only latest daily/weekly market data was added on top of the current KRX baseline. | Candidate and portfolio changes can be interpreted as normal model response. |
| `data_rebase` | Historical `price.db`, universe, feature panels, or model input history were corrected or rebuilt. | Candidate and portfolio changes must be interpreted as baseline-change effects until old/new impact is reviewed. |
| `schema_or_logic_change` | Collector, feature, filter, threshold, universe, or publish logic changed. | Results are not directly comparable to prior runs without a change note. |
| `emergency_repair` | A failed or partial run was repaired manually. | Publish only after explicit validation and root-cause note. |

The 2026-04 KRX correction is a `data_rebase` event. T-series changes after that rebase should not be described as simple one-day sensitivity until several routine refreshes on the same KRX baseline are observed.

## End-to-End Data Quality Control Process

The operating process has five mandatory controls.

| Control | What to check | Minimum action |
|---|---|---|
| 1. Input data quality gate | `price.db`, stock/ETF row counts, missing/duplicate rows, OHLCV zero/null anomalies, universe counts, KRX source labels, S3 features, regime, fundamentals max dates. | Block or warn before model interpretation if critical input checks fail. |
| 2. T-series volatility gate | Prior-run vs current-run candidate turnover, bucket churn, confirmed/near/observe counts, wrapper/internal asof mismatch, risk-filter exclusions, theme-cap effects. | If churn is abnormal, classify the run reason before publishing or explaining results. |
| 3. Publish restriction | Public current should not update automatically when input quality is critical-fail or T-series dates disagree with wrapper dates. | Hold GCS publish or publish only after explicit override note. |
| 4. Rolling watchlist continuity | T-series candidates must be tracked cumulatively, not treated as valid only on the first day/week they appear. | Maintain active/new/cooling state and first_seen/last_seen fields. |
| 5. Change root-cause log | Large candidate changes must be explained by data, universe, feature, threshold, filter, or publish-layer causes. | Store a dated note/report before final interpretation. |

## Redbot Data Quality Baseline Start

The first redbot data-quality baseline is the 2026-04-17 as-of check recorded on 2026-04-18.

This baseline intentionally uses different comparison bases for the first two controls:

| Control | Baseline comparison basis | Baseline result |
|---|---|---|
| 1. Input data quality gate | Current KRX audit, `price.db` coverage, OHLCV anomaly rate, universe drift, and source/freshness checks for the 2026-04-17 operating data. | `green` |
| 2. T-series volatility gate | Pre-KRX-rebase public current vs current public current. Immediate post-rebase day-to-day comparison is not enough for the first baseline. | `block_or_rebase_review` for T-STOCK and T-ETF |

Baseline evidence:

- Input gate report: `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\input_data_quality_gate_20260417.json`
- Main quality report: `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\quality_gate_report_20260417.md`
- T-series immediate comparison: `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\tseries_volatility_gate_20260417_vs_20260416.json`
- T-ETF pre-rebase comparison: `D:\Quant\reports\data_quality\quality_gate\tseries_input_volatility_gate_20260417_20260418_174910\tseries_volatility_gate_pre_rebase_vs_current_20260417.md`
- Baseline summary document: `D:\Quant\docs\REDBOT_DATA_QUALITY_BASELINE_20260418.md`

Interpretation:

1. The input data quality gate confirms that the current KRX-based data surface is usable.
2. The T-series volatility gate confirms that the KRX rebase materially changed discovery candidates, so the first post-rebase T-series output should be treated as a new baseline rather than a normal daily refresh movement.
3. Future routine refreshes should be compared against this baseline unless another `data_rebase`, `schema_or_logic_change`, or `emergency_repair` run occurs.

## Management Indicators

Track these indicators for every daily or weekly operating run. Use `warn` as a review trigger and `block` as a default publish-hold trigger unless an explicit override is recorded.

### Source And Freshness Indicators

| Indicator | Scope | Green | Warn | Block |
|---|---|---:|---:|---:|
| `price_max_date_lag_days` | stock, ETF | 0 trading days | 1 trading day | 2+ trading days |
| `stock_price_rows_asof` | current stock universe | >= 98% of expected tickers | 95% to <98% | <95% |
| `etf_price_rows_asof` | ETF master universe | >= 98% of expected tickers | 95% to <98% | <95% |
| `duplicate_price_rows` | `prices_daily` `(ticker,date)` | 0 | 1 to 5 | >5 |
| `ohlcv_null_or_zero_rate` | model universe | <= 0.5% | >0.5% to 2% | >2% |
| `krx_audit_mismatch_rate` | audited rows | 0% | >0% to 0.2% | >0.2% or any held ticker mismatch |
| `krx_missing_db_rows` | audited rows | 0 | 1 to 5 explainable rows | >5 or unexplained held ticker rows |

### Universe And Feature Alignment Indicators

| Indicator | Scope | Green | Warn | Block |
|---|---|---:|---:|---:|
| `stock_universe_count_drift_pct` | latest vs prior stock universe | <= 5% | >5% to 10% | >10% |
| `etf_universe_count_drift_pct` | latest vs prior ETF universe | <= 5% | >5% to 10% | >10% |
| `fundready_count` | stock universe | >= 180 | 160 to 179 | <160 |
| `s3_price_feature_max_date_lag_days` | S3 feature DB | 0 trading days | 1 trading day | 2+ trading days |
| `regime_max_date_lag_days` | regime DB | 0 trading days | 1 trading day | 2+ trading days |
| `fundamentals_month_end_alignment` | fundamentals DB | latest available month-end | one month stale | two+ months stale |

### T-series Stability Indicators

| Indicator | Scope | Green | Warn | Block / Hold |
|---|---|---:|---:|---:|
| `tseries_wrapper_internal_date_match` | T-STOCK, T-ETF | all match | any mismatch | any mismatch in publish candidate |
| `tseries_candidate_turnover_pct` | current vs prior watchlist | <= 40% | >40% to 70% | >70% unless run_type is `data_rebase` or `schema_or_logic_change` |
| `confirmed_bucket_turnover_pct` | confirmed bucket | <= 50% | >50% to 80% | >80% unless explained |
| `candidate_count_collapse_pct` | current vs prior candidate count | <= 50% drop | >50% to 75% drop | >75% drop |
| `risk_filter_exclusion_spike_pct` | risk-filter exclusions | <= 2x prior median | >2x to 4x | >4x |
| `theme_cap_binding_count` | T-series theme cap | stable or explained | unexplained spike | spike that removes all confirmed names |
| `rolling_watchlist_state_coverage` | active/new/cooling rows | 100% | 95% to <100% | <95% |

### Publish And Handoff Indicators

| Indicator | Scope | Green | Warn | Block |
|---|---|---:|---:|---:|
| `web_snapshot_validator_status` | public current | pass | n/a | fail |
| `admin_tracker_validator_status` | admin current | pass | n/a | fail |
| `trading_sign_validator_status` | trading sign current | pass | n/a | fail |
| `gcs_publish_asof_match` | remote current | all match | any lag | any critical current lag |
| `root_cause_log_coverage` | material changes | 100% | 80% to <100% | <80% |

## Publish Decision Rules

Use these rules after model generation and before GCS publish:

1. If any source/freshness indicator is `block`, do not publish public current until reviewed.
2. If same-day stock data is present but same-day ETF coverage is incomplete, do not publish the evening run as canonical current. Keep public current on the last complete common date and rerun the final batch the next morning.
3. If T-series wrapper/internal dates do not match, do not publish T-series current.
4. If T-series turnover is `block` but run type is `data_rebase` or `schema_or_logic_change`, publish only after old/new comparison and change note.
5. If the run is `routine_refresh` and T-series turnover is `block`, hold publish and inspect root cause.
6. If validators fail, do not publish.
7. If publish is overridden, record the override reason, owner, run type, and affected payloads.

## Required Run Note Template

Every material run should leave a short note in the related report directory or handoff summary:

```text
run_date:
asof_date:
run_type: routine_refresh | data_rebase | schema_or_logic_change | emergency_repair
data_scope: stock | etf | both
source_summary:
quality_status: pass | warn | block | override
model_impact_summary:
tseries_turnover_summary:
publish_decision: published | held | override_published
root_cause:
follow_up:
```

## Execution Module

Primary wrapper:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --help
```

Daily plan-only:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --asof 20260416 --cadence daily --asset-scope both
```

Daily audit execution:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --asof 20260416 --cadence daily --asset-scope both --execute
```

Weekly 3-month dry-run backfill:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --asof 20260416 --cadence weekly --asset-scope both --execute
```

Weekly 3-month apply after review:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --asof 20260416 --cadence weekly --asset-scope both --execute --apply
```

Quarterly previous-year dry-run:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --asof 20260416 --cadence quarterly --target-year 2025 --asset-scope both --execute
```

Custom stock-only audit:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --cadence custom --operation audit --asset-scope stock --start 20260301 --end 20260331 --execute
```

Custom ETF-only dry-run backfill:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\run_krx_data_quality_cycle.py --cadence custom --operation backfill --asset-scope etf --start 20260301 --end 20260331 --execute
```

## Output Contract

Every cycle writes a plan directory under:

```text
D:\Quant\reports\data_quality\krx_operation_cycle\krx_cycle_<cadence>_<operation>_<timestamp>
```

Files:

- `plan.json`: machine-readable plan
- `plan.md`: human-readable command plan
- `command_*.log`: command logs when `--execute` is used
- `execution_results.json`: command return codes when `--execute` is used

The underlying audit/backfill scripts continue to write detailed reports into their existing data-quality directories and DB tables.

## Model Impact Audit

KRX data changes should not automatically imply model publication.

After material `price.db` changes:

1. rerun the affected historical/current model outputs,
2. compare old/new metrics and portfolios,
3. inspect S2 cash-weight changes and S3/S3_CORE2 holding changes,
4. regenerate public current only after the changes are understood,
5. publish to web current only after snapshot validation passes.

Current helper for historical model-output rebase:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\rebase_historical_model_outputs.py --run-id <run_id>
```

## Operational Interpretation

KRX data is the official input, but model trust comes from:

- official source collection,
- repeated rolling verification,
- old/new difference logs,
- controlled upsert,
- model-impact comparison.

For QuantService/redbot operations, this means data quality is not a support task. It is part of the model itself.
