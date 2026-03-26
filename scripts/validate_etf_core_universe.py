# validate_etf_core_universe.py ver 2026-03-17_001
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(r"D:\Quant")


def _required_cols() -> set[str]:
    return {
        "ticker",
        "name",
        "asset_type",
        "asset_class",
        "group_key",
        "currency_exposure",
        "is_inverse",
        "is_leveraged",
        "liquidity_20d_value",
        "min_liquidity_pass",
        "asof",
    }


def _load_rules(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _validate_recent_history(db_path: Path, tickers: list[str], asof: str, min_history_days: int) -> None:
    placeholders = ",".join("?" for _ in tickers)
    with sqlite3.connect(str(db_path)) as con:
        sql = f"""
        WITH ranked AS (
            SELECT ticker, date, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM prices_daily
            WHERE ticker IN ({placeholders})
              AND date <= ?
        )
        SELECT ticker, COUNT(*) AS history_days
        FROM ranked
        WHERE rn <= ?
        GROUP BY ticker
        """
        params = tuple(tickers) + (asof, min_history_days)
        hist = pd.read_sql_query(sql, con, params=params)
    hist["ticker"] = hist["ticker"].astype(str).str.zfill(6)
    bad = hist[hist["history_days"] < min_history_days]
    missing = sorted(set(tickers) - set(hist["ticker"].tolist()))
    if missing:
        raise AssertionError(f"Missing price history for tickers: {missing}")
    if not bad.empty:
        raise AssertionError(f"Insufficient history for tickers: {bad.to_dict(orient='records')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate ETF core universe outputs.")
    ap.add_argument("--asof", required=True, help="YYYYMMDD or YYYY-MM-DD")
    ap.add_argument("--core-csv", default="")
    ap.add_argument("--meta-csv", default="")
    ap.add_argument("--rules-yml", default=str(PROJECT_ROOT / r"data\universe\etf_classification_rules.yml"))
    ap.add_argument("--price-db", default=str(PROJECT_ROOT / r"data\db\price.db"))
    args = ap.parse_args()

    asof = str(args.asof).strip().replace("-", "")
    core_csv = Path(args.core_csv) if args.core_csv else PROJECT_ROOT / "data" / "universe" / f"universe_etf_core_{asof}.csv"
    meta_csv = Path(args.meta_csv) if args.meta_csv else PROJECT_ROOT / "data" / "universe" / f"etf_meta_{asof}.csv"
    rules = _load_rules(Path(args.rules_yml))
    min_history_days = int(rules.get("defaults", {}).get("min_history_days", 20))
    required_groups = list(rules.get("required_groups", []))

    if not core_csv.exists():
        raise AssertionError(f"Core CSV not found: {core_csv}")
    if not meta_csv.exists():
        raise AssertionError(f"Meta CSV not found: {meta_csv}")

    core_df = pd.read_csv(core_csv, dtype={"ticker": "string"})
    meta_df = pd.read_csv(meta_csv, dtype={"ticker": "string"})

    missing_cols = _required_cols() - set(core_df.columns)
    if missing_cols:
        raise AssertionError(f"Missing core columns: {sorted(missing_cols)}")
    if core_df.empty:
        raise AssertionError("Core universe is empty.")
    if meta_df.empty:
        raise AssertionError("ETF meta output is empty.")
    if core_df["ticker"].duplicated().any():
        raise AssertionError("Core universe contains duplicate tickers.")
    if (core_df["asset_type"].astype(str) != "ETF").any():
        raise AssertionError("Core universe contains non-ETF rows.")
    for col in ["asset_class", "group_key", "currency_exposure"]:
        if core_df[col].astype(str).str.strip().eq("").any():
            raise AssertionError(f"Core universe has blank values in {col}.")
    if (~core_df["min_liquidity_pass"].astype(bool)).any():
        raise AssertionError("Core universe contains rows that failed the liquidity threshold.")
    if (pd.to_numeric(core_df["liquidity_20d_value"], errors="coerce").fillna(0) <= 0).any():
        raise AssertionError("Core universe contains non-positive liquidity_20d_value.")

    present_groups = set(core_df["group_key"].astype(str).tolist())
    missing_groups = [g for g in required_groups if g not in present_groups]
    if missing_groups:
        raise AssertionError(f"Missing required groups: {missing_groups}")

    tickers = core_df["ticker"].astype(str).str.zfill(6).tolist()
    asof_date = f"{asof[0:4]}-{asof[4:6]}-{asof[6:8]}"
    _validate_recent_history(Path(args.price_db), tickers, asof_date, min_history_days)

    print(f"[OK] core_csv={core_csv}")
    print(f"[OK] meta_csv={meta_csv}")
    print(f"[OK] core_rows={len(core_df)} groups={sorted(present_groups)}")
    print(f"[OK] validated_recent_history_days={min_history_days}")


if __name__ == "__main__":
    main()
