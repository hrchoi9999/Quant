from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service_platform.publishers.build_user_facing_snapshots import main as build_main

CURRENT_DIR = ROOT / "service_platform" / "web" / "public_data" / "current"
REQUIRED = [
    "user_model_catalog.json",
    "user_model_snapshot_report.json",
    "user_performance_summary.json",
    "user_recent_changes.json",
    "publish_manifest.json",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Redbot web user-facing snapshots")
    parser.add_argument("--asof", default="2026-03-20")
    args = parser.parse_args()

    sys.argv = [sys.argv[0], "--asof", args.asof]
    build_main()

    missing = [name for name in REQUIRED if not (CURRENT_DIR / name).exists()]
    if missing:
        raise SystemExit("Missing snapshot files: " + ", ".join(missing))

    catalog = json.loads((CURRENT_DIR / "user_model_catalog.json").read_text(encoding="utf-8"))
    reports = json.loads((CURRENT_DIR / "user_model_snapshot_report.json").read_text(encoding="utf-8"))
    performance = json.loads((CURRENT_DIR / "user_performance_summary.json").read_text(encoding="utf-8"))
    changes = json.loads((CURRENT_DIR / "user_recent_changes.json").read_text(encoding="utf-8"))

    assert len(catalog.get("models", [])) == 4
    assert len(reports.get("reports", [])) == 4
    assert len(performance.get("models", [])) == 4
    assert len(changes.get("changes", [])) == 4

    banned_terms = ["추천", "권유", "매수 추천", "매도 추천", "개인 맞춤", "성향별 추천", "오늘의 추천", "추천 전략", "매수 전략", "매도 전략"]
    report_text = json.dumps(reports, ensure_ascii=False)
    bad_hits = [token for token in banned_terms if token in report_text]
    if bad_hits:
        raise SystemExit("Detected banned advisory terms in user_model_snapshot_report.json: " + ", ".join(bad_hits))

    required_model_terms = ["멀티애셋 데이터 기반 퀀트투자 모델", "공개 기준 기반 퀀트투자 모델", "주간 브리핑용 퀀트투자 모델", "모델 포트폴리오를 산출하는 퀀트투자 모델"]
    missing_terms = [token for token in required_model_terms if token not in report_text]
    if missing_terms:
        raise SystemExit("Missing quant model identity terms in user_model_snapshot_report.json: " + ", ".join(missing_terms))

    suspicious_tokens = ["�", "??/????"]
    suspicious_hits = [token for token in suspicious_tokens if token in report_text]
    if suspicious_hits:
        raise SystemExit("Detected garbled Korean tokens in user_model_snapshot_report.json: " + ", ".join(suspicious_hits))

    for report in reports.get("reports", []):
        compliance = report.get("compliance_metadata", {})
        model_metadata = report.get("model_metadata", {})
        required_compliance = [
            "public_same_for_all_users", "non_personalized", "actual_investment_result", "backtest_result",
            "disclaimer_required", "model_version", "calculation_version", "asof_date", "rebalance_frequency",
            "fee_bps", "slippage_bps", "benchmark_name", "backtest_start_date", "backtest_end_date",
            "universe_definition", "data_source_summary"
        ]
        if compliance.get("is_personalized_advice") is not False:
            raise SystemExit(f"Invalid compliance flag: {report}")
        missing_fields = [field for field in required_compliance if field not in compliance]
        if missing_fields:
            raise SystemExit(f"Missing compliance fields in report: {missing_fields}")
        required_model_meta = ["model_display_name", "model_family_name", "model_public_type", "model_brief_type", "model_portfolio_type", "model_one_line_desc", "model_scope_desc"]
        missing_model_meta = [field for field in required_model_meta if field not in model_metadata]
        if missing_model_meta:
            raise SystemExit(f"Missing model metadata fields in report: {missing_model_meta}")
        for item in report.get("allocation_items", []):
            code = item.get("security_code")
            asset_group = item.get("asset_group")
            if asset_group == "cash":
                continue
            if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
                raise SystemExit(f"Invalid security_code in allocation_items: {item}")
            name = str(item.get("display_name", "")).strip()
            if not name:
                raise SystemExit(f"Empty display_name in allocation_items: {item}")

    for row in changes.get("changes", []):
        for key, expected_direction in (("increase_items", "increase"), ("decrease_items", "decrease")):
            for item in row.get(key, []):
                if not isinstance(item, dict):
                    raise SystemExit(f"Change item must be object: {item}")
                if not str(item.get("display_name", "")).strip():
                    raise SystemExit(f"Change item missing display_name: {item}")
                code = item.get("security_code")
                if code is not None and (not isinstance(code, str) or len(code) != 6 or not code.isdigit()):
                    raise SystemExit(f"Invalid security_code in change item: {item}")
                if not isinstance(item.get("delta_weight"), (int, float)):
                    raise SystemExit(f"delta_weight must be numeric: {item}")
                if item.get("direction") != expected_direction:
                    raise SystemExit(f"direction mismatch in change item: {item}")

    print("validated_user_models=4")
    print("validated_reports=4")
    print("validated_performance_models=4")
    print("validated_changes=4")
    print("validated_korean_text=clean")
    print("validated_security_code=ok")
    print("validated_compliance_language=ok")


if __name__ == "__main__":
    main()
