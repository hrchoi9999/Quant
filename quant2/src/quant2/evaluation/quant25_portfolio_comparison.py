"""Fixed monthly selection/retention policies for reconstructed research replay."""
from __future__ import annotations

import math

import pandas as pd

from src.evaluation.normalized_nav import Publication, schedule_publications
from src.quant2.evaluation.quant25_restriction_guard import guard_restricted_entries

POLICIES = ("replace20", "retain30")


def monthly_names(scored: pd.DataFrame, held: set[str], policy: str) -> list[str]:
    """Retention changes only the rank cutoff; eligibility is identical.

    The 30-rank buffer is fixed before return inspection, not optimized.
    At each monthly decision all surviving and new names target 5 percent.
    """
    if policy not in POLICIES:
        raise ValueError("unknown holding policy")
    if scored.ticker.isna().any() or scored.ticker.duplicated().any():
        raise ValueError("invalid candidate ticker keys")
    eligible = scored.loc[scored.eligible].copy()
    if not eligible.score.map(lambda x: math.isfinite(float(x))).all():
        raise ValueError("invalid eligible score")
    names = eligible.sort_values(["score", "ticker"], ascending=[False, True], kind="stable").ticker.tolist()
    if policy == "replace20":
        return names[:20]
    kept = [t for t in names[:30] if t in held]
    if len(kept) > 20:
        raise ValueError("previous holdings exceed 20-name contract")
    return kept + [t for t in names if t not in kept][:20 - len(kept)]


def validate_weights(weights: dict[str, float]) -> None:
    if any(not math.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError("invalid target weights")
    if not math.isclose(sum(weights.values()), 1., abs_tol=1e-9):
        raise ValueError("target weights must sum to one without normalization")
    stocks = {k: v for k, v in weights.items() if k != "CASH" and v > 0}
    if len(stocks) > 20 or any(not math.isclose(w, .05, abs_tol=1e-9) for w in stocks.values()):
        raise ValueError("invalid 20 slots of 5 percent")


def compile_targets(scores: pd.DataFrame, variant: str, policy: str,
                    calendar: list[str], restrictions: list[dict]) -> tuple[list, list, dict | None]:
    if calendar != sorted(set(calendar)):
        raise ValueError("calendar must be unique and ordered")
    subset = scores.loc[scores.variant.eq(variant) & scores.decision_date.lt(calendar[-1])]
    if subset.empty or subset.duplicated(["decision_date", "ticker"]).any():
        raise ValueError("missing or duplicate monthly scores")
    events, records, held = [], [], set()
    for day, frame in subset.groupby("decision_date", sort=True):
        names = monthly_names(frame, held, policy)
        target = {t: .05 for t in names}
        target["CASH"] = 1 - .05 * len(names)
        validate_weights(target)
        event = schedule_publications([
            Publication(f"{variant}_{policy}", pd.Timestamp(day), pd.Timestamp(day + "T16:00:00+09:00"),
                        "Q25_PORTFOLIO_V01", target, "RECONSTRUCTED_PRICE_ONLY")
        ], pd.DatetimeIndex(pd.to_datetime(calendar)))[0]
        execution = event.execution_date.strftime("%Y-%m-%d")
        guarded = guard_restricted_entries(target, held, decision_at=day + "T16:00:00+09:00",
                                           execution_at=execution + "T09:00:00+09:00", restrictions=restrictions)
        if guarded["weights"] is None:
            return events, records, {"date": execution, "reason": "known held restriction",
                                     "tickers": guarded["blocked_held_tickers"]}
        weights = guarded["weights"]
        validate_weights(weights)
        event = type(event)(event.model_code, event.decision_date, event.published_at,
                            event.execution_date, event.run_id, weights, event.evidence_state)
        events.append(event)
        current = {t for t, w in weights.items() if t != "CASH" and w > 0}
        records.append({"decision_date": day, "execution_date": execution, "variant": variant, "policy": policy,
                        "weights": weights, "retained_names": len(current & held), "new_names": len(current - held),
                        "exited_names": len(held - current), "excluded_entries": guarded["excluded_entries"]})
        held = current
    return events, records, None
