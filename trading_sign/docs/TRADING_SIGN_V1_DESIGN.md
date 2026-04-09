# Trading Sign V1 Design

## Goal

Build a V1 timing overlay model that improves buy and sell timing for Quant-selected stocks without replacing the existing stock-selection model.

The V1 model should answer three questions:

1. Is a selected stock eligible for entry now?
2. Should a held stock remain in the portfolio?
3. When should a sold stock become eligible again?

For the first release, the user-facing scope is narrower:

- provide daily timing-signal information for recommended stocks
- provide daily timing-signal information for currently held stocks
- do not automate execution
- do not attempt personalized trade instruction

## Boundary

- Existing Quant models outside this workspace are treated as upstream signal providers.
- Existing backtest and research assets outside this workspace are treated as read-only references.
- All new design, code, tests, and reports for this thread live only under `D:\Quant\trading_sign`.

## V1 product definition

V1 is a rules-based timing overlay with explicit state.

- `selection layer`
  - upstream Quant model supplies candidate stocks
- `timing layer`
  - entry filter
  - hold/exit manager
  - re-entry manager
- `execution layer`
  - downstream execution consumes timing decisions on a decision date and applies trades on the next executable date

## Investment horizon rule

V1 timing decisions must match the investment horizon of the upstream Quant models.

- this is not a day-trading or short-term tactical signal engine
- signal analysis should refresh daily using data collected up to the previous trading day
- decision interpretation should remain weekly or slower in spirit
- one-bar price noise should not dominate timing decisions
- persistent trend and deterioration signals should be preferred over fast triggers
- the system should behave like a portfolio maintenance overlay for mid- to long-horizon positions

## Signal refresh rule

V1 should recompute timing states every day after new end-of-day data is available.

- input cutoff is the latest completed trading day
- no intraday or same-day partial data is required for V1
- daily refresh is used to detect gradual deterioration or recovery earlier
- daily refresh does not change the fact that the underlying strategy is for mid- to long-horizon investing

## Why rules-first

V1 should be rules-based because:

- the current research already points to useful signals
- the behavior is explainable and auditable
- leakage risk is lower than jumping directly to ML
- debugging is easier when the selection model and timing model are separated

## Research signals to use first

Based on the read-only research references, the initial signal family should emphasize:

- fundamentals acceleration
  - `rev_delta_3m`
  - `op_delta_3m`
  - related acceleration composites
- long-trend alignment
  - `close > ma60 > ma120`
  - positive `ma60_slope`
  - positive `ma_stack_gap`

Signals that should be used cautiously or mostly as penalties:

- short-term crowdedness / overheat
  - `mom20`
  - `dist_ma60`
  - `breakout60`

## Core design principles

1. Keep alpha ownership separate.
The upstream Quant model owns stock selection. The timing model only manages entry, hold, exit, and re-entry.

2. Separate portfolio timing from stock timing.
Market-wide risk gating and stock-specific timing should not be mixed into one opaque rule.

3. Preserve decision-date semantics.
Signals are evaluated on a decision date. Execution assumptions are handled separately.

4. Make state explicit.
Exit streaks, cool-down windows, and re-entry eligibility should be stored as explicit state variables.

5. Match the upstream model horizon.
Timing rules must fit mid- to long-horizon investing and should not be optimized for intraday or short-term swing behavior.

6. Be model-aware by default.
Each upstream model has different turnover, holding style, and risk behavior, so timing rules must be configurable by model family and model code.

7. Separate refresh cadence from holding horizon.
The system should support daily signal recomputation while keeping thresholds and reactions aligned with multi-week to multi-month holding behavior.

## V1 module plan

The initial workspace structure should evolve toward the following:

- `D:\Quant\trading_sign\src\trading_sign\config.py`
- `D:\Quant\trading_sign\src\trading_sign\model_profiles.py`
- `D:\Quant\trading_sign\src\trading_sign\features.py`
- `D:\Quant\trading_sign\src\trading_sign\entry_rules.py`
- `D:\Quant\trading_sign\src\trading_sign\exit_rules.py`
- `D:\Quant\trading_sign\src\trading_sign\state.py`
- `D:\Quant\trading_sign\src\trading_sign\overlay.py`
- `D:\Quant\trading_sign\src\trading_sign\signal_history.py`
- `D:\Quant\trading_sign\src\trading_sign\validation.py`
- `D:\Quant\trading_sign\src\trading_sign\backtest.py`
- `D:\Quant\trading_sign\tests\`

## V1 state model

Per ticker state should include:

- `in_position`
- `entry_signal_date`
- `entry_exec_date`
- `entry_price`
- `holding_weeks`
- `below_ma60_streak`
- `nonpositive_ma60_slope_streak`
- `cooldown_weeks_left`
- `last_exit_reason`
- `last_exit_signal_date`

Portfolio-level state should include:

- `market_gate_open`
- `cash_weight`
- `rebalance_date`

## V1 entry logic

Entry should require both upstream candidacy and timing confirmation.

### Hard filters

- ticker is in the upstream selected set
- sufficient price history exists
- `close > ma60`
- `ma60 > ma120`
- `ma60_slope > 0`

### Quality filters

- acceleration features are above threshold
- crowdedness / overheat is not extreme

### Example V1 entry score

`entry_score = 0.45 * fund_accel + 0.35 * trend_align - 0.20 * overheat`

The score is only for thresholding and diagnostics in V1, not as a replacement for the upstream rank model.

## V1 hold / exit logic

Exit logic should be conservative and stateful.

### Base exit rules

- exit if `close < ma60` for `N1` consecutive decisions
- exit if `ma60_slope <= 0` for `N2` consecutive decisions
- exit if portfolio market gate closes and the stock also fails stock-level trend support

### Optional tightening rules for later sweeps

- stronger exit when overheat unwind happens after failed breakout
- partial de-risk instead of full exit

## V1 re-entry logic

Re-entry is allowed, but not immediately after every exit.

### Base re-entry rules

- cooldown window after exit
- trend alignment must recover
- entry score must again clear threshold

## Feature groups

### Entry features

- `close`, `ma20`, `ma60`, `ma120`
- `ma60_slope`, `ma120_slope`
- `dist_ma60`
- `ma_stack_gap`
- `rev_delta_3m`
- `op_delta_3m`
- `growth_score` or upstream rank metadata if available

### Exit features

- `close < ma60`
- `ma60_slope <= 0`
- cumulative return since entry
- drawdown from post-entry peak

### Portfolio timing features

- market breadth or aggregate market gate
- market trend state

## Model profile layer

V1 should include a model profile layer that maps each upstream model to a timing personality.

Minimum profile fields:

- `model_code`
- `signal_refresh_frequency`
- `decision_frequency`
- `expected_holding_horizon`
- `entry_style`
- `exit_style`
- `cooldown_style`
- `default_threshold_set`

Initial example groups:

- `fundamental_slow`
  - slower entry confirmation
  - slower exit persistence
  - lower sensitivity to short overheat
- `trend_following`
  - strong dependence on trend alignment
  - medium sensitivity to persistent trend breaks
  - re-entry allowed after structural recovery
- `defensive_allocation`
  - portfolio gate first
  - stock-level timing secondary
  - high emphasis on drawdown control

Default cadence assumptions:

- signal refresh: `daily_eod`
- source cutoff: `previous_trading_day_close`
- interpretation horizon: `multi_week`

## Evaluation framework

V1 must be judged on both portfolio and trade quality.

### Portfolio metrics

- CAGR
- MDD
- Sharpe
- turnover
- average cash weight

### Trade metrics

- win rate
- average gain
- average loss
- average holding period
- exit reason distribution
- re-entry frequency

### Timing quality metrics

- forward 4-week / 8-week / 12-week return after entry
- path MDD after entry
- avoided drawdown after exit
- missed upside after exit
- daily state stability and unnecessary churn rate

## Signal history requirement

Every generated daily timing signal should be stored for later replay and validation.

The stored record should preserve:

- `signal_date`
- `data_asof_date`
- `ticker`
- `model_code` or `service_profile`
- `current_state`
- `entry_score`
- `exit_risk_score` when available
- `reason_tags`
- `reason_summary`
- whether the name was recommended or already held at the time

This history is required so future validation can answer:

- what signal was actually generated on that day
- how often the state changed
- whether the signal improved later multi-week outcomes

## Development phases

### Phase 1. Workspace bootstrap

- create thread-local folder structure
- lock thread rules in docs
- define V1 architecture and interfaces

### Phase 2. Feature and state layer

- build feature calculators inside this workspace
- implement ticker state tracking
- define model profile registry and default timing presets
- add daily end-of-day refresh semantics based on previous trading day data

### Phase 3. Rules overlay

- implement entry rules
- implement exit rules
- implement re-entry rules
- bind timing rules to model profiles instead of one global rule set
- ensure rules use persistence so daily refresh does not degenerate into short-term overtrading

### Phase 4. Backtest harness

- build thread-local backtest runner that consumes upstream exported data or read-only references
- produce metrics and diagnostics under this workspace

### Phase 5. Parameter sweep

- threshold sweep for entry / exit persistence
- pick robust candidates

## Non-goals for V1

- end-to-end production deployment outside this workspace
- direct modification of existing Quant or QuantService code
- ML-first timing classifier

## Required handoff cases

Create a work request instead of editing external targets when:

- the upstream model must expose new fields
- an external backtest engine must be extended
- production reporting outside this workspace must consume timing outputs

## Immediate next implementation target

The next concrete step should be to create the thread-local source skeleton and implement:

- timing config schema
- feature schema
- ticker state container
- V1 entry and exit rule interfaces

The staged execution plan for this work is documented separately in:

- `D:\Quant\trading_sign\docs\TRADING_SIGN_PHASED_PLAN.md`
