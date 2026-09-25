from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

HARNESS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "harness"
sys.path.insert(0, str(HARNESS_DIR))

SPEC = importlib.util.spec_from_file_location("build_model_governance_review", HARNESS_DIR / "build_model_governance_review.py")
assert SPEC is not None
GOVERNANCE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GOVERNANCE)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_model_scope_registry_includes_governance_rules() -> None:
    registry_path = Path(__file__).resolve().parents[1] / "config" / "harness" / "model_scope_registry.yaml"
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry = data["model_scope_registry"]
    governance = registry["performance_governance"]
    version_boundary = registry["model_version_boundary"]
    scope_contract = registry["operating_scope_contract"]
    quant1_2_observation = registry["quant_1_2_parallel_performance_observation"]

    assert version_boundary["operating_model_version"] == "Quant 1.0"
    assert version_boundary["excluded_model_versions"] == ["Quant 1.1", "Quant 2.x"]
    assert "separate explicit version-specific instruction" in version_boundary["rules"][1]
    assert scope_contract["resolution_mode"] == "legacy_static"
    assert scope_contract["activation_state"] == "inactive"
    assert scope_contract["fail_closed"] is True
    assert scope_contract["quant_os_manifest"]["required_model_count"] == 6
    assert scope_contract["quant_os_manifest"]["required_schema_version"] == 1
    live_gate = scope_contract["quant_os_manifest"]["live_shadow_gate"]
    assert live_gate["frozen_asof"] == "2026-08-22"
    assert live_gate["minimum_calendar_days"] == 180
    assert live_gate["earliest_review_date"] == "2027-02-18"
    assert live_gate["candidate_requirements"]["S2"]["minimum_decision_count"] == 26
    assert live_gate["candidate_requirements"]["S4"]["minimum_decision_count"] == 6
    assert scope_contract["quant_os_manifest"]["pinned_models"] == {}

    assert quant1_2_observation["state"] == "research_shadow_only"
    assert quant1_2_observation["active_scope_impact"] == "none"
    assert quant1_2_observation["candidate_version_state"] == "frozen_immutable"
    assert quant1_2_observation["semantic_change_target_version"] == "Quant 1.3"
    assert quant1_2_observation["candidate_model_codes"] == [
        "S2",
        "S3",
        "S3_CORE2",
        "S3_ACCEL_V01",
        "S4",
        "S5",
        "S6",
    ]
    assert governance["final_goal"].startswith("Improve the user's investment returns")
    assert "keep" in governance["decision_labels"]["strategy_models"]
    assert "downgrade_candidate" in governance["decision_labels"]["strategy_models"]
    assert "refresh_needed" in governance["decision_labels"]["ai_learning_models"]
    assert "reports/harness_model_governance/<run_id>/model_governance_review.json" in governance["default_report_outputs"]


def test_build_model_governance_review_from_sample_payloads(tmp_path: Path) -> None:
    registry_path = tmp_path / "model_scope_registry.yaml"
    internal_path = tmp_path / "internal_model_validation_current.json"
    ai_path = tmp_path / "ai_learning_models_current.json"
    out_dir = tmp_path / "out"

    registry_path.write_text(
        yaml.safe_dump(
            {
                "model_scope_registry": {
                    "ai_learning_models": {
                        "operating_core": ["AI-CORE-V01"],
                        "observation": ["AI-OBS-V01"],
                        "research_archive_excluded_from_default": ["AI-ARCHIVE-V01"],
                        "excluded_from_default": [],
                    }
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    _write_json(
        internal_path,
        {
            "as_of_date": "2026-07-08",
            "models": [
                {
                    "model_code": "S4",
                    "review_state": "PASS",
                    "recommended_action": "KEEP",
                    "validation_score": {"total_score": 91.2, "grade": "A"},
                    "current_backtest_metrics": {"trailing_1y": 0.44, "mdd_1y": -0.12},
                    "current_live_metrics": {
                        "one_month_avg_return": 0.04,
                        "one_month_win_rate": 0.61,
                        "one_month_avg_mdd": -0.08,
                        "sample_confidence": "high",
                    },
                },
                {
                    "model_code": "S2",
                    "review_state": "REVIEW",
                    "recommended_action": "MODEL_REVIEW_OR_DOWNGRADE_CANDIDATE",
                    "review_reasons": ["live_current_avg_return actual=-0.1 target=0.0"],
                    "validation_score": {"total_score": 76.2, "grade": "C"},
                    "current_backtest_metrics": {"trailing_1y": 0.77, "mdd_1y": -0.2},
                    "current_live_metrics": {
                        "one_month_avg_return": 0.01,
                        "one_month_win_rate": 0.37,
                        "one_month_avg_mdd": -0.2,
                        "sample_confidence": "high",
                    },
                },
            ],
        },
    )
    _write_json(
        ai_path,
        {
            "as_of_date": "2026-07-04",
            "models": [
                {"model_code": "AI-CORE-V01", "status": "available", "as_of_date": "2026-07-04", "summary": {}},
                {"model_code": "AI-ARCHIVE-V01", "status": "available", "as_of_date": "2026-07-08", "summary": {}},
            ],
        },
    )

    review = GOVERNANCE.build_review(
        run_id="unit_governance",
        asof="2026-07-08",
        registry_path=registry_path,
        internal_validation_path=internal_path,
        ai_learning_path=ai_path,
        quant1_2_requirements_path=tmp_path / "missing_quant1_2_requirements.json",
        quant1_2_shadow_root=tmp_path / "missing_forward_shadow",
        quant1_2_readiness_path=tmp_path / "missing_readiness.json",
    )
    outputs = GOVERNANCE.write_review(review, out_dir)

    assert review["summary"]["strategy_model_count"] == 2
    assert [row["model_code"] for row in review["high_performance_models_to_expand"]] == ["S4"]
    assert [row["model_code"] for row in review["low_performance_models_to_reduce_or_archive"]] == ["S2"]
    assert review["ai_models_to_refresh_or_downgrade"] == []
    assert review["new_model_research_candidates"]
    assert review["quant_1_2_vs_quant_1_0_live_comparison"]["status"] == "not_configured"
    assert review["quant_1_2_vs_quant_1_0_live_comparison"]["active_scope_impact"] == "none"
    assert Path(outputs["json"]).exists()
    assert Path(outputs["markdown"]).exists()
    assert "Harness Model Governance Review" in Path(outputs["markdown"]).read_text(encoding="utf-8")
    assert "Quant 1.2 vs Quant 1.0 Live Shadow" in Path(outputs["markdown"]).read_text(encoding="utf-8")


def test_quant1_2_live_comparison_uses_frozen_baseline_candidate_metrics(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    shadow_root = tmp_path / "forward_shadow"
    readiness_path = tmp_path / "readiness.json"
    model_dir = shadow_root / "S2"
    model_dir.mkdir(parents=True)
    _write_json(
        requirements_path,
        {
            "live_review_policy": {
                "frozen_asof": "2026-08-22",
                "minimum_calendar_days": 180,
                "earliest_review_date": "2027-02-18",
                "candidate_model_codes": ["S2"],
            },
            "models": {
                "S2": {
                    "candidate_id": "s2_v12_candidate",
                    "forward_gate": {
                        "minimum_calendar_days": 180,
                        "minimum_decision_count": 26,
                    },
                }
            },
        },
    )
    _write_json(
        model_dir / "risk_evaluation.json",
        {
            "model_code": "S2",
            "candidate_id": "s2_v12_candidate",
            "asof": "2027-02-18",
            "frozen_asof": "2026-08-22",
            "status": "passed",
            "forward_gate": {
                "required": {"minimum_calendar_days": 180, "minimum_decision_count": 26},
                "actual": {"calendar_days": 180, "decision_count": 26},
                "passed": True,
            },
            "baseline": {
                "total_return": 0.12,
                "mdd": -0.08,
                "annual_vol": 0.16,
                "avg_turnover": 0.20,
            },
            "candidate": {
                "total_return": 0.18,
                "mdd": -0.07,
                "annual_vol": 0.15,
                "avg_turnover": 0.22,
            },
            "deltas": {
                "total_return": 0.06,
                "mdd": 0.01,
                "annual_vol": -0.01,
                "turnover_increase_ratio": 0.10,
            },
            "checks": {"total_return_delta": True, "mdd": True},
            "operating_mutation": False,
        },
    )
    _write_json(
        model_dir / "observations.json",
        {
            "candidate_id": "s2_v12_candidate",
            "frozen_asof": "2026-08-22",
            "last_asof": "2027-02-18",
            "decision_count": 26,
            "operating_mutation": False,
        },
    )
    _write_json(
        readiness_path,
        {
            "status": "ready_for_manual_adoption_review",
            "ready_model_count": 8,
            "total_model_count": 8,
            "models": {
                "S2": {
                    "gates": {"candidate_immutable_fingerprint_matches": True}
                }
            },
        },
    )

    comparison = GOVERNANCE._quant1_2_comparison(
        requirements_path=requirements_path,
        shadow_root=shadow_root,
        readiness_path=readiness_path,
    )

    assert comparison["status"] == "comparison_available"
    assert comparison["active_scope_impact"] == "none"
    row = comparison["models"][0]
    assert row["quant_1_0_total_return"] == 0.12
    assert row["quant_1_2_total_return"] == 0.18
    assert row["total_return_delta"] == 0.06
    assert row["calendar_progress_ratio"] == 1.0
    assert row["decision_progress_ratio"] == 1.0
    assert row["candidate_immutable_fingerprint_matches"] is True
    assert row["semantic_change_target_version"] == "Quant 1.3"


def test_quant1_2_live_comparison_rejects_immutable_fingerprint_mismatch(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    shadow_root = tmp_path / "forward_shadow"
    readiness_path = tmp_path / "readiness.json"
    model_dir = shadow_root / "S2"
    model_dir.mkdir(parents=True)
    _write_json(
        requirements_path,
        {
            "live_review_policy": {
                "frozen_asof": "2026-08-22",
                "candidate_model_codes": ["S2"],
            },
            "models": {"S2": {"candidate_id": "candidate", "forward_gate": {}}},
        },
    )
    _write_json(
        model_dir / "risk_evaluation.json",
        {
            "candidate_id": "candidate",
            "frozen_asof": "2026-08-22",
            "baseline": {"total_return": 0.1},
            "candidate": {"total_return": 0.2},
            "operating_mutation": False,
        },
    )
    _write_json(
        readiness_path,
        {
            "status": "blocked_research_only",
            "models": {
                "S2": {
                    "gates": {"candidate_immutable_fingerprint_matches": False}
                }
            },
        },
    )

    comparison = GOVERNANCE._quant1_2_comparison(
        requirements_path=requirements_path,
        shadow_root=shadow_root,
        readiness_path=readiness_path,
    )

    row = comparison["models"][0]
    assert row["comparison_status"] == "blocked_quant_1_2_immutable_fingerprint_mismatch"
    assert row["quant_1_0_total_return"] is None
    assert row["quant_1_2_total_return"] is None
    assert "immutable_fingerprint_mismatch:S2" in comparison["known_issues"]
