# filter_universe_by_price_db.py ver 2026-02-05_001
import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe-in", required=True)
    ap.add_argument("--universe-out", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--asof", required=True, help="YYYY-MM-DD (예: 2026-02-05)")
    ap.add_argument("--price-db", default=r"D:\Quant\data\db\price.db")
    ap.add_argument("--price-table", default="prices_daily")
    ap.add_argument("--save-dropped", default="")
    args = ap.parse_args()

    df = pd.read_csv(args.universe_in, dtype={args.ticker_col: str})
    df[args.ticker_col] = df[args.ticker_col].str.zfill(6)

    con = sqlite3.connect(args.price_db)

    # asof에 데이터가 있는 ticker 목록
    q = f"SELECT ticker FROM {args.price_table} WHERE date = ?"
    have = pd.read_sql_query(q, con, params=[args.asof])
    con.close()

    have_set = set(have["ticker"].astype(str).str.zfill(6))

    ok = df[df[args.ticker_col].isin(have_set)].copy()
    bad = df[~df[args.ticker_col].isin(have_set)].copy()

    Path(args.universe_out).parent.mkdir(parents=True, exist_ok=True)
    ok.to_csv(args.universe_out, index=False, encoding="utf-8-sig")
    print(f"[DONE] ok={len(ok)} dropped={len(bad)} -> {args.universe_out}")

    if args.save_dropped and len(bad) > 0:
        Path(args.save_dropped).parent.mkdir(parents=True, exist_ok=True)
        bad.to_csv(args.save_dropped, index=False, encoding="utf-8-sig")
        print(f"[SAVE] dropped -> {args.save_dropped}")


if __name__ == "__main__":
    main()
