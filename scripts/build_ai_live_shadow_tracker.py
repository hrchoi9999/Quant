from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import pandas as pd

ROOT = Path(r"D:\Quant")
REPORT_DIR = ROOT / r"reports\ai_overlay_v01"
PRICE_DB = ROOT / r"data\db\price.db"
OUT_DB = ROOT / r"data\db\ai_learning.db"
MODEL_CODE = "AI-CANDIDATE-VALIDATION-V01"
MODEL_NAME_KO = "퀀트후보검증AI"
LEGACY_MODEL_CODE = "AI-OVERLAY-V01"
HORIZONS = {
    "1w": 5,
    "2w": 10,
    "1m": 21,
    "2m": 42,
    "3m": 63,
}
SHADOW_FILE_RE = re.compile(r"^ai_overlay_shadow_scores_(\d{8})\.csv$")


def _load_shadow(asof: str) -> pd.DataFrame:
    token = asof.replace("-", "")
    path = REPORT_DIR / f"ai_overlay_shadow_scores_{token}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, dtype={"ticker": str}, low_memory=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df["scored_at"] = pd.to_datetime(df["scored_at"], errors="coerce")
    df["shadow_asof_date"] = asof
    return df.dropna(subset=["ticker", "event_date", "scored_at"])


def _available_shadow_asofs(asof: str, lookback_days: int) -> list[str]:
    asof_ts = pd.Timestamp(asof)
    min_ts = asof_ts - pd.Timedelta(days=int(lookback_days))
    dates: list[str] = []
    for path in REPORT_DIR.glob("ai_overlay_shadow_scores_*.csv"):
        match = SHADOW_FILE_RE.match(path.name)
        if not match:
            continue
        ts = pd.Timestamp(datetime.strptime(match.group(1), "%Y%m%d").date())
        if min_ts <= ts <= asof_ts:
            dates.append(ts.strftime("%Y-%m-%d"))
    return sorted(set(dates))


def _load_prices(tickers: list[str], max_date: str) -> pd.DataFrame:
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
    return df.dropna(subset=["date", "close"])


def _forward_return(price_frame: pd.DataFrame, start_date: pd.Timestamp, asof_date: pd.Timestamp, trading_days: int) -> tuple[float | None, str | None, int]:
    hist = price_frame[price_frame["date"] >= start_date].sort_values("date").reset_index(drop=True)
    hist = hist[hist["date"] <= asof_date].reset_index(drop=True)
    if hist.empty:
        return None, None, 0
    start_close = float(hist.iloc[0]["close"])
    if start_close <= 0:
        return None, None, 0
    target_idx = min(trading_days, len(hist) - 1)
    if target_idx <= 0:
        return None, None, len(hist)
    end = hist.iloc[target_idx]
    return round(float(end["close"]) / start_close - 1.0, 6), pd.Timestamp(end["date"]).strftime("%Y-%m-%d"), len(hist)


def _build_live_rows(shadow: pd.DataFrame, asof: str) -> pd.DataFrame:
    asof_ts = pd.Timestamp(asof)
    prices = _load_prices(sorted(shadow["ticker"].dropna().unique().tolist()), asof)
    price_groups = {ticker: frame for ticker, frame in prices.groupby("ticker")} if not prices.empty else {}
    rows = []
    for row in shadow.to_dict(orient="records"):
        scored_ts = pd.Timestamp(row["scored_at"]).normalize()
        track_start = max(pd.Timestamp(row["event_date"]), scored_ts)
        price_frame = price_groups.get(str(row["ticker"]))
        item: dict[str, Any] = {
            "ai_model_code": MODEL_CODE,
            "ai_model_name_ko": MODEL_NAME_KO,
            "ai_model_legacy_code": LEGACY_MODEL_CODE,
            "shadow_asof_date": row.get("shadow_asof_date"),
            "performance_asof_date": asof,
            "scope_key": row.get("scope_key"),
            "model_id": row.get("model_id"),
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "event_date": pd.Timestamp(row["event_date"]).strftime("%Y-%m-%d"),
            "scored_at": pd.Timestamp(row["scored_at"]).isoformat(),
            "track_start_date": track_start.strftime("%Y-%m-%d"),
            "ai_shadow_tags": row.get("ai_shadow_tags"),
            "ai_shadow_decision": row.get("ai_shadow_decision"),
            "ai_short_confirm_prob": row.get("ai_short_confirm_prob"),
            "ai_medium_quality_prob": row.get("ai_medium_quality_prob"),
            "ai_long_quality_prob": row.get("ai_long_quality_prob"),
            "ai_upside_strict_prob": row.get("ai_upside_strict_prob"),
            "ai_risk_strict_prob": row.get("ai_risk_strict_prob"),
            "ai_model_specific_quality_prob": row.get("ai_model_specific_quality_prob"),
            "ai_model_specific_risk_prob": row.get("ai_model_specific_risk_prob"),
            "ai_model_specific_tag": row.get("ai_model_specific_tag"),
        }
        if price_frame is None or price_frame.empty:
            for horizon in HORIZONS:
                item[f"live_ret_{horizon}"] = None
                item[f"live_ret_{horizon}_end_date"] = None
                item[f"live_ret_{horizon}_available"] = 0
            rows.append(item)
            continue
        for horizon, trading_days in HORIZONS.items():
            ret, end_date, available_days = _forward_return(price_frame, track_start, asof_ts, trading_days)
            item[f"live_ret_{horizon}"] = ret
            item[f"live_ret_{horizon}_end_date"] = end_date
            item[f"live_ret_{horizon}_available"] = int(available_days > trading_days)
        rows.append(item)
    return pd.DataFrame(rows)


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_column(con: sqlite3.Connection, table_name: str, column_name: str, column_type: str = "TEXT") -> None:
    if not _table_exists(con, table_name):
        return
    columns = {
        row[1]
        for row in con.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _sqlite_type_for_series(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    return "TEXT"


def _ensure_dataframe_columns(con: sqlite3.Connection, table_name: str, frame: pd.DataFrame) -> None:
    if not _table_exists(con, table_name):
        return
    for column in frame.columns:
        _ensure_column(con, table_name, str(column), _sqlite_type_for_series(frame[column]))


def _upsert_run_tables(live: pd.DataFrame, summary: pd.DataFrame, shadow_asof: str, asof: str) -> None:
    with sqlite3.connect(str(OUT_DB)) as con:
        _ensure_column(con, "ai_live_shadow_tracker_detail", "performance_asof_date")
        _ensure_column(con, "ai_live_shadow_tracker_summary", "shadow_asof_date")
        _ensure_dataframe_columns(con, "ai_live_shadow_tracker_detail", live)
        _ensure_dataframe_columns(con, "ai_live_shadow_tracker_summary", summary)
        if _table_exists(con, "ai_live_shadow_tracker_detail"):
            con.execute(
                """
                DELETE FROM ai_live_shadow_tracker_detail
                WHERE performance_asof_date IS NULL
                  AND shadow_asof_date = ?
                """,
                (shadow_asof,),
            )
            con.execute(
                """
                DELETE FROM ai_live_shadow_tracker_detail
                WHERE shadow_asof_date = ?
                  AND performance_asof_date = ?
                """,
                (shadow_asof, asof),
            )
        if _table_exists(con, "ai_live_shadow_tracker_summary"):
            con.execute(
                """
                DELETE FROM ai_live_shadow_tracker_summary
                WHERE shadow_asof_date IS NULL
                  AND asof_date = ?
                """,
                (asof,),
            )
            con.execute(
                """
                DELETE FROM ai_live_shadow_tracker_summary
                WHERE shadow_asof_date = ?
                  AND asof_date = ?
                """,
                (shadow_asof, asof),
            )
        live.to_sql("ai_live_shadow_tracker_detail", con, if_exists="append", index=False)
        summary.to_sql("ai_live_shadow_tracker_summary", con, if_exists="append", index=False)


def _summary_rows(live: pd.DataFrame, asof: str) -> pd.DataFrame:
    rows = []
    for group_type, group_col in [("decision", "ai_shadow_decision")]:
        for group_value, frame in live.groupby(group_col):
            for horizon in HORIZONS:
                col = f"live_ret_{horizon}"
                vals = pd.to_numeric(frame[col], errors="coerce").dropna()
                rows.append(
                    {
                        "ai_model_code": MODEL_CODE,
                        "ai_model_name_ko": MODEL_NAME_KO,
                        "ai_model_legacy_code": LEGACY_MODEL_CODE,
                        "shadow_asof_date": frame["shadow_asof_date"].iloc[0] if "shadow_asof_date" in frame else None,
                        "asof_date": asof,
                        "group_type": group_type,
                        "group_value": group_value,
                        "horizon": horizon,
                        "sample_count": int(len(vals)),
                        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
                        "median_return": None if vals.empty else round(float(vals.median()), 6),
                        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
    exploded = []
    for row in live.to_dict(orient="records"):
        for tag in str(row.get("ai_shadow_tags") or "OBSERVE").split(","):
            tag = tag.strip()
            if not tag:
                continue
            item = dict(row)
            item["ai_shadow_tag_single"] = tag
            exploded.append(item)
    tag_df = pd.DataFrame(exploded)
    if not tag_df.empty:
        for tag, frame in tag_df.groupby("ai_shadow_tag_single"):
            for horizon in HORIZONS:
                col = f"live_ret_{horizon}"
                vals = pd.to_numeric(frame[col], errors="coerce").dropna()
                rows.append(
                    {
                        "ai_model_code": MODEL_CODE,
                        "ai_model_name_ko": MODEL_NAME_KO,
                        "ai_model_legacy_code": LEGACY_MODEL_CODE,
                        "shadow_asof_date": frame["shadow_asof_date"].iloc[0] if "shadow_asof_date" in frame else None,
                        "asof_date": asof,
                        "group_type": "tag",
                        "group_value": tag,
                        "horizon": horizon,
                        "sample_count": int(len(vals)),
                        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
                        "median_return": None if vals.empty else round(float(vals.median()), 6),
                        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
    if "ai_model_specific_tag" in live.columns:
        for tag, frame in live.groupby("ai_model_specific_tag"):
            for horizon in HORIZONS:
                col = f"live_ret_{horizon}"
                vals = pd.to_numeric(frame[col], errors="coerce").dropna()
                rows.append(
                    {
                        "ai_model_code": MODEL_CODE,
                        "ai_model_name_ko": MODEL_NAME_KO,
                        "ai_model_legacy_code": LEGACY_MODEL_CODE,
                        "shadow_asof_date": frame["shadow_asof_date"].iloc[0] if "shadow_asof_date" in frame else None,
                        "asof_date": asof,
                        "group_type": "model_specific_tag",
                        "group_value": tag,
                        "horizon": horizon,
                        "sample_count": int(len(vals)),
                        "avg_return": None if vals.empty else round(float(vals.mean()), 6),
                        "median_return": None if vals.empty else round(float(vals.median()), 6),
                        "win_rate": None if vals.empty else round(float((vals > 0).mean()), 6),
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
    return pd.DataFrame(rows)


def build_live_tracker(shadow_asof: str, asof: str) -> dict[str, Any]:
    shadow = _load_shadow(shadow_asof)
    live = _build_live_rows(shadow, asof)
    summary = _summary_rows(live, asof)
    token = asof.replace("-", "")
    shadow_token = shadow_asof.replace("-", "")
    detail_csv = REPORT_DIR / f"ai_live_shadow_tracker_detail_{shadow_token}_to_{token}.csv"
    summary_csv = REPORT_DIR / f"ai_live_shadow_tracker_summary_{shadow_token}_to_{token}.csv"
    md_path = REPORT_DIR / f"ai_live_shadow_tracker_{shadow_token}_to_{token}.md"
    json_path = REPORT_DIR / f"ai_live_shadow_tracker_{shadow_token}_to_{token}.json"
    live.to_csv(detail_csv, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    _upsert_run_tables(live, summary, shadow_asof, asof)

    lines = [
        f"# AI Live Shadow Tracker - {shadow_asof} to {asof}",
        "",
        f"- model_code: `{MODEL_CODE}`",
        f"- model_name_ko: `{MODEL_NAME_KO}`",
        f"- legacy_model_code: `{LEGACY_MODEL_CODE}`",
        f"- shadow_asof_date: `{shadow_asof}`",
        f"- performance_asof_date: `{asof}`",
        f"- detail_rows: `{len(live)}`",
        f"- summary_rows: `{len(summary)}`",
        "",
        "## Summary",
        "",
        "| group_type | group_value | horizon | samples | avg return | win rate |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for _, row in summary.sort_values(["group_type", "group_value", "horizon"]).iterrows():
        avg = "N/A" if pd.isna(row["avg_return"]) else f"{float(row['avg_return']):.2%}"
        win = "N/A" if pd.isna(row["win_rate"]) else f"{float(row['win_rate']):.2%}"
        lines.append(f"| {row['group_type']} | {row['group_value']} | {row['horizon']} | {int(row['sample_count'])} | {avg} | {win} |")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    payload = {
        "model_code": MODEL_CODE,
        "model_name_ko": MODEL_NAME_KO,
        "legacy_model_code": LEGACY_MODEL_CODE,
        "shadow_asof_date": shadow_asof,
        "performance_asof_date": asof,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "detail_rows": int(len(live)),
        "summary_rows": int(len(summary)),
        "outputs": {
            "detail_csv": str(detail_csv),
            "summary_csv": str(summary_csv),
            "md": str(md_path),
            "json": str(json_path),
            "db": str(OUT_DB),
        },
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build live-only AI shadow tracker.")
    parser.add_argument("--shadow-asof", required=True, help="Date of shadow score file, YYYY-MM-DD, or 'all'")
    parser.add_argument("--asof", required=True, help="Performance as-of date, YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=120, help="When --shadow-asof all, refresh shadow files within this many calendar days")
    args = parser.parse_args()
    if str(args.shadow_asof).lower() == "all":
        shadow_asofs = _available_shadow_asofs(args.asof, int(args.lookback_days))
        results = [build_live_tracker(shadow_asof, args.asof) for shadow_asof in shadow_asofs]
        print(
            json.dumps(
                {
                    "status": "ok",
                    "model_code": MODEL_CODE,
                    "model_name_ko": MODEL_NAME_KO,
                    "legacy_model_code": LEGACY_MODEL_CODE,
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
    result = build_live_tracker(args.shadow_asof, args.asof)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
