# AI Overlay Shadow Policy Review Principle - 2026-05-17

## Purpose

Define the operating principle for reviewing AI overlay policy maps before any production strategy-model application.

## Current Status

- Scope: S/T/I strategy models and user-facing model overlays
- Current stage: admin-only shadow tracking
- Live recommendation application: disabled
- Shadow tracking start date: 2026-05-12
- Current policy map basis: initial backtest/ablation champion policy by model

## Review Principle

AI overlay scores and tags may be monitored daily, but policy changes must not be made from daily noise.

Policy-map changes require enough forward-performance observations to evaluate return and risk impact.

## Review Cadence

| Cadence | Purpose | Policy Change Decision |
|---|---|---|
| Daily | Payload health, score/tag drift, abnormal concentration check | No |
| Weekly | Directional baseline vs overlay monitoring | No, except critical data error |
| 1M+ | First formal policy review | Yes, limited review |
| 8W+ | Policy maintain/modify/hold decision | Yes |
| 12W+ | Production application candidate review | Yes, if robust |

## First Formal Review Date

- Shadow tracking start: 2026-05-12
- Minimum elapsed period: 1 month
- First eligible policy review date: 2026-06-12 or later

## Review Metrics

The first review must compare baseline and AI overlay by model using:

- Average period return
- Compounded return
- Win rate
- MDD / worst period return
- Downside period rate
- Risk-tag concentration
- Stability of the selected policy across weeks

## Current Policy Change Rule

Until 2026-06-12:

- Do not change model-level AI overlay policy maps based on daily results.
- Continue daily score/tag/payload generation.
- Continue weekly monitoring.
- Only fix data, payload, or implementation errors.

After 2026-06-12:

- Review whether each model keeps, modifies, or suspends its current policy.
- S3_ACCEL_V01 and I-STOCK require special attention because current shadow evidence is weaker or risk tradeoff is not clean.

## Production Application Rule

AI overlay remains shadow-only until a separate production adoption decision is documented.

Production application requires:

- At least 8 weeks of stable shadow evidence, preferably 12 weeks
- Return improvement over baseline
- No material MDD deterioration
- Clear model-specific policy rationale
- QS web/admin display readiness
- Explicit approval before public recommendation impact
