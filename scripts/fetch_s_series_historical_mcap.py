from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(r"D:\Quant")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.krx_openapi import fetch_stock_daily, load_api_key

QS_DB = PROJECT_ROOT / r"data\db\quant_service.db"
QS_DETAIL_DB = PROJECT_ROOT / r"data\db\quant_service_detail.db"
OUTDIR = PROJECT_ROOT / r"reports\score_correlation_review\20260424_s_series_challenger_backtest_historical_mcap"


def read_sql(db: Path, query: str, params: tuple | None = None, parse_dates: list[str] | None = None) -> pd.DataFrame:
    con = sqlite3.connect(str(db))
    try:
        return pd.read_sql_query(query, con, params=params or (), parse_dates=parse_dates or None)
    finally:
        con.close()


def load_signal_dates() -> list[pd.Timestamp]:
    runs = read_sql(
        QS_DB,
        """
        SELECT model_code, published_run_id
        FROM pub_model_current
        WHERE model_code IN ('S2','S3','S3_CORE2')
        """,
    )
    frames = []
    for row in runs.itertuples(index=False):
        frames.append(
            read_sql(
                QS_DETAIL_DB,
                "SELECT DISTINCT date FROM run_holdings_history WHERE run_id=? ORDER BY date",
                params=(row.published_run_id,),
                parse_dates=["date"],
            )
        )
    if not frames:
        return []
    dates = pd.concat(frames, ignore_index=True)["date"].dropna().drop_duplicates().sort_values()
    return [pd.Timestamp(d) for d in dates]


def load_universe_tickers() -> set[str]:
    path = PROJECT_ROOT / r"data\universe\universe_mix_top400_latest_fundready.csv"
    df = pd.read_csv(path, dtype={"ticker": str})
    return set(df["ticker"].astype(str).str.zfill(6))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--output", default=str(OUTDIR / "historical_mcap_signal_dates.csv"))
    ap.add_argument("--start-date", default="", help="Optional YYYY-MM-DD lower bound for signal dates")
    ap.add_argument("--end-date", default="", help="Optional YYYY-MM-DD upper bound for signal dates")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    outpath = Path(args.output)
    outpath.parent.mkdir(parents=True, exist_ok=True)

    dates = load_signal_dates()
    if args.start_date:
        dates = [d for d in dates if d >= pd.Timestamp(args.start_date)]
    if args.end_date:
        dates = [d for d in dates if d <= pd.Timestamp(args.end_date)]
    universe_tickers = load_universe_tickers()
    api_key = load_api_key()

    rows = []
    for dt in dates:
        bas_dd = dt.strftime("%Y%m%d")
        for market in ["KOSPI", "KOSDAQ"]:
            frame = fetch_stock_daily(market, bas_dd, api_key=api_key)
            if frame.empty:
                continue
            frame["ticker"] = frame["ticker"].astype(str).str.zfill(6)
            frame = frame[frame["ticker"].isin(universe_tickers)].copy()
            if frame.empty:
                continue
            frame["date"] = pd.Timestamp(dt)
            rows.append(frame[["date", "ticker", "name", "market", "mcap", "list_shares"]].copy())
            time.sleep(args.sleep)

    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "ticker", "name", "market", "mcap", "list_shares"])
    out = out.drop_duplicates(["date", "ticker"]).sort_values(["date", "ticker"])
    out.to_csv(outpath, index=False, encoding="utf-8-sig")
    print(f"[OK] wrote {outpath} rows={len(out)} dates={out['date'].nunique() if not out.empty else 0}")


if __name__ == "__main__":
    main()
