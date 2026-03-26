# validate_etf_pipeline.py ver 2026-03-16_001
"""
Minimal validation for the ETF P0 pipeline.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def _latest_universe_csv(universe_dir: Path) -> Path:
    candidates = sorted(universe_dir.glob("universe_etf_master_*.csv"))
    if not candidates:
        raise FileNotFoundError("No ETF universe CSV found.")
    return candidates[-1]


def _load_universe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"ticker": "string"})
    required = {"ticker", "name", "asset_type", "asof", "is_active"}
    missing = required - set(df.columns)
    if missing:
        raise AssertionError(f"Universe columns missing: {sorted(missing)}")
    return df


def _validate_universe(df: pd.DataFrame) -> None:
    if df.empty:
        raise AssertionError("Universe is empty.")
    dupes = int(df.duplicated(subset=["ticker"]).sum())
    if dupes > 0:
        raise AssertionError(f"Universe has duplicate tickers: {dupes}")
    if (df["asset_type"].astype(str) != "ETF").any():
        raise AssertionError("Universe contains non-ETF asset_type values.")
    if df["ticker"].astype(str).str.fullmatch(r"\d{6}").fillna(False).sum() != len(df):
        raise AssertionError("Universe contains invalid ticker format.")


def _query_scalar(con: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def _validate_prices(con: sqlite3.Connection, tickers: list[str], start: str, end: str) -> dict[str, int]:
    placeholders = ",".join("?" for _ in tickers)
    params = tuple(tickers) + (start, end)
    loaded_rows = _query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date >= ?
          AND date <= ?;
        """,
        params,
    )
    duplicate_rows = _query_scalar(
        con,
        f"""
        SELECT COUNT(*) FROM (
            SELECT ticker, date, COUNT(*) AS cnt
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date >= ?
              AND date <= ?
            GROUP BY ticker, date
            HAVING COUNT(*) > 1
        );
        """,
        params,
    )
    null_close_rows = _query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date >= ?
          AND date <= ?
          AND close IS NULL;
        """,
        params,
    )
    distinct_tickers = _query_scalar(
        con,
        f"""
        SELECT COUNT(DISTINCT ticker)
        FROM prices_daily
        WHERE ticker IN ({placeholders})
          AND date >= ?
          AND date <= ?;
        """,
        params,
    )
    return {
        "loaded_rows": loaded_rows,
        "duplicate_rows": duplicate_rows,
        "null_close_rows": null_close_rows,
        "distinct_tickers": distinct_tickers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ETF P0 pipeline outputs.")
    parser.add_argument("--universe-csv", type=str, default="")
    parser.add_argument("--db", type=str, default="")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    here = Path(__file__).resolve()
    project_root = _find_project_root(here.parent)
    universe_csv = Path(args.universe_csv) if args.universe_csv else _latest_universe_csv(project_root / "data" / "universe")
    db_path = Path(args.db) if args.db else project_root / "data" / "db" / "price.db"

    df = _load_universe(universe_csv)
    _validate_universe(df)
    tickers = df["ticker"].astype(str).tolist()

    with sqlite3.connect(str(db_path)) as con:
        stats = _validate_prices(con, tickers, args.start, args.end)

    if stats["loaded_rows"] <= 0:
        raise AssertionError("No ETF price rows were loaded in the requested range.")
    if stats["duplicate_rows"] != 0:
        raise AssertionError(f"Duplicate ETF price rows found: {stats['duplicate_rows']}")
    if stats["distinct_tickers"] <= 0:
        raise AssertionError("No ETF tickers found in price.db for the requested range.")

    print(f"[OK] universe_csv={universe_csv}")
    print(f"[OK] db={db_path}")
    print(
        f"[OK] universe_rows={len(df)} loaded_rows={stats['loaded_rows']} "
        f"distinct_tickers={stats['distinct_tickers']} null_close_rows={stats['null_close_rows']}"
    )


if __name__ == "__main__":
    main()
