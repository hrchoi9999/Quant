# tmp_check_growth_score_distinct.py ver 2026-02-02_001
"""
Check distinct counts of growth_score in fundamentals table.

- Overall distinct count of growth_score
- Distinct count by available_from (date)
- Optional: filter to tickers in a universe csv
- Optional: focus on specific available_from date
"""

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def _read_table_cols(con: sqlite3.Connection, table: str) -> list[str]:
    df = pd.read_sql_query(f"PRAGMA table_info('{table}')", con)
    return df["name"].tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="D:/Quant/data/db/fundamentals.db")
    ap.add_argument("--table", default="fundamentals_monthly_mix400_20260129")
    ap.add_argument("--score-col", default="growth_score")
    ap.add_argument("--universe-file", default=None, help="optional CSV to filter tickers (e.g., universe_mix_top400_...csv)")
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--asof", default=None, help="optional available_from date (YYYY-MM-DD) to inspect")
    ap.add_argument("--topk", type=int, default=15, help="how many dates to show for low/high distinct")
    args = ap.parse_args()

    db_path = str(args.db)
    table = args.table
    score_col = args.score_col

    con = sqlite3.connect(db_path)

    # sanity: columns
    cols = _read_table_cols(con, table)
    must = {"ticker", "available_from", score_col}
    missing = sorted(list(must - set(cols)))
    if missing:
        con.close()
        raise SystemExit(f"[ERROR] Missing columns in {table}: {missing}. Existing cols={cols}")

    # optional ticker filter from universe
    tickers = None
    if args.universe_file:
        u = pd.read_csv(args.universe_file, dtype={args.ticker_col: str})
        if args.ticker_col not in u.columns:
            con.close()
            raise SystemExit(f"[ERROR] universe file has no column '{args.ticker_col}'")
        tickers = u[args.ticker_col].astype(str).str.zfill(6).unique().tolist()
        print(f"[INFO] universe tickers loaded: {len(tickers)} from {args.universe_file}")

    # load minimal columns
    q = f"SELECT ticker, available_from, {score_col} AS score FROM {table}"
    df = pd.read_sql_query(q, con)
    con.close()

    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["available_from"] = pd.to_datetime(df["available_from"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")

    if tickers is not None:
        df = df[df["ticker"].isin(tickers)].copy()

    # drop rows with no available_from (shouldn't happen)
    df = df.dropna(subset=["available_from"])

    # Overall summary
    overall_n = len(df)
    overall_nonnull = int(df["score"].notna().sum())
    overall_uniq = int(df["score"].nunique(dropna=True))
    print("\n==============================")
    print("[OVERALL]")
    print("==============================")
    print(f"rows={overall_n:,} | score_nonnull={overall_nonnull:,} | score_distinct={overall_uniq:,}")
    if overall_nonnull > 0:
        desc = df["score"].describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99])
        print("\n[score describe]")
        print(desc.to_string())

        top_vals = df["score"].value_counts(dropna=True).head(10)
        print("\n[top 10 most frequent score values]")
        print(top_vals.to_string())

    # Distinct by available_from
    g = (
        df.groupby(df["available_from"].dt.date)
          .agg(rows=("score", "size"),
               nonnull=("score", lambda s: int(s.notna().sum())),
               distinct=("score", lambda s: int(s.nunique(dropna=True))),
               min=("score", "min"),
               max=("score", "max"))
          .reset_index()
          .rename(columns={"available_from": "available_from_date"})
    )

    print("\n==============================")
    print("[BY available_from]")
    print("==============================")
    print(f"dates={len(g)}")

    # show low distinct dates
    low = g.sort_values(["distinct", "nonnull", "rows"], ascending=[True, True, True]).head(args.topk)
    high = g.sort_values(["distinct", "nonnull", "rows"], ascending=[False, False, False]).head(args.topk)

    print(f"\n[LOW distinct top {args.topk}]")
    print(low.to_string(index=False))

    print(f"\n[HIGH distinct top {args.topk}]")
    print(high.to_string(index=False))

    # Optional: inspect one date deeply
    if args.asof:
        asof = pd.to_datetime(args.asof).date()
        sub = df[df["available_from"].dt.date == asof].copy()
        print("\n==============================")
        print(f"[DETAIL for available_from={asof}]")
        print("==============================")
        print(f"rows={len(sub):,} | nonnull={int(sub['score'].notna().sum()):,} | distinct={int(sub['score'].nunique(dropna=True)):,}")

        vc = sub["score"].value_counts(dropna=True).head(20)
        print("\n[top 20 score values on that date]")
        print(vc.to_string())

        # show sample tickers for the most frequent score
        if len(vc) > 0:
            top_score = vc.index[0]
            samp = sub[sub["score"] == top_score][["ticker", "available_from", "score"]].head(30)
            print(f"\n[sample tickers with most frequent score={top_score}]")
            print(samp.to_string(index=False))

    print("\n[DONE]")


if __name__ == "__main__":
    main()
