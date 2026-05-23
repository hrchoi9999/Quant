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
VALUATION_DIR = ROOT / r"reports\valuation_ai"
DOWNSIDE_DIR = ROOT / r"reports\downside_risk_ai_v01"
REPORT_DIR = ROOT / r"reports\candidate_rank_delta_ai_v01"

RANDOM_STATE = 42
KEY_COLUMNS = {"scope_key", "model_id", "ticker", "name", "event_date", "week_end", "live_start_date"}
FORWARD_PREFIXES = ("fwd_", "label_", "has_")
EXCLUDED_NUMERIC = {"is_current", "is_live_event"}

LABEL_SPECS: list[dict[str, Any]] = [
    {"label": "upgrade_excess_p5_mdd12", "kind": "upgrade", "ret_th": 0.05, "mdd_th": -0.12, "logic": "and", "description": "excess >= +5% and MDD > -12%"},
    {"label": "upgrade_excess_p3_mdd15", "kind": "upgrade", "ret_th": 0.03, "mdd_th": -0.15, "logic": "and", "description": "excess >= +3% and MDD > -15%"},
    {"label": "upgrade_return_p5", "kind": "upgrade_abs", "ret_th": 0.05, "description": "absolute return >= +5%"},
    {"label": "upgrade_return_p10", "kind": "upgrade_abs", "ret_th": 0.10, "description": "absolute return >= +10%"},
    {"label": "downgrade_excess_m5_mdd12", "kind": "downgrade", "ret_th": -0.05, "mdd_th": -0.12, "logic": "or", "description": "excess <= -5% or MDD <= -12%"},
    {"label": "downgrade_return_neg_or_mdd12", "kind": "downgrade_abs", "ret_th": 0.0, "mdd_th": -0.12, "logic": "or", "description": "return < 0 or MDD <= -12%"},
]
LABEL_NAMES = {str(spec["label"]) for spec in LABEL_SPECS}
FEATURE_SETS = ["BASE", "AI_SCORES"]


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
    if "asset_type" in df.columns:
        asset = df["asset_type"].astype(str).str.upper()
        df = df[~asset.str.contains("ETF", na=False)].copy()
    return _add_labels(df)


def _add_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ret = pd.to_numeric(out.get("fwd_ret_1m"), errors="coerce")
    mdd = pd.to_numeric(out.get("fwd_mdd_1m"), errors="coerce")
    median_ret_by_date = out.assign(_ret=ret).groupby("event_date")["_ret"].transform("median")
    excess = ret - median_ret_by_date
    for spec in LABEL_SPECS:
        label = str(spec["label"])
        kind = str(spec["kind"])
        if kind == "upgrade":
            hit = (excess >= float(spec["ret_th"])) & (mdd.isna() | (mdd > float(spec["mdd_th"])))
        elif kind == "upgrade_abs":
            hit = ret >= float(spec["ret_th"])
        elif kind == "downgrade":
            hit = (excess <= float(spec["ret_th"])) | (mdd.fillna(0) <= float(spec["mdd_th"]))
        else:
            hit = (ret < float(spec["ret_th"])) | (mdd.fillna(0) <= float(spec["mdd_th"]))
        out[label] = np.where(ret.notna(), hit.astype(int), np.nan)
    return out


def _join_current_ai_scores(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    out = df.copy()
    token = asof.replace("-", "")
    join_keys = ["scope_key", "model_id", "ticker"]
    downside_path = DOWNSIDE_DIR / f"downside_risk_ai_current_scores_{token}.csv"
    if downside_path.exists():
        downside = pd.read_csv(downside_path, dtype={"ticker": str}, low_memory=False)
        downside["ticker"] = downside["ticker"].astype(str).str.zfill(6)
        cols = [*join_keys, "downside_risk_prob"]
        out = out.merge(downside[[col for col in cols if col in downside.columns]].drop_duplicates(join_keys), on=join_keys, how="left")
    val_path = VALUATION_DIR / f"valuation_ai_challenger_current_candidates_{token}.csv"
    if val_path.exists():
        val = pd.read_csv(val_path, dtype={"security_code": str}, low_memory=False)
        val["ticker"] = val["security_code"].astype(str).str.zfill(6)
        keep = ["ticker", "champion_score", "challenger_score", "risk_score"]
        val_small = val[[col for col in keep if col in val.columns]].drop_duplicates(["ticker"])
        out = out.merge(val_small, on="ticker", how="left")
    return out


def _feature_columns(df: pd.DataFrame, feature_set: str) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    ai_cols = {"downside_risk_prob", "champion_score", "challenger_score", "risk_score"}
    for col in df.columns:
        if col in KEY_COLUMNS or col in EXCLUDED_NUMERIC or col in LABEL_NAMES or col.startswith(FORWARD_PREFIXES):
            continue
        if col in ai_cols and feature_set != "AI_SCORES":
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _split(df: pd.DataFrame, label: str, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[label].notna()].sort_values("event_date").copy()
    train = labeled[labeled["event_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["event_date"] >= pd.Timestamp(valid_start)) & (labeled["event_date"] <= pd.Timestamp(valid_end))].copy()
    return train, valid


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


def _evaluate(df: pd.DataFrame, label: str, feature_set: str, train_end: str, valid_start: str, valid_end: str) -> dict[str, Any]:
    train, valid = _split(df, label, train_end, valid_start, valid_end)
    numeric, categorical = _feature_columns(train, feature_set)
    row: dict[str, Any] = {
        "label": label,
        "feature_set": feature_set,
        "label_kind": next((str(spec["kind"]) for spec in LABEL_SPECS if spec["label"] == label), ""),
        "description": next((str(spec["description"]) for spec in LABEL_SPECS if spec["label"] == label), ""),
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "train_positive_rate": _safe_float(train[label].mean()) if not train.empty else None,
        "valid_positive_rate": _safe_float(valid[label].mean()) if not valid.empty else None,
        "status": "ok",
    }
    if train.empty or valid.empty or train[label].nunique() < 2 or valid[label].nunique() < 2:
        row["status"] = "skipped"
        row["reason"] = "insufficient_rows_or_one_class"
        return row
    model = _fit(train, label, numeric, categorical)
    prob = model.predict_proba(valid)[:, 1]
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    row.update(
        {
            "numeric_features": int(len(numeric)),
            "categorical_features": int(len(categorical)),
            "auc": _safe_float(roc_auc_score(valid[label].astype(int), prob)),
            "top30_label_rate": _safe_float(top[label].mean()),
            "bottom30_label_rate": _safe_float(bottom[label].mean()),
            "top_bottom_label_spread": _safe_float(top[label].mean() - bottom[label].mean()),
            "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()),
            "bottom30_avg_1m_return": _safe_float(pd.to_numeric(bottom.get("fwd_ret_1m"), errors="coerce").mean()),
            "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()),
        }
    )
    return row


def run_ablation(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    base = _read_mart(asof)
    ai = _join_current_ai_scores(base, asof)
    rows = []
    for label in LABEL_NAMES:
        rows.append(_evaluate(base, label, "BASE", train_end, valid_start, asof))
        rows.append(_evaluate(ai, label, "AI_SCORES", train_end, valid_start, asof))
    result = pd.DataFrame(rows).sort_values(["auc", "top_bottom_label_spread"], ascending=False, na_position="last")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    csv_path = REPORT_DIR / f"candidate_rank_delta_ablation_{token}.csv"
    json_path = REPORT_DIR / f"candidate_rank_delta_ablation_{token}.json"
    md_path = REPORT_DIR / f"candidate_rank_delta_ablation_{token}.md"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "candidate_rank_delta_ablation",
        "model_code": "AI-CANDIDATE-RANK-DELTA-V01",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results": result.where(pd.notna(result), None).to_dict(orient="records"),
        "outputs": {"csv": str(csv_path), "json": str(json_path), "md": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# Candidate Rank Delta Ablation - {asof}",
                "",
                "| label | feature_set | auc | top30_label | bottom30_label | top30_ret | top30_mdd |",
                "|---|---|---:|---:|---:|---:|---:|",
                *[
                    "| {label} | {feature_set} | {auc} | {top30_label_rate} | {bottom30_label_rate} | {top30_avg_1m_return} | {top30_avg_1m_mdd} |".format(
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
    parser = argparse.ArgumentParser(description="Run label/feature ablation for AI-CANDIDATE-RANK-DELTA-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_ablation(args.asof, args.train_end, args.valid_start)
    print(json.dumps({"status": "ok", "as_of_date": args.asof, "best": payload["results"][0], "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
