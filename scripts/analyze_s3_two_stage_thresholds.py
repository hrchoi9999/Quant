from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
BASE_DIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_MODELING\logistic_regression"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260331\S3_TWO_STAGE_THRESHOLD_ANALYSIS"
THRESHOLDS = [round(x, 3) for x in [0.45, 0.47, 0.49, 0.50, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58]]


def evaluate_thresholds(pred_df: pd.DataFrame, stage_name: str):
    rows = []
    by_h_rows = []
    for threshold in THRESHOLDS:
        window_rows = []
        for (horizon, signal_date), g in pred_df.groupby(["horizon", "signal_date"]):
            selected = g[g["pred_prob"] >= threshold].copy()
            pos_n = int(g["label"].sum())
            hits = int(selected["label"].sum())
            base_rate = float(g["label"].mean()) if len(g) else 0.0
            precision = float(selected["label"].mean()) if len(selected) else 0.0
            selected_n = int(len(selected))
            window_rows.append({
                "horizon": horizon,
                "signal_date": signal_date,
                "threshold": threshold,
                "candidate_pool_n": int(len(g)),
                "selected_n": selected_n,
                "positive_n": pos_n,
                "hits": hits,
                "base_rate": base_rate,
                "precision": precision,
                "capture_rate": float(hits / pos_n) if pos_n else None,
                "lift": float(precision / base_rate) if base_rate and selected_n > 0 else None,
                "selection_rate": float(selected_n / len(g)) if len(g) else 0.0,
            })
        win_df = pd.DataFrame(window_rows)
        overall = win_df.groupby(lambda _: 0).agg(
            windows=("signal_date", "size"),
            avg_candidate_pool_n=("candidate_pool_n", "mean"),
            avg_selected_n=("selected_n", "mean"),
            total_positive_n=("positive_n", "sum"),
            total_hits=("hits", "sum"),
            avg_base_rate=("base_rate", "mean"),
            avg_precision=("precision", "mean"),
            avg_capture_rate=("capture_rate", "mean"),
            avg_lift=("lift", "mean"),
            avg_selection_rate=("selection_rate", "mean"),
        ).reset_index(drop=True)
        overall.insert(0, "threshold", threshold)
        overall.insert(0, "stage", stage_name)
        rows.append(overall)

        by_h = win_df.groupby("horizon").agg(
            windows=("signal_date", "size"),
            avg_candidate_pool_n=("candidate_pool_n", "mean"),
            avg_selected_n=("selected_n", "mean"),
            total_positive_n=("positive_n", "sum"),
            total_hits=("hits", "sum"),
            avg_base_rate=("base_rate", "mean"),
            avg_precision=("precision", "mean"),
            avg_capture_rate=("capture_rate", "mean"),
            avg_lift=("lift", "mean"),
            avg_selection_rate=("selection_rate", "mean"),
        ).reset_index()
        by_h.insert(0, "threshold", threshold)
        by_h.insert(0, "stage", stage_name)
        by_h_rows.append(by_h)
    return pd.concat(rows, ignore_index=True), pd.concat(by_h_rows, ignore_index=True)


def render_md(stage1: pd.DataFrame, stage2: pd.DataFrame) -> str:
    lines = ["# S3 Two-Stage Threshold Analysis", ""]
    lines.append("- model: `logistic_regression`")
    lines.append("- labels: `2~4 steps within`")
    lines.append("")
    for name, df in [("stage1", stage1), ("stage2", stage2)]:
        lines.append(f"## {name}")
        lines.append("| Threshold | Avg selected | Precision | Capture | Lift | Selection rate |")
        lines.append("|---:|---:|---:|---:|---:|---:|")
        for r in df.sort_values("threshold").itertuples(index=False):
            lines.append(
                f"| {r.threshold:.3f} | {r.avg_selected_n:.2f} | {r.avg_precision:.2%} | {r.avg_capture_rate:.2%} | {r.avg_lift:.2f}x | {r.avg_selection_rate:.2%} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    stage1_pred = pd.read_csv(BASE_DIR / 'stage1_test_predictions.csv', parse_dates=['signal_date'])
    stage2_pred = pd.read_csv(BASE_DIR / 'stage2_test_predictions.csv', parse_dates=['signal_date'])
    stage1_overall, stage1_by_h = evaluate_thresholds(stage1_pred, 'stage1')
    stage2_overall, stage2_by_h = evaluate_thresholds(stage2_pred, 'stage2')
    stage1_overall.to_csv(OUTDIR / 'stage1_threshold_summary.csv', index=False, encoding='utf-8-sig')
    stage1_by_h.to_csv(OUTDIR / 'stage1_threshold_by_horizon.csv', index=False, encoding='utf-8-sig')
    stage2_overall.to_csv(OUTDIR / 'stage2_threshold_summary.csv', index=False, encoding='utf-8-sig')
    stage2_by_h.to_csv(OUTDIR / 'stage2_threshold_by_horizon.csv', index=False, encoding='utf-8-sig')
    (OUTDIR / 's3_two_stage_threshold_analysis.md').write_text(render_md(stage1_overall, stage2_overall), encoding='utf-8')
    print(stage1_overall.to_string(index=False))
    print()
    print(stage2_overall.to_string(index=False))


if __name__ == '__main__':
    main()
