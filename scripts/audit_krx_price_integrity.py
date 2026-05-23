from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.krx_openapi import fetch_etf_daily, fetch_stock_daily, iter_bas_dd, load_api_key


DEFAULT_PRICE_DB = ROOT / "data" / "db" / "price.db"
DEFAULT_AUDIT_DB = ROOT / "data" / "db" / "data_quality.db"
DEFAULT_OUT_ROOT = ROOT / "reports" / "data_quality" / "krx_price_audit"


COMPARE_FIELDS = ("open", "high", "low", "close", "volume", "value")


@dataclass(frozen=True)
class AuditResult:
    run_id: str
    start: str
    end: str
    markets: str
    ticker_count: int | None
    date_count: int
    krx_rows: int
    db_rows: int
    compared_rows: int
    missing_in_db: int
    missing_in_krx: int
    mismatch_rows: int
    mismatch_cells: int
    status: str


def _parse_markets(value: str) -> list[str]:
    markets = [item.strip().upper() for item in str(value).split(",") if item.strip()]
    valid = {"KOSPI", "KOSDAQ", "ETF"}
    invalid = sorted(set(markets) - valid)
    if invalid:
        raise ValueError(f"unsupported markets: {invalid}; valid={sorted(valid)}")
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


def _date_to_db(value: str) -> str:
    text = str(value).strip().replace("-", "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _normalize_price_frame(frame: pd.DataFrame, tickers: set[str] | None) -> pd.DataFrame:
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


def _fetch_krx_frames(markets: list[str], bas_dd: str, api_key: str, tickers: set[str] | None, calendar_market: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    stock_markets = [market for market in markets if market != "ETF"]
    if not stock_markets and "ETF" in markets and calendar_market:
        calendar_frame = fetch_stock_daily(calendar_market, bas_dd, api_key)
        if calendar_frame.empty:
            print(f"[INFO] basDd={bas_dd} calendar_market={calendar_market} non_trading_day_skip=1")
            return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])

    for market in stock_markets:
        frame = fetch_stock_daily(market, bas_dd, api_key)
        norm = _normalize_price_frame(frame, tickers)
        if not norm.empty:
            frames.append(norm)
        print(f"[INFO] basDd={bas_dd} market={market} krx_rows={len(norm)}")

    if stock_markets and not frames:
        print(f"[INFO] basDd={bas_dd} stock_markets={','.join(stock_markets)} non_trading_day_skip=1")
        return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])

    if "ETF" in markets:
        frame = fetch_etf_daily(bas_dd, api_key)
        norm = _normalize_price_frame(frame, tickers)
        if not norm.empty:
            frames.append(norm)
        print(f"[INFO] basDd={bas_dd} market=ETF krx_rows={len(norm)}")
    if not frames:
        return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])
    return pd.concat(frames, ignore_index=True).drop_duplicates(["ticker", "date"])


def _read_db_prices(db_path: Path, start: str, end: str, tickers: set[str] | None) -> pd.DataFrame:
    start_db = _date_to_db(start)
    end_db = _date_to_db(end)
    params: list[object] = [start_db, end_db]
    ticker_clause = ""
    if tickers:
        placeholders = ",".join("?" for _ in tickers)
        ticker_clause = f" AND ticker IN ({placeholders})"
        params.extend(sorted(tickers))
    query = f"""
        SELECT ticker, date, open, high, low, close, volume, value, source
        FROM prices_daily
        WHERE date >= ? AND date <= ?{ticker_clause}
    """
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(query, con, params=params)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS, "source"])
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    for col in COMPARE_FIELDS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _cell_diff(db_value: float | int | None, krx_value: float | int | None, tolerance: float) -> tuple[bool, float | None, float | None]:
    db_na = pd.isna(db_value)
    krx_na = pd.isna(krx_value)
    if db_na and krx_na:
        return False, None, None
    if db_na != krx_na:
        return True, None, None
    diff = abs(float(db_value) - float(krx_value))
    rel = diff / abs(float(krx_value)) if float(krx_value) != 0 else (0.0 if diff == 0 else None)
    return diff > tolerance, diff, rel


def _compare(db_df: pd.DataFrame, krx_df: pd.DataFrame, price_tol: float, value_tol: float, volume_tol: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = db_df.merge(
        krx_df,
        on=["ticker", "date"],
        how="outer",
        suffixes=("_db", "_krx"),
        indicator=True,
    )
    summary_rows = []
    detail_rows = []
    for _, row in merged.iterrows():
        ticker = row["ticker"]
        date = row["date"]
        status = str(row["_merge"])
        row_mismatches = 0
        if status == "left_only":
            summary_rows.append({"ticker": ticker, "date": date, "status": "missing_in_krx", "mismatch_cells": 0, "source": row.get("source")})
            continue
        if status == "right_only":
            summary_rows.append({"ticker": ticker, "date": date, "status": "missing_in_db", "mismatch_cells": 0, "source": None})
            continue
        for field in COMPARE_FIELDS:
            tolerance = volume_tol if field == "volume" else value_tol if field == "value" else price_tol
            changed, abs_diff, rel_diff = _cell_diff(row.get(f"{field}_db"), row.get(f"{field}_krx"), tolerance)
            if changed:
                row_mismatches += 1
                detail_rows.append(
                    {
                        "ticker": ticker,
                        "date": date,
                        "field": field,
                        "db_value": row.get(f"{field}_db"),
                        "krx_value": row.get(f"{field}_krx"),
                        "abs_diff": abs_diff,
                        "rel_diff": rel_diff,
                        "source": row.get("source"),
                    }
                )
        summary_rows.append(
            {
                "ticker": ticker,
                "date": date,
                "status": "mismatch" if row_mismatches else "ok",
                "mismatch_cells": row_mismatches,
                "source": row.get("source"),
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(detail_rows)


def _init_audit_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS krx_price_audit_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT,
                finished_at TEXT,
                start_date TEXT,
                end_date TEXT,
                markets TEXT,
                ticker_count INTEGER,
                date_count INTEGER,
                krx_rows INTEGER,
                db_rows INTEGER,
                compared_rows INTEGER,
                missing_in_db INTEGER,
                missing_in_krx INTEGER,
                mismatch_rows INTEGER,
                mismatch_cells INTEGER,
                status TEXT,
                report_dir TEXT,
                notes TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS krx_price_audit_mismatch_samples (
                run_id TEXT,
                ticker TEXT,
                date TEXT,
                field TEXT,
                db_value REAL,
                krx_value REAL,
                abs_diff REAL,
                rel_diff REAL,
                source TEXT
            )
            """
        )


def _write_audit_db(audit_db: Path, result: AuditResult, report_dir: Path, started_at: str, finished_at: str, notes: str, detail_df: pd.DataFrame, sample_limit: int) -> None:
    _init_audit_db(audit_db)
    with sqlite3.connect(audit_db) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO krx_price_audit_runs (
                run_id, started_at, finished_at, start_date, end_date, markets, ticker_count, date_count,
                krx_rows, db_rows, compared_rows, missing_in_db, missing_in_krx,
                mismatch_rows, mismatch_cells, status, report_dir, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                started_at,
                finished_at,
                result.start,
                result.end,
                result.markets,
                result.ticker_count,
                result.date_count,
                result.krx_rows,
                result.db_rows,
                result.compared_rows,
                result.missing_in_db,
                result.missing_in_krx,
                result.mismatch_rows,
                result.mismatch_cells,
                result.status,
                str(report_dir),
                notes,
            ),
        )
        if not detail_df.empty:
            sample = detail_df.head(sample_limit).copy()
            sample.insert(0, "run_id", result.run_id)
            sample.to_sql("krx_price_audit_mismatch_samples", con, if_exists="append", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit existing price.db rows against KRX OpenAPI without overwriting price.db.")
    parser.add_argument("--start", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--markets", default="KOSPI,KOSDAQ", help="Comma list: KOSPI,KOSDAQ,ETF")
    parser.add_argument("--db", default=str(DEFAULT_PRICE_DB))
    parser.add_argument("--audit-db", default=str(DEFAULT_AUDIT_DB))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--api-key-file", default=str(ROOT / r"config\KRX_API_Key.json"))
    parser.add_argument("--tickers-file", default="", help="Optional CSV to restrict audit universe")
    parser.add_argument("--ticker-col", default="ticker")
    parser.add_argument("--price-tolerance", type=float, default=0.0001)
    parser.add_argument("--value-tolerance", type=float, default=1.0)
    parser.add_argument("--volume-tolerance", type=float, default=0.0)
    parser.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between dates to reduce API pressure")
    parser.add_argument("--calendar-market", default="KOSPI", choices=["KOSPI", "KOSDAQ", ""], help="Stock market calendar check for ETF-only audits")
    parser.add_argument("--sample-limit", type=int, default=5000)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    started_at = datetime.now().replace(microsecond=0).isoformat()
    run_id = f"krx_price_audit_{started_at.replace(':', '').replace('-', '').replace('T', '_')}"
    markets = _parse_markets(args.markets)
    tickers = _read_tickers(args.tickers_file, args.ticker_col)
    dates = iter_bas_dd(args.start, args.end)
    api_key = load_api_key(args.api_key_file)

    print(f"[INFO] run_id={run_id}")
    print(f"[INFO] range={args.start}~{args.end} dates={len(dates)} markets={markets}")
    print(f"[INFO] target_filter={'all' if tickers is None else len(tickers)}")

    krx_frames = []
    for i, bas_dd in enumerate(dates):
        krx_frames.append(_fetch_krx_frames(markets, bas_dd, api_key, tickers, args.calendar_market))
        if args.sleep > 0 and i < len(dates) - 1:
            time.sleep(args.sleep)
    krx_df = pd.concat(krx_frames, ignore_index=True) if krx_frames else pd.DataFrame(columns=["ticker", "date", *COMPARE_FIELDS])
    krx_df = krx_df.drop_duplicates(["ticker", "date"])
    db_df = _read_db_prices(Path(args.db), args.start, args.end, tickers)
    summary_df, detail_df = _compare(db_df, krx_df, args.price_tolerance, args.value_tolerance, args.volume_tolerance)

    missing_in_db = int((summary_df["status"] == "missing_in_db").sum()) if not summary_df.empty else 0
    missing_in_krx = int((summary_df["status"] == "missing_in_krx").sum()) if not summary_df.empty else 0
    mismatch_rows = int((summary_df["status"] == "mismatch").sum()) if not summary_df.empty else 0
    mismatch_cells = int(summary_df["mismatch_cells"].sum()) if not summary_df.empty else 0
    status = "pass" if missing_in_db == 0 and missing_in_krx == 0 and mismatch_rows == 0 else "warn"
    finished_at = datetime.now().replace(microsecond=0).isoformat()

    out_dir = Path(args.out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.csv"
    detail_path = out_dir / "mismatch_detail.csv"
    manifest_path = out_dir / "manifest.json"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    detail_df.to_csv(detail_path, index=False, encoding="utf-8-sig")

    result = AuditResult(
        run_id=run_id,
        start=_date_to_db(args.start),
        end=_date_to_db(args.end),
        markets=",".join(markets),
        ticker_count=None if tickers is None else len(tickers),
        date_count=len(dates),
        krx_rows=len(krx_df),
        db_rows=len(db_df),
        compared_rows=int((summary_df["status"] == "ok").sum() + mismatch_rows) if not summary_df.empty else 0,
        missing_in_db=missing_in_db,
        missing_in_krx=missing_in_krx,
        mismatch_rows=mismatch_rows,
        mismatch_cells=mismatch_cells,
        status=status,
    )
    manifest_path.write_text(
        pd.Series(
            {
                "run_id": result.run_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "start_date": result.start,
                "end_date": result.end,
                "markets": result.markets,
                "ticker_count": result.ticker_count,
                "date_count": result.date_count,
                "krx_rows": result.krx_rows,
                "db_rows": result.db_rows,
                "compared_rows": result.compared_rows,
                "missing_in_db": result.missing_in_db,
                "missing_in_krx": result.missing_in_krx,
                "mismatch_rows": result.mismatch_rows,
                "mismatch_cells": result.mismatch_cells,
                "status": result.status,
                "summary_path": str(summary_path),
                "detail_path": str(detail_path),
            }
        ).to_json(force_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_audit_db(Path(args.audit_db), result, out_dir, started_at, finished_at, args.notes, detail_df, args.sample_limit)

    print("[DONE] KRX price audit")
    print(f"[DONE] status={result.status} krx_rows={result.krx_rows} db_rows={result.db_rows} compared_rows={result.compared_rows}")
    print(f"[DONE] missing_in_db={result.missing_in_db} missing_in_krx={result.missing_in_krx} mismatch_rows={result.mismatch_rows} mismatch_cells={result.mismatch_cells}")
    print(f"[DONE] report_dir={out_dir}")


if __name__ == "__main__":
    main()
