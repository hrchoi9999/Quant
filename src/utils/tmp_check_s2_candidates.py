import pandas as pd, sqlite3

dt = "2026-01-29"

u = pd.read_csv("D:/Quant/data/universe/universe_mix_top400_20260129_fundready.csv", dtype={"ticker": str})
ticks = u["ticker"].str.zfill(6).tolist()

# fundamentals as-of
con = sqlite3.connect("D:/Quant/data/db/fundamentals.db")
f = pd.read_sql_query("select ticker, available_from, growth_score from fundamentals_monthly_mix400_20260129", con)
con.close()

f["available_from"] = pd.to_datetime(f["available_from"])
f = f[f["ticker"].isin(ticks) & (f["available_from"] <= dt)]
asof = f.sort_values(["ticker","available_from"]).groupby("ticker").tail(1)

print("asof rows=", len(asof), "growth_score nonna=", int(asof["growth_score"].notna().sum()))

# regime at dt
con = sqlite3.connect("D:/Quant/data/db/regime.db")
r = pd.read_sql_query("select ticker, regime from regime_history where date=? and horizon='3m'", con, params=[dt])
con.close()
print("regime rows=", len(r), "good(3,4)=", int(r["regime"].isin([3,4]).sum()))

# price SMA120 ok
con = sqlite3.connect("D:/Quant/data/db/price.db")
ph = ",".join(["?"] * len(ticks))
sql = f"select date,ticker,close from prices_daily where date<=? and ticker in ({ph})"
p = pd.read_sql_query(sql, con, params=[dt] + ticks)
con.close()

p["date"] = pd.to_datetime(p["date"])
piv = p.pivot(index="date", columns="ticker", values="close").sort_index().ffill()
sma = piv.tail(120).mean()
px = piv.iloc[-1]
ok = (px > sma)
print("price_ok=", int(ok.sum()))

# candidates after all filters
cand = asof.merge(r, on="ticker", how="inner")
cand = cand[cand["regime"].isin([3,4])]
cand = cand[cand["ticker"].map(ok.to_dict()) == True]
cand = cand.dropna(subset=["growth_score"])

print("candidates after all filters=", len(cand))
print(cand.sort_values("growth_score", ascending=False).head(10).to_string(index=False))
