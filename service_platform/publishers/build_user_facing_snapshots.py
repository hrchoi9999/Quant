from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reporting.public_model_terms import build_public_model_metadata
from src.reporting.render_redbot_user_report import load_mapping
from src.quant_service.read_tseries_operational import build_snapshot as build_tseries_snapshot, connect as connect_tseries

CURRENT_DIR = ROOT / "service_platform" / "web" / "public_data" / "current"
REPORT_DIR = ROOT / "reports" / "redbot_user_reports"
ROUTER_DIR = ROOT / "reports" / "backtest_router"
LEGACY_REPORT = CURRENT_DIR / "user_recommendation_report.json"
CANONICAL_REPORT = CURRENT_DIR / "user_model_snapshot_report.json"
T_SERIES_DISCOVERY = CURRENT_DIR / "quantservice_tseries_discovery.json"
CHANGE_HISTORY = CURRENT_DIR / "user_model_change_history.json"
LEGACY_MANIFEST = CURRENT_DIR / "publish_manifest_user.json"
REPORT_DATE_RE = re.compile(r"_(20\d{6})\.json$")


def load_report(service_profile: str, asof: str) -> dict[str, Any]:
    path = REPORT_DIR / f"redbot_user_report_{service_profile}_{asof.replace('-', '')}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def current_market_regime() -> str:
    files = sorted(ROUTER_DIR.glob("router_decisions_*_balanced.csv"), key=lambda p: (p.stat().st_mtime, p.name))
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


def build_reports(mapping: dict[str, Any], asof: str, generated_at: str) -> dict[str, Any]:
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
    return {"as_of_date": asof, "generated_at": generated_at, "current_market_regime": current_market_regime(), "performance_meta": performance_meta, "reports": reports}


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


def _report_date(path: Path) -> str | None:
    match = REPORT_DATE_RE.search(path.name)
    if not match:
        return None
    token = match.group(1)
    return f"{token[:4]}-{token[4:6]}-{token[6:8]}"


def _change_row_from_report(row: dict[str, Any], report: dict[str, Any], change_asof: str) -> dict[str, Any]:
    changes = report.get("model_changes", {})
    model_metadata = report.get("model_metadata", build_public_model_metadata(row["service_profile"]))
    copy_aliases = build_copy_aliases(row["service_profile"])
    increase_items = changes.get("increased_assets", []) or []
    decrease_items = changes.get("decreased_assets", []) or []
    return {
        "as_of_date": change_asof,
        "user_model_name": row["user_model_name"],
        "service_profile": row["service_profile"],
        "change_type": "rebalanced" if increase_items or decrease_items else "unchanged",
        "summary": report.get("executive_summary", {}).get("summary_basis"),
        "model_metadata": model_metadata,
        **copy_aliases,
        "change_subject_name": changes.get("change_subject_name"),
        "change_basis_desc": changes.get("change_basis"),
        "change_reason_desc": changes.get("change_reason_desc"),
        "increase_items": increase_items,
        "decrease_items": decrease_items,
        "reason_text": changes.get("change_basis", "공개 규칙 기반 산출 결과에 따라 구성이 갱신되었습니다."),
        "compliance_metadata": report.get("compliance_metadata", {}),
    }


def _dedupe_month_items(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_date = row.get("as_of_date")
        for item in row.get(key, []) or []:
            code = item.get("security_code")
            display_name = str(item.get("display_name", "")).strip()
            dedupe_key = str(code or display_name)
            if not dedupe_key:
                continue
            bucket = by_key.setdefault(
                dedupe_key,
                {
                    "display_name": display_name,
                    "security_code": code,
                    "direction": item.get("direction"),
                    "latest_delta_weight": item.get("delta_weight"),
                    "source_dates": [],
                    "occurrence_count": 0,
                },
            )
            bucket["display_name"] = display_name or bucket["display_name"]
            bucket["security_code"] = code
            bucket["direction"] = item.get("direction")
            bucket["latest_delta_weight"] = item.get("delta_weight")
            bucket["occurrence_count"] = int(bucket["occurrence_count"]) + 1
            if source_date and source_date not in bucket["source_dates"]:
                bucket["source_dates"].append(source_date)
    return sorted(
        by_key.values(),
        key=lambda item: (
            -int(item.get("occurrence_count") or 0),
            str(item.get("display_name") or ""),
        ),
    )


def build_change_history(mapping: dict[str, Any], asof: str, generated_at: str) -> dict[str, Any]:
    profile_rows = {row["service_profile"]: row for row in mapping["user_models"]}
    snapshots_by_date: dict[str, list[dict[str, Any]]] = {}
    for profile, row in profile_rows.items():
        for path in sorted(REPORT_DIR.glob(f"redbot_user_report_{profile}_*.json")):
            change_asof = _report_date(path)
            if not change_asof or change_asof > asof:
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            snapshots_by_date.setdefault(change_asof, []).append(_change_row_from_report(row, report, change_asof))

    dated_snapshots = []
    for change_asof in sorted(snapshots_by_date.keys(), reverse=True):
        models = sorted(
            snapshots_by_date[change_asof],
            key=lambda item: list(profile_rows.keys()).index(item["service_profile"]),
        )
        dated_snapshots.append(
            {
                "period_type": "weekly",
                "period_key": change_asof,
                "as_of_date": change_asof,
                "models": models,
            }
        )

    monthly_groups: dict[str, list[dict[str, Any]]] = {}
    for change_asof, rows in snapshots_by_date.items():
        monthly_groups.setdefault(change_asof[:7], []).extend(rows)

    monthly = []
    for month in sorted(monthly_groups.keys(), reverse=True):
        rows = monthly_groups[month]
        dates = sorted({str(row.get("as_of_date")) for row in rows if row.get("as_of_date")})
        models = []
        for profile, profile_row in profile_rows.items():
            profile_rows_for_month = [row for row in rows if row.get("service_profile") == profile]
            if not profile_rows_for_month:
                continue
            latest_row = sorted(profile_rows_for_month, key=lambda item: item["as_of_date"])[-1]
            models.append(
                {
                    "user_model_name": profile_row["user_model_name"],
                    "service_profile": profile,
                    "change_type": "rebalanced"
                    if any(row.get("increase_items") or row.get("decrease_items") for row in profile_rows_for_month)
                    else "unchanged",
                    "source_dates": sorted({row["as_of_date"] for row in profile_rows_for_month}),
                    "summary": latest_row.get("summary"),
                    "change_subject_name": latest_row.get("change_subject_name"),
                    "change_basis_desc": "해당 월에 생성된 공개 모델 변경 내역을 월 단위로 집계했습니다.",
                    "change_reason_desc": latest_row.get("change_reason_desc"),
                    "increase_items": _dedupe_month_items(profile_rows_for_month, "increase_items"),
                    "decrease_items": _dedupe_month_items(profile_rows_for_month, "decrease_items"),
                    "compliance_metadata": latest_row.get("compliance_metadata", {}),
                }
            )
        monthly.append(
            {
                "period_type": "monthly",
                "period_key": month,
                "start_date": dates[0] if dates else None,
                "end_date": dates[-1] if dates else None,
                "source_dates": dates,
                "models": models,
            }
        )

    return {
        "source_name": "handoff:user_model_change_history",
        "schema_version": "v1",
        "as_of_date": asof,
        "generated_at": generated_at,
        "profiles": list(profile_rows.keys()),
        "available_dates": sorted(snapshots_by_date.keys(), reverse=True),
        "weekly": dated_snapshots,
        "monthly": monthly,
    }


def _normalize_tseries_model(snapshot: dict[str, Any]) -> dict[str, Any]:
    profile = snapshot.get("profile") or {}
    meta = snapshot.get("meta") or {}
    shadow_rows = snapshot.get("shadow_summary") or []
    shadow_summary: dict[str, dict[str, Any]] = {"confirmed": {}, "near": {}, "observe": {}}
    if isinstance(shadow_rows, list):
        for row in shadow_rows:
            if not isinstance(row, dict):
                continue
            bucket = row.get("candidate_bucket")
            horizon = row.get("horizon")
            if not bucket or horizon not in (None, "", "overall"):
                continue
            target_bucket = str(bucket)
            if target_bucket == "historical_stage2":
                target_bucket = "confirmed"
            elif target_bucket == "historical_stage1":
                target_bucket = "near"
            elif target_bucket not in ("confirmed", "near", "observe"):
                continue
            shadow_summary[target_bucket] = {
                "obs_n": row.get("obs_n"),
                "t10_hit_rate": row.get("t10_hit_rate"),
                "t3_hit_rate": row.get("t3_hit_rate"),
                "avg_stage1_prob": row.get("avg_stage1_prob"),
                "avg_stage2_prob": row.get("avg_stage2_prob"),
            }
    top_by_bucket = snapshot.get("top_by_bucket") or {}
    bucket_counts = snapshot.get("bucket_counts") or {}
    performance_summary = snapshot.get("performance_summary") or {}
    rolling = snapshot.get("rolling_watchlist") or {}
    rolling_summary = rolling.get("summary") if isinstance(rolling, dict) else []
    rolling_items = rolling.get("items") if isinstance(rolling, dict) else []
    if not isinstance(rolling_summary, list):
        rolling_summary = []
    if not isinstance(rolling_items, list):
        rolling_items = []
    for bucket in ("confirmed", "near", "observe"):
        top_by_bucket.setdefault(bucket, [])
        bucket_counts.setdefault(bucket, 0)
    threshold_summary = "threshold values not published"
    stage1 = profile.get("stage1_threshold")
    confirmed = profile.get("stage2_confirmed_th")
    near = profile.get("stage2_near_th")
    parts = []
    if stage1 is not None:
        parts.append(f"stage1 {float(stage1):.3f}")
    if confirmed is not None:
        parts.append(f"confirmed {float(confirmed):.3f}")
    if near is not None:
        parts.append(f"near {float(near):.3f}")
    if parts:
        threshold_summary = " / ".join(parts)
    asset_scope = str(meta.get("asset_scope") or "").strip().lower()
    asset_scope_label = "Stock" if asset_scope == "stock" else "ETF"
    display_name = str(meta.get("display_name") or "").strip() or f"전이형 발굴 모델 · {asset_scope_label}"
    return {
        "model_code": snapshot.get("model_code"),
        "asof_date": snapshot.get("asof_date"),
        "meta": {
            "display_name": display_name,
            "display_name_en": "transition-based discovery model",
            "display_name_ko": "전이형 발굴 모델",
            "service_model_code": "T_STOCK_DISCOVERY" if asset_scope == "stock" else "T_ETF_DISCOVERY",
            "service_family": "discovery",
            "service_role": "watchlist",
            "asset_scope": asset_scope,
            "version": meta.get("version_label") or meta.get("version") or "V01",
            "version_label": meta.get("version_label") or meta.get("version") or "V01",
            "stage_structure": meta.get("stage_structure") or "two_stage",
            "status": meta.get("status") or "active",
            "notes": meta.get("notes") or "",
            "display_order": 1 if asset_scope == "stock" else 2,
        },
        "profile": {
            "profile_code": profile.get("profile_code"),
            "threshold_summary": threshold_summary,
            "risk_filter_version": profile.get("risk_filter_version"),
            "threshold_values": {
                "stage1_threshold": stage1,
                "stage2_confirmed_threshold": confirmed,
                "stage2_near_threshold": near,
            },
            "notes": profile.get("notes"),
        },
        "run": {
            "refresh_kind": (snapshot.get("run") or {}).get("refresh_kind"),
            "status": (snapshot.get("run") or {}).get("status"),
            "started_at": (snapshot.get("run") or {}).get("started_at"),
            "finished_at": (snapshot.get("run") or {}).get("finished_at"),
            "notes": (snapshot.get("run") or {}).get("notes"),
        },
        "bucket_counts": bucket_counts,
        "top_by_bucket": top_by_bucket,
        "shadow_summary": shadow_summary,
        "rolling_watchlist": {
            "summary": rolling_summary,
            "items": rolling_items[:20],
        },
        "performance_summary": performance_summary,
    }


def build_tseries_discovery(asof: str, generated_at: str) -> dict[str, Any]:
    con = connect_tseries()
    try:
        models = [
            _normalize_tseries_model(build_tseries_snapshot(con, "T-STOCK-V01")),
            _normalize_tseries_model(build_tseries_snapshot(con, "T-ETF-V01")),
        ]
    finally:
        con.close()
    return {
        "source_name": "handoff:tseries_discovery_current",
        "warnings": [],
        "errors": [],
        "as_of_date": asof,
        "generated_at": generated_at,
        "channel": "tseries-discovery",
        "schema_version": "v1",
        "models": models,
    }


def build_manifest(asof: str, generated_at: str) -> dict[str, Any]:
    return {
        "as_of_date": asof,
        "generated_at": generated_at,
        "files": ["user_model_catalog.json", "user_model_snapshot_report.json", "user_performance_summary.json", "user_recent_changes.json", "user_model_change_history.json", "quantservice_tseries_discovery.json"],
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
    generated_at = datetime.now().isoformat(timespec="seconds")
    write_json(CURRENT_DIR / "user_model_catalog.json", build_catalog(mapping, args.asof))
    write_json(CANONICAL_REPORT, build_reports(mapping, args.asof, generated_at))
    write_json(CURRENT_DIR / "user_performance_summary.json", build_performance(mapping, args.asof))
    write_json(CURRENT_DIR / "user_recent_changes.json", build_changes(mapping, args.asof))
    write_json(CHANGE_HISTORY, build_change_history(mapping, args.asof, generated_at))
    write_json(T_SERIES_DISCOVERY, build_tseries_discovery(args.asof, generated_at))
    manifest = build_manifest(args.asof, generated_at)
    write_json(CURRENT_DIR / "publish_manifest.json", manifest)
    write_json(LEGACY_MANIFEST, manifest)
    if LEGACY_REPORT.exists():
        LEGACY_REPORT.unlink()
    print(f"[OK] built user-facing snapshots for asof={args.asof} -> {CURRENT_DIR}")


if __name__ == "__main__":
    main()

