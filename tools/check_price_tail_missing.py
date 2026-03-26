# check_price_tail_missing.py ver 2026-02-05_002
import sqlite3
import pandas as pd

DART_DB  = r"D:\Quant\data\db\dart_main.db"
PRICE_DB = r"D:\Quant\data\db\price.db"
UNI_TABLE = "universe_top400_fundready"
PRICE_TABLE = "prices_daily"
ASOF = "2026-02-04"  # 원하는 기준일

def main():
    con_d = sqlite3.connect(DART_DB)
    u = pd.read_sql_query(f"SELECT ticker, name, market FROM {UNI_TABLE}", con_d)
    con_d.close()
    u["ticker"] = u["ticker"].astype(str).str.zfill(6)

    con_p = sqlite3.connect(PRICE_DB)

    mm = pd.read_sql_query(f"SELECT MAX(date) AS max_date FROM {PRICE_TABLE}", con_p)
    max_date = mm.loc[0, "max_date"]
    effective_asof = ASOF
    if max_date and ASOF > max_date:
        print(f"[WARN] ASOF({ASOF}) > DB max_date({max_date}). Using effective_asof={max_date}")
        effective_asof = max_date

    have = pd.read_sql_query(
        f"SELECT ticker FROM {PRICE_TABLE} WHERE date = ? GROUP BY ticker",
        con_p,
        params=[effective_asof],
    )
    con_p.close()

    have_set = set(have["ticker"].astype(str).str.zfill(6))
    u_set = set(u["ticker"])
    missing = sorted(list(u_set - have_set))

    print(f"[RESULT] effective_asof={effective_asof} missing tickers = {len(missing)} / {len(u_set)}")

    if missing:
        miss_df = u[u["ticker"].isin(missing)].sort_values(["market","ticker"])
        out_csv = r"D:\Quant\tools\missing_price_tickers.csv"
        miss_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"[SAVE] missing list -> {out_csv}")

if __name__ == "__main__":
    main()
