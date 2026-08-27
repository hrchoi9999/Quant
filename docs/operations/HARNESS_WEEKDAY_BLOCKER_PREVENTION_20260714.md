# Weekday Harness Blocker Prevention

date: 2026-07-14
run_id: 20260714_130438_prompt_weekday_20260713

## Incidents

### WD03 historical target versus newer current

- The requested EOD target was 2026-07-13 while live market current had advanced to a 2026-07-14 intraday publish.
- The old prompt attempted to restore current to the target date, which raced with the newer current producer and mixed `api_v1_*` and `quantservice_*` payload families.
- QuantMarket added separate `history` and `current` validation modes, endpoint coherence checks, cache-busted reads, and history-only publish support.

Prevention:

- Never roll live current back for a historical target.
- Reuse WD02 remote publish history evidence when it already exists.
- Validate the historical target from immutable history and validate live current coherence separately.
- Publish history-only only when target history evidence is missing.

### WD04 timebox interruption

- WD04 inherited the 10-minute default timebox even though the normal weekday `daily_light` rear chain requires roughly 20-25 minutes.
- The process was interrupted after user snapshot generation, leaving admin, AI governance, trading-sign, and contract validation incomplete.
- A targeted recovery completed the missing chain without rerunning strategy models.

Prevention:

- WD04 has a 30-minute stage timebox.
- The standard rear command and no-publish boundary are explicit in the prompt.
- If interrupted, resume only after the last successful timing-report command.
- Completion requires admin tracker, internal/AI governance current, trading-sign, daily contract, and user snapshot/history validation.

## Expected Effect

- WD03 should avoid duplicate publish and current rollback work.
- WD04 should finish in one uninterrupted run under normal operating duration.
- A partial failure should use targeted recovery instead of repeating completed model work.
