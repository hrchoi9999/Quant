from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(r"D:\Quant")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service_platform.publishers.build_user_facing_snapshots import load_mapping
from src.quant_service.read_tseries_operational import (
    _append_latest_mark_to_market,
    _build_portfolio_nav,
    _normalize_history_bucket,
    load_candidate_history,
    load_latest_candidates,
)

PUBLIC_HISTORY_DIR = ROOT / r"service_platform\web\public_data\history"
ADMIN_CURRENT_DIR = ROOT / r"service_platform\web\admin_data\current"
QUANT_SERVICE_DB = ROOT / r"data\db\quant_service.db"
TSERIES_DB = ROOT / r"data\db\tseries_operational.db"
ISERIES_DB = ROOT / r"data\db\i_series_operational.db"
REPORT_DIR = ROOT / r"reports\redbot_user_reports"
REPORT_DATE_RE = re.compile(r"_(20\d{6})\.json$")
INTERNAL_MODEL_CODES = ("S2", "S2_PIT_V01", "S3", "S3_CORE2", "S3_ACCEL_V01", "S4", "S5", "S6")
ISERIES_MODEL_CODES = ("I-STOCK-STRONG-RSI-V01",)
TSERIES_MODEL_CODES = ("T-STOCK-V01", "T-ETF-V01")
TRADING_WINDOWS = {
    "1w": 5,
    "2w": 10,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "1y": 252,
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _report_date(path: Path) -> str | None:
    match = REPORT_DATE_RE.search(path.name)
    if not match:
        return None
    token = match.group(1)
    return f"{token[:4]}-{token[4:6]}-{token[6:8]}"


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_period_map(perf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    period_map: dict[str, dict[str, Any]] = {}
    for row in perf.get("period_metrics", []) or []:
        period = str(row.get("period") or "").upper()
        if period:
            period_map[period] = row
    return period_map


def _rank_portfolio_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    sortable: list[tuple[float, int, dict[str, Any]]] = []
    for idx, item in enumerate(items):
        try:
            weight = float(item.get("target_weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        sortable.append((weight, idx, dict(item)))
    for rank_no, (_, _, item) in enumerate(sorted(sortable, key=lambda row: (-row[0], row[1])), start=1):
        item["rank_no"] = rank_no
        item["strategy_fit_score"] = round(float(item.get("target_weight") or 0.0), 6)
        ranked.append(item)
    return ranked


def build_user_model_performance_history(mapping: dict[str, Any], asof: str, generated_at: str) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    for row in mapping["user_models"]:
        profile = str(row["service_profile"])
        for path in sorted(REPORT_DIR.glob(f"redbot_user_report_{profile}_*.json")):
            report_asof = _report_date(path)
            if not report_asof or report_asof > asof:
                continue
            report = _load_report(path)
            perf = report.get("recent_performance") or {}
            headline = perf.get("headline_metrics") or {}
            period_map = _extract_period_map(perf)
            full_metric = headline.get("reference_full") or period_map.get("FULL") or {}
            series.append(
                {
                    "asof_date": report_asof,
                    "service_profile": profile,
                    "cagr": headline.get("cagr"),
                    "trailing_3m": (headline.get("trailing_3m") or period_map.get("3M") or {}).get("total_return"),
                    "trailing_6m": (headline.get("trailing_6m") or period_map.get("6M") or {}).get("total_return"),
                    "trailing_1y": (headline.get("trailing_1y") or period_map.get("1Y") or {}).get("total_return"),
                    "mdd_1y": (headline.get("trailing_1y") or period_map.get("1Y") or {}).get("mdd"),
                    "sharpe_1y": (headline.get("trailing_1y") or period_map.get("1Y") or {}).get("sharpe"),
                    "itd_return": full_metric.get("total_return"),
                }
            )
    return {
        "source_name": "handoff:user_model_performance_history",
        "schema_version": "v1",
        "as_of_date": asof,
        "generated_at": generated_at,
        "scope": "user",
        "timezone": "Asia/Seoul",
        "interval": "1w",
        "series": sorted(series, key=lambda row: (row["asof_date"], row["service_profile"])),
    }


def build_user_model_holdings_history(mapping: dict[str, Any], asof: str, generated_at: str) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    for row in mapping["user_models"]:
        profile = str(row["service_profile"])
        history: list[dict[str, Any]] = []
        for path in sorted(REPORT_DIR.glob(f"redbot_user_report_{profile}_*.json")):
            report_asof = _report_date(path)
            if not report_asof or report_asof > asof:
                continue
            report = _load_report(path)
            ranked = _rank_portfolio_items(report.get("model_portfolio") or report.get("recommended_portfolio") or [])
            holdings: dict[str, dict[str, Any]] = {}
            for item in ranked:
                code = str(item.get("security_code") or "").strip()
                if not code:
                    continue
                holdings[code.zfill(6)] = {
                    "display_name": item.get("display_name") or code,
                    "target_weight": round(float(item.get("target_weight") or 0.0), 6),
                    "rank_no": int(item["rank_no"]),
                    "strategy_fit_score": round(float(item["strategy_fit_score"]), 6),
                }
            history.append({"asof_date": report_asof, "holdings": holdings})
        if len(history) < 2:
            continue
        seen_before: set[str] = set(history[0]["holdings"].keys())
        for prev, curr in zip(history[:-1], history[1:]):
            prev_map = prev["holdings"]
            curr_map = curr["holdings"]
            for code in sorted(set(prev_map) | set(curr_map)):
                prev_item = prev_map.get(code)
                curr_item = curr_map.get(code)
                prev_weight = 0.0 if prev_item is None else float(prev_item["target_weight"])
                curr_weight = 0.0 if curr_item is None else float(curr_item["target_weight"])
                if prev_item is None and curr_item is not None:
                    event_type = "re_entry" if code in seen_before else "new_entry"
                elif prev_item is not None and curr_item is None:
                    event_type = "exit"
                elif curr_weight > prev_weight:
                    event_type = "weight_increase"
                elif curr_weight < prev_weight:
                    event_type = "decrease"
                else:
                    continue
                display = (curr_item or prev_item or {}).get("display_name") or code
                series.append(
                    {
                        "asof_date": curr["asof_date"],
                        "service_profile": profile,
                        "security_code": code,
                        "display_name": display,
                        "target_weight": round(curr_weight, 6),
                        "rank_no": None if curr_item is None else int(curr_item["rank_no"]),
                        "strategy_fit_score": None if curr_item is None else round(float(curr_item["strategy_fit_score"]), 6),
                        "event_type": event_type,
                    }
                )
                if curr_item is not None:
                    seen_before.add(code)
    return {
        "source_name": "handoff:user_model_holdings_history",
        "schema_version": "v1",
        "as_of_date": asof,
        "generated_at": generated_at,
        "scope": "user",
        "timezone": "Asia/Seoul",
        "interval": "1w",
        "series": sorted(series, key=lambda row: (row["asof_date"], row["service_profile"], row["security_code"], row["event_type"])),
    }


def _build_nav_history_series(
    *,
    model_code: str,
    display_name: str,
    nav_df: pd.DataFrame,
    asof_date: str,
    metric_basis: str,
) -> list[dict[str, Any]]:
    work = nav_df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["nav"] = pd.to_numeric(work["nav"], errors="coerce")
    work = work.dropna(subset=["date", "nav"]).sort_values("date").reset_index(drop=True)
    if len(work) < 2:
        return []
    rows: list[dict[str, Any]] = []
    for idx in range(1, len(work)):
        latest_nav = float(work.at[idx, "nav"])
        first_nav = float(work.at[0, "nav"])
        elapsed_years = max((work.at[idx, "date"] - work.at[0, "date"]).days / 365.25, 1.0 / 252.0)
        cagr = None if first_nav <= 0 else round((latest_nav / first_nav) ** (1.0 / elapsed_years) - 1.0, 6)
        row: dict[str, Any] = {
            "asof_date": work.at[idx, "date"].strftime("%Y-%m-%d"),
            "model_code": model_code,
            "display_name": display_name,
            "cagr": cagr,
            "metric_basis": metric_basis,
        }
        for label, steps in TRADING_WINDOWS.items():
            start_idx = idx - steps
            if start_idx < 0:
                row[f"trailing_{label}"] = None
                continue
            start_nav = float(work.at[start_idx, "nav"])
            row[f"trailing_{label}"] = None if start_nav == 0 else round(latest_nav / start_nav - 1.0, 6)
        peak = work.loc[max(0, idx - 252) : idx, "nav"].cummax()
        dd = work.loc[max(0, idx - 252) : idx, "nav"] / peak - 1.0
        row["mdd_1y"] = round(float(dd.min()), 6) if not dd.empty else None
        ret_window = work.loc[max(0, idx - 252) : idx, "nav"].pct_change().dropna()
        if ret_window.empty or float(ret_window.std(ddof=0)) <= 0:
            row["sharpe_1y"] = None
        else:
            row["sharpe_1y"] = round(float(ret_window.mean() / ret_window.std(ddof=0) * (252.0 ** 0.5)), 6)
        row["itd_return"] = None if first_nav == 0 else round(latest_nav / first_nav - 1.0, 6)
        rows.append(row)
    return [row for row in rows if row["asof_date"] <= asof_date]


def build_internal_model_performance_history(asof: str, generated_at: str) -> dict[str, Any]:
    if not QUANT_SERVICE_DB.exists():
        series: list[dict[str, Any]] = []
    else:
        with sqlite3.connect(str(QUANT_SERVICE_DB)) as con:
            published = pd.read_sql_query(
                f"""
                SELECT model_code, display_name
                FROM pub_model_current
                WHERE model_code IN ({",".join(["?"] * len(INTERNAL_MODEL_CODES))})
                ORDER BY model_code
                """,
                con,
                params=list(INTERNAL_MODEL_CODES),
            )
            series = []
            for row in published.itertuples(index=False):
                nav = pd.read_sql_query(
                    """
                    SELECT date, nav
                    FROM pub_model_nav_history
                    WHERE model_code = ?
                      AND date <= ?
                    ORDER BY date
                    """,
                    con,
                    params=[str(row.model_code), asof],
                )
                series.extend(
                    _build_nav_history_series(
                        model_code=str(row.model_code),
                        display_name=str(row.display_name),
                        nav_df=nav,
                        asof_date=asof,
                        metric_basis="published_backtest",
                    )
                )
    if ISERIES_DB.exists():
        with sqlite3.connect(str(ISERIES_DB)) as con:
            meta = pd.read_sql_query(
                """
                SELECT model_code, display_name
                FROM is_meta_models
                WHERE model_code IN ('I-STOCK-STRONG-RSI-V01')
                """,
                con,
            )
            for row in meta.itertuples(index=False):
                nav = pd.read_sql_query(
                    """
                    SELECT date, nav
                    FROM is_backtest_nav
                    WHERE date <= ?
                    ORDER BY date
                    """,
                    con,
                    params=[asof],
                )
                series.extend(
                    _build_nav_history_series(
                        model_code=str(row.model_code),
                        display_name=str(row.display_name),
                        nav_df=nav,
                        asof_date=asof,
                        metric_basis="i_series_shadow_backtest",
                    )
                )
    return {
        "source_name": "handoff:internal_model_performance_history",
        "schema_version": "v1",
        "as_of_date": asof,
        "generated_at": generated_at,
        "scope": "internal",
        "timezone": "Asia/Seoul",
        "interval": "1d",
        "series": sorted(series, key=lambda row: (row["asof_date"], row["model_code"])),
    }


def _compute_tseries_history_rows(model_code: str, asof: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with sqlite3.connect(str(TSERIES_DB)) as con:
        hist = pd.read_sql_query(
            """
            SELECT model_code, signal_date AS asof_date, candidate_bucket, ticker
            FROM ts_candidates_history
            WHERE model_code = ?
              AND signal_date <= ?
            """,
            con,
            params=[model_code, asof],
        )
        latest = pd.read_sql_query(
            """
            SELECT model_code, asof_date, candidate_bucket, ticker
            FROM ts_candidates_latest
            WHERE model_code = ?
              AND asof_date <= ?
            """,
            con,
            params=[model_code, asof],
        )
        rolling_summary = pd.read_sql_query(
            """
            SELECT model_code, asof_date, bucket, count
            FROM ts_rolling_watchlist_summary
            WHERE model_code = ?
              AND asof_date <= ?
            ORDER BY asof_date, bucket
            """,
            con,
            params=[model_code, asof],
        )
        meta_row = con.execute(
            "SELECT display_name FROM ts_meta_models WHERE model_code = ?",
            (model_code,),
        ).fetchone()
        display_name = model_code if meta_row is None else str(meta_row[0])
        candidate_history = load_candidate_history(con, model_code)
        nav_df = _build_portfolio_nav(candidate_history, model_code)
        current_candidates = load_latest_candidates(con, model_code, asof)
        nav_df = _append_latest_mark_to_market(nav_df, current_candidates, asof, model_code)

    snap = pd.concat([hist, latest], ignore_index=True)
    if snap.empty:
        return rows
    snap["asof_date"] = pd.to_datetime(snap["asof_date"]).dt.strftime("%Y-%m-%d")
    snap["mapped_bucket"] = snap["candidate_bucket"].map(_normalize_history_bucket)
    snap["ticker"] = snap["ticker"].astype(str).str.zfill(6)

    bucket_counts = (
        snap.groupby(["asof_date", "mapped_bucket"], as_index=False)
        .agg(count=("ticker", "nunique"))
        .pivot(index="asof_date", columns="mapped_bucket", values="count")
        .fillna(0)
        .reset_index()
    )
    bucket_count_map = {
        str(row["asof_date"]): {
            "confirmed": int(row.get("confirmed", 0) or 0),
            "near": int(row.get("near", 0) or 0),
            "observe": int(row.get("observe", 0) or 0),
        }
        for row in bucket_counts.to_dict(orient="records")
    }

    rolling_map: dict[str, dict[str, int]] = {}
    if not rolling_summary.empty:
        rolling_summary["asof_date"] = pd.to_datetime(rolling_summary["asof_date"]).dt.strftime("%Y-%m-%d")
        for asof_date, frame in rolling_summary.groupby("asof_date", sort=True):
            rolling_map[asof_date] = {str(bucket): int(count) for bucket, count in zip(frame["bucket"], frame["count"])}

    perf_rows = _build_nav_history_series(
        model_code=model_code,
        display_name=display_name,
        nav_df=nav_df,
        asof_date=asof,
        metric_basis="shadow_portfolio",
    )
    perf_map = {row["asof_date"]: row for row in perf_rows}

    all_dates = sorted(set(bucket_count_map) | set(rolling_map) | set(perf_map))
    for event_date in all_dates:
        perf = perf_map.get(event_date, {})
        rows.append(
            {
                "asof_date": event_date,
                "model_code": model_code,
                "bucket_counts": bucket_count_map.get(event_date, {"confirmed": 0, "near": 0, "observe": 0}),
                "performance_summary": {
                    "headline_metrics": {
                        "cagr": perf.get("cagr"),
                        "mdd_1y": perf.get("mdd_1y"),
                        "sharpe_1y": perf.get("sharpe_1y"),
                        "trailing_1m": perf.get("trailing_1m"),
                        "trailing_3m": perf.get("trailing_3m"),
                        "trailing_6m": perf.get("trailing_6m"),
                        "trailing_1y": perf.get("trailing_1y"),
                        "itd_return": perf.get("itd_return"),
                    },
                    "metric_basis": "shadow_portfolio",
                },
                "rolling_watchlist": {
                    "summary": {
                        "new": int((rolling_map.get(event_date) or {}).get("new", 0)),
                        "active": int((rolling_map.get(event_date) or {}).get("active", 0)),
                        "cooling": int((rolling_map.get(event_date) or {}).get("cooling", 0)),
                    }
                },
                "items_count": int(sum((bucket_count_map.get(event_date) or {"confirmed": 0, "near": 0, "observe": 0}).values())),
            }
        )
    return rows


def build_tseries_discovery_history(asof: str, generated_at: str) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    if TSERIES_DB.exists():
        for model_code in TSERIES_MODEL_CODES:
            series.extend(_compute_tseries_history_rows(model_code, asof))
    return {
        "source_name": "handoff:tseries_discovery_history",
        "schema_version": "v1",
        "as_of_date": asof,
        "generated_at": generated_at,
        "scope": "tseries",
        "timezone": "Asia/Seoul",
        "interval": "1w",
        "series": sorted(series, key=lambda row: (row["asof_date"], row["model_code"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build redbot history payloads.")
    parser.add_argument("--asof", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    mapping = load_mapping()
    generated_at = datetime.now().isoformat(timespec="seconds")
    user_perf = build_user_model_performance_history(mapping, args.asof, generated_at)
    user_holdings = build_user_model_holdings_history(mapping, args.asof, generated_at)
    internal_perf = build_internal_model_performance_history(args.asof, generated_at)
    tseries_hist = build_tseries_discovery_history(args.asof, generated_at)

    _write_json(PUBLIC_HISTORY_DIR / "user_model_performance_history.json", user_perf)
    _write_json(PUBLIC_HISTORY_DIR / "user_model_holdings_history.json", user_holdings)
    _write_json(ADMIN_CURRENT_DIR / "internal_model_performance_history.json", internal_perf)
    _write_json(PUBLIC_HISTORY_DIR / "quantservice_tseries_discovery_history.json", tseries_hist)

    print(
        json.dumps(
            {
                "as_of_date": args.asof,
                "generated_at": generated_at,
                "user_model_performance_rows": len(user_perf["series"]),
                "user_model_holdings_rows": len(user_holdings["series"]),
                "internal_model_performance_rows": len(internal_perf["series"]),
                "tseries_history_rows": len(tseries_hist["series"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
