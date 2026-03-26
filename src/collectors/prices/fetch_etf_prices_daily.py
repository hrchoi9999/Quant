# fetch_etf_prices_daily.py ver 2026-03-17_005
"""
Fetch ETF daily OHLCV and upsert into price.db.prices_daily.

Primary path:
- pykrx.stock.get_etf_ohlcv_by_date(start, end, ticker)

Fallback path:
- FinanceDataReader.DataReader(ticker, start, end)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd

try:
    from src.collectors.price.price_store import PriceStore
except Exception:
    CURRENT = Path(__file__).resolve()
    ROOT = next((p for p in [CURRENT] + list(CURRENT.parents) if (p / "src").exists()), CURRENT.parent)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.collectors.price.price_store import PriceStore


K_OPEN = "\uC2DC\uAC00"
K_HIGH = "\uACE0\uAC00"
K_LOW = "\uC800\uAC00"
K_CLOSE = "\uC885\uAC00"
K_VOLUME = "\uAC70\uB798\uB7C9"
K_VALUE = "\uAC70\uB798\uB300\uAE08"


def _parse_ymd(s: str) -> date:
    raw = str(s).strip()
    if len(raw) == 8 and raw.isdigit():
        return datetime.strptime(raw, "%Y%m%d").date()
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def _read_tickers(csv_path: Path, ticker_col: str) -> list[str]:
    df = pd.read_csv(csv_path, dtype={ticker_col: "string"})
    if ticker_col not in df.columns:
        raise ValueError(f"missing ticker column: {ticker_col}")
    tickers = (
        df[ticker_col]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .map(lambda x: x.zfill(6))
    )
    tickers = [t for t in tickers.tolist() if t.isdigit() and len(t) == 6]
    return list(dict.fromkeys(tickers))


def _resolve_recent_trading_day(ref: date, lookback_days: int) -> date:
    for lag in range(lookback_days + 1):
        probe = ref - timedelta(days=lag)
        if probe.weekday() < 5:
            return probe
    return ref


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    for col in ["open", "high", "low", "close", "volume", "value"]:
        if col not in df.columns:
            df[col] = None

    for col in ["open", "high", "low", "close", "volume", "value"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    missing_value = df["value"].isna() | (df["value"] <= 0)
    df.loc[missing_value, "value"] = df.loc[missing_value, "close"].fillna(0) * df.loc[missing_value, "volume"].fillna(0)

    df = df[["open", "high", "low", "close", "volume", "value"]].copy()
    df.index = pd.to_datetime(df.index)
    return df


def fetch_etf_ohlcv_pykrx(ticker: str, start: date, end: date) -> pd.DataFrame:
    from pykrx import stock

    df = stock.get_etf_ohlcv_by_date(_ymd(start), _ymd(end), ticker)
    if df is None or df.empty:
        return pd.DataFrame()

    rename_map = {
        K_OPEN: "open",
        K_HIGH: "high",
        K_LOW: "low",
        K_CLOSE: "close",
        K_VOLUME: "volume",
        K_VALUE: "value",
    }
    df = df.rename(columns=rename_map)
    return _normalize_frame(df)


def fetch_etf_ohlcv_fdr(ticker: str, start: date, end: date) -> pd.DataFrame:
    import FinanceDataReader as fdr

    df = fdr.DataReader(ticker, start.isoformat(), end.isoformat())
    if df is None or df.empty:
        return pd.DataFrame()

    rename_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Value": "value",
        "Amount": "value",
    }
    df = df.rename(columns=rename_map)
    return _normalize_frame(df)


def fetch_etf_ohlcv(ticker: str, start: date, end: date) -> Tuple[pd.DataFrame, str]:
    try:
        df = fetch_etf_ohlcv_pykrx(ticker, start, end)
        if not df.empty:
            return df, "pykrx_etf"
    except Exception as exc:
        print(f"[WARN] pykrx ETF price fallback triggered for {ticker}: {exc}")

    df = fetch_etf_ohlcv_fdr(ticker, start, end)
    if df.empty:
        return df, "fdr_etf_empty"
    return df, "fdr_etf"


def _compute_fetch_start(store: PriceStore, ticker: str, start_override: date, force_window: bool) -> date:
    if force_window:
        return start_override
    last = store.get_last_date(ticker)
    if last is None:
        return start_override
    return max(start_override, last + timedelta(days=1))


def _iter_fetch_targets(tickers: Iterable[str]) -> Iterable[str]:
    for ticker in tickers:
        norm = str(ticker).strip().zfill(6)
        if norm.isdigit() and len(norm) == 6:
            yield norm


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch KRX ETF prices into price.db")
    parser.add_argument("--start", required=True, help="YYYYMMDD or YYYY-MM-DD")
    parser.add_argument("--end", default="", help="Defaults to most recent weekday")
    parser.add_argument(
        "--universe-csv",
        type=str,
        default="",
        help="ETF universe CSV path. Defaults to latest universe_etf_master_*.csv",
    )
    parser.add_argument("--ticker-col", type=str, default="ticker")
    parser.add_argument("--db", type=str, default="", help="Optional price.db path")
    parser.add_argument("--sleep", type=float, default=0.2, help="Rate limit delay per ticker")
    parser.add_argument("--retries", type=int, default=3, help="Retry count per ticker")
    parser.add_argument("--limit", type=int, default=0, help="Optional ticker limit for smoke tests")
    parser.add_argument("--force-window", action="store_true", help="Fetch the full requested start/end window even if newer rows already exist")
    args = parser.parse_args()

    here = Path(__file__).resolve()
    project_root = _find_project_root(here.parent)
    universe_dir = project_root / "data" / "universe"
    db_path = Path(args.db) if args.db else project_root / "data" / "db" / "price.db"

    start = _parse_ymd(args.start)
    end = _parse_ymd(args.end) if args.end else _resolve_recent_trading_day(date.today(), 10)
    if start > end:
        raise ValueError("start must be <= end")

    if args.universe_csv:
        universe_csv = Path(args.universe_csv)
    else:
        candidates = sorted(universe_dir.glob("universe_etf_master_*.csv"))
        if not candidates:
            raise FileNotFoundError("No ETF universe CSV found. Run build_universe_etf_krx.py first.")
        universe_csv = candidates[-1]

    tickers = list(_iter_fetch_targets(_read_tickers(universe_csv, args.ticker_col)))
    if args.limit > 0:
        tickers = tickers[: args.limit]
    if not tickers:
        raise RuntimeError(f"No ETF tickers found in {universe_csv}")

    store = PriceStore(db_path=db_path)
    total_saved = 0
    skipped = 0
    empty = 0

    print(f"[INFO] universe_csv={universe_csv}")
    print(f"[INFO] db={db_path}")
    print(f"[INFO] tickers={len(tickers)}, range={start}~{end}")
    print(f"[INFO] force_window={bool(args.force_window)}")

    for idx, ticker in enumerate(tickers, start=1):
        fetch_start = _compute_fetch_start(store, ticker, start, bool(args.force_window))
        if fetch_start > end:
            skipped += 1
            print(f"[SKIP] ({idx}/{len(tickers)}) {ticker} already up to date")
            continue

        for attempt in range(1, args.retries + 1):
            try:
                df, source = fetch_etf_ohlcv(ticker, fetch_start, end)
                if df.empty:
                    empty += 1
                    print(f"[EMPTY] ({idx}/{len(tickers)}) {ticker} {fetch_start}~{end}")
                    break
                saved = store.upsert_prices(ticker, df, source=source)
                total_saved += saved
                print(f"[OK] ({idx}/{len(tickers)}) {ticker} saved={saved} source={source}")
                break
            except Exception as exc:
                if attempt == args.retries:
                    print(f"[FAIL] ({idx}/{len(tickers)}) {ticker}: {exc}", file=sys.stderr)
                else:
                    time.sleep(max(1.0, args.sleep * attempt))
        time.sleep(max(0.0, args.sleep))

    print(
        f"[DONE] tickers={len(tickers)} saved_rows={total_saved} "
        f"skipped={skipped} empty={empty}"
    )


if __name__ == "__main__":
    main()
