"""Isolated append-only paper ledger for frozen Quant 2.5 profiles.

This module records externally supplied, validated events. It never creates fills
from targets and does not connect to an operating database or scheduler.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from .quant25_incremental_selection import SCHEMA as SELECTOR_SCHEMA
from .quant25_incremental_selection import SOURCES as SELECTOR_SOURCES
from .quant25_paper_live import FREEZE_ID, PROFILE_MODEL_IDS, canonical_sha256

SCHEMA_VERSION = "q25_paper_ledger_v1"
CLASSIFICATION = "ISOLATED_PAPER_LEDGER_PREPARATION_NOT_LIVE"
EVENT_TYPES = {"target", "fill", "paper_fill", "nonfill", "mark", "rights"}
ASSET_TYPES = {"STOCK", "ETF"}
SIDES = {"BUY", "SELL"}
PROFILE_IDS = frozenset(PROFILE_MODEL_IDS)
WEIGHT_TOLERANCE = Decimal("1e-9")
OPERATING_DB_NAMES = {
    "price.db",
    "quant_service.db",
    "generated_outputs.db",
    "model_research.db",
    "ai_learning.db",
    "tseries_operational.db",
}


class PaperLedgerError(ValueError):
    """Raised when an event or ledger transition violates the contract."""


@dataclass(frozen=True)
class LedgerConfig:
    freeze_id: str
    starting_capital: Decimal
    currency: str
    fee_rate: Decimal
    created_at: datetime


def _aware(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise PaperLedgerError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperLedgerError(f"{field} must be timezone-aware")
    return parsed


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise PaperLedgerError(f"{field} must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PaperLedgerError(f"{field} must be numeric") from exc
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        qualifier = "positive" if positive else "nonnegative"
        raise PaperLedgerError(f"{field} must be finite and {qualifier}")
    return number


def _number_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _sha256(value: Any, field: str) -> str:
    digest = str(value).lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise PaperLedgerError(f"{field} must be a SHA-256 digest")
    return digest


def _text(value: Any, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise PaperLedgerError(f"{field} must be nonempty")
    return normalized


def _json_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PaperLedgerError(f"{field} must be an object")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PaperLedgerError(f"{field} must be canonical JSON") from exc
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise PaperLedgerError(f"{field} must be an object")
    return decoded


def _guard_isolated_path(path: Path) -> Path:
    resolved = path.resolve()
    parts = [part.casefold() for part in resolved.parts]
    if resolved.name.casefold() in OPERATING_DB_NAMES:
        raise PaperLedgerError("operating database path is prohibited")
    if any(parts[index : index + 2] == ["data", "db"] for index in range(len(parts) - 1)):
        raise PaperLedgerError("operating database directory is prohibited")
    return resolved


def _asset_type(value: Any) -> str:
    normalized = str(value).upper()
    if normalized not in ASSET_TYPES:
        raise PaperLedgerError("asset_type must be STOCK or ETF")
    return normalized


def _side(value: Any) -> str:
    normalized = str(value).upper()
    if normalized not in SIDES:
        raise PaperLedgerError("side must be BUY or SELL")
    return normalized


def _normalize_selector_target(payload: dict[str, Any], observed_at: datetime, profile_id: str) -> dict[str, Any]:
    if payload.get("schema") != SELECTOR_SCHEMA:
        raise PaperLedgerError("unsupported selector schema")
    if payload.get("freeze_id") != FREEZE_ID:
        raise PaperLedgerError("selector freeze_id mismatch")
    body = {key: value for key, value in payload.items() if key != "state_sha256"}
    if canonical_sha256(body) != payload.get("state_sha256"):
        raise PaperLedgerError("selector state_sha256 mismatch")
    historical = payload.get("historical")
    if type(historical) is not bool:
        raise PaperLedgerError("selector historical must be a boolean")
    expected_classification = "HISTORICAL_RECONSTRUCTION" if historical else "CAPTURED_INPUT_PREPARATION"
    if payload.get("classification") != expected_classification:
        raise PaperLedgerError("selector classification mismatch")
    if payload.get("live_started") is not False or payload.get("operationally_actionable") is not False:
        raise PaperLedgerError("selector output cannot be live or operationally actionable")
    cutoff = _aware(payload.get("decision_cutoff"), "selector decision_cutoff")
    execution_open = _aware(f"{payload.get('execution_date')}T09:00:00+09:00", "selector execution open")
    if not historical and not (cutoff <= observed_at < execution_open):
        raise PaperLedgerError("captured selector output must be recorded after cutoff and before execution")
    evidence = payload.get("input_evidence")
    if not isinstance(evidence, dict) or set(evidence) != SELECTOR_SOURCES:
        raise PaperLedgerError("selector input_evidence must contain the frozen source set")
    for source_name, item in evidence.items():
        if not isinstance(item, dict):
            raise PaperLedgerError(f"selector evidence must be an object: {source_name}")
        _sha256(item.get("sha256"), f"selector evidence hash {source_name}")
        for field in ("available_at", "arrived_at"):
            timestamp = item.get(field)
            if timestamp is None:
                if not historical:
                    raise PaperLedgerError(f"captured selector requires {field}: {source_name}")
            elif _aware(timestamp, f"selector {field} {source_name}") > cutoff:
                raise PaperLedgerError(f"selector evidence is available after cutoff: {source_name}")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != PROFILE_IDS:
        raise PaperLedgerError("selector must contain exactly the frozen profiles")
    selected = profiles.get(profile_id)
    if not isinstance(selected, dict):
        raise PaperLedgerError("selector profile payload is missing")
    positions = selected.get("target_positions")
    if not isinstance(positions, list):
        raise PaperLedgerError("selector target_positions must be a list")
    tickers: set[str] = set()
    total = Decimal("0")
    for item in positions:
        if not isinstance(item, dict):
            raise PaperLedgerError("selector target position must be an object")
        ticker = _text(item.get("ticker"), "selector target ticker")
        if ticker in tickers:
            raise PaperLedgerError("selector target tickers must be unique")
        tickers.add(ticker)
        _asset_type(item.get("asset_type"))
        weight = _decimal(item.get("target_weight"), f"selector target weight {ticker}")
        if weight > 1:
            raise PaperLedgerError("selector target weight cannot exceed one")
        total += weight
        _decimal(item.get("reference_price"), f"selector reference price {ticker}", positive=True)
        if type(item.get("fresh_entry_eligible")) is not bool:
            raise PaperLedgerError("selector fresh_entry_eligible must be a strict boolean")
        _text(item.get("target_reason"), "selector target_reason")
    cash_target = _decimal(selected.get("cash_target"), "selector cash_target")
    if abs(total + cash_target - Decimal("1")) > WEIGHT_TOLERANCE:
        raise PaperLedgerError("selector targets and cash must sum to one")
    return payload


def _normalize_target(payload: dict[str, Any], observed_at: datetime, profile_id: str) -> dict[str, Any]:
    if payload.get("schema") == SELECTOR_SCHEMA:
        return _normalize_selector_target(payload, observed_at, profile_id)
    decision_at = _aware(payload.get("decision_at"), "target decision_at")
    if observed_at > decision_at:
        raise PaperLedgerError("target uses input available after decision_at")
    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise PaperLedgerError("target positions must be a list")
    tickers: set[str] = set()
    normalized_positions: list[dict[str, str]] = []
    total = Decimal("0")
    for item in positions:
        if not isinstance(item, dict):
            raise PaperLedgerError("target position must be an object")
        ticker = _text(item.get("ticker"), "target ticker")
        if ticker in tickers:
            raise PaperLedgerError("target tickers must be unique")
        weight = _decimal(item.get("target_weight"), f"target weight {ticker}")
        if weight > 1:
            raise PaperLedgerError("target weight cannot exceed one")
        tickers.add(ticker)
        total += weight
        normalized_positions.append(
            {
                "ticker": ticker,
                "asset_type": _asset_type(item.get("asset_type")),
                "target_weight": _number_text(weight),
            }
        )
    cash_weight = _decimal(payload.get("cash_weight"), "target cash_weight")
    if abs(total + cash_weight - Decimal("1")) > WEIGHT_TOLERANCE:
        raise PaperLedgerError("target positions and cash must sum to one")
    result: dict[str, Any] = {
        "decision_at": decision_at.isoformat(),
        "positions": sorted(normalized_positions, key=lambda item: (item["asset_type"], item["ticker"])),
        "cash_weight": _number_text(cash_weight),
    }
    if "selector_provenance" in payload:
        result["selector_provenance"] = _json_object(payload["selector_provenance"], "selector_provenance")
    return result


def _normalize_fill(payload: dict[str, Any], fee_rate: Decimal, currency: str,
                    *, evidence_kind: str = "actual_provided_fill") -> dict[str, Any]:
    units = _decimal(payload.get("units"), "fill units", positive=True)
    price = _decimal(payload.get("price"), "fill price", positive=True)
    fee = _decimal(payload.get("fee"), "fill fee")
    expected_fee = units * price * fee_rate
    if fee != expected_fee:
        raise PaperLedgerError("fill fee does not match ledger fee_rate")
    if str(payload.get("currency", "")).upper() != currency:
        raise PaperLedgerError("fill currency mismatch")
    evidence = _json_object(payload.get("execution_evidence"), "execution_evidence")
    if evidence.get("kind") != evidence_kind or not str(evidence.get("reference", "")).strip():
        raise PaperLedgerError("fill requires actual provided execution evidence")
    if evidence_kind in {"observed_open_paper_fill", "delayed_daily_open_paper_fill"}:
        if evidence.get("not_broker_execution") is not True:
            raise PaperLedgerError("paper fills must explicitly exclude broker execution")
        _sha256(evidence.get("target_sha256"), "paper target hash")
        if evidence_kind == "observed_open_paper_fill":
            _sha256(evidence.get("quote_sha256"), "paper quote hash")
        else:
            _sha256(evidence.get("daily_sha256"), "delayed daily source hash")
            _sha256(evidence.get("plan_sha256"), "sealed delayed plan hash")
            if evidence.get("price_basis") != "RETROSPECTIVE_OFFICIAL_DAILY_OPEN_ASSUMPTION":
                raise PaperLedgerError("delayed paper price basis is invalid")
            if type(evidence.get("source_binding_verified")) is not bool:
                raise PaperLedgerError("delayed source binding status required")
            _aware(evidence.get("confirmed_at"), "delayed confirmation")
    return {
        "ticker": _text(payload.get("ticker"), "fill ticker"),
        "asset_type": _asset_type(payload.get("asset_type")),
        "side": _side(payload.get("side")),
        "units": _number_text(units),
        "price": _number_text(price),
        "fee": _number_text(fee),
        "currency": currency,
        "execution_evidence": evidence,
    }


def _normalize_nonfill(payload: dict[str, Any]) -> dict[str, Any]:
    reason = _text(payload.get("reason"), "nonfill reason")
    status = str(payload.get("status", "OPEN")).upper()
    if status not in {"OPEN", "FINAL"}:
        raise PaperLedgerError("nonfill status must be OPEN or FINAL")
    result = {
        "ticker": _text(payload.get("ticker"), "nonfill ticker"),
        "asset_type": _asset_type(payload.get("asset_type")),
        "side": _side(payload.get("side")),
        "requested_units": _number_text(
            _decimal(payload.get("requested_units"), "nonfill requested_units", positive=True)
        ),
        "reason": reason,
        "status": status,
    }
    if "delayed_plan_sha256" in payload:
        result["delayed_plan_sha256"] = _sha256(payload["delayed_plan_sha256"], "delayed plan hash")
    return result


def _normalize_mark(payload: dict[str, Any], currency: str, observed_at: datetime) -> dict[str, Any]:
    if str(payload.get("currency", "")).upper() != currency:
        raise PaperLedgerError("mark currency mismatch")
    price_asof = _aware(payload.get("price_asof"), "mark price_asof")
    if price_asof > observed_at:
        raise PaperLedgerError("mark price_asof cannot be after observed_at")
    return {
        "ticker": _text(payload.get("ticker"), "mark ticker"),
        "asset_type": _asset_type(payload.get("asset_type")),
        "price": _number_text(_decimal(payload.get("price"), "mark price", positive=True)),
        "price_asof": price_asof.isoformat(),
        "currency": currency,
    }


def _normalize_rights(payload: dict[str, Any], currency: str) -> dict[str, Any]:
    status = str(payload.get("status", "")).upper()
    if status not in {"UNKNOWN", "CONFIRMED_NOT_RECEIVED", "RECEIVED"}:
        raise PaperLedgerError("rights status is invalid")
    entitlement_type = str(payload.get("entitlement_type", "")).upper()
    if entitlement_type not in {"CASH", "STOCK"}:
        raise PaperLedgerError("rights entitlement_type must be CASH or STOCK")
    amount = payload.get("cash_amount")
    units = payload.get("units")
    evidence = payload.get("evidence")
    if status == "UNKNOWN":
        if amount is not None or units is not None or evidence is not None:
            raise PaperLedgerError("unknown rights cannot contain guessed value or evidence")
        normalized_amount = None
        normalized_units = None
        normalized_evidence = None
    else:
        normalized_evidence = _json_object(evidence, "rights evidence")
        expected_kind = "official_confirmation"
        if status == "RECEIVED":
            expected_kind = "actual_cash_received" if entitlement_type == "CASH" else "actual_stock_received"
        if (
            normalized_evidence.get("kind") != expected_kind
            or not str(normalized_evidence.get("reference", "")).strip()
        ):
            raise PaperLedgerError("rights evidence does not match status")
        if entitlement_type == "CASH":
            normalized_amount = _number_text(_decimal(amount, "rights cash_amount", positive=True))
            if units is not None:
                raise PaperLedgerError("cash rights cannot contain units")
            normalized_units = None
        else:
            normalized_units = _number_text(_decimal(units, "rights units", positive=True))
            if amount is not None:
                raise PaperLedgerError("stock rights cannot contain cash_amount")
            normalized_amount = None
    if str(payload.get("currency", "")).upper() != currency:
        raise PaperLedgerError("rights currency mismatch")
    return {
        "right_id": _text(payload.get("right_id"), "right_id"),
        "ticker": _text(payload.get("ticker"), "rights ticker"),
        "asset_type": _asset_type(payload.get("asset_type")),
        "entitlement_type": entitlement_type,
        "status": status,
        "cash_amount": normalized_amount,
        "units": normalized_units,
        "currency": currency,
        "evidence": normalized_evidence,
    }


class Quant25PaperLedger:
    """Append-only SQLite ledger with deterministic restart recovery."""

    def __init__(self, path: Path, config: LedgerConfig) -> None:
        self.path = _guard_isolated_path(path)
        self.config = config

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        freeze_id: str,
        starting_capital: Any,
        currency: str,
        fee_rate: Any,
        created_at: Any,
    ) -> "Quant25PaperLedger":
        resolved = _guard_isolated_path(path)
        if resolved.exists():
            raise PaperLedgerError("ledger path already exists")
        if freeze_id != FREEZE_ID:
            raise PaperLedgerError("ledger freeze_id does not match frozen release")
        capital = _decimal(starting_capital, "starting_capital", positive=True)
        normalized_currency = _text(currency, "currency").upper()
        normalized_fee_rate = _decimal(fee_rate, "fee_rate")
        if normalized_fee_rate >= 1:
            raise PaperLedgerError("fee_rate must be less than one")
        created = _aware(created_at, "created_at")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(resolved)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(
                """
                CREATE TABLE ledger_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    freeze_id TEXT NOT NULL,
                    starting_capital TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    fee_rate TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    profiles_json TEXT NOT NULL
                );
                CREATE TABLE ledger_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    profile_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    right_payment_key TEXT UNIQUE
                );
                CREATE INDEX idx_ledger_events_profile_sequence
                    ON ledger_events(profile_id, sequence);
                CREATE TRIGGER ledger_events_no_update
                    BEFORE UPDATE ON ledger_events BEGIN
                    SELECT RAISE(ABORT, 'ledger_events is append-only');
                END;
                CREATE TRIGGER ledger_events_no_delete
                    BEFORE DELETE ON ledger_events BEGIN
                    SELECT RAISE(ABORT, 'ledger_events is append-only');
                END;
                CREATE TRIGGER ledger_metadata_no_update
                    BEFORE UPDATE ON ledger_metadata BEGIN
                    SELECT RAISE(ABORT, 'ledger_metadata is immutable');
                END;
                CREATE TRIGGER ledger_metadata_no_delete
                    BEFORE DELETE ON ledger_metadata BEGIN
                    SELECT RAISE(ABORT, 'ledger_metadata is immutable');
                END;
                """
            )
            connection.execute(
                """INSERT INTO ledger_metadata VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    SCHEMA_VERSION,
                    CLASSIFICATION,
                    freeze_id,
                    _number_text(capital),
                    normalized_currency,
                    _number_text(normalized_fee_rate),
                    created.isoformat(),
                    json.dumps(sorted(PROFILE_IDS), separators=(",", ":")),
                ),
            )
            connection.commit()
        except Exception:
            connection.close()
            if resolved.exists():
                resolved.unlink()
            raise
        finally:
            if connection:
                connection.close()
        return cls.open(resolved)

    @classmethod
    def open(cls, path: Path) -> "Quant25PaperLedger":
        resolved = _guard_isolated_path(path)
        if not resolved.is_file():
            raise PaperLedgerError("ledger file does not exist")
        connection = sqlite3.connect(resolved)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT * FROM ledger_metadata WHERE singleton = 1").fetchone()
        except sqlite3.DatabaseError as exc:
            raise PaperLedgerError("invalid ledger database") from exc
        finally:
            connection.close()
        if row is None or row["schema_version"] != SCHEMA_VERSION:
            raise PaperLedgerError("unsupported ledger schema")
        if row["classification"] != CLASSIFICATION or row["freeze_id"] != FREEZE_ID:
            raise PaperLedgerError("ledger metadata contract mismatch")
        if set(json.loads(row["profiles_json"])) != PROFILE_IDS:
            raise PaperLedgerError("ledger profile set mismatch")
        config = LedgerConfig(
            freeze_id=row["freeze_id"],
            starting_capital=_decimal(row["starting_capital"], "stored starting_capital", positive=True),
            currency=row["currency"],
            fee_rate=_decimal(row["fee_rate"], "stored fee_rate"),
            created_at=_aware(row["created_at"], "stored created_at"),
        )
        return cls(resolved, config)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _normalize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise PaperLedgerError("event must be an object")
        required = {
            "event_id",
            "profile_id",
            "event_type",
            "occurred_at",
            "observed_at",
            "source_sha256",
            "arrival_provenance",
            "payload",
        }
        if set(event) != required:
            raise PaperLedgerError("event fields do not match ledger contract")
        event_id = _text(event["event_id"], "event_id")
        profile_id = str(event["profile_id"])
        if profile_id not in PROFILE_IDS:
            raise PaperLedgerError("profile_id is not part of the frozen release")
        event_type = str(event["event_type"]).lower()
        if event_type not in EVENT_TYPES:
            raise PaperLedgerError("event_type is invalid")
        occurred_at = _aware(event["occurred_at"], "occurred_at")
        observed_at = _aware(event["observed_at"], "observed_at")
        if observed_at < occurred_at:
            raise PaperLedgerError("observed_at cannot precede occurred_at")
        arrival = _json_object(event["arrival_provenance"], "arrival_provenance")
        if not str(arrival.get("source_ref", "")).strip():
            raise PaperLedgerError("arrival_provenance requires source_ref")
        received_at = _aware(arrival.get("received_at"), "arrival received_at")
        if received_at != observed_at:
            raise PaperLedgerError("arrival received_at must equal observed_at")
        payload = _json_object(event["payload"], "payload")
        if event_type == "target":
            normalized_payload = _normalize_target(payload, observed_at, profile_id)
        elif event_type in {"fill", "paper_fill"}:
            kind = (payload.get("execution_evidence") or {}).get("kind")
            normalized_payload = _normalize_fill(
                payload, self.config.fee_rate, self.config.currency,
                evidence_kind=(kind if event_type == "paper_fill"
                               and kind == "delayed_daily_open_paper_fill" else
                               "observed_open_paper_fill" if event_type == "paper_fill" else "actual_provided_fill"))
        elif event_type == "nonfill":
            normalized_payload = _normalize_nonfill(payload)
        elif event_type == "mark":
            normalized_payload = _normalize_mark(payload, self.config.currency, observed_at)
        else:
            normalized_payload = _normalize_rights(payload, self.config.currency)
        return {
            "event_id": event_id,
            "profile_id": profile_id,
            "event_type": event_type,
            "occurred_at": occurred_at.isoformat(),
            "observed_at": observed_at.isoformat(),
            "source_sha256": _sha256(event["source_sha256"], "source_sha256"),
            "arrival_provenance": arrival,
            "payload": normalized_payload,
        }

    @staticmethod
    def _events(connection: sqlite3.Connection, profile_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT event_json FROM ledger_events WHERE profile_id = ? ORDER BY sequence",
            (profile_id,),
        ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]

    def _balances(
        self, connection: sqlite3.Connection, profile_id: str
    ) -> tuple[Decimal, dict[str, Decimal], dict[str, str]]:
        cash = self.config.starting_capital
        units: dict[str, Decimal] = {}
        asset_types: dict[str, str] = {}
        for event in self._events(connection, profile_id):
            payload = event["payload"]
            if event["event_type"] in {"fill", "paper_fill"}:
                ticker = payload["ticker"]
                quantity = Decimal(payload["units"])
                notional = quantity * Decimal(payload["price"])
                fee = Decimal(payload["fee"])
                asset_types[ticker] = payload["asset_type"]
                if payload["side"] == "BUY":
                    cash -= notional + fee
                    units[ticker] = units.get(ticker, Decimal("0")) + quantity
                else:
                    cash += notional - fee
                    units[ticker] = units.get(ticker, Decimal("0")) - quantity
            elif event["event_type"] == "rights" and payload["status"] == "RECEIVED":
                if payload["entitlement_type"] == "CASH":
                    cash += Decimal(payload["cash_amount"])
                else:
                    ticker = payload["ticker"]
                    asset_types[ticker] = payload["asset_type"]
                    units[ticker] = units.get(ticker, Decimal("0")) + Decimal(payload["units"])
        return cash, units, asset_types

    def _validate_observation_order(self, connection: sqlite3.Connection, event: dict[str, Any]) -> None:
        observed_at = _aware(event["observed_at"], "observed_at")
        if observed_at < self.config.created_at:
            raise PaperLedgerError("observed_at cannot precede ledger created_at")
        previous = connection.execute(
            """
            SELECT observed_at FROM ledger_events
            WHERE profile_id = ? ORDER BY sequence DESC LIMIT 1
            """,
            (event["profile_id"],),
        ).fetchone()
        if previous is not None and observed_at < _aware(previous["observed_at"], "previous observed_at"):
            raise PaperLedgerError("profile observed_at must be monotonic")

    def _validate_transition(self, connection: sqlite3.Connection, event: dict[str, Any]) -> None:
        payload = event["payload"]
        if event["event_type"] in {"fill", "paper_fill"}:
            cash, units, _ = self._balances(connection, event["profile_id"])
            quantity = Decimal(payload["units"])
            notional = quantity * Decimal(payload["price"])
            fee = Decimal(payload["fee"])
            if payload["side"] == "BUY" and cash - notional - fee < 0:
                raise PaperLedgerError("fill would create negative cash")
            if payload["side"] == "SELL" and units.get(payload["ticker"], Decimal("0")) - quantity < 0:
                raise PaperLedgerError("fill would create negative units")
        if event["event_type"] == "rights" and payload["status"] == "RECEIVED":
            key = f"{event['profile_id']}:{payload['right_id']}"
            existing = connection.execute(
                "SELECT event_id FROM ledger_events WHERE right_payment_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                raise PaperLedgerError("rights receipt is already recorded")

    def append_events(self, events: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
        normalized_events = [self._normalize_event(event) for event in events]
        if not normalized_events:
            raise PaperLedgerError("at least one event is required")
        connection = self._connect()
        results: list[dict[str, str]] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            for event in normalized_events:
                digest = canonical_sha256(event)
                existing = connection.execute(
                    "SELECT payload_sha256 FROM ledger_events WHERE event_id = ?",
                    (event["event_id"],),
                ).fetchone()
                if existing is not None:
                    if existing["payload_sha256"] != digest:
                        raise PaperLedgerError("event_id content mutation is prohibited")
                    results.append({"event_id": event["event_id"], "status": "no_op_same_payload"})
                    continue
                self._validate_observation_order(connection, event)
                self._validate_transition(connection, event)
                right_payment_key = None
                if event["event_type"] == "rights" and event["payload"]["status"] == "RECEIVED":
                    right_payment_key = f"{event['profile_id']}:{event['payload']['right_id']}"
                connection.execute(
                    """
                    INSERT INTO ledger_events (
                        event_id, profile_id, event_type, occurred_at, observed_at,
                        source_sha256, payload_sha256, event_json, right_payment_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_id"],
                        event["profile_id"],
                        event["event_type"],
                        event["occurred_at"],
                        event["observed_at"],
                        event["source_sha256"],
                        digest,
                        json.dumps(
                            event,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                        right_payment_key,
                    ),
                )
                results.append({"event_id": event["event_id"], "status": "appended"})
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return results

    def append_event(self, event: dict[str, Any]) -> dict[str, str]:
        return self.append_events([event])[0]

    def snapshot(self, profile_id: str, *, as_of: Any | None = None) -> dict[str, Any]:
        if profile_id not in PROFILE_IDS:
            raise PaperLedgerError("profile_id is not part of the frozen release")
        cutoff = _aware(as_of, "as_of") if as_of is not None else None
        connection = self._connect()
        try:
            events = self._events(connection, profile_id)
        finally:
            connection.close()
        if cutoff is not None:
            events = [event for event in events if _aware(event["observed_at"], "observed_at") <= cutoff]
        cash = self.config.starting_capital
        units: dict[str, Decimal] = {}
        asset_types: dict[str, str] = {}
        marks: dict[str, tuple[Decimal, datetime]] = {}
        latest_target = None
        nonfills: list[dict[str, Any]] = []
        rights: list[dict[str, Any]] = []
        total_fees = Decimal("0")
        for event in events:
            payload = event["payload"]
            if event["event_type"] == "target":
                latest_target = event
            elif event["event_type"] in {"fill", "paper_fill"}:
                ticker = payload["ticker"]
                quantity = Decimal(payload["units"])
                price = Decimal(payload["price"])
                fee = Decimal(payload["fee"])
                total_fees += fee
                asset_types[ticker] = payload["asset_type"]
                marks[ticker] = (price, _aware(event["occurred_at"], "fill occurred_at"))
                if payload["side"] == "BUY":
                    cash -= quantity * price + fee
                    units[ticker] = units.get(ticker, Decimal("0")) + quantity
                else:
                    cash += quantity * price - fee
                    units[ticker] = units.get(ticker, Decimal("0")) - quantity
            elif event["event_type"] == "nonfill":
                nonfills.append(event)
            elif event["event_type"] == "mark":
                marks[payload["ticker"]] = (
                    Decimal(payload["price"]),
                    _aware(payload["price_asof"], "mark price_asof"),
                )
                asset_types[payload["ticker"]] = payload["asset_type"]
            elif event["event_type"] == "rights":
                rights.append(event)
                if payload["status"] == "RECEIVED":
                    if payload["entitlement_type"] == "CASH":
                        cash += Decimal(payload["cash_amount"])
                    else:
                        ticker = payload["ticker"]
                        asset_types[ticker] = payload["asset_type"]
                        units[ticker] = units.get(ticker, Decimal("0")) + Decimal(payload["units"])
        if cash < 0 or any(quantity < 0 for quantity in units.values()):
            raise PaperLedgerError("stored ledger violates nonnegative balance contract")
        positions = []
        missing_marks: list[str] = []
        stale_marks: list[dict[str, str]] = []
        last_known_market_value = Decimal("0")
        confirmed_market_value = Decimal("0")
        for ticker, quantity in sorted(units.items()):
            if quantity == 0:
                continue
            mark_record = marks.get(ticker)
            mark = mark_record[0] if mark_record is not None else None
            mark_asof = mark_record[1] if mark_record is not None else None
            usable_for_asof = mark_record is not None and (cutoff is None or mark_asof.date() == cutoff.date())
            last_known_value = None
            if mark is None:
                missing_marks.append(ticker)
            else:
                value_decimal = quantity * mark
                last_known_market_value += value_decimal
                last_known_value = _number_text(value_decimal)
                if usable_for_asof:
                    confirmed_market_value += value_decimal
                else:
                    stale_marks.append({"ticker": ticker, "price_asof": mark_asof.isoformat()})
            positions.append(
                {
                    "ticker": ticker,
                    "asset_type": asset_types[ticker],
                    "units": _number_text(quantity),
                    "mark_price": _number_text(mark) if mark is not None else None,
                    "mark_price_asof": mark_asof.isoformat() if mark_asof is not None else None,
                    "market_value": last_known_value if usable_for_asof else None,
                    "last_known_market_value": last_known_value,
                }
            )
        valuation_incomplete = bool(missing_marks or stale_marks)
        market_value = None if valuation_incomplete else _number_text(confirmed_market_value)
        nav = None if valuation_incomplete else _number_text(cash + confirmed_market_value)
        nav_status = "pass" if not valuation_incomplete else "stale_or_asof_unknown"
        paper_kinds = {e["payload"]["execution_evidence"]["kind"] for e in events
                       if e["event_type"] == "paper_fill"}
        delayed_verified = any(
            e["event_type"] == "paper_fill" and
            e["payload"]["execution_evidence"]["kind"] == "delayed_daily_open_paper_fill" and
            e["payload"]["execution_evidence"]["source_binding_verified"] is True
            for e in events)
        delayed_unverified = "delayed_daily_open_paper_fill" in paper_kinds and not delayed_verified
        return {
            "schema_version": SCHEMA_VERSION,
            "classification": ("PRIVATE_DELAYED_PAPER_RESEARCH_ONLY" if delayed_unverified else
                               "PRIVATE_DELAYED_PAPER" if delayed_verified else
                               "PRIVATE_OBSERVED_OPEN_PAPER" if paper_kinds else CLASSIFICATION),
            "freeze_id": self.config.freeze_id,
            "profile_id": profile_id,
            "as_of": cutoff.isoformat() if cutoff is not None else None,
            "starting_capital": _number_text(self.config.starting_capital),
            "currency": self.config.currency,
            "fee_rate": _number_text(self.config.fee_rate),
            "event_count": len(events),
            "latest_target": latest_target,
            "positions": positions,
            "cash": _number_text(cash),
            "market_value": market_value,
            "last_known_market_value": _number_text(last_known_market_value),
            "nav": nav,
            "nav_status": nav_status,
            "return_status": "available" if not valuation_incomplete else "unconfirmed",
            "missing_marks": missing_marks,
            "stale_marks": stale_marks,
            "total_fees": _number_text(total_fees),
            "nonfills": nonfills,
            "rights": rights,
            "targets_are_fills": False,
            "paper_live_started": bool(paper_kinds) and not delayed_unverified,
            "broker_execution": False if any(e["event_type"] == "paper_fill" for e in events) else None,
        }

    def event_count(self) -> int:
        connection = self._connect()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0])
        finally:
            connection.close()
