from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(r"D:\Quant")
PAYLOAD_PATH = ROOT / r"service_platform\web\admin_data\current\admin_new_entry_tracker.json"
INTERNAL_MODEL_CODES = ("S2", "S2_PIT_V01", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5", "S6", "I-STOCK-STRONG-RSI-V01")
TSERIES_MODEL_CODES = ("T-STOCK-V01", "T-ETF-V01")
REQUIRED_PERF_FIELDS = (
    "model_code",
    "asof_date",
    "cagr",
    "mdd_1y",
    "sharpe_1y",
    "trailing_1m",
    "trailing_3m",
    "trailing_6m",
    "trailing_1y",
    "itd_return",
    "sample_count",
    "metric_basis",
)
ACTUAL_LIVE_START_DATES = {
    "user_models": {
        "stable": "2026-03-18",
        "balanced": "2026-03-18",
        "growth": "2026-03-18",
    },
    "internal_models": {
        "S2": "2026-03-12",
        "S3": "2026-03-12",
        "S3_CORE2": "2026-03-12",
        "S4": "2026-03-17",
        "S5": "2026-03-17",
        "S6": "2026-03-17",
        "S2_PIT_V01": "2026-04-23",
        "S3_ACCEL_V01": "2026-04-23",
        "I-STOCK-STRONG-RSI-V01": "2026-04-29",
    },
    "tseries_models": {
        "T-STOCK-V01": "2026-04-01",
        "T-ETF-V01": "2026-04-01",
    },
}
ACTUAL_LIVE_METRICS = ("current_return", "1w", "2w", "1m", "2m", "3m", "6m", "1y")
ACTUAL_LIVE_METRIC_FIELDS = (
    "sample_count",
    "avg_return",
    "median_return",
    "win_rate",
    "mdd_sample_count",
    "avg_mdd",
    "median_mdd",
    "sharpe_sample_count",
    "avg_sharpe",
    "median_sharpe",
)


def _coverage(payload: dict, scope_key: str, model_field: str) -> dict:
    rank_rows = ((payload.get("weekly_rankings") or {}).get(scope_key) or [])
    event_rows = payload.get(scope_key) or []
    rank_set = {
        (str(row.get(model_field)), str(row.get("security_code")), str(row.get("week_end")))
        for row in rank_rows
        if row.get(model_field) and row.get("security_code") and row.get("week_end")
    }
    matched = 0
    for row in event_rows:
        key = (str(row.get(model_field)), str(row.get("security_code")), str(row.get("week_end")))
        if key in rank_set:
            matched += 1
    total = len(event_rows)
    ratio = float(matched) / float(total) if total else 1.0
    return {
        "events": total,
        "weekly_rank_rows": len(rank_rows),
        "matched_events": matched,
        "match_ratio": round(ratio, 6),
    }


def _filter_recent_events(payload: dict, weeks: int) -> dict:
    asof = datetime.fromisoformat(str(payload.get("as_of_date")))
    start = asof - timedelta(weeks=weeks)
    filtered = dict(payload)
    for key in ("user_models", "internal_models", "tseries_models"):
        rows = []
        for row in payload.get(key) or []:
            raw_date = row.get("week_end") or row.get("event_date") or row.get("asof_date")
            try:
                row_date = datetime.fromisoformat(str(raw_date))
            except (TypeError, ValueError):
                row_date = None
            if row_date is not None and row_date >= start:
                rows.append(row)
        filtered[key] = rows
    return filtered


def _direct_population_ratio(rows: list[dict]) -> dict:
    total = len(rows)
    populated = sum(1 for row in rows if row.get("rank_no") is not None or row.get("score") is not None)
    ratio = float(populated) / float(total) if total else 1.0
    return {"rows": total, "populated": populated, "populated_ratio": round(ratio, 6)}


def _tseries_recent_8w(payload: dict) -> dict:
    asof = datetime.fromisoformat(str(payload.get("as_of_date")))
    start = asof - timedelta(weeks=8)
    rows = [
        row
        for row in (payload.get("tseries_models") or [])
        if row.get("model_code") == "T-STOCK-V01"
        and row.get("event_type") == "new_entry"
        and datetime.fromisoformat(str(row.get("event_date"))) >= start
    ]
    return _direct_population_ratio(rows)


def _performance_coverage(rows: list[dict], expected_models: tuple[str, ...]) -> dict:
    index = {str(row.get("model_code")): row for row in rows if row.get("model_code")}
    by_model: list[dict] = []
    missing_models: list[str] = []
    for model_code in expected_models:
        row = index.get(model_code)
        if row is None:
            missing_models.append(model_code)
            by_model.append({"model_code": model_code, "required_fields_present_rate": 0.0, "missing_fields": list(REQUIRED_PERF_FIELDS)})
            continue
        missing_fields = [field for field in REQUIRED_PERF_FIELDS if row.get(field) is None]
        present_rate = (len(REQUIRED_PERF_FIELDS) - len(missing_fields)) / float(len(REQUIRED_PERF_FIELDS))
        by_model.append(
            {
                "model_code": model_code,
                "required_fields_present_rate": round(present_rate, 6),
                "missing_fields": missing_fields,
            }
        )
    return {"models": by_model, "missing_models": missing_models}


def _validate_actual_live_summary(payload: dict) -> tuple[dict, list[str]]:
    summary = payload.get("actual_live_performance_summary")
    failures: list[str] = []
    if not isinstance(summary, dict):
        return {}, ["missing object payload: actual_live_performance_summary"]
    if summary.get("metric_basis") != "actual_market_price_forward_return_since_live_start":
        failures.append("actual_live_performance_summary metric_basis mismatch")
    if summary.get("horizons") != list(ACTUAL_LIVE_METRICS):
        failures.append("actual_live_performance_summary horizons mismatch")

    coverage: dict[str, list[dict]] = {}
    for scope_key, expected_starts in ACTUAL_LIVE_START_DATES.items():
        rows = summary.get(scope_key)
        if not isinstance(rows, list):
            failures.append(f"actual_live_performance_summary missing list: {scope_key}")
            continue
        id_field = "service_profile" if scope_key == "user_models" else "model_code"
        by_model = {str(row.get(id_field)): row for row in rows if row.get(id_field)}
        scope_coverage: list[dict] = []
        for model_key, live_start_date in expected_starts.items():
            row = by_model.get(model_key)
            if row is None:
                failures.append(f"actual_live_performance_summary {scope_key} missing model: {model_key}")
                scope_coverage.append({"model": model_key, "present": False})
                continue
            if row.get("live_start_date") != live_start_date:
                failures.append(f"actual_live_performance_summary {model_key} live_start_date mismatch")
            metrics = row.get("metrics")
            if not isinstance(metrics, dict):
                failures.append(f"actual_live_performance_summary {model_key} missing metrics")
                continue
            for metric in ACTUAL_LIVE_METRICS:
                metric_payload = metrics.get(metric)
                if not isinstance(metric_payload, dict):
                    failures.append(f"actual_live_performance_summary {model_key} missing metric: {metric}")
                    continue
                for field in ACTUAL_LIVE_METRIC_FIELDS:
                    if field not in metric_payload:
                        failures.append(f"actual_live_performance_summary {model_key}.{metric} missing field: {field}")
                sample_count = metric_payload.get("sample_count")
                if not isinstance(sample_count, int) or sample_count < 0:
                    failures.append(f"actual_live_performance_summary {model_key}.{metric} invalid sample_count")
                if sample_count == 0:
                    for field in ("avg_return", "median_return", "win_rate"):
                        if metric_payload.get(field) is not None:
                            failures.append(f"actual_live_performance_summary {model_key}.{metric}.{field} must be null when sample_count=0")
                for count_field in ("mdd_sample_count", "sharpe_sample_count"):
                    value = metric_payload.get(count_field)
                    if not isinstance(value, int) or value < 0:
                        failures.append(f"actual_live_performance_summary {model_key}.{metric} invalid {count_field}")
            scope_coverage.append(
                {
                    "model": model_key,
                    "present": True,
                    "live_start_date": row.get("live_start_date"),
                    "live_event_count": row.get("live_event_count"),
                }
            )
        coverage[scope_key] = scope_coverage
    return coverage, failures


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate admin new entry tracker payload.")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD")
    ap.add_argument("--mode", choices=["quick", "full"], default="full")
    ap.add_argument("--recent-weeks", type=int, default=8, help="Recent event window for quick validation mode")
    ap.add_argument("--user-threshold", type=float, default=0.95)
    ap.add_argument("--internal-threshold", type=float, default=0.90)
    ap.add_argument("--tseries-threshold", type=float, default=0.90)
    args = ap.parse_args()

    if not PAYLOAD_PATH.exists():
        raise SystemExit(f"missing payload: {PAYLOAD_PATH}")
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    if payload.get("as_of_date") != args.asof:
        raise SystemExit(f"as_of_date mismatch: expected {args.asof}, got {payload.get('as_of_date')}")
    for key in ("user_models", "internal_models", "tseries_models"):
        if key not in payload or not isinstance(payload[key], list):
            raise SystemExit(f"missing list payload: {key}")
    weekly_rankings = payload.get("weekly_rankings")
    if not isinstance(weekly_rankings, dict):
        raise SystemExit("missing object payload: weekly_rankings")
    for key in ("user_models", "internal_models", "tseries_models"):
        if key not in weekly_rankings or not isinstance(weekly_rankings[key], list):
            raise SystemExit(f"missing weekly_rankings list payload: {key}")
    model_perf = payload.get("model_performance_summary")
    if not isinstance(model_perf, dict):
        raise SystemExit("missing object payload: model_performance_summary")
    for key in ("internal_models", "tseries_models"):
        if key not in model_perf or not isinstance(model_perf[key], list):
            raise SystemExit(f"missing model_performance_summary list payload: {key}")
    actual_live_coverage, actual_live_failures = _validate_actual_live_summary(payload)

    validation_payload = _filter_recent_events(payload, int(args.recent_weeks)) if args.mode == "quick" else payload
    coverage = {
        "user_models": _coverage(validation_payload, "user_models", "service_profile"),
        "internal_models": _coverage(validation_payload, "internal_models", "model_code"),
        "tseries_models": _coverage(validation_payload, "tseries_models", "model_code"),
    }
    direct_population = {
        "user_models": _direct_population_ratio(validation_payload.get("user_models") or []),
        "internal_models": _direct_population_ratio(validation_payload.get("internal_models") or []),
        "tseries_models": _direct_population_ratio(validation_payload.get("tseries_models") or []),
    }
    performance_coverage = {
        "internal_models": _performance_coverage((model_perf.get("internal_models") or []), INTERNAL_MODEL_CODES),
        "tseries_models": _performance_coverage((model_perf.get("tseries_models") or []), TSERIES_MODEL_CODES),
    }
    tseries_recent_8w = _tseries_recent_8w(payload)
    thresholds = {
        "user_models": float(args.user_threshold),
        "internal_models": float(args.internal_threshold),
        "tseries_models": float(args.tseries_threshold),
    }
    failures = []
    for key, stats in coverage.items():
        if stats["match_ratio"] < thresholds[key]:
            failures.append(f"{key} coverage {stats['match_ratio']:.3f} < threshold {thresholds[key]:.3f}")
    for scope_key in ("internal_models", "tseries_models"):
        scope_perf = performance_coverage[scope_key]
        if scope_perf["missing_models"]:
            failures.append(f"{scope_key} missing performance models: {', '.join(scope_perf['missing_models'])}")
        for item in scope_perf["models"]:
            if item["required_fields_present_rate"] < 1.0:
                failures.append(
                    f"{scope_key} {item['model_code']} performance completeness {item['required_fields_present_rate']:.3f} < 1.000"
                )
    if tseries_recent_8w["populated_ratio"] < 0.95:
        failures.append(
            f"tseries_recent_8w populated_ratio {tseries_recent_8w['populated_ratio']:.3f} < threshold 0.950"
        )
    failures.extend(actual_live_failures)
    if failures:
        raise SystemExit("coverage validation failed: " + "; ".join(failures))

    print(
        json.dumps(
            {
                "asof": payload.get("as_of_date"),
                "mode": args.mode,
                "recent_weeks": int(args.recent_weeks) if args.mode == "quick" else None,
                "user_rows": len(payload.get("user_models", [])),
                "internal_rows": len(payload.get("internal_models", [])),
                "tseries_rows": len(payload.get("tseries_models", [])),
                "validated_event_rows": {
                    "user_models": len(validation_payload.get("user_models", [])),
                    "internal_models": len(validation_payload.get("internal_models", [])),
                    "tseries_models": len(validation_payload.get("tseries_models", [])),
                },
                "coverage": coverage,
                "direct_population": direct_population,
                "performance_coverage": performance_coverage,
                "actual_live_coverage": actual_live_coverage,
                "tseries_recent_8w": tseries_recent_8w,
                "validated_file": str(PAYLOAD_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
