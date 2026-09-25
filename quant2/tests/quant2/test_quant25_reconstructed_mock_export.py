"""A source-pinned reconstruction may be shown only as provisional paper results."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.quant2.adapters.quant25_reconstructed_mock_export import export_view, project

RUN = Path(__file__).resolve().parents[2] / "reports/quant2_0/q25_paper_reconstruction_20260924/run_02_os"
PIN = "72f00e83ec8a97b4fa30343acb4b1701b085b697543561c7d78aff6fa59607e3"


@pytest.fixture
def source():
    return [json.loads((RUN / n).read_text(encoding="utf-8"))
            for n in ("reconstruction.json", "price_rows.json")]


def build(source):
    return project(*source, source_manifest_sha256=PIN, generated_at="2026-09-24T20:00:00+09:00")


def test_real_recording_arithmetic_projection_and_separation(source):
    original = deepcopy(source)
    result = build(source)
    assert source == original
    assert result["evaluation_start"] == "2026-09-07" and result["evaluation_end"] == "2026-09-22"
    assert len(result["models"]) == 3 and all(m["valuation_days"] == 12 for m in result["models"])
    assert sum(m["assumed_trade_count"] for m in result["models"]) == 134
    assert not result["public_eligible"] and result["verified_live_samples"] == 0
    assert "source_hashes" not in result and "owner_review" not in result


@pytest.mark.parametrize("broken", ["fee", "cash", "nav", "units", "return", "drawdown", "duplicate", "promotion", "bool"])
def test_inconsistent_or_promoted_source_rejected(source, broken):
    row = source[0]["daily"][0]
    if broken == "fee":
        source[0]["trades"][0]["fee_krw"] = "0"
    elif broken == "duplicate":
        row["positions"].append(deepcopy(row["positions"][0]))
    elif broken == "units":
        row["positions"][0]["quantity"] += 1
    elif broken == "promotion":
        row["verified_live_return_percent"] = "1"
    else:
        field = {"cash": "cash_krw", "nav": "candidate_nav_krw", "return": "candidate_return_percent",
                 "drawdown": "candidate_drawdown_percent", "bool": "cash_krw"}[broken]
        row[field] = True if broken == "bool" else "987654321"
    with pytest.raises(ValueError):
        build(source)


def test_pinned_export_and_existing_output_preservation(tmp_path):
    output = tmp_path / "export"
    result = export_view(RUN, expected_manifest_sha256=PIN, output_dir=output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert hashlib.sha256((output / "payload.json").read_bytes()).hexdigest() == manifest["payload"]["sha256"]
    assert manifest["output_hash"] == result["output_hash"]
    with pytest.raises(ValueError, match="new private"):
        export_view(RUN, expected_manifest_sha256=PIN, output_dir=output)
    with pytest.raises(ValueError, match="manifest SHA"):
        export_view(RUN, expected_manifest_sha256="0" * 64, output_dir=tmp_path / "wrong")


def test_price_read_cannot_precede_valuation(source):
    source[0]["price_snapshot_read_at"] = "2026-09-21T20:00:00+09:00"
    with pytest.raises(ValueError, match="valuation after"):
        build(source)
