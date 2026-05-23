from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from run_candidate_rank_delta_rank_change_ablation import _add_next_rank_labels

ROOT = Path(r"D:\Quant")
SOURCE_DIR = ROOT / r"reports\ai_overlay_v01"
REPORT_DIR = ROOT / r"reports\candidate_rank_delta_ai_v01"
MODEL_DIR = ROOT / r"data\models\candidate_rank_delta_ai"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

MODEL_CODE = "AI-CANDIDATE-RANK-DELTA-V01"
MODEL_NAME_KO = "후보순위조정AI"
SOURCE_MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
RANDOM_STATE = 42

KEY_COLUMNS = {"scope_key", "model_id", "ticker", "name", "event_date", "week_end", "live_start_date"}
FORWARD_PREFIXES = ("fwd_", "label_", "has_")
EXCLUDED_NUMERIC = {"is_current", "is_live_event"}
RANK_LABEL_COLUMNS = {
    "next_week_end",
    "next_rank_no",
    "next_rank_no_effective",
    "next_rank_size",
    "next_rank_delta",
    "dropped_next_rebalance",
}
MODEL_LABELS = {
    "drop": "label_next_rank_drop",
    "retained_upgrade": "label_next_rank_upgrade_3_retained",
    "retained_downgrade": "label_next_rank_downgrade_3_retained",
}


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _read_mart(asof: str) -> pd.DataFrame:
    path = SOURCE_DIR / f"ai_overlay_training_mart_{asof.replace('-', '')}.csv"
    if not path.exists():
        raise SystemExit(f"missing mart: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df = df[df["event_date"].notna()].copy()
    df["week_end"] = pd.to_datetime(df["week_end"], errors="coerce")
    if "asset_type" in df.columns:
        asset = df["asset_type"].astype(str).str.upper()
        df = df[~asset.str.contains("ETF", na=False)].copy()
    return _add_next_rank_labels(df)


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    for col in df.columns:
        if col in KEY_COLUMNS or col in EXCLUDED_NUMERIC or col in RANK_LABEL_COLUMNS or col.startswith(FORWARD_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _split(df: pd.DataFrame, train_end: str, valid_start: str, valid_end: str, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[label].notna()].sort_values("event_date").copy()
    train = labeled[labeled["event_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["event_date"] >= pd.Timestamp(valid_start)) & (labeled["event_date"] <= pd.Timestamp(valid_end))].copy()
    if len(train) >= 200 and len(valid) >= 50 and train[label].nunique() >= 2 and valid[label].nunique() >= 2:
        return train, valid
    dates = sorted(labeled["event_date"].dropna().unique())
    cut = dates[max(1, int(len(dates) * 0.80)) - 1]
    return labeled[labeled["event_date"] <= cut].copy(), labeled[labeled["event_date"] > cut].copy()


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


def _sample_weight(train: pd.DataFrame) -> np.ndarray:
    max_date = train["event_date"].max()
    cutoff = max_date - pd.DateOffset(years=1)
    weight = np.ones(len(train), dtype=float)
    weight[train["event_date"].ge(cutoff).to_numpy()] = 3.0
    return weight


def _fit(train: pd.DataFrame, label: str, numeric: list[str], categorical: list[str], *, recent_weight: bool = False) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    if recent_weight:
        pipe.fit(train, train[label].astype(int), model__sample_weight=_sample_weight(train))
    else:
        pipe.fit(train, train[label].astype(int))
    return pipe


def _eval(valid: pd.DataFrame, prob: np.ndarray, label: str) -> dict[str, Any]:
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    return {
        "auc": _safe_float(roc_auc_score(valid[label].astype(int), prob)) if valid[label].nunique() >= 2 else None,
        "top30_label_rate": _safe_float(top[label].mean()) if not top.empty else None,
        "bottom30_label_rate": _safe_float(bottom[label].mean()) if not bottom.empty else None,
        "top30_avg_next_rank_delta": _safe_float(pd.to_numeric(top.get("next_rank_delta"), errors="coerce").mean()) if not top.empty else None,
        "bottom30_avg_next_rank_delta": _safe_float(pd.to_numeric(bottom.get("next_rank_delta"), errors="coerce").mean()) if not bottom.empty else None,
        "top30_drop_rate": _safe_float(pd.to_numeric(top.get("dropped_next_rebalance"), errors="coerce").mean()) if not top.empty else None,
        "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()) if not top.empty else None,
        "bottom30_avg_1m_return": _safe_float(pd.to_numeric(bottom.get("fwd_ret_1m"), errors="coerce").mean()) if not bottom.empty else None,
        "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()) if not top.empty else None,
    }


def _split_rank_decision(row: pd.Series) -> str:
    drop_prob = _safe_float(row.get("rank_drop_prob"))
    rank_score = _safe_float(row.get("retained_rank_change_score"))
    if drop_prob is not None:
        if drop_prob >= 0.70:
            return "rank_drop_candidate"
        if drop_prob >= 0.50:
            return "rank_drop_watch"
    if rank_score is None:
        return "rank_observe"
    if rank_score >= 0.25:
        return "rank_upgrade_candidate"
    if rank_score >= 0.10:
        return "rank_upgrade_watch"
    if rank_score <= -0.25:
        return "rank_downgrade_candidate"
    if rank_score <= -0.10:
        return "rank_downgrade_watch"
    return "rank_hold"


def _current_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "is_current" in out.columns:
        current = out[pd.to_numeric(out["is_current"], errors="coerce").fillna(0).astype(int).eq(1)].copy()
        if not current.empty:
            out = current
    key_cols = [col for col in ["scope_key", "model_id", "ticker"] if col in out.columns]
    return out.sort_values("event_date").drop_duplicates(key_cols, keep="last").copy()


def _json_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (int, float, np.floating)):
        return _safe_float(value)
    if pd.isna(value):
        return None
    return value


def _rows(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict(orient="records")]


def build_candidate_rank_delta_ai(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    mart = _read_mart(asof)
    labels = list(MODEL_LABELS.values())
    numeric: list[str] = []
    categorical: list[str] = []
    models: dict[str, Pipeline] = {}
    evaluations: list[dict[str, Any]] = []
    for label in labels:
        train, valid = _split(mart, train_end, valid_start, asof, label)
        if not numeric and not categorical:
            numeric, categorical = _feature_columns(train)
        model = _fit(train, label, numeric, categorical, recent_weight=True)
        models[label] = model
        prob = model.predict_proba(valid)[:, 1]
        evaluations.append(
            {
                "label": label,
                "head": next((name for name, model_label in MODEL_LABELS.items() if model_label == label), label),
                "training_weight": "recent_1y_x3",
                "train_rows": int(len(train)),
                "valid_rows": int(len(valid)),
                "train_positive_rate": _safe_float(train[label].mean()),
                "valid_positive_rate": _safe_float(valid[label].mean()),
                **_eval(valid, prob, label),
            }
        )

    token = asof.replace("-", "")
    model_version = f"{MODEL_CODE}_{token}_001"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"{model_version}.joblib"
    tmp_path = model_path.with_name(f"{model_path.name}.tmp")
    joblib.dump(
        {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KO,
            "model_version": model_version,
            "source_model_code": SOURCE_MODEL_CODE,
            "numeric_features": numeric,
            "categorical_features": categorical,
            "model_structure": "split_drop_and_retained_rank_change",
            "labels": MODEL_LABELS,
            "models": models,
        },
        tmp_path,
    )
    tmp_path.replace(model_path)

    current = _current_rows(mart)
    current["rank_drop_prob"] = models[MODEL_LABELS["drop"]].predict_proba(current)[:, 1]
    current["retained_rank_upgrade_prob"] = models[MODEL_LABELS["retained_upgrade"]].predict_proba(current)[:, 1]
    current["retained_rank_downgrade_prob"] = models[MODEL_LABELS["retained_downgrade"]].predict_proba(current)[:, 1]
    current["retained_rank_change_score"] = current["retained_rank_upgrade_prob"] - current["retained_rank_downgrade_prob"]
    current["rank_delta_score"] = (1.0 - current["rank_drop_prob"]) * current["retained_rank_change_score"]
    current["rank_delta_decision"] = current.apply(_split_rank_decision, axis=1)
    current["model_code"] = MODEL_CODE
    current["model_name_ko"] = MODEL_NAME_KO
    current["model_version"] = model_version
    current["as_of_date"] = asof

    keep_cols = [
        "model_code",
        "model_name_ko",
        "model_version",
        "as_of_date",
        "scope_key",
        "model_id",
        "ticker",
        "name",
        "event_date",
        "candidate_bucket",
        "rank_no",
        "score",
        "rank_drop_prob",
        "retained_rank_upgrade_prob",
        "retained_rank_downgrade_prob",
        "retained_rank_change_score",
        "rank_delta_score",
        "rank_delta_decision",
        "ret_20d",
        "vol_20d",
        "mdd_20d",
        "trading_value_20d",
        "theme_bucket",
        "sector_bucket",
    ]
    current_out = current[[col for col in keep_cols if col in current.columns]].sort_values(
        ["rank_drop_prob", "rank_delta_score", "scope_key", "model_id"], ascending=[False, False, True, True]
    )
    decision_counts = current_out.groupby("rank_delta_decision", as_index=False).size().rename(columns={"size": "count"})

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    detail_path = REPORT_DIR / f"candidate_rank_delta_ai_current_scores_{token}.csv"
    eval_path = REPORT_DIR / f"candidate_rank_delta_ai_eval_{token}.json"
    md_path = REPORT_DIR / f"candidate_rank_delta_ai_eval_{token}.md"
    current_json_path = ADMIN_CURRENT_DIR / "candidate_rank_delta_ai_current.json"

    current_out.to_csv(detail_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "candidate_rank_delta_ai_current",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "model_version": model_version,
        "model_role": "candidate_rank_delta_shadow",
        "source_model_code": SOURCE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_structure": "split_drop_and_retained_rank_change",
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d via candidate validation mart when available",
        "optimization_priority": "return_first",
        "target": {
            "drop": "candidate drops out at the next rebalance",
            "retained_upgrade": "among retained candidates, next rebalance rank improves by at least 3 places",
            "retained_downgrade": "among retained candidates, next rebalance rank worsens by at least 3 places",
            "retained_rank_change_score": "retained_rank_upgrade_prob - retained_rank_downgrade_prob",
            "rank_delta_score": "(1 - rank_drop_prob) * retained_rank_change_score",
        },
        "thresholds": {
            "rank_drop_candidate": "rank_drop_prob >= 0.70",
            "rank_drop_watch": "0.50 <= rank_drop_prob < 0.70",
            "rank_upgrade_candidate": "retained_rank_change_score >= 0.25 and rank_drop_prob < 0.50",
            "rank_upgrade_watch": "0.10 <= retained_rank_change_score < 0.25 and rank_drop_prob < 0.50",
            "rank_hold": "-0.10 < retained_rank_change_score < 0.10 and rank_drop_prob < 0.50",
            "rank_downgrade_watch": "-0.25 < retained_rank_change_score <= -0.10 and rank_drop_prob < 0.50",
            "rank_downgrade_candidate": "retained_rank_change_score <= -0.25 and rank_drop_prob < 0.50",
        },
        "evaluation": evaluations,
        "decision_counts": _rows(decision_counts),
        "top_drop_candidates": _rows(current_out.sort_values("rank_drop_prob", ascending=False).head(100)),
        "top_upgrade_candidates": _rows(current_out.sort_values("retained_rank_change_score", ascending=False).head(100)),
        "top_downgrade_candidates": _rows(current_out.sort_values("retained_rank_change_score", ascending=True).head(100)),
        "outputs": {
            "model_path": str(model_path),
            "detail_csv": str(detail_path),
            "eval_json": str(eval_path),
            "admin_current_json": str(current_json_path),
        },
    }
    eval_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    current_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# {MODEL_CODE} Evaluation - {asof}",
                "",
                f"- Korean name: {MODEL_NAME_KO}",
                f"- Current score rows: {len(current_out):,}",
                "",
                "## Evaluation",
                "",
                *[
                    f"- {row['head']} / {row['label']}: AUC={row.get('auc')}, train={row.get('train_rows')}, valid={row.get('valid_rows')}, top30_label_rate={row.get('top30_label_rate')}"
                    for row in evaluations
                ],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI-CANDIDATE-RANK-DELTA-V01 candidate rank delta model.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = build_candidate_rank_delta_ai(args.asof, args.train_end, args.valid_start)
    print(json.dumps({"status": "ok", "model_code": MODEL_CODE, "as_of_date": args.asof, "rows": len(payload["top_upgrade_candidates"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
