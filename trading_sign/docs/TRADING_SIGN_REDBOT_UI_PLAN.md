# Trading Sign Redbot UI Plan

## Decision

`trading_sign` should not be introduced as a new top-level menu in Phase 1.

For the first release, it should be placed inside the existing `이번 주 모델 기준안` page as a separate model-level block.

Current public model scope:

- S strategy public models: `STABLE`, `BALANCED`, `GROWTH`
- discovery public models: `T_STOCK_DISCOVERY`, `T_ETF_DISCOVERY`
- `AUTO` is legacy/internal only and must not appear in public current or public UI

Recommended placement rule:

- keep `주간 기준안` content as the main block
- add `일간 신호` as a separate companion block under each model section
- do not mix weekly allocation data and daily timing-state rows in the same table

## Why this placement is preferred

### 1. The page intent already matches the user task

`이번 주 모델 기준안` is where users go to check the current model composition and current reference stance.

`trading_sign` is not a standalone research product in Phase 1.
It is a daily interpretation layer for the names already shown in the model guidance flow.

### 2. Weekly model guidance and daily timing signals have different time semantics

The weekly model block answers:

- what the current model is holding or recommending this week
- how the model is positioned at the weekly snapshot level

The daily signal block answers:

- how recommended or held names look as of the latest completed trading day
- whether the current state is `매수`, `보유`, `주의`, `매도`, or `매수 대기`

If both are merged into the same table, users may confuse:

- weekly recommendation
- daily timing state
- actual trade instruction

The UI should separate these concepts visually.

### 3. Separate blocks are operationally safer

The weekly model page and the daily timing block update on different cadences.

- weekly model guidance: weekly snapshot cadence
- daily timing signal: previous-trading-day end-of-day cadence

Separate blocks make it easier to show:

- different timestamps
- stale/fallback status
- different disclaimers
- temporary timing data delays without breaking the weekly block

### 4. A new top-level menu is premature for Phase 1

If `매매신호` becomes a top-level menu immediately, users may interpret it as a standalone trading instruction service.

That is not the intended positioning.
Phase 1 should keep the signal clearly attached to the existing public model-guidance workflow.

## Recommended page structure

For each model section inside `이번 주 모델 기준안`:

1. `주간 기준안` block
2. `일간 신호` block

The two blocks should be visually separated but sequentially connected.

Recommended order:

1. model identity and summary
2. weekly holdings / recommendation block
3. daily timing signal block
4. recent changes or explanation block

## Recommended block title

Use one of the following instead of a sharp trading-style title:

- `전일 종가 기준 일간 신호`
- `오늘 기준 점검`
- `일간 운용 신호`

Preferred title for Phase 1:

- `전일 종가 기준 일간 신호`

Reason:

- it clearly signals that the input cutoff is yesterday's completed trading day
- it reduces misunderstanding about intraday updates
- it feels more like a model-maintenance overlay than a direct trade command

## Recommended model-level layout

### A. Block header

The signal block header should contain:

- block title
- `data_asof_date`
- generated time
- short disclaimer

Recommended helper line:

- `이 신호는 전일 종가 기준으로 계산된 참고용 일간 점검 정보입니다.`

### B. Summary chip row

Show state counts first:

- `매수`
- `보유`
- `주의`
- `매도`
- `매수 대기`

This gives users a fast model-level read before looking at individual names.

### C. Split body by role

Inside the block, divide signals into two sections:

- `추천 종목 신호`
- `보유 종목 신호`

Reason:

- recommended names and held names answer different questions
- users can read candidate-entry and portfolio-maintenance signals separately
- this matches how `trading_sign` already tracks `is_recommended` and `is_held`

### D. Row content per stock

Each row should show:

- stock name
- ticker
- current state
- short reason summary
- latest state change date

Optional later fields:

- entry score
- exit risk score
- reason tags expansion

## Recommended visual hierarchy

The weekly model block should remain visually primary.
The daily signal block should be clearly visible, but secondary.

Design rule:

- weekly block = portfolio composition reference
- daily block = maintenance and check layer

The daily block should not visually dominate the model composition block in Phase 1.

## Recommended text framing

Avoid phrases that feel like direct orders.

Prefer:

- `상태`
- `기준`
- `점검`
- `해석`
- `참고`

Use cautiously:

- `매수`
- `매도`

When `매수` or `매도` is shown, surround it with context that keeps the service positioning clear.

Recommended note:

- `이 상태는 공개 규칙 기반 모델의 참고용 해석이며 특정 이용자에 대한 개별 매매 지시가 아닙니다.`

## Wireframe

```text
[모델 헤더]
모델명 / 위험도 / 요약 설명 / 주간 기준일

[주간 기준안]
- 현재 편입 종목 또는 자산
- 비중
- 이번 주 핵심 설명

[전일 종가 기준 일간 신호]
기준일: 2026-04-01 종가 / 생성: 2026-04-02 18:10 KST
이 신호는 전일 종가 기준으로 계산된 참고용 일간 점검 정보입니다.

[요약 칩]
매수 2 | 보유 16 | 주의 19 | 매도 0 | 매수 대기 0

[추천 종목 신호]
종목명 | 상태 | 이유 | 최근 변화일

[보유 종목 신호]
종목명 | 상태 | 이유 | 최근 변화일

[최근 변경/설명]
- 이번 주 편입 변화
- 기준 변화 이유
```

## Phase 1 recommendation

Phase 1 should use:

- no top-level `매매신호` menu
- no mixed table with weekly holdings data
- a separate daily timing block inside each model section on `이번 주 모델 기준안`

This gives the clearest user reading path:

1. see the weekly model stance
2. see the daily timing interpretation for recommended and held names
3. understand the latest state without confusing it with a direct advisory service

## Later expansion path

If the daily timing block proves useful and stable, Phase 2 can add:

- a dedicated detail page such as `timing briefing`
- homepage summary cards
- signal history drill-down

Even then, the model page block should remain the primary entry point.
