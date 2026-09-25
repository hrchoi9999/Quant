"""Export existing weekly-model selections for QA; no ranking or model execution."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from src.quant_service.non_ai_scope import admin_scope_errors

MODELS = ("S2", "S3", "S3_CORE2", "S3_ACCEL_V01")
MIXED_DATE_CONTRACT = "qa_source_backed_per_model_latest_v1"
QA_CONSUMER_SHA256 = "46a4499f92e12bae848ee9c6cb9646bb834957aa1348ecfc0a11c44a56ff0b96"
FIELDS = ("전략군", "범위", "모델", "순위", "종목코드", "종목명", "선정일", "선정일 종가",
          "선정일 시가총액", "보유종료일", "보유종료일 종가", "선정일 대비 종가 등락율(%)",
          "보유기간(일)", "점수", "비중", "selection_date", "ticker", "source_model",
          "source_run_id", "model_version_id", "universe_identifier", "source_data_asof",
          "generated_at", "actual_execution_date")


def candidate_rows(payload: dict, metadata: dict, prices: dict, *, asof: str, generated_at: str,
                   consumer_contract: str | None = None):
    """Use verified latest rows only. Cash-only models need explicit DB evidence."""
    if consumer_contract not in (None, MIXED_DATE_CONTRACT):
        raise ValueError("unsupported candidate consumer contract")
    errors = admin_scope_errors(payload, asof)
    if errors:
        raise ValueError("; ".join(errors))
    if set(metadata) != set(MODELS):
        raise ValueError("four-model source metadata required")
    pinned = {r["model_code"]: r for r in payload["non_ai_admin"]["internal_source_runs"]}
    ranks = payload["weekly_rankings"]["internal_models"]
    output, model_status = [], []
    for model in MODELS:
        meta = metadata[model]
        if meta["run_id"] != pinned[model]["run_id"] or meta["data_asof"] != asof:
            raise ValueError("tracker and published run mismatch")
        if not meta["model_version_id"] or not meta["universe_name"] or not meta["snapshot_id"]:
            raise ValueError("missing model version or source universe")
        latest = [r for r in ranks if r.get("model_code") == model and r.get("is_latest_snapshot") is True]
        codes = [r["security_code"] for r in latest]
        if len(codes) != len(set(codes)) or set(codes) != set(meta["current_stock_tickers"]):
            raise ValueError("latest candidate coverage differs from published holdings")
        if not latest:
            if not meta["cash_only_verified"]:
                raise ValueError("empty model requires explicit cash-only source")
            model_status.append({"model": model, "status": "verified_cash_only", "rows": 0})
            continue
        dates = {r["snapshot_date"] for r in latest}
        if len(dates) != 1:
            raise ValueError("ambiguous latest weekly selection date")
        selected = next(iter(dates))
        date.fromisoformat(selected)
        if selected > asof:
            raise ValueError("future selection")
        for row in sorted(latest, key=lambda r: r["security_code"]):
            code = row["security_code"]
            if len(code) != 6 or not code.isdigit():
                raise ValueError("invalid stock ticker")
            weight = row["weight"]
            if weight is None and model == "S3_ACCEL_V01":
                bound = meta.get("source_target_weights", {}).get(code, {})
                if bound.get("selection_date") != selected:
                    raise ValueError("missing exact ACCEL source weight binding")
                weight = bound.get("weight")
            if weight is None or not math.isfinite(weight) or not 0 < weight <= 1:
                raise ValueError("invalid source target weight")
            executed = row.get("actual_execution_date")
            if executed and not selected <= executed <= asof:
                raise ValueError("unapplied or inconsistent source execution date")
            start, end = prices[(code, selected)], prices[(code, asof)]
            if not all(math.isfinite(p) and p > 0 for p in (start, end)):
                raise ValueError("missing or invalid exact selection/asof price")
            output.append(dict(zip(FIELDS, (
                "S", "internal", model, row.get("rank_no"), code, row.get("display_name") or code,
                selected, start, None, asof, end, round((end / start - 1) * 100, 6),
                (date.fromisoformat(asof) - date.fromisoformat(selected)).days, row.get("score"), weight,
                selected, code, model, meta["run_id"], meta["model_version_id"],
                meta["universe_name"] + ":" + meta["snapshot_id"], asof, generated_at, executed))))
        model_status.append({"model": model, "status": "source_backed", "rows": len(latest), "selection_date": selected})
    if len({r["selection_date"] for r in output}) > 1 and consumer_contract != MIXED_DATE_CONTRACT:
        raise ValueError("different model selection dates require explicit QA adapter; no global-max dropping")
    if not output:
        raise ValueError("no stock candidates; explicit all-cash consumer handling required")
    return output, model_status


def accel_source_weights(connection, run_id: str, asof: str) -> dict:
    """Use the published run's immutable original weights, never infer 1/N."""
    paths = [Path(row[0]) for row in connection.execute(
        "SELECT artifact_path FROM run_artifacts WHERE run_id=?", (run_id,))]
    paths = [p for p in paths if p.name.startswith("s3_accel_v01_holdings_") and p.suffix == ".csv"]
    if len(paths) != 1:
        raise ValueError("ACCEL immutable holdings missing or ambiguous")
    path = paths[0]
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    manifest_path = path.parent / "artifact_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    records = json.loads(manifest_bytes)
    matches = [r for r in records if Path(r["immutable_path"]).resolve() == path.resolve()]
    if len(matches) != 1 or matches[0]["sha256"] != digest:
        raise ValueError("ACCEL immutable holdings hash mismatch")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    valid = [r for r in rows if r["date"] <= asof]
    if not valid:
        raise ValueError("ACCEL source has no in-range selection")
    selected = max(r["date"] for r in valid)
    date.fromisoformat(selected)
    latest = [r for r in valid if r["date"] == selected and r["ticker"] != "CASH"]
    if len({r["ticker"] for r in latest}) != len(latest):
        raise ValueError("duplicate ACCEL target ticker")
    weights = {r["ticker"]: {"selection_date": selected, "weight": float(r["weight"])} for r in latest}
    if not weights or any(not math.isfinite(r["weight"]) or not 0 < r["weight"] <= 1 for r in weights.values()):
        raise ValueError("invalid immutable ACCEL weight")
    return {"source_target_weights": weights, "source_target_weights_evidence": {
        "path": str(path.resolve()), "sha256": digest, "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(), "run_id": run_id}}


def export_candidates(*, tracker: Path, tracker_sha256: str, core_db: Path, price_db: Path,
                      asof: str, output_dir: Path, consumer_contract: str | None = None,
                      consumer_path: Path | None = None) -> dict:
    consumer_binding = None
    if consumer_contract is not None:
        if consumer_contract != MIXED_DATE_CONTRACT:
            raise ValueError("explicit supported QA consumer contract required")
    if consumer_path is not None:
        if consumer_contract is None:
            raise ValueError("consumer path requires explicit contract")
        consumer_digest = hashlib.sha256(consumer_path.read_bytes()).hexdigest()
        if consumer_digest != QA_CONSUMER_SHA256:
            raise ValueError("QA mixed-date consumer hash mismatch")
        consumer_binding = {"contract": consumer_contract, "path": str(consumer_path.resolve()),
                            "sha256": consumer_digest,
                            "entrypoints": ["load_candidate_bundle_rows", "stock_model_summary"]}
    raw = tracker.read_bytes()
    if hashlib.sha256(raw).hexdigest() != tracker_sha256:
        raise ValueError("tracker hash mismatch")
    payload = json.loads(raw)
    metadata, prices = {}, {}
    with sqlite3.connect(core_db.resolve().as_uri() + "?mode=ro", uri=True) as c, \
            sqlite3.connect(price_db.resolve().as_uri() + "?mode=ro", uri=True) as p:
        c.row_factory = sqlite3.Row
        c.execute("BEGIN")
        p.execute("BEGIN")
        for model in MODELS:
            row = c.execute(
                "SELECT p.published_run_id AS run_id,p.data_asof,r.model_version_id,r.snapshot_id,s.universe_name "
                "FROM pub_model_current p JOIN run_runs r ON r.run_id=p.published_run_id "
                "JOIN run_data_snapshots s ON s.snapshot_id=r.snapshot_id WHERE p.model_code=?", (model,)).fetchone()
            if row is None:
                raise ValueError("missing published model")
            holds = c.execute("SELECT ticker,weight FROM pub_model_current_holdings WHERE model_code=? AND asof_date=?",
                              (model, asof)).fetchall()
            stocks = [h[0] for h in holds if h[0] != "CASH"]
            cash_only = bool(holds) and all(h[0] == "CASH" for h in holds)
            metadata[model] = {**dict(row), "current_stock_tickers": stocks, "cash_only_verified": cash_only}
            latest = [r for r in payload["weekly_rankings"]["internal_models"]
                      if r.get("model_code") == model and r.get("is_latest_snapshot") is True]
            if model == "S3_ACCEL_V01" and any(r.get("weight") is None for r in latest):
                evidence = accel_source_weights(c, row["run_id"], asof)
                if set(evidence["source_target_weights"]) != set(stocks):
                    raise ValueError("ACCEL immutable weights differ from published holdings")
                metadata[model].update(evidence)
        for row in payload["weekly_rankings"]["internal_models"]:
            if row.get("model_code") not in MODELS or row.get("is_latest_snapshot") is not True:
                continue
            for day in (row["snapshot_date"], asof):
                key = (row["security_code"], day)
                found = p.execute("SELECT close FROM prices_daily WHERE ticker=? AND date=?", key).fetchone()
                if found is None or found[0] is None:
                    raise ValueError(f"exact price unavailable: {key}")
                prices[key] = float(found[0])
        generated = datetime.now(timezone.utc).isoformat()
        rows, statuses = candidate_rows(payload, metadata, prices, asof=asof, generated_at=generated,
                                        consumer_contract=consumer_contract)
    if tracker.read_bytes() != raw:
        raise ValueError("tracker changed during export")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    content = buffer.getvalue().encode("utf-8-sig")
    manifest = {
        "schema": "legacy_qa_weekly_candidates_v1", "data_asof": asof, "generated_at": generated,
        "source_tracker": str(tracker.resolve()), "source_tracker_sha256": tracker_sha256,
        "source_tracker_generated_at": payload.get("generated_at"), "models": statuses,
        "source_models": metadata, "candidate_rows": len(rows), "unique_tickers": len({r["ticker"] for r in rows}),
        "output_file": "weekly_candidates.csv", "output_sha256": hashlib.sha256(content).hexdigest(),
        "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "field_notes": {"market_cap": "unavailable_null_not_zero",
                        "holding_end": "valuation_cutoff_not_actual_sale",
                        "return_pct": "selection_close_to_asof_close_not_strategy_NAV",
                        "universe_identifier": "published_run_source_snapshot_not_PIT_certification",
                        "weights": "upstream_weekly_rank_target_weights_not_combined_portfolio",
                        "actual_execution_date": "source_only_null_for_unseparated_legacy_contract"},
        "new_selection_or_ranking": False, "db_writes": 0, "publication": "none"}
    if consumer_binding is not None:
        if hashlib.sha256(consumer_path.read_bytes()).hexdigest() != consumer_binding["sha256"]:
            raise ValueError("QA consumer changed during export")
        manifest["consumer_binding"] = consumer_binding
    elif consumer_contract is not None:
        manifest["consumer_contract"] = consumer_contract
        manifest["consumer_binding_status"] = "requires_qa_owner_validation"
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "weekly_candidates.csv").write_bytes(content)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
