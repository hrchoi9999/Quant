# English filename: 03_preparing_the_model_data_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/9일차 머신러닝 투자모델 검증을 위한 전략 백테스트 I/03_preparing_the_model_data_wget_clear.py
# Original filename: 03_preparing_the_model_data_wget_clear.py

# ---- Cell ----
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/libta-lib0_0.4.0-oneiric1_amd64.deb -qO libta.deb
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/ta-lib0-dev_0.4.0-oneiric1_amd64.deb -qO ta.deb
!dpkg -i libta.deb ta.deb
!pip install ta-lib
!cd ..&& mkdir data&& cd data&&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/data/assets.zip&&unzip -n assets.zip

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import seaborn as sns

from scipy.stats import pearsonr, spearmanr
from talib import RSI, BBANDS, MACD, ATR

# ---- Cell ----
MONTH = 21
YEAR = 12 * MONTH

# ---- Cell ----
START = '2013-01-01'
END = '2017-12-31'

# ---- Cell ----
sns.set_style('whitegrid')
idx = pd.IndexSlice

# ---- Cell ----
ohlcv = ['adj_open', 'adj_close', 'adj_low', 'adj_high', 'adj_volume']

# ---- Cell ----
DATA_STORE = '../data/assets.h5'

# ---- Cell ----
with pd.HDFStore(DATA_STORE) as store:
    prices = (store['quandl/wiki/prices']
              .loc[idx[START:END, :], ohlcv]
              .rename(columns=lambda x: x.replace('adj_', ''))
              .assign(volume=lambda x: x.volume.div(1000))
              .swaplevel()
              .sort_index())

    stocks = (store['us_equities/stocks']
              .loc[:, ['marketcap', 'ipoyear', 'sector']])

# ---- Cell ----
# want at least 2 years of data
min_obs = 2 * YEAR

# have this much per ticker
nobs = prices.groupby(level='ticker').size()

# keep those that exceed the limit
keep = nobs[nobs > min_obs].index

prices = prices.loc[idx[keep, :], :]

# ---- Cell ----
stocks = stocks[~stocks.index.duplicated() & stocks.sector.notnull()]
stocks.sector = stocks.sector.str.lower().str.replace(' ', '_')
stocks.index.name = 'ticker'

# ---- Cell ----
shared = (prices.index.get_level_values('ticker').unique()
          .intersection(stocks.index))
stocks = stocks.loc[shared, :]
prices = prices.loc[idx[shared, :], :]

# ---- Cell ----
prices.info(show_counts=True)

# ---- Cell ----
stocks.info(show_counts=True)

# ---- Cell ----
stocks.sector.value_counts()

# ---- Cell ----
# with pd.HDFStore('tmp.h5') as store:
#     store.put('prices', prices)
#     store.put('stocks', stocks)

# ---- Cell ----
# with pd.HDFStore('tmp.h5') as store:
#     prices = store['prices']
#     stocks = store['stocks']

# ---- Cell ----
# compute dollar volume to determine universe
prices['dollar_vol'] = prices[['close', 'volume']].prod(axis=1)

# ---- Cell ----
prices['dollar_vol_1m'] = (prices.dollar_vol.groupby('ticker')
                           # .rolling(window=21, level='date')
                           .rolling(window=21)
                           .mean()).values

# ---- Cell ----
prices.info(show_counts=True)

# ---- Cell ----
prices['dollar_vol_rank'] = (prices.groupby('date')
                             .dollar_vol_1m
                             .rank(ascending=False))

# ---- Cell ----
prices.info(show_counts=True)

# ---- Cell ----
# prices['rsi'] = prices.groupby('ticker').close.apply(RSI)
prices['rsi'] =pd.concat([RSI(price) for _, price in prices.groupby('ticker').close])

# ---- Cell ----
ax = sns.distplot(prices.rsi.dropna())
ax.axvline(30, ls='--', lw=1, c='k')
ax.axvline(70, ls='--', lw=1, c='k')
ax.set_title('RSI Distribution with Signal Threshold')
plt.tight_layout();

# ---- Cell ----
def compute_bb(close):
    high, mid, low = BBANDS(close, timeperiod=20)
    return pd.DataFrame({'bb_high': high, 'bb_low': low}, index=close.index)

# ---- Cell ----
prices = (prices.join(pd.concat([compute_bb(close) for _, close in prices.groupby('ticker').close])))

# ---- Cell ----
prices.tail()

# ---- Cell ----
prices['bb_high'] = prices.bb_high.sub(prices.close).div(prices.bb_high).apply(np.log1p)
prices['bb_low'] = prices.close.sub(prices.bb_low).div(prices.close).apply(np.log1p)

# ---- Cell ----
fig, axes = plt.subplots(ncols=2, figsize=(15, 5))
sns.distplot(prices.loc[prices.dollar_vol_rank<100, 'bb_low'].dropna(), ax=axes[0])
sns.distplot(prices.loc[prices.dollar_vol_rank<100, 'bb_high'].dropna(), ax=axes[1])
plt.tight_layout();

# ---- Cell ----
def compute_atr(stock_data):
    df = ATR(stock_data.high, stock_data.low,
             stock_data.close, timeperiod=14)
    return df.sub(df.mean()).div(df.std())

# ---- Cell ----
prices['atr'] = (prices.groupby('ticker', group_keys=False)
                 .apply(compute_atr))

# ---- Cell ----
sns.distplot(prices[prices.dollar_vol_rank<50].atr.dropna());

# ---- Cell ----
def compute_macd(close):
    macd = MACD(close)[0]
    return (macd - np.mean(macd))/np.std(macd)

# ---- Cell ----
prices['macd'] = (prices
                  .groupby('ticker', group_keys=False)
                  .close
                  .apply(compute_macd))

# ---- Cell ----
prices.macd.describe()

# ---- Cell ----
prices.macd.describe(percentiles=[.001, .01, .02, .03, .04, .05, .95, .96, .97, .98, .99, .999]).apply(lambda x: f'{x:,.1f}')

# ---- Cell ----
sns.distplot(prices[prices.dollar_vol_rank<100].macd.dropna());

# ---- Cell ----
lags = [1, 5, 10, 21, 42, 63]

# ---- Cell ----
returns = prices.groupby(level='ticker').close.pct_change()
percentiles=[.0001, .001, .01]
percentiles += [1-p for p in percentiles]
returns.describe(percentiles=percentiles).iloc[2:].to_frame('percentiles').style.format(lambda x: f'{x:,.2%}')

# ---- Cell ----
q = 0.0001

# ---- Cell ----
for lag in lags:
    prices[f'return_{lag}d'] = (prices.groupby(level='ticker').close
                                .pct_change(lag)
                                .pipe(lambda x: x.clip(lower=x.quantile(q),
                                                       upper=x.quantile(1 - q)))
                                .add(1)
                                .pow(1 / lag)
                                .sub(1)
                                )

# ---- Cell ----
prices.info()

# ---- Cell ----
for t in [1, 2, 3, 4, 5]:
    for lag in [1, 5, 10, 21]:
        prices[f'return_{lag}d_lag{t}'] = (prices.groupby(level='ticker')
                                           [f'return_{lag}d'].shift(t * lag))

# ---- Cell ----
prices.info()

# ---- Cell ----
for t in [1, 5, 10, 21]:
    prices[f'target_{t}d'] = prices.groupby(level='ticker')[f'return_{t}d'].shift(-t)

# ---- Cell ----
prices = prices.join(stocks[['sector']])

# ---- Cell ----
prices['year'] = prices.index.get_level_values('date').year
prices['month'] = prices.index.get_level_values('date').month

# ---- Cell ----
prices.info()

# ---- Cell ----
prices.assign(sector=pd.factorize(prices.sector, sort=True)[0]).to_hdf('data.h5', 'model_data/no_dummies')

# ---- Cell ----
prices = pd.get_dummies(prices,
                        columns=['year', 'month', 'sector'],
                        prefix=['year', 'month', ''],
                        prefix_sep=['_', '_', ''],
                        drop_first=True)

# ---- Cell ----
prices.info()

# ---- Cell ----
prices.to_hdf('data.h5', 'model_data')

# ---- Cell ----
target = 'target_5d'
top100 = prices[prices.dollar_vol_rank<100].copy()

# ---- Cell ----
top100.loc[:, 'rsi_signal'] = pd.cut(top100.rsi, bins=[0, 30, 70, 100])

# ---- Cell ----
top100.head()

# ---- Cell ----
top100.groupby('rsi_signal')['target_5d'].describe()

# ---- Cell ----
metric = 'bb_low'
j=sns.jointplot(x=metric, y=target, data=top100)

df = top100[[metric, target]].dropna()
r, p = spearmanr(df[metric], df[target])
print(f'{r:,.2%} ({p:.2%})')

# ---- Cell ----
metric = 'bb_high'
j=sns.jointplot(x=metric, y=target, data=top100)

df = top100[[metric, target]].dropna()
r, p = spearmanr(df[metric], df[target])
print(f'{r:,.2%} ({p:.2%})')

# ---- Cell ----
metric = 'atr'
j=sns.jointplot(x=metric, y=target, data=top100)

df = top100[[metric, target]].dropna()
r, p = spearmanr(df[metric], df[target])
print(f'{r:,.2%} ({p:.2%})')

# ---- Cell ----
metric = 'macd'
j=sns.jointplot(x=metric, y=target, data=top100)

df = top100[[metric, target]].dropna()
r, p = spearmanr(df[metric], df[target])
print(f'{r:,.2%} ({p:.2%})')

# ---- Cell ----

