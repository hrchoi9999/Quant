# build_universe_mix_200_200.py ver 2026-02-05_001
import argparse
from pathlib import Path
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kospi-file", required=True)
    ap.add_argument("--kosdaq-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--asof", default="")
    args = ap.parse_args()

    k1 = pd.read_csv(args.kospi_file, dtype={args.ticker_col: str})
    k2 = pd.read_csv(args.kosdaq_file, dtype={args.ticker_col: str})

    k1[args.ticker_col] = k1[args.ticker_col].astype(str).str.zfill(6)
    k2[args.ticker_col] = k2[args.ticker_col].astype(str).str.zfill(6)

    # 필수 컬럼 보정
    if "market" not in k1.columns:
        k1["market"] = "KOSPI"
    if "market" not in k2.columns:
        k2["market"] = "KOSDAQ"

    mix = pd.concat([k1, k2], ignore_index=True)

    # 중복 방지(이론상 없어야 하지만 안전장치)
    mix = mix.drop_duplicates(subset=[args.ticker_col], keep="first").reset_index(drop=True)

    if len(mix) != 400:
        raise RuntimeError(f"mix size must be 400, but got {len(mix)} (kospi={len(k1)}, kosdaq={len(k2)})")

    if args.asof:
        mix["asof"] = args.asof

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mix.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[DONE] saved -> {out_path} | rows={len(mix)}")


if __name__ == "__main__":
    main()
