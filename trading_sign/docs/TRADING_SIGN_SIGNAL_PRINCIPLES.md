# Trading Sign Signal Principles

## Purpose

This document records the core signal-design principles for this thread.

## Principle 1. Mid- to long-horizon alignment

The trading signal model in this thread is not for day trading or short-term tactical trading.

It must be designed with the same horizon assumptions as the upstream Quant models:

- Quant-selected names are mid- to long-horizon candidates
- signal evaluation should be based on weekly or slower analysis by default
- entry and exit logic should react to persistent condition changes rather than intraday noise
- the model should support disciplined portfolio maintenance, not rapid turnover

This horizon rule does not mean signals should only be evaluated weekly.
The system should refresh signals every day using data collected up to the previous trading day, while keeping the interpretation and decision logic aligned with mid- to long-horizon investing.

### Implications

- default signal refresh cadence should be daily
- daily analysis must use data available up to the previous trading day
- default decision interpretation should still target weekly or slower portfolio management
- persistence rules are preferred over one-bar triggers
- overheat and reversal signals should be used as filters or penalties, not as standalone short-term trade triggers
- evaluation should focus on multi-week and multi-month outcomes

## Principle 1-A. Separate refresh cadence from investment horizon

The system must distinguish between:

- `signal refresh cadence`
  - daily
- `portfolio holding horizon`
  - mid- to long-horizon
- `decision style`
  - persistent, stateful, non-intraday

This means the model can update every day without becoming a short-term trading engine.

## Principle 2. Model-specific timing behavior

Each upstream Quant model has its own character.

The timing model must reflect that character instead of applying one universal rule set to all models.

Important dimensions include:

- selection logic
- turnover tendency
- expected holding period
- trend sensitivity
- drawdown tolerance
- portfolio role

### Implications

- timing logic must be model-aware
- thresholds should be adjustable per model or model family
- slower models should not be forced into fast-reacting exit rules
- trend-oriented models can use stronger trend-maintenance conditions
- defensive or allocation-oriented models may prioritize portfolio regime controls over single-name timing signals

## Required design response

The V1 system should have:

1. a shared timing framework
2. model-family timing presets
3. optional model-specific overrides
4. evaluation by model, not only by aggregate pooled results
5. explicit support for daily end-of-day refresh using previous-day data

## Initial grouping direction

Recommended first groups:

- `fundamental_slow`
- `trend_following`
- `defensive_allocation`

Each group should have its own:

- entry confirmation strictness
- exit persistence thresholds
- cooldown length
- tolerance for temporary overheat or pullback

## Validation rule

When evaluating a timing rule change, the review should answer:

1. Is this rule consistent with the mid- to long-horizon nature of the upstream model?
2. Does this rule fit the specific model family it is applied to?

If either answer is no, the rule should not become a default V1 rule.
