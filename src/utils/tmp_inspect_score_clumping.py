# tmp_inspect_score_clumping.py ver 2026-02-02_001
import argparse, sqlite3
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\Quant\data\db\fundamentals.db")
    ap.add_argument("--table", default="fundamentals_monthly_mix400_20260129_dedup")
    ap.add_argument("--asof", default="2025-03-31")
    ap.add_argument("--score", type=float, default=280.75)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    q = f"""
    select ticker, available_from, revenue_yoy, op_income_yoy, growth_score
    from {args.table}
    where available_from = ?
    """
    df = pd.read_sql_query(q, con, params=[args.asof])
    con.close()

    print(f"[DATE] {args.asof} | rows={len(df)}")
    print("[DISTINCT]")
    for col in ["growth_score","revenue_yoy","op_income_yoy"]:
        print(f"  {col}: distinct={df[col].nunique(dropna=False)} nulls={int(df[col].isna().sum())}")

    # score==target
    hit = df[df["growth_score"] == args.score].copy()
    print(f"\n[SCORE=={args.score}] rows={len(hit)}")
    if len(hit) > 0:
        print("\n[revenue_yoy describe]")
        print(hit["revenue_yoy"].describe(percentiles=[.01,.05,.5,.95,.99]).to_string())
        print("\n[op_income_yoy describe]")
        print(hit["op_income_yoy"].describe(percentiles=[.01,.05,.5,.95,.99]).to_string())

        # 얼마나 다양한데 score만 같은지
        print("\n[TOP combos of (revenue_yoy, op_income_yoy)]")
        combo = (hit[["revenue_yoy","op_income_yoy"]]
                 .value_counts(dropna=False)
                 .head(20)
                 .reset_index(name="n"))
        print(combo.to_string(index=False))

    # score 분포
    print("\n[TOP 20 growth_score freq]")
    print(df["growth_score"].value_counts().head(20).to_string())

if __name__ == "__main__":
    main()
