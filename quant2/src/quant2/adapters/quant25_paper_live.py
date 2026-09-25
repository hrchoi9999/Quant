"""Inactive Quant 2.5 paper-live adapter for the frozen three-profile release."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "q25_os_qs_v1"
FREEZE_ID = "Q25_THREE_PROFILES_RESEARCH_FREEZE_20260909_V1"
PROFILE_MODEL_IDS = {
    "activity_retention": "q25_activity_retention",
    "defensive_pg_retention": "q25_defensive_pg_retention",
    "defensive_cash75_retention": "q25_defensive_cash75_retention",
}
PROFILE_DISPLAY_NAMES = {
    "activity_retention": "Quant 2.5 공격형",
    "defensive_pg_retention": "Quant 2.5 방어형",
    "defensive_cash75_retention": "Quant 2.5 방어형 - 주식 축소",
}
ALLOWED_ASSET_TYPES = {"STOCK", "ETF"}
HASH_LENGTH = 64
TOLERANCE = 1e-9


class PaperLiveContractError(ValueError):
    """Raised when an inactive paper-live request violates the frozen contract."""


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PaperLiveContractError(f"JSON object required: {path}")
    return payload


def _timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise PaperLiveContractError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperLiveContractError(f"{field} must include a timezone")
    return parsed


def _iso_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise PaperLiveContractError(f"{field} must be an ISO date") from exc


def _finite_nonnegative(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PaperLiveContractError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise PaperLiveContractError(f"{field} must be finite and nonnegative")
    return number


def _validate_hash(value: Any, field: str) -> str:
    digest = str(value).lower()
    if len(digest) != HASH_LENGTH or any(char not in "0123456789abcdef" for char in digest):
        raise PaperLiveContractError(f"{field} must be a SHA-256 digest")
    return digest


def validate_freeze_bundle(freeze_dir: Path) -> dict[str, Any]:
    """Validate the immutable freeze bundle without consulting operating state."""

    manifest_path = freeze_dir / "freeze_manifest.json"
    contract_path = freeze_dir / "execution_contract.json"
    manifest = _load_json(manifest_path)
    contract = _load_json(contract_path)
    if manifest.get("freeze_id") != FREEZE_ID or contract.get("freeze_id") != FREEZE_ID:
        raise PaperLiveContractError("unexpected freeze id")
    if set(manifest.get("profiles", {})) != set(PROFILE_MODEL_IDS):
        raise PaperLiveContractError("freeze must contain exactly the approved three profiles")
    if manifest.get("promotion_authorized") is not False or manifest.get("live_started") is not False:
        raise PaperLiveContractError("freeze is not eligible for inactive adapter validation")
    manifest_hash = file_sha256(manifest_path)
    expected_parent = _validate_hash(contract.get("parent_manifest_sha256"), "parent manifest hash")
    if manifest_hash != expected_parent:
        raise PaperLiveContractError("execution contract is not bound to the freeze manifest")

    checked_outputs: list[str] = []
    for relative, expected in manifest.get("output_hashes", {}).items():
        path = freeze_dir / relative
        if not path.is_file():
            raise PaperLiveContractError(f"frozen output is missing: {relative}")
        if file_sha256(path) != _validate_hash(expected, f"output hash {relative}"):
            raise PaperLiveContractError(f"frozen output hash mismatch: {relative}")
        checked_outputs.append(relative)

    return {
        "freeze_id": FREEZE_ID,
        "freeze_manifest_sha256": manifest_hash,
        "execution_contract_sha256": file_sha256(contract_path),
        "verified_frozen_output_count": len(checked_outputs),
        "verified_frozen_outputs": checked_outputs,
        "manifest": manifest,
        "execution_contract": contract,
    }


def _validate_target_positions(
    positions: Any,
    *,
    profile_id: str,
    regime: str,
    profile_contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], float]:
    if not isinstance(positions, list):
        raise PaperLiveContractError("target_positions must be a list")
    normalized: list[dict[str, Any]] = []
    tickers: set[str] = set()
    for item in positions:
        if not isinstance(item, dict):
            raise PaperLiveContractError("target position must be an object")
        ticker = str(item.get("ticker", "")).strip()
        asset_type = str(item.get("asset_type", "")).upper()
        if not ticker or ticker in tickers:
            raise PaperLiveContractError("target tickers must be nonempty and unique")
        if asset_type not in ALLOWED_ASSET_TYPES:
            raise PaperLiveContractError("target asset_type must be STOCK or ETF")
        weight = _finite_nonnegative(item.get("target_weight"), f"target weight {ticker}")
        if weight > 1 + TOLERANCE:
            raise PaperLiveContractError("individual target weight cannot exceed one")
        price = _finite_nonnegative(item.get("reference_price"), f"reference price {ticker}")
        if price <= 0:
            raise PaperLiveContractError("reference price must be positive")
        tickers.add(ticker)
        normalized.append(
            {
                "ticker": ticker,
                "asset_type": asset_type,
                "target_weight": weight,
                "reference_price": price,
                "fresh_entry_eligible": bool(item.get("fresh_entry_eligible", False)),
                "restriction_state": str(item.get("restriction_state", "NONE")),
                "target_reason": str(item.get("target_reason", "FROZEN_PROFILE_TARGET")),
            }
        )

    total = sum(item["target_weight"] for item in normalized)
    if total > 1 + TOLERANCE:
        raise PaperLiveContractError("target weights exceed portfolio capital")
    stocks = [item for item in normalized if item["asset_type"] == "STOCK"]
    etfs = [item for item in normalized if item["asset_type"] == "ETF"]
    if profile_id == "activity_retention":
        if etfs:
            raise PaperLiveContractError("activity_retention cannot contain ETF targets")
        if len(stocks) > int(profile_contract["stock_slots"]):
            raise PaperLiveContractError("activity_retention stock slot cap exceeded")
        slot_weight = float(profile_contract["slot_weight"])
        if any(item["target_weight"] > slot_weight + TOLERANCE for item in stocks):
            raise PaperLiveContractError("activity_retention target exceeds frozen slot weight")
    else:
        if len(stocks) > int(profile_contract["stock_slots"]):
            raise PaperLiveContractError("defensive stock slot cap exceeded")
        if len(etfs) > int(profile_contract["etf_max_slots"]):
            raise PaperLiveContractError("defensive ETF slot cap exceeded")
        if len(normalized) > int(profile_contract["combined_target_cap"]):
            raise PaperLiveContractError("defensive combined target cap exceeded")
        if regime not in profile_contract["regime_stock_ceiling"]:
            raise PaperLiveContractError("defensive profile requires a frozen regime label")
        stock_weight = sum(item["target_weight"] for item in stocks)
        ceiling = float(profile_contract["regime_stock_ceiling"][regime])
        if stock_weight > ceiling + TOLERANCE:
            raise PaperLiveContractError("defensive stock ceiling exceeded")
    return sorted(normalized, key=lambda item: (item["asset_type"], item["ticker"])), 1.0 - total


def _validate_actual_positions(positions: Any) -> tuple[list[dict[str, Any]], float]:
    if not isinstance(positions, list):
        raise PaperLiveContractError("actual_positions must be a list")
    normalized: list[dict[str, Any]] = []
    tickers: set[str] = set()
    market_value = 0.0
    for item in positions:
        if not isinstance(item, dict):
            raise PaperLiveContractError("actual position must be an object")
        ticker = str(item.get("ticker", "")).strip()
        if not ticker or ticker in tickers:
            raise PaperLiveContractError("actual tickers must be nonempty and unique")
        asset_type = str(item.get("asset_type", "")).upper()
        if asset_type not in ALLOWED_ASSET_TYPES:
            raise PaperLiveContractError("actual asset_type must be STOCK or ETF")
        units = _finite_nonnegative(item.get("units"), f"actual units {ticker}")
        mark_price = _finite_nonnegative(item.get("mark_price"), f"mark price {ticker}")
        if mark_price <= 0:
            raise PaperLiveContractError("mark price must be positive")
        if units <= TOLERANCE:
            tickers.add(ticker)
            continue
        value = units * mark_price
        market_value += value
        tickers.add(ticker)
        normalized.append(
            {
                "ticker": ticker,
                "asset_type": asset_type,
                "units": units,
                "mark_price": mark_price,
                "market_value_krw": value,
                "tradability_state": str(item.get("tradability_state", "TRADABLE")),
            }
        )
    return sorted(normalized, key=lambda item: (item["asset_type"], item["ticker"])), market_value


def _validate_cash_entitlements(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        raise PaperLiveContractError("cash_entitlements must be a list")
    normalized: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            raise PaperLiveContractError("cash entitlement must be an object")
        status = str(event.get("status", "UNKNOWN"))
        amount = event.get("amount_krw")
        payment_date = event.get("payment_date")
        if status == "UNKNOWN" and (amount is not None or payment_date is not None):
            raise PaperLiveContractError("unknown entitlement cannot contain guessed cash or payment date")
        if status not in {"UNKNOWN", "PENDING_CONFIRMED", "RECEIVED"}:
            raise PaperLiveContractError("unsupported cash entitlement status")
        normalized.append(deepcopy(event))
    return normalized


def build_inactive_dry_run_payload(
    request: dict[str, Any],
    *,
    freeze_dir: Path,
) -> dict[str, Any]:
    """Build an internal dry-run payload without writing any operating state."""

    if request.get("mode") != "isolated_dry_run":
        raise PaperLiveContractError("only isolated_dry_run is allowed before activation")
    if request.get("visibility") != "internal":
        raise PaperLiveContractError("inactive dry-run visibility must be internal")
    profile_id = str(request.get("profile_id", ""))
    if profile_id not in PROFILE_MODEL_IDS:
        raise PaperLiveContractError("profile is not in the approved three-model allowlist")
    model_id = str(request.get("model_id", ""))
    if model_id != PROFILE_MODEL_IDS[profile_id]:
        raise PaperLiveContractError("model_id and profile_id mapping mismatch")

    freeze = validate_freeze_bundle(freeze_dir)
    manifest = freeze["manifest"]
    profile_contract = manifest["profiles"][profile_id]
    data_asof = _iso_date(request.get("data_asof"), "data_asof")
    input_available_at = _timestamp(request.get("input_available_at"), "input_available_at")
    decision_at = _timestamp(request.get("decision_at"), "decision_at")
    execution_at = _timestamp(request.get("execution_at"), "execution_at")
    generated_at = _timestamp(request.get("generated_at"), "generated_at")
    if input_available_at > decision_at:
        raise PaperLiveContractError("late input cannot be backdated into the decision")
    if data_asof >= decision_at.date():
        raise PaperLiveContractError("market input must be from a trading day before the decision")
    if execution_at <= decision_at:
        raise PaperLiveContractError("execution basis must follow the decision")
    if generated_at < decision_at:
        raise PaperLiveContractError("generated_at cannot precede decision_at")

    source_hashes = request.get("source_input_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise PaperLiveContractError("at least one source input hash is required")
    normalized_source_hashes = {
        str(name): _validate_hash(value, f"source input hash {name}")
        for name, value in sorted(source_hashes.items())
    }
    regime = str(request.get("market_regime", ""))
    targets, target_cash_weight = _validate_target_positions(
        request.get("target_positions"),
        profile_id=profile_id,
        regime=regime,
        profile_contract=profile_contract,
    )
    actual, holdings_value = _validate_actual_positions(request.get("actual_positions"))
    cash_krw = _finite_nonnegative(request.get("cash_krw"), "cash_krw")
    portfolio_value = cash_krw + holdings_value
    if portfolio_value <= 0:
        raise PaperLiveContractError("paper portfolio value must be positive")

    actual_by_ticker = {item["ticker"]: item for item in actual}
    order_intents: list[dict[str, Any]] = []
    nonfills: list[dict[str, Any]] = []
    for target in targets:
        held = actual_by_ticker.get(target["ticker"])
        actual_value = 0.0 if held is None else float(held["market_value_krw"])
        desired_value = float(target["target_weight"]) * portfolio_value
        delta_value = desired_value - actual_value
        if abs(delta_value) <= TOLERANCE:
            continue
        is_fresh_buy = delta_value > 0 and held is None
        restriction = target["restriction_state"]
        tradability = "TRADABLE" if held is None else held["tradability_state"]
        block_reason: str | None = None
        if is_fresh_buy and not target["fresh_entry_eligible"]:
            block_reason = "FRESH_ENTRY_INELIGIBLE"
        elif restriction != "NONE":
            block_reason = restriction
        elif tradability != "TRADABLE":
            block_reason = tradability
        if block_reason is not None:
            nonfills.append(
                {
                    "ticker": target["ticker"],
                    "side": "BUY" if delta_value > 0 else "SELL",
                    "reason": block_reason,
                    "actual_units_preserved": 0.0 if held is None else held["units"],
                }
            )
            continue
        whole_units = math.floor(abs(delta_value) / float(target["reference_price"]))
        if whole_units == 0:
            nonfills.append(
                {
                    "ticker": target["ticker"],
                    "side": "BUY" if delta_value > 0 else "SELL",
                    "reason": "BELOW_ONE_UNIT",
                    "actual_units_preserved": 0.0 if held is None else held["units"],
                }
            )
            continue
        order_intents.append(
            {
                "ticker": target["ticker"],
                "side": "BUY" if delta_value > 0 else "SELL",
                "units": whole_units,
                "reference_price": target["reference_price"],
                "execution_status": "NOT_EXECUTED_DRY_RUN",
            }
        )

    target_tickers = {item["ticker"] for item in targets}
    for held in actual:
        if held["ticker"] in target_tickers:
            continue
        if held["tradability_state"] != "TRADABLE":
            nonfills.append(
                {
                    "ticker": held["ticker"],
                    "side": "SELL",
                    "reason": held["tradability_state"],
                    "actual_units_preserved": held["units"],
                }
            )
        else:
            order_intents.append(
                {
                    "ticker": held["ticker"],
                    "side": "SELL",
                    "units": math.floor(held["units"]),
                    "reference_price": held["mark_price"],
                    "execution_status": "NOT_EXECUTED_DRY_RUN",
                }
            )

    cash_entitlements = _validate_cash_entitlements(request.get("cash_entitlements", []))
    unresolved_events = request.get("unresolved_events", [])
    if not isinstance(unresolved_events, list):
        raise PaperLiveContractError("unresolved_events must be a list")
    actual_output = deepcopy(actual)
    for item in actual_output:
        item["actual_weight"] = item["market_value_krw"] / portfolio_value

    input_fingerprint = {
        "request": request,
        "freeze_manifest_sha256": freeze["freeze_manifest_sha256"],
        "execution_contract_sha256": freeze["execution_contract_sha256"],
    }
    if not str(request.get("run_id", "")).strip():
        raise PaperLiveContractError("run_id is required")
    actual_invested_weight = holdings_value / portfolio_value
    actual_cash_weight = cash_krw / portfolio_value
    if abs(actual_invested_weight + actual_cash_weight - 1.0) > TOLERANCE:
        raise PaperLiveContractError("actual holdings plus cash must reconcile to NAV")

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release_id": "Q25_INACTIVE_ADAPTER_PREP_20260909",
        "run_id": str(request.get("run_id", "")),
        "model_id": model_id,
        "profile_id": profile_id,
        "profile_hash": canonical_sha256(profile_contract),
        "display_name": PROFILE_DISPLAY_NAMES[profile_id],
        "freeze_id": FREEZE_ID,
        "freeze_manifest_sha256": freeze["freeze_manifest_sha256"],
        "execution_contract_sha256": freeze["execution_contract_sha256"],
        "source_input_hashes": normalized_source_hashes,
        "input_hash": canonical_sha256(input_fingerprint),
        "rule_hash": freeze["freeze_manifest_sha256"],
        "phase": "research",
        "operation_mode": "isolated_dry_run",
        "evidence_classification": "ISOLATED_DRY_RUN_NOT_LIVE",
        "visibility": "internal",
        "public_eligible": False,
        "activation_status": "inactive_not_scheduled",
        "paper_live_actual_start": None,
        "timing": {
            "data_asof": data_asof.isoformat(),
            "input_available_at": input_available_at.isoformat(),
            "decision_at": decision_at.isoformat(),
            "generated_at": generated_at.isoformat(),
            "execution_at": execution_at.isoformat(),
            "execution_basis": "NEXT_TRADING_SESSION_OPEN",
        },
        "market_regime": regime,
        "target_portfolio": {
            "positions": targets,
            "cash_weight": target_cash_weight,
        },
        "actual_portfolio": {
            "positions": actual_output,
            "cash_krw": cash_krw,
            "portfolio_value_krw": portfolio_value,
            "invested_weight": actual_invested_weight,
            "cash_weight": actual_cash_weight,
            "nav_equation": "sum(actual_position_market_value_krw) + cash_krw",
            "nonfills_are_assets": False,
            "state": "UNCHANGED_BY_DRY_RUN",
        },
        "order_intents": sorted(order_intents, key=lambda item: item["ticker"]),
        "nonfills": sorted(nonfills, key=lambda item: item["ticker"]),
        "cash_entitlements": cash_entitlements,
        "unresolved_events": deepcopy(unresolved_events),
        "evaluation_contract": {
            "period": None,
            "costs": "not_applied_in_adapter_dry_run",
            "taxes": "not_applied_in_adapter_dry_run",
            "dividends": "separate_cash_entitlement_ledger",
            "total_return_coverage": "NOT_ESTABLISHED",
        },
        "validation": {
            "freeze_bundle": "pass",
            "profile_allowlist": "pass",
            "chronological_input_gate": "pass",
            "target_actual_separation": "pass",
            "operating_state_mutation": "none",
            "verified_frozen_output_count": freeze["verified_frozen_output_count"],
        },
        "freshness": {
            "status": "dry_run_only_not_current",
            "serving_eligible": False,
        },
    }
    payload["output_hash"] = canonical_sha256(payload)
    return payload


def build_inactive_dry_run_bundle(
    requests: list[dict[str, Any]],
    *,
    freeze_dir: Path,
) -> dict[str, Any]:
    """Assemble the three validated internal model records in the QS envelope."""

    if not isinstance(requests, list) or len(requests) != len(PROFILE_MODEL_IDS):
        raise PaperLiveContractError("bundle requires exactly three profile requests")
    models = [build_inactive_dry_run_payload(item, freeze_dir=freeze_dir) for item in requests]
    if {item["model_id"] for item in models} != set(PROFILE_MODEL_IDS.values()):
        raise PaperLiveContractError("bundle must contain the exact three-model allowlist")
    run_ids = {item["run_id"] for item in models}
    if len(run_ids) != 1:
        raise PaperLiveContractError("bundle model records must share one run_id")
    timing = {canonical_sha256(item["timing"]) for item in models}
    if len(timing) != 1:
        raise PaperLiveContractError("bundle model records must share one timing contract")

    ordered = sorted(
        models,
        key=lambda item: list(PROFILE_MODEL_IDS.values()).index(item["model_id"]),
    )
    first = ordered[0]
    qs_models = []
    for model in ordered:
        record = deepcopy(model)
        target_weight = 1.0 - float(model["target_portfolio"]["cash_weight"])
        actual_weight = float(model["actual_portfolio"]["invested_weight"])
        record.update(
            {
                "operating_stage": "research",
                "paper_live_start": None,
                "actual_live_start": None,
                "status": "inactive_dry_run",
                "allocation": {
                    "target": {"weight": target_weight},
                    "actual": {"weight": actual_weight},
                    "cash": {
                        "weight": float(model["target_portfolio"]["cash_weight"]),
                        "actual_weight": float(model["actual_portfolio"]["cash_weight"]),
                    },
                    "unfilled": {
                        "weight": 0.0,
                        "actual_weight": 0.0,
                        "accounting": "ORDER_STATE_ONLY_NOT_AN_ASSET",
                    },
                    "other_settled_asset": {"actual_weight": 0.0},
                },
                "performance": {
                    "status": "not_started",
                    "basis": "paper_live",
                    "return_pct": None,
                    "period_start": None,
                    "as_of_date": None,
                    "cost_coverage": "not_available",
                    "dividend_coverage": "not_available",
                    "total_return_coverage": "not_available",
                },
                "holdings": [
                    {
                        "display_name": str(item.get("display_name") or item["ticker"]),
                        "security_code": item["ticker"],
                        "target_weight": float(item["target_weight"]),
                    }
                    for item in model["target_portfolio"]["positions"]
                ],
                "actual_holdings": [
                    {
                        "display_name": str(item.get("display_name") or item["ticker"]),
                        "security_code": item["ticker"],
                        "actual_weight": float(item["actual_weight"]),
                    }
                    for item in model["actual_portfolio"]["positions"]
                ],
            }
        )
        qs_models.append(record)
    release = {
        "release_id": "Q25_INACTIVE_ADAPTER_PREP_20260909",
        "visibility": "internal",
        "activation_status": "inactive_not_scheduled",
        "public_eligible": False,
    }
    release["release_hash"] = canonical_sha256(release)
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release": release,
        "run": {
            "run_id": next(iter(run_ids)),
            "input_hash": canonical_sha256([item["input_hash"] for item in ordered]),
            "rule_hash": first["rule_hash"],
            "output_hash_scope": "canonical JSON of full bundle with run.output_hash omitted",
        },
        "freeze": {
            "freeze_id": FREEZE_ID,
            "freeze_manifest_hash": first["freeze_manifest_sha256"],
            "execution_contract_hash": first["execution_contract_sha256"],
        },
        "freshness": {
            "status": "dry_run_only_not_current",
            "serving_eligible": False,
            **first["timing"],
            "as_of_date": first["timing"]["data_asof"],
            "paper_live_actual_start": None,
        },
        "validation": {
            "status": "pass",
            "validated_at": first["timing"]["generated_at"],
            "classification": "ISOLATED_DRY_RUN_NOT_LIVE",
            "operating_state_mutation": "none",
            "public_contract_eligible": False,
        },
        "models": qs_models,
    }
    bundle["run"]["output_hash"] = canonical_sha256(bundle)
    return bundle

