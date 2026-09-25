"""Price-led selection ablation; fixed research hypotheses, not operating policy."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .quant25_selection_candidate import candidate_scores

VERSION = "q25_soft_selection_v01"
VARIANTS = ("price_only", "price_growth", "price_growth_accel")
PROTOCOL = {
    "version": VERSION,
    "price_momentum_weight": .6,
    "price_activity_weight": .4,
    "growth_centered_weight": .10,
    "accel_signed_magnitude_weight": .025,
    "max_growth_bonus_abs": .05,
    "max_accel_bonus_abs": .025,
    "max_names": 20,
    "slot_weight": .05,
    "entry": "valid_price AND ma60>ma120 AND slope60>0 AND mom_pct>=.7 AND activity_pct>=.6",
    "missing_fundamental_bonus": 0.,
    "unchanged_accel_bonus": 0.,
    "variants": list(VARIANTS),
    "selection_only": True,
    "returns_used_for_tuning": False,
}


def soft_scores(price: pd.DataFrame, fund: pd.DataFrame, cutoff: str,
                variant: str) -> pd.DataFrame:
    """Keep price eligibility fixed; fundamentals only reorder eligible names.

    Growth bonus = .10 * (complete growth percentile - .5).
    Acceleration bonus = .025 * sign(change) * percentile(abs(nonzero change)).
    Rank acceleration magnitudes only among valid complete nonzero observations.
    Zero/missing/nonfinite changes contribute exactly zero; deteriorating growth
    never gets a positive bonus even when most of the cohort deteriorates.
    """
    if variant not in VARIANTS:
        raise ValueError("unknown soft selection variant")
    out = candidate_scores(price, fund, cutoff, "CORE2")
    # Do not carry CORE2's legacy fundamental tie-break into the price baseline.
    out["price_score"] = .6 * out.mom20_pct + .4 * out.vol_ratio_pct
    level_ok = out.growth_level.between(0, 1) & out.price_valid
    out["growth_bonus"] = (.10 * (out.growth_level - .5)).where(level_ok, 0.)
    accel_ok = (out.accel_pct.between(0, 1) & out.price_valid
                & np.isfinite(out.accel_change) & out.accel_change.ne(0))
    magnitude_pct = out.accel_change.abs().where(accel_ok).rank(pct=True)
    out["accel_bonus"] = (.025 * np.sign(out.accel_change) * magnitude_pct).where(accel_ok, 0.)
    out["applied_growth_bonus"] = out.growth_bonus if variant != "price_only" else 0.
    out["applied_accel_bonus"] = out.accel_bonus if variant == "price_growth_accel" else 0.
    out["score"] = out.price_score + out.applied_growth_bonus + out.applied_accel_bonus
    out["variant"] = variant
    return out
