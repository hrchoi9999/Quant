"""Q25 halt v1: frozen units, funded liquid book, no fictitious execution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date

import pandas as pd

from src.evaluation.corporate_actions import number
from src.evaluation.normalized_nav import ExecutionTarget, normalize_weights
from src.quant2.evaluation.quant25_cash_entitlements import CashClaims, recognize_ex_date, settle_cash
from src.quant2.evaluation.quant25_event_exclusion import announced_overlap
from src.quant2.evaluation.quant25_leverage_trim import LeverageTrimRule, reduction_notional
from src.quant2.evaluation.quant25_market_calibration import aware

OFFICIAL_SOURCES = {"krx_openapi", "KRX_OPENAPI_RAW_UNADJUSTED"}


@dataclass
class HaltReplay:
    nav: pd.DataFrame
    ledger: pd.DataFrame
    incidents: pd.DataFrame
    positions: pd.DataFrame
    failure: dict | None
    cash_ledger: pd.DataFrame = dataclass_field(default_factory=pd.DataFrame)
    cash_accounting_status: str = "PRICE_ONLY"


def selection_risk_rules(rules):
    """Map undated conditional notices to exclusion intervals, not halt dates.

    Keep the original notice intact. A later version of the same event replaces
    this precaution at its own publication time through announced_overlap.
    """
    result = []
    for original in rules:
        rule = dict(original)
        if rule.get("effective_from") is None:
            if (
                rule.get("conditional") is not True
                or rule.get("condition") != "HALT_ON_FUTURE_INVESTMENT_RISK_DESIGNATION_DATE"
                or rule.get("effective_until") is not None
            ):
                raise ValueError("unsupported undated event")
            aware(rule["known_at"])
            rule.update(
                official_effective_from=None,
                effective_from=rule["known_at"],
                interval_semantics="PRECAUTION_FROM_DISCLOSURE_UNTIL_UPDATED",
            )
        for field in ["effective_from", "effective_until"]:
            value = rule.get(field)
            if isinstance(value, str) and len(value) == 10:
                rule[field] = pd.Timestamp(value).tz_localize("Asia/Seoul").isoformat()
        result.append(rule)
    return result


def stock_targets(scores, prices, dates, calendar, variant, count, rules):
    """Intent only. Actual holdings and failed orders belong to replay state."""
    quotes = prices.set_index(["date", "ticker"])
    if not quotes.index.is_unique or count not in (15, 20, 25, 30):
        raise ValueError("unique quotes and declared stock count required")
    events, records = [], []
    for i, day in enumerate(dates):
        execution = next(d for d in calendar if d > day)
        horizon = next(d for d in calendar if d > dates[i + 1]) if i + 1 < len(dates) else calendar[-1]
        active = announced_overlap(
            rules, day + "T16:00:00+09:00", execution + "T09:00:00+09:00", horizon + "T09:00:00+09:00"
        )
        daily = scores.loc[scores.decision_date.eq(day) & scores.variant.eq(variant) & scores.eligible]
        names = daily.sort_values(["score", "ticker"], ascending=[False, True]).head(count).ticker
        weights, excluded = {}, []
        for ticker in names:
            try:
                q = quotes.loc[(day, ticker), ["open", "close", "volume"]].astype(float)
                usable = all(math.isfinite(v) and v > 0 for v in q)
            except (KeyError, ValueError, TypeError):
                usable = False
            if ticker in active or not usable:
                excluded.append(
                    {"ticker": ticker, "reason": "announced_event" if ticker in active else "decision_quote_unusable"}
                )
            else:
                weights[ticker] = 1 / count
        weights["CASH"] = max(0.0, 1 - sum(weights.values()))
        events.append(
            ExecutionTarget(
                variant,
                pd.Timestamp(day),
                pd.Timestamp(day + "T16:00:00+09:00"),
                pd.Timestamp(execution),
                "Q25_HALT_V1",
                weights,
                "RESEARCH_ONLY",
            )
        )
        records.append({"decision_date": day, "execution_date": execution, "weights": weights, "exclusions": excluded})
    return events, records


def funded_targets(liquid_pre, current, weights, locked_value, cost_bps, liquid_target_share=1.0):
    """Post-cost target amounts, capped by liquid capital; never finance on locks."""
    if not math.isfinite(cost_bps) or not 0 <= cost_bps < 10000:
        raise ValueError("invalid cost")
    if (
        liquid_pre < 0
        or locked_value < 0
        or not 0 <= liquid_target_share <= 1
        or sum(weights.values()) > liquid_target_share + 1e-9
    ):
        raise ValueError("invalid funded book")
    keys = sorted(set(current) | set(weights))

    def amounts(post):
        wanted = {k: weights.get(k, 0.0) * (post + locked_value) for k in keys}
        # Scale cash and failed-order reservations alongside securities.
        total = liquid_target_share * (post + locked_value)
        scale = min(1.0, post / total) if total else 1.0
        return {k: v * scale for k, v in wanted.items()}

    lo, hi = 0.0, liquid_pre
    for _ in range(70):
        mid = (lo + hi) / 2
        target = amounts(mid)
        gross = sum(abs(target[k] - current.get(k, 0.0)) for k in keys)
        if mid + cost_bps / 10000 * gross > liquid_pre:
            hi = mid
        else:
            lo = mid
    post = (lo + hi) / 2 if cost_bps else liquid_pre
    target = amounts(post)
    gross = sum(abs(target[k] - current.get(k, 0.0)) for k in keys)
    return target, max(0.0, post - sum(target.values())), gross * cost_bps / 10000


def replay_halts(
    events, prices, calendar, *, cost_bps, corporate_actions=(), verified_nontrading=(), max_holdings=None,
    cash_events=None, cash_source_bytes=None, cash_tax_rate=None, cash_price_basis=None,
    leverage_trim=None, fresh_entry_blocks=None,
):
    """Daily official marks may value locks, but never establish a fill.

    Unknown halt causes remain explicit provisional accounting observations.
    Known unhandled corporate actions and missing held marks still stop NAV.

    Optional research cash events recognize previous-close entitlements before
    trading and settle date-only payments after close. Receivables enter NAV,
    but cannot fund orders. This does NOT certify event/universe coverage or
    enable use of amounts that were unknown before their ex date. Raw prices
    and explicit tax assumptions are required; defaults retain price-only output.

    Optional leverage trim is triggered at a completed daily close and executed
    next tradable open, with regular rebalance taking priority. It is not an
    intraday hard cap. Halted units remain frozen until execution is possible.

    Optional fresh-entry blocks must be derived at each event's decision time.
    They apply only to unheld names; blocked target amounts stay in cash.
    """
    if not events or list(calendar) != sorted(set(calendar)):
        raise ValueError("events and ordered unique calendar required")
    if max_holdings is not None and (not isinstance(max_holdings, int) or max_holdings < 1):
        raise ValueError("positive integer holding cap required")
    if fresh_entry_blocks is not None:
        expected = {e.execution_date.strftime("%Y-%m-%d") for e in events}
        if set(fresh_entry_blocks) != expected or any(
            not isinstance(v, (set, frozenset)) or "CASH" in v for v in fresh_entry_blocks.values()
        ):
            raise ValueError("complete per-execution fresh-entry block sets required")
    if leverage_trim is not None:
        if not isinstance(leverage_trim, LeverageTrimRule):
            raise ValueError("explicit LeverageTrimRule required")
        for event in events:
            weights = normalize_weights(event.weights)
            if sum(weights.get(t, 0) for t in leverage_trim.tickers) > leverage_trim.target + 1e-10:
                raise ValueError("scheduled leverage target exceeds trim target")
    cash_enabled = cash_events is not None
    cash_by_day = {}
    if cash_enabled:
        if cash_tax_rate is None or not isinstance(cash_source_bytes, dict) or cash_price_basis != "RAW_UNADJUSTED":
            raise ValueError("cash replay requires explicit tax, source bytes and raw unadjusted prices")
        cash_events = list(cash_events)
        if len({e.event_id for e in cash_events}) != len(cash_events):
            raise ValueError("duplicate cash event or correction requires resolved revision")
        for e in cash_events:
            if not isinstance(e.ex_date, date) or e.ex_date.isoformat() not in calendar[1:]:
                raise ValueError("cash ex date requires an in-calendar previous closing session")
            cash_by_day.setdefault(e.ex_date.isoformat(), []).append(e)
        # Validate the explicit tax contract even when no events occur.
        if number(cash_tax_rate, "explicit research withholding rate") >= 1:
            raise ValueError("invalid withholding rate")
    elif any(v is not None for v in (cash_source_bytes, cash_tax_rate, cash_price_basis)):
        raise ValueError("cash parameters require an explicit cash_events list")
    quotes = prices.set_index(["date", "ticker"])
    if not quotes.index.is_unique:
        raise ValueError("duplicate quotes")
    verified_keys = set()
    for proof in verified_nontrading:
        key = (proof["date"], proof["ticker"])
        digest = proof["source_hash"].lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("verified quote source hash required")
        q = quotes.loc[key]
        if any(float(q[field]) != float(proof[field]) for field in ["open", "close", "volume"]):
            raise ValueError("verified nontrading quote differs from frozen input")
        verified_keys.add(key)
    by_day = {e.execution_date.strftime("%Y-%m-%d"): e for e in events}
    if len(by_day) != len(events) or not set(by_day) <= set(calendar):
        raise ValueError("duplicate or off-calendar events")
    cash, units, last_marks, pending = 1.0, {}, {}, set()
    navs, trades, notes, holdings = [], [], [], []
    claims, cash_rows = CashClaims(), []
    trim_pending = {}
    failure = None
    quote_cache = {}

    def row(day, ticker):
        key = (day, ticker)
        if key in quote_cache:
            return quote_cache[key]
        try:
            quote_cache[key] = quotes.loc[key]
        except KeyError:
            quote_cache[key] = None
        return quote_cache[key]

    def positive(q, field):
        try:
            return q is not None and math.isfinite(float(q[field])) and float(q[field]) > 0
        except (ValueError, TypeError, KeyError):
            return False

    def tradable(q):
        return positive(q, "open") and positive(q, "volume")

    def official_lock(q):
        return (
            q is not None
            and (q.get("source") in OFFICIAL_SOURCES or q.name in verified_keys)
            and positive(q, "close")
            and float(q.get("open", -1)) == 0
            and float(q.get("volume", -1)) == 0
        )

    def record(day, ticker, kind, **extra):
        notes.append({"date": day, "ticker": ticker, "kind": kind, **extra})

    for day_index, day in enumerate(calendar):
        try:
            if cash_enabled:
                day_date = date.fromisoformat(day)
                claims, credit = settle_cash(claims, day=day_date, phase="BEFORE_OPEN")
                cash += float(credit)
                if credit:
                    cash_rows.append({"date": day, "kind": "PAYMENT_BEFORE_OPEN", "cash_credit": float(credit)})
                if day in cash_by_day:
                    previous = date.fromisoformat(calendar[day_index - 1])
                    claims, audit = recognize_ex_date(
                        claims, cash_by_day[day], day=day_date, previous_session=previous,
                        holdings_asof=previous, units=units, tax_rate=cash_tax_rate, source_bytes=cash_source_bytes,
                    )
                    cash_rows.extend({"date": day, "kind": "EX_DATE_RECEIVABLE", **entry} for entry in audit)
            # Event rules are accounting guards, not permission to guess new units.
            active = announced_overlap(
                list(corporate_actions), day + "T08:59:00+09:00", day + "T09:00:00+09:00", day + "T09:00:00+09:00"
            )
            for ticker in units:
                if ticker in active and aware(active[ticker]["effective_from"]) <= aware(day + "T09:00:00+09:00"):
                    raise ValueError(f"unhandled_corporate_action:{ticker}")
                q = row(day, ticker)
                if not positive(q, "close"):
                    raise ValueError(f"held_mark_missing:{ticker}")
                if not tradable(q) and not official_lock(q):
                    raise ValueError(f"held_quote_unclassified:{ticker}")

            event = by_day.get(day)
            if event is not None:
                target = normalize_weights(event.weights)
                if fresh_entry_blocks is not None:
                    for t in sorted(fresh_entry_blocks[day] - set(units)):
                        if target.get(t, 0) > 0:
                            weight = target.pop(t)
                            target["CASH"] = target.get("CASH", 0) + weight
                            record(day, t, "UNHELD_ENTRY_GATE_TARGET_TO_CASH", weight=weight)
                locked = {t for t in units if official_lock(row(day, t))}
                if max_holdings is not None:
                    if len(locked) > max_holdings:
                        raise ValueError("locked_holdings_exceed_cap")
                    desired = [t for t, w in target.items() if t != "CASH" and w > 0 and t not in locked]
                    priority = [t for t in desired if t in units] + [t for t in desired if t not in units]
                    for t in priority[max_holdings - len(locked) :]:
                        weight = target.pop(t)
                        target["CASH"] = target.get("CASH", 0) + weight
                        record(day, t, "HOLDING_CAP_TARGET_TO_CASH", weight=weight)
                needed = set(units) | {t for t, w in target.items() if t != "CASH" and w > 0}
                liquid = {t for t in needed if tradable(row(day, t))}
                for t in needed - liquid - locked:
                    record(day, t, "NEW_ORDER_UNFILLED_CASH")
                for t in locked:
                    record(day, t, "HELD_ORDER_FROZEN", units=units[t], target_weight=target.get(t, 0.0))
                    if target.get(t, 0) == 0:
                        pending.add(t)
                    else:
                        pending.discard(t)
                current = {t: units[t] * float(row(day, t)["open"]) for t in units if t in liquid}
                # Use yesterday's mark for funding at today's open; today's close
                # is available only for end-of-day NAV.
                locked_value = sum(units[t] * last_marks[t] for t in locked) + float(claims.receivable_value)
                liquid_pre = cash + sum(current.values())
                target_values, new_cash, fee = funded_targets(
                    liquid_pre,
                    current,
                    {t: target.get(t, 0.0) for t in liquid},
                    locked_value,
                    cost_bps,
                    max(0.0, 1 - sum(target.get(t, 0.0) for t in locked)),
                )
                new_units = {t: units[t] for t in locked}
                for t in sorted(liquid):
                    amount = target_values.get(t, 0.0)
                    quantity = amount / float(row(day, t)["open"])
                    old = units.get(t, 0.0)
                    if abs(quantity - old) > 1e-14:
                        trades.append(
                            {
                                "date": day,
                                "ticker": t,
                                "reason": "SCHEDULED",
                                "old_units": old,
                                "new_units": quantity,
                                "price": float(row(day, t)["open"]),
                                "notional": abs(quantity - old) * float(row(day, t)["open"]),
                                "cost": abs(quantity - old) * float(row(day, t)["open"]) * cost_bps / 10000,
                            }
                        )
                    if quantity > 1e-15:
                        new_units[t] = quantity
                    pending.discard(t)
                assert abs(liquid_pre - new_cash - sum(target_values.values()) - fee) < 1e-9
                units, cash = new_units, new_cash
            else:
                # Only outstanding sell-all intent survives a halt. Failed buys
                # expire and are never bought automatically after resumption.
                for t in sorted(pending & set(units)):
                    q = row(day, t)
                    if tradable(q):
                        amount = units[t] * float(q["open"])
                        fee = amount * cost_bps / 10000
                        cash += amount - fee
                        trades.append(
                            {
                                "date": day,
                                "ticker": t,
                                "reason": "DEFERRED_EXIT",
                                "old_units": units[t],
                                "new_units": 0.0,
                                "price": float(q["open"]),
                                "notional": amount,
                                "cost": fee,
                            }
                        )
                        del units[t]
                        pending.remove(t)
            if leverage_trim is not None:
                if sum(t in units for t in leverage_trim.tickers) > 1:
                    raise ValueError("trim research supports one leveraged holding")
                for t, signal_date in list(trim_pending.items()):
                    if t not in units:
                        del trim_pending[t]
                        continue
                    q = row(day, t)
                    if not tradable(q):
                        record(day, t, "LEVERAGE_TRIM_DEFERRED", signal_date=signal_date)
                        continue
                    if event is not None:
                        record(day, t, "LEVERAGE_TRIM_HANDLED_BY_SCHEDULED", signal_date=signal_date)
                        del trim_pending[t]
                        continue
                    open_nav = cash + float(claims.receivable_value) + sum(
                        n * (float(row(day, k)["open"]) if tradable(row(day, k)) else last_marks[k])
                        for k, n in units.items()
                    )
                    old = units[t]
                    amount = reduction_notional(old * float(q["open"]), open_nav, leverage_trim.target, cost_bps)
                    fee = amount * cost_bps / 10000
                    quantity = old - amount / float(q["open"])
                    if amount > 1e-14:
                        units[t] = quantity
                        cash += amount - fee
                        trades.append({"date": day, "ticker": t, "reason": "LEVERAGE_CAP_TRIM",
                                       "signal_date": signal_date, "old_units": old, "new_units": quantity,
                                       "price": float(q["open"]), "notional": amount, "cost": fee})
                        record(day, t, "LEVERAGE_TRIM_FILLED", signal_date=signal_date,
                               post_open_weight=quantity * float(q["open"]) / (open_nav - fee))
                    else:
                        record(day, t, "LEVERAGE_TRIM_GAP_RECOVERED", signal_date=signal_date)
                    del trim_pending[t]
            restricted = 0.0
            if max_holdings is not None and len(units) > max_holdings:
                raise ValueError("actual_holdings_exceed_cap")
            for t, quantity in units.items():
                q = row(day, t)
                if not positive(q, "close"):
                    raise ValueError(f"held_mark_missing:{t}")
                last_marks[t] = float(q["close"])
                is_locked = official_lock(q)
                if is_locked:
                    restricted += quantity * last_marks[t]
                    record(day, t, "OFFICIAL_NONTRADING_MARK_PROVISIONAL", units=quantity, close=last_marks[t])
                holdings.append(
                    {"date": day, "ticker": t, "units": quantity, "mark": last_marks[t], "restricted": is_locked}
                )
            if cash_enabled:
                claims, credit = settle_cash(claims, day=day_date, phase="AFTER_CLOSE")
                cash += float(credit)
                if credit:
                    cash_rows.append({"date": day, "kind": "PAYMENT_AFTER_CLOSE", "cash_credit": float(credit)})
            receivable = float(claims.receivable_value)
            nav = cash + sum(n * last_marks[t] for t, n in units.items()) + receivable
            if cash < -1e-10 or not math.isfinite(nav) or nav <= 0:
                raise ValueError("invalid funded NAV")
            risk_fields = {}
            if leverage_trim is not None:
                leveraged = {t: units[t] * last_marks[t] for t in leverage_trim.tickers if t in units}
                leverage_weight = sum(leveraged.values()) / nav
                breach = leverage_weight > leverage_trim.trigger + 1e-10
                if breach:
                    for t in leveraged:
                        if t not in trim_pending:
                            trim_pending[t] = day
                            record(day, t, "LEVERAGE_TRIM_TRIGGERED", observed_weight=leverage_weight)
                risk_fields = {"leveraged_weight": leverage_weight, "leverage_over_trigger": breach,
                               "leverage_trim_pending": len(trim_pending)}
            navs.append(
                {
                    "date": day,
                    "nav": nav,
                    "cash": cash,
                    "restricted_value": restricted,
                    "restricted_weight": restricted / nav,
                    "stress_nav_zero_recovery": nav - restricted,
                    **risk_fields,
                    **({"receivable_value": receivable, "cumulative_cash_distributions": float(claims.settled_cash)} if cash_enabled else {}),
                }
            )
        except (ValueError, KeyError) as exc:
            failure = {"date": day, "reason": str(exc)}
            break
    return HaltReplay(
        pd.DataFrame(navs), pd.DataFrame(trades), pd.DataFrame(notes), pd.DataFrame(holdings), failure,
        pd.DataFrame(cash_rows), "RESEARCH_CASH_EVENTS_INTEGRATED_COVERAGE_UNVERIFIED" if cash_enabled else "PRICE_ONLY",
    )
