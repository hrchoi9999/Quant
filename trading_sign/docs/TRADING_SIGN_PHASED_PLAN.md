# Trading Sign Phased Plan

## Objective for Phase 1

The first release of `trading_sign` should provide daily timing-signal status for:

- recommended stocks
- currently held stocks

The goal is not to automate trading execution.
The goal is to provide a daily-updated, mid- to long-horizon timing interpretation for names already surfaced by upstream Quant models.

## Phase 1 user-facing outcome

For each target stock, the system should show the day's timing state based on data collected up to the previous trading day.

Minimum output per stock:

- ticker
- stock name
- source model or service profile
- current timing state
- short reason summary
- latest state change date

These daily signals must also be stored historically so the team can later verify:

- what signal was generated on each day
- which reasons were attached at that time
- what happened afterward

Recommended state labels:

- `매수`
- `보유`
- `주의`
- `매도`
- `매수 대기`

## Phase breakdown

### Stage 0. Scope lock

Purpose:

- freeze the first delivery scope
- avoid expanding into execution, personalization, or short-term trading logic

Deliverables:

- thread rules document
- signal principles document
- phased plan document

Done when:

- the team agrees that V1 only covers daily signal information for recommended and held names

### Stage 1. Model profile registry

Purpose:

- define how each upstream model should be interpreted by the timing overlay

Tasks:

- group upstream models by timing personality
- define profile fields
- define default thresholds and persistence style per profile

Deliverables:

- `src/trading_sign/model_profiles.py`
- model profile notes in docs

Done when:

- every target upstream model can be mapped to a model profile

### Stage 2. Daily feature specification

Purpose:

- define the daily end-of-day inputs required for timing decisions

Tasks:

- define read-only upstream data sources
- define feature names and calculations
- define `signal_date` and `data_asof_date` semantics

Core feature groups:

- trend alignment
- fundamentals acceleration
- overheat / crowdedness
- market or regime gate

Deliverables:

- `src/trading_sign/features.py`
- feature spec notes

Done when:

- a daily feature snapshot can be built for recommended and held names using previous-trading-day data

### Stage 3. Daily timing state engine

Purpose:

- compute the daily state for each stock

Tasks:

- implement entry-state evaluation
- implement hold / warning / exit-state evaluation
- implement re-entry cooldown logic
- keep logic stateful and persistence-based

Deliverables:

- expanded `entry_rules.py`
- expanded `exit_rules.py`
- state transition logic in `overlay.py`
- signal-record generation compatible with historical storage

Done when:

- the engine can produce one timing state per stock per signal date

### Stage 4. Signal history storage

Purpose:

- preserve daily generated signals for later audit and validation

Tasks:

- define a thread-local signal history schema
- store one record per stock per signal date
- store reasons, state labels, and score fields
- support re-loading past signals by date, model, and ticker

Deliverables:

- `src/trading_sign/signal_history.py`
- `data/db/trading_sign.db` schema definition
- history storage tests

Done when:

- the system can persist and query daily timing signals reliably

### Stage 5. Backtest and validation harness

Purpose:

- validate that the daily state engine improves interpretability and does not create short-term noise

Tasks:

- run daily historical replay
- evaluate state persistence
- evaluate signal usefulness for multi-week outcomes
- attach realized forward outcomes to stored historical signals

Validation focus:

- 4-week / 8-week / 12-week forward return
- path MDD after signal
- unnecessary state churn rate
- model-by-model stability

Deliverables:

- `src/trading_sign/backtest.py`
- `src/trading_sign/validation.py`
- research outputs under `reports/`

Done when:

- rules pass a basic quality gate on both usefulness and stability

### Stage 6. Snapshot generation

Purpose:

- convert daily timing states into web-consumable outputs

Tasks:

- build overview payload
- build per-model detail payload
- build manifest and freshness metadata

Deliverables:

- `tradingsign_overview.json`
- `tradingsign_model_detail.json`
- `tradingsign_manifest.json`
- API-shaped variants if needed

Done when:

- QuantService can consume the outputs without recalculating the signals

### Stage 7. QuantService handoff

Purpose:

- prepare external integration without modifying external workspaces in this thread

Tasks:

- define payload contract
- define UI placement proposal
- write cross-thread work request

Suggested UI landing points:

- summary card on the current model page
- dedicated `timing briefing` detail page

Deliverables:

- handoff spec document
- `docs/TRADING_SIGN_REDBOT_UI_PLAN.md`
- cross-thread work request

Done when:

- QuantService has a clear implementation request with stable payload examples

## Recommended execution order

1. Stage 1. Model profile registry
2. Stage 2. Daily feature specification
3. Stage 3. Daily timing state engine
4. Stage 4. Signal history storage
5. Stage 5. Backtest and validation harness
6. Stage 6. Snapshot generation
7. Stage 7. QuantService handoff

## Phase 1 success criteria

Phase 1 is successful if:

- the system updates daily using previous-trading-day data
- the output covers recommended and held names
- the signal states remain consistent with mid- to long-horizon investing
- the results are explainable
- the outputs are ready for web integration

## Explicit exclusions for Phase 1

Phase 1 does not include:

- automated trade execution
- personalized user-specific signals
- intraday updates
- ultra-short-term trading logic
- direct editing of QuantService from this thread
