# QS Trading Sign Integration Request

## Request title

- `이번 주 모델 기준안` 페이지에 `trading_sign` 일간 신호 블록 추가

## Request date

- 2026-04-02

## Requesting thread

- `trading_sign`

## Target workspace or thread

- `D:\QuantService`
- QS thread

## Requested change

QS에서 `redbot.co.kr`의 `이번 주 모델 기준안` 페이지에 `trading_sign`의 일간 신호 블록을 추가해 주세요.

이번 요청의 핵심은 새로운 최상위 메뉴를 만드는 것이 아니라, 기존 모델 페이지 안에서 모델별 `주간 기준안` 아래에 별도의 `일간 신호` 블록을 추가하는 것입니다.

필요 작업 범위:

- `trading_sign` snapshot loader 추가
- `tradingsign_overview.json` / `tradingsign_model_detail.json` 로딩 경로 연결
- `이번 주 모델 기준안` 페이지에서 모델별 `ui_block` 렌더링
- stale/fallback 처리
- 공개 서비스용 문구와 비자문성 안내 문구 반영

## Current public exposure scope

이번 요청의 공개 대상 모델은 아래 3개 S 전략 모델입니다.

- `STABLE`
- `BALANCED`
- `GROWTH`

`AUTO`는 현재 공개 모델 체계에서 제외되었으므로, QS 공개 UI에서 다시 노출되면 안 됩니다.

## Why this is needed

현재 `trading_sign`는 추천 종목과 보유 종목에 대해 전일 종가 기준의 일간 상태를 계산하고 있습니다.

이 정보는 독립 서비스가 아니라 기존 공개 모델 기준안을 보완하는 해석 레이어이므로:

- 최상위 메뉴로 분리하기보다
- `이번 주 모델 기준안` 내부에서
- 모델별 주간 블록과 일간 점검 블록을 분리해 보여주는 구조

가 가장 적합합니다.

## Inputs from trading_sign

QS는 아래 thread-local 산출물을 읽으면 됩니다.

### Primary snapshot files

- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_overview.json`
- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_model_detail.json`
- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_manifest.json`

### Supporting docs

- `D:\Quant\trading_sign\docs\TRADING_SIGN_REDBOT_UI_PLAN.md`
- `D:\Quant\trading_sign\docs\TRADING_SIGN_V1_DESIGN.md`

## Snapshot contract summary

### Overview payload

`tradingsign_overview.json` contains:

- `asof`
- `generated_at`
- `summary.model_count`
- `summary.signal_count`
- `summary.state_counts`
- `summary.state_order`
- `models[]`

Use case:

- page-level summary
- model selector summary
- diagnostics or stale checks

### Detail payload

`tradingsign_model_detail.json` contains `models[]`, and each model item contains:

- `model_code`
- `model_name`
- `signal_date`
- `record_count`
- `state_counts`
- `ui_block`
- `signals`

QS should primarily use `ui_block` for rendering.

### ui_block fields

Each `ui_block` currently provides:

- `title`
- `description`
- `disclaimer`
- `signal_date`
- `data_asof_date`
- `generated_at`
- `state_chips[]`
- `sections[]`
- `profile_code`

### state_chips

`state_chips[]` is already ordered for UI use:

- `매수`
- `보유`
- `주의`
- `매도`
- `매수 대기`

### sections

`sections[]` is split into:

- `recommended` / `추천 종목 신호`
- `held` / `보유 종목 신호`

Each section contains:

- `record_count`
- `state_counts`
- `signals[]`

Each signal row contains:

- `ticker`
- `security_name`
- `current_state`
- `reason_summary`
- `latest_state_change_date`
- `entry_score`
- `exit_risk_score`

## Recommended UI placement

Target page:

- `이번 주 모델 기준안`

Placement rule:

- keep the existing weekly model guidance block as the primary block
- add the daily signal block under that weekly block
- keep it inside each model section
- do not merge weekly holdings data and daily timing rows into the same table

Recommended order inside each model section:

1. model header
2. weekly model guidance block
3. `전일 종가 기준 일간 신호` block
4. recent changes / explanation block

## Recommended block title and framing

Preferred title:

- `전일 종가 기준 일간 신호`

Helper text:

- `이 신호는 전일 종가 기준으로 계산된 참고용 일간 점검 정보입니다.`

Disclaimer:

- `이 상태는 공개 규칙 기반 모델의 참고용 해석이며 특정 이용자에 대한 개별 매매 지시가 아닙니다.`

## Rendering recommendation

For each model section:

- show header with `data_asof_date` and `generated_at`
- show one chip row using `ui_block.state_chips`
- render `추천 종목 신호` section
- render `보유 종목 신호` section

Recommended row columns:

- 종목명
- 상태
- 이유
- 최근 변화일

Optional later columns:

- ticker
- entry score
- exit risk score

## Stale and fallback handling

Recommended stale policy:

- daily timing block is fresh only when `generated_at` is within expected daily refresh window
- if `tradingsign_manifest.json` exists but detail payload is missing or stale, hide the block and show a soft fallback message

Recommended fallback text:

- `일간 신호 데이터가 아직 준비되지 않았습니다. 다음 갱신 후 다시 확인해 주세요.`

The weekly model guidance block should continue to render even if trading_sign data is unavailable.

## Non-goals for QS in this request

This request does not ask QS to implement:

- a new top-level `매매신호` menu
- a separate dedicated `timing briefing` page
- signal-history drill-down
- user-personalized trading instructions
- any change to the Quant or trading_sign calculation logic

## Expected output

QS should deliver:

- `이번 주 모델 기준안` page updated to render the `trading_sign` daily signal block per model
- loader or adapter for `trading_sign` snapshots
- safe stale/fallback behavior
- production-ready public rendering using the provided `ui_block` contract

## Acceptance criteria

- the page renders without breaking when trading_sign data exists
- weekly model guidance remains the primary visual block
- daily signal block appears as a separate companion block
- `매수 / 보유 / 주의 / 매도 / 매수 대기` chips render in the provided order
- `추천 종목 신호` and `보유 종목 신호` render separately
- if trading_sign data is stale or unavailable, the page still works and the timing block fails gracefully

## Constraints

- no direct edits by the `trading_sign` thread
- QS owns implementation inside `D:\QuantService`
- QS may adapt the loader and template structure to fit its existing architecture
- if QS needs additional fields, request them back through a new cross-thread request

## Handoff status

- draft
