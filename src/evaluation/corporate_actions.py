"""Pure, fail-closed research accounting; no DB access or operating integration.

All event accounting consumes pre-session holdings and raw prices. Source
adapters must verify hashes against immutable bytes and certify completeness;
these helpers never infer an event or imply total-return source readiness.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

CASH_EVENTS = {"cash_dividend", "etf_distribution"}
SPLIT_EVENTS = {"split", "reverse_split"}
STOCK_EVENTS = {"stock_merger", "stock_exchange"}
TERMINAL_EVENTS = {"cash_merger", "delisting"}
EVENT_KINDS = CASH_EVENTS | SPLIT_EVENTS | STOCK_EVENTS | TERMINAL_EVENTS


class ContractViolation(ValueError):
    """Missing, ambiguous, or non-PIT evidence must stop accounting."""


def number(value: object, name: str, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ContractViolation(f"invalid {name}") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ContractViolation(f"invalid {name}")
    return result


def aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractViolation("timezone-aware timestamp required")


@dataclass(frozen=True)
class Provenance:
    source: str
    revision: int
    source_hash: str
    source_published_at: datetime
    available_at: datetime
    pit_evidence: str
    evidence_id: str


def validate_provenance(provenance: Provenance, information_cutoff: datetime) -> None:
    aware(information_cutoff)
    aware(provenance.source_published_at)
    aware(provenance.available_at)
    if not provenance.source.strip() or not provenance.evidence_id.strip():
        raise ContractViolation("missing source or evidence_id")
    if type(provenance.revision) is not int or provenance.revision < 1:
        raise ContractViolation("positive integer revision required")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", provenance.source_hash):
        raise ContractViolation("source_hash must be SHA-256")
    if provenance.pit_evidence != "observed_pit":
        raise ContractViolation("observed_pit provenance required")
    if not provenance.source_published_at <= provenance.available_at <= information_cutoff:
        raise ContractViolation("source unavailable at information cutoff")


def verify_source_bytes(provenance: Provenance, source_bytes: bytes) -> None:
    if hashlib.sha256(source_bytes).hexdigest() != provenance.source_hash.lower():
        raise ContractViolation("source_hash mismatch")


@dataclass(frozen=True)
class CorporateAction:
    event_id: str
    kind: str
    ticker: str
    effective_date: date
    provenance: Provenance
    confirmed: bool = False
    date_quality: str = "unproven"
    ex_date: date | None = None
    cash_per_unit: Decimal | None = None
    ratio: Decimal | None = None
    successor_ticker: str | None = None
    currency: str = "KRW"


def validate_event(event: CorporateAction, event_date: date, information_cutoff: datetime) -> None:
    validate_provenance(event.provenance, information_cutoff)
    if not event.event_id.strip() or not event.ticker.strip() or event.ticker == "CASH":
        raise ContractViolation("event_id and security ticker required")
    if event.kind not in EVENT_KINDS or event.confirmed is not True:
        raise ContractViolation("unsupported or unconfirmed event")
    if event.effective_date != event_date or event.date_quality != "confirmed_effective_date":
        raise ContractViolation("confirmed effective date required")
    if event.currency != "KRW":
        raise ContractViolation("FX accounting not contracted")
    if event.kind in CASH_EVENTS:
        if event.ex_date != event_date:
            raise ContractViolation("confirmed ex_date required")
        number(event.cash_per_unit, "cash_per_unit", positive=True)
        if event.ratio is not None or event.successor_ticker is not None:
            raise ContractViolation("mixed dividend terms not contracted")
    elif event.kind in SPLIT_EVENTS | STOCK_EVENTS:
        number(event.ratio, "ratio", positive=True)
        if event.kind in STOCK_EVENTS and (
            not event.successor_ticker or not event.successor_ticker.strip()
            or event.successor_ticker in {event.ticker, "CASH"}
        ):
            raise ContractViolation("successor ticker required")
        if event.cash_per_unit is not None:
            raise ContractViolation("mixed cash/stock or split cash terms not contracted")
        if event.kind in SPLIT_EVENTS and event.successor_ticker is not None:
            raise ContractViolation("split cannot change ticker")
        if event.kind == "split" and number(event.ratio, "ratio") <= 1:
            raise ContractViolation("split ratio must exceed 1")
        if event.kind == "reverse_split" and number(event.ratio, "ratio") >= 1:
            raise ContractViolation("reverse split ratio must be below 1")
    elif event.kind in TERMINAL_EVENTS:
        # Explicit confirmed zero is distinct from an absent price/consideration.
        number(event.cash_per_unit, "confirmed cash consideration")
        if event.ratio is not None or event.successor_ticker is not None:
            raise ContractViolation("mixed terminal terms not contracted")


@dataclass(frozen=True)
class PortfolioState:
    asof_date: date
    units: Mapping[str, Decimal]
    cash: Decimal
    applied_event_ids: frozenset[str] = field(default_factory=frozenset)


def apply_actions(
    state: PortfolioState,
    events: Sequence[CorporateAction],
    *,
    event_date: date,
    information_cutoff: datetime,
) -> tuple[PortfolioState, tuple[dict, ...]]:
    """Apply one session's confirmed actions before trades; never reinvest cash.

Caller must supply the previous session close state. Same-instrument compound
events (including a successor's event) require a separate sequencing contract.
Corrections to an already applied event require replay, never a second credit.
"""
    aware(information_cutoff)
    if state.asof_date >= event_date:
        raise ContractViolation("previous-session close state required")
    # A post-session timestamp cannot be used to backfill historical knowledge.
    if information_cutoff > datetime.combine(event_date, time(9), ZoneInfo("Asia/Seoul")):
        raise ContractViolation("post-event information cutoff")
    units = {ticker: number(value, "units") for ticker, value in state.units.items()}
    if any(not ticker.strip() or ticker == "CASH" for ticker in units):
        raise ContractViolation("invalid units ticker")
    cash = number(state.cash, "cash")
    ids = [event.event_id for event in events]
    tickers = [event.ticker for event in events]
    if len(set(ids)) != len(ids) or set(ids) & state.applied_event_ids:
        raise ContractViolation("duplicate event or revision requires replay")
    if len(set(tickers)) != len(tickers) or any(event.successor_ticker in tickers for event in events):
        raise ContractViolation("compound event sequence not contracted")
    for event in events:
        validate_event(event, event_date, information_cutoff)
    ledger = []
    for event in events:
        before = units.get(event.ticker, Decimal(0))
        credit = Decimal(0)
        labels = []
        if event.kind in CASH_EVENTS:
            credit = before * number(event.cash_per_unit, "cash_per_unit", positive=True)
            labels.append("EX_DATE_CASH_CREDIT_RESEARCH_NOT_PAY_DATE_SETTLEMENT")
        elif event.kind in SPLIT_EVENTS:
            units[event.ticker] = before * number(event.ratio, "ratio", positive=True)
        elif event.kind in STOCK_EVENTS:
            successor = str(event.successor_ticker)
            units[successor] = units.get(successor, Decimal(0)) + before * number(event.ratio, "ratio", positive=True)
            units.pop(event.ticker, None)
            labels.append("EXACT_FRACTIONAL_RESEARCH_UNITS")
        else:
            credit = before * number(event.cash_per_unit, "cash consideration")
            units.pop(event.ticker, None)
        cash += credit
        ledger.append({
            "event_id": event.event_id, "kind": event.kind, "ticker": event.ticker,
            "effective_date": event_date.isoformat(), "entitled_units": str(before),
            "cash_credit": str(credit), "revision": event.provenance.revision,
            "source": event.provenance.source, "source_hash": event.provenance.source_hash,
            "available_at": event.provenance.available_at.isoformat(),
            "source_published_at": event.provenance.source_published_at.isoformat(),
            "pit_evidence": event.provenance.pit_evidence,
            "evidence_id": event.provenance.evidence_id, "labels": labels,
        })
    return PortfolioState(event_date, units, cash, state.applied_event_ids | frozenset(ids)), tuple(ledger)


@dataclass(frozen=True)
class HaltStatus:
    ticker: str
    start_date: date
    through_date: date
    official: bool
    provenance: Provenance


@dataclass(frozen=True)
class OfficialClose:
    ticker: str
    date: date
    close: Decimal
    official: bool
    provenance: Provenance


def halted_price(
    status: HaltStatus,
    last_valid_close: OfficialClose | None,
    *,
    valuation_date: date,
    information_cutoff: datetime,
    for_execution: bool = False,
) -> tuple[Decimal, str]:
    if for_execution:
        raise ContractViolation("halted execution prohibited")
    validate_provenance(status.provenance, information_cutoff)
    if information_cutoff.astimezone(ZoneInfo("Asia/Seoul")).date() > valuation_date:
        raise ContractViolation("post-valuation halt information cutoff")
    if not status.official or not status.start_date <= valuation_date <= status.through_date:
        raise ContractViolation("official date-bounded halt status required")
    if last_valid_close is None or not last_valid_close.official:
        raise ContractViolation("official last valid close required")
    validate_provenance(last_valid_close.provenance, information_cutoff)
    if last_valid_close.ticker != status.ticker or last_valid_close.date >= status.start_date:
        raise ContractViolation("pre-halt close for same ticker required")
    return number(last_valid_close.close, "last valid close", positive=True), "OFFICIAL_HALT_LAST_VALID_CLOSE_CARRY"


@dataclass(frozen=True)
class Coverage:
    instrument: str
    start_date: date
    end_date: date
    event_kinds: frozenset[str]
    status: str
    provenance: Provenance


def require_complete_coverage(
    coverage: Coverage | None, *, instrument: str, start_date: date, end_date: date,
    event_kinds: frozenset[str], information_cutoff: datetime,
) -> None:
    if coverage is None or coverage.status != "complete":
        raise ContractViolation("source completeness unproven")
    validate_provenance(coverage.provenance, information_cutoff)
    if start_date > end_date or coverage.instrument != instrument:
        raise ContractViolation("coverage instrument/window mismatch")
    if coverage.start_date > start_date or coverage.end_date < end_date or not event_kinds <= coverage.event_kinds:
        raise ContractViolation("coverage does not cover requested window/event kinds")


def validate_headline_benchmark(
    *, index_family: str, return_basis: str, currency: str,
    dates: Sequence[date], required_dates: Sequence[date],
    levels: Sequence[Decimal], start_clock: str, required_start_clock: str,
    official: bool, coverage: Coverage | None, provenance: Provenance,
    information_cutoff: datetime,
) -> None:
    if index_family != "KOSPI" or return_basis != "total_return":
        raise ContractViolation("PRICE_RETURN_DIAGNOSTIC_ONLY: KOSPI total-return required")
    if not official or currency != "KRW":
        raise ContractViolation("official KRW benchmark required")
    validate_provenance(provenance, information_cutoff)
    if not required_dates or tuple(dates) != tuple(required_dates) or list(dates) != sorted(set(dates)):
        raise ContractViolation("benchmark period/calendar mismatch")
    last_close_time = datetime.combine(dates[-1], time(15, 30), ZoneInfo("Asia/Seoul"))
    if not last_close_time <= provenance.source_published_at <= information_cutoff:
        raise ContractViolation("benchmark closing observations unavailable at cutoff")
    if not start_clock or start_clock != required_start_clock:
        raise ContractViolation("benchmark start clock mismatch")
    if len(levels) != len(dates):
        raise ContractViolation("benchmark levels missing")
    for value in levels:
        number(value, "benchmark level", positive=True)
    require_complete_coverage(
        coverage, instrument="KOSPI", start_date=dates[0], end_date=dates[-1],
        event_kinds=frozenset({"total_return_index"}), information_cutoff=information_cutoff,
    )
