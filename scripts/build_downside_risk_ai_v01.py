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

ROOT = Path(r"D:\Quant")
SOURCE_DIR = ROOT / r"reports\ai_overlay_v01"
REPORT_DIR = ROOT / r"reports\downside_risk_ai_v01"
MODEL_DIR = ROOT / r"data\models\downside_risk_ai"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

MODEL_CODE = "AI-DOWNSIDE-RISK-V01"
MODEL_NAME_KO = "하락위험예측AI"
SOURCE_MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
RANDOM_STATE = 42

KEY_COLUMNS = {
    "scope_key",
    "model_id",
    "ticker",
    "name",
    "event_date",
    "week_end",
    "live_start_date",
    "scored_at",
}
FORWARD_PREFIXES = ("fwd_", "label_", "has_")
EXCLUDED_NUMERIC = {"is_current", "is_live_event"}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"missing input file: {path}")
    return pd.read_csv(path, dtype={"ticker": str}, low_memory=False)


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    blocked = set(KEY_COLUMNS)
    numeric: list[str] = []
    categorical: list[str] = []
    for col in df.columns:
        if col in blocked or col in EXCLUDED_NUMERIC or col.startswith(FORWARD_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            if df[col].notna().any():
                numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _add_downside_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ret = pd.to_numeric(out.get("fwd_ret_1m"), errors="coerce")
    mdd = pd.to_numeric(out.get("fwd_mdd_1m"), errors="coerce")
    median_ret_by_date = out.assign(_ret=ret).groupby("event_date")["_ret"].transform("median")
    excess_ret = ret - median_ret_by_date
    out["label_excess_m5_or_mdd12"] = np.where(
        ret.notna(),
        ((excess_ret <= -0.05) | (mdd.fillna(0) <= -0.12)).astype(int),
        np.nan,
    )
    if "label_bad_1m_strict" in out.columns:
        out["label_downside_1m"] = pd.to_numeric(out["label_bad_1m_strict"], errors="coerce")
    else:
        out["label_downside_1m"] = np.where(ret.notna(), ((ret <= -0.03) | (mdd.fillna(0) <= -0.15)).astype(int), np.nan)
    if "label_risk_1m" not in out.columns:
        out["label_risk_1m"] = np.where(ret.notna(), ((ret < 0) | (mdd.fillna(0) <= -0.15)).astype(int), np.nan)
    return out


def _stock_scope(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "asset_type" in out.columns:
        asset = out["asset_type"].astype(str).str.upper()
        out = out[~asset.str.contains("ETF", na=False)].copy()
    return out


def _preprocessor(df: pd.DataFrame, numeric: list[str], categorical: list[str]) -> ColumnTransformer:
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


def _fit_classifier(train: pd.DataFrame, numeric: list[str], categorical: list[str], label: str) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(train, numeric, categorical)), ("model", model)])
    pipe.fit(train, train[label].astype(int))
    return pipe


def _time_split(df: pd.DataFrame, train_end: str, valid_start: str, valid_end: str, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[label].notna()].copy()
    labeled["event_date"] = pd.to_datetime(labeled["event_date"], errors="coerce")
    labeled = labeled[labeled["event_date"].notna()].sort_values("event_date")
    train = labeled[labeled["event_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["event_date"] >= pd.Timestamp(valid_start)) & (labeled["event_date"] <= pd.Timestamp(valid_end))].copy()
    if len(train) >= 200 and len(valid) >= 50 and train[label].nunique() >= 2 and valid[label].nunique() >= 2:
        return train, valid
    dates = sorted(labeled["event_date"].dropna().unique())
    if len(dates) < 5:
        raise SystemExit("insufficient dated labels for downside risk AI")
    cut = dates[max(1, int(len(dates) * 0.80)) - 1]
    train = labeled[labeled["event_date"] <= cut].copy()
    valid = labeled[labeled["event_date"] > cut].copy()
    return train, valid


def _eval_predictions(valid: pd.DataFrame, prob: np.ndarray, label: str) -> dict[str, Any]:
    scored = valid.copy()
    scored["downside_risk_prob"] = prob
    top = scored.sort_values("downside_risk_prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("downside_risk_prob", ascending=True).head(min(30, len(scored)))
    auc = None
    if valid[label].nunique() >= 2:
        auc = round(float(roc_auc_score(valid[label].astype(int), prob)), 6)
    return {
        "auc": auc,
        "top30_actual_downside_rate": _safe_float(top[label].mean()) if not top.empty else None,
        "bottom30_actual_downside_rate": _safe_float(bottom[label].mean()) if not bottom.empty else None,
        "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()) if not top.empty else None,
        "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()) if not top.empty else None,
        "bottom30_avg_1m_return": _safe_float(pd.to_numeric(bottom.get("fwd_ret_1m"), errors="coerce").mean()) if not bottom.empty else None,
    }


def _risk_tag(prob: Any) -> str:
    value = _safe_float(prob)
    if value is None:
        return "risk_unknown"
    if value >= 0.70:
        return "risk_exit_watch"
    if value >= 0.60:
        return "risk_caution"
    if value >= 0.45:
        return "risk_watch"
    return "risk_clear"


def _action_hint(tag: str) -> str:
    return {
        "risk_exit_watch": "매도/비중축소 후보 관찰",
        "risk_caution": "비중축소 검토",
        "risk_watch": "관찰 필요",
        "risk_clear": "유지 가능",
    }.get(tag, "판단 보류")


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


def _current_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["event_date"] = pd.to_datetime(out["event_date"], errors="coerce")
    if "is_current" in out.columns:
        current = out[pd.to_numeric(out["is_current"], errors="coerce").fillna(0).astype(int).eq(1)].copy()
        if not current.empty:
            out = current
    key_cols = [col for col in ["scope_key", "model_id", "ticker"] if col in out.columns]
    return out.sort_values("event_date").drop_duplicates(key_cols, keep="last").copy()


def _rows(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    records = []
    for row in df.to_dict(orient="records"):
        records.append({key: _json_value(value) for key, value in row.items()})
    return records


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "(empty)"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in df.to_dict(orient="records"):
        lines.append("| " + " | ".join(str(_json_value(row.get(col)) or "") for col in cols) + " |")
    return "\n".join(lines)


def build_downside_risk_ai(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    token = asof.replace("-", "")
    mart = _read_csv(SOURCE_DIR / f"ai_overlay_training_mart_{token}.csv")
    mart["ticker"] = mart["ticker"].astype(str).str.zfill(6)
    mart = _stock_scope(_add_downside_labels(mart))
    label = "label_excess_m5_or_mdd12"
    train, valid = _time_split(mart, train_end, valid_start, asof, label)
    numeric, categorical = _feature_columns(train)
    if train.empty or valid.empty:
        raise SystemExit("empty train/valid split")
    if train[label].nunique() < 2:
        raise SystemExit("training label has one class only")

    model = _fit_classifier(train, numeric, categorical, label)
    valid_prob = model.predict_proba(valid)[:, 1]
    eval_payload = _eval_predictions(valid, valid_prob, label)
    model_version = f"{MODEL_CODE}_{token}_001"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"{model_version}.joblib"
    temp_path = model_path.with_name(f"{model_path.name}.tmp")
    joblib.dump(
        {
            "model_code": MODEL_CODE,
            "model_name_ko": MODEL_NAME_KO,
            "model_version": model_version,
            "source_model_code": SOURCE_MODEL_CODE,
            "label": label,
            "numeric_features": numeric,
            "categorical_features": categorical,
            "model": model,
        },
        temp_path,
    )
    temp_path.replace(model_path)

    current = _current_rows(mart)
    current["downside_risk_prob"] = model.predict_proba(current)[:, 1] if not current.empty else np.nan
    current["downside_risk_tag"] = current["downside_risk_prob"].map(_risk_tag)
    current["action_hint"] = current["downside_risk_tag"].map(_action_hint)
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
        "downside_risk_prob",
        "downside_risk_tag",
        "action_hint",
        "ret_20d",
        "vol_20d",
        "mdd_20d",
        "trading_value_20d",
        "theme_bucket",
        "sector_bucket",
    ]
    current_out = current[[col for col in keep_cols if col in current.columns]].sort_values(
        ["downside_risk_prob", "scope_key", "model_id"], ascending=[False, True, True]
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    detail_path = REPORT_DIR / f"downside_risk_ai_current_scores_{token}.csv"
    eval_path = REPORT_DIR / f"downside_risk_ai_eval_{token}.json"
    md_path = REPORT_DIR / f"downside_risk_ai_eval_{token}.md"
    current_json_path = ADMIN_CURRENT_DIR / "downside_risk_ai_current.json"

    current_out.to_csv(detail_path, index=False, encoding="utf-8-sig")
    tag_counts = current_out.groupby("downside_risk_tag", as_index=False).size().rename(columns={"size": "count"})
    payload = {
        "source_name": "downside_risk_ai_current",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "model_version": model_version,
        "model_role": "risk_overlay_shadow",
        "source_model_code": SOURCE_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "market_context_source": "QuantMarket handoff primary ridge calibration 20d via candidate validation mart when available",
        "optimization_priority": "return_first_with_downside_control",
        "scope_note": "주식 후보 대상. ETF는 AI-ETF 계열 별도 트랙에서 개발한다.",
        "target": {
            "label": label,
            "definition": "1M forward excess return proxy <= -5% or 1M forward MDD <= -12%",
            "excess_return_proxy": "ticker 1M forward return minus same event_date median 1M forward return",
        },
        "thresholds": {
            "risk_exit_watch": "prob >= 0.70",
            "risk_caution": "0.60 <= prob < 0.70",
            "risk_watch": "0.45 <= prob < 0.60",
            "risk_clear": "prob < 0.45",
        },
        "evaluation": {
            "train_rows": int(len(train)),
            "valid_rows": int(len(valid)),
            "train_start": str(train["event_date"].min().date()),
            "train_end": str(train["event_date"].max().date()),
            "valid_start": str(valid["event_date"].min().date()),
            "valid_end": str(valid["event_date"].max().date()),
            **eval_payload,
        },
        "tag_counts": _rows(tag_counts),
        "top_risk_candidates": _rows(current_out.head(100)),
        "outputs": {
            "model_path": str(model_path),
            "detail_csv": str(detail_path),
            "eval_json": str(eval_path),
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
                f"- Train rows: {len(train):,}",
                f"- Valid rows: {len(valid):,}",
                f"- AUC: {eval_payload.get('auc')}",
                f"- Top30 downside rate: {eval_payload.get('top30_actual_downside_rate')}",
                f"- Bottom30 downside rate: {eval_payload.get('bottom30_actual_downside_rate')}",
                f"- Current score rows: {len(current_out):,}",
                "",
                "## Tag Counts",
                "",
                _markdown_table(tag_counts),
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI-DOWNSIDE-RISK-V01 downside risk shadow model.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = build_downside_risk_ai(args.asof, args.train_end, args.valid_start)
    print(json.dumps({"status": "ok", "model_code": MODEL_CODE, "as_of_date": args.asof, "rows": len(payload.get("top_risk_candidates") or [])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
