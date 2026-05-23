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

from build_theme_persistence_ai_v01 import (
    QM_CONTEXT_DIR,
    REPORT_DIR,
    _add_acceleration_features,
    _join_qm_market_risk_flow_context,
    _join_theme_quality_features,
    _safe_float,
)

RANDOM_STATE = 42
FWD_STEPS = 20

LABEL_SPECS = [
    {"label": "continue_ret_pos_mom_pos", "kind": "continue", "description": "future 1m ret > 0 and momentum > 0"},
    {"label": "continue_ret_p3_mom_pos", "kind": "continue", "description": "future 1m ret >= +3% and momentum > 0"},
    {"label": "continue_top5", "kind": "continue", "description": "future leading rank <= 5"},
    {"label": "continue_rank_hold_top8", "kind": "continue", "description": "future leading rank <= 8 and rank does not worsen by 3+"},
    {"label": "fade_ret_neg", "kind": "fade", "description": "future 1m ret < 0"},
    {"label": "fade_mom_neg", "kind": "fade", "description": "future momentum < 0"},
    {"label": "fade_rank_worse3", "kind": "fade", "description": "future rank worsens by 3+"},
    {"label": "fade_ret_neg_or_rank_worse3", "kind": "fade", "description": "future 1m ret < 0 or rank worsens by 3+"},
]
EXCLUDE_COLUMNS = {
    "asof_date",
    "quant_theme_bucket",
    "quantmarket_theme_bucket",
    "theme_name_kr",
    "generated_at",
    "feature_version",
    "schema_version",
    "future_ret_1m",
    "future_momentum",
    "future_rank",
    "rank_change",
    *[str(spec["label"]) for spec in LABEL_SPECS],
}


def _feature_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    numeric: list[str] = []
    categorical: list[str] = []
    for col in df.columns:
        if col in EXCLUDE_COLUMNS or col.startswith("future_") or col.startswith("label_"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].notna().any():
            numeric.append(col)
        elif df[col].dtype == object and df[col].notna().any():
            categorical.append(col)
    return numeric, categorical


FEATURE_MODES = {"BASE", "ACCELERATION", "ACCELERATION_QM_CONTEXT", "THEME_QUALITY", "ACCELERATION_THEME_QUALITY"}


def _read_context(
    *,
    include_qm_context: bool,
    include_acceleration: bool,
    include_theme_quality: bool,
    quality_asof: str | None,
) -> pd.DataFrame:
    path = QM_CONTEXT_DIR / "theme_context_daily_quant_bucket_current.csv"
    df = pd.read_csv(path, low_memory=False)
    df["asof_date"] = pd.to_datetime(df["asof_date"], errors="coerce")
    df = df[df["asof_date"].notna() & df["quant_theme_bucket"].notna()].copy()
    df = df.sort_values(["quant_theme_bucket", "asof_date"]).drop_duplicates(["quant_theme_bucket", "asof_date"], keep="last")
    if include_acceleration:
        df = _add_acceleration_features(df)
    if include_qm_context:
        df = _join_qm_market_risk_flow_context(df)
    if include_theme_quality:
        df = _join_theme_quality_features(df, quality_asof)
    group = df.groupby("quant_theme_bucket", group_keys=False)
    df["future_ret_1m"] = group["theme_ret_1m"].shift(-FWD_STEPS)
    df["future_momentum"] = group["theme_momentum_score"].shift(-FWD_STEPS)
    df["future_rank"] = group["leading_theme_rank"].shift(-FWD_STEPS)
    df["rank_change"] = pd.to_numeric(df["leading_theme_rank"], errors="coerce") - pd.to_numeric(df["future_rank"], errors="coerce")
    return _add_labels(df)


def _add_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    fut_ret = pd.to_numeric(out["future_ret_1m"], errors="coerce")
    fut_mom = pd.to_numeric(out["future_momentum"], errors="coerce")
    fut_rank = pd.to_numeric(out["future_rank"], errors="coerce")
    rank_change = pd.to_numeric(out["rank_change"], errors="coerce")
    has_future = fut_ret.notna() & fut_mom.notna() & fut_rank.notna()
    labels = {
        "continue_ret_pos_mom_pos": (fut_ret > 0.0) & (fut_mom > 0.0),
        "continue_ret_p3_mom_pos": (fut_ret >= 0.03) & (fut_mom > 0.0),
        "continue_top5": fut_rank <= 5,
        "continue_rank_hold_top8": (fut_rank <= 8) & (rank_change >= -2),
        "fade_ret_neg": fut_ret < 0.0,
        "fade_mom_neg": fut_mom < 0.0,
        "fade_rank_worse3": rank_change <= -3,
        "fade_ret_neg_or_rank_worse3": (fut_ret < 0.0) | (rank_change <= -3),
    }
    for label, hit in labels.items():
        out[label] = np.where(has_future, hit.astype(int), np.nan)
    return out


def _split(df: pd.DataFrame, label: str, train_end: str, valid_start: str, valid_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[label].notna()].sort_values("asof_date").copy()
    train = labeled[labeled["asof_date"] <= pd.Timestamp(train_end)].copy()
    valid = labeled[(labeled["asof_date"] >= pd.Timestamp(valid_start)) & (labeled["asof_date"] <= pd.Timestamp(valid_end))].copy()
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
    max_date = train["asof_date"].max()
    cutoff = max_date - pd.DateOffset(years=1)
    weight = np.ones(len(train), dtype=float)
    weight[train["asof_date"].ge(cutoff).to_numpy()] = 3.0
    pipe.fit(train, train[label].astype(int), model__sample_weight=weight)
    return pipe


def _eval(df: pd.DataFrame, spec: dict[str, str], feature_mode: str, train_end: str, valid_start: str, valid_end: str) -> dict[str, Any]:
    label = spec["label"]
    train, valid = _split(df, label, train_end, valid_start, valid_end)
    numeric, categorical = _feature_columns(train)
    row: dict[str, Any] = {
        **spec,
        "feature_mode": feature_mode,
        "train_rows": int(len(train)),
        "valid_rows": int(len(valid)),
        "train_positive_rate": _safe_float(train[label].mean()) if not train.empty else None,
        "valid_positive_rate": _safe_float(valid[label].mean()) if not valid.empty else None,
        "status": "ok",
    }
    if train.empty or valid.empty or train[label].nunique() < 2 or valid[label].nunique() < 2:
        row.update({"status": "skipped", "reason": "insufficient_rows_or_one_class"})
        return row
    model = _fit(train, label, numeric, categorical)
    prob = model.predict_proba(valid)[:, 1]
    scored = valid.copy()
    scored["prob"] = prob
    top = scored.sort_values("prob", ascending=False).head(min(30, len(scored)))
    bottom = scored.sort_values("prob", ascending=True).head(min(30, len(scored)))
    row.update(
        {
            "auc": _safe_float(roc_auc_score(valid[label].astype(int), prob)),
            "top30_label_rate": _safe_float(top[label].mean()),
            "bottom30_label_rate": _safe_float(bottom[label].mean()),
            "top_bottom_label_spread": _safe_float(top[label].mean() - bottom[label].mean()),
            "top30_future_ret_1m": _safe_float(pd.to_numeric(top["future_ret_1m"], errors="coerce").mean()),
            "bottom30_future_ret_1m": _safe_float(pd.to_numeric(bottom["future_ret_1m"], errors="coerce").mean()),
            "top30_future_rank": _safe_float(pd.to_numeric(top["future_rank"], errors="coerce").mean()),
            "bottom30_future_rank": _safe_float(pd.to_numeric(bottom["future_rank"], errors="coerce").mean()),
        }
    )
    return row


def run_ablation(
    asof: str,
    train_end: str,
    valid_start: str,
    labels: list[str] | None = None,
    feature_modes: list[str] | None = None,
    quality_asof: str | None = None,
) -> dict[str, Any]:
    run_specs = [spec for spec in LABEL_SPECS if labels is None or spec["label"] in labels]
    quality_asof = quality_asof or asof
    frame_builders = {
        "BASE": lambda: _read_context(
            include_qm_context=False, include_acceleration=False, include_theme_quality=False, quality_asof=quality_asof
        ),
        "ACCELERATION": lambda: _read_context(
            include_qm_context=False, include_acceleration=True, include_theme_quality=False, quality_asof=quality_asof
        ),
        "ACCELERATION_QM_CONTEXT": lambda: _read_context(
            include_qm_context=True, include_acceleration=True, include_theme_quality=False, quality_asof=quality_asof
        ),
        "THEME_QUALITY": lambda: _read_context(
            include_qm_context=False, include_acceleration=False, include_theme_quality=True, quality_asof=quality_asof
        ),
        "ACCELERATION_THEME_QUALITY": lambda: _read_context(
            include_qm_context=False, include_acceleration=True, include_theme_quality=True, quality_asof=quality_asof
        ),
    }
    selected_modes = feature_modes or list(frame_builders)
    frames = {mode: frame_builders[mode]() for mode in selected_modes}
    rows = []
    for feature_mode, df in frames.items():
        rows.extend(_eval(df, spec, feature_mode, train_end, valid_start, asof) for spec in run_specs)
    result = pd.DataFrame(rows).sort_values(["auc", "top_bottom_label_spread"], ascending=False, na_position="last")
    token = asof.replace("-", "")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORT_DIR / f"theme_persistence_label_ablation_{token}.csv"
    json_path = REPORT_DIR / f"theme_persistence_label_ablation_{token}.json"
    md_path = REPORT_DIR / f"theme_persistence_label_ablation_{token}.md"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "source_name": "theme_persistence_label_ablation",
        "model_code": "AI-THEME-PERSISTENCE-V01",
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "quality_asof": quality_asof,
        "results": result.replace({np.nan: None}).to_dict(orient="records"),
        "outputs": {"csv": str(csv_path), "json": str(json_path), "md": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# Theme Persistence Label Ablation - {asof}",
                "",
                "| feature_mode | label | kind | auc | top30_label | bottom30_label | top30_future_ret | bottom30_future_ret |",
                "|---|---|---|---:|---:|---:|---:|---:|",
                *[
                    "| {feature_mode} | {label} | {kind} | {auc} | {top30_label_rate} | {bottom30_label_rate} | {top30_future_ret_1m} | {bottom30_future_ret_1m} |".format(
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
    parser = argparse.ArgumentParser(description="Run label ablation for AI-THEME-PERSISTENCE-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--labels", nargs="*", default=None)
    parser.add_argument("--feature-modes", nargs="*", default=None)
    parser.add_argument("--quality-asof", default=None)
    args = parser.parse_args()
    if args.labels:
        unknown = sorted(set(args.labels) - {str(spec["label"]) for spec in LABEL_SPECS})
        if unknown:
            raise SystemExit(f"unknown labels: {unknown}")
    if args.feature_modes:
        unknown_modes = sorted(set(args.feature_modes) - FEATURE_MODES)
        if unknown_modes:
            raise SystemExit(f"unknown feature modes: {unknown_modes}")
    payload = run_ablation(args.asof, args.train_end, args.valid_start, args.labels, args.feature_modes, args.quality_asof)
    print(json.dumps({"status": "ok", "as_of_date": args.asof, "best": payload["results"][0], "outputs": payload["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
