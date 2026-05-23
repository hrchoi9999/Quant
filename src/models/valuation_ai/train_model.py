# train_model.py ver 2026-05-06_001
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .common import now_ts, read_sql, write_json, write_table
from .config import (
    CATEGORICAL_COLUMNS,
    EVAL_TABLE,
    FEATURE_COLUMNS,
    FEATURE_TABLE,
    LABEL_TABLE,
    MODEL_CODE,
    MODEL_NAME_KR,
    MODEL_DIR,
    OUT_DB,
    REPORT_DIR,
)


def _load_training_data(db: Path) -> pd.DataFrame:
    features = read_sql(db, f"SELECT * FROM {FEATURE_TABLE}", parse_dates=["asof_date"])
    labels = read_sql(db, f"SELECT * FROM {LABEL_TABLE}", parse_dates=["asof_date"])
    if features.empty or labels.empty:
        raise SystemExit("features or labels are empty")
    features["ticker"] = features["ticker"].astype(str).str.zfill(6)
    labels["ticker"] = labels["ticker"].astype(str).str.zfill(6)
    return features.merge(labels, on=["asof_date", "ticker"], how="left", suffixes=("", "_label"))


def _preprocessor(df: pd.DataFrame) -> ColumnTransformer:
    numeric = [col for col in FEATURE_COLUMNS if col in df.columns and df[col].notna().any()]
    categorical = [col for col in CATEGORICAL_COLUMNS if col in df.columns and df[col].notna().any()]
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ]
    )


def _fit_regressor(train: pd.DataFrame) -> Pipeline:
    model = GradientBoostingRegressor(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=42)
    pipe = Pipeline([("prep", _preprocessor(train)), ("model", model)])
    pipe.fit(train, train["fwd_excess_ret_12m"].astype(float))
    return pipe


def _fit_classifier(train: pd.DataFrame, label: str) -> Pipeline | None:
    if train[label].nunique() < 2:
        return None
    model = GradientBoostingClassifier(n_estimators=160, learning_rate=0.04, max_depth=3, random_state=42)
    pipe = Pipeline([("prep", _preprocessor(train)), ("model", model)])
    pipe.fit(train, train[label].astype(int))
    return pipe


def _eval_regression(valid: pd.DataFrame, pred: np.ndarray) -> dict[str, Any]:
    target = pd.to_numeric(valid["fwd_excess_ret_12m"], errors="coerce")
    pred_s = pd.Series(pred, index=valid.index)
    top = valid.assign(pred=pred_s).sort_values("pred", ascending=False).head(min(30, len(valid)))
    bottom = valid.assign(pred=pred_s).sort_values("pred", ascending=True).head(min(30, len(valid)))
    return {
        "rank_ic": None if len(valid) < 5 else round(float(pred_s.rank().corr(target.rank())), 6),
        "ic": None if len(valid) < 5 else round(float(pred_s.corr(target)), 6),
        "top30_avg_excess_12m": None if top.empty else round(float(top["fwd_excess_ret_12m"].mean()), 6),
        "top30_avg_ret_12m": None if top.empty else round(float(top["fwd_ret_12m"].mean()), 6),
        "bottom30_avg_excess_12m": None if bottom.empty else round(float(bottom["fwd_excess_ret_12m"].mean()), 6),
        "top_bottom_spread_12m": None if top.empty or bottom.empty else round(float(top["fwd_excess_ret_12m"].mean() - bottom["fwd_excess_ret_12m"].mean()), 6),
        "top30_win_rate": None if top.empty else round(float((top["fwd_excess_ret_12m"] > 0).mean()), 6),
    }


def train_model(db: Path, train_end: str, valid_start: str | None, valid_end: str, model_version: str | None = None) -> dict[str, Any]:
    df = _load_training_data(db)
    df = df[df["fwd_excess_ret_12m"].notna()].sort_values("asof_date").copy()
    if df.empty:
        raise SystemExit("no 12M labels available for valuation AI training")
    valid_start_ts = pd.Timestamp(valid_start) if valid_start else pd.Timestamp(train_end) + pd.Timedelta(days=1)
    train = df[df["asof_date"] <= pd.Timestamp(train_end)].copy()
    valid = df[(df["asof_date"] >= valid_start_ts) & (df["asof_date"] <= pd.Timestamp(valid_end))].copy()
    if train.empty or len(train) < 200:
        raise SystemExit(f"insufficient training rows: {len(train)}")
    if valid.empty:
        # Keep a holdout even when recent 12M labels are not yet available.
        cut = sorted(df["asof_date"].unique())[max(1, int(len(df["asof_date"].unique()) * 0.80)) - 1]
        train = df[df["asof_date"] <= cut].copy()
        valid = df[df["asof_date"] > cut].copy()

    regressor = _fit_regressor(train)
    out_model_dir = MODEL_DIR
    out_model_dir.mkdir(parents=True, exist_ok=True)
    model_version = model_version or f"{MODEL_CODE}_{valid_end.replace('-', '')}_001"
    model_path = out_model_dir / f"{model_version}.joblib"
    bundle = {
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KR,
        "model_version": model_version,
        "regressor": regressor,
    }

    pred = regressor.predict(valid)
    eval_payload = {
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KR,
        "model_version": model_version,
        "status": "ok",
        "train_start": str(train["asof_date"].min().date()),
        "train_end": str(train["asof_date"].max().date()),
        "valid_start": str(valid["asof_date"].min().date()),
        "valid_end": str(valid["asof_date"].max().date()),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "target": "fwd_excess_ret_12m",
        "optimization_priority": "return_first",
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d when available",
        **_eval_regression(valid, pred),
        "created_at": now_ts(),
        "model_path": str(model_path),
    }

    class_rows = []
    for label in ["label_outperform", "label_underperform", "label_overheated", "label_value_creation"]:
        cls_train = train[train[label].notna()].copy()
        cls_valid = valid[valid[label].notna()].copy()
        classifier = _fit_classifier(cls_train, label) if len(cls_train) >= 200 else None
        auc = None
        if classifier is not None and not cls_valid.empty and cls_valid[label].nunique() >= 2:
            prob = classifier.predict_proba(cls_valid)[:, 1]
            auc = float(roc_auc_score(cls_valid[label].astype(int), prob))
        if classifier is not None:
            bundle[label] = classifier
        class_rows.append(
            {
                "model_code": MODEL_CODE,
                "model_name_ko": MODEL_NAME_KR,
                "model_version": model_version,
                "target": label,
                "train_rows": int(len(cls_train)),
                "valid_rows": int(len(cls_valid)),
                "auc": None if auc is None else round(auc, 6),
                "created_at": now_ts(),
            }
        )

    eval_df = pd.DataFrame([eval_payload, *class_rows])
    temp_model_path = model_path.with_name(f"{model_path.name}.tmp")
    joblib.dump(bundle, temp_model_path)
    temp_model_path.replace(model_path)
    write_table(db, EVAL_TABLE, eval_df)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    eval_df.to_csv(REPORT_DIR / f"valuation_model_eval_{valid_end.replace('-', '')}.csv", index=False, encoding="utf-8-sig")
    write_json(
        REPORT_DIR / f"valuation_model_eval_{valid_end.replace('-', '')}.json",
        {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KR,
            "regression": eval_payload,
            "classification": class_rows,
        },
    )
    write_json(
        out_model_dir / f"{model_version}_metadata.json",
        {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KR,
            "model_version": model_version,
            "feature_columns": FEATURE_COLUMNS,
            "categorical_columns": CATEGORICAL_COLUMNS,
            "optimization_priority": "return_first",
            "market_context_source": "QuantMarket handoff primary ridge calibration 20d when available",
            "evaluation": eval_payload,
        },
    )
    return eval_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Train AI-GROWTH-VALUATION-V01 baseline model.")
    parser.add_argument("--db", default=str(OUT_DB))
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--valid-end", required=True)
    parser.add_argument("--model-version")
    args = parser.parse_args()
    result = train_model(Path(args.db), args.train_end, args.valid_start, args.valid_end, args.model_version)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
