# English filename: 04_preparing_the_model_data_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/12일차 미국주식 고급머신러닝 투자전략 I/04_preparing_the_model_data_clear.py
# Original filename: 04_preparing_the_model_data_clear.py

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
import talib
from talib import RSI, BBANDS, MACD, ATR

# ---- Cell ----
MONTH = 21
YEAR = 12 * MONTH

# ---- Cell ----
START = '2010-01-01'
END = '2017-12-31'

# ---- Cell ----
sns.set_style('darkgrid')
idx = pd.IndexSlice

# ---- Cell ----
percentiles = [.001, .01, .02, .03, .04, .05]
percentiles += [1-p for p in percentiles[::-1]]

# ---- Cell ----
percentiles

# ---- Cell ----
T = [1, 5, 10, 21, 42, 63]

# ---- Cell ----
DATA_STORE = '../data/assets.h5'
ohlcv = ['adj_open', 'adj_close', 'adj_low', 'adj_high', 'adj_volume']
with pd.HDFStore(DATA_STORE) as store:
    prices = (store['quandl/wiki/prices']
              .loc[idx[START:END, :], ohlcv] # select OHLCV columns from 2010 until 2017
              .rename(columns=lambda x: x.replace('adj_', '')) # simplify column names
              .swaplevel()
              .sort_index())
    metadata = (store['us_equities/stocks'].loc[:, ['marketcap', 'sector']])

# ---- Cell ----
prices.volume /= 1e3 # make vol figures a bit smaller
prices.index.names = ['symbol', 'date']
metadata.index.name = 'symbol'

# ---- Cell ----
min_obs = 7 * YEAR
nobs = prices.groupby(level='symbol').size()
keep = nobs[nobs > min_obs].index
prices = prices.loc[idx[keep, :], :]

# ---- Cell ----
metadata = metadata[~metadata.index.duplicated() & metadata.sector.notnull()]
metadata.sector = metadata.sector.str.lower().str.replace(' ', '_')

# ---- Cell ----
shared = (prices.index.get_level_values('symbol').unique()
          .intersection(metadata.index))
metadata = metadata.loc[shared, :]
prices = prices.loc[idx[shared, :], :]

# ---- Cell ----
universe = metadata.marketcap.nlargest(1000).index
prices = prices.loc[idx[universe, :], :]
metadata = metadata.loc[universe]

# ---- Cell ----
metadata.sector.value_counts()

# ---- Cell ----
prices.info(show_counts=True)

# ---- Cell ----
metadata.info()

# ---- Cell ----
prices['dollar_vol'] = prices[['close', 'volume']].prod(1).div(1e3)

# ---- Cell ----
# compute dollar volume to determine universe
dollar_vol_ma = (prices
                 .dollar_vol
                 .unstack('symbol')
                 .rolling(window=21, min_periods=1) # 1 trading month
                 .mean())

# ---- Cell ----
prices['dollar_vol_rank'] = (dollar_vol_ma
                            .rank(axis=1, ascending=False)
                            .stack('symbol')
                            .swaplevel())

# ---- Cell ----
prices.info(show_counts=True)

# ---- Cell ----
prices['rsi'] = pd.concat([RSI(x) for ticker, x in prices.groupby(level='symbol').close])

# ---- Cell ----
ax = sns.distplot(prices.rsi.dropna())
ax.axvline(30, ls='--', lw=1, c='k')
ax.axvline(70, ls='--', lw=1, c='k')
ax.set_title('RSI Distribution with Signal Threshold')
sns.despine()
plt.tight_layout();

# ---- Cell ----
def compute_bb(close):
    high, mid, low = BBANDS(close, timeperiod=20)
    return pd.DataFrame({'bb_high': high, 'bb_low': low}, index=close.index)

# ---- Cell ----
prices = (prices.join(pd.concat([compute_bb(x) for _, x in prices.groupby(level='symbol').close])))

# ---- Cell ----
prices['bb_high'] = prices.bb_high.sub(prices.close).div(prices.bb_high).apply(np.log1p)
prices['bb_low'] = prices.close.sub(prices.bb_low).div(prices.close).apply(np.log1p)

# ---- Cell ----
fig, axes = plt.subplots(ncols=2, figsize=(15, 5))
sns.distplot(prices.loc[prices.dollar_vol_rank<100, 'bb_low'].dropna(), ax=axes[0])
sns.distplot(prices.loc[prices.dollar_vol_rank<100, 'bb_high'].dropna(), ax=axes[1])
sns.despine()
plt.tight_layout();

# ---- Cell ----
prices['NATR'] = prices.groupby(level='symbol',
                                group_keys=False).apply(lambda x:
                                                        talib.NATR(x.high, x.low, x.close))

# ---- Cell ----
def compute_atr(stock_data):
    df = ATR(stock_data.high, stock_data.low,
             stock_data.close, timeperiod=14)
    return df.sub(df.mean()).div(df.std())

# ---- Cell ----
prices['ATR'] = (prices.groupby('symbol', group_keys=False)
                 .apply(compute_atr))

# ---- Cell ----
prices['PPO'] = pd.concat([talib.PPO(x) for ticker, x in prices.groupby(level='symbol').close])

# ---- Cell ----
def compute_macd(close):
    macd = MACD(close)[0]
    return (macd - np.mean(macd))/np.std(macd)

# ---- Cell ----
prices['MACD'] = (prices
                  .groupby('symbol', group_keys=False)
                  .close
                  .apply(compute_macd))

# ---- Cell ----
metadata.sector = pd.factorize(metadata.sector)[0].astype(int)
prices = prices.join(metadata[['sector']])

# ---- Cell ----
by_sym = prices.groupby(level='symbol', group_keys=False).close
for t in T:
    prices[f'r{t:02}'] = by_sym.pct_change(t)

# ---- Cell ----
# 인위적으로 추가함
prices = prices.dropna()

# ---- Cell ----
for t in T:
    prices[f'r{t:02}dec'] = (prices[f'r{t:02}']
                             .groupby(level='date', group_keys=False)
                             .apply(lambda x: pd.qcut(x,
                                                      q=10,
                                                      labels=False,
                                                      duplicates='drop'))
                            )

# ---- Cell ----
for t in T:
    prices[f'r{t:02}q_sector'] = (prices
                                  .groupby(['date', 'sector'], group_keys=False)[f'r{t:02}']
                                  .transform(lambda x: pd.qcut(x,
                                                               q=5,
                                                               labels=False,
                                                               duplicates='drop'))
                                 )

# ---- Cell ----
for t in [1, 5, 21]:
    prices[f'r{t:02}_fwd'] = prices.groupby(level='symbol', group_keys=False)[f'r{t:02}'].shift(-t)

# ---- Cell ----
prices[[f'r{t:02}' for t in T]].describe()

# ---- Cell ----
outliers = prices[prices.r01 > 1].index.get_level_values('symbol').unique()

# ---- Cell ----
prices = prices.drop(outliers, level='symbol')

# ---- Cell ----
prices['year'] = prices.index.get_level_values('date').year
prices['month'] = prices.index.get_level_values('date').month
prices['weekday'] = prices.index.get_level_values('date').weekday

# ---- Cell ----
prices.info(show_counts=True)

# ---- Cell ----
prices.drop(['open', 'close', 'low', 'high', 'volume'], axis=1).to_hdf('data.h5', 'model_data')

# ---- Cell ----

