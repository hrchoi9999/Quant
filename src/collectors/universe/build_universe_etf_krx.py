# build_universe_etf_krx.py ver 2026-04-18_001
"""
Build a KRX ETF master universe using KRX OpenAPI.

Source:
- KRX OpenAPI ETF daily trading endpoint (/etp/etf_bydd_trd)
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from src.collectors.krx_openapi import fetch_etf_daily, load_api_key, normalize_bas_dd
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / "src").exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.collectors.krx_openapi import fetch_etf_daily, load_api_key, normalize_bas_dd


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def _normalize_asof(value: str) -> str:
    return normalize_bas_dd(value)


def _utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _build_universe_rows_from_krx_openapi(asof: str, api_key: str) -> tuple[pd.DataFrame, str]:
    frame = fetch_etf_daily(asof, api_key)
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "name", "asset_type", "asof", "is_active"]), "krx_openapi_empty"

    out = frame[["ticker", "name"]].copy()
    out["ticker"] = out["ticker"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(6)
    out["name"] = out["name"].astype(str).str.strip()
    out = out[out["ticker"].str.fullmatch(r"\d{6}", na=False)].copy()
    out = out.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    out["asset_type"] = "ETF"
    out["asof"] = asof
    out["is_active"] = 1
    return out[["ticker", "name", "asset_type", "asof", "is_active"]], "krx_openapi_etf_daily"


def _resolve_trading_day_and_rows(asof: str, max_back_days: int, api_key: str) -> tuple[str, pd.DataFrame, str]:
    ref = datetime.strptime(asof, "%Y%m%d").date()
    last_error: Exception | None = None
    for lag in range(max_back_days + 1):
        probe = (ref - timedelta(days=lag)).strftime("%Y%m%d")
        try:
            df, source = _build_universe_rows_from_krx_openapi(probe, api_key)
        except Exception as exc:
            last_error = exc
            continue
        if not df.empty:
            return probe, df, source

    if last_error is not None:
        raise RuntimeError(f"KRX OpenAPI ETF universe failed through {max_back_days} back days: {last_error}") from last_error
    raise RuntimeError(f"KRX OpenAPI ETF universe is empty for asof={asof}")


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
    parser = argparse.ArgumentParser(description="Build KRX OpenAPI ETF universe master CSV.")
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
    parser.add_argument("--api-key-file", default=str(Path(r"D:\Quant\config\KRX_API_Key.json")))
    args = parser.parse_args()

    here = Path(__file__).resolve()
    project_root = _find_project_root(here.parent)
    asof_req = _normalize_asof(args.asof)
    api_key = load_api_key(args.api_key_file)
    asof, df, source = _resolve_trading_day_and_rows(asof_req, args.max_back_days, api_key)

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
