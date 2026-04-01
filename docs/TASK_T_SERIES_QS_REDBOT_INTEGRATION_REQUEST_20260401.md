## T-series QS / redbot.co.kr Integration Request

### 1. Objective

- Reflect `T-series` model outputs in QS so they can also be queried and displayed on `redbot.co.kr`
- Keep existing `S-series` behavior unchanged
- Expose `T-series` as a new shadow/discovery model family first, without mixing it into current `S-series` ranking logic

### 2. Background

`T-series` is no longer a research-only output.

The following operational models are now available:
- `T-STOCK-V01`
- `T-ETF-V01`

Current storage:
- Operational DB: [D:\Quant\data\db\tseries_operational.db](D:/Quant/data/db/tseries_operational.db)
- Reader module: [D:\Quant\src\quant_service\read_tseries_operational.py](D:/Quant/src/quant_service/read_tseries_operational.py)
- Query CLI: [D:\Quant\scripts\query_tseries_operational.py](D:/Quant/scripts/query_tseries_operational.py)

Current pipeline status:
- Daily orchestration already runs `T-STOCK-V01` and `T-ETF-V01` as shadow refresh models
- Results are synced into `tseries_operational.db`
- `S-series` operational DBs remain unchanged

### 3. Naming Rules For QS

Do not expose internal-only family labels as primary service labels.

Use the following names in QS / service:

- `T-STOCK-V01`
  - English label: `transition-based discovery model`
  - Korean label: `전이형 발굴 모델`
  - Asset scope: `stock`

- `T-ETF-V01`
  - English label: `transition-based discovery model`
  - Korean label: `전이형 발굴 모델`
  - Asset scope: `etf`

For `S-series`, keep current internal naming, but QS display wording should remain:
- English label: `cross-sectional ranking model`
- Korean label: `랭킹형 종목선정 모델`

### 3.1 Internal To Service Mapping Rules

`T-series` should not be mapped into the same primary model slot used by `S-series`.

Recommended mapping:

- `T-STOCK-V01`
  - `service_model_code`: `T_STOCK_DISCOVERY`
  - `service_family`: `discovery`
  - `service_role`: `watchlist`
  - `is_user_visible`: `1`

- `T-ETF-V01`
  - `service_model_code`: `T_ETF_DISCOVERY`
  - `service_family`: `discovery`
  - `service_role`: `watchlist`
  - `is_user_visible`: `1`

Reference rule:
- `S-series` remains the primary `ranking` / `allocation` family
- `T-series` is a separate `discovery` family
- `T-series` must not overwrite or replace current `pub_model_current` semantics for `S-series`

If QS needs a mapping table or config, recommended fields are:
- `internal_model_code`
- `service_model_code`
- `service_family`
- `service_role`
- `display_name_en`
- `display_name_ko`
- `asset_scope`
- `is_user_visible`
- `display_order`

### 4. Source Of Truth

QS should read `T-series` data from:
- [D:\Quant\data\db\tseries_operational.db](D:/Quant/data/db/tseries_operational.db)

Primary tables:
- `ts_meta_models`
- `ts_threshold_profiles`
- `ts_runs`
- `ts_candidates_latest`
- `ts_candidates_history`
- `ts_shadow_tracking_summary`

Recommended read path:
- Use [D:\Quant\src\quant_service\read_tseries_operational.py](D:/Quant/src/quant_service/read_tseries_operational.py) as the application-side read layer
- Do not read random CSV files under `reports\...` directly for service integration

### 5. Minimum QS Exposure Scope

Expose the following for each `T-series` model.

#### 5.1 Model summary

- `model_code`
- display name
- asset scope
- version
- latest `asof_date`
- profile code
- threshold summary
- risk filter version

#### 5.2 Candidate buckets

Expose latest candidates by bucket:
- `confirmed`
- `near`
- `observe`

Fields to expose:
- `ticker`
- `name`
- `market`
- `theme_bucket`
- `theme_name_kr`
- `stage1_prob`
- `stage2_prob`
- `is_s2_overlap` for stock only when available

#### 5.3 Shadow tracking summary

Expose summary metrics:
- `obs_n`
- `t10_hit_rate`
- `t3_hit_rate`
- `avg_stage1_prob`
- `avg_stage2_prob`

### 6. Service Behavior

Initial release should be read-only and separated from current `S-series` holdings views.

Recommended behavior:
- Add a new `T-series` section in QS / service
- Do not replace current `S2/S3/S4/S5/S6` views
- Do not merge `T-series` candidates into current live holdings tables
- Treat `T-series` as discovery/watchlist outputs

### 7. redbot.co.kr Display Recommendations

Recommended first display block:

- Section title: `T-series Discovery`
- Tabs:
  - `Stock`
  - `ETF`

Inside each tab:
- latest model info
- `confirmed / near / observe` sections
- short explanation:
  - `confirmed`: high-priority discovery candidates
  - `near`: second-priority candidates
  - `observe`: monitoring candidates

Recommended disclaimer:
- `T-series is a transition-based discovery model. It is designed to identify potential upgrade candidates, not to replace the existing ranking models.`

Korean:
- `T-series는 전이형 발굴 모델이며, 기존 랭킹형 모델을 대체하기보다 상위 그룹 승격 가능성이 있는 후보를 탐지하기 위한 모델입니다.`

### 8. API / Adapter Requirement

QS should implement one adapter layer that returns a normalized payload per model.

Target payload shape:
- `model_code`
- `asof_date`
- `meta`
- `profile`
- `run`
- `bucket_counts`
- `top_by_bucket`
- `shadow_summary`

This is already aligned with:
- [D:\Quant\src\quant_service\read_tseries_operational.py](D:/Quant/src/quant_service/read_tseries_operational.py)

### 9. Non-goals For This Request

Do not include the following in this task:
- T-series data collection automation changes
- T-series DB schema redesign
- S-series logic changes
- router decision integration
- trading execution integration
- Google Sheets integration

### 10. Acceptance Criteria

This task is complete when all of the following are true.

1. QS can read both `T-STOCK-V01` and `T-ETF-V01` from `tseries_operational.db`
2. `redbot.co.kr` can display latest `confirmed / near / observe` candidates for both models
3. Latest `asof_date`, threshold profile, and shadow summary are visible
4. Existing `S-series` pages and data are unaffected
5. Missing candidate buckets are handled gracefully
6. No direct dependency on research CSV paths remains in the service layer

### 11. Current Reference Snapshot

Current examples at time of request:

- `T-STOCK-V01`
  - latest `asof_date`: `2026-03-26`
  - buckets: `confirmed 6 / near 3 / observe 1`

- `T-ETF-V01`
  - latest `asof_date`: `2026-03-31`
  - buckets: `confirmed 1 / near 2`

These values may change after future refreshes, but the read structure should remain stable.

### 12. Implementation Priority

Recommended order:

1. QS backend adapter for `tseries_operational.db`
2. API response contract
3. redbot service section rendering
4. UI wording / labels / disclaimer
5. QA with latest live shadow refresh output

