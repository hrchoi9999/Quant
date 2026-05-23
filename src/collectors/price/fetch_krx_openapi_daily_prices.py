from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    from src.collectors.krx_openapi import (
        fetch_etf_daily,
        fetch_stock_daily,
        iter_bas_dd,
        load_api_key,
        price_frame_to_store_frame,
    )
    from src.collectors.price.price_store import PriceStore
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / "src").exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.collectors.krx_openapi import (
        fetch_etf_daily,
        fetch_stock_daily,
        iter_bas_dd,
        load_api_key,
        price_frame_to_store_frame,
    )
    from src.collectors.price.price_store import PriceStore


def _find_project_root(start_path: Path) -> Path:
    for path in [start_path] + list(start_path.parents):
        if (path / "src").exists() and (path / "modules").exists():
            return path
    return start_path


def _parse_markets(value: str) -> list[str]:
    markets = [item.strip().upper() for item in str(value).split(",") if item.strip()]
    if not markets:
        raise ValueError("markets is empty")
    valid = {"KOSPI", "KOSDAQ", "ETF"}
    invalid = sorted(set(markets) - valid)
    if invalid:
        raise ValueError(f"unsupported markets: {invalid}; valid={sorted(valid)}")
    return markets


def _target_filter(frame: pd.DataFrame, tickers: set[str] | None) -> pd.DataFrame:
    if tickers is None or frame.empty:
        return frame
    return frame.loc[frame["ticker"].astype(str).str.zfill(6).isin(tickers)].copy()


def _read_tickers(path: str, ticker_col: str) -> set[str] | None:
    if not path:
        return None
    df = pd.read_csv(Path(path), dtype={ticker_col: "string"})
    if ticker_col not in df.columns:
        raise ValueError(f"missing ticker column {ticker_col}: {path}")
    return {
        str(value).strip().replace(".0", "").zfill(6)
        for value in df[ticker_col].dropna().tolist()
        if str(value).strip()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch KRX OpenAPI daily OHLCV rows into price.db.")
    parser.add_argument("--start", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--markets", default="KOSPI,KOSDAQ", help="Comma list: KOSPI,KOSDAQ,ETF")
    parser.add_argument("--db", default="", help="Optional price.db path")
    parser.add_argument("--api-key-file", default=str(Path(r"D:\Quant\config\KRX_API_Key.json")))
    parser.add_argument("--tickers-file", default="", help="Optional CSV to restrict inserted tickers")
    parser.add_argument("--ticker-col", default="ticker")
    args = parser.parse_args()

    current = Path(__file__).resolve()
    root = _find_project_root(current.parent)
    db_path = Path(args.db) if args.db else root / "data" / "db" / "price.db"
    store = PriceStore(db_path=db_path)
    api_key = load_api_key(args.api_key_file)
    markets = _parse_markets(args.markets)
    target_tickers = _read_tickers(args.tickers_file, args.ticker_col)

    total_rows = 0
    inserted_rows = 0
    print(f"[INFO] db={db_path}")
    print(f"[INFO] markets={markets}, range={args.start}~{args.end}")
    print(f"[INFO] target_filter={'all' if target_tickers is None else len(target_tickers)}")

    for bas_dd in iter_bas_dd(args.start, args.end):
        frames: list[pd.DataFrame] = []
        for market in markets:
            if market == "ETF":
                frame = fetch_etf_daily(bas_dd, api_key)
            else:
                frame = fetch_stock_daily(market, bas_dd, api_key)
            frame = _target_filter(frame, target_tickers)
            if not frame.empty:
                frames.append(frame)
            print(f"[INFO] basDd={bas_dd} market={market} rows={len(frame)}")
        if not frames:
            continue
        daily = pd.concat(frames, ignore_index=True)
        total_rows += len(daily)
        for ticker, _ in daily.groupby("ticker", sort=False):
            store_frame = price_frame_to_store_frame(daily, str(ticker))
            inserted_rows += store.upsert_prices(str(ticker).zfill(6), store_frame, source="krx_openapi")

    print(f"[DONE] fetched_rows={total_rows} upserted_rows={inserted_rows}")


if __name__ == "__main__":
    main()
