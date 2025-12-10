# English filename: hdf5_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/9일차 머신러닝 투자모델 검증을 위한 전략 백테스트 I/HDF5연습.py
# Original filename: HDF5연습.py

# ---- Cell ----
!pip -q install yfinance

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 20)


# ---- Cell ----
# 원하는 티커를 필요에 맞게 변경하세요
TICKERS = ["AAPL", "MSFT", "AMZN"]

START = "2015-01-01"
END   = "2020-12-31"

DATA_STORE = "data_store.h5"  # HDF5 파일명


# ---- Cell ----
raw = yf.download(TICKERS, start=START, end=END, group_by="ticker", auto_adjust=False, progress=False)

# 멀티컬럼(TICKER, [Open, High, Low, Close, Adj Close, Volume]) → tidy
frames = []
for t in TICKERS:
    df = raw[t].copy()
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]  # open, high, low, close, adj_close, volume
    df["adj_factor"] = df["adj_close"] / df["close"]
    # 조정 OHLCV
    df["adj_open"]   = df["open"]  * df["adj_factor"]
    df["adj_high"]   = df["high"]  * df["adj_factor"]
    df["adj_low"]    = df["low"]   * df["adj_factor"]
    # 보통 adj_close는 그대로 사용
    df["adj_volume"] = df["volume"] / df["adj_factor"]  # 분할 등 반영 (관행적으로 adj_volume은 역으로 조정)
    df["ticker"]     = t
    frames.append(df[["ticker", "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume", "open", "high", "low", "close", "volume"]].copy())

prices_adj = pd.concat(frames)
prices_adj.index.name = "date"

# (date, ticker) → (ticker, date) 멀티인덱스
prices_adj = prices_adj.reset_index().set_index(["ticker", "date"]).sort_index()
prices_adj.head()


# ---- Cell ----
# def safe_get_info(t):
#     info = {}
#     try:
#         ti = yf.Ticker(t)
#         # 빠른 정보
#         try:
#             info["marketcap"] = getattr(ti.fast_info, "market_cap", np.nan)
#         except Exception:
#             info["marketcap"] = np.nan
#         # 일반 info
#         try:
#             gi = ti.get_info()
#         except Exception:
#             gi = {}
#         info["sector"]  = gi.get("sector", None)
#         # 상장연도 근사: firstTradeDateEpochSeconds → year
#         try:
#             first_ts = gi.get("firstTradeDateEpochSeconds", None)
#             info["ipoyear"] = datetime.utcfromtimestamp(first_ts).year if first_ts else None
#         except Exception:
#             info["ipoyear"] = None
#     except Exception:
#         info = {"marketcap": np.nan, "sector": None, "ipoyear": None}
#     return info

# stocks_rows = []
# for t in TICKERS:
#     gi = safe_get_info(t)
#     stocks_rows.append({"ticker": t, "marketcap": gi["marketcap"], "ipoyear": gi["ipoyear"], "sector": gi["sector"]})

# stocks = pd.DataFrame(stocks_rows).set_index("ticker")
# stocks


# ---- Cell ----
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

def get_stock_info(t):
    """단일 티커의 기본 정보(시장가치, 섹터, 상장연도)를 안전하게 반환"""
    marketcap, sector, ipoyear = np.nan, None, None
    try:
        ti = yf.Ticker(t)
        marketcap = getattr(ti.fast_info, "market_cap", np.nan)
        info = ti.get_info()
        sector = info.get("sector")
        ts = info.get("firstTradeDateEpochSeconds")
        if ts:
            ipoyear = datetime.utcfromtimestamp(ts).year
    except Exception:
        pass
    return {"ticker": t, "marketcap": marketcap, "sector": sector, "ipoyear": ipoyear}

# 여러 티커에 대해 한 번에 실행
stocks = pd.DataFrame([get_stock_info(t) for t in TICKERS]).set_index("ticker")
stocks


# ---- Cell ----
with pd.HDFStore(DATA_STORE, mode="w") as store:
    # 테이블 포맷으로 저장(조건조회 가능)
    store.put("quandl/wiki/prices", prices_adj, format="table", data_columns=True)
    store.put("us_equities/stocks", stocks,     format="table", data_columns=True)

print("저장 완료:", DATA_STORE)
with pd.HDFStore(DATA_STORE) as store:
    print("키 목록:", store.keys())


# ---- Cell ----
from pandas import IndexSlice as idx

ohlcv = ["open", "high", "low", "close", "volume"]  # 조정 제거 후 사용할 칼럼명
START_READ, END_READ = START, END  # 동일 기간 재사용

with pd.HDFStore(DATA_STORE) as store:
    # 1) prices: adj_ 접두사 제거 → volume 단위 변경(천주) → 인덱스 레벨 스왑 → 정렬
    prices = (store["quandl/wiki/prices"]
              .loc[idx[:, pd.to_datetime(START_READ):pd.to_datetime(END_READ)], :]  # 기간 필터
              .rename(columns=lambda x: x.replace("adj_", ""))                       # adj_ 제거
              .assign(volume=lambda x: x["volume"].div(1000))                        # 천주 단위
              .swaplevel()                                                           # (ticker, date)→(date, ticker)였으면 반대로, 여기선 (ticker,date)라 영향X
              .sort_index())

    # ohlcv만 추리기
    prices = prices.loc[:, ohlcv]

    # 2) stocks: 필요한 칼럼만
    stocks_read = (store["us_equities/stocks"]
                   .loc[:, ["marketcap", "ipoyear", "sector"]])

prices.head(), stocks_read.head()


# ---- Cell ----
# 예: 2019-01-01 이후의 AAPL 행만 조회
# 인덱스가 (ticker, date) MultiIndex이므로 data_columns=True로 저장했으면 두 레벨 모두 조건 가능
q = pd.read_hdf(DATA_STORE,
                key="quandl/wiki/prices",
                where=['ticker="AAPL"', 'date>=Timestamp("2019-01-01")'])
q.head()


# ---- Cell ----
# 덮어쓰기 (전체 교체)
prices_adj.iloc[:1000].to_hdf(DATA_STORE, key="quandl/wiki/prices", mode="a", format="table", data_columns=True)

# 추가 (append) - 같은 key에 이어붙이기
prices_adj.iloc[1000:1200].to_hdf(DATA_STORE, key="quandl/wiki/prices", mode="a", format="table", data_columns=True)


# ---- Cell ----
# 간단히 한 번에 읽기 (조건 조회 필요 없을 때)
prices_simple = pd.read_hdf(DATA_STORE, key="quandl/wiki/prices")
stocks_simple = pd.read_hdf(DATA_STORE, key="us_equities/stocks")
prices_simple.head(), stocks_simple.head()


# ---- Cell ----
with pd.HDFStore(DATA_STORE) as stor
    print("키 목록:", store.keys())


# ---- Cell ----

