import json

import pytest

from src.quant2.operations import ai_retirement as policy


@pytest.mark.parametrize("code", ["AI-GROWTH-VALUATION-V01", "T_STOCK_V01",
                                 "AI-CANDIDATE-VALIDATION-V01-MODEL-SPECIFIC",
                                 "AI-GROWTH-VALUATION-V01_20260716_001",
                                 "E-ETF-V01", "T-ETF-V01"])
def test_retired_models_and_aliases_cannot_execute(code):
    with pytest.raises(policy.RetiredModelError, match="retired"):
        policy.require_model_active(code)


@pytest.mark.parametrize("code", ["S2", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5",
                                 "Q25", "MARKET-RIDGE"])
def test_other_models_not_retired_by_this_policy(code):
    policy.require_model_active(code)


def test_policy_missing_or_narrowed_cannot_revive_model(tmp_path, monkeypatch):
    body = policy.load()
    path = tmp_path / "contract.json"
    monkeypatch.setattr(policy, "CONTRACT_PATH", path)
    with pytest.raises(FileNotFoundError):
        policy.require_model_active("T-STOCK-V01")
    body["retired_model_ids"].remove("T-STOCK-V01")
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid"):
        policy.require_model_active("T-STOCK-V01")


@pytest.mark.parametrize("name", ["admin/current/ai_learning_models_current.json",
                                 r"D:\saved\quantservice_tseries_discovery.json",
                                 "valuation_ai_shadow_monitor.json"])
def test_current_outputs_rejected(name):
    with pytest.raises(policy.RetiredModelError):
        policy.require_current_object(name)


@pytest.mark.parametrize("name", ["e_series_etf_total_return_adjustment_current.json",
                                 "investment_portfolio_latest.json", "q25_current.json",
                                 "internal_model_performance_history.json"])
def test_shared_and_non_ai_outputs_preserved(name):
    policy.require_current_object(name)
