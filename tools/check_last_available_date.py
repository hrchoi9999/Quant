# check_last_available_date.py ver 2026-02-05_001
from datetime import date, timedelta
import pandas as pd
from pykrx import stock

def last_available_date(ref=None, probe="005930", lookback_days=30):
    ref = ref or date.today()
    start = ref - timedelta(days=lookback_days)
    df = stock.get_market_ohlcv_by_date(start.strftime("%Y%m%d"), ref.strftime("%Y%m%d"), probe)
    if df is None or df.empty:
        return None
    return pd.to_datetime(df.index.max()).date()

if __name__ == "__main__":
    lad = last_available_date()
    print("last_available_date =", lad)
