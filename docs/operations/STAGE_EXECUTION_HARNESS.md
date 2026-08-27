# Stage Execution Harness

기준일: 2026-06-27

## 목적

1차 Update Pipeline Harness가 만든 단계 정의와 handoff 흐름 위에, stage별 command 실행 어댑터를 붙인다.

이번 범위는 안전한 실행 기록 장치다. LLM Agent, LangChain, LangGraph, 자동매매, 자동배포, GCS publish 자동 실행은 포함하지 않는다.

## 1차 Harness와 차이

- 1차 Harness: workflow 상태, handoff 지시문, 다음 thread 안내
- 2차 Execution Harness: diagnostic-only 보조 장치. stage command dry-run, safe echo, preflight, 결과/로그 수집만 담당

## 설정 파일

- `D:\Quant\config\harness\stage_commands.yaml`
- `D:\Quant\config\harness\stage_commands_operational.yaml`
- `D:\Quant\config\harness\stage_command_risk_policy.yaml`
- `D:\Quant\config\harness\thread_roles.yaml`
- `D:\Quant\config\harness\update_pipeline_weekday.yaml`
- `D:\Quant\config\harness\update_pipeline_weekend.yaml`

초기 command는 모두 `scripts/harness/safe_echo.py` placeholder다. 실제 Quant 운영 command는 추후 명시적으로 연결한다.

운영 후보 command는 `stage_commands_operational.yaml`에 분리한다. 이 파일은 기본 실행 config가 아니며, 명시적으로 `--config`를 줄 때만 사용한다.

운영 orchestration의 primary는 prompt handoff harness다. 운영 후보 command는 prompt 기반 작업요청 범위와 일치할 때만 등록한다. 기존 직접 지시보다 범위가 넓어지는 command는 `command: null`, `command_status: manual_prompt_only`로 두고 command harness 실행 후보에서 제외한다.

Thread root는 `thread_roles.yaml` 기준으로 검증한다.

## 실행 모드

기본값은 dry-run이다.

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\run_stage.py --run-id 20260627_weekday --stage-id WD01_QUANT_FRONT --dry-run
```

safe execute:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\run_stage.py --run-id 20260627_weekday --stage-id WD01_QUANT_FRONT --execute
```

운영 후보 dry-run:

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\run_stage.py --run-id 20260627_weekday --stage-id WD01_QUANT_FRONT --dry-run --config D:\Quant\config\harness\stage_commands_operational.yaml
```

## safe_run 정책

`--execute`를 명시해도 아래 조건을 모두 만족해야 실제 실행한다.

- `safe_run: true`
- `risk_level: low` 또는 `medium`
- operational config에서는 `command_status: approved_for_harness_execute`
- blocked pattern 미매칭
- command가 비어 있지 않음
- stage_id가 `stage_commands.yaml`에 존재
- command_status가 `manual_prompt_only`가 아님

TASK 03에서는 operational command를 `approved_for_harness_execute`로 승격하지 않으므로 실제 운영 command execute는 차단된다.

## Thread File Alignment Audit

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\audit_thread_file_alignment.py
```

감사 항목:

- stage thread와 `working_dir`가 `thread_roles.yaml` root와 일치하는지
- command가 등록되어 있는지
- Python/PowerShell entrypoint가 실제 존재하는지
- safe placeholder가 thread root 변경 후에도 절대경로로 실행 가능한지

## Cycle Runner 연동

`run_update_cycle.py`는 각 stage 실행에 `run_stage.py`를 재사용한다.

- dry-run cycle: `run_stage.py --dry-run`
- execute-safe cycle: `run_stage.py --execute`
- operational config execute-safe: 정책상 차단

Cycle 종료 후 `cycle_summary.md`와 `final_summary.md`가 생성된다.

## risk_level 정책

- `low`: 실행 가능
- `medium`: 실행 가능
- `high`: 차단
- `critical`: 차단

초기 설정은 safe echo만 `low`로 등록한다.

## blocked 조건

아래 경우 `status=blocked`로 기록한다.

- `safe_run=false`
- `risk_level=high`
- `risk_level=critical`
- command 공백
- `command_status=manual_prompt_only`
- stage 설정 없음

실패 또는 blocked 상태에서는 다음 stage 자동 진행을 하지 않는다.

## 저장 구조

각 stage 결과는 아래에 저장한다.

```text
D:\Quant\reports\harness_runs\<run_id>\<stage_id>\
```

생성 파일:

- `command.txt`
- `stdout.log`
- `stderr.log`
- `result.json`
- `artifact_validation.json`
- `handoff.md`

## run_state.json 반영

`D:\Quant\reports\harness_runs\<run_id>\run_state.json`이 이미 있으면 `run_stage.py`가 호환 방식으로 stage 항목을 갱신한다.

반영 필드:

- `stage.status`
- `stage.started_at`
- `stage.completed_at`
- `stage.validation_result`
- `stage.known_issues`
- `stage.handoff_file`

`dry_run_completed`는 실제 다음 단계 진행 허용 상태가 아니다. 실제 진행은 `completed` 또는 `validated` 기준으로 본다.
