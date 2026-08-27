from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("prompt_handoff_cycle", HARNESS_DIR / "prompt_handoff_cycle.py")
assert SPEC is not None
PROMPT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROMPT)


def _approved_scope_manifest() -> dict:
    model_codes = ["S2", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5", "S6", "T_STOCK_V01"]
    models = {}
    for code in model_codes:
        canonical_code = "T-STOCK-V01" if code == "T_STOCK_V01" else code
        keep_current = canonical_code == "T-STOCK-V01"
        cadence = "weekly" if canonical_code in {"S2", "S3", "S3_CORE2", "S3_ACCEL_V01"} else "monthly"
        models[code] = {
            "model_code": canonical_code,
            "approval_status": "approved",
            "decision": "keep_current_revision" if keep_current else "adopt_candidate_revision",
            "operating_revision": "quant_1_0_canonical" if keep_current else f"{canonical_code.lower()}_approved_revision",
            "source_candidate_id": "" if keep_current else f"{canonical_code.lower()}_candidate",
        }
        if not keep_current:
            models[code]["live_shadow_evidence"] = {
                "frozen_asof": "2026-08-22",
                "evidence_asof": "2027-02-18",
                "calendar_days": 180,
                "decision_count": 26 if cadence == "weekly" else 6,
                "risk_gate_status": "passed",
                "risk_evidence_path": f"reports/quant1_2/forward_shadow/{canonical_code}/risk_evaluation.json",
            }
    return {
        "schema_version": 1,
        "manifest_type": "quant_os_operating_scope",
        "scope_id": "quant_os_approved_unit",
        "status": "approved_8_of_8",
        "operating_mutation_allowed": True,
        "approval": {
            "approved_model_count": 8,
            "total_model_count": 8,
            "user_final_approval": True,
            "user_approval_reference": "unit-final-approval",
        },
        "models": models,
    }


def _scope_registry_for_test(tmp_path: Path, *, active: bool) -> Path:
    source = Path(__file__).resolve().parents[1] / "config" / "harness" / "model_scope_registry.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    contract = payload["model_scope_registry"]["operating_scope_contract"]
    contract["resolution_mode"] = "quant_os_manifest" if active else "legacy_static"
    contract["activation_state"] = "active" if active else "inactive"
    contract["research_candidate_observation"]["path"] = str(tmp_path / "missing_research.json")
    output = tmp_path / "model_scope_registry.yaml"
    output.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return output


def test_weekday_prompt_starts_at_wd01_without_direct_execution() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-06-26", "unit_prompt_weekday")

    current = PROMPT.current_stage(state)

    assert state["mode"] == "prompt_handoff"
    assert state["direct_execution_allowed"] is False
    assert state["operating_model_version"] == "Quant 1.0"
    assert state["excluded_model_versions"] == ["Quant 1.1", "Quant 1.2", "Quant 2.x"]
    assert state["allowed_non_operating_observations"] == [
        "Quant 1.2 frozen live-shadow read-only comparison"
    ]
    assert state["operating_scope"]["scope_status"] == "legacy_compatible_fail_closed"
    assert state["operating_scope"]["active_scope_source"] == "model_scope_registry_legacy"
    assert current["stage_id"] == "WD01_QUANT_FRONT"
    assert current["thread"] == "Quant"


def test_prompt_contains_report_contract_and_no_direct_execution() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-06-26", "unit_prompt_weekday")

    prompt = PROMPT.render_prompt(state)

    assert "Harness는 실행파일을 직접 실행하지 않는다" in prompt
    assert "primary_orchestration: prompt_handoff" in prompt
    assert "command_harness_role: diagnostic_only" in prompt
    assert "operating_model_version: Quant 1.0" in prompt
    assert "scope_resolution_mode: legacy_static" in prompt
    assert "operating_scope_status: legacy_compatible_fail_closed" in prompt
    assert "operating_scope_source: model_scope_registry_legacy" in prompt
    assert "model_revision_scope_status: resolved_by_model_code_and_operating_revision" in prompt
    assert "manifest_activation_eligible: False" in prompt
    assert "excluded_model_versions: Quant 1.1, Quant 1.2, Quant 2.x" in prompt
    assert "allowed_non_operating_observations: Quant 1.2 frozen live-shadow read-only comparison" in prompt
    assert "Quant 1.2 is excluded from operation/publish" in prompt
    assert "frozen 읽기 전용 governance 비교만 실행·게시 권한 없이 허용" in prompt
    assert "사용자가 각 thread에 직접 지시하던 운영 범위를 넘기지 않는다" in prompt
    assert "기존 직접 지시보다 범위가 넓어질 것 같으면 실행하지 말고 blocked로 보고한다" in prompt
    assert "stage_id: WD01_QUANT_FRONT" in prompt
    assert "--include-etf --data-refresh-only" in prompt
    assert "`--include-etf`를 생략하지 않는다" in prompt
    assert "226490" in prompt
    assert "blocked_needs_etf_price_refresh" in prompt
    assert "전체 data-refresh 체인을 중복 실행하지 않는다" in prompt
    assert "status: completed | blocked | failed" in prompt


def test_scope_contract_stays_legacy_while_inactive_even_with_approved_manifest(tmp_path: Path) -> None:
    registry_path = _scope_registry_for_test(tmp_path, active=False)
    manifest_path = tmp_path / "approved_operating_manifest.json"
    manifest_path.write_text(json.dumps(_approved_scope_manifest()), encoding="utf-8")

    scope = PROMPT.resolve_operating_scope(registry_path, manifest_path)

    assert scope["manifest_activation_eligible"] is True
    assert scope["active_scope_source"] == "model_scope_registry_legacy"
    assert "contract_inactive" in scope["activation_blockers"]
    assert "resolution_mode_legacy_static" in scope["activation_blockers"]
    assert {row["operating_revision"] for row in scope["active_models"]} == {"quant_1_0_canonical"}


def test_scope_contract_requires_final_user_approval(tmp_path: Path) -> None:
    registry_path = _scope_registry_for_test(tmp_path, active=True)
    manifest = _approved_scope_manifest()
    manifest["approval"]["user_final_approval"] = False
    manifest_path = tmp_path / "not_user_approved.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    scope = PROMPT.resolve_operating_scope(registry_path, manifest_path)

    assert scope["manifest_activation_eligible"] is False
    assert scope["active_scope_source"] == "model_scope_registry_legacy"
    assert "user_final_approval_missing" in scope["activation_blockers"]


def test_scope_contract_requires_six_month_live_shadow_and_risk_pass(tmp_path: Path) -> None:
    registry_path = _scope_registry_for_test(tmp_path, active=True)
    manifest = _approved_scope_manifest()
    manifest["models"]["S2"]["live_shadow_evidence"].update(
        {
            "evidence_asof": "2027-02-17",
            "calendar_days": 179,
            "decision_count": 25,
            "risk_gate_status": "failed_candidate_risk_gate",
        }
    )
    manifest_path = tmp_path / "insufficient_live_shadow.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    scope = PROMPT.resolve_operating_scope(registry_path, manifest_path)

    assert scope["manifest_activation_eligible"] is False
    assert scope["active_scope_source"] == "model_scope_registry_legacy"
    assert "live_shadow_calendar_days_insufficient:S2" in scope["activation_blockers"]
    assert "live_shadow_decision_count_insufficient:S2" in scope["activation_blockers"]
    assert "live_shadow_risk_gate_not_passed:S2" in scope["activation_blockers"]
    assert "live_shadow_before_earliest_review_date:S2" in scope["activation_blockers"]


def test_scope_contract_can_resolve_approved_model_revisions_after_activation(tmp_path: Path) -> None:
    registry_path = _scope_registry_for_test(tmp_path, active=True)
    manifest_path = tmp_path / "approved_operating_manifest.json"
    manifest_path.write_text(json.dumps(_approved_scope_manifest()), encoding="utf-8")

    scope = PROMPT.resolve_operating_scope(registry_path, manifest_path)

    assert scope["scope_status"] == "manifest_active"
    assert scope["active_scope_source"] == "quant_os_operating_manifest"
    assert len(scope["active_models"]) == 8
    t_stock = next(row for row in scope["active_models"] if row["model_code"] == "T-STOCK-V01")
    assert t_stock == {
        "model_code": "T-STOCK-V01",
        "operating_revision": "quant_1_0_canonical",
        "decision": "keep_current_revision",
        "source_candidate_id": "",
    }


def test_selection_freeze_manifest_cannot_activate_operating_scope(tmp_path: Path) -> None:
    registry_path = _scope_registry_for_test(tmp_path, active=True)
    selection_freeze = (
        Path(__file__).resolve().parents[1]
        / "reports"
        / "quant1_2"
        / "operational_readiness"
        / "selection_freeze_manifest.json"
    )

    scope = PROMPT.resolve_operating_scope(registry_path, selection_freeze)

    assert scope["manifest_activation_eligible"] is False
    assert scope["active_scope_source"] == "model_scope_registry_legacy"
    assert "manifest_type_not_approved_operating_scope" in scope["activation_blockers"]
    assert "research_only_manifest_forbidden" in scope["activation_blockers"]
    assert "operating_mutation_not_allowed" in scope["activation_blockers"]


def test_record_report_advances_to_next_stage(tmp_path: Path) -> None:
    PROMPT.RUN_ROOT = tmp_path
    state = PROMPT.build_initial_state("weekday", "2026-06-26", "unit_prompt_weekday")
    report = """stage_id: WD01_QUANT_FRONT
status: completed
asof: 2026-06-26
evidence_files:
- timing.json
known_issues:
- none
handoff_to_next:
- WD02 ready
"""

    advanced = PROMPT.record_report(
        state,
        status="completed",
        report_text=report,
        evidence_files=["timing.json"],
        known_issues=["none"],
        advance=True,
    )

    current = PROMPT.current_stage(advanced)

    assert advanced["stages"][0]["status"] == "completed"
    assert current["stage_id"] == "WD02_MARKET_COLLECT"
    assert current["thread"] == "QuantMarketData"


def test_weekday_stage_order_includes_publish_gate_before_close() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-07-07", "unit_prompt_weekday")

    stage_ids = [row["stage_id"] for row in state["stages"]]

    assert stage_ids == [
        "WD01_QUANT_FRONT",
        "WD02_MARKET_COLLECT",
        "WD03_MARKET_ANALYSIS",
        "WD04_QUANT_REAR",
        "WD05_PORTFOLIO_ANALYSIS",
        "WD06_PRE_GCS_PUBLISH",
        "WD07_HARNESS_CLOSE",
    ]


def test_prompt_thread_targets_cover_all_cycle_stages() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = yaml.safe_load(
        (root / "config" / "harness" / "prompt_thread_targets.yaml").read_text(encoding="utf-8")
    )["prompt_thread_targets"]
    configured = yaml.safe_load(
        (root / "config" / "harness" / "prompt_handoff_stages.yaml").read_text(encoding="utf-8")
    )["prompt_handoff"]
    expected = {
        stage_id
        for cycle in configured["cycles"].values()
        for stage_id in cycle["stages"]
    }

    assert set(targets["stage_targets"]) == expected
    assert targets["threads"]["Quant"]["title"] == "Quant OS"


def test_final_stage_report_automatically_writes_cycle_summary(tmp_path: Path) -> None:
    PROMPT.RUN_ROOT = tmp_path
    state = PROMPT.build_initial_state("weekend", "2026-08-23", "unit_weekend_close")
    state["stages"][0]["status"] = "completed"
    state["stages"][0]["reported_status"] = "completed"
    state["stages"][0]["completed_at"] = state["created_at"]
    state["current_stage_index"] = 1
    state["stages"][1]["status"] = "in_progress"
    state["stages"][1]["started_at"] = state["created_at"]
    report = """stage_id: WE06_HARNESS_CLOSE
status: completed
summary: weekend cycle closed
known_issues:
- none
"""

    closed = PROMPT.record_report(
        state,
        status="completed",
        report_text=report,
        evidence_files=[],
        known_issues=["none"],
        advance=True,
    )

    summary_path = tmp_path / "unit_weekend_close" / "final_summary.md"
    assert closed["status"] == "completed"
    assert closed["final_summary_file"] == str(summary_path)
    assert summary_path.is_file()
    assert "total_elapsed:" in summary_path.read_text(encoding="utf-8")


def test_record_report_rejects_incomplete_report(tmp_path: Path) -> None:
    PROMPT.RUN_ROOT = tmp_path
    state = PROMPT.build_initial_state("weekday", "2026-06-26", "unit_prompt_weekday")

    try:
        PROMPT.record_report(
            state,
            status="completed",
            report_text="stage_id: WD01_QUANT_FRONT\nstatus: completed\n",
            evidence_files=[],
            known_issues=[],
            advance=True,
        )
    except SystemExit as exc:
        assert "report_quality_gate_failed" in str(exc)
    else:
        raise AssertionError("incomplete report should fail quality gate")


def test_wd02_prompt_requires_market_context_mart_freshness() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-07-07", "unit_prompt_weekday")
    state["current_stage_index"] = 1

    prompt = PROMPT.render_prompt(state)

    assert "timebox_minutes: 30" in prompt
    assert "check_kiwoom_ip_auth.py --asof <data_asof>" in prompt
    assert "blocked_needs_kiwoom_allowed_ip_update" in prompt
    assert "공동인증서 로그인과 최종 IP 등록은 사용자가 수행/승인" in prompt
    assert "preflight를 정확히 1회 재실행" in prompt
    assert "kiwoom_preflight_status" in prompt
    assert "kiwoom_public_ip" in prompt
    assert "kiwoom_recovery_status" in prompt
    assert "하네스 asof는 요청/운영일" in prompt
    assert "data_asof(최신 가용 데이터 기준일)" in prompt
    assert "최신 가용 데이터가 하네스 asof 전일이면 data_asof 기준으로 생성/게시" in prompt
    assert "장 마감/데이터 적재 전이라 DB/mart가 전 거래일까지라면" in prompt
    assert "market_model_input_daily_current.csv max asof_date" in prompt
    assert "market_forecast_ai_calibrated_daily_current.csv max asof_date" in prompt
    assert "run_daily_market_ai_training_update.py --profile operational --expected-asof <data_asof>" in prompt
    assert "`run_daily_market_ai_training_update.py --profile full` 또는 AI v1.1 학습/비교 단계는 WD02에서 실행하지 않는다" in prompt
    assert "blocked_needs_operational_mart_refresh" in prompt
    assert "daily market-context update 결과 report" in prompt
    assert "3축 그래프 입력 데이터가 data_asof 기준인지" in prompt
    assert "최신 가용 Quant handoff를 생성/검증" in prompt
    assert "run_market_analysis_pipeline.py --market KR --asof <data_asof>T19:00:00+09:00 --publish-remote" in prompt
    assert "publish_market_analysis_remote.py --asof <data_asof>T19:00:00+09:00" in prompt
    assert "validate_quantmarket_daily.py --expected-asof <data_asof> --check-remote" in prompt
    assert "blocked_needs_market_context_mart_refresh" in prompt
    assert "blocked_forecast_source_stale" in prompt
    assert "data_asof" in prompt
    assert "latest_available_data_asof" in prompt
    assert "market_context_mart_status" in prompt
    assert "forecast_current_status" in prompt
    assert "three_axis_graph_input_status" in prompt
    assert "quant_handoff_status" in prompt
    assert "market_remote_publish_status" in prompt
    assert "runner checkpoint" in prompt
    assert "중복 시작하지 않는다" in prompt
    assert "--start-at <last_completed_step 다음 단계>" in prompt


def test_wd03_prompt_blocks_stale_market_context_mart() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-07-07", "unit_prompt_weekday")
    state["current_stage_index"] = 2

    prompt = PROMPT.render_prompt(state)

    assert "timebox_minutes: 30" in prompt
    assert "기존 직접 지시의 '마켓분석 진행' 범위" in prompt
    assert "최신 가용 데이터 기준일(data_asof)" in prompt
    assert "publish_asof는 웹 게시 기준시각" in prompt
    assert "DB/mart가 전 거래일까지 있으면 data_asof 기준 분석" in prompt
    assert "WD01_QUANT_FRONT 완료 보고를 확인한다" in prompt
    assert "WD02_MARKET_COLLECT 완료 보고를 확인한다" in prompt
    assert "WD02 보고서의 data_asof/latest_available_data_asof" in prompt
    assert "publish_asof와 data_asof를 분리 보고한다" in prompt
    assert "하네스 asof와 data_asof가 달라도 최신 가용 거래일이면 stale로 보지 않는다" in prompt
    assert "WD02 보고서의 market_context_mart_status" in prompt
    assert "WD02 보고서의 market_remote_publish_status" in prompt
    assert "market_model_input_daily_current.csv max asof_date" in prompt
    assert "market_forecast_ai_calibrated_daily_current.csv max asof_date" in prompt
    assert "blocked_needs_market_context_mart_refresh" in prompt
    assert "blocked_forecast_source_stale" in prompt
    assert "data_asof 기준 market_analysis public payload를 생성" in prompt
    assert "QuantService handoff current" in prompt
    assert "quantservice_market_manifest.json" in prompt
    assert "api_v1_market_analysis_detail.json" in prompt
    assert "GCS 게시 증거를 필수 확인" in prompt
    assert "미게시 target만 current 또는 history-only 방식으로 한 번 게시" in prompt
    assert "remote publish report/history" in prompt
    assert "GCS history 검증 실패" in prompt
    assert "market_context_mart_status" in prompt
    assert "forecast_current_status" in prompt
    assert "three_axis_graph_input_status" in prompt
    assert "quantservice_handoff_status" in prompt
    assert "market_analysis_payload_status" in prompt
    assert "market_remote_publish_status" in prompt
    assert "remote_current_manifest_status" in prompt
    assert "validation_mode=current|history" in prompt
    assert "--validation-mode history" in prompt
    assert "--remote-publish-report <target remote publish report>" in prompt
    assert "--remote-history-only" in prompt
    assert "live current를 과거일로 재게시하거나 롤백하지 않는다" in prompt
    assert "--validation-mode current --check-remote" in prompt
    assert "WD02가 같은 target/data_asof의 remote publish report" in prompt
    assert "validated_target_asof" in prompt
    assert "validation_mode" in prompt


def test_wd04_prompt_requires_user_model_snapshot_freshness() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-07-07", "unit_prompt_weekday")
    state["current_stage_index"] = 3

    prompt = PROMPT.render_prompt(state)

    assert "timebox_minutes: 30" in prompt
    assert "--model-run-only --pipeline-mode daily_light --skip-remote-current-publish" in prompt
    assert "10분 제한을 적용하지 않는다" in prompt
    assert "timing report의 마지막 성공 command 이후" in prompt
    assert "장시간 모델 명령을 재실행하지 않는다" in prompt
    assert "model_scope_registry.yaml" in prompt
    assert "model_scope_gate_status" in prompt
    assert "model_version_scope_status" in prompt
    assert "이번 WD04의 운영 모델 범위는 Quant 1.0뿐이다" in prompt
    assert "operating_scope_contract`가 `legacy_static/inactive`" in prompt
    assert "selection freeze/readiness/candidate 산출물은 운영 scope 권한이 아니며" in prompt
    assert "최소 180 calendar days의 live shadow" in prompt
    assert "주간 26회 또는 월간 6회 결정" in prompt
    assert "가장 빠른 검토일은 2027-02-18" in prompt
    assert "operating_scope_source" in prompt
    assert "operating_scope_manifest_status" in prompt
    assert "model_revision_scope_status" in prompt
    assert "excluded_model_status" in prompt
    assert "review_model_status" in prompt
    assert "ai_learning_model_freshness_status" in prompt
    assert "S2_PIT_V01" in prompt
    assert "I-STOCK-STRONG-RSI-V01" in prompt
    assert "research_archive_excluded_from_default" in prompt
    assert "excluded_from_default" in prompt
    assert "REVIEW 상태 모델은 자동 제외하지 말고" in prompt
    assert "blocked_needs_ai_core_freshness_decision" in prompt
    assert "redbot_user_report_<profile>_<target_asof>.json" in prompt
    assert "user_model_snapshot_report.json" in prompt
    assert "user_model_holdings_history.json" in prompt
    assert "user_model_snapshot_status" in prompt
    assert "Model Performance Governance" in prompt
    assert "high_performance_models_to_expand" in prompt
    assert "low_performance_models_to_reduce_or_archive" in prompt
    assert "ai_models_to_refresh_or_downgrade" in prompt
    assert "new_model_research_candidates" in prompt
    assert "model_improvement_experiments" in prompt
    assert "expected_return_improvement_hypothesis" in prompt
    assert "keep`, `improve`, `review`, `downgrade_candidate`, `retire_candidate" in prompt
    assert "governance payload의 target asof와 underlying model evidence date를 분리" in prompt
    assert "validate_daily_pipeline_contract.py --asof <target_asof>" in prompt
    assert "validate_trading_sign_snapshots.py --asof <target_asof>" in prompt
    assert "38-chain 또는 해당 표준 체인의 완료" in prompt
    assert "한 번의 freshness inventory" in prompt
    assert "평일 AI live shadow의 표준 범위는 target_asof 단일 기준일" in prompt
    assert "historical `all` 재계산을 선택 복구로 추가하지 않는다" in prompt


def test_wd05_prompt_requires_portfolio_update_before_review() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-07-07", "unit_prompt_weekday")
    state["current_stage_index"] = 4

    prompt = PROMPT.render_prompt(state)

    assert "기준일자 투자 포트폴리오 업데이트" in prompt
    assert "D:\\Quant\\venv64\\Scripts\\python.exe D:\\QuantAnalysis\\portfolio_pipeline.py --asof <target_asof>" in prompt
    assert "--skip-gcs-publish`는 붙이지 않고" in prompt
    assert "QUANTANALYSIS_SKIP_GCS_PUBLISH=1" in prompt
    assert "investment_portfolio_latest.json" in prompt
    assert "investment_portfolio_latest.md" in prompt
    assert "analysis.db" in prompt
    assert "portfolio_runs" in prompt
    assert "Portfolio Performance Governance" in prompt
    assert "selection history, top10/top3" in prompt
    assert "rank4~10" in prompt
    assert "benchmark-relative" in prompt
    assert "source model attribution" in prompt
    assert "절대수익률과 지수 대비 성과를 분리" in prompt
    assert "top10 후보와 top3 후보" in prompt
    assert "top3_return_avg" in prompt
    assert "rank4_10_return_avg" in prompt
    assert "weak_model_combinations" in prompt
    assert "strong_model_combinations" in prompt
    assert "REVIEW/성과 저하 모델 후보" in prompt
    assert "improvement_candidates_for_validation" in prompt
    assert "admin/current/investment_portfolio_latest.json" in prompt
    assert "portfolio_gcs_publish_status" in prompt
    assert "needs_quantanalysis_portfolio_refresh" in prompt
    assert "portfolio_update_status" in prompt
    assert "investment_portfolio_current_status" in prompt
    assert "investment_portfolio_db_status" in prompt
    assert "selection_history_summary" in prompt
    assert "top10_performance" in prompt
    assert "top3_performance" in prompt
    assert "rank4_10_performance" in prompt
    assert "top3_vs_rank4_10_gap" in prompt
    assert "benchmark_relative_performance" in prompt
    assert "model_attribution_summary" in prompt
    assert "risk_flags" in prompt
    assert "policy_change_required" in prompt
    assert "improvement_candidates_no_policy_change" in prompt
    assert "publish_allowed_with_performance_warning" in prompt
    assert "handoff_to_weekend_research" in prompt
    assert "redbot_user_report_*" in prompt
    assert "WD04/WD06 이슈" in prompt
    assert "readonly/immutable 모드" in prompt
    assert "쓰기 가능한 Cloud SDK config 경로" in prompt
    assert "장기 성과 재계산을 추가로 시작하지 않는다" in prompt


def test_wd06_prompt_requires_validation_before_gcs_publish() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-07-07", "unit_prompt_weekday")
    state["current_stage_index"] = 5

    prompt = PROMPT.render_prompt(state)

    assert "stage_id: WD06_PRE_GCS_PUBLISH" in prompt
    assert "run_quant_validation_suite.py --asof <target_asof> --mode pre_gcs_publish" in prompt
    assert "publish_public_current_to_gcs.py" in prompt
    assert "pre_gcs_publish가 pass인 경우에만" in prompt
    assert "자동 매매, 자동 배포, 정책 변경은 하지 않는다" in prompt


def test_weekend_uses_weekend_only_scope() -> None:
    state = PROMPT.build_initial_state("weekend", "2026-06-26", "unit_prompt_weekend")

    stage_ids = [row["stage_id"] for row in state["stages"]]
    threads = [row["thread"] for row in state["stages"]]

    assert stage_ids == [
        "WE01_QUANT_WEEKEND_PIPELINE",
        "WE06_HARNESS_CLOSE",
    ]
    assert threads == ["Quant", "Quant"]


def test_weekend_quant_pipeline_scope_excludes_unsafe_actions() -> None:
    state = PROMPT.build_initial_state("weekend", "2026-06-26", "unit_prompt_weekend")
    prompt = PROMPT.render_prompt(state)

    assert "stage_id: WE01_QUANT_WEEKEND_PIPELINE" in prompt
    assert "timebox_minutes: 120" in prompt
    assert "model_scope_registry.yaml" in prompt
    assert "model_scope_gate_status" in prompt
    assert "model_version_scope_status" in prompt
    assert "이번 WE01의 운영 실행 및 운영 성능 거버넌스 범위는 Quant 1.0뿐이다" in prompt
    assert "Quant 1.2 frozen live-shadow의 Quant 1.0 baseline 대비 읽기 전용 성능 비교" in prompt
    assert "Quant 1.2 selection freeze/readiness는 읽기 전용 연구 evidence" in prompt
    assert "180일 live shadow, 주간 26회·월간 6회 결정" in prompt
    assert "가장 빠른 검토 가능일은 2027-02-18" in prompt
    assert "기존 frozen shadow의 비교 보고는 WE01에 포함" in prompt
    assert "Quant 1.2 후보는 frozen/immutable" in prompt
    assert "별도 Quant 1.3 후보 연구로 분리" in prompt
    assert "candidate_immutable_fingerprint_matches" in prompt
    assert "blocked_quant_1_2_immutable_fingerprint_mismatch" in prompt
    assert "candidate-minus-baseline 수익률/MDD/변동성/turnover" in prompt
    assert "waiting_live_metrics" in prompt
    assert "evaluate_quant1_2_forward_risk.py --asof <data_asof>" in prompt
    assert "blocked_needs_quant_1_2_shadow_refresh" in prompt
    assert "build_model_governance_review.py --run-id <run_id> --asof <data_asof>" in prompt
    assert "quant_1_2_vs_quant_1_0_live_comparison` 섹션" in prompt
    assert "Quant 1.2 비교 evidence의 stale/missing은 Quant 1.0 주말 운영 파이프라인 완료를 차단하지 않으며" in prompt
    assert "quant_1_0_operating_performance_status" in prompt
    assert "quant_1_2_live_shadow_comparison_status" in prompt
    assert "quant_1_2_vs_quant_1_0_model_comparison" in prompt
    assert "quant_1_2_live_gate_progress" in prompt
    assert "resolve된 `model_code`/`operating_revision`만 점검 범위" in prompt
    assert "excluded_model_status" in prompt
    assert "review_model_status" in prompt
    assert "ai_learning_model_freshness_status" in prompt
    assert "S2_PIT_V01" in prompt
    assert "I-STOCK-STRONG-RSI-V01" in prompt
    assert "research_archive_excluded_from_default" in prompt
    assert "excluded_from_default" in prompt
    assert "downgrade_or_redesign_candidate" in prompt
    assert "A operating core AI가 stale이면" in prompt
    assert "주말 모델/AI 검증 통합 파이프라인" in prompt
    assert "정책 변경 확정, 자동 publish는 하지 않는다" in prompt
    assert "asof: 2026-06-26" in prompt
    assert "주말 target_asof는 하네스 요청/운영일" in prompt
    assert "토요일·일요일·휴장일" in prompt
    assert "non_trading_day_binding: latest_available_trading_day" in prompt
    assert "target_asof와 data_asof가 달라도 stale 또는 blocked로 보지 않으며" in prompt
    assert "QuantMarket, QuantMarketData, QuantAnalysis 스레드로 handoff하지 않는다" in prompt
    assert "market remote publish, portfolio_pipeline.py, public current GCS publish를 실행하지 않는다" in prompt
    assert "asof_binding_status" in prompt
    assert "publish_scope_status" in prompt
    assert "Model Performance Governance" in prompt
    assert "high_performance_models_to_expand" in prompt
    assert "low_performance_models_to_reduce_or_archive" in prompt
    assert "ai_models_to_refresh_or_downgrade" in prompt
    assert "new_model_research_candidates" in prompt
    assert "model_improvement_experiments" in prompt
    assert "expected_return_improvement_hypothesis" in prompt
    assert "기존 운영 모델 대비 수익률 개선 가설" in prompt
    assert "helper_unknown_error: setup refresh had errors" in prompt
    assert "D:\\Quant\\tools\\pwsh\\pwsh.exe -NoProfile -Command" in prompt
    assert "주말 통합 파이프라인을 중복 시작하지 않는다" in prompt
    assert "Win32_Process ParentProcessId 체인" in prompt
    assert "독립 task 프로세스는 종료·중단·재시작하지 않고" in prompt


def test_summary_includes_total_and_stage_elapsed() -> None:
    state = PROMPT.build_initial_state("weekday", "2026-06-26", "unit_prompt_weekday")
    state["status"] = "completed"
    state["created_at"] = "2026-06-27T23:14:25"
    state["completed_at"] = "2026-06-28T01:16:27"
    state["stages"][0]["status"] = "completed"
    state["stages"][0]["started_at"] = "2026-06-27T23:14:25"
    state["stages"][0]["completed_at"] = "2026-06-27T23:27:43"

    summary = PROMPT.render_summary(state)

    assert "- total_elapsed: 2h 02m 02s" in summary
    assert "| order | stage_id | thread | status | started_at | completed_at | elapsed | report |" in summary
    assert "13m 18s" in summary
