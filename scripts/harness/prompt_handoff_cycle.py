from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

from harness_common import ROOT, now_stamp, read_json, read_yaml, write_json

CONFIG_PATH = ROOT / "config" / "harness" / "prompt_handoff_stages.yaml"
MODEL_SCOPE_REGISTRY_PATH = ROOT / "config" / "harness" / "model_scope_registry.yaml"
RUN_ROOT = ROOT / "reports" / "prompt_handoff_runs"
CLOSE_SUFFIX = "_HARNESS_CLOSE"


def _token(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace(" ", "_")


def _default_run_id(cycle: str, asof: str) -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_prompt_{cycle}_{_token(asof)}"


def _config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    data = read_yaml(path)
    cfg = data.get("prompt_handoff")
    if not isinstance(cfg, dict):
        raise SystemExit(f"missing prompt_handoff config: {path}")
    return cfg


def _scope_registry(path: Path = MODEL_SCOPE_REGISTRY_PATH) -> dict[str, Any]:
    data = read_yaml(path)
    registry = data.get("model_scope_registry")
    if not isinstance(registry, dict):
        raise SystemExit(f"missing model_scope_registry config: {path}")
    return registry


def _normalize_model_code(value: Any, aliases: dict[str, str]) -> str:
    code = str(value or "").strip()
    return aliases.get(code, code)


def _read_json_diagnostic(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "manifest_missing"
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"manifest_invalid_json:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return None, "manifest_root_not_mapping"
    return payload, None


def resolve_operating_scope(
    registry_path: Path = MODEL_SCOPE_REGISTRY_PATH,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve the operating model scope without mutating operating artifacts."""
    registry = _scope_registry(registry_path)
    contract = registry.get("operating_scope_contract") or {}
    if not isinstance(contract, dict):
        contract = {}
    manifest_contract = contract.get("quant_os_manifest") or {}
    if not isinstance(manifest_contract, dict):
        manifest_contract = {}
    aliases = {
        str(key): str(value)
        for key, value in (manifest_contract.get("model_code_aliases") or {}).items()
    }
    required_codes = [
        _normalize_model_code(item, aliases)
        for item in manifest_contract.get("required_model_codes") or []
    ]
    contract_blockers: list[str] = []
    required_count_value = int(manifest_contract.get("required_model_count") or 0)
    if contract.get("fail_closed") is not True:
        contract_blockers.append("scope_contract_not_fail_closed")
    if not manifest_contract.get("manifest_type"):
        contract_blockers.append("required_manifest_type_missing")
    if not isinstance(manifest_contract.get("required_schema_version"), int):
        contract_blockers.append("required_manifest_schema_version_missing")
    if not manifest_contract.get("required_status"):
        contract_blockers.append("required_manifest_status_missing")
    if not required_codes or len(set(required_codes)) != len(required_codes):
        contract_blockers.append("required_model_codes_invalid")
    if required_count_value != len(required_codes):
        contract_blockers.append("required_model_count_contract_mismatch")
    live_gate = manifest_contract.get("live_shadow_gate") or {}
    if not isinstance(live_gate, dict):
        live_gate = {}
    candidate_requirements = live_gate.get("candidate_requirements") or {}
    if not isinstance(candidate_requirements, dict):
        candidate_requirements = {}
    pinned_models = manifest_contract.get("pinned_models") or {}
    expected_candidate_codes = set(required_codes) - set(pinned_models)
    if set(candidate_requirements) != expected_candidate_codes:
        contract_blockers.append("live_shadow_candidate_set_mismatch")
    try:
        frozen_date = date.fromisoformat(str(live_gate.get("frozen_asof") or ""))
        earliest_review_date = date.fromisoformat(str(live_gate.get("earliest_review_date") or ""))
    except ValueError:
        frozen_date = None
        earliest_review_date = None
        contract_blockers.append("live_shadow_contract_date_invalid")
    minimum_calendar_days = int(live_gate.get("minimum_calendar_days") or 0)
    if minimum_calendar_days < 180:
        contract_blockers.append("live_shadow_minimum_calendar_days_below_180")
    if (
        frozen_date is not None
        and earliest_review_date is not None
        and (earliest_review_date - frozen_date).days < minimum_calendar_days
    ):
        contract_blockers.append("earliest_review_date_before_minimum_live_window")
    for code, requirement in candidate_requirements.items():
        if not isinstance(requirement, dict):
            contract_blockers.append(f"live_shadow_requirement_invalid:{code}")
            continue
        cadence = requirement.get("cadence")
        minimum_decisions = int(requirement.get("minimum_decision_count") or 0)
        if cadence == "weekly" and minimum_decisions < 26:
            contract_blockers.append(f"weekly_decision_gate_below_26:{code}")
        if cadence == "monthly" and minimum_decisions < 6:
            contract_blockers.append(f"monthly_decision_gate_below_6:{code}")
    legacy_codes = [
        str(item)
        for item in ((registry.get("strategy_models") or {}).get("active_operational") or [])
    ]
    legacy = contract.get("legacy_compatibility") or {}
    legacy_revision = str(legacy.get("operating_revision") or "quant_1_0_canonical")
    legacy_models = [
        {"model_code": code, "operating_revision": legacy_revision, "decision": "keep_current_revision"}
        for code in legacy_codes
    ]

    configured_path = manifest_contract.get("path")
    resolved_manifest_path = manifest_path or (Path(str(configured_path)) if configured_path else None)
    manifest: dict[str, Any] | None = None
    manifest_error: str | None = None
    if resolved_manifest_path is None:
        manifest_error = "manifest_path_not_configured"
    else:
        manifest, manifest_error = _read_json_diagnostic(resolved_manifest_path)

    manifest_blockers: list[str] = []
    if manifest_error:
        manifest_blockers.append(manifest_error)
    manifest_models: list[dict[str, str]] = []
    if manifest is not None:
        if manifest.get("schema_version") != manifest_contract.get("required_schema_version"):
            manifest_blockers.append("manifest_schema_version_mismatch")
        if not str(manifest.get("scope_id") or "").strip():
            manifest_blockers.append("manifest_scope_id_missing")
        if manifest.get("manifest_type") != manifest_contract.get("manifest_type"):
            manifest_blockers.append("manifest_type_not_approved_operating_scope")
        if manifest.get("status") != manifest_contract.get("required_status"):
            manifest_blockers.append("manifest_status_not_approved_8_of_8")
        if manifest.get("research_only") is True:
            manifest_blockers.append("research_only_manifest_forbidden")
        if bool(manifest.get("operating_mutation_allowed")) is not True:
            manifest_blockers.append("operating_mutation_not_allowed")

        approval = manifest.get("approval") or {}
        if not isinstance(approval, dict):
            approval = {}
        required_count = required_count_value
        if approval.get("approved_model_count") != required_count:
            manifest_blockers.append("approved_model_count_mismatch")
        if approval.get("total_model_count") != required_count:
            manifest_blockers.append("total_model_count_mismatch")
        if approval.get("user_final_approval") is not True:
            manifest_blockers.append("user_final_approval_missing")
        if not str(approval.get("user_approval_reference") or "").strip():
            manifest_blockers.append("user_approval_reference_missing")

        raw_models = manifest.get("models") or {}
        if not isinstance(raw_models, dict):
            raw_models = {}
            manifest_blockers.append("manifest_models_not_mapping")
        normalized_rows: dict[str, dict[str, Any]] = {}
        for key, value in raw_models.items():
            if not isinstance(value, dict):
                manifest_blockers.append(f"model_row_not_mapping:{key}")
                continue
            code = _normalize_model_code(value.get("model_code") or key, aliases)
            if code in normalized_rows:
                manifest_blockers.append(f"duplicate_model_code:{code}")
                continue
            normalized_rows[code] = value
        if set(normalized_rows) != set(required_codes):
            manifest_blockers.append("required_model_code_set_mismatch")

        allowed_decisions = {str(item) for item in manifest_contract.get("allowed_decisions") or []}
        for code in required_codes:
            row = normalized_rows.get(code)
            if row is None:
                continue
            decision = str(row.get("decision") or "")
            revision = str(row.get("operating_revision") or "").strip()
            if row.get("approval_status") != "approved":
                manifest_blockers.append(f"model_not_approved:{code}")
            if decision not in allowed_decisions:
                manifest_blockers.append(f"model_decision_invalid:{code}")
            if not revision:
                manifest_blockers.append(f"operating_revision_missing:{code}")
            source_candidate_id = str(row.get("source_candidate_id") or "").strip()
            if decision == "adopt_candidate_revision" and not source_candidate_id:
                manifest_blockers.append(f"source_candidate_id_missing:{code}")
            pin = pinned_models.get(code) or {}
            if pin and decision != pin.get("required_decision"):
                manifest_blockers.append(f"pinned_model_decision_mismatch:{code}")
            if pin and revision != pin.get("required_revision"):
                manifest_blockers.append(f"pinned_model_revision_mismatch:{code}")
            live_requirement = candidate_requirements.get(code)
            if isinstance(live_requirement, dict):
                live_evidence = row.get("live_shadow_evidence") or {}
                if not isinstance(live_evidence, dict):
                    live_evidence = {}
                if live_evidence.get("frozen_asof") != live_gate.get("frozen_asof"):
                    manifest_blockers.append(f"live_shadow_freeze_mismatch:{code}")
                try:
                    evidence_date = date.fromisoformat(
                        str(live_evidence.get("evidence_asof") or "")
                    )
                except ValueError:
                    evidence_date = None
                    manifest_blockers.append(f"live_shadow_evidence_asof_invalid:{code}")
                actual_calendar_days = int(live_evidence.get("calendar_days") or 0)
                if actual_calendar_days < minimum_calendar_days:
                    manifest_blockers.append(f"live_shadow_calendar_days_insufficient:{code}")
                if (
                    frozen_date is not None
                    and evidence_date is not None
                    and (evidence_date - frozen_date).days < minimum_calendar_days
                ):
                    manifest_blockers.append(f"live_shadow_elapsed_date_insufficient:{code}")
                if earliest_review_date is not None and (
                    evidence_date is None or evidence_date < earliest_review_date
                ):
                    manifest_blockers.append(f"live_shadow_before_earliest_review_date:{code}")
                minimum_decisions = int(live_requirement.get("minimum_decision_count") or 0)
                if int(live_evidence.get("decision_count") or 0) < minimum_decisions:
                    manifest_blockers.append(f"live_shadow_decision_count_insufficient:{code}")
                if live_evidence.get("risk_gate_status") != live_gate.get(
                    "required_risk_gate_status"
                ):
                    manifest_blockers.append(f"live_shadow_risk_gate_not_passed:{code}")
                if live_gate.get("require_risk_evidence_path") is True and not str(
                    live_evidence.get("risk_evidence_path") or ""
                ).strip():
                    manifest_blockers.append(f"live_shadow_risk_evidence_missing:{code}")
            manifest_models.append(
                {
                    "model_code": code,
                    "operating_revision": revision,
                    "decision": decision,
                    "source_candidate_id": source_candidate_id,
                }
            )

    manifest_blockers = list(dict.fromkeys(manifest_blockers))
    manifest_activation_eligible = manifest is not None and not contract_blockers and not manifest_blockers
    resolution_mode = str(contract.get("resolution_mode") or "legacy_static")
    activation_state = str(contract.get("activation_state") or "inactive")
    activation_blockers = [*contract_blockers, *manifest_blockers]
    if resolution_mode != "quant_os_manifest":
        activation_blockers.insert(0, "resolution_mode_legacy_static")
    if activation_state != "active":
        activation_blockers.insert(0, "contract_inactive")
    activation_blockers = list(dict.fromkeys(activation_blockers))
    activated = not activation_blockers

    observation_cfg = contract.get("research_candidate_observation") or {}
    observation_path_text = observation_cfg.get("path") if isinstance(observation_cfg, dict) else None
    observation_path = Path(str(observation_path_text)) if observation_path_text else None
    observation, observation_error = (
        _read_json_diagnostic(observation_path) if observation_path else (None, "manifest_path_not_configured")
    )
    observation_summary = {
        "path": str(observation_path) if observation_path else None,
        "status": observation_error or "observed_research_only",
        "research_only": observation.get("research_only") if observation else None,
        "operating_mutation": observation.get("operating_mutation") if observation else None,
        "model_count": len(observation.get("models") or {}) if observation else 0,
    }

    return {
        "schema_version": int(contract.get("schema_version") or 1),
        "resolution_mode": resolution_mode,
        "activation_state": activation_state,
        "fail_closed": bool(contract.get("fail_closed", True)),
        "scope_status": "manifest_active"
        if activated
        else str(legacy.get("scope_status") or "legacy_compatible_fail_closed"),
        "active_scope_source": "quant_os_operating_manifest"
        if activated
        else "model_scope_registry_legacy",
        "active_scope_id": str(manifest.get("scope_id"))
        if activated and manifest is not None
        else str(legacy.get("scope_id") or "quant_1_0_canonical"),
        "active_models": manifest_models if activated else legacy_models,
        "manifest_path": str(resolved_manifest_path) if resolved_manifest_path else None,
        "manifest_activation_eligible": manifest_activation_eligible,
        "activation_blockers": activation_blockers,
        "research_candidate_observation": observation_summary,
    }


def _stage_rows(cycle: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    cycle_cfg = (cfg.get("cycles") or {}).get(cycle)
    if not isinstance(cycle_cfg, dict):
        raise SystemExit(f"unsupported cycle: {cycle}")
    stage_ids = cycle_cfg.get("stages") or []
    stage_cfg = cfg.get("stages") or {}
    rows: list[dict[str, Any]] = []
    for order, stage_id in enumerate(stage_ids, start=1):
        stage_id = str(stage_id)
        if stage_id.endswith(CLOSE_SUFFIX):
            rows.append(
                {
                    "order": order,
                    "stage_id": stage_id,
                    "thread": "Quant",
                    "title": "Harness close",
                    "objective": "prompt handoff cycle을 마감하고 최종 요약을 작성한다.",
                    "handoff_focus": "none",
                    "expected_report": ["status", "summary", "known_issues"],
                    "close_stage": True,
                }
            )
            continue
        row = stage_cfg.get(stage_id)
        if not isinstance(row, dict):
            raise SystemExit(f"missing prompt stage config: {stage_id}")
        rows.append({"order": order, "stage_id": stage_id, "close_stage": False, **row})
    return rows


def run_dir(run_id: str) -> Path:
    return RUN_ROOT / run_id


def state_path(run_id: str) -> Path:
    return run_dir(run_id) / "prompt_cycle_state.json"


def _stage_dir(run_id: str, stage_id: str) -> Path:
    return run_dir(run_id) / stage_id


def build_initial_state(cycle: str, asof: str, run_id: str | None = None, *, operator_note: str = "") -> dict[str, Any]:
    cfg = _config()
    operating_scope = resolve_operating_scope()
    if cycle == "all":
        raise SystemExit("weekday_weekend_combined_run_forbidden")
    rows = _stage_rows(cycle, cfg)
    stamp = now_stamp()
    rid = run_id or _default_run_id(cycle, asof)
    return {
        "source_name": "prompt_handoff_cycle",
        "schema_version": 1,
        "run_id": rid,
        "cycle_type": cycle,
        "asof": asof,
        "mode": "prompt_handoff",
        "primary_orchestration": cfg.get("primary_orchestration") or "prompt_handoff",
        "command_harness_role": cfg.get("command_harness_role") or "diagnostic_only",
        "status": "in_progress",
        "current_stage_index": 0,
        "created_at": stamp,
        "updated_at": stamp,
        "direct_execution_allowed": False,
        "auto_thread_control_allowed": False,
        "weekday_weekend_combined_run_forbidden": True,
        "auto_repeat_allowed": False,
        "operating_model_version": str(cfg.get("operating_model_version") or "Quant 1.0"),
        "excluded_model_versions": [str(item) for item in cfg.get("excluded_model_versions") or []],
        "allowed_non_operating_observations": [
            str(item) for item in cfg.get("allowed_non_operating_observations") or []
        ],
        "model_version_boundary": str(cfg.get("model_version_boundary") or "Quant 1.0 operating scope only."),
        "operating_scope": operating_scope,
        "default_timebox_minutes": int(cfg.get("default_timebox_minutes") or 10),
        "report_quality_gate": cfg.get("report_quality_gate")
        or {
            "enabled": True,
            "base_required_fields": ["stage_id", "status", "asof", "evidence_files", "known_issues", "handoff_to_next"],
        },
        "operator_note": operator_note,
        "stages": [
            {
                **row,
                "status": "in_progress" if idx == 0 else "pending",
                "started_at": stamp if idx == 0 else None,
                "completed_at": None,
                "prompt_file": None,
                "report_file": None,
                "reported_status": None,
                "evidence_files": [],
                "known_issues": [],
            }
            for idx, row in enumerate(rows)
        ],
    }


def load_state(run_id: str) -> dict[str, Any]:
    path = state_path(run_id)
    if not path.exists():
        raise SystemExit(f"missing prompt cycle state: {path}")
    return read_json(path)


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = now_stamp()
    write_json(state_path(str(state["run_id"])), state)


def current_stage(state: dict[str, Any]) -> dict[str, Any] | None:
    idx = int(state.get("current_stage_index", 0))
    stages = state.get("stages") or []
    if idx < 0 or idx >= len(stages):
        return None
    return stages[idx]


def _parse_stamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_elapsed(start: Any, end: Any) -> str:
    start_dt = _parse_stamp(start)
    end_dt = _parse_stamp(end)
    if start_dt is None or end_dt is None or end_dt < start_dt:
        return ""
    seconds = int((end_dt - start_dt).total_seconds())
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _run_end_stamp(state: dict[str, Any]) -> str | None:
    if state.get("completed_at"):
        return str(state["completed_at"])
    completed = [
        str(row["completed_at"])
        for row in state.get("stages") or []
        if row.get("completed_at")
    ]
    if completed:
        return max(completed)
    if state.get("updated_at"):
        return str(state["updated_at"])
    return None


def _previous_completed(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in state.get("stages") or [] if row.get("status") == "completed"]


def render_prompt(state: dict[str, Any]) -> str:
    stage = current_stage(state)
    if stage is None:
        return "Prompt handoff cycle is completed. No next prompt."
    previous = _previous_completed(state)
    previous_text = "\n".join(
        f"- {row['stage_id']} ({row['thread']}): report={row.get('report_file') or 'none'}, status={row.get('reported_status') or row.get('status')}"
        for row in previous
    ) or "- none"
    fields = "\n".join(f"- {item}" for item in stage.get("expected_report") or [])
    required_checks = "\n".join(f"- {item}" for item in stage.get("required_checks") or [])
    execution_controls = "\n".join(f"- {item}" for item in stage.get("execution_controls") or [])
    required_checks_section = (
        f"""
## 필수 선행/품질 점검
{required_checks}
"""
        if required_checks
        else ""
    )
    execution_controls_section = (
        f"""
## 실행 제어
{execution_controls}
"""
        if execution_controls
        else ""
    )
    timebox_minutes = int(stage.get("timebox_minutes") or state.get("default_timebox_minutes") or 10)
    return f"""# Quant Update Prompt Handoff

대상 thread: {stage['thread']}
cycle_type: {state['cycle_type']}
asof: {state['asof']}
run_id: {state['run_id']}
stage_id: {stage['stage_id']}
stage_title: {stage['title']}

## 중요한 운영 원칙
- 이 지시문은 프롬프트 기반 handoff용이다.
- Harness는 실행파일을 직접 실행하지 않는다.
- 주중/주말 동시 실행은 금지한다.
- 자동 반복 실행은 금지한다.
- 자동 매매, 자동 배포, 자동 승인 작업은 하지 않는다.
- Harness 도입 전 사용자가 각 thread에 직접 지시하던 운영 범위를 넘기지 않는다.
- 새 장기 작업, full rebuild, research_full, forecast 재생성, 정책 변경은 stage 목적에 명시되어 있지 않으면 수행하지 않는다.
- 기존 직접 지시보다 범위가 넓어질 것 같으면 실행하지 말고 blocked로 보고한다.
- 필요한 실행/검증은 대상 thread의 기존 운영 원칙에 따라 해당 thread에서 수행하고, 결과만 아래 형식으로 보고한다.

## Harness 관리 기준
- primary_orchestration: {state.get('primary_orchestration') or 'prompt_handoff'}
- command_harness_role: {state.get('command_harness_role') or 'diagnostic_only'}
- operating_model_version: {state.get('operating_model_version') or 'Quant 1.0'}
- excluded_model_versions: {', '.join(state.get('excluded_model_versions') or ['none'])}
- allowed_non_operating_observations: {', '.join(state.get('allowed_non_operating_observations') or ['none'])}
- 모델 버전 경계: {state.get('model_version_boundary') or 'Quant 1.0 operating scope only.'}
- scope_resolution_mode: {(state.get('operating_scope') or {}).get('resolution_mode') or 'legacy_static'}
- operating_scope_status: {(state.get('operating_scope') or {}).get('scope_status') or 'legacy_compatible_fail_closed'}
- operating_scope_source: {(state.get('operating_scope') or {}).get('active_scope_source') or 'model_scope_registry_legacy'}
- operating_model_codes: {', '.join(str(row.get('model_code')) for row in ((state.get('operating_scope') or {}).get('active_models') or [])) or 'none'}
- model_revision_scope_status: resolved_by_model_code_and_operating_revision
- manifest_activation_eligible: {(state.get('operating_scope') or {}).get('manifest_activation_eligible') is True}
- scope_activation_blockers: {', '.join((state.get('operating_scope') or {}).get('activation_blockers') or ['none'])}
- `operating_model_version`은 현재 호환 표시값이며, 실제 범위 권위는 fail-closed로 resolve된 `model_code`와 `operating_revision`이다.
- 제외된 모델 버전은 운영 입력, promotion, current/admin/public payload 또는 publish에 포함하지 않는다. 단, `allowed_non_operating_observations`에 명시된 frozen 읽기 전용 governance 비교만 실행·게시 권한 없이 허용한다.
- timebox_minutes: {timebox_minutes}
- timebox는 목표 소요시간이다. Harness가 실행을 임의로 중단하지 않으며, 이미 확인된 정상 프로세스가 진행 중이면 완료 report 또는 checkpoint를 기다린다.
- 목표 시간을 넘기고 새 로그, 산출물 갱신, checkpoint 진행이 모두 없을 때만 대상 thread의 checkpoint/실행 상태를 먼저 확인한다. 중복 전체 실행을 시작하지 않는다.
- 보고서에는 `stage_id`, `status`, `asof`, `evidence_files`, `known_issues`, `handoff_to_next`를 반드시 포함한다.

## 이전 단계 결과
{previous_text}

## 이번 단계 목적
{stage['objective']}

## 이번 단계에서 확인할 것
- 하네스 asof `{state['asof']}`는 요청/운영 기준일이다.
- 데이터 기준일은 각 stage의 목적과 대상 thread의 운영 원칙에 따라 확정한다. 특히 장 마감/데이터 적재 전에는 최신 가용 거래일을 `data_asof`로 분리 보고한다.
- 이전 단계 report와 known_issues를 먼저 확인한다.
- 이번 단계가 다음 단계에 넘겨야 할 입력과 차단 이슈를 분리해서 보고한다.
- 직접 수정이 필요한 다른 thread 코드가 있으면 수정하지 말고 요청사항으로 보고한다.
{required_checks_section}
{execution_controls_section}

## 다음 handoff 초점
{stage['handoff_focus']}

## 보고 형식
아래 항목을 포함해서 이 Harness thread에 결과를 보고한다.
{fields}

권장 보고 템플릿:

```text
stage_id: {stage['stage_id']}
status: completed | blocked | failed
asof: {state['asof']}
data_asof: <해당 stage의 실제 데이터 기준일. 하네스 asof와 같으면 같은 날짜를 기재>
completed_work:
- ...
evidence_files:
- ...
known_issues:
- none
handoff_to_next:
- ...
```
"""


def report_quality_issues(state: dict[str, Any], stage: dict[str, Any], status: str, report_text: str) -> list[str]:
    gate = state.get("report_quality_gate") or {}
    if gate.get("enabled") is False:
        return []
    text = report_text.lower()
    required = [str(item) for item in (gate.get("base_required_fields") or [])]
    if not required:
        required = ["stage_id", "status", "asof", "evidence_files", "known_issues", "handoff_to_next"]
    if bool(stage.get("close_stage")):
        required = ["status", "summary", "known_issues"]

    issues: list[str] = []
    for field in required:
        if f"{field.lower()}:" not in text:
            issues.append(f"missing_report_field:{field}")

    stage_id = str(stage.get("stage_id") or "")
    if stage_id and f"stage_id: {stage_id.lower()}" not in text:
        issues.append("stage_id_mismatch_or_missing")
    if f"status: {status.lower()}" not in text:
        issues.append("status_mismatch_or_missing")

    asof = str(state.get("asof") or "")
    if asof and not bool(stage.get("close_stage")) and f"asof: {asof.lower()}" not in text:
        issues.append("asof_mismatch_or_missing")
    return issues


def write_prompt(state: dict[str, Any]) -> Path:
    stage = current_stage(state)
    if stage is None:
        raise SystemExit("no active stage")
    out = _stage_dir(str(state["run_id"]), str(stage["stage_id"]))
    out.mkdir(parents=True, exist_ok=True)
    path = out / "prompt.md"
    path.write_text(render_prompt(state), encoding="utf-8")
    stage["prompt_file"] = str(path)
    save_state(state)
    return path


def _advance_after_completion(state: dict[str, Any]) -> None:
    idx = int(state["current_stage_index"])
    stages = state["stages"]
    if idx + 1 >= len(stages):
        state["status"] = "completed"
        state["current_stage_index"] = len(stages)
        return
    state["current_stage_index"] = idx + 1
    next_stage = stages[idx + 1]
    next_stage["status"] = "in_progress"
    next_stage["started_at"] = now_stamp()


def record_report(
    state: dict[str, Any],
    *,
    status: str,
    report_text: str,
    evidence_files: list[str],
    known_issues: list[str],
    advance: bool,
) -> dict[str, Any]:
    if status not in {"completed", "blocked", "failed"}:
        raise SystemExit("status must be one of: completed, blocked, failed")
    next_state = deepcopy(state)
    stage = current_stage(next_state)
    if stage is None:
        raise SystemExit("no active stage")
    quality_issues = report_quality_issues(next_state, stage, status, report_text)
    if quality_issues:
        raise SystemExit("report_quality_gate_failed: " + ", ".join(quality_issues))
    out = _stage_dir(str(next_state["run_id"]), str(stage["stage_id"]))
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "thread_report.md"
    report_path.write_text(report_text.rstrip() + "\n", encoding="utf-8")
    stage["status"] = status
    stage["reported_status"] = status
    stage["completed_at"] = now_stamp()
    stage["report_file"] = str(report_path)
    stage["evidence_files"] = evidence_files
    stage["known_issues"] = known_issues
    stage["report_quality"] = {"status": "passed", "issues": []}
    if status in {"blocked", "failed"}:
        next_state["status"] = status
    elif advance:
        _advance_after_completion(next_state)
    save_state(next_state)
    if status == "completed" and advance and next_state.get("status") == "in_progress":
        write_prompt(next_state)
    if status == "completed" and advance and next_state.get("status") == "completed":
        return close_cycle(next_state)
    return next_state


def close_cycle(state: dict[str, Any]) -> dict[str, Any]:
    next_state = deepcopy(state)
    stage = current_stage(next_state)
    if stage and str(stage.get("stage_id", "")).endswith(CLOSE_SUFFIX):
        close_stamp = now_stamp()
        stage["status"] = "completed"
        stage["reported_status"] = "completed"
        stage["completed_at"] = close_stamp
        next_state["completed_at"] = close_stamp
    elif not next_state.get("completed_at"):
        next_state["completed_at"] = _run_end_stamp(next_state)
    next_state["status"] = "completed"
    next_state["current_stage_index"] = len(next_state.get("stages") or [])
    out = run_dir(str(next_state["run_id"]))
    summary = out / "final_summary.md"
    summary.write_text(render_summary(next_state), encoding="utf-8")
    next_state["final_summary_file"] = str(summary)
    save_state(next_state)
    return next_state


def render_summary(state: dict[str, Any]) -> str:
    run_end = _run_end_stamp(state)
    total_elapsed = _format_elapsed(state.get("created_at"), run_end)
    lines = [
        "# Prompt Handoff Cycle Summary",
        "",
        f"- run_id: {state['run_id']}",
        f"- cycle_type: {state['cycle_type']}",
        f"- asof: {state['asof']}",
        f"- status: {state['status']}",
        f"- started_at: {state.get('created_at') or ''}",
        f"- completed_at: {run_end or ''}",
        f"- total_elapsed: {total_elapsed or 'unknown'}",
        f"- direct_execution_allowed: {state['direct_execution_allowed']}",
        f"- primary_orchestration: {state.get('primary_orchestration') or 'prompt_handoff'}",
        f"- command_harness_role: {state.get('command_harness_role') or 'diagnostic_only'}",
        "",
        "| order | stage_id | thread | status | started_at | completed_at | elapsed | report |",
        "|---:|---|---|---|---|---|---:|---|",
    ]
    for row in state.get("stages") or []:
        elapsed = _format_elapsed(row.get("started_at"), row.get("completed_at"))
        lines.append(
            f"| {row['order']} | {row['stage_id']} | {row['thread']} | {row['status']} | "
            f"{row.get('started_at') or ''} | {row.get('completed_at') or ''} | {elapsed or ''} | {row.get('report_file') or ''} |"
        )
    return "\n".join(lines) + "\n"


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    stage = current_stage(state)
    return {
        "run_id": state.get("run_id"),
        "cycle_type": state.get("cycle_type"),
        "asof": state.get("asof"),
        "status": state.get("status"),
        "mode": state.get("mode"),
        "primary_orchestration": state.get("primary_orchestration") or "prompt_handoff",
        "command_harness_role": state.get("command_harness_role") or "diagnostic_only",
        "current_stage": None
        if stage is None
        else {
            "stage_id": stage.get("stage_id"),
            "thread": stage.get("thread"),
            "status": stage.get("status"),
            "prompt_file": stage.get("prompt_file"),
        },
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Manual prompt handoff harness for weekday/weekend update cycles.")
    sub = ap.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--cycle", choices=["weekday", "weekend"], required=True)
    start.add_argument("--asof", required=True)
    start.add_argument("--run-id", default=None)
    start.add_argument("--operator-note", default="")

    status = sub.add_parser("status")
    status.add_argument("--run-id", required=True)

    prompt = sub.add_parser("render-prompt")
    prompt.add_argument("--run-id", required=True)

    report = sub.add_parser("record-report")
    report.add_argument("--run-id", required=True)
    report.add_argument("--status", choices=["completed", "blocked", "failed"], required=True)
    report.add_argument("--report-file", required=True)
    report.add_argument("--evidence", action="append", default=[])
    report.add_argument("--issue", action="append", default=[])
    report.add_argument("--no-advance", action="store_true")

    close = sub.add_parser("close")
    close.add_argument("--run-id", required=True)

    scope = sub.add_parser("scope-dry-run")
    scope.add_argument("--registry", default=str(MODEL_SCOPE_REGISTRY_PATH))
    scope.add_argument("--manifest", default=None)

    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "start":
        state = build_initial_state(args.cycle, args.asof, args.run_id, operator_note=args.operator_note)
        save_state(state)
        prompt_path = write_prompt(state)
        print(json.dumps({"prompt": str(prompt_path), **summarize(state)}, ensure_ascii=False, indent=2))
        return
    if args.command == "status":
        print(json.dumps(summarize(load_state(args.run_id)), ensure_ascii=False, indent=2))
        return
    if args.command == "render-prompt":
        state = load_state(args.run_id)
        prompt_path = write_prompt(state)
        print(json.dumps({"prompt": str(prompt_path), **summarize(state)}, ensure_ascii=False, indent=2))
        return
    if args.command == "record-report":
        report_path = Path(args.report_file)
        if not report_path.exists():
            raise SystemExit(f"missing report file: {report_path}")
        state = record_report(
            load_state(args.run_id),
            status=args.status,
            report_text=report_path.read_text(encoding="utf-8"),
            evidence_files=list(args.evidence),
            known_issues=list(args.issue),
            advance=not args.no_advance,
        )
        print(json.dumps(summarize(state), ensure_ascii=False, indent=2))
        return
    if args.command == "close":
        state = close_cycle(load_state(args.run_id))
        print(json.dumps(summarize(state), ensure_ascii=False, indent=2))
        return
    if args.command == "scope-dry-run":
        scope = resolve_operating_scope(
            registry_path=Path(args.registry),
            manifest_path=Path(args.manifest) if args.manifest else None,
        )
        print(json.dumps(scope, ensure_ascii=False, indent=2))
        return
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
