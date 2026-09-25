"""Inactive, one-decision Q25 selector. Targets never imply actual holdings.

Uses the frozen score, baseline, risk-budget and sector functions. The small
retention state transition is checked against the frozen batch implementation.
Monthly core ETF intents remain a separately verified input, not recomputed here.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pandas as pd

from src.quant2.evaluation.quant25_halt_policy import stock_targets
from src.quant2.evaluation.quant25_integrated_allocation import integrated_targets
from src.quant2.evaluation.quant25_risk_allocation import QM_MODES
from src.quant2.evaluation.quant25_sector_leverage import add_sector_leverage, choose_sector
from src.quant2.evaluation.quant25_soft_selection import soft_scores

from .quant25_paper_live import FREEZE_ID, PROFILE_MODEL_IDS, canonical_sha256
from .quant25_rules_consumer import announced_overlap

SCHEMA = "q25_incremental_selection_v1"
SOURCES = {"features", "fundamentals", "prices", "qm", "etf_intent", "rules", "calendar", "universe", "sector"}
CANDIDATE_CONTRACT = "Q25_BOOTSTRAP_DELAYED_OPEN_CANDIDATE_V1_NOT_APPROVED"


def aware(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return stamp


def check_evidence(evidence, cutoff, *, historical):
    """Check capture metadata; the file entry point also verifies source bytes."""
    if set(evidence) != SOURCES:
        raise ValueError("complete named input provenance required")
    for name, item in evidence.items():
        digest = item.get("sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"invalid source hash: {name}")
        for field in ("available_at", "arrived_at"):
            value = item.get(field)
            if value is None:
                if not historical:
                    raise ValueError(f"unknown {field}: {name}")
            elif aware(value) > cutoff:
                raise ValueError(f"input arrived or became available after cutoff: {name}")
        if item.get("arrived_at") and item.get("available_at"):
            if aware(item["arrived_at"]) < aware(item["available_at"]):
                raise ValueError(f"arrival precedes availability: {name}")


def score_inputs(features, fundamentals, day):
    """Recompute both price-led scores; never accept caller-provided final ranks."""
    if set(features.ticker) != set(fundamentals.ticker):
        raise ValueError("fundamental cohort must explicitly include missing-data rows")
    result = {}
    for variant in ("price_only", "price_growth"):
        frame = soft_scores(features, fundamentals, day, variant)
        frame["decision_date"] = day
        result[variant] = frame
    return result


def select_manual_candidate(*, timing, execution_date, decision_at, **inputs):
    """Explicit candidate facade; the default selector retains same-day guards."""
    from .quant25_manual_collection_candidate import CONTRACT, validate_monthly, validate_open

    day = inputs["day"]
    if timing.get("signal_date") != day or set(inputs["features"].date.astype(str)) != {day}:
        raise ValueError("exact manual signal-day features required")
    validity = validate_open(timing, inputs["calendar"], inputs["evidence"], cutoff=decision_at,
                             execution_date=execution_date, next_rebalance=inputs["next_rebalance"])
    etf = inputs["etf_intent"]
    validate_monthly({"decision_date": etf.decision_date.strftime("%Y-%m-%d"),
                      "execution_date": etf.execution_date.strftime("%Y-%m-%d"),
                      "published_at": etf.published_at.isoformat(), "weights": etf.weights,
                      "evidence_state": etf.evidence_state}, inputs["calendar"],
                     signal_day=day, availability_cutoff=decision_at)
    result = select_decision(**inputs, historical=False, decision_at=decision_at,
                             candidate_timing={"contract_id": CANDIDATE_CONTRACT,
                                               "classification": "SYNTHETIC_TEST_ONLY",
                                               "execution_date": execution_date})
    result.pop("state_sha256")
    result.update(manual_timing_contract=CONTRACT, signal_date=day, expires_at=validity["expires_at"],
                  availability_cutoff=decision_at, collection_evidence_sha256=canonical_sha256(timing))
    result["state_sha256"] = canonical_sha256(result)
    return result


def _retain(event, daily, prices, previous, stocks, rules, day, execution, horizon, cutoff):
    """Prior intended names have an activity waiver; unheld entries do not."""
    active = announced_overlap(rules, cutoff.isoformat(), execution + "T09:00:00+09:00",
                               horizon + "T09:00:00+09:00")
    quotes = prices.loc[prices.date.eq(day)].set_index("ticker")
    trend = daily.price_valid & daily.ma60.gt(daily.ma120) & daily.ma60_slope.gt(0) & daily.mom20_pct.ge(.7)
    ranked = daily.loc[trend].sort_values(["score", "ticker"], ascending=[False, True])
    safe = []
    for row in ranked.itertuples():
        if row.ticker not in stocks or row.ticker in active or row.ticker not in quotes.index:
            continue
        quote = quotes.loc[row.ticker, ["open", "close", "volume"]].to_numpy(float)
        if np.isfinite(quote).all() and (quote > 0).all() and math.isfinite(row.score):
            safe.append(row.ticker)
    names = [t for t, w in event.weights.items() if t in stocks and w > 0]
    if not set(names) <= set(safe):
        raise ValueError("baseline eligibility mismatch")
    kept = [t for t in safe if t in previous][:len(names)]
    chosen = kept + [t for t in names if t not in kept][:len(names) - len(kept)]
    slot = event.weights[names[0]] if names else 0.
    weights = {t: w for t, w in event.weights.items() if t not in stocks}
    weights.update({t: slot for t in chosen})
    return replace(event, weights=weights), kept


def select_decision(*, features, fundamentals, prices, stocks, calendar, day, next_rebalance,
                    qm, etf_intent, sector_candidates, rules, evidence, previous=None,
                    historical=True, decision_at=None, candidate_timing=None, manual_timing=None):
    """Compute three target books for one scheduled decision, without execution.

    `next_rebalance` is the next scheduled execution session, not a forecast.
    For frozen-history parity the final horizon may be the last replay session.
    Historical mode preserves unknown arrival times and cannot become Live.
    History keeps the 16:00 replay reference. Captured inputs may use their
    actual same-decision-day publication timestamp, after close and before open.
    """
    if type(historical) is not bool:
        raise ValueError("historical must be a boolean")
    timing_context = None
    materiality = None
    if manual_timing is not None:
        from .quant25_input_timing import opted_in, validity, verify_coverage
        if not opted_in(manual_timing):
            manual_timing = None
        elif historical or candidate_timing is not None or decision_at is None:
            raise ValueError("manual opt-in requires captured inputs and actual decision time")
    if calendar != sorted(set(calendar)) or day not in calendar or next_rebalance not in calendar:
        raise ValueError("ordered calendar and declared schedule required")
    index = calendar.index(day)
    if index == 0 or index + 1 >= len(calendar):
        raise ValueError("previous and next trading sessions required")
    execution, observation = calendar[index + 1], calendar[index - 1]
    reference_execution = execution
    if manual_timing is not None:
        timing_context = validity(manual_timing, calendar, signal_day=day, cutoff=decision_at,
                                  next_rebalance=next_rebalance)
        execution = timing_context["execution_date"]
    if candidate_timing is not None:
        if (historical or candidate_timing.get("contract_id") != CANDIDATE_CONTRACT
                or candidate_timing.get("classification") != "SYNTHETIC_TEST_ONLY"
                or decision_at is None):
            raise ValueError("explicit synthetic timing candidate required")
        execution = candidate_timing.get("execution_date")
        if execution not in calendar or execution < reference_execution or execution >= next_rebalance:
            raise ValueError("candidate execution outside declared validity horizon")
    if next_rebalance < execution:
        raise ValueError("invalid next rebalance horizon")
    cutoff = aware(day + "T16:00:00+09:00")
    if decision_at is not None:
        if historical:
            raise ValueError("historical replay cannot override its reference timestamp")
        cutoff = aware(decision_at).tz_convert("Asia/Seoul")
        if ((candidate_timing is None and manual_timing is None and cutoff.strftime("%Y-%m-%d") != day)
                or cutoff < aware(day + "T15:30:00+09:00")
                or cutoff >= aware(execution + "T09:00:00+09:00")):
            raise ValueError("actual decision must follow same-day close, without backdating")
    check_evidence(evidence, cutoff, historical=historical)
    if manual_timing is not None:
        from .quant25_input_timing import consumer_opted_in, verify_consumer_receipts
        if consumer_opted_in(manual_timing):
            verify_consumer_receipts(manual_timing, evidence, cutoff=cutoff,
                inputs={"features": features, "fundamentals": fundamentals, "prices": prices,
                        "universe": stocks, "qm": qm, "calendar": calendar, "sector": sector_candidates,
                        "rules": rules, "etf_intent": etf_intent})
        coverage_scope = set(stocks) | (set(etf_intent.weights) - {"CASH"}) | {c["ticker"] for c in sector_candidates}
        reviewed = verify_coverage(manual_timing, evidence=evidence, stocks=coverage_scope, calendar=calendar,
                                   cutoff=cutoff, execution=execution, horizon=next_rebalance)
        materiality = reviewed.get("consumer_assessment")
    if qm.get("asof_date") != observation or qm.get("market_state_label") not in QM_MODES:
        raise ValueError("exact previous-session QM label required")
    mode = QM_MODES[qm["market_state_label"]]
    if not historical:
        anchor = pd.Timestamp(day) + pd.Timedelta(days=(2 - pd.Timestamp(day).weekday()) % 7)
        if anchor.strftime("%Y-%m-%d") > calendar[-1]:
            raise ValueError("calendar must cover the Wednesday anchor")
        scheduled = max(d for d in calendar if d <= anchor.strftime("%Y-%m-%d"))
        if day != scheduled:
            raise ValueError("not a weekly Wednesday or preceding holiday session")
    if (not stocks or len(stocks) != len(set(stocks)) or set(features.ticker) != set(stocks)
            or "CASH" in stocks):
        raise ValueError("explicit stock-only cohort required")
    if prices.duplicated(["date", "ticker"]).any() or prices.date.gt(day).any():
        raise ValueError("duplicate or future prices")
    if pd.to_datetime(features.date, errors="coerce").gt(pd.Timestamp(day)).any():
        raise ValueError("future features are forbidden")
    if (etf_intent.decision_date.strftime("%Y-%m-%d") > day or etf_intent.published_at > cutoff
            or etf_intent.published_at.tzinfo is None):
        raise ValueError("ETF intent is not already published")
    # Explicitly demand the most recent completed month; no indefinite stale reuse.
    current_month = pd.Timestamp(day).to_period("M")
    current_days = [d for d in calendar if pd.Timestamp(d).to_period("M") == current_month]
    month_finished = (day == max(current_days) and
                      calendar[-1] >= current_month.end_time.strftime("%Y-%m-%d"))
    completed = current_month if month_finished else current_month - 1
    month_days = [d for d in calendar if pd.Timestamp(d).to_period("M") == completed]
    if not month_days or etf_intent.decision_date.strftime("%Y-%m-%d") != max(month_days):
        raise ValueError(f"latest completed monthly ETF intent required: {day}")
    if set(etf_intent.weights) & set(stocks):
        raise ValueError("ETF and stock universes overlap")
    if (len({c["ticker"] for c in sector_candidates}) != len(sector_candidates)
            or {c["ticker"] for c in sector_candidates} & (set(stocks) | set(etf_intent.weights))):
        raise ValueError("sector universe overlap or duplicates")
    prior = {p: set() for p in PROFILE_MODEL_IDS}
    if previous is not None:
        body = {k: v for k, v in previous.items() if k != "state_sha256"}
        if (canonical_sha256(body) != previous.get("state_sha256") or previous.get("schema") != SCHEMA
                or previous.get("freeze_id") != FREEZE_ID or previous["decision_date"] >= day
                or (previous.get("next_rebalance") != execution if candidate_timing is None and manual_timing is None else
                    (previous.get("input_timing_contract") != timing_context["contract_id"] if manual_timing is not None else
                     previous.get("candidate_contract") != CANDIDATE_CONTRACT)
                    or previous.get("next_rebalance", "9999") > reference_execution)
                or set(previous.get("profiles", {})) != set(PROFILE_MODEL_IDS)
                or previous.get("historical") is not historical):
            raise ValueError("invalid, nonchronological or mixed-mode selection state")
        prior = {p: {r["ticker"] for r in previous["profiles"][p]["target_positions"]
                     if r["asset_type"] == "STOCK" and r["target_weight"] > 0} for p in PROFILE_MODEL_IDS}
        reconciliation = previous.get("retention_reconciliation")
        if reconciliation is not None:
            original = {k: v for k, v in body.items() if k != "retention_reconciliation"}
            if (not materiality or reconciliation.get("schema") != "Q25_VERIFIED_PROFILE_RETENTION_V1"
                    or canonical_sha256(original) != reconciliation.get("source_state_sha256")
                    or set(reconciliation.get("profiles", {})) != set(PROFILE_MODEL_IDS)):
                raise ValueError("invalid profile retention provenance")
            prior = {p: {t for t, ref in rows.items() if ref["target"]["asset_type"] == "STOCK"
                         and ref["target"]["ticker"] == t and ref["target"]["target_weight"] > 0}
                     for p, rows in reconciliation["profiles"].items()}
    scored = score_inputs(features, fundamentals, day)
    bounded_calendar = [d for d in calendar if d <= next_rebalance]
    bases = {}
    active = announced_overlap(rules, cutoff.isoformat(), execution + "T09:00:00+09:00",
                               next_rebalance + "T09:00:00+09:00")
    for variant, count in (("price_only", 20), ("price_growth", 25)):
        base = stock_targets(scored[variant], prices, [day], bounded_calendar,
                             variant, count, rules if historical else [])[0][0]
        if not historical:
            # Reuse frozen ranking/quote filters; apply the same event exclusion
            # at actual publication, without changing frozen replay source code.
            weights = {t: w for t, w in base.weights.items() if t == "CASH" or t not in active}
            weights["CASH"] = 1 - sum(w for t, w in weights.items() if t != "CASH")
            base = replace(base, weights=weights, published_at=cutoff)
        bases[variant] = base
    pg = integrated_targets([bases["price_growth"]], [etf_intent], calendar, {observation: mode},
                            defensive=True, cap=30)[0][0]
    selected, sector_audit = choose_sector(prices, calendar, observation, sector_candidates)
    pg, sector_budget = add_sector_leverage(pg, mode, selected, set(stocks))
    cash75 = {t: w * .75 if t in stocks else w for t, w in pg.weights.items()}
    cash75["CASH"] = 1 - sum(w for t, w in cash75.items() if t != "CASH")
    baselines = {"activity_retention": bases["price_only"], "defensive_pg_retention": pg,
                 "defensive_cash75_retention": replace(pg, weights=cash75)}
    output = {}
    quotes = prices.loc[prices.date.eq(day)].set_index("ticker")
    for profile, base in baselines.items():
        variant = "price_only" if profile == "activity_retention" else "price_growth"
        frame = scored[variant]
        event, kept = _retain(base, frame, prices, prior[profile], set(stocks), rules, day, execution,
                             next_rebalance, cutoff)
        if materiality:
            restricted = set(materiality["new_entry_restricted_tickers"])
            weights = {t: w for t, w in event.weights.items() if t == "CASH" or t not in restricted}
            weights["CASH"] = 1 - sum(w for t, w in weights.items() if t != "CASH")
            event = replace(event, weights=weights)
            kept = [t for t in kept if t not in restricted]
        if abs(sum(event.weights.values()) - 1) > 1e-9 or len(event.weights) - 1 > 30:
            raise ValueError("unfunded or oversized target")
        eligible = set(frame.loc[frame.eligible, "ticker"])
        positions = []
        for ticker, weight in event.weights.items():
            if ticker == "CASH" or weight <= 0:
                continue
            if ticker not in quotes.index:
                raise ValueError("missing target reference price")
            price = float(quotes.loc[ticker, "close"])
            if not math.isfinite(price) or price <= 0:
                raise ValueError("unusable target reference price")
            positions.append({"ticker": ticker, "asset_type": "STOCK" if ticker in stocks else "ETF",
                              "target_weight": float(weight), "reference_price": price,
                              "fresh_entry_eligible": ticker in eligible if ticker in stocks else True,
                              "target_reason": "CONTINUING_TARGET" if ticker in kept else "BASELINE_TARGET"})
        output[profile] = {"model_id": PROFILE_MODEL_IDS[profile], "target_positions": positions,
                           "cash_target": float(event.weights["CASH"]), "retained_count": len(kept)}
    result = {"schema": SCHEMA, "freeze_id": FREEZE_ID, "historical": historical,
              "classification": "HISTORICAL_RECONSTRUCTION" if historical else "CAPTURED_INPUT_PREPARATION",
              "operationally_actionable": False, "live_started": False,
              "decision_date": day, "decision_cutoff": cutoff.isoformat(), "execution_date": execution,
              "next_rebalance": next_rebalance, "market_observation_date": observation, "regime": mode,
              "parent_state_sha256": previous["state_sha256"] if previous else None,
              "input_evidence": evidence, "profiles": output, "sector_budget": sector_budget,
              "sector_diagnostics": sector_audit,
              "limitations": ["Target state is not actual holdings or fills", "Monthly ETF intent is an external input",
                              "No scheduler, broker or operating DB connection", "No new performance claim"]}
    if materiality:
        result["event_materiality"] = materiality
    result["state_sha256"] = canonical_sha256(result)
    if candidate_timing is not None:
        result.pop("state_sha256")
        result.update(classification="SYNTHETIC_TEST_ONLY", candidate_contract=CANDIDATE_CONTRACT,
                      reference_execution_date=reference_execution, approval_status="NOT_APPROVED",
                      active=False, public_eligible=False, scheduler_registered=False,
                      actual_publication=False, actual_receipt=False, counts_as_live_sample=False)
        result["state_sha256"] = canonical_sha256(result)
    if timing_context is not None:
        result.pop("state_sha256")
        result.update(input_timing_contract=timing_context["contract_id"], input_timing_context=timing_context,
                      reference_execution_date=reference_execution, availability_cutoff=cutoff.isoformat())
        if timing_context["evidence_mode"] == "SYNTHETIC_TEST_ONLY":
            result.update(classification="SYNTHETIC_TEST_ONLY", actual_publication=False, actual_receipt=False)
        result["state_sha256"] = canonical_sha256(result)
    return result
