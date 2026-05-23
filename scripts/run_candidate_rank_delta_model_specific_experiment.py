from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from run_candidate_rank_delta_rank_change_ablation import (
    LABEL_NAMES,
    MODEL_CODE,
    MODEL_NAME_KO,
    REPORT_DIR,
    _add_next_rank_labels,
    _feature_columns,
    _fit,
    _read_mart,
    _safe_float,
    _split,
)

VALUATION_DIR = Path(r"D:\Quant") / r"reports\valuation_ai"
DOWNSIDE_DIR = Path(r"D:\Quant") / r"reports\downside_risk_ai_v01"

VALUATION_SCORE_COLUMNS = [
    "valuation_ai_score",
    "predicted_excess_return_12m",
    "current_valuation_percentile",
    "implied_growth_pressure",
    "valuation_growth_gap",
    "expected_return_score",
    "valuation_safety_score",
    "growth_quality_score",
    "revision_momentum_score",
    "downside_safety_score",
    "downside_risk_score",
    "confidence_score",
    "outperform_prob",
    "underperform_prob",
    "overheated_prob",
    "value_creation_prob",
]


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


def _join_ai_score_snapshot(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    out = df.copy()
    token = asof.replace("-", "")
    downside_path = DOWNSIDE_DIR / f"downside_risk_ai_current_scores_{token}.csv"
    if downside_path.exists():
        downside = pd.read_csv(downside_path, dtype={"ticker": str}, low_memory=False)
        downside["ticker"] = downside["ticker"].astype(str).str.zfill(6)
        keep = ["scope_key", "model_id", "ticker", "downside_risk_prob", "downside_risk_tag"]
        downside_small = downside[[col for col in keep if col in downside.columns]].drop_duplicates(["scope_key", "model_id", "ticker"])
        out = out.merge(downside_small, on=["scope_key", "model_id", "ticker"], how="left")

    valuation_path = VALUATION_DIR / f"valuation_scores_{token}.csv"
    if valuation_path.exists():
        valuation = pd.read_csv(valuation_path, dtype={"ticker": str}, low_memory=False)
        valuation["ticker"] = valuation["ticker"].astype(str).str.zfill(6)
        keep = ["ticker", *VALUATION_SCORE_COLUMNS]
        valuation_small = valuation[[col for col in keep if col in valuation.columns]].drop_duplicates(["ticker"])
        rename = {col: f"valuation_{col}" for col in valuation_small.columns if col != "ticker" and not col.startswith("valuation_")}
        valuation_small = valuation_small.rename(columns=rename)
        out = out.merge(valuation_small, on="ticker", how="left")

    challenger_path = VALUATION_DIR / f"valuation_ai_challenger_current_candidates_{token}.csv"
    if challenger_path.exists():
        challenger = pd.read_csv(challenger_path, dtype={"security_code": str}, low_memory=False)
        challenger["ticker"] = challenger["security_code"].astype(str).str.zfill(6)
        keep = [
            "ticker",
            "champion_score",
            "challenger_score",
            "challenger_score_delta",
            "risk_score",
            "risk_score_delta",
            "risk_tag",
        ]
        challenger_small = challenger[[col for col in keep if col in challenger.columns]].drop_duplicates(["ticker"])
        challenger_small = challenger_small.rename(
            columns={
                "champion_score": "valuation_champion_score",
                "challenger_score": "valuation_challenger_score",
                "challenger_score_delta": "valuation_challenger_score_delta",
                "risk_score": "valuation_risk_score",
                "risk_score_delta": "valuation_risk_score_delta",
                "risk_tag": "valuation_risk_tag",
            }
        )
        out = out.merge(challenger_small, on="ticker", how="left")
    return out


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
        "bottom30_drop_rate": _safe_float(bottom["dropped_next_rebalance"].mean()),
        "top30_avg_1m_return": _safe_float(pd.to_numeric(top.get("fwd_ret_1m"), errors="coerce").mean()),
        "top30_avg_1m_mdd": _safe_float(pd.to_numeric(top.get("fwd_mdd_1m"), errors="coerce").mean()),
    }


def _evaluate_segment(
    df: pd.DataFrame,
    segment_type: str,
    segment_key: str,
    feature_mode: str,
    label: str,
    train_end: str,
    valid_start: str,
    valid_end: str,
    min_train: int,
    min_valid: int,
) -> dict[str, Any]:
    train, valid = _split(df, label, train_end, valid_start, valid_end)
    row: dict[str, Any] = {
        "segment_type": segment_type,
        "segment_key": segment_key,
        "feature_mode": feature_mode,
        "label": label,
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
    if not numeric and not categorical:
        row.update({"status": "skipped", "reason": "no_features"})
        return row
    model = _fit(train, label, numeric, categorical)
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


def _attach_pooled_baseline(result: pd.DataFrame, asof: str) -> pd.DataFrame:
    token = asof.replace("-", "")
    out = result.copy()
    out["pooled_auc"] = np.nan
    family_path = REPORT_DIR / f"candidate_rank_delta_family_breakdown_{token}.csv"
    model_path = REPORT_DIR / f"candidate_rank_delta_model_breakdown_{token}.csv"
    baselines: list[pd.DataFrame] = []
    if family_path.exists():
        family = pd.read_csv(family_path, low_memory=False)
        family["segment_type"] = "family"
        family["segment_key"] = family["model_family"].astype(str)
        baselines.append(family[["segment_type", "segment_key", "label", "auc"]])
    if model_path.exists():
        model = pd.read_csv(model_path, low_memory=False)
        model["segment_type"] = "model"
        model["segment_key"] = model["scope_key"].astype(str) + "/" + model["model_id"].astype(str)
        baselines.append(model[["segment_type", "segment_key", "label", "auc"]])
    if not baselines:
        return out
    base = pd.concat(baselines, ignore_index=True).rename(columns={"auc": "pooled_auc"})
    out = out.drop(columns=["pooled_auc"]).merge(base, on=["segment_type", "segment_key", "label"], how="left")
    out["auc_lift_vs_pooled"] = out["auc"] - out["pooled_auc"]
    return out


def _best_by_segment(result: pd.DataFrame) -> pd.DataFrame:
    ok = result[result["status"].eq("ok")].copy()
    if ok.empty:
        return ok
    ok = ok.sort_values(
        ["segment_type", "segment_key", "auc", "top_bottom_label_spread", "valid_rows"],
        ascending=[True, True, False, False, False],
    )
    return ok.groupby(["segment_type", "segment_key"], as_index=False).head(1).reset_index(drop=True)


def _best_feature_lift(result: pd.DataFrame) -> pd.DataFrame:
    ok = result[result["status"].eq("ok")].copy()
    if ok.empty:
        return ok
    keys = ["segment_type", "segment_key", "label"]
    base = ok[ok["feature_mode"].eq("BASE")][[*keys, "auc"]].rename(columns={"auc": "base_auc"})
    ai = ok[ok["feature_mode"].eq("AI_SCORE_SNAPSHOT")].merge(base, on=keys, how="left")
    ai["ai_feature_auc_lift"] = ai["auc"] - ai["base_auc"]
    return ai.sort_values(
        ["segment_type", "segment_key", "ai_feature_auc_lift", "auc"],
        ascending=[True, True, False, False],
        na_position="last",
    ).groupby(["segment_type", "segment_key"], as_index=False).head(1).reset_index(drop=True)


def run_model_specific_experiment(
    asof: str,
    train_end: str,
    valid_start: str,
    min_train: int,
    min_valid: int,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    base_mart = _add_next_rank_labels(_read_mart(asof))
    base_mart = base_mart[base_mart[sorted(LABEL_NAMES)].notna().any(axis=1)].copy()
    base_mart["model_family"] = base_mart["model_id"].map(_model_family)
    feature_frames = {
        "BASE": base_mart,
        "AI_SCORE_SNAPSHOT": _join_ai_score_snapshot(base_mart, asof),
    }
    run_labels = sorted(labels or LABEL_NAMES)

    rows: list[dict[str, Any]] = []
    for feature_mode, mart in feature_frames.items():
        for family, seg in mart.groupby("model_family", dropna=False):
            for label in run_labels:
                rows.append(_evaluate_segment(seg, "family", str(family), feature_mode, label, train_end, valid_start, asof, min_train, min_valid))

        for (scope_key, model_id), seg in mart.groupby(["scope_key", "model_id"], dropna=False):
            segment_key = f"{scope_key}/{model_id}"
            for label in run_labels:
                rows.append(_evaluate_segment(seg, "model", segment_key, feature_mode, label, train_end, valid_start, asof, min_train, min_valid))

    result = pd.DataFrame(rows)
    result = _attach_pooled_baseline(result, asof)
    if "auc_lift_vs_pooled" not in result.columns:
        result["auc_lift_vs_pooled"] = np.nan
    result = result.sort_values(
        ["segment_type", "segment_key", "status", "auc", "top_bottom_label_spread"],
        ascending=[True, True, True, False, False],
        na_position="last",
    )
    best = _best_by_segment(result)
    feature_lift = _best_feature_lift(result)

    token = asof.replace("-", "")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    result_csv = REPORT_DIR / f"candidate_rank_delta_model_specific_experiment_{token}.csv"
    best_csv = REPORT_DIR / f"candidate_rank_delta_model_specific_best_{token}.csv"
    lift_csv = REPORT_DIR / f"candidate_rank_delta_ai_score_feature_lift_{token}.csv"
    json_path = REPORT_DIR / f"candidate_rank_delta_model_specific_experiment_{token}.json"
    md_path = REPORT_DIR / f"candidate_rank_delta_model_specific_experiment_{token}.md"

    result.to_csv(result_csv, index=False, encoding="utf-8-sig")
    best.to_csv(best_csv, index=False, encoding="utf-8-sig")
    feature_lift.to_csv(lift_csv, index=False, encoding="utf-8-sig")

    payload = {
        "source_name": "candidate_rank_delta_model_specific_experiment",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_train": min_train,
        "min_valid": min_valid,
        "feature_modes": list(feature_frames.keys()),
        "labels": run_labels,
        "ai_score_feature_note": "AI_SCORE_SNAPSHOT uses 2026-05-08 current AI score snapshots joined to historical rank-change rows; treat as feature stress test, not leakage-free backtest.",
        "best_by_segment": best.replace({np.nan: None}).to_dict(orient="records"),
        "best_ai_score_feature_lift": feature_lift.replace({np.nan: None}).to_dict(orient="records"),
        "outputs": {
            "result_csv": str(result_csv),
            "best_csv": str(best_csv),
            "ai_score_feature_lift_csv": str(lift_csv),
            "json": str(json_path),
            "md": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# Candidate Rank Delta Model-Specific Experiment - {asof}",
        "",
        f"- Model: {MODEL_CODE} / {MODEL_NAME_KO}",
        f"- Minimum train/valid rows: {min_train}/{min_valid}",
        "",
        "Note: `AI_SCORE_SNAPSHOT` is a current-snapshot feature stress test, not a leakage-free historical backtest.",
        "",
        "| segment_type | segment | feature_mode | best_label | rows | auc | pooled_auc | lift | top30_label | bottom30_label |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in best.to_dict(orient="records"):
        md_lines.append(
            "| {segment_type} | {segment_key} | {feature_mode} | {label} | {valid_rows} | {auc} | {pooled_auc} | {auc_lift_vs_pooled} | {top30_label_rate} | {bottom30_label_rate} |".format(
                **{k: "" if pd.isna(v) else v for k, v in row.items()}
            )
        )
    md_lines.extend(
        [
            "",
            "## Best AI Score Feature Lift",
            "",
            "| segment_type | segment | label | base_auc | ai_auc | ai_lift |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for row in feature_lift.to_dict(orient="records"):
        md_lines.append(
            "| {segment_type} | {segment_key} | {label} | {base_auc} | {auc} | {ai_feature_auc_lift} |".format(
                **{k: "" if pd.isna(v) else v for k, v in row.items()}
            )
        )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run model-specific learning and label selection for AI-CANDIDATE-RANK-DELTA-V01.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--min-train", type=int, default=200)
    parser.add_argument("--min-valid", type=int, default=50)
    parser.add_argument("--labels", nargs="*", default=None)
    args = parser.parse_args()
    labels = args.labels
    if labels:
        unknown = sorted(set(labels) - set(LABEL_NAMES))
        if unknown:
            raise SystemExit(f"unknown labels: {unknown}")
    payload = run_model_specific_experiment(args.asof, args.train_end, args.valid_start, args.min_train, args.min_valid, labels)
    print(
        json.dumps(
            {
                "status": "ok",
                "as_of_date": args.asof,
                "segments": len(payload["best_by_segment"]),
                "best_by_segment": payload["best_by_segment"],
                "best_ai_score_feature_lift": payload["best_ai_score_feature_lift"],
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
