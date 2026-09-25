"""Q25 selection candidates. Pure research functions; no operational writes.

Daily cutoffs mean after-close decisions. Date guards do not establish source
vintages, historical universe membership, or corporate-action correctness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .quant25_selection_audit import fund_snapshot

CANDIDATE_VERSION = "q25_selection_v01"
PRICE_FIELDS = ("close", "ma60", "ma120", "ma60_slope", "ma120_slope",
                "mom20", "vol_ratio_20", "breakout60")


class SelectionInputError(ValueError):
    """Unusable input must not be interpreted as a market regime or cash signal."""


def _keys(frame: pd.DataFrame) -> None:
    if frame.ticker.isna().any() or frame.ticker.astype(str).str.strip().eq("").any():
        raise SelectionInputError("missing ticker")
    if frame.ticker.duplicated().any():
        raise SelectionInputError("duplicate ticker")


def _finite(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    return frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce").replace(
        [np.inf, -np.inf], np.nan)


def corrected_fund_snapshot(history: pd.DataFrame, cutoff: str,
                            tickers: list[str]) -> pd.DataFrame:
    """Raw-growth level and true growth-rate change, independently ranked.

    Compare with the as-of snapshot at the third preceding calendar month-end,
    never the third previous stored row. Rank only complete observations in
    the supplied cohort; missing values stay missing rather than becoming ranks.
    """
    cohort = pd.DataFrame({"ticker": tickers})
    _keys(cohort)
    day = pd.Timestamp(cutoff)
    prior_day = (day.to_period("M") - 3).end_time.strftime("%Y-%m-%d")
    columns = ["ticker", "date", "available_from", "revenue_yoy", "op_income_yoy"]
    now = fund_snapshot(history, cutoff)[columns]
    prior = fund_snapshot(history, prior_day)[columns]
    out = cohort.merge(now, how="left", on="ticker", validate="one_to_one").merge(
        prior.rename(columns={c: "prior_" + c for c in columns if c != "ticker"}),
        how="left", on="ticker", validate="one_to_one")
    current_fields = ("revenue_yoy", "op_income_yoy")
    previous_fields = ("prior_revenue_yoy", "prior_op_income_yoy")
    out[list(current_fields)] = _finite(out, current_fields)
    out[list(previous_fields)] = _finite(out, previous_fields)
    out["fund_complete"] = out[list(current_fields)].notna().all(axis=1)
    out["accel_complete"] = out.fund_complete & out[list(previous_fields)].notna().all(axis=1)
    complete = out.fund_complete
    out["growth_level"] = np.nan
    out.loc[complete, "growth_level"] = (
        .7 * out.loc[complete, "revenue_yoy"].rank(pct=True)
        + .3 * out.loc[complete, "op_income_yoy"].rank(pct=True))
    out["accel_change"] = (
        .7 * (out.revenue_yoy - out.prior_revenue_yoy)
        + .3 * (out.op_income_yoy - out.prior_op_income_yoy)).where(out.accel_complete)
    out["accel_pct"] = out.accel_change.rank(pct=True)
    out["prior_cutoff"] = prior_day
    return out.rename(columns={"date": "fund_date"})


def price_quality(price: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Per-security incomplete inputs plus a blocking whole-cohort check."""
    _keys(price)
    if price.empty:
        raise SelectionInputError("empty price cohort")
    out = price.copy()
    date_ok = pd.to_datetime(out["date"], errors="coerce").eq(pd.Timestamp(cutoff))
    out[list(PRICE_FIELDS)] = _finite(out, PRICE_FIELDS)
    finite = out[list(PRICE_FIELDS)].notna().all(axis=1)
    domain = (out[["close", "ma60", "ma120"]].gt(0).all(axis=1)
              & out.vol_ratio_20.ge(0) & out.breakout60.isin([0, 1]))
    out["price_valid"] = date_ok & finite & domain
    out["price_status"] = np.select(
        [~date_ok, ~finite, ~domain],
        ["missing_or_wrong_price_date", "incomplete_or_nonfinite_features", "invalid_feature_domain"],
        default="ok")
    if not out.price_valid.any():
        raise SelectionInputError("no valid price features; not a cash or regime signal")
    return out


def candidate_scores(price: pd.DataFrame, fund: pd.DataFrame, cutoff: str,
                     model: str) -> pd.DataFrame:
    """S3 uses complete fundamentals; CORE2 keeps neutral missing tie-breaks.

    Legacy weights and price entry thresholds are retained for diagnosis.
    S3 additionally requires a positive actual growth-rate change, so an
    unchanged annual report cannot pass acceleration merely via tied ranks.
    """
    if model not in {"S3", "CORE2"}:
        raise ValueError("unknown model")
    _keys(fund)
    out = price_quality(price, cutoff).merge(fund, on="ticker", how="left", validate="one_to_one")
    # Candidate API also rejects future/unknown fundamental metadata supplied
    # by a caller bypassing corrected_fund_snapshot.
    current_time_ok = (
        pd.to_datetime(out.fund_date, errors="coerce").le(pd.Timestamp(cutoff))
        & pd.to_datetime(out.available_from, errors="coerce").le(pd.Timestamp(cutoff)))
    prior_cutoff = (pd.Timestamp(cutoff).to_period("M") - 3).end_time.normalize()
    prior_time_ok = (
        pd.to_datetime(out.prior_date, errors="coerce").le(prior_cutoff)
        & pd.to_datetime(out.prior_available_from, errors="coerce").le(prior_cutoff))
    level_ok = out.fund_complete.eq(True) & current_time_ok & np.isfinite(out.growth_level)
    accel_ok = out.accel_complete.eq(True) & level_ok & prior_time_ok & np.isfinite(out.accel_pct)
    out["growth_level"] = out.growth_level.where(level_ok)
    out["accel_pct"] = out.accel_pct.where(accel_ok)
    valid = out.price_valid
    for col, name in [("mom20", "mom20_pct"), ("vol_ratio_20", "vol_ratio_pct")]:
        out[name] = out[col].where(valid).rank(pct=True)
    trend = (out.ma60 > out.ma120) & (out.ma60_slope > 0)
    if model == "S3":
        if not (valid & accel_ok).any():
            raise SelectionInputError("no complete S3 fundamental history; not a cash signal")
        out["score"] = (.3 * out.growth_level + .2 * out.accel_pct
                        + .25 * out.mom20_pct + .1 * out.vol_ratio_pct
                        + .05 * out.breakout60 + .1 * trend.astype(int))
        out["eligible"] = (valid & accel_ok & trend & out.breakout60.eq(1)
                           & out.mom20_pct.ge(.7) & out.accel_pct.ge(.6)
                           & out.accel_change.gt(0))
    else:
        out["score"] = (.6 * out.mom20_pct + .4 * out.vol_ratio_pct
                        + .002 * out.growth_level.fillna(.5)
                        + .001 * out.accel_pct.fillna(.5))
        out["eligible"] = valid & trend & out.mom20_pct.ge(.7) & out.vol_ratio_pct.ge(.6)
    out["score"] = out.score.where(valid)
    return out
