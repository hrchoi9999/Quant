from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / r"reports\ai_overlay_backtest"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"

POLICY_LABELS = {
    "risk_tilt_renorm": "하락위험예측AI 중심",
    "valuation_tilt_renorm": "주가수준평가AI 중심",
    "rank_delta_tilt_renorm": "후보순위조정AI 중심",
    "combo_equal_renorm": "하락위험/주가수준/후보순위 조합",
    "combo_equal_cash": "하락위험/주가수준/후보순위 조합, 현금 보유",
}

AI_COMPONENTS = [
    {
        "model_code": "AI-DOWNSIDE-RISK-V01",
        "model_name_ko": "하락위험예측AI",
        "role": "하락위험 tag 기반 비중 축소/caution",
    },
    {
        "model_code": "AI-GROWTH-VALUATION-V01",
        "model_name_ko": "주가수준평가AI",
        "role": "valuation state 기반 비중 tilt",
    },
    {
        "model_code": "AI-CANDIDATE-RANK-DELTA-V01",
        "model_name_ko": "후보순위조정AI",
        "role": "다음 리밸런싱 순위 변화 기반 비중/rank 조정",
    },
]


def _token(asof: str) -> str:
    return str(asof).replace("-", "")


def _safe_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if np.isnan(value):
            return None
        return round(float(value), 8)
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: _safe_value(value) for key, value in row.items()} for row in df.to_dict(orient="records")]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return pd.read_csv(path, low_memory=False)


def _enrich_model_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["mapped_policy_label_ko"] = out["mapped_policy"].map(POLICY_LABELS).fillna(out["mapped_policy"])
    out["return_delta_pctp"] = pd.to_numeric(out["avg_return_delta"], errors="coerce") * 100.0
    out["win_rate_delta_pctp"] = pd.to_numeric(out["win_rate_delta"], errors="coerce") * 100.0
    out["mdd_delta_pctp"] = pd.to_numeric(out["nav_mdd_delta"], errors="coerce") * 100.0
    out["overlay_result_tag"] = np.select(
        [
            out["avg_return_delta"].gt(0) & out["nav_mdd_delta"].ge(0),
            out["avg_return_delta"].gt(0) & out["nav_mdd_delta"].lt(0),
            out["avg_return_delta"].le(0),
        ],
        ["return_and_risk_improved", "return_up_risk_check", "no_improvement"],
        default="insufficient_data",
    )
    out.loc[out["avg_return_delta"].isna(), "overlay_result_tag"] = "insufficient_data"
    out["overlay_result_label_ko"] = out["overlay_result_tag"].map(
        {
            "return_and_risk_improved": "수익/리스크 개선",
            "return_up_risk_check": "수익 개선, 리스크 점검",
            "no_improvement": "개선 부족",
            "insufficient_data": "관찰 부족",
        }
    )
    return out


def _enrich_family_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["return_delta_pctp"] = pd.to_numeric(out["avg_return_delta"], errors="coerce") * 100.0
    out["win_rate_delta_pctp"] = pd.to_numeric(out["win_rate_delta"], errors="coerce") * 100.0
    out["mdd_delta_pctp"] = pd.to_numeric(out["nav_mdd_delta"], errors="coerce") * 100.0
    out["overlay_result_tag"] = np.select(
        [
            out["avg_return_delta"].gt(0) & out["nav_mdd_delta"].ge(0),
            out["avg_return_delta"].gt(0) & out["nav_mdd_delta"].lt(0),
            out["avg_return_delta"].le(0),
        ],
        ["return_and_risk_improved", "return_up_risk_check", "no_improvement"],
        default="insufficient_data",
    )
    out.loc[out["avg_return_delta"].isna(), "overlay_result_tag"] = "insufficient_data"
    return out


def build_payloads(asof: str) -> dict[str, Any]:
    token = _token(asof)
    model_path = REPORT_DIR / f"ai_overlay_policy_map_vs_baseline_by_model_{token}.csv"
    family_path = REPORT_DIR / f"ai_overlay_policy_map_vs_baseline_by_family_{token}.csv"
    periods_path = REPORT_DIR / f"ai_overlay_policy_map_periods_{token}.csv"
    combo_family_path = REPORT_DIR / f"ai_overlay_combo_strategy_best_by_family_{token}.csv"
    combo_model_path = REPORT_DIR / f"ai_overlay_combo_strategy_best_by_model_{token}.csv"

    model_rows = _enrich_model_rows(_read_csv(model_path))
    family_rows = _enrich_family_rows(_read_csv(family_path))
    periods = _read_csv(periods_path)
    combo_family = _read_csv(combo_family_path) if combo_family_path.exists() else pd.DataFrame()
    combo_model = _read_csv(combo_model_path) if combo_model_path.exists() else pd.DataFrame()

    generated_at = datetime.now().isoformat(timespec="seconds")
    common = {
        "schema_version": "1.0",
        "visibility": "admin_only",
        "as_of_date": asof,
        "generated_at": generated_at,
        "timezone": "Asia/Seoul",
        "status": "shadow_observation",
        "live_recommendation_applied": False,
        "shadow_tracking_start_date": "2026-05-12",
        "base_data_date": asof,
        "interpretation_note": "기존 전략모델 baseline과 전략모델+AI overlay policy map의 연구용 shadow 비교입니다. 실제 추천 반영 상태가 아닙니다.",
        "null_display_rule": "null/NaN/unavailable values must be displayed as N/A, not 0%.",
    }

    internal_payload = {
        **common,
        "source_name": "internal_models_ai_overlay_shadow_current",
        "model_role": "strategy_model_overlay_shadow",
        "page_target": "admin_internal_models",
        "policy_map": _records(
            model_rows[
                [
                    "strategy_family",
                    "scope_key",
                    "model_id",
                    "mapped_policy",
                    "mapped_policy_label_ko",
                    "overlay_result_tag",
                    "overlay_result_label_ko",
                ]
            ]
        ),
        "family_summary": _records(family_rows),
        "model_summary": _records(model_rows),
        "period_summary": {
            "rows": int(len(periods)),
            "models": int(periods[["scope_key", "model_id"]].drop_duplicates().shape[0]) if not periods.empty else 0,
            "periods": int(periods["snapshot_date"].nunique()) if "snapshot_date" in periods.columns else 0,
        },
        "watch_notes": [
            {
                "model_id": "S3_CORE2",
                "level": "caution",
                "text": "수익 개선폭은 크지만 MDD 악화가 확인되어 risk cap 추가 검증이 필요합니다.",
            }
        ],
        "source_files": {
            "model_csv": str(model_path),
            "family_csv": str(family_path),
            "periods_csv": str(periods_path),
            "markdown": str(REPORT_DIR / f"AI_OVERLAY_POLICY_MAP_BACKTEST_{token}.md"),
        },
    }

    ai_monitor_payload = {
        **common,
        "source_name": "ai_learning_overlay_monitor_current",
        "model_role": "ai_overlay_effect_monitor",
        "page_target": "admin_ai_learning_models",
        "component_models": AI_COMPONENTS,
        "overlay_policy_map_summary": {
            "family_summary": _records(family_rows),
            "model_summary": _records(model_rows),
        },
        "combo_ablation_summary": {
            "best_by_family": _records(combo_family) if not combo_family.empty else [],
            "best_by_model": _records(combo_model) if not combo_model.empty else [],
        },
        "etf_track_note": "ETF전용포트폴리오AI는 주식 overlay와 별도 트랙으로 관리합니다.",
        "source_files": {
            "policy_map_json": str(REPORT_DIR / f"ai_overlay_policy_map_backtest_{token}.json"),
            "policy_map_markdown": str(REPORT_DIR / f"AI_OVERLAY_POLICY_MAP_BACKTEST_{token}.md"),
            "combo_markdown": str(REPORT_DIR / f"AI_OVERLAY_COMBO_STRATEGY_BACKTEST_{token}.md"),
            "downside_risk_markdown": str(REPORT_DIR / f"DOWNSIDE_RISK_AI_WEEKLY_OVERLAY_BACKTEST_{token}.md"),
            "valuation_markdown": str(REPORT_DIR / f"VALUATION_AI_WEEKLY_OVERLAY_BACKTEST_{token}.md"),
            "candidate_rank_delta_markdown": str(REPORT_DIR / f"CANDIDATE_RANK_DELTA_AI_WEEKLY_OVERLAY_BACKTEST_{token}.md"),
        },
    }

    ADMIN_CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    internal_path = ADMIN_CURRENT_DIR / "internal_models_ai_overlay_shadow_current.json"
    ai_monitor_path = ADMIN_CURRENT_DIR / "ai_learning_overlay_monitor_current.json"
    internal_path.write_text(json.dumps(internal_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ai_monitor_path.write_text(json.dumps(ai_monitor_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "as_of_date": asof,
        "outputs": {
            "internal_models_ai_overlay_shadow_current": str(internal_path),
            "ai_learning_overlay_monitor_current": str(ai_monitor_path),
        },
        "model_rows": int(len(model_rows)),
        "family_rows": int(len(family_rows)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build admin current payloads for AI overlay policy map monitoring.")
    parser.add_argument("--asof", required=True)
    args = parser.parse_args()
    print(json.dumps(build_payloads(str(args.asof)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
