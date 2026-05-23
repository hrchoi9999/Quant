from __future__ import annotations

import argparse
import json
import sys
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

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quant_market.market_handoff import market_context_frame

SOURCE_DIR = ROOT / r"reports\ai_overlay_v01"
REPORT_DIR = ROOT / r"reports\model_selection_ai_v01"
MODEL_DIR = ROOT / r"data\models\model_selection_ai"

MODEL_CODE = "AI-MODEL-SELECTION-V01"
MODEL_NAME_KO = "모델선택AI"
RANDOM_STATE = 42

KEY_COLUMNS = {"event_date", "scope_key", "model_id", "model_family"}
LABEL_COLUMNS = {
    "future_model_return_1m",
    "future_model_win_rate_1m",
    "future_model_rank_pct_1m",
    "label_model_top_tercile_1m",
}


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return _safe_float(value)
    if pd.isna(value):
        return None
    return value


def _json_records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    return [{key: _json_value(value) for key, value in row.items()} for row in df.to_dict(orient="records")]


def _model_family(model_id: Any) -> str:
    value = str(model_id or "").upper()
    if value in {"GROWTH", "BALANCED", "STABLE"}:
        return "USER"
    if value.startswith("S"):
        return "S"
    if value.startswith("T-ETF"):
        return "T_ETF"
    if value.startswith("T-"):
        return "T"
    if value.startswith("I-"):
        return "I"
    return "OTHER"


def _read_mart(asof: str) -> pd.DataFrame:
    path = SOURCE_DIR / f"ai_overlay_training_mart_{asof.replace('-', '')}.csv"
    if not path.exists():
        raise SystemExit(f"missing training mart: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df = df[df["event_date"].notna() & df["scope_key"].notna() & df["model_id"].notna()].copy()
    if "asset_type" in df.columns:
        df = df[~df["asset_type"].astype(str).str.upper().eq("ETF")].copy()
    return df


def _read_market_context() -> pd.DataFrame:
    df = market_context_frame(scope="ALL", date_col="event_date", prefix="qm_market_")
    if df.empty:
        return pd.DataFrame(columns=["event_date"])
    df["event_date"] = pd.to_datetime(df.get("event_date"), errors="coerce")
    return df[df["event_date"].notna()].copy()


def _model_level_frame(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [
        "rank_no",
        "score",
        "weight",
        "stage1_prob",
        "stage2_prob",
        "universe_rank_no",
        "universe_rank_score",
        "display_score",
        "model_overlap_count",
        "overlap_user_count",
        "overlap_internal_count",
        "overlap_tseries_count",
        "ret_5d",
        "ret_10d",
        "ret_20d",
        "ret_60d",
        "vol_20d",
        "mdd_20d",
        "trading_value_20d",
        "confidence_score",
        "annual_revenue_yoy",
        "annual_op_income_yoy",
        "half_revenue_yoy",
        "half_op_income_yoy",
        "q_revenue_yoy",
        "q_op_income_yoy",
        "q_revenue_yoy_delta_1q",
        "q_op_income_yoy_delta_1q",
        "pit_growth_score",
        "positive_relation_count",
        "negative_relation_count",
        "theme_support_score",
        "etf_support_score",
        "hedge_risk_score",
        "cluster_concentration_score",
        "c_overlay_score",
        "kiwoom_foreign_net_value_20d",
        "kiwoom_foreign_net_buy_days_20d",
        "kiwoom_institution_net_value_20d",
        "kiwoom_institution_net_buy_days_20d",
        "dart_events_90d",
        "dart_major_events_90d",
        "dart_days_since_last_event",
    ]
    for col in [*numeric_cols, "fwd_ret_1m"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    agg_spec: dict[str, tuple[str, str]] = {
        "candidate_count": ("ticker", "nunique"),
        "row_count": ("ticker", "size"),
        "future_model_return_1m": ("fwd_ret_1m", "mean"),
        "future_model_win_rate_1m": ("fwd_ret_1m", lambda s: float((s > 0).mean()) if s.notna().any() else np.nan),
    }
    agg_spec.update({f"avg_{col}": (col, "mean") for col in numeric_cols if col in df.columns})
    if "rank_no" in df.columns:
        agg_spec["min_rank_no"] = ("rank_no", "min")
    out = df.groupby(["event_date", "scope_key", "model_id"], as_index=False).agg(**agg_spec)
    out["model_family"] = out["model_id"].map(_model_family)

    peer_count = out.groupby("event_date")["model_id"].transform("nunique")
    out = out[peer_count >= 2].copy()
    out["future_model_rank_pct_1m"] = out.groupby("event_date")["future_model_return_1m"].rank(
        pct=True,
        ascending=False,
        method="first",
    )
    out["label_model_top_tercile_1m"] = np.where(
        out["future_model_return_1m"].notna(),
        (out["future_model_rank_pct_1m"] <= 0.34).astype(int),
        np.nan,
    )
    return out.sort_values(["scope_key", "model_id", "event_date"]).reset_index(drop=True)


def _add_trailing_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values(["scope_key", "model_id", "event_date"]).copy()
    groups = out.groupby(["scope_key", "model_id"], group_keys=False)
    base = pd.to_numeric(out["future_model_return_1m"], errors="coerce")
    win = pd.to_numeric(out["future_model_win_rate_1m"], errors="coerce")
    shifted_ret = base.groupby([out["scope_key"], out["model_id"]]).shift(1)
    shifted_win = win.groupby([out["scope_key"], out["model_id"]]).shift(1)
    out["trail_return_4"] = groups["future_model_return_1m"].transform(lambda s: s.shift(1).rolling(4, min_periods=2).mean())
    out["trail_return_8"] = groups["future_model_return_1m"].transform(lambda s: s.shift(1).rolling(8, min_periods=3).mean())
    out["trail_win_rate_4"] = groups["future_model_win_rate_1m"].transform(lambda s: s.shift(1).rolling(4, min_periods=2).mean())
    out["trail_win_rate_8"] = groups["future_model_win_rate_1m"].transform(lambda s: s.shift(1).rolling(8, min_periods=3).mean())
    out["prev_model_return_1m"] = shifted_ret
    out["prev_model_win_rate_1m"] = shifted_win
    return out


def _build_frame(asof: str) -> pd.DataFrame:
    mart = _read_mart(asof)
    frame = _model_level_frame(mart)
    frame = _add_trailing_features(frame)
    market = _read_market_context()
    if not market.empty:
        frame = frame.merge(market, on="event_date", how="left")
    return frame


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    for col in df.columns:
        if col in KEY_COLUMNS or col in LABEL_COLUMNS or col.startswith("future_") or col.startswith("label_"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _split(df: pd.DataFrame, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df["label_model_top_tercile_1m"].notna()].copy()
    train = labeled[labeled["event_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["event_date"] >= pd.Timestamp(valid_start)) & (labeled["event_date"] <= pd.Timestamp(valid_end))].copy()
    return train, valid


def _preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ],
        remainder="drop",
    )


def _fit(train: pd.DataFrame, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    max_date = train["event_date"].max()
    cutoff = max_date - pd.DateOffset(years=2)
    weight = np.ones(len(train), dtype=float)
    weight[train["event_date"].ge(cutoff).to_numpy()] = 2.0
    pipe.fit(train, train["label_model_top_tercile_1m"].astype(int), model__sample_weight=weight)
    return pipe


def _score_eval(valid: pd.DataFrame, prob: np.ndarray) -> dict[str, Any]:
    scored = valid.copy()
    scored["model_selection_prob"] = prob
    top = scored.sort_values("model_selection_prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("model_selection_prob", ascending=True).head(min(30, len(scored)))
    return {
        "auc": _safe_float(roc_auc_score(valid["label_model_top_tercile_1m"].astype(int), prob))
        if valid["label_model_top_tercile_1m"].nunique() >= 2
        else None,
        "valid_rows": int(len(valid)),
        "valid_positive_rate": _safe_float(valid["label_model_top_tercile_1m"].mean()),
        "top30_label_rate": _safe_float(top["label_model_top_tercile_1m"].mean()),
        "bottom30_label_rate": _safe_float(bottom["label_model_top_tercile_1m"].mean()),
        "top30_future_return_1m": _safe_float(top["future_model_return_1m"].mean()),
        "bottom30_future_return_1m": _safe_float(bottom["future_model_return_1m"].mean()),
    }


def run_experiment(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    frame = _build_frame(asof)
    train, valid = _split(frame, train_end, valid_start, asof)
    if train.empty or valid.empty or train["label_model_top_tercile_1m"].nunique() < 2 or valid["label_model_top_tercile_1m"].nunique() < 2:
        raise SystemExit(f"insufficient train/valid classes: train={len(train)}, valid={len(valid)}")
    numeric, categorical = _feature_columns(train)
    model = _fit(train, numeric, categorical)
    prob = model.predict_proba(valid)[:, 1]
    evaluation = _score_eval(valid, prob)

    current = frame[frame["event_date"] <= pd.Timestamp(asof)].sort_values("event_date").drop_duplicates(
        ["scope_key", "model_id"],
        keep="last",
    )
    current = current.copy()
    current["model_selection_prob"] = model.predict_proba(current)[:, 1]
    current["model_selection_rank"] = current["model_selection_prob"].rank(ascending=False, method="first").astype(int)
    current_out = current.sort_values("model_selection_prob", ascending=False)

    token = asof.replace("-", "")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    result_csv = REPORT_DIR / f"model_selection_ai_experiment_{token}.csv"
    current_csv = REPORT_DIR / f"model_selection_ai_current_scores_{token}.csv"
    json_path = REPORT_DIR / f"model_selection_ai_experiment_{token}.json"
    md_path = REPORT_DIR / f"model_selection_ai_experiment_{token}.md"
    model_path = MODEL_DIR / f"{MODEL_CODE}_{token}_001.joblib"

    current_out.to_csv(current_csv, index=False, encoding="utf-8-sig")
    valid_scored = valid.copy()
    valid_scored["model_selection_prob"] = prob
    valid_scored.to_csv(result_csv, index=False, encoding="utf-8-sig")
    joblib.dump(
        {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KO,
            "numeric_features": numeric,
            "categorical_features": categorical,
            "target": "label_model_top_tercile_1m",
            "model": model,
        },
        model_path,
    )

    payload = {
        "source_name": "model_selection_ai_experiment",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target": "Per event_date, model is top tercile by next 1M average candidate return.",
        "scope": "stock strategy models only; ETF excluded",
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d",
        "optimization_priority": "return_first",
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "numeric_feature_count": len(numeric),
        "categorical_feature_count": len(categorical),
        "evaluation": evaluation,
        "current_top_models": _json_records(current_out, 20),
        "outputs": {
            "valid_scored_csv": str(result_csv),
            "current_scores_csv": str(current_csv),
            "model_path": str(model_path),
            "json": str(json_path),
            "md": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# {MODEL_CODE} Experiment - {asof}",
                "",
                f"- Korean name: {MODEL_NAME_KO}",
                "- Scope: stock strategy models only; ETF excluded",
                "- Target: top tercile by next 1M average candidate return within the same event date",
                f"- Train rows: {len(train):,}",
                f"- Valid rows: {len(valid):,}",
                "",
                "## Evaluation",
                "",
                f"- AUC: {evaluation.get('auc')}",
                f"- Top30 label rate: {evaluation.get('top30_label_rate')}",
                f"- Bottom30 label rate: {evaluation.get('bottom30_label_rate')}",
                f"- Top30 future return 1M: {evaluation.get('top30_future_return_1m')}",
                f"- Bottom30 future return 1M: {evaluation.get('bottom30_future_return_1m')}",
                "",
                "## Current Top Models",
                "",
                *[
                    f"- {row.get('scope_key')} / {row.get('model_id')}: prob={_safe_float(row.get('model_selection_prob'))}, candidates={int(row.get('candidate_count') or 0)}"
                    for row in current_out.head(10).to_dict(orient="records")
                ],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI-MODEL-SELECTION-V01 baseline experiment.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_experiment(args.asof, args.train_end, args.valid_start)
    print(
        json.dumps(
            {
                "status": "ok",
                "model_code": MODEL_CODE,
                "as_of_date": args.asof,
                "evaluation": payload["evaluation"],
                "top_models": [
                    {
                        "scope_key": row.get("scope_key"),
                        "model_id": row.get("model_id"),
                        "model_selection_prob": _safe_float(row.get("model_selection_prob")),
                    }
                    for row in payload["current_top_models"][:5]
                ],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
