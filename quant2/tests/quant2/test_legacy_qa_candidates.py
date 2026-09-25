import copy
import hashlib
import json
import sqlite3

import pytest

from src.quant2.operations import legacy_qa_candidates as producer
from src.quant2.operations import standalone_retirement as standalone
from src.quant2.operations.legacy_qa_candidates import MODELS, accel_source_weights, candidate_rows, export_candidates
from src.quant_service import non_ai_scope as scope


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    contract_path = tmp_path / "standalone_model_retirement.json"
    contract_path.write_text(json.dumps({
        "contract_version": "standalone_model_retirement_v1",
        "namespace": "internal_standalone_models",
        "enabled": True,
        "retired_model_codes": ["S6"],
        "retired_at": "2026-09-22T11:47:44+09:00",
    }), encoding="utf-8")
    monkeypatch.setattr(standalone, "CONTRACT_PATH", contract_path)
    day, selected = "2026-09-15", "2026-09-09"
    operating_models = tuple(model for model in scope.MODELS if standalone.active(model))
    assert operating_models == ("S2", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5")
    ranks, metadata, prices = [], {}, {}
    for i, model in enumerate(MODELS, 1):
        code = str(i).zfill(6)
        ranks.append({"model_code": model, "is_latest_snapshot": True, "snapshot_date": selected,
                      "security_code": code, "rank_no": i, "score": None if i == 1 else 2.5,
                      "weight": .1, "actual_execution_date": "2026-09-10", "display_name": model})
        metadata[model] = {"run_id": model + "-run", "data_asof": day, "model_version_id": model + "-v1",
                           "universe_name": "source-universe", "snapshot_id": "snap", "current_stock_tickers": [code],
                           "cash_only_verified": False}
        prices[code, selected] = 100.
        prices[code, day] = 120.
    payload = {"scope_revision": scope.REVISION, "completion_basis": scope.COMPLETION_BASIS,
               "visibility": "admin_only", "schema_version": "v2", "as_of_date": day,
               "generated_at": "2026-09-17T10:00:00", "weekly_rankings": {"internal_models": ranks, "summary": {}},
               "summary": {}, "model_performance_summary": {}, "actual_live_performance_summary": {}, "freshness": {},
               "non_ai_admin": {"preserved_asof": "2026-09-09", "internal_source_runs": [
                   {"model_code": m, "run_id": m + "-run", "asof_date": day, "data_asof": day, "end_date": day}
                   for m in operating_models]}}
    payload["non_ai_admin"]["preserved_sections_sha256"] = scope.admin_preserved_hash(payload)
    return payload, metadata, prices


def test_export_preserves_source_model_rank_score_weights_and_dates(inputs):
    original = copy.deepcopy(inputs)
    rows, statuses = candidate_rows(*inputs, asof="2026-09-15", generated_at="now")
    assert inputs == original
    assert len(rows) == len(statuses) == 4
    assert {r["selection_date"] for r in rows} == {"2026-09-09"}
    assert rows[0]["점수"] is None
    assert all(r["비중"] == .1 and r["선정일 대비 종가 등락율(%)"] == 20. for r in rows)
    assert all(r["선정일 시가총액"] is None for r in rows)


def test_six_model_operating_gate_remains_enforced(inputs):
    payload, metadata, prices = inputs
    assert scope.admin_scope_errors(payload, "2026-09-15") == []
    payload["non_ai_admin"]["internal_source_runs"] = [
        run for run in payload["non_ai_admin"]["internal_source_runs"]
        if run["model_code"] != "S5"
    ]
    with pytest.raises(ValueError, match="internal source model coverage mismatch"):
        candidate_rows(payload, metadata, prices, asof="2026-09-15", generated_at="now")


@pytest.mark.parametrize("defect", ["run", "coverage", "execution", "price", "dates"])
def test_inconsistent_source_is_not_silently_repaired(inputs, defect):
    payload, metadata, prices = inputs
    row = payload["weekly_rankings"]["internal_models"][0]
    if defect == "run":
        metadata["S2"]["run_id"] = "different"
    elif defect == "coverage":
        metadata["S2"]["current_stock_tickers"] = []
    elif defect == "execution":
        row["actual_execution_date"] = "2026-09-16"
    elif defect == "price":
        prices["000001", "2026-09-09"] = 0.
    else:
        row["snapshot_date"] = "2026-09-08"
        prices["000001", "2026-09-08"] = 100.
    with pytest.raises(ValueError):
        candidate_rows(payload, metadata, prices, asof="2026-09-15", generated_at="now")


def test_cash_only_needs_positive_evidence(inputs):
    payload, metadata, prices = inputs
    payload["weekly_rankings"]["internal_models"] = payload["weekly_rankings"]["internal_models"][1:]
    metadata["S2"]["current_stock_tickers"] = []
    with pytest.raises(ValueError, match="cash-only"):
        candidate_rows(payload, metadata, prices, asof="2026-09-15", generated_at="now")
    metadata["S2"]["cash_only_verified"] = True
    rows, statuses = candidate_rows(payload, metadata, prices, asof="2026-09-15", generated_at="now")
    assert len(rows) == 3 and statuses[0]["status"] == "verified_cash_only"


@pytest.mark.parametrize("mixed", [False, True])
def test_complete_export_is_read_only_and_hash_bound(inputs, tmp_path, monkeypatch, mixed):
    payload, metadata, prices = inputs
    options = {}
    if mixed:
        row = payload["weekly_rankings"]["internal_models"][-1]
        row.update(snapshot_date="2026-09-15", actual_execution_date=None)
        consumer = tmp_path / "consumer.py"
        consumer.write_text("verified test consumer", encoding="utf-8")
        monkeypatch.setattr(producer, "QA_CONSUMER_SHA256", hashlib.sha256(consumer.read_bytes()).hexdigest())
        options = {"consumer_contract": producer.MIXED_DATE_CONTRACT, "consumer_path": consumer}
    tracker = tmp_path / "tracker.json"
    tracker.write_text(json.dumps(payload), encoding="utf-8")
    checksum = hashlib.sha256(tracker.read_bytes()).hexdigest()
    core, price = tmp_path / "core.db", tmp_path / "price.db"
    with sqlite3.connect(core) as c:
        c.executescript("CREATE TABLE pub_model_current(model_code,published_run_id,data_asof);"
                        "CREATE TABLE run_runs(run_id,model_version_id,snapshot_id);"
                        "CREATE TABLE run_data_snapshots(snapshot_id,universe_name);"
                        "CREATE TABLE pub_model_current_holdings(model_code,asof_date,ticker,weight);")
        c.execute("INSERT INTO run_data_snapshots VALUES ('snap','source-universe')")
        for model, meta in metadata.items():
            c.execute("INSERT INTO pub_model_current VALUES (?,?,?)", (model, meta["run_id"], meta["data_asof"]))
            c.execute("INSERT INTO run_runs VALUES (?,?,?)", (meta["run_id"], meta["model_version_id"], "snap"))
            c.execute("INSERT INTO pub_model_current_holdings VALUES (?,?,?,?)", (model, meta["data_asof"], meta["current_stock_tickers"][0], .1))
    with sqlite3.connect(price) as c:
        c.execute("CREATE TABLE prices_daily(ticker,date,close)")
        c.executemany("INSERT INTO prices_daily VALUES (?,?,?)", [(k[0], k[1], v) for k, v in prices.items()])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (core, price, tracker)}
    manifest = export_candidates(tracker=tracker, tracker_sha256=checksum, core_db=core, price_db=price,
                                 asof="2026-09-15", output_dir=tmp_path / "out", **options)
    assert manifest["candidate_rows"] == manifest["unique_tickers"] == 4
    assert manifest["output_sha256"] == hashlib.sha256((tmp_path / "out/weekly_candidates.csv").read_bytes()).hexdigest()
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    if mixed:
        assert {s["selection_date"] for s in manifest["models"]} == {"2026-09-09", "2026-09-15"}
        assert manifest["consumer_binding"]["sha256"] == producer.QA_CONSUMER_SHA256
        unbound = export_candidates(tracker=tracker, tracker_sha256=checksum, core_db=core, price_db=price,
                                    asof="2026-09-15", output_dir=tmp_path / "unbound",
                                    consumer_contract=producer.MIXED_DATE_CONTRACT)
        assert unbound["candidate_rows"] == 4
        assert unbound["consumer_binding_status"] == "requires_qa_owner_validation"
        assert "consumer_binding" not in unbound
        consumer.write_text("unverified changed consumer", encoding="utf-8")
        with pytest.raises(ValueError, match="consumer hash"):
            export_candidates(tracker=tracker, tracker_sha256=checksum, core_db=core, price_db=price,
                              asof="2026-09-15", output_dir=tmp_path / "rejected", **options)
        assert not (tmp_path / "rejected").exists()
    else:
        assert "consumer_binding" not in manifest
    with pytest.raises(ValueError, match="tracker hash"):
        export_candidates(tracker=tracker, tracker_sha256="wrong", core_db=core, price_db=price,
                          asof="2026-09-15", output_dir=tmp_path / "must_not_exist")
    assert not (tmp_path / "must_not_exist").exists()


def test_opt_in_preserves_same_date_and_mixed_date_rows(inputs):
    baseline = candidate_rows(*inputs, asof="2026-09-15", generated_at="now")
    opted = candidate_rows(*inputs, asof="2026-09-15", generated_at="now",
                           consumer_contract=producer.MIXED_DATE_CONTRACT)
    assert opted == baseline
    payload, metadata, prices = inputs
    payload["weekly_rankings"]["internal_models"][-1].update(
        snapshot_date="2026-09-15", actual_execution_date=None)
    with pytest.raises(ValueError, match="different model selection dates"):
        candidate_rows(*inputs, asof="2026-09-15", generated_at="now")
    original = copy.deepcopy(inputs)
    rows, statuses = candidate_rows(*inputs, asof="2026-09-15", generated_at="now",
                                    consumer_contract=producer.MIXED_DATE_CONTRACT)
    assert inputs == original
    assert len(rows) == len(statuses) == 4
    assert rows[:3] == baseline[0][:3]
    assert rows[-1]["selection_date"] == rows[-1]["선정일"] == "2026-09-15"
    assert rows[-1]["선정일 종가"] == 120. and rows[-1]["비중"] == .1
    with pytest.raises(ValueError, match="unsupported"):
        candidate_rows(*inputs, asof="2026-09-15", generated_at="now", consumer_contract="other")


@pytest.mark.parametrize("defect", ["future", "duplicate", "asof"])
def test_opt_in_keeps_source_guards(inputs, defect):
    payload, metadata, prices = inputs
    if defect == "future":
        payload["weekly_rankings"]["internal_models"][-1]["snapshot_date"] = "2026-09-16"
    elif defect == "duplicate":
        payload["weekly_rankings"]["internal_models"].append(payload["weekly_rankings"]["internal_models"][-1].copy())
    else:
        metadata["S3_ACCEL_V01"]["data_asof"] = "2026-09-14"
    with pytest.raises(ValueError):
        candidate_rows(*inputs, asof="2026-09-15", generated_at="now",
                       consumer_contract=producer.MIXED_DATE_CONTRACT)


def test_null_accel_weight_uses_verified_original_not_equal_weight(inputs, tmp_path):
    payload, metadata, prices = inputs
    row = payload["weekly_rankings"]["internal_models"][-1]
    row["weight"] = None
    with pytest.raises(ValueError, match="weight binding"):
        candidate_rows(payload, metadata, prices, asof="2026-09-15", generated_at="now")
    path = tmp_path / "s3_accel_v01_holdings_test.csv"
    path.write_text("date,ticker,weight\n2026-09-09,000004,0.37\n", encoding="utf-8")
    (tmp_path / "artifact_manifest.json").write_text(json.dumps([
        {"immutable_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]))
    with sqlite3.connect(":memory:") as c:
        c.execute("CREATE TABLE run_artifacts(run_id,artifact_path)")
        c.execute("INSERT INTO run_artifacts VALUES ('S3_ACCEL_V01-run',?)", (str(path),))
        metadata["S3_ACCEL_V01"].update(accel_source_weights(c, "S3_ACCEL_V01-run", "2026-09-15"))
        rows, _ = candidate_rows(payload, metadata, prices, asof="2026-09-15", generated_at="now")
        assert rows[-1]["비중"] == .37
        metadata["S3_ACCEL_V01"]["source_target_weights"]["000004"]["selection_date"] = "2026-09-08"
        with pytest.raises(ValueError, match="weight binding"):
            candidate_rows(payload, metadata, prices, asof="2026-09-15", generated_at="now")
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="hash mismatch"):
            accel_source_weights(c, "S3_ACCEL_V01-run", "2026-09-15")
