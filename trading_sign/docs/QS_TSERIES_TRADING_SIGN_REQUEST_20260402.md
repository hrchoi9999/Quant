# QS T-Series Trading Sign Integration Request

## Request title

- T-series 발굴 후보 페이지에 `trading_sign` 일간 신호 블록 추가

## Request date

- 2026-04-02

## Requesting thread

- `trading_sign`

## Target workspace or thread

- `D:\QuantService`
- QS thread

## Requested change

QS에서 T-series 발굴 후보 페이지에도 `trading_sign`의 일간 신호 정보를 함께 보여주도록 반영해 주세요.

이번 요청은 기존 `이번 주 모델 기준안` 반영 요청과 별개로, T-series 후보를 보여주는 페이지 또는 섹션에 맞춘 추가 요청입니다.

필요 작업 범위:

- T-series 발굴 후보 화면에서 `T_STOCK_DISCOVERY`, `T_ETF_DISCOVERY`용 `trading_sign` 데이터 로딩
- 후보 리스트와 일간 신호 상태를 함께 보여주는 별도 블록 또는 컬럼 추가
- stale/fallback 처리
- 공개 서비스용 참고 문구와 비자문성 문구 반영

## Current public exposure scope

이번 요청의 공개 대상 discovery 모델은 아래 2개입니다.

- `T_STOCK_DISCOVERY`
- `T_ETF_DISCOVERY`

공개 S 전략 모델은 별도 요청서 기준 `STABLE / BALANCED / GROWTH` 3개이며, `AUTO`는 현재 공개 모델 체계에서 제외되었습니다.

## Why this is needed

현재 `trading_sign`는 S 전략 계열뿐 아니라 T-series 발굴 후보에 대해서도 일간 신호를 이미 생성하고 있습니다.

하지만 웹 노출은 아직 `이번 주 모델 기준안` 중심으로만 요청되어 있어, T-series 페이지에서는 사용자가 발굴 후보는 보되 해당 종목의 현재 `매수 / 주의 / 매수 대기` 같은 상태를 함께 확인할 수 없습니다.

T-series는 성격상 "발굴 후보" 화면에서 바로 현재 상태를 함께 보는 것이 더 자연스럽기 때문에, 해당 페이지에도 신호 정보를 연결하는 것이 필요합니다.

## Inputs from trading_sign

QS는 아래 산출물을 읽으면 됩니다.

### Primary snapshot files

- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_overview.json`
- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_model_detail.json`
- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_manifest.json`

### Relevant model codes

- `T_STOCK_DISCOVERY`
- `T_ETF_DISCOVERY`

### Supporting docs

- `D:\Quant\trading_sign\docs\TRADING_SIGN_REDBOT_UI_PLAN.md`
- `D:\Quant\trading_sign\docs\TRADING_SIGN_V1_DESIGN.md`

## Snapshot contract summary for T-series

QS는 `tradingsign_model_detail.json`의 아래 모델 항목을 사용하면 됩니다.

- `model_code = T_STOCK_DISCOVERY`
- `model_code = T_ETF_DISCOVERY`

각 모델 항목에는 다음이 포함됩니다.

- `model_code`
- `model_name`
- `signal_date`
- `record_count`
- `state_counts`
- `ui_block`
- `signals`

QS는 가능하면 `ui_block`을 우선 사용해 주세요.

### ui_block fields

`ui_block`에는 아래 정보가 준비되어 있습니다.

- `title`
- `description`
- `disclaimer`
- `signal_date`
- `data_asof_date`
- `generated_at`
- `state_chips[]`
- `sections[]`
- `profile_code`

### Sections for T-series

T-series는 대부분 `추천 종목 신호` 중심으로 보게 될 가능성이 높습니다.

`sections[]`에는 기본적으로 아래 두 구간이 들어 있습니다.

- `recommended` / `추천 종목 신호`
- `held` / `보유 종목 신호`

T-series 페이지에서는 보통 `recommended` 섹션이 주요 렌더링 대상입니다.

각 signal row에는 아래 필드가 있습니다.

- `ticker`
- `security_name`
- `current_state`
- `reason_summary`
- `latest_state_change_date`
- `entry_score`
- `exit_risk_score`

## Recommended UI placement

Target area:

- T-series 발굴 후보 페이지
- 또는 QS 내 T-series 후보를 렌더링하는 기존 섹션

권장 방식은 두 가지 중 하나입니다.

### Option A. 후보 리스트 아래 별도 `일간 신호` 블록 추가

권장안입니다.

- 기존 발굴 후보 리스트는 유지
- 그 아래 `전일 종가 기준 일간 신호` 블록 추가
- `추천 종목 신호` 중심으로 상태와 이유를 별도 노출

장점:

- 기존 후보 표를 크게 흔들지 않음
- 주간/발굴 후보 정보와 일간 상태를 시각적으로 분리 가능
- 사용자 해석이 더 명확함

### Option B. 기존 후보 표에 상태 컬럼 추가

보조안입니다.

- 후보 표에 `상태`와 `이유` 일부를 추가

단점:

- 표가 복잡해질 수 있음
- 일간 신호와 후보 선정을 같은 층위로 오해할 수 있음

권장 결론:

- Phase 1에서는 `별도 신호 블록` 방식이 더 적합함

## Recommended block title and framing

Preferred title:

- `전일 종가 기준 일간 신호`

Helper text:

- `이 신호는 전일 종가 기준으로 계산된 참고용 일간 점검 정보입니다.`

Disclaimer:

- `이 상태는 공개 규칙 기반 모델의 참고용 해석이며 특정 이용자에 대한 개별 매매 지시가 아닙니다.`

## Rendering recommendation

T-series 페이지에서는 아래 순서를 권장합니다.

1. T-series 후보 설명 또는 후보 리스트
2. `전일 종가 기준 일간 신호` 블록
3. 필요시 모델 설명 또는 주의 문구

Recommended row columns:

- 종목명
- 상태
- 이유
- 최근 변화일

Optional later columns:

- ticker
- entry score
- exit risk score

If QS wants a compact rendering:

- 1차는 `추천 종목 신호`만 우선 노출
- `보유 종목 신호`는 데이터가 있을 때만 조건부 렌더링

## Stale and fallback handling

Recommended stale policy:

- T-series 신호 블록은 `generated_at` 기준으로 일간 신호 freshness를 판단
- payload가 없거나 stale이면 블록을 숨기고 fallback 문구 표시

Recommended fallback text:

- `T-series 일간 신호 데이터가 아직 준비되지 않았습니다. 다음 갱신 후 다시 확인해 주세요.`

기존 T-series 후보 리스트는 trading_sign 데이터가 없어도 계속 렌더링되어야 합니다.

## Non-goals for QS in this request

이번 요청은 아래를 포함하지 않습니다.

- 새로운 최상위 `매매신호` 메뉴 추가
- T-series 전용 별도 독립 페이지 신설
- signal history drill-down
- 개인화 매매 지시 기능
- Quant 또는 trading_sign 계산 로직 수정

## Expected output

QS should deliver:

- T-series 발굴 후보 페이지에서 `trading_sign` 상태 확인 가능
- `T_STOCK_DISCOVERY`, `T_ETF_DISCOVERY` 신호 로딩 연결
- 별도 일간 신호 블록 또는 이에 준하는 명확한 UI 반영
- stale/fallback 처리

## Acceptance criteria

- T-series 후보 페이지에서 trading_sign 데이터가 존재할 때 신호 블록이 렌더링된다
- `추천 종목 신호`가 우선적으로 잘 보인다
- `매수 / 보유 / 주의 / 매도 / 매수 대기` 상태가 제공 순서대로 렌더링된다
- 기존 후보 정보와 일간 신호가 혼동되지 않도록 시각적으로 분리된다
- trading_sign 데이터가 없거나 stale이어도 기존 페이지는 정상 동작한다

## Constraints

- no direct edits by the `trading_sign` thread
- QS owns implementation inside `D:\QuantService`
- QS may adapt the final component structure to fit its existing T-series page architecture
- if additional fields are needed, request them back through a new cross-thread request

## Handoff status

- draft
