# price_update_daily.py ver 2026-01-27_001
"""
매일 증분 업데이트(마지막 저장일 + 1 ~ end)만 수집해서 저장합니다.

권장 운영
1) (1회/수시) union 619개 갭 복구/백필:
   python price_update_daily.py --tickers-file data\\universe_union_kospi_top200_201501_202512.csv --start 2013-01-01

2) (매일) top200 업데이트:
   python price_update_daily.py --tickers-file data\\universe_top200_kospi_20251230.csv

주의:
- 인자 없이 실행하면 종료합니다(과거처럼 005930만 업데이트되는 사고 방지).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from price_store import PriceStore
from price_backfill import fetch_ohlcv_pykrx


# -----------------------------
# helpers
# -----------------------------
def _parse_ymd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _read_tickers_from_csv(path: Path, col: str) -> List[str]:
    df = pd.read_csv(path)
    if col not in df.columns:
        raise ValueError(f"CSV에 '{col}' 컬럼이 없습니다. columns={list(df.columns)}")
    tickers = (
        df[col]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .tolist()
    )
    tickers = [t.zfill(6) for t in tickers if t and t != "nan"]
    # 중복 제거(순서 유지)
    seen = set()
    uniq = []
    for t in tickers:
        if t not in seen:
            uniq.append(t)
            seen.add(t)
    return uniq


def _ensure_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _infer_recent_trading_day(
    ref_ticker: str,
    today: date,
    lookback_days: int = 10,
) -> date:
    """
    end를 '오늘'로 잡았는데 비거래일/데이터 공백이면 빈 DF가 나올 수 있습니다.
    ref_ticker로 최근 lookback_days 안에서 데이터가 존재하는 가장 최근 날짜를 찾아 end로 사용합니다.
    """
    for k in range(0, lookback_days):
        cand = today - timedelta(days=k)
        start = cand - timedelta(days=7)  # 여유
        try:
            df = fetch_ohlcv_pykrx(ref_ticker, start, cand)
            if df is not None and len(df) > 0:
                return cand
        except Exception:
            # 인증/서버 문제 등으로 ref 조회가 깨질 수도 있음 -> 상위에서 처리
            pass
    return today  # 최후 fallback


def _safe_len(df: Optional[pd.DataFrame]) -> int:
    try:
        return 0 if df is None else int(len(df))
    except Exception:
        return 0


# -----------------------------
# core
# -----------------------------
def _compute_start_end(
    store: PriceStore,
    ticker: str,
    end: date,
    start_override: Optional[date],
    backfill_if_missing: bool,
) -> Tuple[Optional[date], date]:
    """
    - 기본: last+1 ~ end
    - DB에 없으면:
        - backfill_if_missing=True  -> start_override가 있으면 그때부터, 없으면 end(=하루치)
        - backfill_if_missing=False -> None 반환(스킵)
    - start_override가 있으면 last+1과 max()로 갭 복구/강제 시작점 지원
    """
    last = store.get_last_date(ticker)

    if last is None:
        if not backfill_if_missing:
            return None, end
        if start_override is not None:
            return start_override, end
        return end, end  # 기본은 하루만
    else:
        start = last + timedelta(days=1)
        if start_override is not None:
            start = max(start, start_override)
        return start, end


def update_one(
    store: PriceStore,
    ticker: str,
    end: date,
    start_override: Optional[date],
    sleep_sec: float,
    retries: int,
    backfill_if_missing: bool,
    fail_on_empty: bool,
) -> Tuple[int, str]:
    """
    Returns:
      (saved_rows, status)
      status: "UPDATED" | "SKIP" | "EMPTY" | "FAIL"
    """
    ticker = ticker.strip().zfill(6)

    start_end = _compute_start_end(
        store=store,
        ticker=ticker,
        end=end,
        start_override=start_override,
        backfill_if_missing=backfill_if_missing,
    )
    start, end = start_end

    if start is None:
        return 0, "SKIP"
    if start > end:
        return 0, "SKIP"

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            df = fetch_ohlcv_pykrx(ticker, start, end)
            if _safe_len(df) == 0:
                # 비거래일 범위/데이터 공백/조회 실패(빈 결과) 등
                if fail_on_empty:
                    return 0, "FAIL"
                return 0, "EMPTY"

            n = store.upsert_prices(ticker, df, source="pykrx")
            return int(n), "UPDATED"

        except Exception as e:
            last_err = e
            if attempt == retries:
                print(f"[FAIL] {ticker} update failed: {e}", file=sys.stderr)
                return 0, "FAIL"
            # 지수 백오프(0.5, 1, 2... + 기본 sleep)
            backoff = (2 ** (attempt - 1)) * 0.5
            time.sleep(max(1.0, sleep_sec + backoff))

    if last_err:
        print(f"[FAIL] {ticker} update failed: {last_err}", file=sys.stderr)
    return 0, "FAIL"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=str, default="", help="예: 005930,000660 (콤마 구분)")
    ap.add_argument("--tickers-file", type=str, default="", help="유니버스 CSV 경로")
    ap.add_argument("--ticker-col", type=str, default="ticker", help="CSV의 종목코드 컬럼명")
    ap.add_argument("--start", type=str, default="", help="강제 시작일(YYYYMMDD 또는 YYYY-MM-DD). 예: 20251231")
    ap.add_argument("--end", type=str, default="", help="종료일(미지정 시 최근 거래일 자동 추정)")
    ap.add_argument("--ref-ticker", type=str, default="005930", help="최근 거래일 추정용 기준 종목")
    ap.add_argument("--sleep", type=float, default=0.2, help="요청 간 sleep(초)")
    ap.add_argument("--retries", type=int, default=3, help="종목별 재시도 횟수")
    ap.add_argument("--db", type=str, default="", help="price.db 경로(미지정 시 PriceStore 기본 경로)")
    ap.add_argument("--fail-log", type=str, default="", help="실패 티커 로그 파일 경로(미지정 시 logs 자동)")
    ap.add_argument(
        "--backfill-if-missing",
        action="store_true",
        help="DB에 티커가 없을 때도 수집(기본은 스킵). --start와 함께 쓰면 백필 가능",
    )
    ap.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="조회 결과가 빈 DF이면 FAIL 처리(기본은 EMPTY 처리).",
    )
    args = ap.parse_args()

    # tickers 입력 검증(인자 없이 실행 방지)
    if not args.tickers_file and not args.tickers.strip():
        raise SystemExit(
            "ERROR: --tickers-file 또는 --tickers 를 지정해 주세요. "
            "인자 없이 실행하면 전체 업데이트가 되지 않습니다."
        )

    start_override = _parse_ymd(args.start) if args.start.strip() else None

    # end 자동 추정(최근 거래일)
    if args.end.strip():
        end = _parse_ymd(args.end)
    else:
        today = date.today()
        end_guess = _infer_recent_trading_day(args.ref_ticker.strip().zfill(6), today, lookback_days=10)
        end = end_guess

    db_path = Path(args.db) if args.db else None
    store = PriceStore(db_path=db_path) if db_path else PriceStore()

    if args.tickers_file:
        tickers = _read_tickers_from_csv(Path(args.tickers_file), args.ticker_col)
    else:
        tickers = [t.strip().zfill(6) for t in args.tickers.split(",") if t.strip()]

    if not tickers:
        raise ValueError("tickers가 비어 있습니다.")

    # fail log path
    if args.fail_log:
        fail_log_path = Path(args.fail_log)
    else:
        # 프로젝트 루트에서 실행한다고 가정하고 logs 폴더에 저장
        fail_log_path = Path("logs") / f"price_update_fail_{end.strftime('%Y%m%d')}.txt"
    _ensure_dir(fail_log_path)

    print(f"[INFO] DB: {store.db_path}")
    print(f"[INFO] tickers={len(tickers)}")
    print(f"[INFO] start_override={start_override} (None이면 종목별 last+1)")
    print(f"[INFO] end={end} (최근 거래일 자동 추정 가능)")
    print(f"[INFO] fail_log={fail_log_path}")

    total_saved = 0
    cnt_updated = 0
    cnt_skip = 0
    cnt_empty = 0
    cnt_fail = 0
    failed = []

    for i, ticker in enumerate(tickers, start=1):
        n, status = update_one(
            store,
            ticker,
            end=end,
            start_override=start_override,
            sleep_sec=args.sleep,
            retries=args.retries,
            backfill_if_missing=bool(args.backfill_if_missing),
            fail_on_empty=bool(args.fail_on_empty),
        )

        total_saved += n
        if status == "UPDATED":
            cnt_updated += 1
        elif status == "SKIP":
            cnt_skip += 1
        elif status == "EMPTY":
            cnt_empty += 1
        else:
            cnt_fail += 1
            failed.append(ticker)

        print(f"  - ({i}/{len(tickers)}) {ticker}: status={status}, saved={n}")
        time.sleep(max(0.0, args.sleep))

    # 실패 목록 저장
    if failed:
        with open(fail_log_path, "w", encoding="utf-8") as f:
            for t in failed:
                f.write(f"{t}\n")

    print(
        "[DONE] "
        f"total_saved_rows={total_saved}, "
        f"updated={cnt_updated}, skip={cnt_skip}, empty={cnt_empty}, fail={cnt_fail}"
    )
    if failed:
        print(f"[WARN] failed_tickers={len(failed)} -> {fail_log_path}")


if __name__ == "__main__":
    main()
