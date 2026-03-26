# validate_universe_by_price.py ver 2026-02-05_001
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from pykrx import stock


def has_any_price(ticker: str, asof: str, lookback_days: int = 30) -> bool:
    end = datetime.strptime(asof, "%Y-%m-%d").date()
    start = end - timedelta(days=lookback_days)
    df = stock.get_market_ohlcv_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker)
    return df is not None and not df.empty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outfile", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--asof", required=True)
    ap.add_argument("--lookback-days", type=int, default=30)
    ap.add_argument("--drop-report", default="")
    args = ap.parse_args()

    df = pd.read_csv(args.infile, dtype={args.ticker_col: str})
    df[args.ticker_col] = df[args.ticker_col].str.zfill(6)

    ok_rows = []
    dropped = []

    for _, r in df.iterrows():
        t = r[args.ticker_col]
        if has_any_price(t, args.asof, args.lookback_days):
            ok_rows.append(r)
        else:
            dropped.append(r)

    out = pd.DataFrame(ok_rows)
    out.to_csv(args.outfile, index=False, encoding="utf-8-sig")

    print(f"[OK] input={len(df)} output={len(out)} dropped={len(dropped)}")
    if dropped:
        dd = pd.DataFrame(dropped)
        print("[DROPPED]")
        print(dd[[args.ticker_col, "market", "mcap"]].head(20).to_string(index=False))
        if args.drop_report:
            Path(args.drop_report).parent.mkdir(parents=True, exist_ok=True)
            dd.to_csv(args.drop_report, index=False, encoding="utf-8-sig")
            print(f"[SAVE] dropped -> {args.drop_report}")


if __name__ == "__main__":
    main()
