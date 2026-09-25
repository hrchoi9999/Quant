"""Common cadence and separate stock/ETF sleeves for Q25 research."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from src.backtest.configs.s6_defensive_config import S6DefensiveConfig
from src.backtest.portfolio.s6_defensive_allocator import allocate_s6_defensive
from src.evaluation.normalized_nav import ExecutionTarget, next_open_after_publication
from src.quant2.evaluation.quant25_event_exclusion import compile_event_targets
from src.quant2.evaluation.quant25_selection_candidate import PRICE_FIELDS


def feature_coverage(features: pd.DataFrame, calendar: list[str], tickers: list[str]) -> pd.DataFrame:
    dates = sorted(set(decision_dates(calendar, "W")) | set(decision_dates(calendar, "M")))
    subset = features.loc[features.ticker.isin(tickers)].copy()
    if subset.duplicated(["date", "ticker"]).any():
        raise ValueError("duplicate feature keys")
    subset["complete"] = np.isfinite(subset[list(PRICE_FIELDS)].apply(pd.to_numeric, errors="coerce")).all(axis=1)
    rows = subset.groupby("date").agg(rows=("ticker", "size"), complete=("complete", "sum"))
    return rows.reindex(dates, fill_value=0).rename_axis("date").reset_index()


def decision_dates(calendar: list[str], cadence: str, seed: str = "2023-06-30") -> list[str]:
    """Common seed then Wednesday/previous-session or completed month-end."""
    if calendar != sorted(set(calendar)) or seed not in calendar:
        raise ValueError("unique ordered calendar including seed required")
    idx = pd.DatetimeIndex(pd.to_datetime(calendar))
    cutoff = idx[-1]
    if cadence == "W":
        anchors = pd.date_range(seed, cutoff, freq="W-WED")
        days = [idx[idx <= d][-1].strftime("%Y-%m-%d") for d in anchors]
    elif cadence == "M":
        days = [
            g.max().strftime("%Y-%m-%d")
            for _, g in pd.Series(idx).groupby(idx.to_period("M"))
            if g.max().to_period("M").end_time.normalize() <= cutoff
        ]
    else:
        raise ValueError("cadence must be W or M")
    return sorted({seed, *[d for d in days if seed < d < calendar[-1]]})


def valid_weights(weights: dict[str, float]) -> None:
    values = np.array(list(weights.values()), dtype=float)
    if not len(values) or not np.isfinite(values).all() or (values < 0).any() or abs(values.sum() - 1) > 1e-9:
        raise ValueError("finite nonnegative fully funded weights required")


def stock_events(scores, prices, variant, cadence, count, calendar, rules):
    if count not in (15, 20):
        raise ValueError("predeclared stock count must be 15 or 20")
    days = decision_dates(calendar, cadence)
    subset = scores.loc[scores.decision_date.isin(days) & scores.variant.eq(variant)].copy()
    for day in days:
        daily = subset.loc[subset.decision_date.eq(day) & subset.eligible].sort_values(
            ["score", "ticker"], ascending=[False, True]
        )
        subset.loc[daily.index[count:], "eligible"] = False
    events, records, issue = compile_event_targets(subset, prices, variant, "replace20", calendar, rules)
    # The existing guard uses 20 fixed slots; convert to the declared slot count.
    transformed = []
    for event, row in zip(events, records):
        weights = {k: v * 20 / count for k, v in event.weights.items() if k != "CASH"}
        weights["CASH"] = max(0.0, 1 - sum(weights.values()))
        valid_weights(weights)
        transformed.append(replace(event, weights=weights, model_code="Q25_CADENCE_STOCK"))
        row.update(weights=weights, cadence=cadence, max_names=count)
        for exclusion in row["excluded_entries_or_targets"]:
            exclusion["weight_to_cash"] = 1 / count
    return transformed, records, issue


def etf_events(prices, meta, calendar, cadence):
    """Reuse S6 allocation, with strictly as-of availability and liquidity."""
    selected = prices.loc[prices.ticker.isin(meta.ticker)]
    dates = sorted(prices.date.unique())
    close = selected.pivot(index="date", columns="ticker", values="close").reindex(dates)
    value = selected.pivot(index="date", columns="ticker", values="value").reindex(dates)
    close.index = pd.to_datetime(close.index)
    value.index = pd.to_datetime(value.index)
    quotes = selected.set_index(["date", "ticker"])
    cfg = S6DefensiveConfig()
    events, records, held = [], [], set()
    for day in decision_dates(calendar, cadence):
        stamp = pd.Timestamp(day)
        px = close.loc[:stamp].tail(21)
        activity = value.loc[:stamp].tail(20)
        valid = px.columns[
            (px.notna() & np.isfinite(px) & px.gt(0)).all() & activity.notna().all() & activity.gt(0).all()
        ]
        if len(px) < 21 or len(activity) < 20:
            valid = []
        tradable = set()
        for ticker in valid:
            try:
                quote = quotes.loc[(day, ticker), ["open", "close", "volume"]].astype(float)
                if np.isfinite(quote).all() and quote.gt(0).all():
                    tradable.add(ticker)
            except KeyError:
                pass
        # A held missing quote cannot be silently converted to cash.
        locked = []
        for ticker in held:
            try:
                q = quotes.loc[(day, ticker), ["open", "close", "volume"]].astype(float)
                usable = np.isfinite(q).all() and q.gt(0).all()
            except KeyError:
                usable = False
            if not usable:
                locked.append(ticker)
        execution = next_open_after_publication(pd.Timestamp(day + "T16:00:00+09:00"), pd.DatetimeIndex(calendar))
        if locked:
            return (
                events,
                records,
                {
                    "date": execution.strftime("%Y-%m-%d"),
                    "decision_date": day,
                    "reason": "held_etf_quote_unusable",
                    "locked_tickers": sorted(locked),
                },
            )
        core = meta.loc[meta.ticker.isin(tradable)].copy()
        core["liquidity_20d_value"] = core.ticker.map(activity.mean())
        # Keep the market signal comparable across dates. The legacy broad-group
        # metadata also contains KOSDAQ and sector ETFs; liquidity must not switch
        # the market being measured. Portfolio ETF groups remain asset-specific.
        core = core.loc[core.group_key.ne(cfg.signals.market_group) | core.ticker.eq("069500")]
        if "069500" not in set(core.ticker):
            return (
                events,
                records,
                {
                    "date": execution.strftime("%Y-%m-%d"),
                    "decision_date": day,
                    "reason": "fixed_market_proxy_signal_unavailable",
                    "held_tickers": sorted(held),
                },
            )
        if core.empty:
            return (
                events,
                records,
                {
                    "date": execution.strftime("%Y-%m-%d"),
                    "decision_date": day,
                    "reason": "all_etf_signals_unavailable_not_a_cash_signal",
                    "held_tickers": sorted(held),
                },
            )
        else:
            history = close.loc[:stamp]
            alloc = allocate_s6_defensive(
                core_df=core,
                close_wide=history,
                ret_wide=history.pct_change(fill_method=None),
                asof=stamp,
                cfg=cfg,
                available_tickers=sorted(tradable),
            )
            weights = {k: float(v) for k, v in alloc.weights.items() if v > 0}
            diagnostics = alloc.diagnostics
        valid_weights(weights)
        if len(set(weights) - {"CASH"}) > 5:
            raise ValueError("unexpected S6 ETF count")
        inverse = set(meta.loc[meta.is_inverse.eq(1), "ticker"])
        if sum(weights.get(t, 0.0) for t in inverse) > cfg.bounds.inverse_cap + 1e-9:
            raise ValueError("S6 normalized inverse weight breaches declared cap")
        events.append(
            ExecutionTarget(
                "S6_REFERENCE",
                stamp,
                pd.Timestamp(day + "T16:00:00+09:00"),
                execution,
                "Q25_CADENCE_ETF",
                weights,
                "RECONSTRUCTED_PRICE_ONLY",
            )
        )
        records.append(
            {
                "decision_date": day,
                "execution_date": execution.strftime("%Y-%m-%d"),
                "cadence": cadence,
                "weights": weights,
                "diagnostics": diagnostics,
            }
        )
        held = set(weights) - {"CASH"}
    return events, records, None


def combine_sleeves(stock: pd.DataFrame, etf: pd.DataFrame, stock_share: float = 0.5) -> pd.DataFrame:
    """Initial capital split; no hidden trades/transfers on another sleeve's dates."""
    if not 0 <= stock_share <= 1 or stock.date.tolist() != etf.date.tolist():
        raise ValueError("equal dates and bounded initial allocation required")
    result = stock[["date"]].copy()
    for field in ["nav", "cash"]:
        result[field] = stock_share * stock[field].to_numpy() + (1 - stock_share) * etf[field].to_numpy()
    return result
