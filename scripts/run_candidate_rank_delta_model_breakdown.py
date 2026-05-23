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


def _segment_metrics(scored: pd.DataFrame, label: str, min_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (scope_key, model_id), seg in scored.groupby(["scope_key", "model_id"], dropna=False):
        if len(seg) < min_rows:
            continue
        if seg[label].nunique() < 2:
            continue
        top = seg.sort_values("prob", ascending=False).head(min(30, len(seg)))
        bottom = seg.sort_values("prob", ascending=True).head(min(30, len(seg)))
        rows.append(
            {
                "label": label,
                "scope_key": scope_key,
                "model_id": model_id,
                "model_family": _model_family(model_id),
                "valid_rows": int(len(seg)),
                "positive_rate": _safe_float(seg[label].mean()),
                "auc": _safe_float(roc_auc_score(seg[label].astype(int), seg["prob"])),
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
        )
    return rows


def _family_metrics(scored: pd.DataFrame, label: str, min_rows: int) -> list[dict[str, Any]]:
    family_scored = scored.copy()
    family_scored["model_family"] = family_scored["model_id"].map(_model_family)
    rows: list[dict[str, Any]] = []
    for family, seg in family_scored.groupby("model_family", dropna=False):
        if len(seg) < min_rows or seg[label].nunique() < 2:
            continue
        top = seg.sort_values("prob", ascending=False).head(min(30, len(seg)))
        bottom = seg.sort_values("prob", ascending=True).head(min(30, len(seg)))
        rows.append(
            {
                "label": label,
                "model_family": family,
                "valid_rows": int(len(seg)),
                "positive_rate": _safe_float(seg[label].mean()),
                "auc": _safe_float(roc_auc_score(seg[label].astype(int), seg["prob"])),
                "top30_label_rate": _safe_float(top[label].mean()),
                "bottom30_label_rate": _safe_float(bottom[label].mean()),
                "top_bottom_label_spread": _safe_float(top[label].mean() - bottom[label].mean()),
                "top30_avg_next_rank_delta": _safe_float(top["next_rank_delta"].mean()),
                "top30_drop_rate": _safe_float(top["dropped_next_rebalance"].mean()),
            }
        )
    return rows


def run_breakdown(asof: str, train_end: str, valid_start: str, min_rows: int) -> dict[str, Any]:
    mart = _add_next_rank_labels(_read_mart(asof))
    model_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    for label in sorted(LABEL_NAMES):
        train, valid = _split(mart, label, train_end, valid_start, asof)
        numeric, categorical = _feature_columns(train)
        if train.empty or valid.empty or train[label].nunique() < 2 or valid[label].nunique() < 2:
            continue
        model = _fit(train, label, numeric, categorical)
        scored = valid.copy()
        scored["prob"] = model.predict_proba(valid)[:, 1]
        model_rows.extend(_segment_metrics(scored, label, min_rows))
        family_rows.extend(_family_metrics(scored, label, min_rows))

    model_result = pd.DataFrame(model_rows).sort_values(["label", "valid_rows", "auc"], ascending=[True, False, False])
    family_result = pd.DataFrame(family_rows).sort_values(["label", "valid_rows", "auc"], ascending=[True, False, False])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = asof.replace("-", "")
    model_csv = REPORT_DIR / f"candidate_rank_delta_model_breakdown_{token}.csv"
    family_csv = REPORT_DIR / f"candidate_rank_delta_family_breakdown_{token}.csv"
    json_path = REPORT_DIR / f"candidate_rank_delta_model_breakdown_{token}.json"
    md_path = REPORT_DIR / f"candidate_rank_delta_model_breakdown_{token}.md"
    model_result.to_csv(model_csv, index=False, encoding="utf-8-sig")
    family_result.to_csv(family_csv, index=False, encoding="utf-8-sig")

    payload = {
        "source_name": "candidate_rank_delta_model_breakdown",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_rows": min_rows,
        "model_results": model_result.replace({np.nan: None}).to_dict(orient="records"),
        "family_results": family_result.replace({np.nan: None}).to_dict(orient="records"),
        "outputs": {"model_csv": str(model_csv), "family_csv": str(family_csv), "json": str(json_path), "md": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    key_labels = [
        "label_next_rank_drop",
        "label_next_rank_downgrade_3_retained",
        "label_next_rank_upgrade_3_retained",
    ]
    model_md = model_result[model_result["label"].isin(key_labels)].copy()
    md_lines = [
        f"# Candidate Rank Delta Model Breakdown - {asof}",
        "",
        f"- Model: {MODEL_CODE} / {MODEL_NAME_KO}",
        f"- Minimum valid rows per segment: {min_rows}",
        "",
        "## Family Breakdown",
        "",
        "| label | family | rows | auc | top30_label | bottom30_label |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in family_result[family_result["label"].isin(key_labels)].to_dict(orient="records"):
        md_lines.append(
            f"| {row['label']} | {row['model_family']} | {row['valid_rows']} | {row['auc']} | {row['top30_label_rate']} | {row['bottom30_label_rate']} |"
        )
    md_lines.extend(
        [
            "",
            "## Model Breakdown",
            "",
            "| label | scope | model | rows | auc | top30_label | bottom30_label |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in model_md.to_dict(orient="records"):
        md_lines.append(
            f"| {row['label']} | {row['scope_key']} | {row['model_id']} | {row['valid_rows']} | {row['auc']} | {row['top30_label_rate']} | {row['bottom30_label_rate']} |"
        )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Break down AI-CANDIDATE-RANK-DELTA-V01 rank-change label performance by model.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--train-end", default="2023-12-31")
    parser.add_argument("--valid-start", default="2024-01-01")
    parser.add_argument("--min-rows", type=int, default=50)
    args = parser.parse_args()
    payload = run_breakdown(args.asof, args.train_end, args.valid_start, args.min_rows)
    print(
        json.dumps(
            {
                "status": "ok",
                "as_of_date": args.asof,
                "model_segments": len(payload["model_results"]),
                "family_segments": len(payload["family_results"]),
                "outputs": payload["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
