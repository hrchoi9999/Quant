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

HORIZONS = {
    "1w": {"return_col": "fwd_ret_1w", "threshold": 0.01},
    "2w": {"return_col": "fwd_ret_2w", "threshold": 0.015},
    "1m": {"return_col": "fwd_ret_1m", "threshold": 0.03},
    "2m": {"return_col": "fwd_ret_2m", "threshold": 0.05},
    "3m": {"return_col": "fwd_ret_3m", "threshold": 0.07},
}


def add_horizon_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for horizon, spec in HORIZONS.items():
        col = spec["return_col"]
        threshold = float(spec["threshold"])
        if col not in out.columns:
            out[f"label_quality_{horizon}"] = np.nan
            out[f"label_positive_{horizon}"] = np.nan
            continue
        has = out[col].notna()
        out[f"label_positive_{horizon}"] = np.where(has, (out[col] > 0).astype(int), np.nan)
        out[f"label_quality_{horizon}"] = np.where(has, (out[col] >= threshold).astype(int), np.nan)
    return out


def _label_summary(df: pd.DataFrame, label: str) -> dict[str, Any]:
    sub = df[df[label].notna()].copy()
    live = sub[sub["is_live_event"].fillna(0).astype(int) == 1] if "is_live_event" in sub.columns else pd.DataFrame()
    return {
        "label": label,
        "rows": int(len(sub)),
        "positive_rows": int(sub[label].sum()) if not sub.empty else 0,
        "positive_rate": None if sub.empty else round(float(sub[label].mean()), 6),
        "live_rows": int(len(live)),
        "live_positive_rows": int(live[label].sum()) if not live.empty else 0,
        "live_positive_rate": None if live.empty else round(float(live[label].mean()), 6),
    }


def _eval_labels(df: pd.DataFrame, labels: list[str], feature_set: str) -> pd.DataFrame:
    evals: list[dict[str, Any]] = []
    for label in labels:
        for kind in ("logistic", "gb"):
            _model, payload, _pred = _fit_model(df, label, kind, feature_set)
            evals.append(payload)
    return pd.DataFrame(evals)


def run_experiment(asof: str, feature_set: str) -> dict[str, Any]:
    token = asof.replace("-", "")
    mart_path = REPORT_DIR / f"ai_overlay_training_mart_{token}.csv"
    if not mart_path.exists():
        raise FileNotFoundError(mart_path)
    df = pd.read_csv(mart_path, dtype={"ticker": str}, low_memory=False)
    df = add_horizon_labels(df)
    labels = []
    for horizon in HORIZONS:
        labels.extend([f"label_positive_{horizon}", f"label_quality_{horizon}"])

    summary = [_label_summary(df, label) for label in labels]
    eval_df = _eval_labels(df, labels, feature_set)
    summary_df = pd.DataFrame(summary)

    out_eval_csv = REPORT_DIR / f"ai_horizon_label_eval_{token}.csv"
    out_summary_csv = REPORT_DIR / f"ai_horizon_label_summary_{token}.csv"
    out_md = REPORT_DIR / f"ai_horizon_label_eval_{token}.md"
    out_json = REPORT_DIR / f"ai_horizon_label_eval_{token}.json"
    eval_df.to_csv(out_eval_csv, index=False, encoding="utf-8-sig")
    summary_df.to_csv(out_summary_csv, index=False, encoding="utf-8-sig")

    lines = [
        f"# AI Horizon Label Experiment - {asof}",
        "",
        f"- feature_set: `{feature_set}`",
        f"- mart_rows: `{len(df)}`",
        "",
        "## Perspective Split",
        "",
        "- `rows` and `positive_rate` are reconstructed/backtest-history labels.",
        "- `live_rows` and `live_positive_rate` are actual-operation labels after each model's live start date.",
        "- The model training results below are based on reconstructed/backtest-history labels because live samples are still small.",
        "",
        "## Label Coverage",
        "",
        "| label | rows | positive rate | live rows | live positive rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary:
        pr = "-" if row["positive_rate"] is None else f"{row['positive_rate']:.2%}"
        lpr = "-" if row["live_positive_rate"] is None else f"{row['live_positive_rate']:.2%}"
        lines.append(f"| {row['label']} | {row['rows']} | {pr} | {row['live_rows']} | {lpr} |")

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
        lines.extend(["", "## GB Best By AUC", ""])
        for _, row in gb.sort_values("auc", ascending=False).head(5).iterrows():
            top = "-" if pd.isna(row.get("top30_avg_1m_return")) else f"{float(row['top30_avg_1m_return']):.2%}"
            lines.append(f"- `{row['label']}`: AUC `{float(row['auc']):.3f}`, top30 1M `{top}`")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    payload = {
        "asof_date": asof,
        "feature_set": feature_set,
        "mart_rows": int(len(df)),
        "label_summary": summary,
        "evaluations": eval_df.to_dict(orient="records"),
        "outputs": {
            "eval_csv": str(out_eval_csv),
            "summary_csv": str(out_summary_csv),
            "eval_md": str(out_md),
        },
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI horizon label experiment.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--feature-set", default="kiwoom_dart", choices=["base", "kiwoom", "dart", "kiwoom_dart", "all"])
    args = parser.parse_args()
    result = run_experiment(args.asof, args.feature_set)
    print(json.dumps({"status": "ok", "asof_date": args.asof, "outputs": result["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
