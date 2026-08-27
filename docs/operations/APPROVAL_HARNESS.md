# Approval Harness

기준일: 2026-06-27

## 위치

TASK_APPROVAL_HARNESS_01은 Agent Shadow Review와 Trend Review 이후 단계다.

목적은 사람이 승인/거절/보류/철회할 수 있는 파일 기반 approval gate를 만드는 것이다.

## 원칙

이번 단계는 `human_approval_only`다.

- 자동 승인 없음
- Agent 실행 권한 없음
- operational command 자동 실행 없음
- `approved_for_harness_execute` 생성 없음
- GCS publish / DB sync / Trading Sign / 실거래 없음

## 흐름

```text
approval readiness
→ approval request
→ manual decision
→ approval gate validation
→ approval packet
```

## 승인 Scope

허용:

- `single_stage_manual_pilot`
- `manual_operational_cycle_pilot`
- `manual_stage_execute`
- `manual_cycle_execute`

금지:

- `auto_execute`
- `auto_approval`
- `approved_for_harness_execute`
- `publish_automation`
- `trading_automation`

## 차단 원칙

- readiness가 `not_ready` 또는 `insufficient_data`면 request 차단
- high/critical risk 차단
- blocked pattern 차단
- rejected/deferred/revoked/expired decision은 gate 통과 불가

## 사용 예시

```powershell
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\build_approval_request.py --target-run-id 20260627_manual_weekday_cycle_dryrun --target-cycle-type weekday --approval-scope manual_operational_cycle_pilot
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\record_manual_approval_decision.py --approval-id <approval_id> --decision approved --decided-by manual --note "Approved for one manual cycle pilot."
D:\Quant\venv64\Scripts\python.exe D:\Quant\scripts\harness\validate_approval_gate.py --approval-id <approval_id> --target-run-id 20260627_manual_weekday_cycle_dryrun --execution-type manual_operational_cycle_pilot
```

## Execution 연동

TASK_APPROVAL_HARNESS_02부터 manual stage/cycle runner는 `--approval-id`를 받을 수 있다.

`--approval-id`가 있으면 execution 전에 approval resolution과 gate validation을 수행한다. gate가 `passed`가 아니면 command를 실행하지 않는다.
