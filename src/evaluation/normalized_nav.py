"""Publication-aware price-return NAV engine for normalized diagnostics.

This module is deliberately separate from operating backtest and publishing
code.  It does not infer unavailable fills and fails closed on trade-day price
gaps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

SEOUL = "Asia/Seoul"


@dataclass(frozen=True)
class Publication:
    model_code: str
    decision_date: pd.Timestamp
    published_at: pd.Timestamp
    run_id: str
    weights: Mapping[str, float]
    evidence_state: str = "observed_published_live"


@dataclass(frozen=True)
class ExecutionTarget:
    model_code: str
    decision_date: pd.Timestamp
    published_at: pd.Timestamp
    execution_date: pd.Timestamp
    run_id: str
    weights: Mapping[str, float]
    evidence_state: str


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, raw_value in weights.items():
        value = float(raw_value)
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"invalid weight: {key}={raw_value}")
        if value > 0:
            normalized[str(key)] = normalized.get(str(key), 0.0) + value
    total = float(sum(normalized.values()))
    if total > 1.000001:
        raise ValueError(f"weights exceed 1.0: {total}")
    normalized["CASH"] = normalized.get("CASH", 0.0) + max(0.0, 1.0 - total)
    return normalized


def _published_local(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.tz_convert(SEOUL)


def next_open_after_publication(
    published_at: pd.Timestamp,
    trading_calendar: pd.DatetimeIndex,
) -> pd.Timestamp:
    """Return the first market open strictly after the publication instant."""
    if trading_calendar.empty:
        raise ValueError("empty trading calendar")
    calendar = pd.DatetimeIndex(pd.to_datetime(trading_calendar)).normalize().unique().sort_values()
    local = _published_local(published_at)
    local_day = local.tz_localize(None).normalize()
    open_time = local.normalize() + pd.Timedelta(hours=9)
    if local < open_time and local_day in calendar:
        return pd.Timestamp(local_day)
    later = calendar[calendar > local_day]
    if later.empty:
        raise ValueError(f"no trading session after publication: {published_at}")
    return pd.Timestamp(later[0])


def schedule_publications(
    publications: Sequence[Publication],
    trading_calendar: pd.DatetimeIndex,
) -> list[ExecutionTarget]:
    """Schedule publications and collapse targets superseded before an open."""
    scheduled: list[ExecutionTarget] = []
    for publication in publications:
        execution_date = next_open_after_publication(publication.published_at, trading_calendar)
        scheduled.append(
            ExecutionTarget(
                model_code=publication.model_code,
                decision_date=pd.Timestamp(publication.decision_date).normalize(),
                published_at=_published_local(publication.published_at),
                execution_date=execution_date,
                run_id=publication.run_id,
                weights=normalize_weights(publication.weights),
                evidence_state=publication.evidence_state,
            )
        )

    by_key: dict[tuple[str, pd.Timestamp], ExecutionTarget] = {}
    for event in sorted(scheduled, key=lambda item: (item.execution_date, item.decision_date, item.published_at)):
        key = (event.model_code, event.execution_date)
        current = by_key.get(key)
        if current is None or (event.decision_date, event.published_at) >= (
            current.decision_date,
            current.published_at,
        ):
            by_key[key] = event
    return sorted(by_key.values(), key=lambda item: (item.execution_date, item.model_code))


def turnover(current: Mapping[str, float], target: Mapping[str, float]) -> float:
    keys = set(current) | set(target)
    return 0.5 * float(sum(abs(float(target.get(key, 0.0)) - float(current.get(key, 0.0))) for key in keys))


def replay_price_return(
    events: Sequence[ExecutionTarget],
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replay target weights at execution-day open and mark at daily close."""
    if not events:
        raise ValueError("no execution events")
    if cost_bps < 0:
        raise ValueError("cost_bps must be non-negative")

    opens = opens.copy().sort_index()
    closes = closes.copy().sort_index()
    calendar = opens.index.intersection(closes.index).sort_values()
    first_execution = min(event.execution_date for event in events)
    calendar = calendar[calendar >= first_execution]
    if calendar.empty:
        raise ValueError("no price dates on or after first execution")

    by_date = {event.execution_date: event for event in events}
    cash = 1.0
    units: dict[str, float] = {}
    nav_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []

    for date in calendar:
        event = by_date.get(pd.Timestamp(date))
        if event is not None:
            required = (set(units) | {ticker for ticker in event.weights if ticker != "CASH"})
            missing = [ticker for ticker in required if ticker not in opens.columns or pd.isna(opens.loc[date, ticker])]
            if missing:
                raise ValueError(f"missing execution open on {date.date()}: {sorted(missing)}")
            invalid_open = [
                ticker
                for ticker in required
                if not np.isfinite(float(opens.loc[date, ticker]))
                or float(opens.loc[date, ticker]) <= 0
            ]
            if invalid_open:
                raise ValueError(f"invalid execution open on {date.date()}: {sorted(invalid_open)}")

            pretrade_nav = cash + sum(units[ticker] * float(opens.loc[date, ticker]) for ticker in units)
            if pretrade_nav <= 0 or not np.isfinite(pretrade_nav):
                raise ValueError(f"invalid pretrade NAV on {date.date()}: {pretrade_nav}")
            current = {ticker: units[ticker] * float(opens.loc[date, ticker]) / pretrade_nav for ticker in units}
            current["CASH"] = cash / pretrade_nav
            target = normalize_weights(event.weights)
            traded = turnover(current, target)
            cost = pretrade_nav * traded * cost_bps / 10000.0
            post_cost_nav = pretrade_nav - cost
            units = {
                ticker: post_cost_nav * weight / float(opens.loc[date, ticker])
                for ticker, weight in target.items()
                if ticker != "CASH" and weight > 0
            }
            cash = post_cost_nav * target.get("CASH", 0.0)
            ledger_rows.append(
                {
                    "model_code": event.model_code,
                    "decision_date": event.decision_date.date().isoformat(),
                    "published_at": event.published_at.isoformat(),
                    "execution_date": event.execution_date.date().isoformat(),
                    "run_id": event.run_id,
                    "evidence_state": event.evidence_state,
                    "turnover": traded,
                    "cost": cost,
                    "pretrade_nav": pretrade_nav,
                    "post_cost_nav": post_cost_nav,
                }
            )

        missing_close = [ticker for ticker in units if ticker not in closes.columns or pd.isna(closes.loc[date, ticker])]
        if missing_close:
            raise ValueError(f"missing mark close on {date.date()}: {sorted(missing_close)}")
        invalid_close = [
            ticker
            for ticker in units
            if not np.isfinite(float(closes.loc[date, ticker]))
            or float(closes.loc[date, ticker]) <= 0
        ]
        if invalid_close:
            raise ValueError(f"invalid mark close on {date.date()}: {sorted(invalid_close)}")
        nav = cash + sum(units[ticker] * float(closes.loc[date, ticker]) for ticker in units)
        nav_rows.append({"date": pd.Timestamp(date), "nav": nav})

    return pd.DataFrame(nav_rows), pd.DataFrame(ledger_rows)


def benchmark_price_nav(
    market: pd.DataFrame,
    *,
    start_date: pd.Timestamp,
) -> pd.DataFrame:
    """Build benchmark NAV from start-session open, then daily closes."""
    frame = market.copy()
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index)).normalize()
    frame = frame.loc[frame.index >= pd.Timestamp(start_date).normalize(), ["open", "close"]].dropna()
    if frame.empty:
        raise ValueError("empty benchmark window")
    base = float(frame.iloc[0]["open"])
    if base <= 0:
        raise ValueError("invalid benchmark open")
    return pd.DataFrame({"date": frame.index, "nav": frame["close"].astype(float).to_numpy() / base})


def nav_metrics(nav: pd.DataFrame, *, initial_nav: float = 1.0) -> dict[str, float | int | None]:
    if nav.empty:
        raise ValueError("empty NAV")
    values = nav.sort_values("date")["nav"].astype(float).reset_index(drop=True)
    augmented = pd.concat([pd.Series([initial_nav]), values], ignore_index=True)
    returns = augmented.pct_change(fill_method=None).dropna()
    peaks = augmented.cummax()
    drawdowns = augmented / peaks - 1.0
    volatility = float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) > 1 else None
    sharpe = None
    if volatility is not None and volatility > 0:
        sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252))
    return {
        "total_return": float(values.iloc[-1] / initial_nav - 1.0),
        "mdd": float(drawdowns.min()),
        "volatility": volatility,
        "sharpe_zero_rf": sharpe,
        "observed_days": int(len(values)),
    }
