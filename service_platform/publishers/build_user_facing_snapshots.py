from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporting.public_model_terms import build_public_model_metadata
from src.reporting.render_redbot_user_report import load_mapping

CURRENT_DIR = ROOT / "service_platform" / "web" / "public_data" / "current"
REPORT_DIR = ROOT / "reports" / "redbot_user_reports"
ROUTER_DIR = ROOT / "reports" / "backtest_router"
LEGACY_REPORT = CURRENT_DIR / "user_recommendation_report.json"
CANONICAL_REPORT = CURRENT_DIR / "user_model_snapshot_report.json"


def load_report(service_profile: str, asof: str) -> dict[str, Any]:
    path = REPORT_DIR / f"redbot_user_report_{service_profile}_{asof.replace('-', '')}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def current_market_regime() -> str:
    files = sorted(ROUTER_DIR.glob("router_decisions_*_auto.csv"), key=lambda p: (p.stat().st_mtime, p.name))
    if not files:
        return "unknown"
    import pandas as pd
    df = pd.read_csv(files[-1])
    return "unknown" if df.empty else str(df.iloc[-1]["detected_regime"])




def build_copy_aliases(service_profile: str) -> dict[str, str]:
    meta = build_public_model_metadata(service_profile)
    return {
        "quant_model_name": meta["model_display_name"],
        "model_definition_line": meta["model_public_type"],
        "model_definition_detail": meta["model_role_desc"],
    }

def build_catalog(mapping: dict[str, Any], asof: str) -> dict[str, Any]:
    models = []
    for idx, row in enumerate(mapping["user_models"], start=1):
        model_metadata = build_public_model_metadata(row["service_profile"])
        copy_aliases = build_copy_aliases(row["service_profile"])
        models.append({
            "user_model_id": f"user_{idx}",
            "user_model_name": row["user_model_name"],
            "service_profile": row["service_profile"],
            "model_metadata": model_metadata,
            **copy_aliases,
            "summary": model_metadata["model_one_line_desc"],
            "risk_label": row["risk_label"],
            "reference_usage_context": model_metadata["model_profile_desc"],
            "primary_asset_mix": row.get("key_assets", []),
            "is_active": True,
            "compliance_metadata": {
                "content_class": "service_public_model",
                "public_same_for_all_users": True,
                "non_personalized": True,
                "is_personalized_advice": False,
                "is_one_to_one_advisory": False,
                "is_actual_trade_instruction": False,
                "actual_investment_result": False,
                "backtest_result": False,
                "disclaimer_required": True,
                "data_basis": "rule_based_public_model_information",
                "model_version": f"public-model-{asof.replace('-', '.')}",
                "calculation_version": "calc-2026-03-24-compliance-v1",
                "asof_date": asof,
                "rebalance_frequency": "monthly",
                "fee_bps": 0.0,
                "slippage_bps": 0.0,
                "benchmark_name": "KOSPI200",
                "backtest_start_date": asof,
                "backtest_end_date": asof,
                "universe_definition": "KR stocks + KR ETFs used by public rule-based models",
                "data_source_summary": "Rule-based public model catalog generated from Quant outputs"
            }
        })
    return {"as_of_date": asof, "models": models}


def build_reports(mapping: dict[str, Any], asof: str) -> dict[str, Any]:
    reports = []
    for row in mapping["user_models"]:
        report = load_report(row["service_profile"], asof)
        model_metadata = report.get("model_metadata", build_public_model_metadata(row["service_profile"]))
        copy_aliases = build_copy_aliases(row["service_profile"])
        reports.append({
            "user_model_name": row["user_model_name"],
            "service_profile": row["service_profile"],
            "summary_text": report["model_overview"]["model_character"],
            "model_metadata": model_metadata,
            **copy_aliases,
            "market_view": report["executive_summary"]["market_view"],
            "allocation_items": report["model_portfolio"],
            "rationale_items": report["model_rationale"],
            "risk_level": report["risk_guide"]["risk_level"],
            "performance_summary": report["recent_performance"],
            "change_log": report["model_changes"],
            "disclaimer_text": report["disclaimer"]["informational_purpose"],
            "compliance_metadata": report["compliance_metadata"]
        })
    performance_meta = reports[0]["compliance_metadata"] if reports else {}
    return {"as_of_date": asof, "generated_at": datetime.now().isoformat(timespec="seconds"), "current_market_regime": current_market_regime(), "performance_meta": performance_meta, "reports": reports}


def build_performance(mapping: dict[str, Any], asof: str) -> dict[str, Any]:
    rows = []
    for row in mapping["user_models"]:
        report = load_report(row["service_profile"], asof)
        perf = report["recent_performance"]
        model_metadata = report.get("model_metadata", build_public_model_metadata(row["service_profile"]))
        copy_aliases = build_copy_aliases(row["service_profile"])
        rows.append({
            "user_model_name": row["user_model_name"],
            "service_profile": row["service_profile"],
            "risk_label": row["risk_label"],
            "performance_cards": {
                "primary_period": perf["headline_metrics"].get("primary_period", "1Y"),
                "display_metric": perf["headline_metrics"].get("display_metric", "cagr"),
                "cagr": perf["headline_metrics"]["cagr"],
                "total_return": perf["headline_metrics"].get("total_return"),
                "mdd": perf["headline_metrics"]["mdd"],
                "sharpe": perf["headline_metrics"]["sharpe"]
            },
            "model_metadata": model_metadata,
            **copy_aliases,
            "period_table": perf["period_metrics"],
            "performance_subject_name": report["recent_performance"].get("performance_subject_name"),
            "performance_subject_type": report["recent_performance"].get("performance_subject_type"),
            "portfolio_generation_basis": report["recent_performance"].get("portfolio_generation_basis"),
            "reference_metrics": {
                "five_year": perf["headline_metrics"].get("reference_5y"),
                "full": perf["headline_metrics"].get("reference_full")
            },
            "note": row["description"],
            "compliance_metadata": report["compliance_metadata"]
        })
    performance_meta = rows[0]["compliance_metadata"] if rows else {}
    return {"as_of_date": asof, "performance_meta": performance_meta, "models": rows}


def build_changes(mapping: dict[str, Any], asof: str) -> dict[str, Any]:
    rows = []
    for row in mapping["user_models"]:
        report = load_report(row["service_profile"], asof)
        changes = report["model_changes"]
        model_metadata = report.get("model_metadata", build_public_model_metadata(row["service_profile"]))
        copy_aliases = build_copy_aliases(row["service_profile"])
        rows.append({
            "user_model_name": row["user_model_name"],
            "change_type": "rebalanced" if changes.get("increased_assets") or changes.get("decreased_assets") else "unchanged",
            "summary": report["executive_summary"]["summary_basis"],
            "model_metadata": model_metadata,
            **copy_aliases,
            "change_subject_name": changes.get("change_subject_name"),
            "change_basis_desc": changes.get("change_basis"),
            "change_reason_desc": changes.get("change_reason_desc"),
            "increase_items": changes.get("increased_assets", []),
            "decrease_items": changes.get("decreased_assets", []),
            "reason_text": changes.get("change_basis", "공개 규칙 기반 산출 결과에 따라 구성이 갱신되었습니다."),
            "compliance_metadata": report["compliance_metadata"]
        })
    return {"as_of_date": asof, "changes": rows}


def build_manifest(asof: str) -> dict[str, Any]:
    return {
        "as_of_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "files": ["user_model_catalog.json", "user_model_snapshot_report.json", "user_performance_summary.json", "user_recent_changes.json"],
        "channel": "user-facing",
        "version": "v2",
        "compliance_note": "public_model_snapshot_only"
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build user-facing web snapshots")
    parser.add_argument("--asof", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    mapping = load_mapping()
    write_json(CURRENT_DIR / "user_model_catalog.json", build_catalog(mapping, args.asof))
    write_json(CANONICAL_REPORT, build_reports(mapping, args.asof))
    write_json(CURRENT_DIR / "user_performance_summary.json", build_performance(mapping, args.asof))
    write_json(CURRENT_DIR / "user_recent_changes.json", build_changes(mapping, args.asof))
    write_json(CURRENT_DIR / "publish_manifest.json", build_manifest(args.asof))
    if LEGACY_REPORT.exists():
        LEGACY_REPORT.unlink()
    print(f"[OK] built user-facing snapshots for asof={args.asof} -> {CURRENT_DIR}")


if __name__ == "__main__":
    main()
