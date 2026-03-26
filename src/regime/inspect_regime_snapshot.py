# inspect_regime_snapshot.py ver 2026-01-29_001
"""
Regime snapshot report

- Reads regime_history from regime.db
- Picks a target date (default: max(date) in DB)
- For each horizon (1y/6m/3m):
  - regime distribution counts (0..4)
  - Top N by score
  - Bottom N by score
  - Top N among regime=4
  - Bottom N among regime=0
- Optionally restricts to tickers from a universe CSV
- Saves CSV files under reports/regime_snapshot/
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

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


def load_universe_tickers(universe_file: str, ticker_col: str) -> List[str]:
    df = pd.read_csv(universe_file)
    if ticker_col not in df.columns:
        raise RuntimeError(f"ticker_col not found: {ticker_col}. cols={list(df.columns)}")
    tickers = sorted({_ensure_ticker6(x) for x in df[ticker_col].dropna().astype(str).tolist()})
    return tickers


def get_max_date(con: sqlite3.Connection, table: str) -> str:
    cur = con.cursor()
    d = cur.execute(f"SELECT MAX(date) FROM {table}").fetchone()[0]
    if not d:
        raise RuntimeError(f"table empty or no date: {table}")
    return str(d)


def fetch_snapshot(
    con: sqlite3.Connection,
    table: str,
    date: str,
    horizon: str,
    tickers: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Returns DataFrame: date, ticker, horizon, score, regime
    """
    cur = con.cursor()
    if tickers:
        # chunk IN clause to avoid SQLITE_MAX_VARIABLE_NUMBER
        out = []
        chunk = 900
        for i in range(0, len(tickers), chunk):
            chunk_t = tickers[i : i + chunk]
            ph = ",".join(["?"] * len(chunk_t))
            sql = f"""
                SELECT date, ticker, horizon, score, regime
                FROM {table}
                WHERE date = ? AND horizon = ?
                  AND ticker IN ({ph})
            """
            params = [date, horizon] + chunk_t
            out.extend(cur.execute(sql, params).fetchall())
        df = pd.DataFrame(out, columns=["date", "ticker", "horizon", "score", "regime"])
    else:
        sql = f"""
            SELECT date, ticker, horizon, score, regime
            FROM {table}
            WHERE date = ? AND horizon = ?
        """
        df = pd.DataFrame(cur.execute(sql, (date, horizon)).fetchall(),
                          columns=["date", "ticker", "horizon", "score", "regime"])

    if df.empty:
        return df

    df["ticker"] = df["ticker"].map(_ensure_ticker6)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    # regime should already be integer in DB; keep as int where possible
    df["regime"] = pd.to_numeric(df["regime"], errors="coerce").astype("Int64")
    return df


def print_section(title: str) -> None:
    _log("")
    _log("=" * 80)
    _log(title)
    _log("=" * 80)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime-db", required=True, help="path to regime.db")
    ap.add_argument("--regime-table", default="regime_history")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: max(date))")
    ap.add_argument("--horizons", default="1y,6m,3m", help="comma-separated horizons")
    ap.add_argument("--top", type=int, default=10, help="Top N rows to show")
    ap.add_argument("--universe-file", default="", help="optional universe csv to restrict tickers")
    ap.add_argument("--ticker-col", default="ticker", help="ticker column in universe file")
    ap.add_argument("--outdir", default=r".\reports\regime_snapshot", help="output directory")
    args = ap.parse_args()

    project_root = resolve_project_root(Path.cwd())
    os.chdir(project_root)

    regime_db = Path(args.regime_db).resolve()
    if not regime_db.exists():
        raise FileNotFoundError(str(regime_db))

    tickers: Optional[List[str]] = None
    if args.universe_file:
        uni_path = Path(args.universe_file).resolve()
        if not uni_path.exists():
            raise FileNotFoundError(str(uni_path))
        tickers = load_universe_tickers(str(uni_path), args.ticker_col)
        _log(f"[INFO] universe tickers loaded: {len(tickers):,}")

    outdir = (Path(project_root) / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]

    con = sqlite3.connect(str(regime_db))
    try:
        date = args.date.strip()
        if not date:
            date = get_max_date(con, args.regime_table)
        _log(f"[INFO] regime_db={regime_db}")
        _log(f"[INFO] table={args.regime_table}")
        _log(f"[INFO] snapshot date={date}")
        _log(f"[INFO] horizons={horizons}")
        _log(f"[INFO] outdir={outdir}")

        for hz in horizons:
            df = fetch_snapshot(con, args.regime_table, date, hz, tickers=tickers)
            print_section(f"SNAPSHOT | date={date} | horizon={hz} | rows={len(df):,}")

            if df.empty:
                _log("[WARN] empty snapshot for this horizon.")
                continue

            # regime distribution
            dist = (df["regime"].value_counts(dropna=False).sort_index())
            _log("[DIST] regime counts:")
            _log(dist.to_string())

            # Sort by score desc/asc
            df_sorted_desc = df.sort_values(["score", "ticker"], ascending=[False, True])
            df_sorted_asc = df.sort_values(["score", "ticker"], ascending=[True, True])

            topN = args.top

            _log("")
            _log(f"[TOP {topN}] by score")
            _log(df_sorted_desc.head(topN).to_string(index=False))

            _log("")
            _log(f"[BOTTOM {topN}] by score")
            _log(df_sorted_asc.head(topN).to_string(index=False))

            df_r4 = df[df["regime"] == 4].sort_values(["score", "ticker"], ascending=[False, True])
            df_r0 = df[df["regime"] == 0].sort_values(["score", "ticker"], ascending=[True, True])

            _log("")
            _log(f"[TOP {topN}] within regime=4")
            _log(df_r4.head(topN).to_string(index=False) if not df_r4.empty else "(none)")

            _log("")
            _log(f"[BOTTOM {topN}] within regime=0")
            _log(df_r0.head(topN).to_string(index=False) if not df_r0.empty else "(none)")

            # Save CSV
            csv_path = outdir / f"regime_snapshot_{date}_{hz}.csv"
            df_sorted_desc.to_csv(csv_path, index=False, encoding="utf-8-sig")
            _log(f"[SAVE] {csv_path}")

        _log("\n[INFO] done.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
