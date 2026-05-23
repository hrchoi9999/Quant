from __future__ import annotations

import argparse
import json
import sys
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quant_market.market_handoff import context_dir, market_context_frame

SOURCE_DIR = ROOT / r"reports\ai_overlay_v01"
QM_CONTEXT_DIR = context_dir()
REPORT_DIR = ROOT / r"reports\downside_risk_ai_v01"

LABEL = "label_excess_m5_or_mdd12"
RANDOM_STATE = 42
MIN_TRAIN_ROWS = 400
MIN_VALID_ROWS = 80

KEY_COLUMNS = {"scope_key", "model_id", "ticker", "name", "event_date", "week_end", "live_start_date"}
FORWARD_PREFIXES = ("fwd_", "label_", "has_")
EXCLUDED_NUMERIC = {"is_current", "is_live_event"}
QM_RISK_COLUMNS = [
    "qm_usdkrw_ret_1m",
    "qm_gold_proxy_ret_1m",
    "qm_bond_proxy_ret_1m",
    "qm_inverse_etf_ret_1m",
    "qm_defensive_asset_strength_score",
    "qm_market_stress_score",
    "qm_drawdown_pressure_score",
    "qm_crash_warning_flag",
    "qm_predicted_forward_return",
    "qm_calibrated_forecast_score",
    "qm_calibration_confidence_score",
    "qm_expected_volatility_score",
    "qm_drawdown_risk_score",
    "qm_risk_score",
    "qm_risk_on_score",
    "qm_risk_off_score",
    "qm_global_risk_on_score",
    "qm_overall_feature_coverage_ratio",
]
QM_RISK_CATEGORICAL = ["qm_volatility_regime_label"]


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
    return _add_label(df)


def _add_label(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ret = pd.to_numeric(out.get("fwd_ret_1m"), errors="coerce")
    mdd = pd.to_numeric(out.get("fwd_mdd_1m"), errors="coerce")
    median_ret_by_date = out.assign(_ret=ret).groupby("event_date")["_ret"].transform("median")
    excess_ret = ret - median_ret_by_date
    out[LABEL] = np.where(ret.notna(), ((excess_ret <= -0.05) | (mdd.fillna(0) <= -0.12)).astype(int), np.nan)
    return out


def _read_qm_risk() -> pd.DataFrame:
    handoff = market_context_frame(scope="ALL", date_col="asof_date", prefix="qm_")
    if not handoff.empty:
        handoff["asof_date"] = pd.to_datetime(handoff["asof_date"], errors="coerce")
        return handoff.dropna(subset=["asof_date"]).sort_values("asof_date")

    path = QM_CONTEXT_DIR / "risk_context_daily_current.csv"
    if not path.exists():
        raise SystemExit(f"missing QM risk context: {path}")
    risk = pd.read_csv(path, low_memory=False)
    risk["asof_date"] = pd.to_datetime(risk["asof_date"], errors="coerce")
    risk = risk.dropna(subset=["asof_date"]).sort_values("asof_date")
    cols = [
        "asof_date",
        "usdkrw_ret_1m",
        "gold_proxy_ret_1m",
        "bond_proxy_ret_1m",
        "inverse_etf_ret_1m",
        "defensive_asset_strength_score",
        "market_stress_score",
        "drawdown_pressure_score",
        "crash_warning_flag",
        "volatility_regime_label",
    ]
    risk = risk[[col for col in cols if col in risk.columns]].rename(
        columns={
            "usdkrw_ret_1m": "qm_usdkrw_ret_1m",
            "gold_proxy_ret_1m": "qm_gold_proxy_ret_1m",
            "bond_proxy_ret_1m": "qm_bond_proxy_ret_1m",
            "inverse_etf_ret_1m": "qm_inverse_etf_ret_1m",
            "defensive_asset_strength_score": "qm_defensive_asset_strength_score",
            "market_stress_score": "qm_market_stress_score",
            "drawdown_pressure_score": "qm_drawdown_pressure_score",
            "crash_warning_flag": "qm_crash_warning_flag",
            "volatility_regime_label": "qm_volatility_regime_label",
        }
    )
    return risk


def _join_qm_risk(df: pd.DataFrame) -> pd.DataFrame:
    risk = _read_qm_risk()
    return pd.merge_asof(df.sort_values("event_date"), risk, left_on="event_date", right_on="asof_date", direction="backward").drop(columns=["asof_date"], errors="ignore")


def _split(df: pd.DataFrame, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[LABEL].notna()].sort_values("event_date").copy()
    train = labeled[labeled["event_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["event_date"] >= pd.Timestamp(valid_start)) & (labeled["event_date"] <= pd.Timestamp(valid_end))].copy()
    return train, valid


def _feature_columns(df: pd.DataFrame, feature_set: str, model_specific: bool) -> tuple[list[str], list[str]]:
    include_qm = feature_set == "QM_RISK"
    numeric: list[str] = []
    categorical: list[str] = []
    blocked = set(KEY_COLUMNS)
    if model_specific:
        blocked.update({"scope_key", "model_id"})
    for col in df.columns:
        if col in blocked or col in EXCLUDED_NUMERIC or col == LABEL or col.startswith(FORWARD_PREFIXES):
            continue
        is_qm = col.startswith("qm_")
        if is_qm and not include_qm:
            continue
        if ((not is_qm) or col in QM_RISK_COLUMNS) and pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        if ((not is_qm) or col in QM_RISK_CATEGORICAL) and df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


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


def _sample_weight(train: pd.DataFrame, weighting: str) -> np.ndarray | None:
    if weighting == "none":
        return None
    if weighting == "recent_2023_x3":
        weights = np.ones(len(train), dtype=float)
        weights[train["event_date"] >= pd.Timestamp("2023-01-01")] = 3.0
        return weights
    raise KeyError(f"unknown weighting: {weighting}")


def _fit(train: pd.DataFrame, numeric: list[str], categorical: list[str], weighting: str) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=160, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    weights = _sample_weight(train, weighting)
    fit_kwargs = {"model__sample_weight": weights} if weights is not None else {}
    pipe.fit(train, train[LABEL].astype(int), **fit_kwargs)
    return pipe


def _score_eval(valid: pd.DataFrame, prob: np.ndarray) -> dict[str, Any]:
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    return {
        "auc": _safe_float(roc_auc_score(valid[LABEL].astype(int), prob)) if valid[LABEL].nunique() >= 2 else None,
        "top30_positive_rate": _safe_float(top[LABEL].mean()) if not top.empty else None,
        "bottom30_positive_rate": _safe_float(bottom[LABEL].mean()) if not bottom.empty else None,
        "top_bottom_positive_spread": _safe_float(top[LABEL].mean() - bottom[LABEL].mean()) if not top.empty and not bottom.empty else None,
        "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()) if not top.empty else None,
        "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()) if not top.empty else None,
    }


def _evaluate_common(df: pd.DataFrame, feature_set: str, weighting: str, train_end: str, valid_start: str, valid_end: str) -> dict[str, Any]:
    train, valid = _split(df, train_end, valid_start, valid_end)
    numeric, categorical = _feature_columns(train, feature_set, model_specific=False)
    model = _fit(train, numeric, categorical, weighting)
    prob = model.predict_proba(valid)[:, 1]
    return {
        "training_scope": "common",
        "feature_set": feature_set,
        "weighting": weighting,
        "scope_key": "ALL",
        "model_id": "ALL",
        "status": "ok",
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "train_positive_rate": _safe_float(train[LABEL].mean()),
        "valid_positive_rate": _safe_float(valid[LABEL].mean()),
        **_score_eval(valid, prob),
    }


def _evaluate_specific(df: pd.DataFrame, feature_set: str, weighting: str, train_end: str, valid_start: str, valid_end: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (scope_key, model_id), frame in df.groupby(["scope_key", "model_id"], dropna=False):
        train, valid = _split(frame, train_end, valid_start, valid_end)
        base = {
            "training_scope": "model_specific",
            "feature_set": feature_set,
            "weighting": weighting,
            "scope_key": str(scope_key),
            "model_id": str(model_id),
            "train_rows": int(len(train)),
            "valid_rows": int(len(valid)),
            "train_positive_rate": _safe_float(train[LABEL].mean()) if not train.empty else None,
            "valid_positive_rate": _safe_float(valid[LABEL].mean()) if not valid.empty else None,
        }
        if len(train) < MIN_TRAIN_ROWS or len(valid) < MIN_VALID_ROWS or train[LABEL].nunique() < 2 or valid[LABEL].nunique() < 2:
            rows.append({**base, "status": "skipped", "reason": "insufficient_rows_or_one_class"})
            continue
        numeric, categorical = _feature_columns(train, feature_set, model_specific=True)
        model = _fit(train, numeric, categorical, weighting)
        prob = model.predict_proba(valid)[:, 1]
        rows.append({**base, "status": "ok", **_score_eval(valid, prob)})
    return rows


def run_ablation(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    base = _read_mart(asof)
    qm = _join_qm_risk(base)
    scenarios = [
        ("BASE", base, "none"),
        ("QM_RISK", qm, "none"),
        ("BASE", base, "recent_2023_x3"),
    ]
    rows: list[dict[str, Any]] = []
    for feature_set, frame, weighting in scenarios:
        rows.append(_evaluate_common(frame, feature_set, weighting, train_end, valid_start, asof))
        rows.extend(_evaluate_specific(frame, feature_set, weighting, train_end, valid_start, asof))
    results = pd.DataFrame(rows)
    ok = results[results["status"].eq("ok")].sort_values(["auc", "top_bottom_positive_spread"], ascending=False, na_position="last")
    skipped = results[~results["status"].eq("ok")]
    ordered = pd.concat([ok, skipped], ignore_index=True)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    csv_path = REPORT_DIR / f"downside_risk_model_specific_ablation_{token}.csv"
    json_path = REPORT_DIR / f"downside_risk_model_specific_ablation_{token}.json"
    md_path = REPORT_DIR / f"downside_risk_model_specific_ablation_{token}.md"
    ordered.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "downside_risk_model_specific_ablation",
        "model_code": "AI-DOWNSIDE-RISK-V01",
        "label": LABEL,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_train_rows": MIN_TRAIN_ROWS,
        "min_valid_rows": MIN_VALID_ROWS,
        "results": ordered.where(pd.notna(ordered), None).to_dict(orient="records"),
        "outputs": {"csv": str(csv_path), "json": str(json_path), "md": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    top = ok.head(20)
    md_path.write_text(
        "\n".join(
            [
                f"# Downside Risk Model-Specific Ablation - {asof}",
                "",
                "| scope | feature_set | weighting | model_id | auc | train | valid | top30_pos | top30_mdd |",
                "|---|---|---|---|---:|---:|---:|---:|---:|",
                *[
                    "| {training_scope} | {feature_set} | {weighting} | {model_id} | {auc} | {train_rows} | {valid_rows} | {top30_positive_rate} | {top30_avg_1m_mdd} |".format(
                        **{k: "" if pd.isna(v) else v for k, v in row.items()}
                    )
                    for row in top.to_dict(orient="records")
                ],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run model-specific ablation for AI-DOWNSIDE-RISK-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_ablation(args.asof, args.train_end, args.valid_start)
    ok = [row for row in payload["results"] if row.get("status") == "ok"]
    print(json.dumps({"status": "ok", "as_of_date": args.asof, "ok_models": len(ok), "best": ok[:5], "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
