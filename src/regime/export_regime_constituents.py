# export_regime_constituents.py ver 2026-01-29_001
"""
Export regime constituents (snapshot) to CSV.

Outputs CSV columns:
- date: snapshot date
- ticker: 6-digit code
- name: optional (joined from meta)
- market_cap: optional (joined from meta)
- regime: 0..4 (integer)
- score: horizon return used for ranking (from regime_history.score)

Meta join options (optional):
1) --meta-csv  (recommended)
   CSV must include columns: ticker, name, market_cap (configurable)
2) --meta-db/--meta-table
   Table must include ticker + (name, market_cap) columns (configurable)

If meta not provided or join fails, name/market_cap will be empty.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Optional, List

import pandas as pd


def _log(msg: str) -> None:
    print(msg, flush=True)


def resolve_project_root(start: Path) -> Path:
    p = start.resolve()
    if p.is_file():
        p = p.parent
    for _ in range(12):
        if (p / "src").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return start.resolve()


def _ensure_ticker6(x: str) -> str:
    s = str(x).strip()
    if s.isdigit() and len(s) < 6:
        s = s.zfill(6)
    return s


def get_max_date(con: sqlite3.Connection, table: str, horizon: str) -> str:
    cur = con.cursor()
    d = cur.execute(f"SELECT MAX(date) FROM {table} WHERE horizon = ?", (horizon,)).fetchone()[0]
    if not d:
        raise RuntimeError(f"cannot find max(date) for horizon={horizon} in table={table}")
    return str(d)


def load_universe_tickers(universe_file: str, ticker_col: str) -> List[str]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns:
        raise RuntimeError(f"ticker_col not found: {ticker_col}. cols={list(df.columns)}")
    return sorted({_ensure_ticker6(x) for x in df[ticker_col].dropna().astype(str).tolist()})


def fetch_regime_snapshot(
    regime_db: str,
    regime_table: str,
    horizon: str,
    date: str,
    tickers: Optional[List[str]] = None,
) -> pd.DataFrame:
    con = sqlite3.connect(regime_db)
    try:
        cur = con.cursor()
        if tickers:
            out = []
            chunk = 900
            for i in range(0, len(tickers), chunk):
                ct = tickers[i : i + chunk]
                ph = ",".join(["?"] * len(ct))
                sql = f"""
                    SELECT date, ticker, horizon, score, regime
                    FROM {regime_table}
                    WHERE horizon = ?
                      AND date = ?
                      AND ticker IN ({ph})
                """
                params = [horizon, date] + ct
                out.extend(cur.execute(sql, params).fetchall())
            df = pd.DataFrame(out, columns=["date", "ticker", "horizon", "score", "regime"])
        else:
            sql = f"""
                SELECT date, ticker, horizon, score, regime
                FROM {regime_table}
                WHERE horizon = ?
                  AND date = ?
            """
            df = pd.read_sql_query(sql, con, params=(horizon, date))
    finally:
        con.close()

    if df.empty:
        raise RuntimeError(f"snapshot empty: horizon={horizon}, date={date} (tickers filtered? {bool(tickers)})")

    df["ticker"] = df["ticker"].map(_ensure_ticker6)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["regime"] = pd.to_numeric(df["regime"], errors="coerce").astype("Int64")
    df = df[df["regime"].notna()].copy()
    df["regime"] = df["regime"].astype(int)
    return df


def load_meta_from_csv(
    meta_csv: str,
    meta_ticker_col: str,
    meta_name_col: str,
    meta_mcap_col: str,
) -> pd.DataFrame:
    df = pd.read_csv(meta_csv)
    for c in (meta_ticker_col, meta_name_col, meta_mcap_col):
        if c not in df.columns:
            raise RuntimeError(f"meta csv missing column: {c}. cols={list(df.columns)}")
    out = df[[meta_ticker_col, meta_name_col, meta_mcap_col]].copy()
    out.columns = ["ticker", "name", "market_cap"]
    out["ticker"] = out["ticker"].map(_ensure_ticker6)
    out["name"] = out["name"].astype(str)
    out["market_cap"] = pd.to_numeric(out["market_cap"], errors="coerce")
    out = out.drop_duplicates(subset=["ticker"], keep="last")
    return out


def load_meta_from_db(
    meta_db: str,
    meta_table: str,
    meta_ticker_col: str,
    meta_name_col: str,
    meta_mcap_col: str,
) -> pd.DataFrame:
    con = sqlite3.connect(meta_db)
    try:
        sql = f"""
            SELECT {meta_ticker_col} AS ticker,
                   {meta_name_col}   AS name,
                   {meta_mcap_col}   AS market_cap
            FROM {meta_table}
        """
        df = pd.read_sql_query(sql, con)
    finally:
        con.close()

    df["ticker"] = df["ticker"].map(_ensure_ticker6)
    df["name"] = df["name"].astype(str)
    df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce")
    df = df.drop_duplicates(subset=["ticker"], keep="last")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime-db", required=True)
    ap.add_argument("--regime-table", default="regime_history")
    ap.add_argument("--horizon", default="3m", help="3m/6m/1y")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: max(date) for that horizon)")
    ap.add_argument("--universe-file", default="", help="optional ticker universe csv")
    ap.add_argument("--ticker-col", default="ticker", help="ticker column in universe file")
    ap.add_argument("--outdir", default=r".\reports\regime_constituents")

    # meta (optional)
    ap.add_argument("--meta-csv", default="", help="optional meta csv containing ticker/name/market_cap")
    ap.add_argument("--meta-db", default="", help="optional meta sqlite db")
    ap.add_argument("--meta-table", default="", help="optional meta table name")
    ap.add_argument("--meta-ticker-col", default="ticker")
    ap.add_argument("--meta-name-col", default="name")
    ap.add_argument("--meta-mcap-col", default="market_cap")

    args = ap.parse_args()

    project_root = resolve_project_root(Path.cwd())
    os.chdir(project_root)

    regime_db = str(Path(args.regime_db).resolve())
    if not Path(regime_db).exists():
        raise FileNotFoundError(regime_db)

    tickers: Optional[List[str]] = None
    if args.universe_file:
        uni_path = Path(args.universe_file).resolve()
        if not uni_path.exists():
            raise FileNotFoundError(str(uni_path))
        tickers = load_universe_tickers(str(uni_path), args.ticker_col)
        _log(f"[INFO] universe tickers={len(tickers):,}")

    # determine date
    date = args.date.strip()
    if not date:
        con = sqlite3.connect(regime_db)
        try:
            date = get_max_date(con, args.regime_table, args.horizon)
        finally:
            con.close()
    _log(f"[INFO] snapshot date={date} horizon={args.horizon}")

    # fetch snapshot
    snap = fetch_regime_snapshot(
        regime_db=regime_db,
        regime_table=args.regime_table,
        horizon=args.horizon,
        date=date,
        tickers=tickers,
    )
    _log(f"[INFO] snapshot rows={len(snap):,}")

    # load meta if provided
    meta = None
    try:
        if args.meta_csv:
            meta = load_meta_from_csv(
                meta_csv=str(Path(args.meta_csv).resolve()),
                meta_ticker_col=args.meta_ticker_col,
                meta_name_col=args.meta_name_col,
                meta_mcap_col=args.meta_mcap_col,
            )
            _log(f"[INFO] meta loaded from csv: rows={len(meta):,}")
        elif args.meta_db and args.meta_table:
            meta = load_meta_from_db(
                meta_db=str(Path(args.meta_db).resolve()),
                meta_table=args.meta_table,
                meta_ticker_col=args.meta_ticker_col,
                meta_name_col=args.meta_name_col,
                meta_mcap_col=args.meta_mcap_col,
            )
            _log(f"[INFO] meta loaded from db: rows={len(meta):,}")
    except Exception as e:
        _log(f"[WARN] meta load failed: {e}")
        meta = None

    if meta is not None:
        out = snap.merge(meta, on="ticker", how="left")
    else:
        out = snap.copy()
        out["name"] = pd.NA
        out["market_cap"] = pd.NA

    # reorder columns to your requested layout
    out = out[["date", "ticker", "name", "market_cap", "regime", "score"]].copy()

    # sort (regime desc then score desc by default)
    out = out.sort_values(["regime", "score", "ticker"], ascending=[False, False, True])

    outdir = (Path(project_root) / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    out_path = outdir / f"regime_constituents_{date}_{args.horizon}.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")

    _log(f"[SAVE] {out_path}")
    _log("[INFO] done.")


if __name__ == "__main__":
    main()
