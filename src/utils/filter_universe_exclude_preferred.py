# filter_universe_exclude_preferred.py ver 2026-02-02_002
import argparse
import sqlite3
import pandas as pd
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe-in", required=True)
    ap.add_argument("--ticker-col", default="ticker")
    ap.add_argument("--dart-db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    u = pd.read_csv(args.universe_in)
    if args.ticker_col not in u.columns:
        raise ValueError(f"ticker_col '{args.ticker_col}' not found in {args.universe_in}")

    u[args.ticker_col] = (
        u[args.ticker_col].astype(str).str.replace(r"\D","",regex=True).str.zfill(6)
    )

    con = sqlite3.connect(args.dart_db)
    dim = pd.read_sql_query(
        "select stock_code, corp_code, corp_name from dim_corp_listed",
        con
    )
    con.close()

    dim["stock_code"] = dim["stock_code"].astype(str).str.zfill(6)

    m = u.merge(dim, left_on=args.ticker_col, right_on="stock_code", how="left")

    # corp_code가 없는 티커는 판단 불가 -> 일단 유지(원하시면 제외로 바꿀 수 있음)
    # corp_code가 있는 그룹에서 "보통주 후보"를 정합니다: 기본은 코드 끝이 '0'
    def pick_common_code(codes):
        codes = sorted([c for c in codes if isinstance(c, str)])
        # 1순위: 끝이 0인 코드
        zeros = [c for c in codes if c.endswith("0")]
        if zeros:
            return zeros[0]
        # 2순위: 없으면 가장 작은 코드(보수적)
        return codes[0] if codes else None

    keep_map = (
        m.dropna(subset=["corp_code"])
         .groupby("corp_code")["stock_code"]
         .apply(lambda s: pick_common_code(list(s.unique())))
         .to_dict()
    )

    # keep_code가 정해진 corp_code 그룹에서는 keep_code만 남기고 나머지는 제거
    def should_remove(row):
        corp = row["corp_code"]
        code = row["stock_code"]
        if pd.isna(corp) or pd.isna(code):
            return False
        keep_code = keep_map.get(corp)
        return (keep_code is not None) and (code != keep_code)

    m["remove_pref_like"] = m.apply(should_remove, axis=1)

    before = len(m)
    out = m[~m["remove_pref_like"]].copy()
    after = len(out)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out[u.columns].to_csv(args.out, index=False, encoding="utf-8-sig")

    removed = m[m["remove_pref_like"]][[args.ticker_col, "corp_name", "corp_code"]].sort_values(args.ticker_col)
    print(f"[INFO] before={before} after={after} removed={before-after}")
    if len(removed) > 0:
        print("[REMOVED by corp_code (keep common-like code)]")
        print(removed.to_string(index=False))

if __name__ == "__main__":
    main()
