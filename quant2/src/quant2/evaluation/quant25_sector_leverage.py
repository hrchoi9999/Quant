"""Research-only sector leverage targets within the existing equity-risk budget."""

import math
from dataclasses import replace

import pandas as pd


def choose_sector(prices, calendar, observation_date, candidates):
    """Use only complete pre-decision daily data; never synthesize leveraged returns."""
    days = [d for d in calendar if d <= observation_date][-64:]
    if len(days) < 64 or days[-1] != observation_date:
        return None, []
    diagnostics = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        if candidate["daily_multiplier"] != 2 or candidate["region"] != "KR" or candidate["is_inverse"]:
            raise ValueError("only verified domestic positive 2x sector ETFs")
        q = prices[prices.ticker.eq(ticker) & prices.date.isin(days)].sort_values("date")
        if q.date.duplicated().any():
            raise ValueError("duplicate sector quotes")
        if q.date.tolist() != days or candidate["list_date"] > days[0]:
            diagnostics.append({"ticker": ticker, "eligible": False, "reason": "INSUFFICIENT_LISTED_HISTORY"})
            continue
        values = q[["open", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
        if not values.map(math.isfinite).all().all() or not values.gt(0).all().all():
            diagnostics.append({"ticker": ticker, "eligible": False, "reason": "UNUSABLE_QUOTES_OR_HALT"})
            continue
        close = values.close
        liquidity = float((values.close * values.volume).tail(20).mean())
        momentum = float(close.iloc[-1] / close.iloc[0] - 1)
        eligible = (
            liquidity >= 1_000_000_000
            and momentum > 0
            and close.iloc[-1] > close.tail(20).mean()
            and close.iloc[-1] > close.tail(60).mean()
        )
        diagnostics.append(
            {
                "ticker": ticker,
                "sector": candidate["sector"],
                "eligible": bool(eligible),
                "momentum_63": momentum,
                "mean_traded_value_proxy_20": liquidity,
            }
        )
    eligible = [row for row in diagnostics if row["eligible"]]
    return (
        sorted(eligible, key=lambda row: (-row["momentum_63"], -row["mean_traded_value_proxy_20"], row["ticker"]))[0]
        if eligible
        else None
    ), diagnostics


def add_sector_leverage(event, mode, selection, stock_tickers, *, max_weight=0.05, cap=30):
    """A 5% 2x ETF displaces 10% stock exposure; released balance stays cash."""
    if not 0 < max_weight <= 0.05 or cap != 30 or mode not in {"risk_on", "neutral", "risk_off"}:
        raise ValueError("declared leverage limit and total cap required")
    weights = dict(event.weights)
    if any(not math.isfinite(w) or w < 0 for w in weights.values()) or abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("unfunded source target")
    stocks = [t for t in weights if t != "CASH" and t in stock_tickers and weights[t] > 0]
    initial_stock = sum(weights[t] for t in stocks)
    record = {
        "mode": mode,
        "selected_ticker": None,
        "leverage_weight": 0.0,
        "stock_target_before": initial_stock,
        "dropped_stock_targets": [],
        "status": "NO_LEVERAGE_OUTSIDE_RISK_ON",
    }
    if mode == "risk_on" and selection and initial_stock > 0:
        ticker = selection["ticker"]
        if ticker in weights:
            raise ValueError("sector target overlaps existing instrument")
        weight = min(max_weight, initial_stock / 2)
        ratio = (initial_stock - 2 * weight) / initial_stock
        for stock in stocks:
            weights[stock] *= ratio
        weights = {t: w for t, w in weights.items() if t == "CASH" or w > 0}
        weights[ticker] = weight
        # Original stock insertion order is descending selection rank.
        while sum(t != "CASH" for t in weights) > cap:
            drop = next((t for t in reversed(stocks) if t in weights), None)
            if drop is None:
                raise ValueError("no stock target available to respect cap")
            weights.pop(drop)
            record["dropped_stock_targets"].append(drop)
        record.update(
            selected_ticker=ticker, leverage_weight=weight, status="RESEARCH_TARGET_REQUIRES_OVERLAP_AND_TR_VALIDATION"
        )
    elif mode == "risk_on":
        record["status"] = "NO_ELIGIBLE_SECTOR_OR_STOCK_BUDGET"
    if record["leverage_weight"] > 0:
        weights["CASH"] = 1 - sum(w for t, w in weights.items() if t != "CASH")
    effective = sum(weights.get(t, 0) for t in stocks) + 2 * record["leverage_weight"]
    if weights["CASH"] < -1e-10 or effective > initial_stock + 1e-10 or len(weights) - 1 > cap:
        raise ValueError("funding, effective exposure, or holding cap violated")
    record.update(
        stock_target_after=sum(weights.get(t, 0) for t in stocks),
        effective_equity_exposure=effective,
        cash_target=weights["CASH"],
        target_names=len(weights) - 1,
    )
    return replace(event, weights=weights, run_id="Q25_30_SECTOR_LEVERAGE_V1"), record
