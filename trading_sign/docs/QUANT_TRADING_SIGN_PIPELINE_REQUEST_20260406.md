# Quant Trading Sign Pipeline Integration Request

## Request title

- Quant daily pipeline에 `trading_sign` 자동 생성 및 웹 handoff 단계 추가

## Request date

- 2026-04-06

## Requesting thread

- `trading_sign`

## Target workspace or thread

- `D:\Quant`
- Quant model thread

## Requested change

Quant daily pipeline에서 데이터 업데이트와 백테스트가 끝난 뒤, `trading_sign` 일간 신호도 자동으로 생성하고 웹 전달 대상 current/handoff까지 함께 갱신되도록 파이프라인을 확장해 주세요.

이번 요청의 목적은:

- Quant 데이터가 갱신되면
- `trading_sign`도 같은 배치 안에서 자동 갱신되고
- 웹 쪽이 읽는 current/handoff 자산도 함께 최신화되는 것

입니다.

## Current public exposure scope

현재 공개 대상 모델 세트는 아래 5개입니다.

- `STABLE`
- `BALANCED`
- `GROWTH`
- `T_STOCK_DISCOVERY`
- `T_ETF_DISCOVERY`

`AUTO`는 과거 공개 체계의 잔존 레거시 코드일 수 있으나, 현재 공개 current 및 웹 노출 대상에는 포함되지 않습니다.

## Why this is needed

현재 `trading_sign`는 아래 입력을 읽어 일간 신호를 생성합니다.

- `D:\Quant\service_platform\web\public_data\current\user_model_snapshot_report.json`
- `D:\Quant\service_platform\web\public_data\current\user_recent_changes.json`
- `D:\Quant\service_platform\web\public_data\current\quantservice_tseries_discovery.json`
- `D:\Quant\data\db\price.db`
- `D:\Quant\data\db\fundamentals.db`

즉 `trading_sign`는 Quant의 daily pipeline 산출물에 종속됩니다.
그리고 공개 current 기준으로는 `stable / balanced / growth`와 T-series discovery만 사용해야 합니다.

현재는 수동 실행으로는 갱신할 수 있지만, 앞으로는 Quant 파이프라인이 성공적으로 끝났을 때 같은 배치 안에서 `trading_sign`도 자동 갱신되어야:

- S 전략 모델 페이지
- T-series 발굴 후보 페이지

에 필요한 일간 신호가 항상 최신 상태로 유지될 수 있습니다.

## Current relevant Quant pipeline flow

현재 `D:\Quant\src\quant_service\run_daily_quant_pipeline.py`와 문서 기준 기본 흐름은 대략 아래입니다.

1. data refresh
2. S2/S3/S4/S5/S6 backtests
3. router/profile reports
4. T-series shadow refresh
5. ingest
6. publish
7. web snapshots
8. canonical public current republish to GCS

관련 근거:

- `D:\Quant\src\quant_service\run_daily_quant_pipeline.py`
- `D:\Quant\service_platform\publishers\build_user_facing_snapshots.py`
- `D:\Quant\scripts\publish_public_current_to_gcs.py`
- `D:\Quant\docs\BACKTEST_COMMAND_20260311.md`

## Required integration point

`trading_sign` 단계는 아래 조건을 만족하는 위치에 들어가야 합니다.

- `build_user_facing_snapshots.py` 실행 이후
- T-series shadow refresh 이후
- remote current publish 이전

이유:

- `trading_sign`는 current public snapshot과 T-series discovery snapshot을 읽어야 함
- 따라서 upstream current snapshot이 먼저 준비되어야 함
- 그리고 그 결과를 웹 전달 대상으로 포함하려면 remote publish 이전에 생성되어야 함

권장 순서:

1. web snapshots 생성
2. `trading_sign` current snapshot 생성
3. `trading_sign` validation
4. canonical current publish / handoff

## Requested implementation details

### 1. Daily pipeline command 추가

`D:\Quant\src\quant_service\run_daily_quant_pipeline.py`의 command builder에 `trading_sign` 단계 추가를 요청합니다.

권장 방식:

- 새로운 command group 예: `trading_sign_cmds`
- 이 그룹을 `web_snapshot_cmds` 다음, `remote_publish_cmds` 이전에 실행

권장 실행 커맨드 예시:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\trading_sign\scripts\run_daily_public_signals.py --signal-date {asof} --data-asof-date {asof}
```

기본 해석:

- Quant pipeline의 `--asof`는 최신 확정 데이터 기준일
- `trading_sign`도 같은 기준일로 current snapshot을 생성

예:

- Quant asof = `2026-04-03`
- trading_sign signal_date = `2026-04-03`
- trading_sign data_asof_date = `2026-04-03`

## 2. Optional wrapper script 추가

직접 외부 workspace script를 호출하는 대신, Quant 쪽에 얇은 wrapper를 두는 것도 허용 가능합니다.

예시:

- `D:\Quant\scripts\run_trading_sign_from_quant_pipeline.py`

wrapper 책임:

- `D:\Quant\trading_sign` 경로 존재 여부 확인
- `run_daily_public_signals.py` 호출
- 실패 시 명확한 로그 출력

장점:

- Quant pipeline 내부 command가 더 읽기 쉬워짐
- 향후 파라미터나 handoff 경로 변경 시 wrapper만 수정 가능

## 3. Validation step 추가

`trading_sign` 생성 이후 간단한 validation step 추가를 요청합니다.

최소 검증 대상:

- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_overview.json`
- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_model_detail.json`
- `D:\Quant\trading_sign\service_platform\web\public_data\current\tradingsign_manifest.json`

최소 검증 항목:

- 파일 존재 여부
- asof 일치 여부
- model count > 0 여부
- JSON parse 가능 여부

가능하면 별도 스크립트 예:

- `D:\Quant\scripts\validate_trading_sign_snapshots.py`

## 4. Web handoff / publish 반영

`trading_sign`는 current snapshot 생성만으로 끝나면 안 되고, 웹 쪽이 읽을 수 있는 전달 경로까지 포함되어야 합니다.

권장 옵션은 아래 둘 중 하나입니다.

### Option A. canonical current publish에 trading_sign 파일 포함

`D:\Quant\scripts\publish_public_current_to_gcs.py`를 확장해서 `trading_sign` current 파일도 함께 publish하도록 요청합니다.

권장 publish 대상:

- `tradingsign_overview.json`
- `tradingsign_model_detail.json`
- `tradingsign_manifest.json`

권장 object path 예:

- `trading_sign/current/tradingsign_overview.json`
- `trading_sign/current/tradingsign_model_detail.json`
- `trading_sign/current/tradingsign_manifest.json`

이 방식이 가능하면 가장 깔끔합니다.

### Option B. shared handoff current 디렉터리로 copy

만약 기존 GCS current publish 구조에 바로 포함하기 어렵다면, 최소한 QS가 안정적으로 읽을 수 있는 shared handoff current 경로로 copy하는 단계라도 추가해 주세요.

예:

- `D:\Quant\service_platform\web\public_data\handoff\trading_sign\current\...`

권장 결론:

- 가능하면 Option A
- 어려우면 Phase 1은 Option B라도 먼저 구축

## 5. Daily batch checklist / docs 갱신

Quant 문서에도 `trading_sign` 단계가 기본 daily pipeline 일부임을 반영해 주세요.

대상 후보:

- `D:\Quant\docs\BACKTEST_COMMAND_20260311.md`
- `D:\Quant\docs\DAILY_QUANT_BATCH_CHECKLIST_20260320.md`

반영 내용:

- daily pipeline flow에 `trading_sign` 추가
- 장애 시 재실행 runbook 추가
- handoff/publish 확인 항목 추가

## Inputs from trading_sign

Quant thread는 아래를 참고하면 됩니다.

### Script

- `D:\Quant\trading_sign\scripts\run_daily_public_signals.py`

### Output directory

- `D:\Quant\trading_sign\service_platform\web\public_data\current`

### Output files

- `tradingsign_overview.json`
- `tradingsign_model_detail.json`
- `tradingsign_manifest.json`

### Supporting docs

- `D:\Quant\trading_sign\docs\TRADING_SIGN_V1_DESIGN.md`
- `D:\Quant\trading_sign\docs\TRADING_SIGN_REDBOT_UI_PLAN.md`
- `D:\Quant\trading_sign\docs\QS_TRADING_SIGN_INTEGRATION_REQUEST_20260402.md`
- `D:\Quant\trading_sign\docs\QS_TSERIES_TRADING_SIGN_REQUEST_20260402.md`

## Expected output

Quant thread should deliver:

- daily pipeline에서 trading_sign 자동 생성
- validation step 포함
- web handoff 또는 canonical publish 반영
- docs/checklist 갱신

## Acceptance criteria

- Quant daily pipeline 성공 시 trading_sign current snapshot도 자동 갱신된다
- pipeline 순서상 upstream web snapshots 이후에 trading_sign가 실행된다
- trading_sign snapshot validation이 추가된다
- 웹 쪽이 읽을 수 있는 current/handoff 경로가 자동 갱신된다
- pipeline 문서와 체크리스트에 trading_sign 단계가 반영된다

## Constraints

- no direct edits by the `trading_sign` thread
- Quant thread owns implementation inside `D:\Quant`
- if Quant thread needs additional parameters or schema changes from trading_sign, send a return request

## Handoff status

- draft
