"""Q25 research Ridge: reuse QM math, admit only targets known at decision time.

Target timing is enforced; this does not certify historical feature vintages.
No DB, publishing or operating runner dependencies.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

VERSION = "Q25_RIDGE_MATURE_TARGET_V1"


def aware(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("explicit timezone-aware timestamp required")
    return stamp.tz_convert("UTC")


def mature_indices(decisions: pd.Series, available: pd.Series, targets: pd.Series,
                   cutoff: pd.Timestamp) -> list[int]:
    return decisions.index[(decisions < cutoff) & (available <= cutoff)
                           & np.isfinite(targets)].tolist()


def calibrate_mature_targets(
    frame: pd.DataFrame, features: list[str], *, min_train: int = 252,
    refit_interval: int = 20, ridge_alpha: float = 1.0,
) -> pd.DataFrame:
    """One scope/horizon; unavailable target timestamps stay excluded.

    Caller supplies target_available_at from evidence, not row order. For
    reconstructed research it may be a disclosed conservative proxy. Outputs
    never claim PIT eligibility or calibrated probability.
    """
    if min_train < 2 or refit_interval < 1 or not np.isfinite(ridge_alpha) or ridge_alpha < 0:
        raise ValueError("invalid calibration parameters")
    reserved = {"decision_at", "target_available_at", "forward_return"}
    if not features or len(set(features)) != len(features) or set(features) & reserved:
        raise ValueError("unique non-target features required")
    for column in ("market_scope", "forecast_horizon"):
        if column in frame and frame[column].nunique(dropna=False) != 1:
            raise ValueError("one scope and horizon per calibration")
    data = frame.copy()
    data["decision_at"] = data["decision_at"].map(aware)
    if data["decision_at"].duplicated().any():
        raise ValueError("duplicate decisions")
    data = data.sort_values("decision_at").reset_index(drop=True)
    available = pd.to_datetime(data["target_available_at"].map(
        lambda value: pd.NaT if pd.isna(value) else aware(value)
    ), utc=True)
    if ((available <= data["decision_at"]) & available.notna()).any():
        raise ValueError("forward target availability must follow its own decision")
    y = pd.to_numeric(data["forward_return"], errors="coerce")
    x = data[features].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    beta = None
    trained: list[int] = []
    results = []
    for index, cutoff in enumerate(data["decision_at"]):
        eligible = mature_indices(data["decision_at"], available, y, cutoff)
        if len(eligible) >= min_train and (beta is None or len(eligible) - len(trained) >= refit_interval):
            trained = eligible
            train = x.loc[trained]
            medians = train.median().fillna(0.0)
            filled = train.fillna(medians)
            means = filled.mean()
            stds = filled.std(ddof=0).replace(0.0, 1.0).fillna(1.0)
            matrix = np.column_stack([np.ones(len(trained)), (filled - means) / stds])
            penalty = np.eye(matrix.shape[1]) * ridge_alpha
            penalty[0, 0] = 0
            beta = np.linalg.pinv(matrix.T @ matrix + penalty) @ matrix.T @ y.loc[trained].to_numpy()
            target_mean = float(y.loc[trained].mean())
            target_std = float(y.loc[trained].std(ddof=0)) or 1.0
            training_cutoff = cutoff
        prediction = score = None
        if beta is not None:
            vector = (x.loc[index].fillna(medians) - means) / stds
            prediction = float(np.array([1.0, *vector]) @ beta)
            score = float(np.clip((prediction - target_mean) / target_std, -3, 3))
            if not np.isfinite(prediction):
                raise ValueError("nonfinite prediction")
        train_dates = [data.at[i, "decision_at"].isoformat() for i in trained]
        results.append({
            "decision_at": cutoff.isoformat(), "candidate_id": VERSION,
            "predicted_forward_return": prediction, "score": score,
            "mature_eligible_count": len(eligible), "fitted_sample_count": len(trained),
            "training_cutoff": training_cutoff.isoformat() if trained else None,
            "max_target_available_at": available.loc[trained].max().isoformat() if trained else None,
            "immature_target_count": int((available.loc[trained] > cutoff).sum()),
            "training_dates_sha256": hashlib.sha256(json.dumps(train_dates).encode()).hexdigest(),
            "probability": None, "evidence_state": "RESEARCH_INPUT_PIT_UNVERIFIED",
            "operationally_actionable": False,
        })
    return pd.DataFrame(results)
