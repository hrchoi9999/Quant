from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / r"reports\ai_overlay_v01"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
OUT_DB = ROOT / r"data\db\ai_learning.db"
MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
MODEL_NAME_KO = "퀀트후보검증AI"
LEGACY_MODEL_CODE = "AI-OVERLAY-V01"
HORIZONS = ["1w", "2w", "1m", "2m", "3m"]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"ticker": str}, low_memory=False)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _none_if_nan(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, float):
        return round(float(value), 6)
    if isinstance(value, (int, str, bool)):
        return value
    return value


def _rows(df: pd.DataFrame, columns: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    if df.empty:
        return []
    use = df if columns is None else df[[col for col in columns if col in df.columns]].copy()
    if limit is not None:
        use = use.head(limit)
    return [{key: _none_if_nan(value) for key, value in row.items()} for row in use.to_dict(orient="records")]


def _horizon_rows(summary: pd.DataFrame, group_type: str, horizon: str = "1m") -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    out = summary[(summary["group_type"] == group_type) & (summary["horizon"] == horizon)].copy()
    return out.sort_values(["avg_return", "win_rate"], ascending=False, na_position="last")


def _eval_summary(eval_payload: dict[str, Any]) -> dict[str, Any]:
    evaluations = pd.DataFrame(eval_payload.get("evaluations") or [])
    if evaluations.empty or "training_scope" not in evaluations.columns:
        return {
            "trained_models": [],
            "fallback_models": [],
            "evaluation_rows": [],
        }
    model_specific = evaluations[evaluations["training_scope"].eq("model_specific")].copy()
    trained = model_specific[model_specific["status"].eq("ok") & model_specific["label"].eq("label_quality_1m")].copy()
    skipped = model_specific[model_specific["status"].eq("skipped") & model_specific["label"].eq("label_quality_1m")].copy()
    trained = trained.sort_values(["scope_key", "model_id"])
    skipped = skipped.sort_values(["scope_key", "model_id"])
    return {
        "trained_models": _rows(
            trained,
            [
                "scope_key",
                "model_id",
                "label",
                "label_rows",
                "train_rows",
                "test_rows",
                "auc",
                "top30_avg_1m_return",
                "top30_win_rate",
            ],
        ),
        "fallback_models": _rows(skipped, ["scope_key", "model_id", "label_rows", "reason"]),
        "evaluation_rows": _rows(
            model_specific,
            [
                "scope_key",
                "model_id",
                "label",
                "status",
                "reason",
                "label_rows",
                "train_rows",
                "test_rows",
                "auc",
                "top30_avg_1m_return",
                "top30_win_rate",
            ],
        ),
    }


def build_payload(asof: str) -> dict[str, Any]:
    token = asof.replace("-", "")
    common_summary = _read_csv(REPORT_DIR / f"ai_common_vs_model_specific_summary_{token}.csv")
    common_matrix = _read_csv(REPORT_DIR / f"ai_common_vs_model_specific_matrix_{token}.csv")
    reconstructed = _read_csv(REPORT_DIR / f"ai_shadow_performance_tracker_{token}.csv")
    live_summary = _read_csv(REPORT_DIR / f"ai_live_shadow_tracker_summary_{token}_to_{token}.csv")
    shadow_scores = _read_csv(REPORT_DIR / f"ai_overlay_shadow_scores_{token}.csv")
    eval_payload = _read_json(REPORT_DIR / f"ai_overlay_model_eval_{token}.json")

    if common_summary.empty:
        raise SystemExit(f"missing comparison summary for {asof}; run compare_ai_common_vs_model_specific.py first")
    if reconstructed.empty:
        raise SystemExit(f"missing reconstructed tracker for {asof}; run build_ai_shadow_performance_tracker.py first")
    if shadow_scores.empty:
        raise SystemExit(f"missing shadow scores for {asof}; run build_ai_overlay_v01.py first")

    live_horizon_status = []
    if not live_summary.empty:
        for horizon in HORIZONS:
            frame = live_summary[live_summary["horizon"].eq(horizon)]
            live_horizon_status.append(
                {
                    "horizon": horizon,
                    "sample_count": int(pd.to_numeric(frame.get("sample_count"), errors="coerce").fillna(0).sum()),
                    "available": bool(pd.to_numeric(frame.get("sample_count"), errors="coerce").fillna(0).sum() > 0),
                }
            )

    shadow_counts = []
    for cols in (["common_ai_bucket"], ["model_ai_bucket"], ["comparison_bucket"]):
        col = cols[0]
        detail_path = REPORT_DIR / f"ai_common_vs_model_specific_detail_{token}.csv"
        detail = _read_csv(detail_path)
        if not detail.empty and col in detail.columns:
            counts = detail.groupby(col, as_index=False).size().rename(columns={col: "bucket", "size": "count"})
            counts["bucket_type"] = col
            shadow_counts.extend(_rows(counts[["bucket_type", "bucket", "count"]]))

    payload = {
        "source_name": "quant_ai_shadow_observation",
        "schema_version": "1.0",
        "visibility": "admin_only",
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "legacy_model_code": LEGACY_MODEL_CODE,
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "timezone": "Asia/Seoul",
        "metric_basis": {
            "reconstructed": "historical/reconstructed shadow rows; research validation only",
            "live": "actual prices after AI shadow scored_at date; primary operating observation",
        },
        "description": "퀀트후보검증AI shadow 관찰용 payload. 공통 AI와 모델별 AI의 분리력 및 live-only 추적 상태를 admin 화면에 제공한다.",
        "horizons": HORIZONS,
        "model_specific_training": _eval_summary(eval_payload),
        "decision_matrix": _rows(common_matrix),
        "shadow_counts": shadow_counts,
        "reconstructed_summary": {
            "common_ai_1m": _rows(
                _horizon_rows(common_summary, "common_ai_bucket"),
                ["group_value", "row_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"],
            ),
            "model_specific_ai_1m": _rows(
                _horizon_rows(common_summary, "model_ai_bucket"),
                ["group_value", "row_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"],
            ),
            "comparison_bucket_1m": _rows(
                _horizon_rows(common_summary, "comparison_bucket"),
                ["group_value", "row_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"],
            ),
            "reconstructed_model_specific_tag_1m": _rows(
                _horizon_rows(reconstructed, "model_specific_tag"),
                ["group_value", "row_count", "sample_count", "avg_return", "median_return", "win_rate", "avg_mdd", "avg_sharpe"],
            ),
        },
        "live_summary": {
            "status": "pending_samples" if live_summary.empty or not any(item["available"] for item in live_horizon_status) else "active",
            "horizon_status": live_horizon_status,
            "decision_rows": _rows(live_summary[live_summary.get("group_type", pd.Series(dtype=str)).eq("decision")]) if not live_summary.empty else [],
            "tag_rows": _rows(live_summary[live_summary.get("group_type", pd.Series(dtype=str)).eq("tag")]) if not live_summary.empty else [],
            "model_specific_tag_rows": _rows(live_summary[live_summary.get("group_type", pd.Series(dtype=str)).eq("model_specific_tag")]) if not live_summary.empty else [],
        },
        "latest_shadow_sample": _rows(
            shadow_scores.sort_values(["ai_model_specific_tag", "ai_shadow_decision", "scope_key", "model_id", "ticker"]),
            [
                "scope_key",
                "model_id",
                "ticker",
                "name",
                "event_date",
                "ai_shadow_decision",
                "ai_shadow_tags",
                "ai_model_specific_tag",
                "ai_quality_prob",
                "ai_risk_prob",
                "ai_model_specific_quality_prob",
                "ai_model_specific_risk_prob",
            ],
            limit=100,
        ),
        "outputs": {
            "db": str(OUT_DB),
            "report_dir": str(REPORT_DIR),
        },
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build admin AI shadow observation payload for QS/redbot.")
    parser.add_argument("--asof", required=True)
    parser.add_argument("--out", default=str(ADMIN_CURRENT_DIR / "ai_shadow_observation.json"))
    args = parser.parse_args()
    payload = build_payload(args.asof)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "as_of_date": payload["as_of_date"],
                "generated_at": payload["generated_at"],
                "out": str(out),
                "trained_model_count": len(payload["model_specific_training"]["trained_models"]),
                "fallback_model_count": len(payload["model_specific_training"]["fallback_models"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
