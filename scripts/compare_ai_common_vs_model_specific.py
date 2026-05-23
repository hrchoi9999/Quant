from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / r"reports\ai_overlay_v01"
HORIZONS = ["1w", "2w", "1m", "2m", "3m"]


def _load_inputs(asof: str) -> pd.DataFrame:
    token = asof.replace("-", "")
    shadow_path = REPORT_DIR / f"ai_overlay_shadow_scores_{token}.csv"
    mart_path = REPORT_DIR / f"ai_overlay_training_mart_{token}.csv"
    if not shadow_path.exists():
        raise FileNotFoundError(shadow_path)
    if not mart_path.exists():
        raise FileNotFoundError(mart_path)
    shadow = pd.read_csv(shadow_path, dtype={"ticker": str}, low_memory=False)
    mart = pd.read_csv(mart_path, dtype={"ticker": str}, low_memory=False)
    keys = ["scope_key", "model_id", "ticker", "event_date"]
    fwd_cols = [f"fwd_ret_{h}" for h in HORIZONS if f"fwd_ret_{h}" in mart.columns]
    risk_cols = [col for col in ["fwd_mdd_1m", "fwd_sharpe_1m"] if col in mart.columns]
    base = mart[keys + fwd_cols + risk_cols].drop_duplicates(keys)
    merged = shadow.merge(base, on=keys, how="left")
    if "ai_model_specific_tag" not in merged.columns:
        raise RuntimeError("ai_model_specific_tag is missing. Rebuild AI overlay first.")
    return merged


def _common_bucket(value: Any) -> str:
    text = str(value or "")
    if text in {"AI_HIGH_CONVICTION", "AI_CONFIRM"}:
        return "COMMON_CONFIRM"
    if text == "AI_RISK_REVIEW":
        return "COMMON_RISK"
    return "COMMON_OBSERVE"


def _model_bucket(value: Any) -> str:
    text = str(value or "")
    if text == "MS_CONFIRM":
        return "MS_CONFIRM"
    if text == "MS_RISK_REVIEW":
        return "MS_RISK"
    if text == "MS_FALLBACK_COMMON":
        return "MS_FALLBACK"
    return "MS_OBSERVE"


def _combo_bucket(row: pd.Series) -> str:
    common = row["common_ai_bucket"]
    model = row["model_ai_bucket"]
    if common == "COMMON_CONFIRM" and model == "MS_CONFIRM":
        return "both_confirm"
    if common == "COMMON_RISK" and model == "MS_RISK":
        return "both_risk"
    if common != "COMMON_CONFIRM" and model == "MS_CONFIRM":
        return "model_only_confirm"
    if common == "COMMON_CONFIRM" and model != "MS_CONFIRM":
        return "common_only_confirm"
    if common != "COMMON_RISK" and model == "MS_RISK":
        return "model_only_risk"
    if common == "COMMON_RISK" and model != "MS_RISK":
        return "common_only_risk"
    if model == "MS_FALLBACK":
        return "model_fallback"
    return "both_observe_or_neutral"


def _metric_row(frame: pd.DataFrame, group_type: str, group_value: str, horizon: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    col = f"fwd_ret_{horizon}"
    vals = pd.to_numeric(frame.get(col), errors="coerce").dropna()
    row: dict[str, Any] = {
        "group_type": group_type,
        "group_value": group_value,
        "horizon": horizon,
        "row_count": int(len(frame)),
        "sample_count": int(len(vals)),
        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
        "median_return": None if vals.empty else round(float(vals.median()), 6),
        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
    }
    if horizon == "1m":
        mdd = pd.to_numeric(frame.get("fwd_mdd_1m"), errors="coerce").dropna()
        sharpe = pd.to_numeric(frame.get("fwd_sharpe_1m"), errors="coerce").dropna()
        row.update(
            {
                "mdd_sample_count": int(len(mdd)),
                "avg_mdd": None if mdd.empty else round(float(mdd.mean()), 6),
                "sharpe_sample_count": int(len(sharpe)),
                "avg_sharpe": None if sharpe.empty else round(float(sharpe.mean()), 6),
            }
        )
    if extra:
        row.update(extra)
    return row


def _summarize(frame: pd.DataFrame, group_type: str, group_value: str, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [_metric_row(frame, group_type, group_value, horizon, extra) for horizon in HORIZONS]


def _fmt_pct(value: Any) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.2%}"


def _matrix_markdown(matrix: pd.DataFrame) -> list[str]:
    cols = [str(col) for col in matrix.columns.tolist()]
    lines = ["| common \\ model | " + " | ".join(cols) + " |"]
    lines.append("|---|" + "|".join(["---:"] * len(cols)) + "|")
    for idx, row in matrix.iterrows():
        values = [str(int(row[col])) for col in matrix.columns]
        lines.append(f"| `{idx}` | " + " | ".join(values) + " |")
    return lines


def compare(asof: str) -> dict[str, Any]:
    df = _load_inputs(asof)
    df["common_ai_bucket"] = df["ai_shadow_decision"].map(_common_bucket)
    df["model_ai_bucket"] = df["ai_model_specific_tag"].map(_model_bucket)
    df["comparison_bucket"] = df.apply(_combo_bucket, axis=1)

    rows: list[dict[str, Any]] = []
    for value, frame in df.groupby("common_ai_bucket"):
        rows.extend(_summarize(frame, "common_ai_bucket", str(value)))
    for value, frame in df.groupby("model_ai_bucket"):
        rows.extend(_summarize(frame, "model_ai_bucket", str(value)))
    for value, frame in df.groupby("comparison_bucket"):
        rows.extend(_summarize(frame, "comparison_bucket", str(value)))
    for (scope, model_id, value), frame in df.groupby(["scope_key", "model_id", "comparison_bucket"]):
        rows.extend(
            _summarize(
                frame,
                "model_comparison_bucket",
                f"{scope}:{model_id}:{value}",
                {"scope_key": scope, "model_id": model_id},
            )
        )

    summary = pd.DataFrame(rows)
    matrix = (
        df.groupby(["common_ai_bucket", "model_ai_bucket"], as_index=False)
        .size()
        .pivot(index="common_ai_bucket", columns="model_ai_bucket", values="size")
        .fillna(0)
        .astype(int)
    )

    token = asof.replace("-", "")
    detail_csv = REPORT_DIR / f"ai_common_vs_model_specific_detail_{token}.csv"
    summary_csv = REPORT_DIR / f"ai_common_vs_model_specific_summary_{token}.csv"
    matrix_csv = REPORT_DIR / f"ai_common_vs_model_specific_matrix_{token}.csv"
    json_path = REPORT_DIR / f"ai_common_vs_model_specific_{token}.json"
    md_path = REPORT_DIR / f"ai_common_vs_model_specific_{token}.md"

    df.to_csv(detail_csv, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    matrix.to_csv(matrix_csv, encoding="utf-8-sig")

    one_month = summary[summary["horizon"] == "1m"].copy()
    combo_1m = one_month[one_month["group_type"] == "comparison_bucket"].sort_values("avg_return", ascending=False, na_position="last")
    common_1m = one_month[one_month["group_type"] == "common_ai_bucket"].sort_values("avg_return", ascending=False, na_position="last")
    model_1m = one_month[one_month["group_type"] == "model_ai_bucket"].sort_values("avg_return", ascending=False, na_position="last")

    lines = [
        f"# Common AI vs Model-Specific AI - {asof}",
        "",
        "## Scope",
        "",
        "- Basis: reconstructed AI shadow rows, not live-only performance.",
        f"- Rows: `{len(df)}`",
        "",
        "## Decision Matrix",
        "",
        *_matrix_markdown(matrix),
        "",
        "## 1M Performance By Common AI",
        "",
        "| common bucket | rows | samples | avg return | win rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in common_1m.itertuples(index=False):
        lines.append(f"| `{row.group_value}` | {int(row.row_count)} | {int(row.sample_count)} | {_fmt_pct(row.avg_return)} | {_fmt_pct(row.win_rate)} |")

    lines.extend(["", "## 1M Performance By Model-Specific AI", "", "| model bucket | rows | samples | avg return | win rate |", "|---|---:|---:|---:|---:|"])
    for row in model_1m.itertuples(index=False):
        lines.append(f"| `{row.group_value}` | {int(row.row_count)} | {int(row.sample_count)} | {_fmt_pct(row.avg_return)} | {_fmt_pct(row.win_rate)} |")

    lines.extend(["", "## 1M Performance By Comparison Bucket", "", "| bucket | rows | samples | avg return | win rate |", "|---|---:|---:|---:|---:|"])
    for row in combo_1m.itertuples(index=False):
        lines.append(f"| `{row.group_value}` | {int(row.row_count)} | {int(row.sample_count)} | {_fmt_pct(row.avg_return)} | {_fmt_pct(row.win_rate)} |")

    payload = {
        "status": "ok",
        "asof_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "outputs": {
            "detail_csv": str(detail_csv),
            "summary_csv": str(summary_csv),
            "matrix_csv": str(matrix_csv),
            "json": str(json_path),
            "md": str(md_path),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare common AI overlay tags against model-specific AI tags.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.asof), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
