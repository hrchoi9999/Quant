from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(r"D:\Quant")
PRICE_DB = ROOT / r"data\db\price.db"
REGIME_DB = ROOT / r"data\db\regime.db"
S3_FEATURE_DB = ROOT / r"data\db_s3\features_s3.db"
FUNDAMENTALS_DB = ROOT / r"data\db\fundamentals.db"
QUANT_SERVICE_DB = ROOT / r"data\db\quant_service.db"
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"

PUBLIC_CURRENT_DIR = ROOT / r"service_platform\web\public_data\current"
PUBLIC_HISTORY_DIR = ROOT / r"service_platform\web\public_data\history"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
TRADING_SIGN_CURRENT_DIR = ROOT / r"trading_sign\service_platform\web\public_data\current"

STOCK_UNIVERSE = ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"
ETF_UNIVERSE = ROOT / r"data\universe\universe_etf_master_latest.csv"

REQUIRED_PUBLIC_FILES = (
    "publish_manifest.json",
    "publish_manifest_user.json",
    "user_model_catalog.json",
    "user_model_snapshot_report.json",
    "user_performance_summary.json",
    "user_recent_changes.json",
    "user_model_change_history.json",
    "quantservice_tseries_discovery.json",
)
REQUIRED_PUBLIC_HISTORY_FILES = (
    "user_model_performance_history.json",
    "user_model_holdings_history.json",
    "quantservice_tseries_discovery_history.json",
)
REQUIRED_TRADING_SIGN_FILES = (
    "tradingsign_overview.json",
    "tradingsign_model_detail.json",
    "tradingsign_manifest.json",
)
REQUIRED_PUBLISHED_MODELS = ("S2", "S3", "S3_CORE2", "S4", "S5", "S6")


@dataclass
class CheckResult:
    name: str
    status: str
    detail: dict[str, Any]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _max_date(db_path: Path, table: str, column: str = "date") -> str | None:
    if not db_path.exists():
        return None
    with sqlite3.connect(str(db_path)) as con:
        row = con.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
    return None if not row or row[0] is None else str(row[0])


def _read_tickers(path: Path, ticker_col: str = "ticker") -> list[str]:
    if not path.exists():
        return []
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                if ticker_col not in (reader.fieldnames or []):
                    return []
                return sorted({str(row[ticker_col]).strip().zfill(6) for row in reader if str(row.get(ticker_col, "")).strip()})
        except UnicodeDecodeError:
            continue
    return []


def _price_coverage(tickers: list[str], asof: str) -> tuple[int, int, float]:
    if not tickers:
        return 0, 0, 0.0
    with sqlite3.connect(str(PRICE_DB)) as con:
        found: set[str] = set()
        chunk = 900
        for i in range(0, len(tickers), chunk):
            part = tickers[i : i + chunk]
            qmarks = ",".join(["?"] * len(part))
            rows = con.execute(
                f"""
                SELECT DISTINCT ticker
                FROM prices_daily
                WHERE date = ?
                  AND ticker IN ({qmarks})
                  AND close IS NOT NULL
                """,
                [asof, *part],
            ).fetchall()
            found.update(str(row[0]).zfill(6) for row in rows)
    expected = len(tickers)
    actual = len(found)
    return expected, actual, actual / expected if expected else 0.0


def _previous_month_end(asof: str) -> str:
    dt = datetime.strptime(asof, "%Y-%m-%d").date()
    first = date(dt.year, dt.month, 1)
    prev = first.fromordinal(first.toordinal() - 1)
    return prev.strftime("%Y-%m-%d")


def _previous_month_trading_end(asof: str) -> str:
    prev_month_end = _previous_month_end(asof)
    if not PRICE_DB.exists():
        return prev_month_end
    with sqlite3.connect(str(PRICE_DB)) as con:
        row = con.execute(
            """
            SELECT MAX(date)
            FROM prices_daily
            WHERE date <= ?
              AND date >= substr(?, 1, 7) || '-01'
            """,
            (prev_month_end, prev_month_end),
        ).fetchone()
    return prev_month_end if not row or row[0] is None else str(row[0])


def _status_from_bool(ok: bool, warn: bool = False) -> str:
    if ok:
        return "pass"
    return "warn" if warn else "fail"


def _check_public_payloads(asof: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    missing = [name for name in REQUIRED_PUBLIC_FILES if not (PUBLIC_CURRENT_DIR / name).exists()]
    results.append(CheckResult("public_current_files_exist", _status_from_bool(not missing), {"missing": missing}))
    if missing:
        return results

    manifest = _load_json(PUBLIC_CURRENT_DIR / "publish_manifest.json")
    catalog = _load_json(PUBLIC_CURRENT_DIR / "user_model_catalog.json")
    snapshot = _load_json(PUBLIC_CURRENT_DIR / "user_model_snapshot_report.json")
    performance = _load_json(PUBLIC_CURRENT_DIR / "user_performance_summary.json")
    changes = _load_json(PUBLIC_CURRENT_DIR / "user_recent_changes.json")
    history = _load_json(PUBLIC_CURRENT_DIR / "user_model_change_history.json")
    tseries = _load_json(PUBLIC_CURRENT_DIR / "quantservice_tseries_discovery.json")

    date_fields = {
        "publish_manifest": manifest.get("as_of_date"),
        "user_model_catalog": catalog.get("as_of_date"),
        "user_model_snapshot_report": snapshot.get("as_of_date"),
        "user_performance_summary": performance.get("as_of_date"),
        "user_recent_changes": changes.get("as_of_date"),
        "user_model_change_history": history.get("as_of_date"),
        "quantservice_tseries_discovery": tseries.get("as_of_date"),
    }
    results.append(CheckResult("public_payload_asof_match", _status_from_bool(all(v == asof for v in date_fields.values())), date_fields))

    profile_set = {row.get("service_profile") for row in catalog.get("models", [])}
    results.append(
        CheckResult(
            "public_user_model_set",
            _status_from_bool(profile_set == {"stable", "balanced", "growth"}),
            {"profiles": sorted(str(x) for x in profile_set), "model_count": len(catalog.get("models", []))},
        )
    )

    tseries_models = tseries.get("models") or []
    model_asofs = {row.get("model_code"): row.get("asof_date") for row in tseries_models if isinstance(row, dict)}
    tstock_ok = model_asofs.get("T-STOCK-V01") == asof
    tetf_asof = model_asofs.get("T-ETF-V01")
    tetf_ok = bool(tetf_asof) and str(tetf_asof) <= asof
    results.append(
        CheckResult(
            "tseries_payload_internal_asof_match",
            _status_from_bool(tstock_ok and tetf_ok),
            {"model_asofs": model_asofs, "rule": "T-STOCK exact asof; T-ETF native PIT/monthly asof may be <= pipeline asof"},
        )
    )
    return results


def _check_history_payloads(asof: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    missing = [name for name in REQUIRED_PUBLIC_HISTORY_FILES if not (PUBLIC_HISTORY_DIR / name).exists()]
    results.append(CheckResult("public_history_files_exist", _status_from_bool(not missing), {"missing": missing}))
    admin_hist = ADMIN_CURRENT_DIR / "internal_model_performance_history.json"
    results.append(
        CheckResult(
            "admin_internal_history_exists",
            _status_from_bool(admin_hist.exists()),
            {"path": str(admin_hist)},
        )
    )
    if missing or not admin_hist.exists():
        return results
    user_perf = _load_json(PUBLIC_HISTORY_DIR / "user_model_performance_history.json")
    user_holdings = _load_json(PUBLIC_HISTORY_DIR / "user_model_holdings_history.json")
    tseries_hist = _load_json(PUBLIC_HISTORY_DIR / "quantservice_tseries_discovery_history.json")
    internal_hist = _load_json(admin_hist)
    asofs = {
        "user_model_performance_history": user_perf.get("as_of_date"),
        "user_model_holdings_history": user_holdings.get("as_of_date"),
        "quantservice_tseries_discovery_history": tseries_hist.get("as_of_date"),
        "internal_model_performance_history": internal_hist.get("as_of_date"),
    }
    results.append(CheckResult("history_payload_asof_match", _status_from_bool(all(v == asof for v in asofs.values())), asofs))
    return results


def _check_admin_and_trading_payloads(asof: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    admin_path = ADMIN_CURRENT_DIR / "admin_new_entry_tracker.json"
    if not admin_path.exists():
        results.append(CheckResult("admin_new_entry_tracker_exists", "fail", {"path": str(admin_path)}))
    else:
        admin = _load_json(admin_path)
        results.append(CheckResult("admin_new_entry_tracker_asof_match", _status_from_bool(admin.get("as_of_date") == asof), {"as_of_date": admin.get("as_of_date")}))

    missing = [name for name in REQUIRED_TRADING_SIGN_FILES if not (TRADING_SIGN_CURRENT_DIR / name).exists()]
    results.append(CheckResult("trading_sign_files_exist", _status_from_bool(not missing), {"missing": missing}))
    if not missing:
        asofs = {}
        for name in REQUIRED_TRADING_SIGN_FILES:
            payload = _load_json(TRADING_SIGN_CURRENT_DIR / name)
            asofs[name] = payload.get("asof")
        results.append(CheckResult("trading_sign_asof_match", _status_from_bool(all(v == asof for v in asofs.values())), asofs))
    return results


def _check_data_dbs(asof: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    price_max = _max_date(PRICE_DB, "prices_daily")
    regime_max = _max_date(REGIME_DB, "regime_history")
    s3_price_max = _max_date(S3_FEATURE_DB, "s3_price_features_daily")
    s3_fund_max = _max_date(S3_FEATURE_DB, "s3_fund_features_monthly")
    fund_max = _max_date(FUNDAMENTALS_DB, "fundamentals_monthly_mix400_latest")
    prev_calendar_month_end = _previous_month_end(asof)
    prev_month_end = _previous_month_trading_end(asof)
    results.append(CheckResult("price_db_freshness", _status_from_bool(price_max is not None and price_max >= asof), {"max_date": price_max, "expected_at_least": asof}))
    results.append(CheckResult("regime_db_freshness", _status_from_bool(regime_max is not None and regime_max >= asof), {"max_date": regime_max, "expected_at_least": asof}))
    results.append(CheckResult("s3_price_features_freshness", _status_from_bool(s3_price_max is not None and s3_price_max >= asof), {"max_date": s3_price_max, "expected_at_least": asof}))
    month_detail = {"expected_at_least": prev_month_end, "calendar_month_end": prev_calendar_month_end, "basis": "previous_month_last_trading_day"}
    results.append(CheckResult("s3_fund_features_monthly_alignment", _status_from_bool(s3_fund_max is not None and s3_fund_max >= prev_month_end), {"max_date": s3_fund_max, **month_detail}))
    results.append(CheckResult("fundamentals_monthly_alignment", _status_from_bool(fund_max is not None and fund_max >= prev_month_end), {"max_date": fund_max, **month_detail}))

    with sqlite3.connect(str(PRICE_DB)) as con:
        duplicate_rows = con.execute(
            """
            SELECT COUNT(*)
            FROM (
              SELECT ticker, date, COUNT(*) AS c
              FROM prices_daily
              WHERE date = ?
              GROUP BY ticker, date
              HAVING c > 1
            )
            """,
            (asof,),
        ).fetchone()[0]
    results.append(CheckResult("price_db_duplicate_rows_asof", _status_from_bool(int(duplicate_rows) == 0), {"duplicate_rows": int(duplicate_rows), "asof": asof}))

    stock_tickers = _read_tickers(STOCK_UNIVERSE)
    expected, actual, ratio = _price_coverage(stock_tickers, asof)
    results.append(
        CheckResult(
            "stock_universe_price_coverage",
            _status_from_bool(ratio >= 0.98),
            {"universe_file": str(STOCK_UNIVERSE), "expected": expected, "actual": actual, "coverage": round(ratio, 6)},
        )
    )
    etf_tickers = _read_tickers(ETF_UNIVERSE)
    expected, actual, ratio = _price_coverage(etf_tickers, asof)
    results.append(
        CheckResult(
            "etf_universe_price_coverage",
            _status_from_bool(ratio >= 0.95),
            {"universe_file": str(ETF_UNIVERSE), "expected": expected, "actual": actual, "coverage": round(ratio, 6)},
        )
    )
    return results


def _check_model_publish_db(asof: str) -> list[CheckResult]:
    if not QUANT_SERVICE_DB.exists():
        return [CheckResult("quant_service_db_exists", "fail", {"path": str(QUANT_SERVICE_DB)})]
    with sqlite3.connect(str(QUANT_SERVICE_DB)) as con:
        run_rows = con.execute(
            """
            SELECT model_code, COUNT(*)
            FROM run_runs
            WHERE asof_date = ?
              AND status = 'completed'
            GROUP BY model_code
            """,
            (asof,),
        ).fetchall()
        pub_rows = con.execute(
            """
            SELECT model_code, data_asof, signal_asof, latest_holdings_count
            FROM pub_model_current
            WHERE model_code IN ('S2','S3','S3_CORE2','S4','S5','S6')
            ORDER BY model_code
            """
        ).fetchall()

    run_counts = {str(row[0]): int(row[1]) for row in run_rows}
    published = {
        str(row[0]): {
            "data_asof": row[1],
            "signal_asof": row[2],
            "latest_holdings_count": row[3],
        }
        for row in pub_rows
    }
    missing_runs = [model for model in REQUIRED_PUBLISHED_MODELS if run_counts.get(model, 0) <= 0]
    stale_published = {
        model: payload
        for model, payload in published.items()
        if payload.get("data_asof") != asof
    }
    missing_published = [model for model in REQUIRED_PUBLISHED_MODELS if model not in published]
    return [
        CheckResult("quant_service_completed_runs_asof", _status_from_bool(not missing_runs), {"run_counts": run_counts, "missing_models": missing_runs}),
        CheckResult(
            "quant_service_current_publish_asof",
            _status_from_bool(not stale_published and not missing_published),
            {"published": published, "stale_models": stale_published, "missing_models": missing_published},
        ),
    ]


def _check_tseries_db(asof: str) -> list[CheckResult]:
    if not TSERIES_DB.exists():
        return [CheckResult("tseries_operational_db_exists", "fail", {"path": str(TSERIES_DB)})]
    with sqlite3.connect(str(TSERIES_DB)) as con:
        current_profiles = con.execute(
            """
            SELECT model_code, profile_code, COUNT(*), GROUP_CONCAT(asof_date)
            FROM ts_threshold_profiles
            WHERE is_current = 1
            GROUP BY model_code, profile_code
            """
        ).fetchall()
        candidate_rows = con.execute(
            """
            SELECT model_code, asof_date, COUNT(*)
            FROM ts_candidates_latest
            WHERE asof_date <= ?
            GROUP BY model_code, asof_date
            """,
            (asof,),
        ).fetchall()
        rolling_rows = con.execute(
            """
            SELECT model_code, asof_date, watch_status, COUNT(*)
            FROM ts_rolling_watchlist_latest
            WHERE asof_date <= ?
            GROUP BY model_code, asof_date, watch_status
            """,
            (asof,),
        ).fetchall()

    profile_counts = {f"{row[0]}::{row[1]}": {"count": int(row[2]), "asof_dates": row[3]} for row in current_profiles}
    expected_profiles = {("T-STOCK-V01", "operating_v2"), ("T-ETF-V01", "operational_pit_v1")}
    actual_profiles = {(row[0], row[1]) for row in current_profiles}
    profile_ok = actual_profiles == expected_profiles and all(v["count"] == 1 for v in profile_counts.values())
    candidate_latest: dict[str, dict[str, object]] = {}
    for model_code, row_asof, count in candidate_rows:
        current = candidate_latest.get(str(model_code))
        if current is None or str(row_asof) > str(current["asof_date"]):
            candidate_latest[str(model_code)] = {"asof_date": str(row_asof), "count": int(count)}

    rolling_latest_asof: dict[str, str] = {}
    for model_code, row_asof, _status, _count in rolling_rows:
        model = str(model_code)
        if model not in rolling_latest_asof or str(row_asof) > rolling_latest_asof[model]:
            rolling_latest_asof[model] = str(row_asof)
    rolling = [
        {"model_code": row[0], "asof_date": row[1], "watch_status": row[2], "count": int(row[3])}
        for row in rolling_rows
        if rolling_latest_asof.get(str(row[0])) == str(row[1])
    ]
    candidate_ok = (
        candidate_latest.get("T-STOCK-V01", {}).get("asof_date") == asof
        and int(candidate_latest.get("T-STOCK-V01", {}).get("count", 0)) > 0
        and bool(candidate_latest.get("T-ETF-V01", {}).get("asof_date"))
        and str(candidate_latest.get("T-ETF-V01", {}).get("asof_date")) <= asof
        and int(candidate_latest.get("T-ETF-V01", {}).get("count", 0)) > 0
    )
    rolling_ok = (
        any(row["model_code"] == "T-STOCK-V01" and row["asof_date"] == asof for row in rolling)
        and any(row["model_code"] == "T-ETF-V01" and str(row["asof_date"]) <= asof for row in rolling)
    )
    return [
        CheckResult("tseries_current_profile_uniqueness", _status_from_bool(profile_ok), {"profiles": profile_counts}),
        CheckResult(
            "tseries_latest_candidates_exist",
            _status_from_bool(candidate_ok),
            {"candidate_latest": candidate_latest, "rule": "T-STOCK exact asof; T-ETF native PIT/monthly asof may be <= pipeline asof"},
        ),
        CheckResult("tseries_rolling_watchlist_states", _status_from_bool(rolling_ok), {"states": rolling}),
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate end-to-end daily Quant pipeline contract before remote publish.")
    ap.add_argument("--asof", required=True, help="Expected operating as-of date, YYYY-MM-DD")
    ap.add_argument("--report-dir", default=str(ROOT / r"reports\data_quality\pipeline_contract"))
    args = ap.parse_args()

    asof = str(args.asof)
    results: list[CheckResult] = []
    results.extend(_check_data_dbs(asof))
    results.extend(_check_model_publish_db(asof))
    results.extend(_check_tseries_db(asof))
    results.extend(_check_public_payloads(asof))
    results.extend(_check_history_payloads(asof))
    results.extend(_check_admin_and_trading_payloads(asof))

    failures = [item for item in results if item.status == "fail"]
    warnings = [item for item in results if item.status == "warn"]
    payload = {
        "asof": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "fail" if failures else ("warn" if warnings else "pass"),
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "checks": [item.__dict__ for item in results],
    }

    out_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"daily_pipeline_contract_{asof.replace('-', '')}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "asof": asof, "report": str(out_path), "failures": [item.name for item in failures]}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
