"""Confirmed dividend receivables, separate from spendable settlement cash.

Research primitive only: not connected to operational or historical NAV engines.
Unknown ex/record/pay dates or amount availability must block recognition.
"""

import hashlib
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.evaluation.corporate_actions import ContractViolation, number


@dataclass(frozen=True)
class CashEvent:
    event_id: str
    ticker: str
    ex_date: date
    record_date: date
    pay_date: date
    cash_per_unit: Decimal
    available_at: datetime
    source_hash: str
    date_quality: str


@dataclass(frozen=True)
class Receivable:
    event_id: str
    ticker: str
    entitled_units: Decimal
    amount: Decimal
    pay_date: date


@dataclass(frozen=True)
class CashClaims:
    receivables: tuple[Receivable, ...] = ()
    recognized_ids: frozenset[str] = frozenset()
    settled_cash: Decimal = Decimal(0)  # Cumulative credits, not the broker's spendable cash balance.

    @property
    def receivable_value(self):
        return sum((r.amount for r in self.receivables), Decimal(0))


def recognize_ex_date(state, events, *, day, previous_session, holdings_asof, units, tax_rate, source_bytes):
    """Caller supplies previous-session closing units; ex-day buyers get no claim."""
    if holdings_asof != previous_session or previous_session >= day:
        raise ContractViolation("previous-session closing units required")
    tax = number(tax_rate, "explicit research withholding rate")
    if tax >= 1:
        raise ContractViolation("invalid withholding rate")
    ids = [e.event_id for e in events]
    if len(set(ids)) != len(ids) or set(ids) & state.recognized_ids:
        raise ContractViolation("duplicate event or correction requires replay")
    claims, audit = list(state.receivables), []
    cutoff = datetime.combine(day, time(9), ZoneInfo("Asia/Seoul"))
    for event in events:
        if not event.event_id or not event.ticker or event.ticker == "CASH":
            raise ContractViolation("event and security identity required")
        if event.ex_date != day or not isinstance(event.record_date, date) or not isinstance(event.pay_date, date):
            raise ContractViolation("confirmed ex/record/pay date required")
        if not event.ex_date <= event.record_date <= event.pay_date:
            raise ContractViolation("inconsistent entitlement dates")
        if event.date_quality not in {"OFFICIAL_EXPLICIT", "OFFICIAL_RULE_DERIVED"}:
            raise ContractViolation("unproven date or proxy date")
        if not isinstance(event.available_at, datetime) or event.available_at.tzinfo is None or event.available_at.utcoffset() is None or event.available_at > cutoff:
            raise ContractViolation("amount or dates unavailable before ex-date trading")
        if len(event.source_hash) != 64 or any(c not in "0123456789abcdef" for c in event.source_hash.lower()):
            raise ContractViolation("verified source SHA-256 required")
        raw = source_bytes.get(event.event_id)
        if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != event.source_hash.lower():
            raise ContractViolation("immutable source bytes missing or hash mismatch")
        quantity = number(units.get(event.ticker, 0), "entitled units")
        gross = quantity * number(event.cash_per_unit, "cash per unit", positive=True)
        net = gross*(1-tax)
        if quantity:
            claims.append(Receivable(event.event_id, event.ticker, quantity, net, event.pay_date))
        audit.append({"event_id": event.event_id, "entitled_units": str(quantity), "gross_claim": str(gross), "net_claim": str(net), "spendable_cash_credit": "0"})
    return replace(state, receivables=tuple(claims), recognized_ids=state.recognized_ids | frozenset(ids)), audit


def settle_cash(state, *, day, phase):
    """Return incremental cash credit once; caller adds only that delta to cash.

    Date-only payments are usable after pay-day close, never that day's open.
    """
    if phase not in {"BEFORE_OPEN", "AFTER_CLOSE"}:
        raise ContractViolation("explicit settlement phase required")
    due = [r for r in state.receivables if r.pay_date < day or (phase == "AFTER_CLOSE" and r.pay_date == day)]
    credit = sum((r.amount for r in due), Decimal(0))
    ids = {r.event_id for r in due}
    pending = tuple(r for r in state.receivables if r.event_id not in ids)
    return replace(state, receivables=pending, settled_cash=state.settled_cash+credit), credit
