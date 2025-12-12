# English filename: 00_build_dataset_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/14일차 딥러닝 시계열의 이해_한국주식실습/2. RNN과 LSTM_고급실습/00_build_dataset_clear.py
# Original filename: 00_build_dataset_clear.py

# ---- Cell ----
!cd ..&& mkdir data&& cd data&&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/data/assets.zip&&unzip -n assets.zip

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
from pathlib import Path

import numpy as np
import pandas as pd

# ---- Cell ----
np.random.seed(42)

# ---- Cell ----
idx = pd.IndexSlice

# ---- Cell ----
DATA_DIR = Path('..', 'data')

# ---- Cell ----
prices = (pd.read_hdf(DATA_DIR / 'assets.h5', 'quandl/wiki/prices')
          .loc[idx['2010':'2017', :], ['adj_close', 'adj_volume']])
prices.info()

# ---- Cell ----
n_dates = len(prices.index.unique('date'))
dollar_vol = (prices.adj_close.mul(prices.adj_volume)
              .unstack('ticker')
              .dropna(thresh=int(.95 * n_dates), axis=1)
              .rank(ascending=False, axis=1)
              .stack('ticker'))

# ---- Cell ----
most_traded = dollar_vol.groupby(level='ticker').mean().nsmallest(500).index

# ---- Cell ----
returns = (prices.loc[idx[:, most_traded], 'adj_close']
           .unstack('ticker')
           .pct_change()
           .sort_index(ascending=False))
returns.info()

# ---- Cell ----
n = len(returns)
T = 21 # days
tcols = list(range(T))
tickers = returns.columns

# ---- Cell ----
data = pd.DataFrame()
for i in range(n-T-1):
    df = returns.iloc[i:i+T+1]
    date = df.index.max()
    data = pd.concat([data,
                      df.reset_index(drop=True).T
                      .assign(date=date, ticker=tickers)
                      .set_index(['ticker', 'date'])])
data = data.rename(columns={0: 'label'}).sort_index().dropna()
data.loc[:, tcols[1:]] = (data.loc[:, tcols[1:]].apply(lambda x: x.clip(lower=x.quantile(.01),
                                                  upper=x.quantile(.99))))
data.info()

# ---- Cell ----
data.shape

# ---- Cell ----
data.to_hdf('data.h5', 'returns_daily')

# ---- Cell ----
prices = (pd.read_hdf(DATA_DIR / 'assets.h5', 'quandl/wiki/prices')
          .adj_close
          .unstack().loc['2007':])
prices.info()

# ---- Cell ----
returns = (prices
           .resample('W')
           .last()
           .pct_change()
           .loc['2008': '2017']
           .dropna(axis=1)
           .sort_index(ascending=False))
returns.info()

# ---- Cell ----
returns.head()

# ---- Cell ----
n = len(returns)
T = 52 # weeks
tcols = list(range(T))
tickers = returns.columns

# ---- Cell ----
data = pd.DataFrame()
for i in range(n-T-1):
    df = returns.iloc[i:i+T+1]
    date = df.index.max()
    data = pd.concat([data, (df.reset_index(drop=True).T
                             .assign(date=date, ticker=tickers)
                             .set_index(['ticker', 'date']))])
data.info()

# ---- Cell ----
data[tcols] = (data[tcols].apply(lambda x: x.clip(lower=x.quantile(.01),
                                                  upper=x.quantile(.99))))

# ---- Cell ----
data = data.rename(columns={0: 'fwd_returns'})

# ---- Cell ----
data['label'] = (data['fwd_returns'] > 0).astype(int)

# ---- Cell ----
data.shape

# ---- Cell ----
data.sort_index().to_hdf('data.h5', 'returns_weekly')

# ---- Cell ----
data.head()

# ---- Cell ----

