"""Frozen Q25 stock selection with explicitly lagged market risk budgets."""

from __future__ import annotations

import math
from dataclasses import replace

import pandas as pd

EXPOSURES = {"risk_on": 0.70, "neutral": 0.40, "risk_off": 0.10}
QM_MODES = {
    "strong_up": "risk_on",
    "up": "risk_on",
    "neutral": "neutral",
    "down": "risk_off",
    "strong_down": "risk_off",
}


def price_trend_modes(frame):
    data = frame.sort_values("date").copy()
    if data.date.duplicated().any() or not ((data.close > 0) & data.close.map(math.isfinite)).all():
        raise ValueError("unique dates and finite positive prices required")
    data["ma20"] = data.close.rolling(20, min_periods=20).mean()
    data["ma60"] = data.close.rolling(60, min_periods=60).mean()
    data["mode"] = None
    valid = data.ma60.notna()
    data.loc[valid, "mode"] = "neutral"
    data.loc[valid & data.close.gt(data.ma60) & data.ma20.gt(data.ma60), "mode"] = "risk_on"
    data.loc[valid & data.close.lt(data.ma60) & data.ma20.lt(data.ma60), "mode"] = "risk_off"
    return data


def risk_targets(events, calendar, modes=None, *, fixed_exposure=None):
    """Use the exact prior session, preserving decisions, execution, and names."""
    if list(calendar) != sorted(set(calendar)):
        raise ValueError("ordered unique calendar required")
    if (modes is None) == (fixed_exposure is None):
        raise ValueError("provide either modes or a fixed exposure")
    if fixed_exposure is not None and (not math.isfinite(fixed_exposure) or not 0 <= fixed_exposure <= 1):
        raise ValueError("invalid fixed exposure")
    targets, records = [], []
    for event in events:
        day = event.decision_date.strftime("%Y-%m-%d")
        idx = calendar.index(day)
        if idx == 0 or event.execution_date.strftime("%Y-%m-%d") != calendar[idx + 1]:
            raise ValueError("prior observation and next-session execution required")
        source_date = calendar[idx - 1]
        mode = modes.get(source_date) if modes is not None else "fixed"
        if modes is not None and mode not in EXPOSURES:
            raise ValueError(f"missing or invalid market mode:{source_date}")
        exposure = EXPOSURES[mode] if modes is not None else fixed_exposure
        weights = {t: float(w) for t, w in event.weights.items()}
        if any(not math.isfinite(w) or w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1) > 1e-9:
            raise ValueError("invalid base target weights")
        scaled = {t: w * exposure for t, w in weights.items() if t != "CASH"}
        scaled["CASH"] = max(0.0, 1 - sum(scaled.values()))
        targets.append(replace(event, weights=scaled))
        records.append(
            {
                "decision_date": day,
                "execution_date": event.execution_date.strftime("%Y-%m-%d"),
                "market_observation_date": source_date,
                "mode": mode,
                "budget": exposure,
                "stock_target": 1 - scaled["CASH"],
                "cash_target": scaled["CASH"],
            }
        )
    return targets, pd.DataFrame(records)


def grouped_period_metrics(nav, groups):
    """Calendar-period returns use prior close; disjoint labels omit MDD."""
    data = nav[["date", "nav"]].copy()
    data["return"] = data.nav.div(data.nav.shift(1, fill_value=1.0)) - 1
    data["group"] = data.date.map(groups)
    if data.group.isna().any():
        raise ValueError("complete performance groups required")
    result = []
    for name, block in data.groupby("group", sort=True):
        result.append(
            {
                "group": name,
                "days": len(block),
                "conditional_compound_return": float((1 + block["return"]).prod() - 1),
                "mean_daily_return": float(block["return"].mean()),
                "worst_daily_return": float(block["return"].min()),
            }
        )
    return pd.DataFrame(result)
