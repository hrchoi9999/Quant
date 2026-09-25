"""Reconstructed paper accounting stays separate from verified Live."""
import hashlib
import json
from decimal import Decimal

import pytest

from src.quant2.adapters import quant25_paper_reconstruction as reconstruction
from src.quant2.adapters.quant25_paper_live import canonical_sha256
from src.quant2.adapters.quant25_paper_reconstruction import (
    _completed_asof,
    _rebalance,
    _unchanged_economic_prices,
    _verify_extension,
    reconstruct,
)


def test_whole_share_open_rebalance_charges_20bp_and_keeps_cash():
    shares = {}
    cash, trades, nonfills = _rebalance(
        shares, Decimal(1000), {"AAA": Decimal("0.5"), "BBB": Decimal("0.25")},
        {"AAA": Decimal(100), "BBB": Decimal(200)},
        profile="test", day="2026-09-07", source="snapshot")
    assert shares == {"AAA": 5, "BBB": 1}
    assert cash == Decimal("298.6")
    assert [trade["fee_krw"] for trade in trades] == ["1.000", "0.400"]
    assert nonfills == []


def test_ineligible_new_buy_is_nonfill_while_held_increase_is_allowed():
    shares = {}
    cash, trades, nonfills = _rebalance(
        shares, Decimal(1000), {"AAA": Decimal("0.5")}, {"AAA": Decimal(100)},
        profile="test", day="2026-09-14", source="decision", eligible={"AAA": False})
    assert cash == 1000 and shares == {} and trades == []
    assert nonfills[0]["reason"] == "FRESH_ENTRY_INELIGIBLE"
    shares = {"AAA": 1}
    cash, trades, nonfills = _rebalance(
        shares, Decimal(900), {"AAA": Decimal("0.5")}, {"AAA": Decimal(100)},
        profile="test", day="2026-09-14", source="decision", eligible={"AAA": False})
    assert shares["AAA"] == 5 and len(trades) == 1 and nonfills == []


def test_initial_capital_is_mdd_peak_and_missing_price_breaks_continuity():
    baseline = {"models": [{"profile_id": "test", "actual_portfolio": {
        "nav": 1, "cash": 0.5, "nav_equation_status": "pass",
        "positions": [{"ticker": "AAA", "market_value": 0.5}]}}]}
    rows = [
        {"ticker": "AAA", "date": "2026-09-07", "open": 100, "high": 101,
         "low": 89, "close": 90, "volume": 100, "source": "krx_openapi"},
        {"ticker": "AAA", "date": "2026-09-08", "open": 90, "high": 111,
         "low": 89, "close": 110, "volume": 100, "source": "krx_openapi"},
    ]
    daily, trades, nonfills, missing = reconstruct(
        baseline, [], rows, ["2026-09-07", "2026-09-08", "2026-09-09"])
    assert len(daily) == 2 and len(trades) == 1 and nonfills == []
    assert Decimal(daily[0]["candidate_nav_krw"]) == 94900000
    assert Decimal(daily[0]["candidate_max_drawdown_percent"]) == Decimal("-5.1")
    assert Decimal(daily[1]["candidate_max_drawdown_percent"]) == Decimal("-5.1")
    assert daily[1]["verified_live_return_percent"] is None
    assert missing == [{"date": "2026-09-09", "reason": "required_price_missing", "tickers": ["AAA"]}]
    _, _, _, pending = reconstruct(
        baseline, [], rows, ["2026-09-07", "2026-09-08", "2026-09-09"],
        completed_data_asof="2026-09-08")
    assert pending == [{"date": "2026-09-09", "reason": "awaiting_manual_refresh", "tickers": []}]
    _, _, _, incomplete = reconstruct(
        baseline, [], rows, ["2026-09-07", "2026-09-08", "2026-09-09"],
        completed_data_asof="2026-09-09")
    assert incomplete[0]["reason"] == "required_price_missing_within_completed_asof"


def test_completion_receipt_requires_exact_hash_and_completed_cycle(tmp_path):
    path = tmp_path / "completion.json"
    path.write_text(json.dumps({"overall_task_complete": False,
                                "final_completed_asof": "2026-09-23"}))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="not completed"):
        _completed_asof(path, digest)
    path.write_text(json.dumps({"overall_task_complete": True,
                                "final_completed_asof": "2026-09-23"}))
    with pytest.raises(ValueError, match="SHA mismatch"):
        _completed_asof(path, digest)
    assert _completed_asof(path, hashlib.sha256(path.read_bytes()).hexdigest()) == "2026-09-23"


def test_resume_keeps_prior_prefix_and_distinguishes_missing_from_uncollected():
    previous = {"valuation_end_date": "2026-09-07", "daily": [{"date": "2026-09-07", "nav": 99}],
                "trades": [{"date": "2026-09-07", "quantity": 1}], "nonfills": []}
    daily = previous["daily"] + [{"date": "2026-09-08", "nav": 101}]
    _verify_extension(previous, daily, previous["trades"], [],
                      [{"date": "2026-09-09", "reason": "awaiting_manual_refresh"}])
    with pytest.raises(ValueError, match="prior trades"):
        _verify_extension(previous, daily, [{"date": "2026-09-07", "quantity": 2}], [], [])
    with pytest.raises(ValueError, match="inside completed"):
        _verify_extension(previous, daily, previous["trades"], [],
                          [{"date": "2026-09-09",
                            "reason": "required_price_missing_within_completed_asof"}])
    with pytest.raises(ValueError, match="no evaluated new day"):
        _verify_extension(previous, previous["daily"], previous["trades"], [], [])


def test_resume_detects_economic_price_change_but_allows_metadata_change():
    saved = [{"ticker": "AAA", "date": "2026-09-07", "open": 100, "high": 110,
              "low": 90, "close": 101, "volume": 10, "value": 1010,
              "source": "krx_openapi", "updated_at": "old"}]
    current = [dict(saved[0], updated_at="new")]
    _unchanged_economic_prices(saved, current)
    with pytest.raises(ValueError, match="economic value changed"):
        _unchanged_economic_prices(saved, [dict(current[0], close=102)])


def test_prior_bundle_rejects_path_mix_and_generated_time_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(reconstruction, "ROOT", tmp_path)
    folder = tmp_path / "reports" / "prior"
    folder.mkdir(parents=True)
    rows = []
    (folder / "price_rows.json").write_text(json.dumps(rows))
    (folder / "decisions.json").write_text("[]")
    result = {"schema": reconstruction.SCHEMA,
              "classification": reconstruction.CLASSIFICATION,
              "generated_at": "2026-09-24T12:00:00+09:00",
              "source_hashes": {"price_rows_sha256": canonical_sha256(rows)}}
    (folder / "reconstruction.json").write_text(json.dumps(result))
    file_hashes = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                   for name in ("price_rows.json", "decisions.json", "reconstruction.json")}
    manifest = {"schema": "q25_retrospective_paper_manifest_v1",
                "classification": reconstruction.CLASSIFICATION,
                "generated_at": "2026-09-24T12:01:00+09:00", "files": file_hashes}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="source pin mismatch"):
        reconstruction._prior_bundle(folder, digest)
    manifest["files"]["../other.json"] = "0" * 64
    path.write_text(json.dumps(manifest))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="file list changed"):
        reconstruction._prior_bundle(folder, digest)
