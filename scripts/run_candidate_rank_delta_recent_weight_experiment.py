from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from run_candidate_rank_delta_rank_change_ablation import (
    MODEL_CODE,
    MODEL_NAME_KO,
    REPORT_DIR,
    _add_next_rank_labels,
    _feature_columns,
    _read_mart,
    _safe_float,
    _split,
)

RANDOM_STATE = 42

TARGET_SPECS = [
    {"segment_type": "family", "segment_key": "S", "label": "label_next_rank_upgrade_5"},
    {"segment_type": "family", "segment_key": "I", "label": "label_next_rank_upgrade_3_retained"},
    {"segment_type": "family", "segment_key": "T", "label": "label_next_rank_upgrade_3_retained"},
    {"segment_type": "model", "segment_key": "internal/S2", "label": "label_next_rank_upgrade_3_retained"},
    {"segment_type": "model", "segment_key": "internal/S3", "label": "label_next_rank_drop"},
    {"segment_type": "model", "segment_key": "internal/S3_ACCEL_V01", "label": "label_next_rank_drop"},
    {"segment_type": "model", "segment_key": "internal/S3_CORE2", "label": "label_next_rank_upgrade_5"},
    {"segment_type": "model", "segment_key": "tseries/T-STOCK-V01", "label": "label_next_rank_upgrade_3_retained"},
]

WEIGHT_MODES = {
    "none": {"years": 0, "weight": 1.0},
    "recent_1y_x3": {"years": 1, "weight": 3.0},
    "recent_2y_x2": {"years": 2, "weight": 2.0},
    "recent_2y_x3": {"years": 2, "weight": 3.0},
}


def _model_family(model_id: Any) -> str:
    value = str(model_id)
    if value.startswith("S"):
        return "S"
    if value.startswith("T-"):
        return "T"
    if value.startswith("I-"):
        return "I"
    if value.startswith("C"):
        return "C"
    return "OTHER"


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
    )


def _fit(train: pd.DataFrame, label: str, numeric: list[str], categorical: list[str], sample_weight: np.ndarray | None) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=160, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    if sample_weight is None:
        pipe.fit(train, train[label].astype(int))
    else:
        pipe.fit(train, train[label].astype(int), model__sample_weight=sample_weight)
    return pipe


def _sample_weight(train: pd.DataFrame, mode: str) -> np.ndarray | None:
    spec = WEIGHT_MODES[mode]
    years = int(spec["years"])
    if years <= 0:
        return None
    max_date = train["event_date"].max()
    cutoff = max_date - pd.DateOffset(years=years)
    weight = np.ones(len(train), dtype=float)
    weight[train["event_date"].ge(cutoff).to_numpy()] = float(spec["weight"])
    return weight


def _segment(df: pd.DataFrame, segment_type: str, segment_key: str) -> pd.DataFrame:
    if segment_type == "family":
        return df[df["model_family"].eq(segment_key)].copy()
    scope, model_id = segment_key.split("/", 1)
    return df[df["scope_key"].eq(scope) & df["model_id"].eq(model_id)].copy()


def _top_bottom(scored: pd.DataFrame, label: str) -> dict[str, Any]:
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    return {
        "top30_label_rate": _safe_float(top[label].mean()),
        "bottom30_label_rate": _safe_float(bottom[label].mean()),
        "top_bottom_label_spread": _safe_float(top[label].mean() - bottom[label].mean()),
        "top30_avg_next_rank_delta": _safe_float(top["next_rank_delta"].mean()),
        "bottom30_avg_next_rank_delta": _safe_float(bottom["next_rank_delta"].mean()),
        "top30_drop_rate": _safe_float(top["dropped_next_rebalance"].mean()),
        "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()),
        "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()),
    }


def _evaluate(
    df: pd.DataFrame,
    spec: dict[str, str],
    weight_mode: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    min_train: int,
    min_valid: int,
) -> dict[str, Any]:
    label = spec["label"]
    train, valid = _split(df, label, train_end, valid_start, valid_end)
    row: dict[str, Any] = {
        **spec,
        "weight_mode": weight_mode,
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "train_positive_rate": _safe_float(train[label].mean()) if not train.empty else None,
        "valid_positive_rate": _safe_float(valid[label].mean()) if not valid.empty else None,
        "status": "ok",
    }
    if len(train) < min_train or len(valid) < min_valid:
        row.update({"status": "skipped", "reason": "insufficient_rows"})
        return row
    if train[label].nunique() < 2 or valid[label].nunique() < 2:
        row.update({"status": "skipped", "reason": "one_class"})
        return row
    numeric, categorical = _feature_columns(train)
    model = _fit(train, label, numeric, categorical, _sample_weight(train, weight_mode))
    scored = valid.copy()
    scored["prob"] = model.predict_proba(valid)[:, 1]
    row.update(
        {
            "numeric_features": int(len(numeric)),
            "categorical_features": int(len(categorical)),
            "auc": _safe_float(roc_auc_score(valid[label].astype(int), scored["prob"])),
            **_top_bottom(scored, label),
        }
    )
    return row


def run_recent_weight_experiment(asof: str, train_end: str, valid_start: str, min_train: int, min_valid: int) -> dict[str, Any]:
    mart = _add_next_rank_labels(_read_mart(asof))
    mart["model_family"] = mart["model_id"].map(_model_family)
    rows: list[dict[str, Any]] = []
    for spec in TARGET_SPECS:
        seg = _segment(mart, spec["segment_type"], spec["segment_key"])
        for mode in WEIGHT_MODES:
            rows.append(_evaluate(seg, spec, mode, train_end, valid_start, asof, min_train, min_valid))

    result = pd.DataFrame(rows)
    ok = result[result["status"].eq("ok")].copy()
    base = ok[ok["weight_mode"].eq("none")][["segment_type", "segment_key", "label", "auc"]].rename(columns={"auc": "base_auc"})
    result = result.merge(base, on=["segment_type", "segment_key", "label"], how="left")
    result["auc_lift_vs_none"] = result["auc"] - result["base_auc"]
    result = result.sort_values(["segment_type", "segment_key", "auc"], ascending=[True, True, False], na_position="last")
    best = (
        result[result["status"].eq("ok")]
        .sort_values(["segment_type", "segment_key", "auc", "top_bottom_label_spread"], ascending=[True, True, False, False])
        .groupby(["segment_type", "segment_key"], as_index=False)
        .head(1)
        .reset_index(drop=True)
    )

    token = asof.replace("-", "")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    result_csv = REPORT_DIR / f"candidate_rank_delta_recent_weight_experiment_{token}.csv"
    best_csv = REPORT_DIR / f"candidate_rank_delta_recent_weight_best_{token}.csv"
    json_path = REPORT_DIR / f"candidate_rank_delta_recent_weight_experiment_{token}.json"
    md_path = REPORT_DIR / f"candidate_rank_delta_recent_weight_experiment_{token}.md"
    result.to_csv(result_csv, index=False, encoding="utf-8-sig")
    best.to_csv(best_csv, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "candidate_rank_delta_recent_weight_experiment",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "weight_modes": WEIGHT_MODES,
        "best_by_segment": best.replace({np.nan: None}).to_dict(orient="records"),
        "outputs": {"result_csv": str(result_csv), "best_csv": str(best_csv), "json": str(json_path), "md": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [
        f"# Candidate Rank Delta Recent Weight Experiment - {asof}",
        "",
        f"- Model: {MODEL_CODE} / {MODEL_NAME_KO}",
        "- Weighting is applied only inside the training window.",
        "",
        "| segment | label | best_weight | auc | base_auc | lift | top30_label | bottom30_label |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in best.to_dict(orient="records"):
        md_lines.append(
            "| {segment_key} | {label} | {weight_mode} | {auc} | {base_auc} | {auc_lift_vs_none} | {top30_label_rate} | {bottom30_label_rate} |".format(
                **{k: "" if pd.isna(v) else v for k, v in row.items()}
            )
        )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run recent weighting experiment for AI-CANDIDATE-RANK-DELTA-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--min-train", type=int, default=200)
    parser.add_argument("--min-valid", type=int, default=50)
    args = parser.parse_args()
    payload = run_recent_weight_experiment(args.asof, args.train_end, args.valid_start, args.min_train, args.min_valid)
    print(
        json.dumps(
            {
                "status": "ok",
                "as_of_date": args.asof,
                "best_by_segment": payload["best_by_segment"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
