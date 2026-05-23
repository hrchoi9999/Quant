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
RANDOM_STATE = 42

LABEL = "label_excess_m5_or_mdd12"
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
    left = df.sort_values("event_date").copy()
    joined = pd.merge_asof(left, risk, left_on="event_date", right_on="asof_date", direction="backward")
    return joined.drop(columns=["asof_date"], errors="ignore")


def _feature_columns(df: pd.DataFrame, feature_set: str) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    include_qm = feature_set.upper() == "QM_RISK"
    for col in df.columns:
        if col in KEY_COLUMNS or col in EXCLUDED_NUMERIC or col == LABEL or col.startswith(FORWARD_PREFIXES):
            continue
        is_qm = col.startswith("qm_")
        if is_qm and not include_qm:
            continue
        if (not is_qm) or col in QM_RISK_COLUMNS:
            if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
                numeric.append(col)
        if ((not is_qm) or col in QM_RISK_CATEGORICAL) and df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


def _split(df: pd.DataFrame, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[LABEL].notna()].sort_values("event_date").copy()
    train = labeled[labeled["event_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["event_date"] >= pd.Timestamp(valid_start)) & (labeled["event_date"] <= pd.Timestamp(valid_end))].copy()
    if len(train) >= 200 and len(valid) >= 50 and train[LABEL].nunique() >= 2 and valid[LABEL].nunique() >= 2:
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


def _fit(train: pd.DataFrame, numeric: list[str], categorical: list[str]) -> Pipeline:
    model = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=3, random_state=RANDOM_STATE)
    pipe = Pipeline([("prep", _preprocessor(numeric, categorical)), ("model", model)])
    pipe.fit(train, train[LABEL].astype(int))
    return pipe


def _evaluate(df: pd.DataFrame, feature_set: str, train_end: str, valid_start: str, valid_end: str) -> dict[str, Any]:
    train, valid = _split(df, train_end, valid_start, valid_end)
    numeric, categorical = _feature_columns(train, feature_set)
    model = _fit(train, numeric, categorical)
    prob = model.predict_proba(valid)[:, 1]
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    return {
        "feature_set": feature_set,
        "label": LABEL,
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "numeric_features": int(len(numeric)),
        "categorical_features": int(len(categorical)),
        "train_positive_rate": _safe_float(train[LABEL].mean()),
        "valid_positive_rate": _safe_float(valid[LABEL].mean()),
        "auc": _safe_float(roc_auc_score(valid[LABEL].astype(int), prob)),
        "top30_positive_rate": _safe_float(top[LABEL].mean()),
        "bottom30_positive_rate": _safe_float(bottom[LABEL].mean()),
        "top_bottom_positive_spread": _safe_float(top[LABEL].mean() - bottom[LABEL].mean()),
        "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()),
        "bottom30_avg_1m_return": _safe_float(pd.to_numeric(bottom.get("fwd_ret_1m"), errors="coerce").mean()),
        "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()),
    }


def run_ablation(asof: str, train_end: str, valid_start: str) -> dict[str, Any]:
    base = _read_mart(asof)
    qm = _join_qm_risk(base)
    results = pd.DataFrame(
        [
            _evaluate(base, "BASE", train_end, valid_start, asof),
            _evaluate(qm, "QM_RISK", train_end, valid_start, asof),
        ]
    ).sort_values(["auc", "top_bottom_positive_spread"], ascending=False)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    csv_path = REPORT_DIR / f"downside_risk_qm_feature_ablation_{token}.csv"
    json_path = REPORT_DIR / f"downside_risk_qm_feature_ablation_{token}.json"
    md_path = REPORT_DIR / f"downside_risk_qm_feature_ablation_{token}.md"
    results.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "downside_risk_qm_feature_ablation",
        "model_code": "AI-DOWNSIDE-RISK-V01",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "qm_context_file": str(QM_CONTEXT_DIR / "risk_context_daily_current.csv"),
        "join_rule": "merge_asof backward on event_date <= qm asof_date",
        "results": results.where(pd.notna(results), None).to_dict(orient="records"),
        "outputs": {"csv": str(csv_path), "json": str(json_path), "md": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# Downside Risk QM Feature Ablation - {asof}",
                "",
                "| feature_set | auc | top30_pos | bottom30_pos | spread | top30_ret | top30_mdd |",
                "|---|---:|---:|---:|---:|---:|---:|",
                *[
                    "| {feature_set} | {auc} | {top30_positive_rate} | {bottom30_positive_rate} | {top_bottom_positive_spread} | {top30_avg_1m_return} | {top30_avg_1m_mdd} |".format(
                        **{k: "" if pd.isna(v) else v for k, v in row.items()}
                    )
                    for row in results.to_dict(orient="records")
                ],
            ]
        ),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QM-RISK feature ablation for AI-DOWNSIDE-RISK-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    args = parser.parse_args()
    payload = run_ablation(args.asof, args.train_end, args.valid_start)
    print(json.dumps({"status": "ok", "as_of_date": args.asof, "results": payload["results"], "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
