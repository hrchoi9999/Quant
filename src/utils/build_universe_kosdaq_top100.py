# build_universe_kosdaq_top100.py ver 2026-02-05_001
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def _has_any_price_pykrx(ticker: str, asof_ymd: str, lookback_days: int = 30) -> bool:
    """
    asof_ymd(YYYYMMDD) 기준 lookback_days 동안 OHLCV가 한 건이라도 있으면 True
    """
    from pykrx import stock

    end = datetime.strptime(asof_ymd, "%Y%m%d").date()
    start = end - timedelta(days=lookback_days)

    df = stock.get_market_ohlcv_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker)
    return df is not None and not df.empty


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (e.g., 2026-02-05)")
    ap.add_argument("--topn", type=int, default=100)
    ap.add_argument("--out", required=True)

    # NEW
    ap.add_argument("--candidate-mult", type=float, default=1.8, help="후보 풀 배수(필터링 대비)")
    ap.add_argument("--lookback-days", type=int, default=30, help="가격 유효성 검증 lookback")
    ap.add_argument("--save-dropped", action="store_true", help="드랍 티커 리포트 저장")
    args = ap.parse_args()

    from pykrx import stock

    dt = args.date.replace("-", "")  # YYYYMMDD

    df = stock.get_market_cap_by_ticker(dt, market="KOSDAQ")
    if df is None or len(df) == 0:
        raise RuntimeError("pykrx returned empty market cap data. Check date / network.")

    # 시총 컬럼 찾기
    mcap_col = None
    for cand in ["시가총액", "Market Cap", "market_cap", "시총"]:
        if cand in df.columns:
            mcap_col = cand
            break
    if mcap_col is None:
        mcap_col = df.columns[0]

    # 후보는 topn보다 넉넉히
    cand_n = max(args.topn, int(args.topn * args.candidate_mult))
    df = df.sort_values(mcap_col, ascending=False).head(cand_n).copy()

    # index(티커) -> 컬럼
    df = df.reset_index()
    first_col = df.columns[0]
    df = df.rename(columns={first_col: "ticker"})

    df["ticker"] = df["ticker"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6)
    df["asof"] = args.date
    df["market"] = "KOSDAQ"
    df = df[["ticker", "market", "asof", mcap_col]].rename(columns={mcap_col: "mcap"}).copy()

    # 1) 가격 유효성 필터
    ok_rows = []
    dropped_rows = []

    for _, r in df.iterrows():
        t = r["ticker"]
        if _has_any_price_pykrx(t, dt, lookback_days=args.lookback_days):
            ok_rows.append(r)
        else:
            dropped_rows.append(r)

    ok = pd.DataFrame(ok_rows)

    # 2) topn 맞추기 (후보 풀 안에서 계속 채우는 구조라, ok가 topn보다 작으면 cand_n을 올려야 함)
    if len(ok) < args.topn:
        # 후보가 부족한 경우를 명확히 에러로 올림 (원인을 알 수 있게)
        # 필요하면 candidate-mult를 더 키우면 됩니다.
        raise RuntimeError(
            f"KOSDAQ universe not enough after price validation: "
            f"ok={len(ok)} < topn={args.topn}. "
            f"Try increase --candidate-mult or --lookback-days."
        )

    ok = ok.head(args.topn).copy()

    # 종목명 붙이기(품질 개선)
    try:
        ok["name"] = ok["ticker"].apply(lambda t: stock.get_market_ticker_name(t))
    except Exception:
        ok["name"] = ""

    out = ok[["ticker", "name", "market", "mcap", "asof"]].copy()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"[DONE] saved -> {args.out} | rows={len(out)} | date={args.date}")

    if args.save_dropped and dropped_rows:
        drop_path = Path(args.out).with_name(Path(args.out).stem + "_dropped_invalid_price.csv")
        pd.DataFrame(dropped_rows).to_csv(drop_path, index=False, encoding="utf-8-sig")
        print(f"[INFO] dropped saved -> {drop_path} | rows={len(dropped_rows)}")


if __name__ == "__main__":
    main()
