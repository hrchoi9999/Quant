# build_universe_mix_top250.py ver 2026-02-05_001
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def _load_universe(path: str, ticker_col: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={ticker_col: str})
    if ticker_col not in df.columns:
        raise ValueError(f"ticker_col '{ticker_col}' not found in {path}")
    df[ticker_col] = (
        df[ticker_col].astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(6)
    )
    return df


def _has_any_price_pykrx(ticker: str, asof_ymd: str, lookback_days: int = 30) -> bool:
    from pykrx import stock
    end = datetime.strptime(asof_ymd, "%Y%m%d").date()
    start = end - timedelta(days=lookback_days)
    df = stock.get_market_ohlcv_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker)
    return df is not None and not df.empty


def _filter_valid_prices(df: pd.DataFrame, ticker_col: str, asof: str, lookback_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    asof_ymd = asof.replace("-", "")
    ok, bad = [], []
    for _, r in df.iterrows():
        t = str(r[ticker_col]).zfill(6)
        if _has_any_price_pykrx(t, asof_ymd, lookback_days):
            ok.append(r)
        else:
            bad.append(r)
    return pd.DataFrame(ok), pd.DataFrame(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kospi-file", required=True)
    ap.add_argument("--kosdaq-file", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--target-size", type=int, default=250)
    ap.add_argument("--keep-kospi-all", action="store_true", default=True)
    ap.add_argument("--out-file", required=True)

    # NEW
    ap.add_argument("--asof", default="", help="YYYY-MM-DD (비우면 kosdaq-file의 asof를 우선 사용)")
    ap.add_argument("--lookback-days", type=int, default=30)
    ap.add_argument("--save-dropped", action="store_true")
    args = ap.parse_args()

    kospi = _load_universe(args.kospi_file, args.ticker_col).copy()
    kosdaq = _load_universe(args.kosdaq_file, args.ticker_col).copy()

    kospi["market"] = kospi.get("market", "KOSPI")
    kosdaq["market"] = kosdaq.get("market", "KOSDAQ")

    # asof 결정
    asof = args.asof.strip()
    if not asof:
        if "asof" in kosdaq.columns and kosdaq["asof"].notna().any():
            asof = str(kosdaq["asof"].dropna().iloc[0])
        else:
            asof = datetime.today().strftime("%Y-%m-%d")

    # KOSPI는 전량 유지
    if args.keep_kospi_all:
        kospi_keep = kospi
        remain = max(0, args.target_size - len(kospi_keep))
        kosdaq_keep = kosdaq.head(remain)
    else:
        half = args.target_size // 2
        kospi_keep = kospi.head(half)
        kosdaq_keep = kosdaq.head(args.target_size - len(kospi_keep))

    mix = pd.concat([kospi_keep, kosdaq_keep], ignore_index=True)

    # 중복 제거(KOSPI 우선)
    mix["_prio"] = mix["market"].map({"KOSPI": 0, "KOSDAQ": 1}).fillna(9)
    mix = (
        mix.sort_values(["_prio", args.ticker_col])
           .drop_duplicates(subset=[args.ticker_col], keep="first")
           .drop(columns=["_prio"])
           .reset_index(drop=True)
    )

    # NEW: 가격 유효성 필터(특히 KOSDAQ 쪽)
    # (KOSPI는 기본적으로 가격 유효할 확률이 높지만, 동일하게 적용해도 무방)
    mix_ok, mix_bad = _filter_valid_prices(mix, args.ticker_col, asof=asof, lookback_days=args.lookback_days)

    # target-size 보정 (부족하면 kosdaq에서 추가로 채움)
    if len(mix_ok) < args.target_size and args.keep_kospi_all:
        need = args.target_size - len(mix_ok)
        already = set(mix_ok[args.ticker_col].astype(str).str.zfill(6))

        # kosdaq 후보 중에서 아직 안 넣은 것 + 가격 유효한 것만 추가
        candidates = kosdaq[~kosdaq[args.ticker_col].astype(str).str.zfill(6).isin(already)].copy()
        # 후보에서도 가격 유효성 필터
        cand_ok, cand_bad = _filter_valid_prices(candidates, args.ticker_col, asof=asof, lookback_days=args.lookback_days)

        add = cand_ok.head(need)
        mix_ok = pd.concat([mix_ok, add], ignore_index=True)

        # bad에 합치기(리포트용)
        if len(cand_bad) > 0:
            mix_bad = pd.concat([mix_bad, cand_bad], ignore_index=True)

    Path(args.out_file).parent.mkdir(parents=True, exist_ok=True)
    mix_ok.to_csv(args.out_file, index=False, encoding="utf-8-sig")

    print(f"[INFO] kospi_in={len(kospi)} kosdaq_in={len(kosdaq)}")
    print(f"[INFO] mix_out={len(mix_ok)} target={args.target_size} asof={asof}")
    print("[INFO] mix market counts:")
    if "market" in mix_ok.columns:
        print(mix_ok["market"].value_counts(dropna=False).to_string())

    if args.save_dropped and len(mix_bad) > 0:
        drop_path = Path(args.out_file).with_name(Path(args.out_file).stem + "_dropped_invalid_price.csv")
        mix_bad.to_csv(drop_path, index=False, encoding="utf-8-sig")
        print(f"[INFO] dropped saved -> {drop_path} | rows={len(mix_bad)}")


if __name__ == "__main__":
    main()
