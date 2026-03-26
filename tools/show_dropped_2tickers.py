# show_dropped_2tickers.py ver 2026-02-05_002
import pandas as pd

mix = r"D:\Quant\data\universe\universe_mix_top400_20260205.csv"
ready = r"D:\Quant\data\universe\universe_mix_top400_20260205_priceready.csv"

df_mix = pd.read_csv(mix, dtype={"ticker": str})
df_ready = pd.read_csv(ready, dtype={"ticker": str})

df_mix["ticker"] = df_mix["ticker"].str.zfill(6)
df_ready["ticker"] = df_ready["ticker"].str.zfill(6)

s_mix = set(df_mix["ticker"])
s_ready = set(df_ready["ticker"])

dropped = sorted(list(s_mix - s_ready))
print("dropped_count =", len(dropped))
print("dropped_tickers =", dropped)

if dropped:
    print("\n[dropped rows]")
    print(df_mix[df_mix["ticker"].isin(dropped)].to_string(index=False))
