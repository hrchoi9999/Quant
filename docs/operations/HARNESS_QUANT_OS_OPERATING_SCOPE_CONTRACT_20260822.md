# Harness Quant OS Operating Scope Contract

## Current decision

- The active harness scope remains the legacy Quant 1.0 canonical scope.
- `operating_model_version` remains as a compatibility label only.
- Operating authority is moving to resolved `model_code` plus `operating_revision` from an approved Quant OS manifest.
- This compatibility layer is inactive and read-only. It does not change code, DB, current payloads, public payloads, or GCS objects.

## Impact analysis

The old global boundary was duplicated in:

- `config/harness/prompt_handoff_stages.yaml` top-level defaults and WD04/WE01 instructions.
- `config/harness/model_scope_registry.yaml` version boundary.
- `scripts/harness/prompt_handoff_cycle.py` initial state and prompt rendering.
- Prompt and governance tests that asserted the Quant 1.0-only text.

WD01-WD07/WE01 stage topology, report advancement, publish approval gates, and WE01 parent PID/asof process protection are outside this change.

## Manifest contract

The future authority file is:

`D:/Quant/reports/quant_os/operating_scope/approved_operating_manifest.json`

Activation requires all of the following:

1. Harness contract is changed to `resolution_mode=quant_os_manifest` and `activation_state=active` in the same approved change.
2. Manifest schema is version 1, `scope_id` is non-empty, type is `quant_os_operating_scope`, and status is `approved_8_of_8`.
3. Exactly eight required model codes are present and individually approved.
4. Every model has an `operating_revision`; adopted candidates also have `source_candidate_id`.
5. Final user approval is true and has a non-empty approval reference.
6. `T-STOCK-V01` is pinned to `keep_current_revision` and `quant_1_0_canonical`.
7. S2, S3, S3_CORE2, S3_ACCEL_V01, S4, S5, and S6 have live shadow evidence from the 2026-08-22 freeze for at least 180 calendar days.
8. Weekly candidates have at least 26 decisions; monthly candidates have at least 6 decisions.
9. Every candidate has passed its predefined return, MDD, volatility, and turnover risk gates with a recorded evidence path.

The earliest possible review date is `2027-02-18`. This date alone is not sufficient; missing data, decisions, or risk evidence extends the review window.

## Parallel performance observation

- WE01 reads the frozen Quant 1.2 shadow evidence and compares each candidate with the same-model Quant 1.0 canonical baseline.
- Quant 1.2 candidate logic, parameters, universe-selection rules, scoring, rebalancing, and risk rules are immutable. The freeze manifest fingerprints candidate code, selected configuration, and shadow execution logic.
- Any fingerprint mismatch invalidates the affected Quant 1.2 comparison. An output-affecting proposal must become a separate Quant 1.3 candidate and cannot reset or overwrite the existing Quant 1.2 shadow.
- Routine input-data refresh, reproducible runs, performance records, and non-semantic monitoring or harness changes remain allowed.
- The comparison reports total return, MDD, annual volatility, average turnover, candidate-minus-baseline deltas, elapsed days, decision count, and risk gate status.
- Missing live metrics are reported as `waiting_live_metrics`; historical research backtests are not substituted.
- The comparison is governance-only and has no effect on operating scope, current/admin/public payloads, portfolio attribution, or GCS publish.
- Output is stored in `reports/harness_model_governance/<run_id>/model_governance_review.json` under `quant_1_2_vs_quant_1_0_live_comparison`.

Any missing or invalid condition resolves to the current legacy scope.

`reports/quant1_2/operational_readiness/selection_freeze_manifest.json` remains a read-only research observation. Its `research_only=true` and `operating_mutation=false` state cannot authorize activation.

## Activation checklist

- After at least six months of live shadow, Quant OS emits the approved 8/8 operating manifest using the contract above.
- The manifest records per-model elapsed days, decision count, risk gate result, and risk evidence path.
- Quant Model verifies model code aliases and the exact canonical in-place revisions.
- User gives final activation approval and its reference is recorded in the manifest.
- Harness scope dry-run reports `manifest_activation_eligible=true` before config activation.
- Regression tests pass for WD04, WE01, report quality, stage order, publish gates, and process ownership protection.
- The contract mode/state switch and Quant OS canonical model change are applied in one controlled window.
- One weekday dry-run and one weekend governance dry-run confirm the resolved model list before any publish.

## Rollback

1. Set `resolution_mode=legacy_static` and `activation_state=inactive`.
2. Run `scope-dry-run` and verify `active_scope_source=model_scope_registry_legacy` with all revisions `quant_1_0_canonical`.
3. Roll back canonical model revisions using the Quant OS rollback package; do not change model codes.
4. Re-run existing WD04/WE01 prompt tests and pre-GCS validation before the next publish.

The harness rollback does not delete the approved manifest or research evidence. It only stops that manifest from being an active scope authority.
