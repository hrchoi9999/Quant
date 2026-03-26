# build_universe_top200_monthly.py ver 2025-12-30_001
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def _find_project_root(start_path: Path) -> Path:
    for p in [start_path] + list(start_path.parents):
        if (p / "src").exists() and (p / "modules").exists():
            return p
    return start_path


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_get_market_cap(date_yyyymmdd: str, market: str):
    from pykrx import stock

    dt = datetime.strptime(date_yyyymmdd, "%Y%m%d")
    last_err = None
    for _ in range(15):  # 최대 15일 전까지 후퇴
        d = dt.strftime("%Y%m%d")
        try:
            cap = stock.get_market_cap(d, market=market)
            if cap is not None and len(cap) > 0:
                return d, cap
        except Exception as e:
            last_err = e
        dt = dt - timedelta(days=1)
    raise RuntimeError(f"get_market_cap 실패: start={date_yyyymmdd}, market={market}, last_err={last_err}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", type=str, default="KOSPI", help="KOSPI|KOSDAQ|KONEX")
    ap.add_argument("--topn", type=int, default=200, help="시총 상위 N")
    ap.add_argument("--start", type=str, default="2015-01-01", help="YYYY-MM-DD")
    ap.add_argument("--end", type=str, default="", help="YYYY-MM-DD (비우면 오늘)")
    args = ap.parse_args()

    start_dt = pd.to_datetime(args.start)
    end_dt = pd.to_datetime(args.end) if args.end else pd.Timestamp.today().normalize()

    # 월말(달력) 시퀀스
    month_ends = pd.date_range(start=start_dt, end=end_dt, freq="ME")

    root = _find_project_root(Path(__file__).resolve().parent)
    out_dir = root / "data" / "universe"
    cache_dir = root / "data" / "cache" / "mcap"
    _ensure_dir(out_dir)
    _ensure_dir(cache_dir)

    all_rows = []
    union = set()

    for me in month_ends:
        me_str = me.strftime("%Y%m%d")
        cache_pq = cache_dir / f"mcap_{args.market.lower()}_{me_str}.parquet"

        if cache_pq.exists():
            cap = pd.read_parquet(cache_pq)
            used = me_str
        else:
            used, cap = _safe_get_market_cap(me_str, market=args.market)
            cap = cap.reset_index()

            # ticker 컬럼 정리
            ticker_col = cap.columns[0]
            cap = cap.rename(columns={ticker_col: "ticker"})
            cap["ticker"] = cap["ticker"].astype(str).str.zfill(6)

            # 시가총액 컬럼 찾기
            mcap_col = None
            for c in cap.columns:
                if "시가총액" in str(c):
                    mcap_col = c
                    break
            if mcap_col is None:
                raise RuntimeError(f"시가총액 컬럼을 찾지 못했습니다. columns={list(cap.columns)}")

            cap = cap[cap["ticker"].str.match(r"^\d{6}$", na=False)].copy()
            cap = cap.sort_values(mcap_col, ascending=False).head(args.topn).copy()
            cap.to_parquet(cache_pq, index=False)

        # 종목명 붙이기(캐시엔 종목명이 없을 수 있어서 매번 보강)
        from pykrx import stock
        cap["name"] = cap["ticker"].apply(lambda t: stock.get_market_ticker_name(t))

        cap["asof"] = me_str
        cap["used_date"] = used

        all_rows.append(cap[["asof", "used_date", "ticker", "name"]])
        union.update(cap["ticker"].tolist())

        print(f"[OK] {me_str} (used={used}) top{args.topn} -> union={len(union)}")

    df_all = pd.concat(all_rows, ignore_index=True).drop_duplicates(subset=["asof", "ticker"])
    df_union = pd.DataFrame({"ticker": sorted(list(union))})

    tag = f"{args.market.lower()}_top{args.topn}_{month_ends[0].strftime('%Y%m')}_{month_ends[-1].strftime('%Y%m')}"
    out_all = out_dir / f"universe_monthly_{tag}.csv"
    out_union = out_dir / f"universe_union_{tag}.csv"

    df_all.to_csv(out_all, index=False, encoding="utf-8-sig")
    df_union.to_csv(out_union, index=False, encoding="utf-8-sig")

    print(f"[DONE] monthly saved: {out_all} (rows={len(df_all)})")
    print(f"[DONE] union  saved: {out_union} (tickers={len(df_union)})")


if __name__ == "__main__":
    main()
