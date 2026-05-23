from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / r"reports\ai_overlay_v01"
OUT_DB = ROOT / r"data\db\ai_learning.db"
MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
MODEL_NAME_KO = "퀀트후보검증AI"
LEGACY_MODEL_CODE = "AI-OVERLAY-V01"
HORIZONS = ["1w", "2w", "1m", "2m", "3m"]


def _load_inputs(asof: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    token = asof.replace("-", "")
    shadow_path = REPORT_DIR / f"ai_overlay_shadow_scores_{token}.csv"
    mart_path = REPORT_DIR / f"ai_overlay_training_mart_{token}.csv"
    if not shadow_path.exists():
        raise FileNotFoundError(shadow_path)
    if not mart_path.exists():
        raise FileNotFoundError(mart_path)
    shadow = pd.read_csv(shadow_path, dtype={"ticker": str}, low_memory=False)
    mart = pd.read_csv(mart_path, dtype={"ticker": str}, low_memory=False)
    return shadow, mart


def _merge_forward_returns(shadow: pd.DataFrame, mart: pd.DataFrame) -> pd.DataFrame:
    keys = ["scope_key", "model_id", "ticker", "event_date"]
    fwd_cols = [f"fwd_ret_{h}" for h in HORIZONS if f"fwd_ret_{h}" in mart.columns]
    risk_cols = [col for col in ["fwd_mdd_1m", "fwd_sharpe_1m", "is_live_event"] if col in mart.columns]
    keep = keys + fwd_cols + risk_cols
    base = mart[keep].drop_duplicates(keys)
    out = shadow.merge(base, on=keys, how="left")
    return out


def _metric_row(frame: pd.DataFrame, group_type: str, group_value: str, horizon: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    col = f"fwd_ret_{horizon}"
    vals = pd.to_numeric(frame.get(col), errors="coerce").dropna()
    row: dict[str, Any] = {
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "legacy_model_code": LEGACY_MODEL_CODE,
        "group_type": group_type,
        "group_value": group_value,
        "horizon": horizon,
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
                "median_mdd": None if mdd.empty else round(float(mdd.median()), 6),
                "sharpe_sample_count": int(len(sharpe)),
                "avg_sharpe": None if sharpe.empty else round(float(sharpe.mean()), 6),
                "median_sharpe": None if sharpe.empty else round(float(sharpe.median()), 6),
            }
        )
    if extra:
        row.update(extra)
    return row


def _summarize_group(frame: pd.DataFrame, group_type: str, group_value: str, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [_metric_row(frame, group_type, group_value, horizon, extra) for horizon in HORIZONS]


def _explode_tags(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in df.to_dict(orient="records"):
        tags = [tag.strip() for tag in str(row.get("ai_shadow_tags") or "OBSERVE").split(",") if tag.strip()]
        for tag in tags:
            item = dict(row)
            item["ai_shadow_tag_single"] = tag
            rows.append(item)
    return pd.DataFrame(rows)


def build_tracker(asof: str) -> dict[str, Any]:
    shadow, mart = _load_inputs(asof)
    merged = _merge_forward_returns(shadow, mart)
    rows: list[dict[str, Any]] = []

    rows.extend(_summarize_group(merged, "all", "all"))

    for value, frame in merged.groupby("ai_shadow_decision"):
        rows.extend(_summarize_group(frame, "decision", str(value)))

    exploded = _explode_tags(merged)
    if not exploded.empty:
        for value, frame in exploded.groupby("ai_shadow_tag_single"):
            rows.extend(_summarize_group(frame, "tag", str(value)))

    for (scope, decision), frame in merged.groupby(["scope_key", "ai_shadow_decision"]):
        rows.extend(_summarize_group(frame, "scope_decision", f"{scope}:{decision}", {"scope_key": scope}))

    for (scope, model_id, decision), frame in merged.groupby(["scope_key", "model_id", "ai_shadow_decision"]):
        rows.extend(
            _summarize_group(
                frame,
                "model_decision",
                f"{scope}:{model_id}:{decision}",
                {"scope_key": scope, "model_id": model_id},
            )
        )

    if "ai_model_specific_tag" in merged.columns:
        for value, frame in merged.groupby("ai_model_specific_tag"):
            rows.extend(_summarize_group(frame, "model_specific_tag", str(value)))

        for (scope, model_id, value), frame in merged.groupby(["scope_key", "model_id", "ai_model_specific_tag"]):
            rows.extend(
                _summarize_group(
                    frame,
                    "model_specific_model_tag",
                    f"{scope}:{model_id}:{value}",
                    {"scope_key": scope, "model_id": model_id},
                )
            )

    summary = pd.DataFrame(rows)
    summary["asof_date"] = asof
    summary["generated_at"] = datetime.now().isoformat(timespec="seconds")

    token = asof.replace("-", "")
    out_csv = REPORT_DIR / f"ai_shadow_performance_tracker_{token}.csv"
    out_json = REPORT_DIR / f"ai_shadow_performance_tracker_{token}.json"
    out_md = REPORT_DIR / f"ai_shadow_performance_tracker_{token}.md"
    summary.to_csv(out_csv, index=False, encoding="utf-8-sig")

    with sqlite3.connect(str(OUT_DB)) as con:
        summary.to_sql("ai_shadow_performance_tracker", con, if_exists="replace", index=False)

    payload = {
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "legacy_model_code": LEGACY_MODEL_CODE,
        "asof_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "shadow_rows": int(len(merged)),
        "summary_rows": int(len(summary)),
        "outputs": {
            "csv": str(out_csv),
            "json": str(out_json),
            "md": str(out_md),
            "db": str(OUT_DB),
        },
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# AI Shadow Performance Tracker - {asof}",
        "",
        f"- model_code: `{MODEL_CODE}`",
        f"- model_name_ko: `{MODEL_NAME_KO}`",
        f"- legacy_model_code: `{LEGACY_MODEL_CODE}`",
        f"- shadow_rows: `{len(merged)}`",
        f"- summary_rows: `{len(summary)}`",
        "",
        "## Decision Summary",
        "",
        "| decision | horizon | samples | avg return | win rate |",
        "|---|---:|---:|---:|---:|",
    ]
    decision = summary[summary["group_type"] == "decision"].copy()
    for _, row in decision.sort_values(["group_value", "horizon"]).iterrows():
        avg = "N/A" if pd.isna(row["avg_return"]) else f"{float(row['avg_return']):.2%}"
        win = "N/A" if pd.isna(row["win_rate"]) else f"{float(row['win_rate']):.2%}"
        lines.append(f"| {row['group_value']} | {row['horizon']} | {int(row['sample_count'])} | {avg} | {win} |")

    lines.extend(["", "## Tag Summary", "", "| tag | horizon | samples | avg return | win rate |", "|---|---:|---:|---:|---:|"])
    tag = summary[summary["group_type"] == "tag"].copy()
    for _, row in tag.sort_values(["group_value", "horizon"]).iterrows():
        avg = "N/A" if pd.isna(row["avg_return"]) else f"{float(row['avg_return']):.2%}"
        win = "N/A" if pd.isna(row["win_rate"]) else f"{float(row['win_rate']):.2%}"
        lines.append(f"| {row['group_value']} | {row['horizon']} | {int(row['sample_count'])} | {avg} | {win} |")

    if "model_specific_tag" in summary["group_type"].unique():
        lines.extend(["", "## Model-Specific Tag Summary", "", "| tag | horizon | samples | avg return | win rate |", "|---|---:|---:|---:|---:|"])
        model_specific_tag = summary[summary["group_type"] == "model_specific_tag"].copy()
        for _, row in model_specific_tag.sort_values(["group_value", "horizon"]).iterrows():
            avg = "N/A" if pd.isna(row["avg_return"]) else f"{float(row['avg_return']):.2%}"
            win = "N/A" if pd.isna(row["win_rate"]) else f"{float(row['win_rate']):.2%}"
            lines.append(f"| {row['group_value']} | {row['horizon']} | {int(row['sample_count'])} | {avg} | {win} |")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI shadow performance tracker.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    result = build_tracker(args.asof)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
