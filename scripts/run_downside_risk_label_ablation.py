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

ROOT = Path(r"D:\Quant")
SOURCE_DIR = ROOT / r"reports\ai_overlay_v01"
REPORT_DIR = ROOT / r"reports\downside_risk_ai_v01"
RANDOM_STATE = 42

KEY_COLUMNS = {
    "scope_key",
    "model_id",
    "ticker",
    "name",
    "event_date",
    "week_end",
    "live_start_date",
}
FORWARD_PREFIXES = ("fwd_", "label_", "has_")
EXCLUDED_NUMERIC = {"is_current", "is_live_event"}

LABEL_SPECS: list[dict[str, Any]] = [
    {
        "label": "risk_current_bad_strict",
        "description": "existing label_bad_1m_strict",
        "mode": "existing",
        "source_col": "label_bad_1m_strict",
    },
    {
        "label": "risk_return_neg_or_mdd15",
        "description": "ret < 0 or mdd <= -15%",
        "ret_op": "<",
        "ret_th": 0.0,
        "mdd_th": -0.15,
        "logic": "or",
    },
    {
        "label": "risk_return_m3_or_mdd15",
        "description": "ret <= -3% or mdd <= -15%",
        "ret_op": "<=",
        "ret_th": -0.03,
        "mdd_th": -0.15,
        "logic": "or",
    },
    {
        "label": "risk_return_m5_or_mdd12",
        "description": "ret <= -5% or mdd <= -12%",
        "ret_op": "<=",
        "ret_th": -0.05,
        "mdd_th": -0.12,
        "logic": "or",
    },
    {
        "label": "risk_return_m5_or_mdd15",
        "description": "ret <= -5% or mdd <= -15%",
        "ret_op": "<=",
        "ret_th": -0.05,
        "mdd_th": -0.15,
        "logic": "or",
    },
    {
        "label": "risk_return_neg_and_mdd10",
        "description": "ret < 0 and mdd <= -10%",
        "ret_op": "<",
        "ret_th": 0.0,
        "mdd_th": -0.10,
        "logic": "and",
    },
    {
        "label": "risk_return_m3_and_mdd10",
        "description": "ret <= -3% and mdd <= -10%",
        "ret_op": "<=",
        "ret_th": -0.03,
        "mdd_th": -0.10,
        "logic": "and",
    },
    {
        "label": "risk_excess_m5_or_mdd12",
        "description": "excess proxy <= -5% or mdd <= -12%",
        "ret_op": "<=",
        "ret_th": -0.05,
        "mdd_th": -0.12,
        "logic": "or",
        "use_excess_proxy": True,
    },
]
LABEL_NAMES = {str(spec["label"]) for spec in LABEL_SPECS}


def _read_mart(asof: str) -> pd.DataFrame:
    path = SOURCE_DIR / f"ai_overlay_training_mart_{asof.replace('-', '')}.csv"
    if not path.exists():
        raise SystemExit(f"missing mart: {path}")
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    if "asset_type" in df.columns:
        asset = df["asset_type"].astype(str).str.upper()
        df = df[~asset.str.contains("ETF", na=False)].copy()
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    return df[df["event_date"].notna()].copy()


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    for col in df.columns:
        if col in KEY_COLUMNS or col in EXCLUDED_NUMERIC or col in LABEL_NAMES or col.startswith(FORWARD_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            if df[col].notna().any():
                numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _compare_ret(ret: pd.Series, op: str, threshold: float) -> pd.Series:
    return ret < threshold if op == "<" else ret <= threshold


def _build_label(df: pd.DataFrame, spec: dict[str, Any]) -> pd.Series:
    if spec.get("mode") == "existing":
        return pd.to_numeric(df.get(str(spec["source_col"])), errors="coerce")
    ret = pd.to_numeric(df.get("fwd_ret_1m"), errors="coerce")
    if spec.get("use_excess_proxy"):
        by_date = df.assign(_ret=ret).groupby("event_date")["_ret"].transform("median")
        ret = ret - by_date
    mdd = pd.to_numeric(df.get("fwd_mdd_1m"), errors="coerce")
    ret_hit = _compare_ret(ret, str(spec.get("ret_op", "<=")), float(spec["ret_th"]))
    mdd_hit = mdd <= float(spec["mdd_th"])
    if spec.get("logic") == "and":
        hit = ret_hit & mdd_hit
    else:
        hit = ret_hit | mdd_hit
    return np.where(ret.notna(), hit.astype(int), np.nan)


def _split(df: pd.DataFrame, label: str, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def _fit(train: pd.DataFrame, label: str, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=160, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    pipe.fit(train, train[label].astype(int))
    return pipe


def _safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def run_ablation(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    base = _read_mart(asof)
    rows: list[dict[str, Any]] = []
    for spec in LABEL_SPECS:
        label = str(spec["label"])
        df = base.copy()
        df[label] = _build_label(df, spec)
        train, valid = _split(df, label, train_end, valid_start, asof)
        numeric, categorical = _feature_columns(train)
        row: dict[str, Any] = {
            "label": label,
            "description": spec["description"],
            "train_rows": int(len(train)),
            "valid_rows": int(len(valid)),
            "train_positive_rate": _safe_float(train[label].mean()) if not train.empty else None,
            "valid_positive_rate": _safe_float(valid[label].mean()) if not valid.empty else None,
            "status": "ok",
        }
        if train.empty or valid.empty or train[label].nunique() < 2 or valid[label].nunique() < 2:
            row["status"] = "skipped"
            row["reason"] = "insufficient_rows_or_one_class"
            rows.append(row)
            continue
        model = _fit(train, label, numeric, categorical)
        prob = model.predict_proba(valid)[:, 1]
        scored = valid.copy()
        scored["prob"] = prob
        top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
        bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
        row.update(
            {
                "auc": _safe_float(roc_auc_score(valid[label].astype(int), prob)),
                "top30_positive_rate": _safe_float(top[label].mean()),
                "bottom30_positive_rate": _safe_float(bottom[label].mean()),
                "top_bottom_positive_spread": _safe_float(top[label].mean() - bottom[label].mean()),
                "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()),
                "bottom30_avg_1m_return": _safe_float(pd.to_numeric(bottom.get("fwd_ret_1m"), errors="coerce").mean()),
                "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()),
            }
        )
        rows.append(row)

    result = pd.DataFrame(rows).sort_values(["auc", "top_bottom_positive_spread"], ascending=False, na_position="last")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    csv_path = REPORT_DIR / f"downside_risk_label_ablation_{token}.csv"
    json_path = REPORT_DIR / f"downside_risk_label_ablation_{token}.json"
    md_path = REPORT_DIR / f"downside_risk_label_ablation_{token}.md"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "downside_risk_label_ablation",
        "model_code": "AI-DOWNSIDE-RISK-V01",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "train_end": train_end,
        "valid_start": valid_start,
        "results": result.where(pd.notna(result), None).to_dict(orient="records"),
        "outputs": {"csv": str(csv_path), "json": str(json_path), "md": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# Downside Risk Label Ablation - {asof}",
                "",
                "| label | auc | train_pos | valid_pos | top30_pos | bottom30_pos | top30_ret | top30_mdd |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
                *[
                    "| {label} | {auc} | {train_positive_rate} | {valid_positive_rate} | {top30_positive_rate} | {bottom30_positive_rate} | {top30_avg_1m_return} | {top30_avg_1m_mdd} |".format(
                        **{k: "" if pd.isna(v) else v for k, v in row.items()}
                    )
                    for row in result.to_dict(orient="records")
                ],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run label ablation for AI-DOWNSIDE-RISK-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_ablation(args.asof, args.train_end, args.valid_start)
    best = payload["results"][0] if payload["results"] else {}
    print(json.dumps({"status": "ok", "as_of_date": args.asof, "best": best, "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
