"""Isolated permanent-retirement regression tests; never execute a real cycle."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/harness"))
import build_model_governance_review as governance  # noqa: E402
import prompt_handoff_cycle as cycle  # noqa: E402
from harness_common import command_matches_blocked_pattern  # noqa: E402
from public_publish_guard import reject_legacy_public_write  # noqa: E402
from retirement_policy import RETIRED_TRAINING_SCRIPTS  # noqa: E402


@pytest.mark.parametrize("script", sorted(RETIRED_TRAINING_SCRIPTS))
@pytest.mark.parametrize("invocation", [
    '"D:\\Quant\\venv64\\Scripts\\python.exe" "D:\\Quant\\scripts\\{script}"',
    "python -m scripts.{module}",
])
def test_reviewed_training_entrypoints_rejected(script, invocation):
    command = invocation.format(script=script, module=script[:-3])
    assert "quant1_ai_retired" in command_matches_blocked_pattern(command, {"blocked_patterns": []})


@pytest.mark.parametrize("command", [
    "python -m src.models.valuation_ai.train_model",
    'python -m "src.models.valuation_ai.train_model" --help',
    "python -msrc.models.valuation_ai.train_model",
    'python "D:\\Quant\\src\\models\\valuation_ai\\train_model.py"',
])
def test_valuation_training_module_and_file_rejected(command):
    assert "quant1_ai_retired" in command_matches_blocked_pattern(command, {"blocked_patterns": []})


@pytest.mark.parametrize("model", ["T-STOCK-V01", "T_STOCK_V01", "T-ETF-V01",
                                  "AI-GROWTH-VALUATION-V01"])
def test_old_active_registry_and_manifest_cannot_revive_ai(tmp_path, model):
    registry = cycle._scope_registry()
    registry["strategy_models"]["active_operational"].append(model)
    contract = registry["operating_scope_contract"]
    contract.update(resolution_mode="quant_os_manifest", activation_state="active")
    contract["quant_os_manifest"]["required_model_codes"].append(model)
    contract["quant_os_manifest"]["required_model_count"] = 7
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"model_scope_registry": registry}), encoding="utf8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"models": {model: {"model_code": model}}}), encoding="utf8")
    result = cycle.resolve_operating_scope(path, manifest)
    assert not result["manifest_activation_eligible"]
    assert not any(cycle.retired_model(x["model_code"]) for x in result["active_models"])
    assert any("retired_model_in_manifest" in b for b in result["activation_blockers"])


@pytest.mark.parametrize("command", [
    "python run_t_stock_v01_operational_refresh.py",
    "python build_ai_overlay_v01.py",
    "python run_daily_quant_pipeline.py --include-ai-research",
    "python build_e_series_etf_sleeve_selection.py",
])
def test_old_approved_ai_commands_are_blocked(command):
    assert "quant1_ai_retired" in command_matches_blocked_pattern(command, {"blocked_patterns": []})


@pytest.mark.parametrize("command", [
    "python collect_etf_distributions.py", "python build_e_series_etf_mart_v2.py",
    "python build_e_series_etf_total_return_adjustment.py",
    "python run_backtest_v5.py --model S2",
    "python run_backtest_v5.py --model S3",
    "python build_s3_price_features_daily.py",
    "python run_sai_s1_stock_alpha_v01_research.py",
    "python -m scripts.run_sai_s1_stock_alpha_v01_research",
    "python src/models/some_other_model/train_model.py",
    "python -m src.models.valuation_ai.train_model_diagnostics",
    "python run_daily_market_ai_training_update.py --profile operational",
])
def test_non_ai_shared_and_external_owner_commands_not_retired(command):
    assert command_matches_blocked_pattern(command, {"blocked_patterns": []}) is None


def test_governance_does_not_open_ai_files_or_db(tmp_path, monkeypatch):
    internal = tmp_path / "internal.json"
    internal.write_text(json.dumps({"models": [
        {"model_code": "S2", "review_state": "PASS", "validation_score": {"total_score": 72}},
        {"model_code": "T-STOCK-V01", "review_state": "PASS"}]}), encoding="utf8")
    read = governance.read_json
    def guarded(path):
        assert path == internal, "unexpected AI/DB input access"
        return read(path)
    monkeypatch.setattr(governance, "read_json", guarded)
    monkeypatch.setattr(governance, "_quant1_2_comparison", lambda **_: {})
    result = governance.build_review(run_id="SYNTHETIC_TEST_ONLY", asof="2026-09-25",
                                     internal_validation_path=internal,
                                     ai_learning_path=tmp_path / "absent_ai.json")
    assert result["ai_learning_models"] == []
    assert result["strategy_models"][0]["total_score"] == 72
    assert [r["model_code"] for r in result["strategy_models"]] == ["S2"]


def test_retired_private_object_blocked_but_non_ai_admin_allowed():
    with pytest.raises(ValueError, match="retired"):
        reject_legacy_public_write("private-bucket", "admin/current/ai_learning_models_current.json")
    reject_legacy_public_write("private-bucket", "admin/current/internal_model_validation_current.json")


def test_weekend_ai_option_cannot_create_a_plan():
    spec = importlib.util.spec_from_file_location("legacy_harness", ROOT / "scripts/update_pipeline_harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="retired"):
        module.workflow_steps("weekend", include_ai_research=True)


def test_current_daily_scope_and_prompt_are_non_ai():
    state = cycle.build_initial_state("weekday", "2026-09-25", "SYNTHETIC_TEST_ONLY")
    assert len(state["operating_scope"]["active_models"]) == 6
    assert state["ai_retirement"]["status"] == "retired"
    assert "영구 폐지" in cycle.render_prompt(state)


def test_exact47_public_retirement_dependency_is_preserved():
    from public_publish_guard import BUCKET, LEGACY_PUBLIC_BLOCKED_OBJECTS

    assert len(LEGACY_PUBLIC_BLOCKED_OBJECTS) == 47
    for name in LEGACY_PUBLIC_BLOCKED_OBJECTS:
        with pytest.raises((ValueError, RuntimeError)):
            reject_legacy_public_write(BUCKET, name)
