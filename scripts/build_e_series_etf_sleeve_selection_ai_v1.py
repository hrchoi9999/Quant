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
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_e_series_etf_mart_v2 import build_e_series_mart_v2


REPORT_DIR = ROOT / r"reports\e_series_etf"
MODEL_DIR = ROOT / r"data\models\e_series_etf_sleeve_selection_ai"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

STRATEGY_MODEL_CODE = "E-ETF-V01"
MODEL_CODE = "AI-E-ETF-SLEEVE-SELECTION-V01"
MODEL_NAME_KO = "E시리즈 ETF슬리브선택AI"
TARGET_LABEL = "e_label_role_top3_1m_risk_adj"
FEATURE_MODE = "E_BASELINE"
RANDOM_STATE = 42

KEY_COLUMNS = {
    "signal_date",
    "feature_date",
    "ticker",
    "name",
    "strategy_family",
    "strategy_model_code",
}
LEAK_PREFIXES = ("label_", "e_label_", "fwd_", "path_mdd_", "risk_adj_")
FEATURE_PREFIXES = ("e_", "ret_", "vol_", "dd_", "dist_", "ma", "rsi", "liquidity_", "etf_metric_")
CATEGORICAL_FEATURES = (
    "e_series_role",
    "e_market_mode",
    "e_region_bucket",
    "e_asset_bucket",
    "e_strategy_bucket",
    "e_theme_bucket",
    "e_product_structure",
    "e_taxonomy_review_flag",
    "asset_class",
    "group_key",
    "currency_exposure",
)


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _safe_float(value: Any, digits: int = 6) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), digits)
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


def _records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    use = df.head(limit) if limit is not None else df
    return [{key: _json_value(value) for key, value in row.items()} for row in use.to_dict("records")]


def _load_or_build_mart(asof: str, rebuild_mart: bool) -> pd.DataFrame:
    token = _token(asof)
    path = REPORT_DIR / f"e_series_etf_mart_v2_{token}.csv"
    if rebuild_mart or not path.exists():
        build_e_series_mart_v2(asof)
    mart = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    mart["ticker"] = mart["ticker"].astype(str).str.zfill(6)
    mart["signal_date"] = pd.to_datetime(mart["signal_date"], errors="coerce")
    return mart


def _is_leak(col: str) -> bool:
    if col in KEY_COLUMNS:
        return True
    if col.startswith(LEAK_PREFIXES):
        return True
    if col.startswith("end_date_"):
        return True
    return False


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    categorical_set = set(CATEGORICAL_FEATURES)
    for col in df.columns:
        if _is_leak(col):
            continue
        if col in categorical_set and df[col].notna().any():
            categorical.append(col)
            continue
        if not col.startswith(FEATURE_PREFIXES):
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().sum() == 0:
            continue
        if pd.api.types.is_numeric_dtype(df[col]) or values.notna().mean() > 0.8:
            numeric.append(col)
    return sorted(set(numeric)), sorted(set(categorical))


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


def _fit(train: pd.DataFrame, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(random_state=RANDOM_STATE, n_estimators=160, max_depth=3)
    return Pipeline([("preprocess", _preprocessor(numeric, categorical)), ("model", model)]).fit(
        train[numeric + categorical],
        train["_target"],
    )


def _top_stats(scored: pd.DataFrame, n: int) -> dict[str, Any]:
    top = scored.sort_values(["signal_date", "sleeve_selection_prob"], ascending=[True, False]).groupby("signal_date").head(n)
    if top.empty:
        return {}
    return {
        f"top{n}_label_rate": _safe_float(top["_target"].mean()),
        f"top{n}_avg_risk_adj_1m": _safe_float(pd.to_numeric(top.get("risk_adj_1m"), errors="coerce").mean()),
        f"top{n}_avg_fwd_ret_1m": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()),
    }


def _role_summary(scored: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for role, frame in scored.groupby("e_series_role", dropna=False):
        if frame.empty or frame["_target"].nunique() < 2:
            auc = np.nan
        else:
            auc = roc_auc_score(frame["_target"], frame["sleeve_selection_prob"])
        row = {
            "e_series_role": role,
            "valid_rows": int(len(frame)),
            "valid_dates": int(frame["signal_date"].nunique()),
            "positive_rate": _safe_float(frame["_target"].mean()),
            "auc": _safe_float(auc),
        }
        for n in [1, 3, 5]:
            row.update(_top_stats(frame, n))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["auc", "e_series_role"], ascending=[False, True], na_position="last")


def _score_current(model: Pipeline, current: pd.DataFrame, numeric: list[str], categorical: list[str]) -> pd.DataFrame:
    out = current.copy()
    out["sleeve_selection_prob"] = model.predict_proba(out[numeric + categorical])[:, 1] if not out.empty else np.nan
    out["sleeve_selection_rank_in_role"] = out.groupby("e_series_role")["sleeve_selection_prob"].rank(
        method="first", ascending=False
    )
    out["sleeve_selection_rank_overall"] = out["sleeve_selection_prob"].rank(method="first", ascending=False)
    return out.sort_values(["e_series_role", "sleeve_selection_rank_in_role", "ticker"])


def train_model(asof: str, train_end: str, valid_start: str, rebuild_mart: bool) -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    token = _token(asof)
    mart = _load_or_build_mart(asof, rebuild_mart)
    if TARGET_LABEL not in mart.columns:
        raise SystemExit(f"missing target label: {TARGET_LABEL}")

    labeled = mart[mart[TARGET_LABEL].notna()].copy()
    labeled["_target"] = pd.to_numeric(labeled[TARGET_LABEL], errors="coerce")
    labeled = labeled[labeled["_target"].isin([0, 1])].copy()
    train = labeled[labeled["signal_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["signal_date"] >= pd.Timestamp(valid_start)) & (labeled["signal_date"] <= pd.Timestamp(asof))].copy()
    if train.empty or valid.empty or train["_target"].nunique() < 2 or valid["_target"].nunique() < 2:
        raise SystemExit("insufficient train/valid rows for E-series sleeve selection AI")

    numeric, categorical = _feature_columns(labeled)
    model = _fit(train, numeric, categorical)
    valid = valid.copy()
    valid["sleeve_selection_prob"] = model.predict_proba(valid[numeric + categorical])[:, 1]
    valid["sleeve_selection_pred"] = (valid["sleeve_selection_prob"] >= 0.5).astype(int)
    auc = roc_auc_score(valid["_target"], valid["sleeve_selection_prob"])
    accuracy = accuracy_score(valid["_target"], valid["sleeve_selection_pred"])
    role_perf = _role_summary(valid)

    current = mart[mart["signal_date"].eq(pd.Timestamp(asof))].copy()
    current_scores = _score_current(model, current, numeric, categorical)

    model_version = f"{MODEL_CODE}_{token}_001"
    model_path = MODEL_DIR / f"{model_version}.joblib"
    metadata_path = MODEL_DIR / f"{model_version}_metadata.json"
    scored_path = REPORT_DIR / f"e_series_etf_sleeve_selection_current_scores_{token}.csv"
    valid_scored_path = REPORT_DIR / f"e_series_etf_sleeve_selection_valid_scored_{token}.csv"
    role_perf_path = REPORT_DIR / f"e_series_etf_sleeve_selection_role_perf_{token}.csv"
    json_path = REPORT_DIR / f"e_series_etf_sleeve_selection_ai_v1_{token}.json"
    md_path = REPORT_DIR / f"e_series_etf_sleeve_selection_ai_v1_{token}.md"
    current_payload_path = ADMIN_CURRENT_DIR / "e_series_etf_sleeve_selection_current.json"

    bundle = {
        "model": model,
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "model_version": model_version,
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "target_label": TARGET_LABEL,
        "feature_mode": FEATURE_MODE,
        "numeric_features": numeric,
        "categorical_features": categorical,
        "train_end": train_end,
        "valid_start": valid_start,
        "as_of_date": asof,
    }
    joblib.dump(bundle, model_path)

    keep_cols = [
        "signal_date",
        "ticker",
        "name",
        "e_series_role",
        "e_market_mode",
        "e_region_bucket",
        "e_asset_bucket",
        "e_strategy_bucket",
        "e_theme_bucket",
        "e_product_structure",
        "e_taxonomy_confidence",
        "e_taxonomy_review_flag",
        "sleeve_selection_prob",
        "sleeve_selection_rank_in_role",
        "sleeve_selection_rank_overall",
        "e_baseline_selection_score",
        "e_baseline_rank_in_role",
        "e_quality_score",
        "e_momentum_score",
        "e_risk_control_score",
    ]
    current_scores[[c for c in keep_cols if c in current_scores.columns]].to_csv(
        scored_path, index=False, encoding="utf-8-sig"
    )
    valid_cols = [
        "signal_date",
        "ticker",
        "name",
        "e_series_role",
        "_target",
        "sleeve_selection_prob",
        "sleeve_selection_pred",
        "risk_adj_1m",
        "fwd_ret_1m",
    ]
    valid[[c for c in valid_cols if c in valid.columns]].to_csv(valid_scored_path, index=False, encoding="utf-8-sig")
    role_perf.to_csv(role_perf_path, index=False, encoding="utf-8-sig")

    summary = {
        "status": "ok",
        "source_name": "e_series_etf_sleeve_selection_ai_v1",
        "strategy_model_code": STRATEGY_MODEL_CODE,
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "model_version": model_version,
        "target_label": TARGET_LABEL,
        "feature_mode": FEATURE_MODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d",
        "optimization_priority": "return_first_with_role_risk_controls",
        "train_end": train_end,
        "valid_start": valid_start,
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "valid_dates": int(valid["signal_date"].nunique()),
        "positive_rate_train": _safe_float(train["_target"].mean()),
        "positive_rate_valid": _safe_float(valid["_target"].mean()),
        "auc": _safe_float(auc),
        "accuracy": _safe_float(accuracy),
        "numeric_feature_count": len(numeric),
        "categorical_feature_count": len(categorical),
        "categorical_features": categorical,
        "taxonomy_features": [
            col
            for col in numeric + categorical
            if col.startswith("e_") and ("bucket" in col or "structure" in col or "taxonomy" in col)
        ],
        "top_stats": {**_top_stats(valid, 1), **_top_stats(valid, 3), **_top_stats(valid, 5)},
        "role_performance": _records(role_perf),
        "current_top_by_role": _records(
            current_scores[current_scores["sleeve_selection_rank_in_role"].le(5)][
                [c for c in keep_cols if c in current_scores.columns]
            ].sort_values(["e_series_role", "sleeve_selection_rank_in_role"])
        ),
        "outputs": {
            "model": str(model_path),
            "metadata": str(metadata_path),
            "current_scores_csv": str(scored_path),
            "valid_scored_csv": str(valid_scored_path),
            "role_perf_csv": str(role_perf_path),
            "json": str(json_path),
            "markdown": str(md_path),
            "admin_current_json": str(current_payload_path),
        },
    }
    metadata_path.write_text(json.dumps({k: v for k, v in summary.items() if k != "current_top_by_role"}, ensure_ascii=False, indent=2), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    current_payload_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, summary)
    return summary


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# E Series ETF Sleeve Selection AI V1",
        "",
        f"- strategy model: `{payload['strategy_model_code']}`",
        f"- model: `{payload['model_code']}` ({payload['model_name_ko']})",
        f"- target: `{payload['target_label']}`",
        f"- feature mode: `{payload['feature_mode']}`",
        f"- as-of: `{payload['as_of_date']}`",
        "",
        "## Validation",
        "",
        f"- AUC: {payload['auc']:.3f}",
        f"- accuracy: {payload['accuracy']:.3f}",
        f"- top1 label rate: {payload['top_stats'].get('top1_label_rate'):.2%}",
        f"- top3 label rate: {payload['top_stats'].get('top3_label_rate'):.2%}",
        f"- top3 avg risk-adjusted 1M: {payload['top_stats'].get('top3_avg_risk_adj_1m'):.2%}",
        "",
        "## Role Performance",
        "",
        "| role | AUC | top3 hit | top3 risk adj | rows |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["role_performance"]:
        auc = "" if row.get("auc") is None else f"{row['auc']:.3f}"
        hit = "" if row.get("top3_label_rate") is None else f"{row['top3_label_rate']:.2%}"
        risk = "" if row.get("top3_avg_risk_adj_1m") is None else f"{row['top3_avg_risk_adj_1m']:.2%}"
        lines.append(f"| {row['e_series_role']} | {auc} | {hit} | {risk} | {row['valid_rows']} |")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- `{payload['outputs']['model']}`",
            f"- `{payload['outputs']['current_scores_csv']}`",
            f"- `{payload['outputs']['admin_current_json']}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train E-series ETF Sleeve Selection AI V1.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--rebuild-mart", action="store_true")
    args = parser.parse_args()
    payload = train_model(
        asof=str(args.asof),
        train_end=str(args.train_end),
        valid_start=str(args.valid_start),
        rebuild_mart=bool(args.rebuild_mart),
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "model_code": payload["model_code"],
                "model_version": payload["model_version"],
                "as_of_date": payload["as_of_date"],
                "auc": payload["auc"],
                "top_stats": payload["top_stats"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
