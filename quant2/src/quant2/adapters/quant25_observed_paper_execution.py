"""One scheduled, observed-open paper rebalance; never a broker execution.

Uses the frozen post-cost funding solver and fractional research units. Daily
OHLCV alone is not accepted as proof that an instrument was tradable at open.
"""
from __future__ import annotations

from decimal import Decimal

from src.quant2.evaluation.quant25_halt_policy import funded_targets

from .quant25_incremental_selection import aware
from .quant25_paper_live import PROFILE_MODEL_IDS


def positive(value):
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("finite positive open price required")
    return number


def _review_matches(materiality, quote, ticker):
    warnings = [w for w in materiality["warnings"] if w["ticker"] == ticker]
    return bool(quote and warnings
                and quote.get("materiality_review_sha256") == materiality["review"]["sha256"]
                and set(quote.get("unresolved_event_ids", [])) == {w["event_id"] for w in warnings}
                and quote.get("event_source_sha256") in {s for w in warnings for s in w["source_sha256"]})


def _current_locked_price(quote, opened, *, mode="observed"):
    """A current official price is a valuation input, never permission to trade."""
    try:
        digest = quote.get("status_source_sha256", "")
        if mode == "delayed":
            if (quote.get("source_kind") != "OFFICIAL_DAILY_OHLCV"
                    or quote.get("valuation_valid") is not True
                    or quote.get("rights_review", {}).get("status") not in {"CLEAR", "WARNING"}):
                return None
            return positive(quote.get("open"))
        if (aware(quote.get("price_asof")) != opened or aware(quote.get("status_known_at")) > opened
                or quote.get("tradability_basis") != "OFFICIAL_OPEN_STATUS"
                or type(quote.get("tradable_at_open")) is not bool
                or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
            return None
        return positive(quote.get("open"))
    except (ValueError, TypeError, AttributeError, ArithmeticError):
        return None


def paper_execution_events(selection, snapshots, quote_input, *, received_at, quote_sha256, fee_rate):
    day = selection["execution_date"]
    opened = aware(day + "T09:00:00+09:00")
    received = aware(received_at)
    if (selection["historical"] is not False or quote_input.get("asof_date") != day
            or received < opened or received.tz_convert("Asia/Seoul").date() != opened.date()):
        raise ValueError("same-session observed open required; no historical or future fill")
    if aware(selection["decision_cutoff"]) >= opened:
        raise ValueError("target must precede the execution open")
    return _paper_execution_events(selection, snapshots, quote_input, received_at=received_at,
                                   quote_sha256=quote_sha256, fee_rate=fee_rate, mode="observed")


def delayed_paper_execution_events(selection, snapshots, daily_input, *, confirmed_at,
                                   daily_sha256, plan_sha256, fee_rate,
                                   source_binding_verified=False):
    """Retrospective paper assumption from next-day official bars, never a live quote."""
    day = selection["execution_date"]
    if selection["historical"] is not False or daily_input.get("asof_date") != day:
        raise ValueError("exact future target/date required for delayed paper")
    if aware(confirmed_at).tz_convert("Asia/Seoul").date() <= aware(day + "T09:00:00+09:00").date():
        raise ValueError("delayed confirmation requires a later local date")
    if aware(selection["decision_cutoff"]) >= aware(day + "T09:00:00+09:00"):
        raise ValueError("target must precede the execution open")
    return _paper_execution_events(selection, snapshots, daily_input, received_at=confirmed_at,
                                   quote_sha256=daily_sha256, fee_rate=fee_rate, mode="delayed",
                                   plan_sha256=plan_sha256,
                                   source_binding_verified=source_binding_verified)


def _paper_execution_events(selection, snapshots, quote_input, *, received_at, quote_sha256,
                            fee_rate, mode, plan_sha256=None, source_binding_verified=False):
    day = selection["execution_date"]
    opened = aware(day + "T09:00:00+09:00")
    if set(snapshots) != set(PROFILE_MODEL_IDS):
        raise ValueError("exact three profile books required")
    materiality = selection.get("event_materiality")
    restricted = set(materiality["new_entry_restricted_tickers"]) if materiality else set()
    quotes = {}
    for row in quote_input["quotes"]:
        ticker = row["ticker"]
        if ticker in quotes:
            raise ValueError("duplicate execution quote")
        if ticker in restricted:
            # This instrument cannot trade. Missing/invalid prices affect its
            # valuation only; never prevent processing independent securities.
            quotes[ticker] = row
            continue
        if mode == "observed":
            known = aware(row["status_known_at"])
            if (known > opened or aware(row["price_asof"]) != opened
                    or row.get("tradability_basis") != "OFFICIAL_OPEN_STATUS"
                    or type(row.get("tradable_at_open")) is not bool
                    or type(row.get("event_coverage_confirmed")) is not bool
                    or type(row.get("unresolved_event")) is not bool):
                raise ValueError("official point-in-time tradability and event coverage required")
            hashes = ("status_source_sha256", "event_source_sha256")
        else:
            if row.get("source_kind") != "OFFICIAL_DAILY_OHLCV":
                raise ValueError("delayed paper requires official daily OHLCV provenance")
            rights = row.get("rights_review")
            if (not isinstance(rights, dict) or rights.get("status") not in
                    {"CLEAR", "WARNING", "RESTRICTED", "UNKNOWN"} or
                    any(k in rights for k in ("cash_amount", "cash_received", "cash_credit"))):
                raise ValueError("dated rights review required; unreceived cash cannot be credited")
            rights_hash = rights.get("source_sha256", "")
            if len(rights_hash) != 64 or any(c not in "0123456789abcdef" for c in rights_hash):
                raise ValueError("rights review source hash required")
            for field in ("open", "high", "low", "close"):
                positive(row.get(field))
            volume = Decimal(str(row.get("volume")))
            if (not volume.is_finite() or volume < 0 or volume != volume.to_integral_value()
                    or positive(row["high"]) < max(positive(row["open"]), positive(row["close"]))
                    or positive(row["low"]) > min(positive(row["open"]), positive(row["close"]))
                    ):
                raise ValueError("inconsistent official daily bar")
            for field in ("trade_permitted_for_paper", "units_valid", "valuation_valid",
                          "event_coverage_confirmed", "unresolved_event"):
                if row.get(field) is not None and type(row[field]) is not bool:
                    raise ValueError("delayed security review must be boolean or unknown")
            hashes = ("daily_source_sha256", "review_source_sha256")
            row = {**row,
                   "tradable_at_open": (row.get("trade_permitted_for_paper") is True
                                        and row.get("units_valid") is True and volume > 0),
                   "event_coverage_confirmed": (row.get("event_coverage_confirmed") is True
                                                and row.get("units_valid") is True
                                                and row.get("valuation_valid") is True
                                                and rights["status"] in {"CLEAR", "WARNING"}),
                   "unresolved_event": (row.get("unresolved_event") is not False
                                        or rights["status"] in {"RESTRICTED", "UNKNOWN"})}
        for field in hashes:
            digest = row.get(field, "")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("official execution source hash required")
        if row["tradable_at_open"]:
            positive(row["open"])
        quotes[ticker] = row
    fee = Decimal(str(fee_rate))
    events = []
    audit = []
    for profile in sorted(selection["profiles"]):
        targets = selection["profiles"][profile]
        snapshot = snapshots[profile]
        held = {r["ticker"]: r for r in snapshot["positions"]}
        desired = {r["ticker"]: r for r in targets["target_positions"]}
        needed = set(held) | set(desired)
        locked, liquid, failed = set(), set(), set()
        for ticker in needed:
            if ticker in restricted:
                (locked if ticker in held else failed).add(ticker)
                continue
            quote = quotes.get(ticker)
            covered = quote and quote["event_coverage_confirmed"] and not quote["unresolved_event"]
            if materiality and quote:
                warnings = [w for w in materiality["warnings"] if w["ticker"] == ticker]
                if warnings:
                    covered = False
                if (warnings and all(w["action"] in {"WARN_LIMITED", "WARN_DISTRIBUTION"} for w in warnings)
                        and _review_matches(materiality, quote, ticker)):
                    covered = True
            if ticker in held and not covered:
                if materiality:
                    locked.add(ticker)
                    continue
                raise ValueError("held corporate-action or open-status coverage unresolved")
            if ticker not in held and ticker in desired and desired[ticker]["fresh_entry_eligible"] is not True:
                failed.add(ticker)
            elif not covered:
                failed.add(ticker)
            elif not quote["tradable_at_open"]:
                if ticker in held:
                    locked.add(ticker)
                else:
                    failed.add(ticker)
            else:
                liquid.add(ticker)
        if len(locked) > (20 if profile == "activity_retention" else 30):
            raise ValueError("locked holdings exceed frozen cap")
        cap = 20 if profile == "activity_retention" else 30
        ordered = [t for t in desired if t in held and t not in locked]
        ordered += [t for t in desired if t not in held and t not in locked]
        for ticker in ordered[cap - len(locked):]:
            if ticker not in held:
                liquid.discard(ticker)
                failed.add(ticker)
            else:
                raise ValueError("held position cap reconciliation requires explicit exit")
        locked_value = Decimal("0")
        unknown_value = set()
        for ticker in locked:
            position = held[ticker]
            if materiality:
                quote = quotes.get(ticker)
                price = _current_locked_price(quote, opened, mode=mode)
                proof = (_review_matches(materiality, quote, ticker) if ticker in restricted else
                         quote and quote["event_coverage_confirmed"] and not quote["unresolved_event"])
                if ticker in materiality["valuation_restricted_tickers"] or price is None or not proof:
                    unknown_value.add(ticker)
                else:
                    locked_value += Decimal(position["units"]) * price
                continue
            if position["mark_price"] is None or aware(position["mark_price_asof"]) >= opened:
                raise ValueError("locked holding requires previous observed mark")
            locked_value += Decimal(position["units"]) * positive(position["mark_price"])
        current = {t: Decimal(held[t]["units"]) * positive(quotes[t]["open"]) for t in liquid & set(held)}
        cash = Decimal(snapshot["cash"])
        weights = {t: float(desired[t]["target_weight"]) if t in desired else 0.0 for t in liquid}
        # Normalize currency scale for the frozen numerical funding solver.
        scale = Decimal(snapshot["starting_capital"])
        liquid_share = max(0.0, 1 - sum(desired[t]["target_weight"] for t in locked if t in desired))
        deferred_budget = set()
        if unknown_value and liquid_share != 1.0:
            # The target amount depends on unvalued assets. Preserve quantities
            # for those adjustments, while honoring independent explicit exits.
            deferred_budget = set(desired) & liquid
            amounts = {t: current.get(t, Decimal("0")) / scale if t in desired else 0 for t in liquid}
            funding_basis = "DEPENDENT_TARGET_AMOUNTS_DEFERRED"
        else:
            # When liquid_share=1, w*(post+locked)*post/(post+locked)=w*post.
            # The frozen solver's cash cap makes amounts independent of ANY
            # nonnegative unknown locked value. Zero here is the reduced equation,
            # not an assigned price, quantity, cash receipt, or total NAV.
            amounts, _, _ = funded_targets(
                float((cash + sum(current.values())) / scale),
                {t: float(v / scale) for t, v in current.items()}, weights,
                0.0 if unknown_value else float(locked_value / scale), float(fee * 10000), liquid_share)
            funding_basis = "CONFIRMED_LIQUID_CAP_INVARIANT" if unknown_value else "CURRENT_CONFIRMED_VALUES"
        fills = []
        for ticker in sorted(liquid):
            if ticker in deferred_budget:
                continue
            price = positive(quotes[ticker]["open"])
            new = Decimal(str(amounts.get(ticker, 0))) * scale / price
            delta = new - Decimal(held[ticker]["units"] if ticker in held else "0")
            if abs(delta) < Decimal("1e-14"):
                continue
            fills.append({"ticker": ticker, "asset_type": (desired.get(ticker) or held[ticker])["asset_type"],
                          "side": "BUY" if delta > 0 else "SELL", "units": abs(delta), "price": price})
        fills.sort(key=lambda r: (r["side"] != "SELL", r["ticker"]))
        rounding = Decimal("0")
        for fill in fills:
            notional = fill["units"] * fill["price"]
            if fill["side"] == "BUY" and notional * (1 + fee) > cash:
                excess = notional * (1 + fee) - cash
                if excess > Decimal("0.01"):
                    raise ValueError("paper funding exceeds cash")
                rounding += excess
                fill["units"] = cash / ((1 + fee) * fill["price"])
                notional = fill["units"] * fill["price"]
            cost = notional * fee
            cash += notional - cost if fill["side"] == "SELL" else -notional - cost
            evidence = {"kind": ("observed_open_paper_fill" if mode == "observed"
                                 else "delayed_daily_open_paper_fill"), "not_broker_execution": True,
                        "reference": f"private-{mode}-paper:{day}",
                        "target_sha256": selection["state_sha256"],
                        "units_basis": "FROZEN_FRACTIONAL_RESEARCH_UNITS"}
            if mode == "observed":
                evidence["quote_sha256"] = quote_sha256
            else:
                evidence.update(daily_sha256=quote_sha256, plan_sha256=plan_sha256,
                                price_basis="RETROSPECTIVE_OFFICIAL_DAILY_OPEN_ASSUMPTION",
                                confirmed_at=received_at,
                                source_binding_verified=source_binding_verified)
            payload = {**{k: str(v) if isinstance(v, Decimal) else v for k, v in fill.items()},
                       "fee": str(cost), "currency": "KRW", "execution_evidence": evidence}
            events.append(_event(day, profile, "paper_fill", fill["ticker"], payload, received_at,
                                 quote_sha256, mode=mode))
        for ticker in sorted(failed | locked):
            if materiality and ticker in locked:
                # A restriction is neither a sell-all intent nor an order for
                # an estimated quantity. Preserve the original position only.
                continue
            if ticker in locked and ticker in desired and desired[ticker]["target_weight"] > 0:
                # A locked position is not a sell-all order. Retained/increased
                # targets remain an observation until executable quantity is known.
                continue
            position = desired.get(ticker) or held[ticker]
            reference = positive(position.get("reference_price") or position.get("mark_price"))
            units = Decimal(held[ticker]["units"]) if ticker in locked else scale * Decimal(str(position["target_weight"])) / reference
            if units <= 0:
                continue
            events.append(_event(day, profile, "nonfill", ticker, {
                "ticker": ticker, "asset_type": position["asset_type"], "side": "SELL" if ticker in locked else "BUY",
                "requested_units": str(units), "reason": "OFFICIAL_LOCK" if ticker in locked else "OPEN_OR_EVENT_EVIDENCE_MISSING",
                "status": "OPEN" if mode == "delayed" or ticker in locked and ticker not in desired else "FINAL",
                **({"delayed_plan_sha256": plan_sha256} if mode == "delayed" else {})},
                received_at, quote_sha256, mode=mode))
        audit.append({"profile_id": profile, "funding_rounding_krw": str(rounding),
                      "paper_fills": len(fills), "unfilled_or_locked": sorted(failed | locked),
                      "locked_holdings_observed": [{"ticker": t, "units": held[t]["units"],
                                                    "target_weight": desired[t]["target_weight"] if t in desired else 0,
                                                    "sell_all_intent": not materiality and t not in desired}
                                                   for t in sorted(locked)],
                      "cash_after": str(cash), "units_basis": "FROZEN_FRACTIONAL_RESEARCH_UNITS"})
        if materiality:
            deferred = locked | failed | deferred_budget
            deferred |= {t for t in desired if t in liquid and Decimal(str(amounts.get(t, 0))) <= 0}
            audit[-1].update(
                status="PARTIAL_SECURITY_RESTRICTIONS" if deferred else "APPLIED",
                funding_basis=funding_basis, unconfirmed_valuation_tickers=sorted(unknown_value),
                total_nav_confirmed=not unknown_value,
                positions_preserved=[held[t] for t in sorted(locked)],
                total_return_status=materiality["total_return_status"],
                target_application={"applied_target_tickers": sorted(set(desired) - deferred),
                                    "deferred_tickers": sorted(deferred)})
    result = {"events": events, "audit": audit,
              "classification": ("OBSERVED_OPEN_PAPER_NOT_BROKER" if mode == "observed"
                                 else "DELAYED_DAILY_OPEN_PAPER_NOT_BROKER")}
    if materiality:
        result["event_materiality"] = materiality
    return result


def _event(day, profile, kind, ticker, payload, received, digest, *, mode="observed"):
    prefix = "paper-open" if mode == "observed" else "delayed-paper"
    occurred = day + "T09:00:00+09:00" if kind == "paper_fill" or mode == "observed" else received
    return {"event_id": f"{prefix}:{day}:{profile}:{kind}:{ticker}", "profile_id": profile,
            "event_type": kind, "occurred_at": occurred, "observed_at": received,
            "source_sha256": digest, "arrival_provenance": {"source_ref": f"{prefix}:{day}", "received_at": received},
            "payload": payload}
