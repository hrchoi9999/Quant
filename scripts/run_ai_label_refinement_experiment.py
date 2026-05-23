from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(r"D:\Quant")
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_ai_overlay_v01 import _fit_model  # noqa: E402

REPORT_DIR = ROOT / r"reports\ai_overlay_v01"


LABEL_DEFS = {
    "label_quality_1m_current": {
        "description": "ret > 0, MDD > -15%, Sharpe > 0 when available",
    },
    "label_quality_1m_loose": {
        "description": "ret > 0 and MDD > -20% when available",
    },
    "label_quality_1m_balanced": {
        "description": "ret >= 3%, MDD > -15%, Sharpe > 0 when available",
    },
    "label_quality_1m_strict": {
        "description": "ret >= 5%, MDD > -10%, Sharpe > 0.3 when available",
    },
    "label_bad_1m_strict": {
        "description": "ret <= -3% or MDD <= -15% or Sharpe < -0.3 when available",
    },
}


def _safe_metric(series: pd.Series, default: float, op: str, threshold: float) -> pd.Series:
    value = series.fillna(default)
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    raise ValueError(op)


def add_refined_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    has = out["fwd_ret_1m"].notna()
    out["label_quality_1m_current"] = np.where(
        has,
        (
            (out["fwd_ret_1m"] > 0)
            & _safe_metric(out["fwd_mdd_1m"], 0.0, ">", -0.15)
            & _safe_metric(out["fwd_sharpe_1m"], 1.0, ">", 0.0)
        ).astype(int),
        np.nan,
    )
    out["label_quality_1m_loose"] = np.where(
        has,
        ((out["fwd_ret_1m"] > 0) & _safe_metric(out["fwd_mdd_1m"], 0.0, ">", -0.20)).astype(int),
        np.nan,
    )
    out["label_quality_1m_balanced"] = np.where(
        has,
        (
            (out["fwd_ret_1m"] >= 0.03)
            & _safe_metric(out["fwd_mdd_1m"], 0.0, ">", -0.15)
            & _safe_metric(out["fwd_sharpe_1m"], 1.0, ">", 0.0)
        ).astype(int),
        np.nan,
    )
    out["label_quality_1m_strict"] = np.where(
        has,
        (
            (out["fwd_ret_1m"] >= 0.05)
            & _safe_metric(out["fwd_mdd_1m"], 0.0, ">", -0.10)
            & _safe_metric(out["fwd_sharpe_1m"], 1.0, ">", 0.3)
        ).astype(int),
        np.nan,
    )
    out["label_bad_1m_strict"] = np.where(
        has,
        (
            (out["fwd_ret_1m"] <= -0.03)
            | _safe_metric(out["fwd_mdd_1m"], 0.0, "<=", -0.15)
            | _safe_metric(out["fwd_sharpe_1m"], 0.0, "<", -0.3)
        ).astype(int),
        np.nan,
    )
    return out


def _label_summary(df: pd.DataFrame, label: str) -> dict[str, Any]:
    sub = df[df[label].notna()].copy()
    positives = int(sub[label].sum()) if not sub.empty else 0
    return {
        "label": label,
        "description": LABEL_DEFS[label]["description"],
        "rows": int(len(sub)),
        "positive_rows": positives,
        "positive_rate": None if sub.empty else round(float(sub[label].mean()), 6),
    }


def run_experiment(asof: str, feature_set: str) -> dict[str, Any]:
    token = asof.replace("-", "")
    mart_path = REPORT_DIR / f"ai_overlay_training_mart_{token}.csv"
    if not mart_path.exists():
        raise FileNotFoundError(mart_path)
    df = pd.read_csv(mart_path, dtype={"ticker": str}, low_memory=False)
    df = add_refined_labels(df)

    evals: list[dict[str, Any]] = []
    for label in LABEL_DEFS:
        for kind in ("logistic", "gb"):
            _model, payload, _pred = _fit_model(df, label, kind, feature_set)
            payload["label_description"] = LABEL_DEFS[label]["description"]
            evals.append(payload)

    summary = [_label_summary(df, label) for label in LABEL_DEFS]
    eval_df = pd.DataFrame(evals)
    summary_df = pd.DataFrame(summary)

    out_csv = REPORT_DIR / f"ai_label_refinement_eval_{token}.csv"
    out_summary_csv = REPORT_DIR / f"ai_label_refinement_summary_{token}.csv"
    out_md = REPORT_DIR / f"ai_label_refinement_eval_{token}.md"
    out_json = REPORT_DIR / f"ai_label_refinement_eval_{token}.json"
    eval_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    summary_df.to_csv(out_summary_csv, index=False, encoding="utf-8-sig")

    lines = [
        f"# AI Label Refinement Experiment - {asof}",
        "",
        f"- feature_set: `{feature_set}`",
        f"- mart_rows: `{len(df)}`",
        "",
        "## Label Definitions",
        "",
        "| label | positive rate | positive rows | definition |",
        "|---|---:|---:|---|",
    ]
    for row in summary:
        rate = "-" if row["positive_rate"] is None else f"{row['positive_rate']:.2%}"
        lines.append(f"| {row['label']} | {rate} | {row['positive_rows']} | {row['description']} |")
    lines.extend(
        [
            "",
            "## Evaluation",
            "",
            "| label | model | auc | top30 1M return | top30 win rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in eval_df.to_dict(orient="records"):
        auc = "-" if pd.isna(row.get("auc")) else f"{float(row['auc']):.3f}"
        top = "-" if pd.isna(row.get("top30_avg_1m_return")) else f"{float(row['top30_avg_1m_return']):.2%}"
        win = "-" if pd.isna(row.get("top30_win_rate")) else f"{float(row['top30_win_rate']):.2%}"
        lines.append(f"| {row.get('label')} | {row.get('model_kind')} | {auc} | {top} | {win} |")

    gb = eval_df[eval_df["model_kind"] == "gb"].copy()
    if not gb.empty:
        lines.extend(["", "## GB Best", ""])
        for metric, label in [
            ("auc", "AUC"),
            ("top30_avg_1m_return", "top30 1M return"),
            ("top30_win_rate", "top30 win rate"),
        ]:
            best = gb.sort_values(metric, ascending=False).iloc[0]
            value = best[metric]
            if metric == "auc":
                text = f"{float(value):.3f}"
            else:
                text = f"{float(value):.2%}"
            lines.append(f"- best {label}: `{best['label']}` ({text})")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    payload = {
        "asof_date": asof,
        "feature_set": feature_set,
        "mart_rows": int(len(df)),
        "label_summary": summary,
        "evaluations": evals,
        "outputs": {
            "eval_csv": str(out_csv),
            "summary_csv": str(out_summary_csv),
            "eval_md": str(out_md),
        },
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI label refinement experiment.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--feature-set", default="kiwoom_dart", choices=["base", "kiwoom", "dart", "kiwoom_dart", "all"])
    args = parser.parse_args()
    result = run_experiment(args.asof, args.feature_set)
    print(json.dumps({"status": "ok", "asof_date": args.asof, "outputs": result["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
