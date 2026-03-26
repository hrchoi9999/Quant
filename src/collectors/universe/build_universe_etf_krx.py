# build_universe_etf_krx.py ver 2026-03-16_003
"""
Build a KRX ETF master universe using PyKRX.

Primary path:
- pykrx.stock.get_etf_ticker_list(asof)
- pykrx.stock.get_etf_ticker_name(ticker)

Fallback path:
- pykrx.website.krx.etx.core.상장종목검색().fetch(market='ETF')
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def _normalize_asof(value: str) -> str:
    s = str(value).strip().replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"invalid asof: {value}")
    return s


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _resolve_trading_day(asof: str, max_back_days: int) -> str:
    from pykrx import stock

    ref = datetime.strptime(asof, "%Y%m%d").date()
    last_error = None
    for lag in range(max_back_days + 1):
        probe = (ref - timedelta(days=lag)).strftime("%Y%m%d")
        try:
            tickers = stock.get_etf_ticker_list(probe)
        except Exception as exc:
            last_error = exc
            continue
        if tickers:
            return probe

    if last_error is not None:
        print(f"[WARN] get_etf_ticker_list fallback triggered: {last_error}")
    return asof


def _build_universe_rows_pykrx(asof: str) -> pd.DataFrame:
    from pykrx import stock

    tickers = stock.get_etf_ticker_list(asof)
    rows = []
    for ticker in tickers:
        ticker = str(ticker).strip().zfill(6)
        if not ticker.isdigit():
            continue
        try:
            name = stock.get_etf_ticker_name(ticker)
        except Exception:
            name = ""
        rows.append(
            {
                "ticker": ticker,
                "name": str(name).strip(),
                "asset_type": "ETF",
                "asof": asof,
                "is_active": 1,
            }
        )

    return pd.DataFrame(rows, columns=["ticker", "name", "asset_type", "asof", "is_active"])


def _build_universe_rows_fallback(asof: str) -> pd.DataFrame:
    import pykrx.website.krx.etx.core as etx_core

    finder_cls = getattr(etx_core, "\uC0C1\uC7A5\uC885\uBAA9\uAC80\uC0C9")
    df = finder_cls().fetch(market="ETF").copy()
    if df.empty:
        return pd.DataFrame(columns=["ticker", "name", "asset_type", "asof", "is_active"])

    df = df.rename(columns={"short_code": "ticker", "codeName": "name"})
    df["ticker"] = df["ticker"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(6)
    df["name"] = df["name"].astype(str).str.strip()
    df = df[df["ticker"].str.fullmatch(r"\d{6}", na=False)].copy()
    df["asset_type"] = "ETF"
    df["asof"] = asof
    df["is_active"] = 1
    return df[["ticker", "name", "asset_type", "asof", "is_active"]]


def _build_universe_rows(asof: str) -> Tuple[pd.DataFrame, str]:
    try:
        df = _build_universe_rows_pykrx(asof)
        if not df.empty:
            return df, "pykrx_stock"
    except Exception as exc:
        print(f"[WARN] pykrx ETF universe primary failed: {exc}")

    df = _build_universe_rows_fallback(asof)
    if df.empty:
        raise RuntimeError(f"ETF universe is empty for asof={asof}")
    return df, "pykrx_finder_fallback"


def _ensure_instrument_master(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS instrument_master (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            asset_type TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            list_date TEXT,
            delist_date TEXT,
            updated_at TEXT
        );
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_instrument_master_asset_type "
        "ON instrument_master(asset_type, is_active);"
    )


def _upsert_instrument_master(db_path: Path, rows: Iterable[tuple[str, str, str, int, str]]) -> int:
    payload = list(rows)
    if not payload:
        return 0

    with sqlite3.connect(str(db_path)) as con:
        _ensure_instrument_master(con)
        con.executemany(
            """
            INSERT INTO instrument_master
                (ticker, name, asset_type, is_active, updated_at)
            VALUES
                (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name=excluded.name,
                asset_type=excluded.asset_type,
                is_active=excluded.is_active,
                updated_at=excluded.updated_at;
            """,
            payload,
        )
    return len(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build KRX ETF universe master CSV.")
    parser.add_argument("--asof", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--max-back-days", type=int, default=10, help="Trading day fallback window")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output CSV path. Defaults to data/universe/universe_etf_master_{asof}.csv",
    )
    parser.add_argument("--update-latest", action="store_true", help="Also update universe_etf_master_latest.csv")
    parser.add_argument(
        "--upsert-instrument-master",
        action="store_true",
        help="Upsert ETF metadata into price.db.instrument_master",
    )
    parser.add_argument(
        "--price-db",
        type=str,
        default="",
        help="Optional price.db path. Defaults to data/db/price.db",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve()
    project_root = _find_project_root(here.parent)
    asof_req = _normalize_asof(args.asof)
    asof = _resolve_trading_day(asof_req, args.max_back_days)

    df, source = _build_universe_rows(asof)
    df = df.drop_duplicates(subset=["ticker"]).sort_values(["ticker"]).reset_index(drop=True)

    out_path = (
        Path(args.output)
        if args.output
        else project_root / "data" / "universe" / f"universe_etf_master_{asof}.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"[INFO] asof_requested={asof_req}, asof_used={asof}")
    print(f"[INFO] source={source}")
    print(f"[INFO] output={out_path}")
    print(f"[INFO] rows={len(df)}")

    if args.update_latest:
        latest_path = out_path.parent / "universe_etf_master_latest.csv"
        shutil.copyfile(out_path, latest_path)
        print(f"[INFO] latest_updated={latest_path}")

    if args.upsert_instrument_master:
        price_db = (
            Path(args.price_db)
            if args.price_db
            else project_root / "data" / "db" / "price.db"
        )
        now = _utcnow_iso()
        count = _upsert_instrument_master(
            price_db,
            (
                (str(r.ticker), str(r.name), "ETF", int(r.is_active), now)
                for r in df.itertuples(index=False)
            ),
        )
        print(f"[INFO] instrument_master_upserted={count}, db={price_db}")


if __name__ == "__main__":
    main()
