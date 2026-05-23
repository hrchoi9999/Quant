from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "valuation_ai"
PRICE_DB = ROOT / "data" / "db" / "price.db"
OUT_DB = ROOT / "data" / "db" / "valuation_ai.db"
MODEL_CODE = "AI-GROWTH-VALUATION-V01"

HORIZONS = {
    "1w": 5,
    "2w": 10,
    "1m": 21,
    "2m": 42,
    "3m": 63,
    "6m": 126,
    "1y": 252,
}
SNAPSHOT_RE = re.compile(r"^valuation_overlay_current_candidates_(\d{8})\.csv$")
FAVORABLE_STATES = {"UNDERVALUED", "FAIR"}
CAUTION_STATES = {"OVERHEATED", "AVOID"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build live shadow tracking for AI-GROWTH-VALUATION-V01 valuation overlay states.")
    parser.add_argument("--shadow-asof", required=True, help="Overlay snapshot asof date, YYYY-MM-DD, or 'all'.")
    parser.add_argument("--asof", required=True, help="Performance asof date, YYYY-MM-DD.")
    parser.add_argument("--lookback-days", type=int, default=180)
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    return parser.parse_args()


def available_shadow_asofs(report_dir: Path, asof: str, lookback_days: int) -> list[str]:
    asof_ts = pd.Timestamp(asof)
    min_ts = asof_ts - pd.Timedelta(days=int(lookback_days))
    dates: list[str] = []
    for path in report_dir.glob("valuation_overlay_current_candidates_*.csv"):
        match = SNAPSHOT_RE.match(path.name)
        if not match:
            continue
        ts = pd.Timestamp(datetime.strptime(match.group(1), "%Y%m%d").date())
        if min_ts <= ts <= asof_ts:
            dates.append(ts.strftime("%Y-%m-%d"))
    return sorted(set(dates))


def load_overlay_snapshot(report_dir: Path, shadow_asof: str) -> pd.DataFrame:
    token = shadow_asof.replace("-", "")
    path = report_dir / f"valuation_overlay_current_candidates_{token}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, dtype={"security_code": str}, low_memory=False)
    df["security_code"] = df["security_code"].astype(str).str.zfill(6)
    df["shadow_asof_date"] = shadow_asof
    df["track_start_date"] = pd.to_datetime(df.get("snapshot_date"), errors="coerce")
    if df["track_start_date"].isna().any():
        fallback = pd.to_datetime(df.get("week_end"), errors="coerce")
        df["track_start_date"] = df["track_start_date"].fillna(fallback)
    df["valuation_state"] = df["valuation_state"].fillna("OUT_OF_SCOPE_OR_MISSING")
    df["valuation_group"] = df["valuation_state"].map(state_group)
    return df.dropna(subset=["security_code", "track_start_date"])


def state_group(state: Any) -> str:
    text = str(state or "OUT_OF_SCOPE_OR_MISSING")
    if text in FAVORABLE_STATES:
        return "FAVORABLE"
    if text in CAUTION_STATES:
        return "CAUTION"
    return "OUT_OF_SCOPE_OR_MISSING"


def load_prices(tickers: list[str], max_date: str) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(tickers))
    with sqlite3.connect(str(PRICE_DB)) as con:
        df = pd.read_sql_query(
            f"""
            SELECT ticker, date, close
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date <= ?
              AND close IS NOT NULL
            ORDER BY ticker, date
            """,
            con,
            params=[*tickers, max_date],
        )
    if df.empty:
        return df
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["ticker", "date", "close"])


def max_drawdown(closes: pd.Series) -> float | None:
    vals = pd.to_numeric(closes, errors="coerce").dropna()
    if len(vals) < 2:
        return None
    running_max = vals.cummax()
    drawdown = vals / running_max - 1.0
    return round(float(drawdown.min()), 6)


def sharpe_ratio(closes: pd.Series) -> float | None:
    vals = pd.to_numeric(closes, errors="coerce").dropna()
    if len(vals) < 3:
        return None
    returns = vals.pct_change().dropna()
    if returns.empty:
        return None
    std = float(returns.std(ddof=0))
    if std == 0:
        return None
    return round(float(returns.mean()) / std * (252 ** 0.5), 6)


def calc_window_metrics(
    price_frame: pd.DataFrame,
    start_date: pd.Timestamp,
    asof_date: pd.Timestamp,
    trading_days: int | None = None,
    require_full_window: bool = False,
) -> dict[str, Any]:
    hist = price_frame[(price_frame["date"] >= start_date) & (price_frame["date"] <= asof_date)].sort_values("date").reset_index(drop=True)
    if hist.empty:
        return {"return": None, "end_date": None, "available": 0, "trading_days_seen": 0, "mdd": None, "sharpe": None}
    if require_full_window and trading_days is not None and len(hist) <= int(trading_days):
        return {
            "return": None,
            "end_date": None,
            "available": 0,
            "trading_days_seen": int(len(hist)),
            "mdd": None,
            "sharpe": None,
        }
    if trading_days is None:
        target_idx = len(hist) - 1
    else:
        target_idx = min(int(trading_days), len(hist) - 1)
    if target_idx <= 0:
        return {
            "return": None,
            "end_date": None,
            "available": 0,
            "trading_days_seen": int(len(hist)),
            "mdd": None,
            "sharpe": None,
        }
    window = hist.iloc[: target_idx + 1].copy()
    start_close = float(window.iloc[0]["close"])
    end_close = float(window.iloc[-1]["close"])
    if start_close <= 0:
        ret = None
    else:
        ret = round(end_close / start_close - 1.0, 6)
    required = target_idx if trading_days is None else int(trading_days)
    return {
        "return": ret,
        "end_date": pd.Timestamp(window.iloc[-1]["date"]).strftime("%Y-%m-%d"),
        "available": int(len(hist) > required),
        "trading_days_seen": int(len(hist)),
        "mdd": max_drawdown(window["close"]),
        "sharpe": sharpe_ratio(window["close"]),
    }


def build_detail(snapshot: pd.DataFrame, performance_asof: str) -> pd.DataFrame:
    asof_ts = pd.Timestamp(performance_asof)
    prices = load_prices(sorted(snapshot["security_code"].dropna().unique().tolist()), performance_asof)
    price_groups = {ticker: frame for ticker, frame in prices.groupby("ticker")} if not prices.empty else {}
    rows: list[dict[str, Any]] = []
    for row in snapshot.to_dict(orient="records"):
        ticker = str(row.get("security_code")).zfill(6)
        track_start = pd.Timestamp(row["track_start_date"]).normalize()
        price_frame = price_groups.get(ticker)
        item: dict[str, Any] = {
            "ai_model_code": MODEL_CODE,
            "shadow_asof_date": row.get("shadow_asof_date"),
            "performance_asof_date": performance_asof,
            "scope": row.get("scope"),
            "model_code": row.get("model_code"),
            "service_profile": row.get("service_profile"),
            "security_code": ticker,
            "display_name": row.get("display_name"),
            "rank_no": row.get("rank_no"),
            "score": row.get("score"),
            "score_basis": row.get("score_basis"),
            "weight": row.get("weight"),
            "candidate_bucket": row.get("candidate_bucket"),
            "snapshot_date": row.get("snapshot_date"),
            "week_end": row.get("week_end"),
            "track_start_date": track_start.strftime("%Y-%m-%d"),
            "valuation_coverage_status": row.get("valuation_coverage_status"),
            "valuation_state": row.get("valuation_state"),
            "valuation_group": row.get("valuation_group"),
            "valuation_ai_score": row.get("valuation_ai_score"),
            "predicted_excess_return_12m": row.get("predicted_excess_return_12m"),
            "current_valuation_percentile": row.get("current_valuation_percentile"),
            "implied_growth_pressure": row.get("implied_growth_pressure"),
            "valuation_growth_gap": row.get("valuation_growth_gap"),
            "outperform_prob": row.get("outperform_prob"),
            "underperform_prob": row.get("underperform_prob"),
            "overheated_prob": row.get("overheated_prob"),
            "reason_codes": row.get("reason_codes"),
        }
        if price_frame is None or price_frame.empty:
            item["live_current_return"] = None
            item["live_current_mdd"] = None
            item["live_current_sharpe"] = None
            item["live_current_end_date"] = None
            item["live_current_trading_days_seen"] = 0
            for horizon in HORIZONS:
                item[f"live_ret_{horizon}"] = None
                item[f"live_mdd_{horizon}"] = None
                item[f"live_sharpe_{horizon}"] = None
                item[f"live_ret_{horizon}_end_date"] = None
                item[f"live_ret_{horizon}_available"] = 0
                item[f"live_ret_{horizon}_trading_days_seen"] = 0
            rows.append(item)
            continue
        current = calc_window_metrics(price_frame, track_start, asof_ts, None)
        item["live_current_return"] = current["return"]
        item["live_current_mdd"] = current["mdd"]
        item["live_current_sharpe"] = current["sharpe"]
        item["live_current_end_date"] = current["end_date"]
        item["live_current_trading_days_seen"] = current["trading_days_seen"]
        for horizon, days in HORIZONS.items():
            metrics = calc_window_metrics(price_frame, track_start, asof_ts, days, require_full_window=True)
            item[f"live_ret_{horizon}"] = metrics["return"]
            item[f"live_mdd_{horizon}"] = metrics["mdd"]
            item[f"live_sharpe_{horizon}"] = metrics["sharpe"]
            item[f"live_ret_{horizon}_end_date"] = metrics["end_date"]
            item[f"live_ret_{horizon}_available"] = metrics["available"]
            item[f"live_ret_{horizon}_trading_days_seen"] = metrics["trading_days_seen"]
        rows.append(item)
    return pd.DataFrame(rows)


def metric_row(frame: pd.DataFrame, group_type: str, group_value: str, horizon: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if horizon == "current":
        ret_col = "live_current_return"
        mdd_col = "live_current_mdd"
        sharpe_col = "live_current_sharpe"
    else:
        ret_col = f"live_ret_{horizon}"
        mdd_col = f"live_mdd_{horizon}"
        sharpe_col = f"live_sharpe_{horizon}"
    vals = pd.to_numeric(frame.get(ret_col), errors="coerce").dropna()
    mdds = pd.to_numeric(frame.get(mdd_col), errors="coerce").dropna()
    sharpes = pd.to_numeric(frame.get(sharpe_col), errors="coerce").dropna()
    row: dict[str, Any] = {
        "ai_model_code": MODEL_CODE,
        "shadow_asof_date": frame["shadow_asof_date"].iloc[0] if not frame.empty and "shadow_asof_date" in frame else None,
        "performance_asof_date": frame["performance_asof_date"].iloc[0] if not frame.empty and "performance_asof_date" in frame else None,
        "group_type": group_type,
        "group_value": group_value,
        "horizon": horizon,
        "candidate_count": int(len(frame)),
        "sample_count": int(len(vals)),
        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
        "median_return": None if vals.empty else round(float(vals.median()), 6),
        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
        "mdd_sample_count": int(len(mdds)),
        "avg_mdd": None if mdds.empty else round(float(mdds.mean()), 6),
        "median_mdd": None if mdds.empty else round(float(mdds.median()), 6),
        "sharpe_sample_count": int(len(sharpes)),
        "avg_sharpe": None if sharpes.empty else round(float(sharpes.mean()), 6),
        "median_sharpe": None if sharpes.empty else round(float(sharpes.median()), 6),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if extra:
        row.update(extra)
    return row


def add_group_summary(rows: list[dict[str, Any]], frame: pd.DataFrame, group_type: str, group_value: str, extra: dict[str, Any] | None = None) -> None:
    for horizon in ["current", *HORIZONS.keys()]:
        rows.append(metric_row(frame, group_type, group_value, horizon, extra))


def build_summary(detail: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    add_group_summary(rows, detail, "all", "all")
    for state, frame in detail.groupby("valuation_state", dropna=False):
        add_group_summary(rows, frame, "valuation_state", str(state))
    for group, frame in detail.groupby("valuation_group", dropna=False):
        add_group_summary(rows, frame, "valuation_group", str(group))
    for scope, frame in detail.groupby("scope", dropna=False):
        add_group_summary(rows, frame, "scope", str(scope), {"scope": scope})
    for (scope, model), frame in detail.groupby(["scope", "model_code"], dropna=False):
        add_group_summary(rows, frame, "model", f"{scope}:{model}", {"scope": scope, "model_code": model})
    for (scope, model, state), frame in detail.groupby(["scope", "model_code", "valuation_state"], dropna=False):
        add_group_summary(rows, frame, "model_state", f"{scope}:{model}:{state}", {"scope": scope, "model_code": model})
    return pd.DataFrame(rows)


def table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def sqlite_type(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    return "TEXT"


def ensure_dataframe_columns(con: sqlite3.Connection, table_name: str, frame: pd.DataFrame) -> None:
    if not table_exists(con, table_name):
        return
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for column in frame.columns:
        if column not in existing:
            con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {sqlite_type(frame[column])}")


def upsert_tables(detail: pd.DataFrame, summary: pd.DataFrame, shadow_asof: str, performance_asof: str) -> None:
    with sqlite3.connect(str(OUT_DB)) as con:
        ensure_dataframe_columns(con, "valuation_overlay_live_shadow_detail", detail)
        ensure_dataframe_columns(con, "valuation_overlay_live_shadow_summary", summary)
        if table_exists(con, "valuation_overlay_live_shadow_detail"):
            con.execute(
                """
                DELETE FROM valuation_overlay_live_shadow_detail
                WHERE shadow_asof_date = ?
                  AND performance_asof_date = ?
                """,
                (shadow_asof, performance_asof),
            )
        if table_exists(con, "valuation_overlay_live_shadow_summary"):
            con.execute(
                """
                DELETE FROM valuation_overlay_live_shadow_summary
                WHERE shadow_asof_date = ?
                  AND performance_asof_date = ?
                """,
                (shadow_asof, performance_asof),
            )
        detail.to_sql("valuation_overlay_live_shadow_detail", con, if_exists="append", index=False)
        summary.to_sql("valuation_overlay_live_shadow_summary", con, if_exists="append", index=False)


def format_pct(value: Any) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.2%}"


def write_md(path: Path, shadow_asof: str, performance_asof: str, detail: pd.DataFrame, summary: pd.DataFrame) -> None:
    state = summary[(summary["group_type"] == "valuation_state") & (summary["horizon"].isin(["current", "1w", "2w", "1m"]))]
    group = summary[(summary["group_type"] == "valuation_group") & (summary["horizon"].isin(["current", "1w", "2w", "1m"]))]
    model_current = summary[(summary["group_type"] == "model") & (summary["horizon"] == "current")].copy()
    model_current = model_current.sort_values(["scope", "group_value"])
    lines = [
        f"# Valuation AI Live Shadow Tracker - {shadow_asof} to {performance_asof}",
        "",
        f"- model_code: `{MODEL_CODE}`",
        f"- shadow_asof_date: `{shadow_asof}`",
        f"- performance_asof_date: `{performance_asof}`",
        f"- detail_rows: `{len(detail)}`",
        f"- summary_rows: `{len(summary)}`",
        "",
        "## Valuation State Summary",
        "",
        "| state | horizon | samples | avg return | median return | win rate | avg MDD | avg Sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in state.sort_values(["group_value", "horizon"]).iterrows():
        sharpe = "N/A" if pd.isna(row["avg_sharpe"]) else f"{float(row['avg_sharpe']):.3f}"
        lines.append(
            f"| {row['group_value']} | {row['horizon']} | {int(row['sample_count'])} | "
            f"{format_pct(row['avg_return'])} | {format_pct(row['median_return'])} | {format_pct(row['win_rate'])} | "
            f"{format_pct(row['avg_mdd'])} | {sharpe} |"
        )
    lines.extend(
        [
            "",
            "## Valuation Group Summary",
            "",
            "| group | horizon | samples | avg return | win rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in group.sort_values(["group_value", "horizon"]).iterrows():
        lines.append(f"| {row['group_value']} | {row['horizon']} | {int(row['sample_count'])} | {format_pct(row['avg_return'])} | {format_pct(row['win_rate'])} |")
    lines.extend(
        [
            "",
            "## Model Current Summary",
            "",
            "| model | candidates | samples | avg current return | avg MDD | avg Sharpe |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in model_current.iterrows():
        sharpe = "N/A" if pd.isna(row["avg_sharpe"]) else f"{float(row['avg_sharpe']):.3f}"
        lines.append(f"| {row['group_value']} | {int(row['candidate_count'])} | {int(row['sample_count'])} | {format_pct(row['avg_return'])} | {format_pct(row['avg_mdd'])} | {sharpe} |")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `current` means return from the overlay snapshot date to the performance asof date.",
            "- Fixed horizons such as `1w` and `1m` are populated only after enough trading days have elapsed.",
            "- This tracker measures live shadow behavior after the overlay snapshot; it is not a backtest replacement.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_tracker(shadow_asof: str, performance_asof: str, report_dir: Path) -> dict[str, Any]:
    snapshot = load_overlay_snapshot(report_dir, shadow_asof)
    detail = build_detail(snapshot, performance_asof)
    summary = build_summary(detail)
    shadow_token = shadow_asof.replace("-", "")
    perf_token = performance_asof.replace("-", "")
    detail_csv = report_dir / f"valuation_overlay_live_shadow_detail_{shadow_token}_to_{perf_token}.csv"
    summary_csv = report_dir / f"valuation_overlay_live_shadow_summary_{shadow_token}_to_{perf_token}.csv"
    json_path = report_dir / f"valuation_overlay_live_shadow_tracker_{shadow_token}_to_{perf_token}.json"
    md_path = report_dir / f"valuation_overlay_live_shadow_tracker_{shadow_token}_to_{perf_token}.md"
    detail.to_csv(detail_csv, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    upsert_tables(detail, summary, shadow_asof, performance_asof)
    write_md(md_path, shadow_asof, performance_asof, detail, summary)
    payload = {
        "source_name": "valuation_ai_live_shadow_tracker",
        "schema_version": "1.0",
        "model_code": MODEL_CODE,
        "shadow_asof_date": shadow_asof,
        "performance_asof_date": performance_asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "detail_rows": int(len(detail)),
        "summary_rows": int(len(summary)),
        "outputs": {
            "detail_csv": str(detail_csv),
            "summary_csv": str(summary_csv),
            "json": str(json_path),
            "md": str(md_path),
            "db": str(OUT_DB),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    args = parse_args()
    report_dir = Path(args.report_dir)
    if str(args.shadow_asof).lower() == "all":
        shadow_asofs = available_shadow_asofs(report_dir, args.asof, args.lookback_days)
        results = [build_tracker(shadow_asof, args.asof, report_dir) for shadow_asof in shadow_asofs]
        print(
            json.dumps(
                {
                    "status": "ok",
                    "model_code": MODEL_CODE,
                    "performance_asof_date": args.asof,
                    "shadow_runs": len(results),
                    "shadow_asof_dates": shadow_asofs,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    result = build_tracker(args.shadow_asof, args.asof, report_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
