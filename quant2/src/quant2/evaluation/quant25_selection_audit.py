"""Research-only selection diagnostics; no operating runners or DB mutations."""
from __future__ import annotations

import numpy as np
import pandas as pd


def fund_snapshot(frame: pd.DataFrame, cutoff: str, *, enforce_feature_date: bool = True) -> pd.DataFrame:
    """Date-level guard only; source publication/revision PIT remains unverified."""
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("duplicate fund ticker/date")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    available = pd.to_datetime(frame["available_from"], errors="coerce")
    mask = available.le(pd.Timestamp(cutoff)) & dates.notna()
    if enforce_feature_date:
        mask &= dates.le(pd.Timestamp(cutoff))
    out = frame.loc[mask].copy()
    out["_date"] = dates[mask]
    out["_available"] = available[mask]
    return (out.sort_values(["ticker", "_available", "_date"], kind="stable")
            .groupby("ticker", as_index=False).tail(1).drop(columns=["_date", "_available"]))


def legacy_scores(frame: pd.DataFrame, model: str) -> pd.DataFrame:
    """Preserve legacy formula, including wrong growth-rank direction, for diagnosis."""
    if model not in {"S3", "CORE2"}:
        raise ValueError("unknown model")
    if frame.ticker.duplicated().any():
        raise ValueError("duplicate candidate ticker")
    out = frame.copy()
    for source, target in [("growth_score", "fund_level_pct"),
                           ("fund_accel_score", "fund_accel_pct"),
                           ("mom20", "mom20_pct"), ("vol_ratio_20", "vol_ratio_pct")]:
        out[target] = out[source].rank(pct=True)
    breakout = out.breakout60.fillna(0).astype(int)
    trend = (out.ma60 > out.ma120) & (out.ma60_slope > 0)
    if model == "S3":
        out["score"] = (.3 * out.fund_level_pct.fillna(0)
                        + .2 * out.fund_accel_pct.fillna(0)
                        + .25 * out.mom20_pct.fillna(0)
                        + .1 * out.vol_ratio_pct.fillna(0)
                        + .05 * breakout + .1 * trend.astype(int))
        out["eligible"] = trend & breakout.eq(1) & out.mom20_pct.ge(.7) & out.fund_accel_pct.ge(.6)
    else:
        out["score"] = (.6 * out.mom20_pct.fillna(0) + .4 * out.vol_ratio_pct.fillna(0)
                        + .002 * out.fund_level_pct.fillna(.5)
                        + .001 * out.fund_accel_pct.fillna(.5))
        out["eligible"] = trend & out.mom20_pct.ge(.7) & out.vol_ratio_pct.ge(.6)
    return out


def fresh_entry_list(scored: pd.DataFrame, top_n: int = 20) -> list[str]:
    """Empty-book diagnostic; excludes original hold/exit/gate and uses stable ticker ties."""
    return scored.loc[scored.eligible].sort_values(
        ["score", "ticker"], ascending=[False, True], kind="stable").head(top_n).ticker.tolist()


def holding_weights(history: pd.DataFrame, nav: pd.DataFrame, cutoff: str) -> tuple[dict[str, float], str]:
    """Extract legacy target weights, validating rather than normalizing bad totals."""
    if nav.date.duplicated().any() or history.duplicated(["date", "ticker"]).any():
        raise ValueError("duplicate holdings/nav keys")
    available = nav.loc[nav.date.le(cutoff)].sort_values("date")
    if available.empty:
        raise ValueError("no previous holdings date")
    row = available.iloc[-1]
    if (pd.Timestamp(cutoff) - pd.Timestamp(row.date)).days > 14:
        raise ValueError("stale holdings date")
    tickers = history.loc[history.date.eq(row.date), "ticker"].tolist()
    cash = float(row.cash_weight)
    if not np.isfinite(cash) or not 0 <= cash <= 1 or len(tickers) != row.holdings:
        raise ValueError("invalid holdings/cash")
    if not tickers and cash != 1:
        raise ValueError("empty invested holdings")
    if "CASH" in tickers:
        raise ValueError("reserved cash ticker")
    weights = {ticker: (1 - cash) / len(tickers) for ticker in tickers}
    return {**weights, "CASH": cash}, str(row.date)


def target_distance(left: dict[str, float], right: dict[str, float]) -> float:
    """Half L1 target-weight distance, not executed turnover or cost."""
    return sum(abs(left.get(k, 0) - right.get(k, 0)) for k in left.keys() | right.keys()) / 2


def set_overlap(left: list[str], right: list[str]) -> dict[str, float | int | None]:
    a, b = set(left), set(right)
    return {"left_count": len(a), "right_count": len(b), "intersection": len(a & b),
            "jaccard": len(a & b) / len(a | b) if a | b else None}
