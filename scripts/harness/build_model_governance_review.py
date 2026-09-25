from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from harness_common import ROOT, now_stamp, read_json, read_yaml, write_json
from retirement_policy import retired_model

REGISTRY_PATH = ROOT / "config" / "harness" / "model_scope_registry.yaml"
ADMIN_CURRENT = ROOT / "service_platform" / "web" / "admin_data" / "current"
INTERNAL_VALIDATION_PATH = ADMIN_CURRENT / "internal_model_validation_current.json"
AI_LEARNING_PATH = ADMIN_CURRENT / "ai_learning_models_current.json"
OUT_ROOT = ROOT / "reports" / "harness_model_governance"
QUANT1_2_REQUIREMENTS_PATH = ROOT / "config" / "quant1_2" / "operational_readiness_requirements.json"
QUANT1_2_SHADOW_ROOT = ROOT / "reports" / "quant1_2" / "forward_shadow"
QUANT1_2_READINESS_ROOT = ROOT / "reports" / "quant1_2" / "operational_readiness"


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for token in (text[:10], text):
        try:
            return date.fromisoformat(token)
        except ValueError:
            continue
    return None


def _days_stale(asof: str, value: Any) -> int | None:
    target = _parse_date(asof)
    actual = _parse_date(value)
    if target is None or actual is None:
        return None
    return (target - actual).days


def _strategy_decision(model: dict[str, Any]) -> str:
    state = str(model.get("review_state") or "").upper()
    score = ((model.get("validation_score") or {}).get("total_score"))
    try:
        score_value = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_value = None
    if state == "PASS":
        return "keep"
    if state == "WATCH":
        return "improve"
    if state == "REVIEW":
        return "retire_candidate" if score_value is not None and score_value < 60 else "downgrade_candidate"
    return "review"


def _ai_registry_bucket(model_code: str, registry: dict[str, Any]) -> str:
    ai_cfg = (((registry.get("model_scope_registry") or {}).get("ai_learning_models")) or {})
    buckets = {
        "operating_core": ai_cfg.get("operating_core") or [],
        "observation": ai_cfg.get("observation") or [],
        "research_archive": ai_cfg.get("research_archive_excluded_from_default") or [],
        "excluded": ai_cfg.get("excluded_from_default") or [],
    }
    for name, values in buckets.items():
        if model_code in {str(value) for value in values}:
            return name
    return "unknown"


def _ai_decision(model: dict[str, Any], registry_bucket: str, stale_days: int | None) -> str:
    if registry_bucket in {"research_archive", "excluded"}:
        return "archive_candidate"
    if stale_days is not None and stale_days > 0:
        return "refresh_needed"
    if registry_bucket == "operating_core":
        return "operating_core"
    return "observation"


def _strategy_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in payload.get("models") or []:
        if not isinstance(model, dict):
            continue
        if retired_model(str(model.get("model_code") or "")):
            continue
        score = model.get("validation_score") or {}
        backtest = model.get("current_backtest_metrics") or {}
        live = model.get("current_live_metrics") or {}
        decision = _strategy_decision(model)
        rows.append(
            {
                "model_code": model.get("model_code"),
                "review_state": model.get("review_state"),
                "governance_decision": decision,
                "recommended_action": model.get("recommended_action"),
                "total_score": score.get("total_score"),
                "grade": score.get("grade"),
                "backtest_1y_return": backtest.get("trailing_1y"),
                "backtest_mdd_1y": backtest.get("mdd_1y"),
                "live_1m_avg_return": live.get("one_month_avg_return"),
                "live_1m_win_rate": live.get("one_month_win_rate"),
                "live_1m_avg_mdd": live.get("one_month_avg_mdd"),
                "sample_confidence": live.get("sample_confidence"),
                "review_reasons": model.get("review_reasons") or [],
                "qualitative_assessment_ko": model.get("qualitative_assessment_ko"),
            }
        )
    return rows


def _ai_rows(payload: dict[str, Any], registry: dict[str, Any], asof: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in payload.get("models") or []:
        if not isinstance(model, dict):
            continue
        model_code = str(model.get("model_code") or "")
        model_asof = model.get("as_of_date") or model.get("performance_asof_date")
        stale_days = _days_stale(asof, model_asof)
        registry_bucket = _ai_registry_bucket(model_code, registry)
        rows.append(
            {
                "model_code": model_code,
                "model_role": model.get("model_role"),
                "status": model.get("status"),
                "registry_bucket": registry_bucket,
                "governance_decision": _ai_decision(model, registry_bucket, stale_days),
                "as_of_date": model.get("as_of_date"),
                "performance_asof_date": model.get("performance_asof_date"),
                "stale_days": stale_days,
                "primary_metrics": ((model.get("metadata") or {}).get("primary_metrics"))
                or ((model.get("display_metadata") or {}).get("primary_metrics"))
                or [],
                "summary": model.get("summary") or {},
            }
        )
    return rows


def _new_model_candidates(strategy_rows: list[dict[str, Any]], ai_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weak_strategy = [row for row in strategy_rows if row["governance_decision"] in {"downgrade_candidate", "retire_candidate"}]
    stale_ai = [row for row in ai_rows if row["governance_decision"] == "refresh_needed"]
    candidates: list[dict[str, Any]] = []
    if weak_strategy:
        candidates.append(
            {
                "candidate": "strategy_replacement_or_meta_router",
                "reason": "Some active strategy models are below live-first governance thresholds.",
                "target_models": [row["model_code"] for row in weak_strategy],
                "expected_return_improvement_hypothesis": "Improve live 1M average return and win-rate while reducing weak-model exposure.",
            }
        )
    if stale_ai:
        candidates.append(
            {
                "candidate": "ai_refresh_or_new_feature_overlay",
                "reason": "Some AI learning models are stale versus target asof.",
                "target_models": [row["model_code"] for row in stale_ai],
                "expected_return_improvement_hypothesis": "Refresh stale AI signals and test whether updated features improve candidate ranking and downside filtering.",
            }
        )
    return candidates


def _strategy_research_observation_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = ((registry.get("model_scope_registry") or {}).get("strategy_research_observation") or {})
    rows: list[dict[str, Any]] = []
    for item in cfg.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "model_code": item.get("model_code"),
                "model_family": item.get("model_family"),
                "role": item.get("role"),
                "state": item.get("state"),
                "baseline": item.get("baseline"),
                "evidence_state": item.get("evidence_state"),
                "observation_priority": item.get("observation_priority"),
                "performance_focus": item.get("performance_focus"),
                "evidence_files": item.get("evidence_files") or [],
            }
        )
    return rows


def _safe_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _latest_readiness_path(root: Path) -> Path | None:
    candidates = sorted(
        (path for path in root.glob("*/readiness_report.json") if path.is_file()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _ratio(actual: Any, required: Any) -> float | None:
    try:
        actual_value = float(actual)
        required_value = float(required)
    except (TypeError, ValueError):
        return None
    if required_value <= 0:
        return 1.0
    return min(max(actual_value / required_value, 0.0), 1.0)


def _quant1_2_comparison(
    *,
    requirements_path: Path,
    shadow_root: Path,
    readiness_path: Path | None,
) -> dict[str, Any]:
    requirements = _safe_json(requirements_path)
    if requirements is None:
        return {
            "status": "not_configured",
            "active_scope_impact": "none",
            "models": [],
            "known_issues": [f"missing_or_invalid_requirements:{requirements_path}"],
        }
    policy = requirements.get("live_review_policy") or {}
    candidate_codes = [str(item) for item in policy.get("candidate_model_codes") or []]
    readiness_file = readiness_path or _latest_readiness_path(QUANT1_2_READINESS_ROOT)
    readiness = _safe_json(readiness_file) if readiness_file else None
    rows: list[dict[str, Any]] = []
    known_issues: list[str] = []
    metrics_available_count = 0
    for model_code in candidate_codes:
        model_cfg = (requirements.get("models") or {}).get(model_code) or {}
        readiness_model = ((readiness or {}).get("models") or {}).get(model_code) or {}
        immutable_fingerprint_matches = (readiness_model.get("gates") or {}).get(
            "candidate_immutable_fingerprint_matches"
        )
        risk_path = shadow_root / model_code / "risk_evaluation.json"
        observation_path = shadow_root / model_code / "observations.json"
        risk = _safe_json(risk_path)
        observation_payload = _safe_json(observation_path)
        observation = observation_payload or {}
        if risk is None:
            known_issues.append(f"missing_or_invalid_risk_evaluation:{model_code}")
            risk = {}
        provenance_issues: list[str] = []
        if immutable_fingerprint_matches is not True:
            provenance_issues.append(f"immutable_fingerprint_mismatch:{model_code}")
        expected_candidate_id = model_cfg.get("candidate_id")
        if risk and risk.get("operating_mutation") is not False:
            provenance_issues.append(f"risk_evaluation_not_research_only:{model_code}")
        if observation_payload and observation_payload.get("operating_mutation") is not False:
            provenance_issues.append(f"observation_not_research_only:{model_code}")
        if risk and risk.get("candidate_id") != expected_candidate_id:
            provenance_issues.append(f"risk_candidate_id_mismatch:{model_code}")
        if observation_payload and observation_payload.get("candidate_id") != expected_candidate_id:
            provenance_issues.append(f"observation_candidate_id_mismatch:{model_code}")
        if risk and risk.get("frozen_asof") != policy.get("frozen_asof"):
            provenance_issues.append(f"risk_frozen_asof_mismatch:{model_code}")
        known_issues.extend(provenance_issues)
        baseline = risk.get("baseline") if isinstance(risk.get("baseline"), dict) else {}
        candidate = risk.get("candidate") if isinstance(risk.get("candidate"), dict) else {}
        if provenance_issues:
            baseline = {}
            candidate = {}
        deltas = risk.get("deltas") if isinstance(risk.get("deltas"), dict) else {}
        forward = risk.get("forward_gate") if isinstance(risk.get("forward_gate"), dict) else {}
        required = forward.get("required") if isinstance(forward.get("required"), dict) else model_cfg.get("forward_gate") or {}
        actual = forward.get("actual") if isinstance(forward.get("actual"), dict) else {}
        if not actual:
            actual = {
                "calendar_days": 0,
                "decision_count": observation.get("decision_count", 0),
                "resolved_labels": observation.get("resolved_labels", 0),
            }
        has_metrics = bool(baseline) and bool(candidate)
        if has_metrics:
            metrics_available_count += 1
        comparison_status = str(risk.get("status") or "missing_risk_evaluation")
        if immutable_fingerprint_matches is not True:
            comparison_status = "blocked_quant_1_2_immutable_fingerprint_mismatch"
        elif provenance_issues:
            comparison_status = "invalid_evidence_provenance"
        elif not has_metrics and risk:
            comparison_status = "waiting_live_metrics"
        row = {
            "model_code": model_code,
            "quant_1_0_baseline_revision": "quant_1_0_canonical",
            "quant_1_2_candidate_id": model_cfg.get("candidate_id") or risk.get("candidate_id"),
            "operating_scope_status": "research_shadow_only_not_operating",
            "candidate_version_state": "frozen_immutable",
            "candidate_immutable_fingerprint_matches": immutable_fingerprint_matches,
            "semantic_change_target_version": "Quant 1.3",
            "comparison_status": comparison_status,
            "frozen_asof": risk.get("frozen_asof") or observation.get("frozen_asof") or policy.get("frozen_asof"),
            "evidence_asof": risk.get("asof") or observation.get("last_asof"),
            "calendar_days": actual.get("calendar_days", 0),
            "required_calendar_days": required.get("minimum_calendar_days"),
            "calendar_progress_ratio": _ratio(actual.get("calendar_days", 0), required.get("minimum_calendar_days")),
            "decision_count": actual.get("decision_count", observation.get("decision_count", 0)),
            "required_decision_count": required.get("minimum_decision_count"),
            "decision_progress_ratio": _ratio(
                actual.get("decision_count", observation.get("decision_count", 0)),
                required.get("minimum_decision_count"),
            ),
            "quant_1_0_total_return": baseline.get("total_return"),
            "quant_1_2_total_return": candidate.get("total_return"),
            "total_return_delta": deltas.get("total_return"),
            "quant_1_0_mdd": baseline.get("mdd"),
            "quant_1_2_mdd": candidate.get("mdd"),
            "mdd_delta": deltas.get("mdd"),
            "quant_1_0_annual_vol": baseline.get("annual_vol"),
            "quant_1_2_annual_vol": candidate.get("annual_vol"),
            "annual_vol_delta": deltas.get("annual_vol"),
            "quant_1_0_avg_turnover": baseline.get("avg_turnover"),
            "quant_1_2_avg_turnover": candidate.get("avg_turnover"),
            "turnover_increase_ratio": deltas.get("turnover_increase_ratio"),
            "risk_gate_status": risk.get("status"),
            "risk_checks": risk.get("checks") or {},
            "evidence_files": [str(risk_path), str(observation_path)],
        }
        rows.append(row)
    if not rows:
        status = "not_configured"
    elif metrics_available_count == len(rows):
        status = "comparison_available"
    elif metrics_available_count:
        status = "partial_comparison_available"
    else:
        status = "waiting_live_evidence"
    return {
        "status": status,
        "active_scope_impact": "none",
        "operating_baseline": "Quant 1.0 canonical",
        "candidate_scope": "Quant 1.2 frozen research shadow",
        "earliest_review_date": policy.get("earliest_review_date"),
        "minimum_calendar_days": policy.get("minimum_calendar_days"),
        "model_count": len(rows),
        "metrics_available_count": metrics_available_count,
        "readiness_status": readiness.get("status") if readiness else "missing",
        "readiness_ready_model_count": readiness.get("ready_model_count") if readiness else None,
        "readiness_total_model_count": readiness.get("total_model_count") if readiness else None,
        "requirements_path": str(requirements_path),
        "readiness_path": str(readiness_file) if readiness_file else None,
        "models": rows,
        "known_issues": known_issues,
    }


def build_review(
    *,
    run_id: str,
    asof: str,
    registry_path: Path = REGISTRY_PATH,
    internal_validation_path: Path = INTERNAL_VALIDATION_PATH,
    ai_learning_path: Path = AI_LEARNING_PATH,
    quant1_2_requirements_path: Path = QUANT1_2_REQUIREMENTS_PATH,
    quant1_2_shadow_root: Path = QUANT1_2_SHADOW_ROOT,
    quant1_2_readiness_path: Path | None = None,
) -> dict[str, Any]:
    registry = read_yaml(registry_path)
    internal = read_json(internal_validation_path)
    strategy_rows = _strategy_rows(internal)
    # Current AI files are historical archives after retirement, not required inputs.
    ai_rows = []
    high_perf = [row for row in strategy_rows if row["governance_decision"] in {"keep", "improve"}]
    low_perf = [row for row in strategy_rows if row["governance_decision"] in {"downgrade_candidate", "retire_candidate"}]
    ai_refresh = [row for row in ai_rows if row["governance_decision"] in {"refresh_needed", "archive_candidate"}]
    new_candidates = _new_model_candidates(strategy_rows, ai_rows)
    research_observation = _strategy_research_observation_rows(registry)
    quant1_2_comparison = _quant1_2_comparison(
        requirements_path=quant1_2_requirements_path,
        shadow_root=quant1_2_shadow_root,
        readiness_path=quant1_2_readiness_path,
    )
    return {
        "source_name": "harness_model_governance_review",
        "schema_version": "2026-08-22.v2",
        "run_id": run_id,
        "asof": asof,
        "generated_at": now_stamp(),
        "purpose": "Consolidate model performance governance inputs for Quant Model thread direction. This report does not change model state.",
        "inputs": {
            "model_scope_registry": str(registry_path),
            "internal_model_validation_current": str(internal_validation_path),
            "ai_learning_models_current": None,
            "internal_validation_as_of_date": internal.get("as_of_date"),
            "ai_learning_as_of_date": None,
            "quant1_2_requirements": str(quant1_2_requirements_path),
            "quant1_2_readiness": quant1_2_comparison.get("readiness_path"),
        },
        "summary": {
            "strategy_model_count": len(strategy_rows),
            "ai_learning_model_count": len(ai_rows),
            "high_performance_models_to_expand_count": len(high_perf),
            "low_performance_models_to_reduce_or_archive_count": len(low_perf),
            "ai_models_to_refresh_or_downgrade_count": len(ai_refresh),
            "new_model_research_candidate_count": len(new_candidates),
            "strategy_research_observation_count": len(research_observation),
            "quant1_2_comparison_model_count": quant1_2_comparison.get("model_count", 0),
            "quant1_2_metrics_available_count": quant1_2_comparison.get("metrics_available_count", 0),
        },
        "strategy_models": strategy_rows,
        "ai_learning_models": ai_rows,
        "high_performance_models_to_expand": high_perf,
        "low_performance_models_to_reduce_or_archive": low_perf,
        "ai_models_to_refresh_or_downgrade": ai_refresh,
        "new_model_research_candidates": new_candidates,
        "strategy_research_observation": research_observation,
        "quant_1_2_vs_quant_1_0_live_comparison": quant1_2_comparison,
        "model_improvement_experiments": [
            {
                "experiment": "validate_high_performance_model_expansion",
                "success_criteria": "Higher live 1M average return or win-rate without worse MDD/turnover.",
                "target_models": [row["model_code"] for row in high_perf],
            },
            {
                "experiment": "weak_model_reduction_or_replacement",
                "success_criteria": "Reduced exposure to REVIEW models improves portfolio return/risk profile.",
                "target_models": [row["model_code"] for row in low_perf],
            },
        ],
        "expected_return_improvement_hypothesis": [
            "Expanding models that pass live-first governance should improve realized return quality if drawdown and turnover remain controlled.",
            "Reducing REVIEW models should lower weak-signal drag and improve hit-rate consistency.",
            "Retired AI/T signals are excluded; historical evidence does not authorize current consumption.",
        ],
        "next_quant_model_instructions": [
            "Confirm the governance decision for each strategy model and report keep/improve/downgrade/retire candidates with evidence.",
            "Do not refresh retired AI/T models; preserve historical records and validate surviving non-AI inputs.",
            "Design new model research only when it has an explicit return, drawdown, hit-rate, turnover, or regime-stability improvement hypothesis.",
            "Do not promote, downgrade, retire, or change policy without explicit harness/user approval.",
            "Review continuous_observation strategy candidates beside active models, without adding them to operating allocation or model scope.",
            "Review Quant 1.2 frozen live-shadow performance against the same-model Quant 1.0 canonical baseline, while keeping Quant 1.2 outside operating scope and publish inputs.",
        ],
    }


def render_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# Harness Model Governance Review",
        "",
        f"- run_id: `{review['run_id']}`",
        f"- asof: `{review['asof']}`",
        f"- generated_at: `{review['generated_at']}`",
        "- state_change: `not_performed`",
        "",
        "## Summary",
        "",
    ]
    for key, value in (review.get("summary") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Strategy Models", "", "| model | state | decision | score | live 1M return | win rate |", "|---|---|---|---:|---:|---:|"])
    for row in review.get("strategy_models") or []:
        lines.append(
            f"| {row.get('model_code')} | {row.get('review_state')} | {row.get('governance_decision')} | "
            f"{row.get('total_score')} | {row.get('live_1m_avg_return')} | {row.get('live_1m_win_rate')} |"
        )
    lines.extend(["", "## AI Learning Models", "", "| model | bucket | decision | asof | stale_days |", "|---|---|---|---|---:|"])
    for row in review.get("ai_learning_models") or []:
        lines.append(
            f"| {row.get('model_code')} | {row.get('registry_bucket')} | {row.get('governance_decision')} | "
            f"{row.get('as_of_date') or row.get('performance_asof_date')} | {row.get('stale_days')} |"
        )
    lines.extend(["", "## Strategy Research Observation", "", "| model | role | state | evidence |", "|---|---|---|---|"])
    for row in review.get("strategy_research_observation") or []:
        lines.append(
            f"| {row.get('model_code')} | {row.get('role')} | {row.get('state')} | {row.get('evidence_state')} |"
        )
    comparison = review.get("quant_1_2_vs_quant_1_0_live_comparison") or {}
    lines.extend(
        [
            "",
            "## Quant 1.2 vs Quant 1.0 Live Shadow",
            "",
            f"- status: `{comparison.get('status')}`",
            f"- active_scope_impact: `{comparison.get('active_scope_impact')}`",
            f"- earliest_review_date: `{comparison.get('earliest_review_date')}`",
            "",
            "| model | status | days | decisions | Q1.0 return | Q1.2 return | delta | Q1.0 MDD | Q1.2 MDD |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in comparison.get("models") or []:
        lines.append(
            f"| {row.get('model_code')} | {row.get('comparison_status')} | "
            f"{row.get('calendar_days')}/{row.get('required_calendar_days')} | "
            f"{row.get('decision_count')}/{row.get('required_decision_count')} | "
            f"{row.get('quant_1_0_total_return')} | {row.get('quant_1_2_total_return')} | "
            f"{row.get('total_return_delta')} | {row.get('quant_1_0_mdd')} | {row.get('quant_1_2_mdd')} |"
        )
    lines.extend(["", "## Next Quant Model Instructions", ""])
    for item in review.get("next_quant_model_instructions") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_review(review: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "model_governance_review.json"
    md_path = out_dir / "model_governance_review.md"
    write_json(json_path, review)
    md_path.write_text(render_markdown(review), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build harness model performance governance review.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--asof", required=True)
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    parser.add_argument("--internal-validation", default=str(INTERNAL_VALIDATION_PATH))
    parser.add_argument("--ai-learning", default=str(AI_LEARNING_PATH))
    parser.add_argument("--quant1-2-requirements", default=str(QUANT1_2_REQUIREMENTS_PATH))
    parser.add_argument("--quant1-2-shadow-root", default=str(QUANT1_2_SHADOW_ROOT))
    parser.add_argument("--quant1-2-readiness", default="")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()
    review = build_review(
        run_id=args.run_id,
        asof=args.asof,
        registry_path=Path(args.registry),
        internal_validation_path=Path(args.internal_validation),
        ai_learning_path=Path(args.ai_learning),
        quant1_2_requirements_path=Path(args.quant1_2_requirements),
        quant1_2_shadow_root=Path(args.quant1_2_shadow_root),
        quant1_2_readiness_path=Path(args.quant1_2_readiness) if args.quant1_2_readiness else None,
    )
    out_dir = Path(args.out_dir) if args.out_dir else OUT_ROOT / args.run_id
    outputs = write_review(review, out_dir)
    print(json.dumps({"status": "ok", "outputs": outputs, "summary": review["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
