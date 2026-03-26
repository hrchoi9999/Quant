# price_update_top200_daily.py ver 2026-01-27_004
r"""
Top200 데일리 업데이트 전용 실행기 (Active 필터 내장: pykrx → CSV → DB lag fallback)

변경(중요)
- DB fallback을 "최근 N일 내 거래"에서 "end 대비 최대 지연일(max_lag_days)" 기준으로 변경
  예) end=2026-01-27, max_lag_days=7 이면 max_date < 2026-01-20 인 티커는 inactive로 제외

운영 옵션(추천)
- --db-max-lag-days 7                 : DB lag 기준 (기본 7)
- --exclude-from-inactive-log         : 과거 inactive/empty 로그에 기록된 티커는 다음 실행부터 제외
- --quarantine-empty                  : 이번 실행에서 EMPTY 발생 티커를 inactive_log에 추가 기록(격리)

실행 예:
  cd D:\Quant
  python src\collectors\price\price_update_top200_daily.py --db D:\Quant\data\db\price.db

  python src\collectors\price\price_update_top200_daily.py ^
    --universe-file D:\Quant\data\universe\universe_top200_kospi_20251230_clean.csv ^
    --db D:\Quant\data\db\price.db ^
    --db-max-lag-days 7 ^
    --exclude-from-inactive-log ^
    --quarantine-empty
"""

from __future__ import annotations

import argparse
import re
import sys
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple, Set

import pandas as pd

from price_store import PriceStore
from price_backfill import fetch_ohlcv_pykrx


# --------------------------
# Helpers
# --------------------------
def _parse_ymd(s: str) -> date:
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.strptime(s, "%Y%m%d").date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def _normalize_ticker(x: str) -> str:
    s = str(x).strip()
    s = re.sub(r"\.0$", "", s)
    if re.fullmatch(r"\d{1,6}", s):
        return s.zfill(6)
    return s


def _read_tickers_from_csv(path: Path, col: str = "ticker") -> List[str]:
    df = pd.read_csv(path, dtype={col: "string"})
    if col not in df.columns:
        raise ValueError(f"CSV에 '{col}' 컬럼이 없습니다. columns={list(df.columns)}")

    tickers = df[col].map(_normalize_ticker).tolist()

    # 6자리 숫자만(특수코드 제거)
    tickers = [t for t in tickers if re.fullmatch(r"\d{6}", t)]

    # 중복 제거(순서 유지)
    seen = set()
    uniq = []
    for t in tickers:
        if t not in seen:
            uniq.append(t)
            seen.add(t)
    return uniq


def _infer_recent_trading_day(ref_ticker: str, today: date, lookback_days: int = 10) -> date:
    """
    ref_ticker로 최근 거래일을 "대략" 추정.
    (pykrx가 특정일에 빈 결과를 주는 경우가 있어, lookback_days 범위에서 유효 응답이 오는 날짜를 end로 사용)
    """
    ref_ticker = ref_ticker.strip().zfill(6)
    for k in range(0, lookback_days):
        cand = today - timedelta(days=k)
        start = cand - timedelta(days=7)
        try:
            df = fetch_ohlcv_pykrx(ref_ticker, start, cand)
            if df is not None and len(df) > 0:
                return cand
        except Exception:
            pass
    return today


def _find_latest_top200_file(universe_dir: Path) -> Path:
    pat = re.compile(r"^universe_top200_kospi_(\d{8})_clean\.csv$", re.IGNORECASE)
    candidates = []
    for p in universe_dir.glob("universe_top200_kospi_*_clean.csv"):
        m = pat.match(p.name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y%m%d").date()
        candidates.append((d, p))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    pat2 = re.compile(r"^universe_top200_kospi_(\d{8})\.csv$", re.IGNORECASE)
    candidates = []
    for p in universe_dir.glob("universe_top200_kospi_*.csv"):
        m = pat2.match(p.name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y%m%d").date()
        candidates.append((d, p))
    if not candidates:
        raise FileNotFoundError(f"{universe_dir} 아래에 universe_top200_kospi_YYYYMMDD(_clean).csv 파일이 없습니다.")
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# --------------------------
# Active ticker sources
# --------------------------
def _get_active_tickers_pykrx() -> Set[str]:
    """
    실행 시점의 '현재 상장' 티커 목록(6자리).
    """
    try:
        from pykrx import stock
    except Exception as e:
        raise RuntimeError(f"pykrx import 실패: {e}")

    active = set()
    for market in ["KOSPI", "KOSDAQ"]:
        lst = stock.get_market_ticker_list(market=market)
        for t in lst:
            t2 = _normalize_ticker(t)
            if re.fullmatch(r"\d{6}", t2):
                active.add(t2)
    return active


def _get_active_tickers_from_master_csv(path: Path, ticker_col: str = "ticker") -> Set[str]:
    df = pd.read_csv(path, dtype={ticker_col: "string"})
    if ticker_col not in df.columns:
        raise ValueError(f"KRX master에 '{ticker_col}' 컬럼이 없습니다. columns={list(df.columns)}")
    s = df[ticker_col].map(_normalize_ticker)
    s = s[s.str.match(r"^\d{6}$", na=False)]
    return set(s.tolist())


def _get_active_tickers_from_db_lag(db_path: Path, tickers: List[str], end: date, max_lag_days: int = 7) -> Set[str]:
    """
    DB 기준 active 판정 (운영용 fallback):
      active = (MAX(date) >= end - max_lag_days)

    - 상폐/코드종료/거래정지/데이터 미제공 등으로 최신이 끊긴 종목을 자동 제외하기 위한 목적.
    - prices_daily(ticker, date, ...) 가정.
    """
    if not tickers:
        return set()

    cutoff = end - timedelta(days=int(max_lag_days))

    con = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join(["?"] * len(tickers))
        q = f"""
        SELECT ticker, MAX(date) AS max_date
        FROM prices_daily
        WHERE ticker IN ({placeholders})
        GROUP BY ticker
        """
        df = pd.read_sql_query(q, con, params=tickers)
    finally:
        con.close()

    if df is None or len(df) == 0:
        return set()

    df["max_date"] = pd.to_datetime(df["max_date"], errors="coerce")
    active = set(df.loc[df["max_date"] >= pd.Timestamp(cutoff), "ticker"].tolist())
    return active


def _load_tickers_from_log(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if re.fullmatch(r"\d{6}", t):
            out.add(t)
    return out


# --------------------------
# Update logic
# --------------------------
def _compute_start_end(store: PriceStore, ticker: str, end: date) -> Optional[Tuple[date, date]]:
    last = store.get_last_date(ticker)
    if last is None:
        # 데일리 업데이트는 '없는 종목 신규 백필' 목적이 아님 → 스킵
        return None
    start = last + timedelta(days=1)
    if start > end:
        return None
    return start, end


def update_one(
    store: PriceStore,
    ticker: str,
    end: date,
    sleep_sec: float,
    retries: int,
    fail_on_empty: bool = False,
) -> Tuple[int, str]:
    """
    Returns: (saved_rows, status)
    status: UPDATED | SKIP | EMPTY | FAIL
    """
    ticker = ticker.strip().zfill(6)
    se = _compute_start_end(store, ticker, end)
    if se is None:
        return 0, "SKIP"
    start, end = se

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            df = fetch_ohlcv_pykrx(ticker, start, end)
            if df is None or len(df) == 0:
                if fail_on_empty:
                    return 0, "FAIL"
                return 0, "EMPTY"
            n = store.upsert_prices(ticker, df, source="pykrx")
            return int(n), "UPDATED"
        except Exception as e:
            last_err = e
            if attempt == retries:
                print(f"[FAIL] {ticker}: {e}", file=sys.stderr)
                return 0, "FAIL"
            backoff = (2 ** (attempt - 1)) * 0.5
            time.sleep(max(1.0, sleep_sec + backoff))

    if last_err:
        print(f"[FAIL] {ticker}: {last_err}", file=sys.stderr)
    return 0, "FAIL"


def main() -> None:
    ap = argparse.ArgumentParser()

    ap.add_argument("--universe-file", type=str, default="", help="Top200 유니버스 파일(미지정 시 최신 파일 자동 선택)")
    ap.add_argument("--ticker-col", type=str, default="ticker", help="유니버스 CSV 종목코드 컬럼명")

    ap.add_argument("--end", type=str, default="", help="종료일 강제(YYYYMMDD 또는 YYYY-MM-DD). 미지정 시 최근 거래일 자동")
    ap.add_argument("--ref-ticker", type=str, default="005930", help="최근 거래일 추정 기준 종목")

    ap.add_argument("--sleep", type=float, default=0.2, help="요청 간 sleep(초)")
    ap.add_argument("--retries", type=int, default=3, help="종목별 재시도 횟수")

    ap.add_argument("--db", type=str, default="", help="price.db 경로(미지정 시 PriceStore 기본 경로)")
    ap.add_argument("--fail-on-empty", action="store_true", help="EMPTY를 FAIL로 처리(기본은 EMPTY)")

    # Active 필터 옵션
    ap.add_argument("--no-active-filter", action="store_true", help="현재 상장(active) 필터링을 끔(기본은 켜짐)")
    ap.add_argument("--krx-master-file", type=str, default="", help="active 목록 fallback용 KRX master CSV 경로")
    ap.add_argument("--krx-master-ticker-col", type=str, default="ticker", help="KRX master CSV의 종목코드 컬럼명")

    # DB fallback 기준(핵심)
    ap.add_argument("--db-max-lag-days", type=int, default=7, help="DB fallback: end 대비 max_date 허용 지연일(기본 7)")

    # 운영 편의
    ap.add_argument("--exclude-from-inactive-log", action="store_true", help="inactive_log/empty_log 기록 티커를 다음 실행부터 자동 제외")
    ap.add_argument("--quarantine-empty", action="store_true", help="이번 실행에서 EMPTY 발생 티커를 inactive_log에 추가 기록(격리)")

    args = ap.parse_args()

    # 프로젝트 루트: .../src/collectors/price/ 이므로 parents[3]가 D:\Quant
    project_root = Path(__file__).resolve().parents[3]
    universe_dir = project_root / "data" / "universe"
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if args.end.strip():
        end = _parse_ymd(args.end)
    else:
        end = _infer_recent_trading_day(args.ref_ticker, date.today(), lookback_days=10)

    if args.universe_file.strip():
        univ_path = Path(args.universe_file)
        if not univ_path.is_absolute():
            univ_path = (project_root / univ_path).resolve()
    else:
        univ_path = _find_latest_top200_file(universe_dir)

    tickers = _read_tickers_from_csv(univ_path, args.ticker_col)

    store = PriceStore(db_path=Path(args.db)) if args.db else PriceStore()

    fail_log = logs_dir / f"price_update_top200_fail_{end.strftime('%Y%m%d')}.txt"
    empty_log = logs_dir / f"price_update_top200_empty_{end.strftime('%Y%m%d')}.txt"
    inactive_log = logs_dir / f"price_update_top200_inactive_{end.strftime('%Y%m%d')}.txt"

    print(f"[INFO] project_root={project_root}")
    print(f"[INFO] DB={store.db_path}")
    print(f"[INFO] universe={univ_path} (tickers={len(tickers)})")
    print(f"[INFO] end={end}")
    print(f"[INFO] fail_log={fail_log}")
    print(f"[INFO] empty_log={empty_log}")
    print(f"[INFO] inactive_log={inactive_log}")

    # (선택) 과거 inactive/empty 로그 티커는 미리 제외
    if args.exclude_from_inactive_log:
        prior_inactive = _load_tickers_from_log(inactive_log)
        prior_empty = _load_tickers_from_log(empty_log)
        prior = prior_inactive | prior_empty
        if prior:
            before = len(tickers)
            tickers = [t for t in tickers if t not in prior]
            print(f"[INFO] exclude-from-log: removed={before-len(tickers)}, remain={len(tickers)}")

    # === Active 필터 적용(기본 ON) ===
    if not args.no_active_filter:
        active = None

        # 1) pykrx로 현재 상장 목록 시도
        try:
            active = _get_active_tickers_pykrx()
            print(f"[INFO] active source=pykrx (active_tickers={len(active)})")
        except Exception as e:
            print(f"[WARN] active_tickers(pykrx) 실패: {e}")

        # 2) 실패 시 CSV fallback
        if (active is None or len(active) == 0) and args.krx_master_file.strip():
            mp = Path(args.krx_master_file)
            if not mp.is_absolute():
                mp = (project_root / mp).resolve()
            try:
                active = _get_active_tickers_from_master_csv(mp, args.krx_master_ticker_col)
                print(f"[INFO] active source=csv ({mp}) (active_tickers={len(active)})")
            except Exception as e:
                print(f"[WARN] active_tickers(csv) 실패: {e}")

        # 3) 마지막 fallback: DB lag 기준 (핵심)
        if (active is None or len(active) == 0):
            try:
                active = _get_active_tickers_from_db_lag(store.db_path, tickers, end, max_lag_days=int(args.db_max_lag_days))
                print(f"[INFO] active source=db_lag({args.db_max_lag_days}d) (active_tickers={len(active)})")
            except Exception as e:
                print(f"[WARN] active_tickers(db_lag) 실패: {e}")

        if active is not None and len(active) > 0:
            before_list = tickers
            tickers = [t for t in tickers if t in active]
            inactive = [t for t in before_list if t not in active]
            print(f"[INFO] active-filter applied: before={len(before_list)}, after={len(tickers)}, inactive={len(inactive)}")
            if inactive:
                with open(inactive_log, "w", encoding="utf-8") as f:
                    f.write("\n".join(inactive) + "\n")
        else:
            print("[WARN] active-filter를 적용하지 못했습니다(활성 티커 목록 확보 실패). 유니버스 그대로 진행합니다.")

    total_saved = 0
    cnt_updated = cnt_skip = cnt_empty = cnt_fail = 0
    failed: List[str] = []
    empties: List[str] = []
    quarantined: List[str] = []

    for i, t in enumerate(tickers, start=1):
        n, st = update_one(
            store=store,
            ticker=t,
            end=end,
            sleep_sec=args.sleep,
            retries=args.retries,
            fail_on_empty=bool(args.fail_on_empty),
        )
        total_saved += n

        if st == "UPDATED":
            cnt_updated += 1
        elif st == "SKIP":
            cnt_skip += 1
        elif st == "EMPTY":
            cnt_empty += 1
            empties.append(t.zfill(6))
            if args.quarantine_empty:
                quarantined.append(t.zfill(6))
        else:
            cnt_fail += 1
            failed.append(t.zfill(6))

        print(f"  - ({i}/{len(tickers)}) {t.zfill(6)}: status={st}, saved={n}")
        time.sleep(max(0.0, args.sleep))

    if failed:
        with open(fail_log, "w", encoding="utf-8") as f:
            f.write("\n".join(failed) + "\n")

    if empties:
        with open(empty_log, "w", encoding="utf-8") as f:
            f.write("\n".join(empties) + "\n")

    # EMPTY 격리: inactive_log에 append (기존 내용 유지)
    if quarantined:
        existing = _load_tickers_from_log(inactive_log)
        merged = list(sorted(existing | set(quarantined)))
        with open(inactive_log, "w", encoding="utf-8") as f:
            f.write("\n".join(merged) + "\n")
        print(f"[INFO] quarantined EMPTY tickers appended to inactive_log: {len(quarantined)}")

    print(f"[DONE] total_saved_rows={total_saved}, updated={cnt_updated}, skip={cnt_skip}, empty={cnt_empty}, fail={cnt_fail}")


if __name__ == "__main__":
    main()
