from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "reports" / "update_pipeline_harness"
HANDOFF_DIR = STATE_DIR / "handoffs"
CURRENT_STATE_PATH = STATE_DIR / "current_state.json"

THREADS = ("Quant", "QuantMarket", "QuantAnalysis")


def _python() -> str:
    return r"D:\Quant\venv64\Scripts\python.exe"


def _quant_pipeline(args: str) -> str:
    return f"{_python()} D:\\Quant\\src\\quant_service\\run_daily_quant_pipeline.py {args}"


def _validation(args: str) -> str:
    return f"{_python()} D:\\Quant\\scripts\\run_quant_validation_suite.py {args}"


def workflow_steps(workflow: str, include_ai_research: bool = False) -> list[dict[str, Any]]:
    if include_ai_research:
        raise ValueError("Quant 1.0 AI retired: include_ai_research is forbidden")
    if workflow == "weekday":
        return [
            {
                "id": "quant_data_refresh",
                "thread": "Quant",
                "title": "주중 전반부 데이터 갱신",
                "purpose": "공통 asof 기준 일별 데이터와 feature를 먼저 갱신한다.",
                "commands": [
                    _quant_pipeline("--asof {asof} --include-etf --data-refresh-only"),
                ],
                "completion_criteria": [
                    "전반부 명령 성공",
                    "timing report 생성",
                    "실패 시 failure.resume_hint 기록",
                ],
                "handoff_focus": "QuantMarket이 같은 asof로 market context / forecast handoff를 갱신할 수 있게 결과와 asof를 전달한다.",
            },
            {
                "id": "quantmarket_handoff",
                "thread": "QuantMarket",
                "title": "QuantMarket market context handoff 갱신",
                "purpose": "Quant 모델 실행 전에 같은 asof의 시장 context / forecast handoff를 준비한다.",
                "commands": [],
                "completion_criteria": [
                    r"D:\QuantMarket\service_platform\quant_model_handoff\market_context\current 갱신",
                    "quant_model_handoff_manifest.json production_ready=true",
                    "20d 기준 ALL/KOSPI/KOSDAQ scope 존재",
                ],
                "handoff_focus": "Quant가 daily_light 후반부를 실행할 수 있도록 manifest 상태와 산출물 경로를 회신한다.",
            },
            {
                "id": "quant_model_run_daily_light",
                "thread": "Quant",
                "title": "주중 후반부 모델/current 산출",
                "purpose": "daily_light 모델, public/admin current, trading sign, contract 검증을 수행한다.",
                "commands": [
                    _quant_pipeline("--asof {asof} --include-etf --model-run-only --pipeline-mode daily_light"),
                    _validation("--asof {asof} --mode daily_contract"),
                ],
                "completion_criteria": [
                    "daily_light 후반부 성공",
                    "daily_contract validation pass",
                    "publish 전이면 pre_gcs_publish 검증 필요 여부 기록",
                ],
                "handoff_focus": "QuantAnalysis가 timing/validation/model change를 검토할 수 있게 report 경로와 특이사항을 전달한다.",
            },
            {
                "id": "quantanalysis_daily_review",
                "thread": "QuantAnalysis",
                "title": "주중 결과 리뷰",
                "purpose": "주중 업데이트 결과의 freshness, 검증, 모델 변화, publish 가능성을 점검한다.",
                "commands": [],
                "completion_criteria": [
                    "latest timing report 확인",
                    "daily_contract validation report 확인",
                    "public publish 가능/보류 판단 근거 정리",
                ],
                "handoff_focus": "Quant가 publish gate 또는 보류 조치를 결정할 수 있게 리뷰 결과를 회신한다.",
            },
            {
                "id": "quant_publish_gate",
                "thread": "Quant",
                "title": "주중 publish gate",
                "purpose": "검증 통과와 리뷰 결과를 기준으로 public publish 여부를 확정한다.",
                "commands": [
                    _validation("--asof {asof} --mode pre_gcs_publish"),
                    f"{_python()} D:\\Quant\\scripts\\publish_public_current_to_gcs.py",
                ],
                "completion_criteria": [
                    "pre_gcs_publish validation pass",
                    "public publish 실행 여부와 근거 기록",
                    "publish 보류 시 다음 액션 기록",
                ],
                "handoff_focus": "완료 상태를 current_state에 남기고 다음 영업일 업데이트 전까지 변경하지 않는다.",
            },
        ]

    if workflow == "weekend":
        research_command = _quant_pipeline("--asof {asof} --include-etf --model-run-only --pipeline-mode research_full")
        research_command += " --skip-remote-current-publish"
        return [
            {
                "id": "quant_weekend_pipeline",
                "thread": "Quant",
                "title": "주말 Quant 비AI 모델 검증 통합 파이프라인",
                "purpose": "폐지 AI/T 실행을 제외한 주말 비AI 모델 검증 결과를 정리한다.",
                "commands": [
                    f"{_python()} D:\\Quant\\scripts\\build_sqlite_db_schema_manifest.py --asof {{asof}} --include-row-counts",
                    research_command,
                    _validation("--asof {asof} --mode research_validation"),
                ],
                "completion_criteria": [
                    "운영 asof 확정",
                    "schema/freshness와 주중 실패/보류 항목 확인",
                    "research_full 성공",
                    "research_validation pass 또는 실패 사유 기록",
                    "폐지 AI/T 학습·추론·생성·freshness 복구 금지, 과거 자료 보존",
                    "성과 개선/손실 위험 축소 근거 확인",
                    "주중 즉시 반영 금지 항목 분리",
                    "다음 주 운영 반영 후보 정리",
                    "운영 반영/보류 판단 기록",
                    "필요 시 QS/QM 요청 문서 작성",
                    "다음 주 weekday harness 시작 조건 기록",
                ],
                "handoff_focus": "완료 상태를 current_state에 남기고 다음 주중 업데이트의 입력으로 사용한다.",
            },
        ]

    raise ValueError(f"unsupported workflow: {workflow}")


def now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def token(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace(" ", "_")


def build_initial_state(
    *,
    workflow: str,
    asof: str,
    batch_type: str,
    include_ai_research: bool = False,
) -> dict[str, Any]:
    steps = workflow_steps(workflow, include_ai_research=include_ai_research)
    generated_at = now_stamp()
    return {
        "source_name": "quant_update_pipeline_harness",
        "schema_version": 1,
        "run_id": f"{workflow}_{token(asof)}_{token(generated_at)}",
        "workflow": workflow,
        "asof": asof,
        "batch_type": batch_type,
        "include_ai_research": bool(include_ai_research),
        "status": "in_progress",
        "current_step_index": 0,
        "created_at": generated_at,
        "updated_at": generated_at,
        "threads": sorted({str(step["thread"]) for step in steps}),
        "steps": [
            {
                **step,
                "status": "in_progress" if idx == 0 else "pending",
                "started_at": generated_at if idx == 0 else None,
                "completed_at": None,
                "evidence": [],
                "notes": [],
            }
            for idx, step in enumerate(steps)
        ],
    }


def load_state(path: Path = CURRENT_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing state file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any], path: Path = CURRENT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_stamp()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def current_step(state: dict[str, Any]) -> dict[str, Any] | None:
    idx = int(state.get("current_step_index", 0))
    steps = state.get("steps", [])
    if idx < 0 or idx >= len(steps):
        return None
    return steps[idx]


def complete_current_step(state: dict[str, Any], evidence: list[str], notes: list[str]) -> dict[str, Any]:
    next_state = deepcopy(state)
    step = current_step(next_state)
    if step is None:
        next_state["status"] = "completed"
        return next_state
    if step["status"] not in {"in_progress", "blocked"}:
        raise SystemExit(f"current step is not active: {step['id']} status={step['status']}")

    stamp = now_stamp()
    step["status"] = "completed"
    step["completed_at"] = stamp
    step["evidence"].extend(evidence)
    step["notes"].extend(notes)

    idx = int(next_state["current_step_index"])
    if idx + 1 >= len(next_state["steps"]):
        next_state["status"] = "completed"
        next_state["current_step_index"] = len(next_state["steps"])
    else:
        next_state["current_step_index"] = idx + 1
        next_step = next_state["steps"][idx + 1]
        next_step["status"] = "in_progress"
        next_step["started_at"] = stamp
        next_state["status"] = "in_progress"
    return next_state


def block_current_step(state: dict[str, Any], notes: list[str]) -> dict[str, Any]:
    next_state = deepcopy(state)
    step = current_step(next_state)
    if step is None:
        raise SystemExit("no active step to block")
    step["status"] = "blocked"
    step["notes"].extend(notes)
    next_state["status"] = "blocked"
    return next_state


def render_prompt(state: dict[str, Any]) -> str:
    step = current_step(state)
    if step is None:
        return "Harness completed. No next thread prompt."

    asof = str(state["asof"])
    commands = [str(cmd).format(asof=asof) for cmd in step.get("commands", [])]
    commands_text = "\n".join(f"- `{cmd}`" for cmd in commands) if commands else "- 이 단계는 해당 thread에서 기존 절차에 따라 실행하고 결과만 회신한다."
    criteria_text = "\n".join(f"- {item}" for item in step.get("completion_criteria", []))

    return f"""# Quant Update Pipeline Handoff

대상 thread: {step["thread"]}
workflow: {state["workflow"]}
asof: {asof}
batch_type: {state["batch_type"]}
step: {step["id"]} - {step["title"]}

## 목적
{step["purpose"]}

## 실행/확인
{commands_text}

## 완료 기준
{criteria_text}

## 회신 형식
- status: pass / fail / blocked
- evidence: 생성 report, manifest, validation 경로
- notes: 실패 원인, resume hint, 다음 thread가 알아야 할 특이사항

## 다음 handoff 초점
{step["handoff_focus"]}
"""


def write_prompt(state: dict[str, Any]) -> Path:
    step = current_step(state)
    if step is None:
        raise SystemExit("no active step to render")
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    idx = int(state["current_step_index"]) + 1
    path = HANDOFF_DIR / f"{state['run_id']}_{idx:02d}_{step['id']}.md"
    path.write_text(render_prompt(state), encoding="utf-8")
    return path


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    step = current_step(state)
    return {
        "status": state.get("status"),
        "workflow": state.get("workflow"),
        "asof": state.get("asof"),
        "batch_type": state.get("batch_type"),
        "current_step": None
        if step is None
        else {
            "id": step.get("id"),
            "thread": step.get("thread"),
            "title": step.get("title"),
            "status": step.get("status"),
        },
        "completed_steps": [s["id"] for s in state.get("steps", []) if s.get("status") == "completed"],
        "pending_steps": [s["id"] for s in state.get("steps", []) if s.get("status") == "pending"],
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Manage Quant weekday/weekend multi-thread update pipeline handoffs.")
    sub = ap.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a new harness state.")
    init.add_argument("--workflow", choices=["weekday", "weekend"], required=True)
    init.add_argument("--asof", required=True, help="YYYY-MM-DD")
    init.add_argument(
        "--batch-type",
        choices=["provisional_evening_internal", "final_operational_publish", "research_full"],
        default="final_operational_publish",
    )
    init.add_argument("--include-ai-research", action="store_true")
    init.add_argument("--force", action="store_true", help="Overwrite an existing active current_state.json.")

    sub.add_parser("status", help="Print current harness status.")
    sub.add_parser("render-next", help="Render the current step handoff prompt.")

    done = sub.add_parser("complete-step", help="Mark current step complete and advance.")
    done.add_argument("--evidence", action="append", default=[])
    done.add_argument("--note", action="append", default=[])
    done.add_argument("--render-next", action="store_true")

    block = sub.add_parser("block-step", help="Mark current step blocked.")
    block.add_argument("--note", action="append", required=True)

    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "init":
        if CURRENT_STATE_PATH.exists() and not args.force:
            existing = load_state()
            if existing.get("status") in {"in_progress", "blocked"}:
                raise SystemExit(f"active harness exists: {CURRENT_STATE_PATH}. Use --force to replace it.")
        state = build_initial_state(
            workflow=args.workflow,
            asof=args.asof,
            batch_type=args.batch_type,
            include_ai_research=bool(args.include_ai_research),
        )
        write_state(state)
        prompt_path = write_prompt(state)
        print(json.dumps({"state": str(CURRENT_STATE_PATH), "prompt": str(prompt_path), **summarize(state)}, ensure_ascii=False, indent=2))
        return

    state = load_state()

    if args.command == "status":
        print(json.dumps(summarize(state), ensure_ascii=False, indent=2))
        return

    if args.command == "render-next":
        prompt_path = write_prompt(state)
        print(json.dumps({"prompt": str(prompt_path), **summarize(state)}, ensure_ascii=False, indent=2))
        return

    if args.command == "complete-step":
        next_state = complete_current_step(state, list(args.evidence), list(args.note))
        write_state(next_state)
        payload = {"state": str(CURRENT_STATE_PATH), **summarize(next_state)}
        if args.render_next and next_state.get("status") != "completed":
            payload["prompt"] = str(write_prompt(next_state))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "block-step":
        next_state = block_current_step(state, list(args.note))
        write_state(next_state)
        print(json.dumps({"state": str(CURRENT_STATE_PATH), **summarize(next_state)}, ensure_ascii=False, indent=2))
        return

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
