# price_backfill.py ver 2026-02-05_001
"""
과거(Backfill) 일봉 가격을 수집해서 SQLite에 저장합니다.

예)
  python price_backfill.py --tickers 005930 --start 20100101
  python price_backfill.py --tickers-file data/universe.csv --ticker-col ticker --start 20150101 --chunk-size 50

기본 Provider: pykrx
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

from price_store import PriceStore


def _parse_ymd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _read_tickers_from_csv(path: Path, col: str) -> List[str]:
    df = pd.read_csv(path, dtype={col: str})
    if col not in df.columns:
        raise ValueError(f"CSV에 '{col}' 컬럼이 없습니다. columns={list(df.columns)}")
    tickers = (
        df[col]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)  # 엑셀에서 숫자로 저장된 경우 대비
        .tolist()
    )
    tickers = [t.zfill(6) for t in tickers if t and t.lower() not in ["nan", "none"]]
    return tickers


def _chunk(lst: List[str], size: int) -> List[List[str]]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def fetch_ohlcv_pykrx(ticker: str, start: date, end: date) -> pd.DataFrame:
    """
    pykrx로 일봉 OHLCV(+거래대금)를 가져와 표준 컬럼으로 반환.
    반환 컬럼: open, high, low, close, volume, value
    """
    from pykrx import stock

    df = stock.get_market_ohlcv_by_date(_ymd(start), _ymd(end), ticker)
    if df is None or df.empty:
        return pd.DataFrame()

    rename_map = {
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
        "거래대금": "value",
    }
    df = df.rename(columns=rename_map)

    for c in ["open", "high", "low", "close", "volume", "value"]:
        if c not in df.columns:
            df[c] = None

    df = df[["open", "high", "low", "close", "volume", "value"]].copy()
    df.index = pd.to_datetime(df.index)
    return df


def _get_last_trading_day_pykrx(ref: date, probe_ticker: str = "005930", lookback_days: int = 21) -> Optional[date]:
    """
    ref 기준으로 최근 거래일을 pykrx로 탐색합니다.
    - 휴장일/주말/미래일 ref가 들어와도 안전하게 보정 가능합니다.
    """
    start = ref - timedelta(days=max(7, lookback_days))
    df = fetch_ohlcv_pykrx(probe_ticker, start, ref)
    if df is None or df.empty:
        return None
    return pd.to_datetime(df.index.max()).date()


def backfill_ticker(
    store: PriceStore,
    ticker: str,
    start: date,
    end: date,
    sleep_sec: float,
    retries: int,
) -> int:
    for attempt in range(1, retries + 1):
        try:
            df = fetch_ohlcv_pykrx(ticker, start, end)
            n = store.upsert_prices(ticker, df, source="pykrx")
            return n
        except Exception as e:
            if attempt == retries:
                print(f"[FAIL] {ticker} backfill failed: {e}", file=sys.stderr)
                return 0
            time.sleep(max(1.0, sleep_sec))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=str, default="005930", help="예: 005930,000660 (콤마 구분)")
    ap.add_argument("--tickers-file", type=str, default="", help="유니버스 CSV 경로")
    ap.add_argument("--ticker-col", type=str, default="ticker", help="CSV의 종목코드 컬럼명")
    ap.add_argument("--start", type=str, required=True, help="YYYYMMDD 또는 YYYY-MM-DD")
    ap.add_argument("--end", type=str, default=date.today().strftime("%Y%m%d"), help="기본: 오늘(내부에서 최근 거래일로 보정)")
    ap.add_argument("--chunk-size", type=int, default=50, help="유니버스 분할 크기")
    ap.add_argument("--sleep", type=float, default=0.2, help="요청 간 sleep(초)")
    ap.add_argument("--retries", type=int, default=3, help="종목별 재시도 횟수")
    ap.add_argument("--db", type=str, default="", help="price.db 경로(미지정 시 기본 경로)")
    ap.add_argument("--probe-ticker", type=str, default="005930", help="최근 거래일 탐색용 대표 티커")
    args = ap.parse_args()

    start = _parse_ymd(args.start)
    requested_end = _parse_ymd(args.end)

    # end를 최근 거래일로 보정
    last_td = _get_last_trading_day_pykrx(requested_end, probe_ticker=args.probe_ticker)
    if last_td:
        end = min(requested_end, last_td)
        if requested_end != end:
            print(f"[WARN] end({requested_end}) is not a trading day. using last_trading_day={end}")
    else:
        end = requested_end
        print(f"[WARN] failed to detect last trading day via pykrx. using end={end}")

    if start > end:
        raise ValueError("start가 end보다 클 수 없습니다.")

    db_path = Path(args.db) if args.db else None
    store = PriceStore(db_path=db_path) if db_path else PriceStore()

    if args.tickers_file:
        tickers = _read_tickers_from_csv(Path(args.tickers_file), args.ticker_col)
    else:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]

    if not tickers:
        raise ValueError("tickers가 비어 있습니다.")

    print(f"[INFO] DB: {store.db_path}")
    print(f"[INFO] tickers={len(tickers)}, range={start}~{end} (requested_end={requested_end})")

    chunks = _chunk(tickers, max(1, args.chunk_size))
    total_saved = 0

    for ci, group in enumerate(chunks, start=1):
        print(f"\n[CHUNK {ci}/{len(chunks)}] size={len(group)}")
        for ti, ticker in enumerate(group, start=1):
            print(f"  - ({ti}/{len(group)}) {ticker} ... ", end="")
            n = backfill_ticker(store, ticker, start, end, args.sleep, args.retries)
            total_saved += n
            print(f"saved={n}")
            time.sleep(max(0.0, args.sleep))

    print(f"\n[DONE] total_saved_rows={total_saved}")


if __name__ == "__main__":
    main()
