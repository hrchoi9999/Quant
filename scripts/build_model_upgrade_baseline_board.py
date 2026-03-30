from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
BASELINE_CSV = PROJECT_ROOT / r"reports\score_correlation_review\20260330\selected_vs_not_selected_3m_6m_1y_summary.csv"
REGISTRY_JSON = PROJECT_ROOT / r"data\configs\model_upgrade_experiment_registry_20260330.json"
OUTDIR = PROJECT_ROOT / r"reports\model_upgrade_research\20260330"


def load_baseline() -> pd.DataFrame:
    df = pd.read_csv(BASELINE_CSV)
    pivot = (
        df.pivot_table(
            index=["model_code", "horizon"],
            columns="scope",
            values=["avg_return", "avg_mdd", "median_return", "median_mdd"],
        )
        .sort_index()
    )
    pivot.columns = [f"{a}_{b}" for a, b in pivot.columns]
    pivot = pivot.reset_index()
    pivot["avg_return_delta"] = pivot["avg_return_selected_only"] - pivot["avg_return_not_selected"]
    pivot["avg_mdd_delta"] = pivot["avg_mdd_selected_only"] - pivot["avg_mdd_not_selected"]
    return pivot


def load_registry() -> pd.DataFrame:
    raw = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    rows = []
    for exp in raw.get("experiments", []):
        rows.append({
            "experiment_id": exp["experiment_id"],
            "model_code": exp["model_code"],
            "priority": exp["priority"],
            "status": exp["status"],
            "objective": exp["objective"],
            "hypothesis": exp["hypothesis"],
            "knobs": ", ".join(exp.get("knobs", [])),
            "success_rules": " | ".join(exp.get("success_rules", [])),
        })
    return pd.DataFrame(rows).sort_values(["priority", "model_code", "experiment_id"])


def render_markdown(baseline: pd.DataFrame, registry: pd.DataFrame) -> str:
    lines = ["# Model Upgrade Baseline Board", ""]
    lines.append("## Universe-relative baseline")
    lines.append("| Model | Horizon | Selected Avg Return | Not Selected Avg Return | Return Delta | Selected Avg MDD | Not Selected Avg MDD | MDD Delta |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in baseline.itertuples(index=False):
        lines.append(
            f"| {r.model_code} | {r.horizon} | {r.avg_return_selected_only:.2%} | {r.avg_return_not_selected:.2%} | {r.avg_return_delta:.2%} | {r.avg_mdd_selected_only:.2%} | {r.avg_mdd_not_selected:.2%} | {r.avg_mdd_delta:.2%} |"
        )
    lines.append("")
    lines.append("## Experiment queue")
    lines.append("| Priority | Experiment ID | Model | Status | Knobs |")
    lines.append("|---:|---|---|---|---|")
    for r in registry.itertuples(index=False):
        lines.append(f"| {r.priority} | {r.experiment_id} | {r.model_code} | {r.status} | {r.knobs} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    baseline = load_baseline()
    registry = load_registry()
    baseline.to_csv(OUTDIR / "model_upgrade_baseline_board.csv", index=False, encoding="utf-8-sig")
    registry.to_csv(OUTDIR / "model_upgrade_experiment_queue.csv", index=False, encoding="utf-8-sig")
    (OUTDIR / "model_upgrade_baseline_board.md").write_text(render_markdown(baseline, registry), encoding="utf-8")
    print("[ok] model upgrade baseline board generated")


if __name__ == "__main__":
    main()
