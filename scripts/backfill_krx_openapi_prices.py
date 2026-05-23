from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.krx_openapi import fetch_etf_daily, fetch_stock_daily, iter_bas_dd
from src.collectors.krx_openapi import load_api_key
from src.collectors.price.price_store import PriceStore


DEFAULT_PRICE_DB = ROOT / "data" / "db" / "price.db"
DEFAULT_AUDIT_DB = ROOT / "data" / "db" / "data_quality.db"
DEFAULT_OUT_ROOT = ROOT / "reports" / "data_quality" / "krx_price_backfill"
COMPARE_FIELDS = ("open", "high", "low", "close", "volume", "value")


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _date_to_db(value: str) -> str:
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value}")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _parse_markets(value: str) -> list[str]:
    markets = [item.strip().upper() for item in str(value).split(",") if item.strip()]
    valid = {"KOSPI", "KOSDAQ", "ETF"}
    invalid = sorted(set(markets) - valid)
    if invalid:
        raise ValueError(f"unsupported markets: {invalid}; valid={sorted(valid)}")
    if not markets:
        raise ValueError("markets is empty")
    return markets


def _read_tickers(path: str, ticker_col: str) -> set[str] | None:
    if not path:
        return None
    df = pd.read_csv(Path(path), dtype={ticker_col: "string"})
    if ticker_col not in df.columns:
        raise ValueError(f"missing ticker column {ticker_col}: {path}")
    return {
        str(value).strip().replace(".0", "").zfill(6)
        for value in df[ticker_col].dropna().tolist()
        if str(value).strip()
    }


def _normalize_krx_frame(frame: pd.DataFrame, tickers: set[str] | None) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])
    out = frame.copy()
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    if tickers is not None:
        out = out.loc[out["ticker"].isin(tickers)].copy()
    for col in COMPARE_FIELDS:
        if col not in out.columns:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out[["ticker", "date", *COMPARE_FIELDS]].drop_duplicates(["ticker", "date"])


def _fetch_krx_daily(markets: list[str], bas_dd: str, api_key: str, tickers: set[str] | None, calendar_market: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    stock_markets = [market for market in markets if market != "ETF"]
    if not stock_markets and "ETF" in markets and calendar_market:
        calendar_frame = fetch_stock_daily(calendar_market, bas_dd, api_key)
        if calendar_frame.empty:
            print(f"[INFO] basDd={bas_dd} calendar_market={calendar_market} non_trading_day_skip=1")
            return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])

    for market in stock_markets:
        frame = fetch_stock_daily(market, bas_dd, api_key)
        norm = _normalize_krx_frame(frame, tickers)
        if not norm.empty:
            frames.append(norm)
        print(f"[INFO] basDd={bas_dd} market={market} krx_rows={len(norm)}")

    if stock_markets and not frames:
        print(f"[INFO] basDd={bas_dd} stock_markets={','.join(stock_markets)} non_trading_day_skip=1")
        return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])

    if "ETF" in markets:
        frame = fetch_etf_daily(bas_dd, api_key)
        norm = _normalize_krx_frame(frame, tickers)
        if not norm.empty:
            frames.append(norm)
        print(f"[INFO] basDd={bas_dd} market=ETF krx_rows={len(norm)}")
    if not frames:
        return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])
    return pd.concat(frames, ignore_index=True).drop_duplicates(["ticker", "date"])


def _read_existing(db_path: Path, start: str, end: str, tickers: set[str] | None) -> pd.DataFrame:
    start_db = _date_to_db(start)
    end_db = _date_to_db(end)
    base_cols = ["ticker", "date", *COMPARE_FIELDS, "source"]
    frames: list[pd.DataFrame] = []
    ticker_list = sorted(tickers) if tickers else [None]
    chunk_size = 850
    with sqlite3.connect(db_path) as con:
        if tickers is None:
            df = pd.read_sql_query(
                """
                SELECT ticker, date, open, high, low, close, volume, value, source
                FROM prices_daily
                WHERE date >= ? AND date <= ?
                """,
                con,
                params=[start_db, end_db],
            )
            frames.append(df)
        else:
            for i in range(0, len(ticker_list), chunk_size):
                chunk = ticker_list[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                df = pd.read_sql_query(
                    f"""
                    SELECT ticker, date, open, high, low, close, volume, value, source
                    FROM prices_daily
                    WHERE date >= ? AND date <= ? AND ticker IN ({placeholders})
                    """,
                    con,
                    params=[start_db, end_db, *chunk],
                )
                frames.append(df)
    if not frames:
        return pd.DataFrame(columns=base_cols)
    out = pd.concat(frames, ignore_index=True)
    if out.empty:
        return pd.DataFrame(columns=base_cols)
    out["ticker"] = out["ticker"].astype(str).str.zfill(6)
    for col in COMPARE_FIELDS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out[base_cols]


def _same_value(left: Any, right: Any, tolerance: float) -> bool:
    left_na = pd.isna(left)
    right_na = pd.isna(right)
    if left_na and right_na:
        return True
    if left_na != right_na:
        return False
    return abs(float(left) - float(right)) <= tolerance


def _diff(left: Any, right: Any) -> tuple[float | None, float | None]:
    if pd.isna(left) or pd.isna(right):
        return None, None
    abs_diff = abs(float(left) - float(right))
    rel_diff = abs_diff / abs(float(right)) if float(right) != 0 else (0.0 if abs_diff == 0 else None)
    return abs_diff, rel_diff


def _classify_changes(
    existing_df: pd.DataFrame,
    krx_df: pd.DataFrame,
    price_tol: float,
    value_tol: float,
    volume_tol: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    existing = existing_df.rename(columns={field: f"{field}_old" for field in COMPARE_FIELDS})
    krx = krx_df.rename(columns={field: f"{field}_new" for field in COMPARE_FIELDS})
    merged = krx.merge(existing, on=["ticker", "date"], how="left")

    row_actions = []
    diffs = []
    for _, row in merged.iterrows():
        ticker = row["ticker"]
        date = row["date"]
        old_source = row.get("source")
        has_existing = not pd.isna(old_source)
        mismatch_fields = 0
        if not has_existing:
            row_actions.append({"ticker": ticker, "date": date, "action": "insert", "old_source": None, "mismatch_cells": 0})
            continue
        for field in COMPARE_FIELDS:
            tol = volume_tol if field == "volume" else value_tol if field == "value" else price_tol
            old_value = row.get(f"{field}_old")
            new_value = row.get(f"{field}_new")
            if not _same_value(old_value, new_value, tol):
                mismatch_fields += 1
                abs_diff, rel_diff = _diff(old_value, new_value)
                diffs.append(
                    {
                        "ticker": ticker,
                        "date": date,
                        "field": field,
                        "old_value": old_value,
                        "new_value": new_value,
                        "abs_diff": abs_diff,
                        "rel_diff": rel_diff,
                        "old_source": old_source,
                    }
                )
        if mismatch_fields:
            action = "update_value_changed"
        elif old_source != "krx_openapi":
            action = "update_source_only"
        else:
            action = "unchanged"
        row_actions.append({"ticker": ticker, "date": date, "action": action, "old_source": old_source, "mismatch_cells": mismatch_fields})
    return pd.DataFrame(row_actions), pd.DataFrame(diffs)


def _init_audit_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS krx_price_backfill_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                finished_at TEXT,
                start_date TEXT,
                end_date TEXT,
                markets TEXT,
                ticker_count INTEGER,
                date_count INTEGER,
                dry_run INTEGER,
                krx_rows INTEGER,
                db_existing_rows INTEGER,
                insert_rows INTEGER,
                update_value_changed_rows INTEGER,
                update_source_only_rows INTEGER,
                unchanged_rows INTEGER,
                mismatch_cells INTEGER,
                upsert_rows INTEGER,
                status TEXT,
                report_dir TEXT,
                notes TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS krx_price_backfill_diff_samples (
                run_id TEXT,
                ticker TEXT,
                date TEXT,
                field TEXT,
                old_value REAL,
                new_value REAL,
                abs_diff REAL,
                rel_diff REAL,
                old_source TEXT
            )
            """
        )


def _write_run_log(
    audit_db: Path,
    result: dict[str, Any],
    diff_df: pd.DataFrame,
    sample_limit: int,
) -> None:
    _init_audit_db(audit_db)
    with sqlite3.connect(audit_db) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO krx_price_backfill_runs (
                run_id, started_at, finished_at, start_date, end_date, markets, ticker_count, date_count,
                dry_run, krx_rows, db_existing_rows, insert_rows, update_value_changed_rows,
                update_source_only_rows, unchanged_rows, mismatch_cells, upsert_rows, status, report_dir, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["run_id"],
                result["started_at"],
                result["finished_at"],
                result["start_date"],
                result["end_date"],
                result["markets"],
                result["ticker_count"],
                result["date_count"],
                1 if result["dry_run"] else 0,
                result["krx_rows"],
                result["db_existing_rows"],
                result["insert_rows"],
                result["update_value_changed_rows"],
                result["update_source_only_rows"],
                result["unchanged_rows"],
                result["mismatch_cells"],
                result["upsert_rows"],
                result["status"],
                result["report_dir"],
                result["notes"],
            ),
        )
        if not diff_df.empty and sample_limit > 0:
            sample = diff_df.head(sample_limit).copy()
            sample.insert(0, "run_id", result["run_id"])
            sample.to_sql("krx_price_backfill_diff_samples", con, if_exists="append", index=False)


def _upsert_krx_rows(db_path: Path, krx_df: pd.DataFrame) -> int:
    if krx_df.empty:
        return 0
    PriceStore(db_path=db_path).init_schema()
    now = _utcnow_iso()
    rows = [
        (
            str(row.ticker).zfill(6),
            str(row.date),
            None if pd.isna(row.open) else float(row.open),
            None if pd.isna(row.high) else float(row.high),
            None if pd.isna(row.low) else float(row.low),
            None if pd.isna(row.close) else float(row.close),
            None if pd.isna(row.volume) else int(row.volume),
            None if pd.isna(row.value) else float(row.value),
            "krx_openapi",
            now,
            now,
        )
        for row in krx_df.itertuples(index=False)
    ]
    sql = """
        INSERT INTO prices_daily
            (ticker, date, open, high, low, close, volume, value, source, created_at, updated_at)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            volume=excluded.volume,
            value=excluded.value,
            source=excluded.source,
            updated_at=excluded.updated_at;
    """
    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA journal_mode=WAL;")
        con.executemany(sql, rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill price.db with KRX OpenAPI rows while logging old/new differences.")
    parser.add_argument("--start", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--markets", default="KOSPI,KOSDAQ", help="Comma list: KOSPI,KOSDAQ,ETF")
    parser.add_argument("--tickers-file", required=True, help="Universe CSV. Backfill is restricted to these tickers.")
    parser.add_argument("--ticker-col", default="ticker")
    parser.add_argument("--db", default=str(DEFAULT_PRICE_DB))
    parser.add_argument("--audit-db", default=str(DEFAULT_AUDIT_DB))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--api-key-file", default=str(ROOT / r"config\KRX_API_Key.json"))
    parser.add_argument("--price-tolerance", type=float, default=0.0001)
    parser.add_argument("--value-tolerance", type=float, default=1.0)
    parser.add_argument("--volume-tolerance", type=float, default=0.0)
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--calendar-market", default="KOSPI", choices=["KOSPI", "KOSDAQ", ""], help="Stock market calendar check for ETF-only backfills")
    parser.add_argument("--dry-run", action="store_true", help="Compare and log only; do not update price.db.")
    parser.add_argument("--sample-limit", type=int, default=10000)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    started_at = datetime.now().replace(microsecond=0).isoformat()
    run_id = f"krx_price_backfill_{started_at.replace(':', '').replace('-', '').replace('T', '_')}"
    markets = _parse_markets(args.markets)
    tickers = _read_tickers(args.tickers_file, args.ticker_col)
    if not tickers:
        raise RuntimeError("--tickers-file produced no tickers; refusing unrestricted backfill")
    dates = iter_bas_dd(args.start, args.end)
    api_key = load_api_key(args.api_key_file)

    print(f"[INFO] run_id={run_id}")
    print(f"[INFO] range={args.start}~{args.end} dates={len(dates)} markets={markets}")
    print(f"[INFO] target_filter={len(tickers)} dry_run={args.dry_run}")

    daily_frames: list[pd.DataFrame] = []
    for i, bas_dd in enumerate(dates):
        daily = _fetch_krx_daily(markets, bas_dd, api_key, tickers, args.calendar_market)
        if not daily.empty:
            daily_frames.append(daily)
        if args.sleep > 0 and i < len(dates) - 1:
            time.sleep(args.sleep)
    krx_df = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])
    krx_df = krx_df.drop_duplicates(["ticker", "date"]).sort_values(["date", "ticker"]).reset_index(drop=True)
    existing_df = _read_existing(Path(args.db), args.start, args.end, tickers)
    row_actions_df, diff_df = _classify_changes(existing_df, krx_df, args.price_tolerance, args.value_tolerance, args.volume_tolerance)

    action_counts = row_actions_df["action"].value_counts().to_dict() if not row_actions_df.empty else {}
    upsert_rows = 0 if args.dry_run else _upsert_krx_rows(Path(args.db), krx_df)

    finished_at = datetime.now().replace(microsecond=0).isoformat()
    out_dir = Path(args.out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    row_actions_path = out_dir / "row_actions.csv"
    diff_path = out_dir / "diff_detail.csv"
    manifest_path = out_dir / "manifest.json"
    row_actions_df.to_csv(row_actions_path, index=False, encoding="utf-8-sig")
    diff_df.to_csv(diff_path, index=False, encoding="utf-8-sig")

    result = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "start_date": _date_to_db(args.start),
        "end_date": _date_to_db(args.end),
        "markets": ",".join(markets),
        "ticker_count": len(tickers),
        "date_count": len(dates),
        "dry_run": args.dry_run,
        "krx_rows": len(krx_df),
        "db_existing_rows": len(existing_df),
        "insert_rows": int(action_counts.get("insert", 0)),
        "update_value_changed_rows": int(action_counts.get("update_value_changed", 0)),
        "update_source_only_rows": int(action_counts.get("update_source_only", 0)),
        "unchanged_rows": int(action_counts.get("unchanged", 0)),
        "mismatch_cells": len(diff_df),
        "upsert_rows": upsert_rows,
        "status": "dry_run" if args.dry_run else "completed",
        "report_dir": str(out_dir),
        "row_actions_path": str(row_actions_path),
        "diff_path": str(diff_path),
        "notes": args.notes,
    }
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_run_log(Path(args.audit_db), result, diff_df, args.sample_limit)

    print("[DONE] KRX price backfill")
    print(
        "[DONE] "
        f"status={result['status']} krx_rows={result['krx_rows']} existing_rows={result['db_existing_rows']} "
        f"insert={result['insert_rows']} value_changed={result['update_value_changed_rows']} "
        f"source_only={result['update_source_only_rows']} unchanged={result['unchanged_rows']} "
        f"mismatch_cells={result['mismatch_cells']} upsert_rows={result['upsert_rows']}"
    )
    print(f"[DONE] report_dir={out_dir}")


if __name__ == "__main__":
    main()
