# English filename: 02_common_alpha_factors_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/1일차 머신러닝 분석을 위한 알파 팩터 수집 및 작성/2_ alpha_factor_library/02_common_alpha_factors_wget.py
# Original filename: 02_common_alpha_factors_wget.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/alpha_factor_library_101.zip && unzip -n alpha_factor_library_101.zip

# ---- Cell ----
# !wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/ta-lib-0.4.0-src.tar.gz &&tar -xvf ta-lib-0.4.0-src.tar.gz &&cd ta-lib/ &&./configure --prefix=/usr &&make &&sudo make install
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/libta-lib0_0.4.0-oneiric1_amd64.deb -qO libta.deb
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/ta-lib0-dev_0.4.0-oneiric1_amd64.deb -qO ta.deb
!dpkg -i libta.deb ta.deb
!pip install ta-lib tables

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

from pathlib import Path
import numpy as np
import pandas as pd
import pandas_datareader.data as web

import statsmodels.api as sm
from statsmodels.regression.rolling import RollingOLS
from sklearn.preprocessing import scale
import talib

import matplotlib.pyplot as plt
import seaborn as sns

# ---- Cell ----
sns.set_style('whitegrid')
idx = pd.IndexSlice
deciles = np.arange(.1, 1, .1).round(1)

# ---- Cell ----
data = pd.read_hdf('data.h5', 'data/top500')
price_sample = pd.read_hdf('data.h5', 'data/sample')

# ---- Cell ----
function_groups = ['Overlap Studies',
                   'Momentum Indicators',
                   'Volume Indicators',
                   'Volatility Indicators',
                   'Price Transform',
                   'Cycle Indicators',
                   'Pattern Recognition',
                   'Statistic Functions',
                   'Math Transform',
                   'Math Operators']

# ---- Cell ----
talib_grps = talib.get_function_groups()

# ---- Cell ----
df = price_sample.loc['2012': '2013', ['close']]

# ---- Cell ----
for t in [5, 21, 63]:
    df[f'SMA_{t}'] = talib.SMA(df.close,
                               timeperiod=t)

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]

# ---- Cell ----
for t in [5, 21, 63]:
    df[f'EMA_{t}'] = talib.EMA(df.close,
                               timeperiod=t)

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]

# ---- Cell ----
for t in [5, 21, 63]:
    df[f'WMA_{t}'] = talib.WMA(df.close,
                               timeperiod=t)

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]

# ---- Cell ----
for t in [5, 21, 63]:
    df[f'DEMA_{t}'] = talib.DEMA(df.close,
                                timeperiod=t)

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]

# ---- Cell ----
for t in [5, 21, 63]:
    df[f'TEMA_{t}'] = talib.TEMA(df.close,
                                timeperiod=t)

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]

# ---- Cell ----
for t in [5, 21, 63]:
    df[f'TRIMA_{t}'] = talib.TRIMA(df.close,
                                timeperiod=t)

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]

# ---- Cell ----
for t in [5, 21, 63]:
    df[f'KAMA_{t}'] = talib.KAMA(df.close,
                                timeperiod=t)

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]

# ---- Cell ----
len(talib.MAMA(df.close,
                         fastlimit=.5,
                         slowlimit=.05))

# ---- Cell ----
mama, fama = talib.MAMA(df.close,
                        fastlimit=.5,
                        slowlimit=.05)
df['mama'] = mama
df['fama'] = fama

# ---- Cell ----
ax = df.plot(figsize=(14, 5), rot=0)
sns.despine()
ax.set_xlabel('');

# ---- Cell ----
df = price_sample.loc['2012', ['close']]
t = 21

# ---- Cell ----
df['SMA'] = talib.SMA(df.close, timeperiod=t)
df['WMA'] = talib.WMA(df.close, timeperiod=t)
df['TRIMA'] = talib.TRIMA(df.close, timeperiod=t)

ax = df[['close', 'SMA', 'WMA', 'TRIMA']].plot(figsize=(16, 8), rot=0)

sns.despine()
ax.set_xlabel('')
plt.tight_layout();

# ---- Cell ----
df['EMA'] = talib.EMA(df.close, timeperiod=t)
df['DEMA'] = talib.DEMA(df.close, timeperiod=t)
df['TEMA'] = talib.TEMA(df.close, timeperiod=t)

ax = df[['close', 'EMA', 'DEMA', 'TEMA']].plot(figsize=(16, 8), rot=0)

ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
df['KAMA'] = talib.KAMA(df.close, timeperiod=t)
mama, fama = talib.MAMA(df.close,
                        fastlimit=.5,
                        slowlimit=.05)
df['MAMA'] = mama
df['FAMA'] = fama
ax = df[['close', 'KAMA', 'MAMA', 'FAMA']].plot(figsize=(16, 8), rot=0)

ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
fig, axes = plt.subplots(nrows=3, figsize=(14, 10), sharex=True, sharey=True)


df[['close', 'SMA', 'WMA', 'TRIMA']].plot(rot=0,
                                          ax=axes[0],
                                          title='Simple, Weighted and Triangular Moving Averages',
                                          lw=1, style=['-', '--', '-.', ':'], c='k')
df[['close', 'EMA', 'DEMA', 'TEMA']].plot(rot=0, ax=axes[1],
                                          title='Simple, Double, and Triple Exponential Moving Averages',
                                          lw=1, style=['-', '--', '-.', ':'], c='k')

df[['close', 'KAMA', 'MAMA', 'FAMA']].plot(rot=0, ax=axes[2],
                                          title='Mesa and Kaufman Adaptive Moving Averages',
                                          lw=1, style=['-', '--', '-.', ':'], c='k')
axes[2].set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
s = talib.BBANDS(df.close,   # Number of periods (2 to 100000)
                 timeperiod=20,
                 nbdevup=2,    # Deviation multiplier for lower band
                 nbdevdn=2,    # Deviation multiplier for upper band
                 matype=1      # default: SMA
                 )

# ---- Cell ----
bb_bands = ['upper', 'middle', 'lower']

# ---- Cell ----
df = price_sample.loc['2012', ['close']]
df = df.assign(**dict(zip(bb_bands, s)))
ax = df.loc[:, ['close'] + bb_bands].plot(figsize=(16, 5), lw=1)

ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
fig, ax = plt.subplots(figsize=(16,5))
df.upper.div(df.close).plot(ax=ax, label='bb_up')
df.lower.div(df.close).plot(ax=ax, label='bb_low')
df.upper.div(df.lower).plot(ax=ax, label='bb_squeeze', rot=0)

plt.legend()
ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
def compute_bb_indicators(close, timeperiod=20, matype=0):
    high, mid, low = talib.BBANDS(close,
                                  timeperiod=20,
                                  matype=matype)
    bb_up = high / close -1
    bb_low = low / close -1
    squeeze = (high - low) / close
    return pd.DataFrame({'BB_UP': bb_up,
                         'BB_LOW': bb_low,
                         'BB_SQUEEZE': squeeze},
                        index=close.index)

# ---- Cell ----
data = (data.join(data.groupby(level='ticker', group_keys=False)['close'].apply(compute_bb_indicators)))

# ---- Cell ----
bb_indicators = ['BB_UP', 'BB_LOW', 'BB_SQUEEZE']

# ---- Cell ----
q = .01
with sns.axes_style('white'):
    fig, axes = plt.subplots(ncols=3, figsize=(14, 4), sharey=True, sharex=True)
    df_ = data[bb_indicators]
    df_ = df_.clip(df_.quantile(q),
                   df_.quantile(1-q), axis=1)
    for i, indicator in enumerate(bb_indicators):
        sns.distplot(df_[indicator], ax=axes[i])
    fig.suptitle('Distribution of normalized Bollinger Band indicators', fontsize=12)

    sns.despine()
    fig.tight_layout()
    fig.subplots_adjust(top=.93);

# ---- Cell ----
# 오래걸립니다.
ncols = len(bb_indicators)
fig, axes = plt.subplots(ncols=ncols, figsize=(5*ncols, 4), sharey=True)
for i, indicator in enumerate(bb_indicators):
    ticker, date = data[indicator].nlargest(1).index[0]
    p = data.loc[idx[ticker, :], :].close.reset_index('ticker', drop=True)
    p = p.div(p.dropna().iloc[0])
    p.plot(ax=axes[i], label=ticker, rot=0)
    c = axes[i].get_lines()[-1].get_color()
    axes[i].axvline(date, ls='--', c=c, lw=1)
    ticker, date = data[indicator].nsmallest(1).index[0]
    p = data.loc[idx[ticker, :], :].close.reset_index('ticker', drop=True)
    p = p.div(p.dropna().iloc[0])
    p.plot(ax=axes[i], label=ticker, rot=0)
    c = axes[i].get_lines()[-1].get_color()
    axes[i].axvline(date, ls='--', c=c, lw=1)
    axes[i].set_title(indicator.upper())
    axes[i].legend()
    axes[i].set_xlabel('')
sns.despine()
fig.tight_layout();

# ---- Cell ----
df = price_sample.loc['2012', ['close']]
df['HT_TRENDLINE'] = talib.HT_TRENDLINE(df.close)

# ---- Cell ----
ax = df.plot(figsize=(16, 4), style=['-', '--'], rot=0)

ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
data['HT'] = (data
              .groupby(level='ticker', group_keys=False)
              .close
              .apply(talib.HT_TRENDLINE)
              .div(data.close).sub(1))

# ---- Cell ----
q=0.005
with sns.axes_style('white'):
    sns.distplot(data.HT.clip(data.HT.quantile(q), data.HT.quantile(1-q)))
    sns.despine();

# ---- Cell ----
df = price_sample.loc['2012', ['close', 'high', 'low']]
df['SAR'] = talib.SAR(df.high, df.low,
                      acceleration=0.02, # common value
                      maximum=0.2)

# ---- Cell ----
ax = df[['close', 'SAR']].plot(figsize=(16, 4), style=['-', '--'], title='Parabolic SAR')
ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
def compute_sar_indicator(x, acceleration=.02, maximum=0.2):
    sar = talib.SAR(x.high,
                    x.low,
                    acceleration=acceleration,
                    maximum=maximum)
    return sar/x.close - 1

# ---- Cell ----
data['SAR'] = (data.groupby(level='ticker', group_keys=False)
                  .apply(compute_sar_indicator))

# ---- Cell ----
q=0.005
with sns.axes_style('white'):
    sns.distplot(data.SAR.clip(data.SAR.quantile(q), data.SAR.quantile(1-q)))
    sns.despine()

# ---- Cell ----
df = price_sample.loc['2012': '2013', ['high', 'low', 'close']]

# ---- Cell ----
df['PLUS_DM'] = talib.PLUS_DM(df.high, df.low, timeperiod=10)
df['MINUS_DM'] = talib.MINUS_DM(df.high, df.low, timeperiod=10)

# ---- Cell ----
ax = df[['close', 'PLUS_DM', 'MINUS_DM']].plot(figsize=(14, 4),
                                               secondary_y=[
                                                   'PLUS_DM', 'MINUS_DM'],
                                               style=['-', '--', '_'],
                                              rot=0)
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
df = price_sample.loc['2012': '2013', ['high', 'low', 'close']]

# ---- Cell ----
df['PLUS_DI'] = talib.PLUS_DI(df.high, df.low, df.close, timeperiod=14)
df['MINUS_DI'] = talib.MINUS_DI(df.high, df.low, df.close, timeperiod=14)

# ---- Cell ----
ax = df[['close', 'PLUS_DI', 'MINUS_DI']].plot(figsize=(14, 5), style=['-', '--', '_'], rot=0)

ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
df = price_sample.loc[:, ['high', 'low', 'close']]

# ---- Cell ----
df['ADX'] = talib.ADX(df.high,
                      df.low,
                      df.close,
                      timeperiod=14)

# ---- Cell ----
ax = df[['close', 'ADX']].plot(figsize=(14, 4), secondary_y='ADX', style=['-', '--'], rot=0)
ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
def compute_adx(x, timeperiod=14):
    return talib.ADX(x.high,
                    x.low,
                    x.close,
                    timeperiod=timeperiod)

# ---- Cell ----
data['ADX'] = (data.groupby(level='ticker', group_keys=False)
                  .apply(compute_adx))

# ---- Cell ----
with sns.axes_style("white"):
    sns.distplot(data.ADX)
    sns.despine();

# ---- Cell ----
df = price_sample.loc[:, ['high', 'low', 'close']]

# ---- Cell ----
df['ADXR'] = talib.ADXR(df.high,
                        df.low,
                        df.close,
                        timeperiod=14)

# ---- Cell ----
ax = df[['close', 'ADXR']].plot(figsize=(14, 5),
                                secondary_y='ADX',
                                style=['-', '--'], rot=0)
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
def compute_adxr(x, timeperiod=14):
    return talib.ADXR(x.high,
                    x.low,
                    x.close,
                    timeperiod=timeperiod)

# ---- Cell ----
data['ADXR'] = (data.groupby(level='ticker', group_keys=False)
                .apply(compute_adxr))

# ---- Cell ----
with sns.axes_style('white'):
    sns.distplot(data.ADXR)
    sns.despine();

# ---- Cell ----
df = price_sample.loc[:, ['close']]

# ---- Cell ----
df['APO'] = talib.APO(df.close,
                      fastperiod=12,
                      slowperiod=26,
                      matype=0)

# ---- Cell ----
ax = df.plot(figsize=(14,4), secondary_y='APO', rot=0, style=['-', '--'])
ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
df = price_sample.loc[:, ['close']]

# ---- Cell ----
df['PPO'] = talib.PPO(df.close,
                      fastperiod=12,
                      slowperiod=26,
                      matype=0)

# ---- Cell ----
ax = df.plot(figsize=(14,4), secondary_y=['APO', 'PPO'], rot=0,  style=['-', '--'])

ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
data['PPO'] = (data.groupby(level='ticker', group_keys=False)
               .close
               .apply(talib.PPO,
                      fastperiod=12,
                      slowperiod=26,
                      matype=1))

# ---- Cell ----
q = 0.001
with sns.axes_style("white"):
    sns.distplot(data.PPO.clip(lower=data.PPO.quantile(q),
                               upper=data.PPO.quantile(1-q)))
    sns.despine()

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
aroonup, aroondwn = talib.AROON(high=df.high,
                                low=df.low,
                                timeperiod=14)
df['AROON_UP'] = aroonup
df['AROON_DWN'] = aroondwn

# ---- Cell ----
fig, axes = plt.subplots(nrows=2, figsize=(14, 7), sharex=True)
df.close.plot(ax=axes[0], rot=0)
df[['AROON_UP', 'AROON_DWN']].plot(ax=axes[1], rot=0)

axes[1].set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
df['AROONOSC'] = talib.AROONOSC(high=df.high,
                                low=df.low,
                                timeperiod=14)

# ---- Cell ----
ax = df[['close', 'AROONOSC']].plot(figsize=(14,4), rot=0, style=['-', '--'], secondary_y='AROONOSC')
ax.set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
data['AARONOSC'] = (data.groupby('ticker',
                                 group_keys=False)
                    .apply(lambda x: talib.AROONOSC(high=x.high,
                                                    low=x.low,
                                                    timeperiod=14)))

# ---- Cell ----
with sns.axes_style("white"):
    sns.distplot(data.AARONOSC)
    sns.despine()

# ---- Cell ----
df = price_sample.loc['2013', ['open', 'high', 'low', 'close']]

# ---- Cell ----
df['BOP'] = talib.BOP(open=df.open,
                      high=df.high,
                      low=df.low,
                      close=df.close)

# ---- Cell ----
axes = df[['close', 'BOP']].plot(figsize=(14, 7), rot=0, subplots=True, title=['AAPL', 'BOP'], legend=False)
axes[1].set_xlabel('')
sns.despine()
plt.tight_layout();

# ---- Cell ----
by_ticker = data.groupby('ticker', group_keys=False)

# ---- Cell ----
data['BOP'] = (by_ticker
               .apply(lambda x: talib.BOP(x.open,
                                          x.high,
                                          x.low,
                                          x.close)))

# ---- Cell ----
q = 0.0005
with sns.axes_style("white"):
    sns.distplot(data.BOP.clip(lower=data.BOP.quantile(q),
                               upper=data.BOP.quantile(1-q)))
    sns.despine()

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
df['CCI'] = talib.CCI(high=df.high,
                      low=df.low,
                      close=df.close,
                      timeperiod=14)

# ---- Cell ----
axes = df[['close', 'CCI']].plot(figsize=(14, 7),
                                 rot=0,
                                 subplots=True,
                                 title=['AAPL', 'CCI'],
                                 legend=False)
axes[1].set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['CCI'] = (by_ticker
               .apply(lambda x: talib.CCI(x.high,
                                          x.low,
                                          x.close,
                                          timeperiod=14)))

# ---- Cell ----
with sns.axes_style('white'):
    sns.distplot(data.CCI)
    sns.despine();

# ---- Cell ----
df = price_sample.loc['2013', ['close']]

# ---- Cell ----
macd, macdsignal, macdhist = talib.MACD(df.close,
                                        fastperiod=12,
                                        slowperiod=26,
                                        signalperiod=9)
df['MACD'] = macd
df['MACDSIG'] = macdsignal
df['MACDHIST'] = macdhist

# ---- Cell ----
axes = df.plot(figsize=(14, 8),
               rot=0,
               subplots=True,
               title=['AAPL', 'MACD', 'MACDSIG', 'MACDHIST'],
               legend=False)

axes[-1].set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
def compute_macd(close, fastperiod=12, slowperiod=26, signalperiod=9):
    macd, macdsignal, macdhist = talib.MACD(close,
                                            fastperiod=fastperiod,
                                            slowperiod=slowperiod,
                                            signalperiod=signalperiod)
    return pd.DataFrame({'MACD': macd,
                         'MACD_SIGNAL': macdsignal,
                         'MACD_HIST': macdhist},
                        index=close.index)

# ---- Cell ----
data = (data.join(data
                  .groupby(level='ticker', group_keys=False)
                  .close
                  .apply(compute_macd)))

# ---- Cell ----
macd_indicators = ['MACD', 'MACD_SIGNAL', 'MACD_HIST']

# ---- Cell ----
data[macd_indicators].corr()

# ---- Cell ----
q = .005
with sns.axes_style('white'):
    fig, axes = plt.subplots(ncols=3, figsize=(14, 4))
    df_ = data[macd_indicators]
    df_ = df_.clip(df_.quantile(q),
                   df_.quantile(1-q), axis=1)
    for i, indicator in enumerate(macd_indicators):
        sns.distplot(df_[indicator], ax=axes[i])
    sns.despine()
    fig.tight_layout();

# ---- Cell ----
df = price_sample.loc['2013', ['close']]

# ---- Cell ----
df['CMO'] = talib.CMO(df.close, timeperiod=14)

# ---- Cell ----
ax = df.plot(figsize=(14, 4), rot=0, secondary_y=['CMO'], style=['-', '--'])

ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
# data['CMO'] = (by_ticker
#                .apply(lambda x: talib.CMO(x.close,
#                                           timeperiod=14)))

# ---- Cell ----
# sns.distplot(data.CMO);

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close', 'volume']]

# ---- Cell ----
df['MFI'] = talib.MFI(df.high,
                      df.low,
                      df.close,
                      df.volume,
                      timeperiod=14)

# ---- Cell ----
axes = df[['close', 'volume', 'MFI']].plot(figsize=(14, 8),
                                           rot=0,
                                           subplots=True,
                                           title=['Close', 'Volume', 'MFI'],
                                           legend=False)
axes[-1].set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['MFI'] = (by_ticker
               .apply(lambda x: talib.MFI(x.high,
                                          x.low,
                                          x.close,
                                          x.volume,
                                          timeperiod=14)))

# ---- Cell ----
with sns.axes_style('white'):
    sns.distplot(data.MFI)
    sns.despine()

# ---- Cell ----
df = price_sample.loc['2013', ['close']]

# ---- Cell ----
df['RSI'] = talib.RSI(df.close, timeperiod=14)

# ---- Cell ----
ax = df.plot(figsize=(14, 4), rot=0, secondary_y=['RSI'], style=['-', '--'])
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['RSI'] = (by_ticker
               .apply(lambda x: talib.RSI(x.close,
                                          timeperiod=14)))

# ---- Cell ----
with sns.axes_style('white'):
    sns.distplot(data.RSI)
    sns.despine();

# ---- Cell ----
df = price_sample.loc['2013', ['close']]

# ---- Cell ----
fastk, fastd = talib.STOCHRSI(df.close,
                              timeperiod=14,
                              fastk_period=14,
                              fastd_period=3,
                              fastd_matype=0)
df['fastk'] = fastk
df['fastd'] = fastd

# ---- Cell ----
ax = df.plot(figsize=(14, 4),
             rot=0,
             secondary_y=['fastk', 'fastd'], style=['-', '--'])
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['STOCHRSI'] = (by_ticker.apply(lambda x: talib.STOCHRSI(x.close,
                                                             timeperiod=14,
                                                             fastk_period=14,
                                                             fastd_period=3,
                                                             fastd_matype=0)[0]))

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
slowk, slowd = talib.STOCH(df.high,
                           df.low,
                           df.close,
                           fastk_period=14,
                           slowk_period=3,
                           slowk_matype=0,
                           slowd_period=3,
                           slowd_matype=0)
df['STOCH'] = slowd / slowk

# ---- Cell ----
ax = df[['close', 'STOCH']].plot(figsize=(14, 4),
                                 rot=0,
                                 secondary_y='STOCH', style=['-', '--'])
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
def compute_stoch(x, fastk_period=14, slowk_period=3,
                  slowk_matype=0, slowd_period=3, slowd_matype=0):
    slowk, slowd = talib.STOCH(x.high, x.low, x.close,
                           fastk_period=fastk_period,
                           slowk_period=slowk_period,
                           slowk_matype=slowk_matype,
                           slowd_period=slowd_period,
                           slowd_matype=slowd_matype)
    return slowd/slowk-1

# ---- Cell ----
data['STOCH'] = by_ticker.apply(compute_stoch)
data.loc[data.STOCH.abs() > 1e5, 'STOCH'] = np.nan

# ---- Cell ----
q = 0.005
with sns.axes_style('white'):
    sns.distplot(data.STOCH.clip(lower=data.STOCH.quantile(q),
                             upper=data.STOCH.quantile(1-q)));

    sns.despine();

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
df['ULTOSC'] = talib.ULTOSC(df.high,
                            df.low,
                            df.close,
                            timeperiod1=7,
                            timeperiod2=14,
                            timeperiod3=28)

# ---- Cell ----
ax = df[['close', 'ULTOSC']].plot(figsize=(14, 4),
                                  rot=0,
                                  secondary_y='ULTOSC', style=['-', '--'])
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
def compute_ultosc(x, timeperiod1=7, timeperiod2=14, timeperiod3=28):
    return talib.ULTOSC(x.high,
                        x.low,
                        x.close,
                        timeperiod1=timeperiod1,
                        timeperiod2=timeperiod2,
                        timeperiod3=timeperiod3)

# ---- Cell ----
data['ULTOSC'] = by_ticker.apply(compute_ultosc)

# ---- Cell ----
with sns.axes_style('white'):
    sns.distplot(data.ULTOSC)
    sns.despine();

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
df['WILLR'] = talib.WILLR(df.high,
                          df.low,
                          df.close,
                          timeperiod=14)

# ---- Cell ----
ax = df[['close', 'WILLR']].plot(figsize=(14, 4),
                                 rot=0,
                                 secondary_y='WILLR', style=['-', '--'])
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['WILLR'] = by_ticker.apply(lambda x: talib.WILLR(x.high, x.low, x.close, timeperiod=14))

# ---- Cell ----
with sns.axes_style('white'):
    sns.distplot(data.WILLR)
    sns.despine();

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close', 'volume']]

# ---- Cell ----
df['AD'] = talib.AD(df.high,
                    df.low,
                    df.close,
                    df.volume)

# ---- Cell ----
ax = df[['close', 'AD']].plot(figsize=(14, 4),
                              rot=0,
                              secondary_y='AD', style=['-', '--'])

ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['AD'] = by_ticker.apply(lambda x: talib.AD(x.high, x.low, x.close, x.volume)/x.volume.mean())

# ---- Cell ----
data.AD.replace((np.inf, -np.inf), np.nan).dropna().describe()

# ---- Cell ----
q = 0.005
AD = data.AD.replace((np.inf, -np.inf), np.nan).dropna()
with sns.axes_style('white'):
    sns.distplot(AD.clip(lower=AD.quantile(q),
                     upper=AD.quantile(1-q)));

    sns.despine();

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close', 'volume']]

# ---- Cell ----
df['ADOSC'] = talib.ADOSC(df.high,
                          df.low,
                          df.close,
                          df.volume,
                          fastperiod=3,
                          slowperiod=10)

# ---- Cell ----
ax = df[['close', 'ADOSC']].plot(figsize=(14, 4),
                                 rot=0,
                                 secondary_y='ADOSC', style=['-', '--'])

ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['ADOSC'] = by_ticker.apply(lambda x: talib.ADOSC(x.high,
                                                      x.low,
                                                      x.close,
                                                      x.volume,
                                                      fastperiod=3,
                                                      slowperiod=10)/x.rolling(14).volume.mean())

# ---- Cell ----
q = 0.0001
with sns.axes_style('white'):
    sns.distplot(data.ADOSC.clip(lower=data.ADOSC.quantile(q),
                             upper=data.ADOSC.quantile(1-q)))
    sns.despine();

# ---- Cell ----
df = price_sample.loc['2013', ['close', 'volume']]

# ---- Cell ----
df['OBV'] = talib.OBV(df.close,
                      df.volume)

# ---- Cell ----
ax = df[['close', 'OBV']].plot(figsize=(14, 4),
                               rot=0,
                               secondary_y='OBV', style=['-', '--'])
ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['OBV'] = by_ticker.apply(lambda x: talib.OBV(x.close,
                                                  x.volume)/x.expanding().volume.mean())

# ---- Cell ----
q = 0.0025
with sns.axes_style('white'):
    sns.distplot(data.OBV.clip(lower=data.OBV.quantile(q),
                               upper=data.OBV.quantile(1-q)))
    sns.despine()

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
df['ATR'] = talib.ATR(df.high,
                      df.low,
                      df.close,
                      timeperiod=14)

# ---- Cell ----
ax = df[['close', 'ATR']].plot(figsize=(14, 4),
                          rot=0,
                          secondary_y='ATR', style=['-', '--'])

ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
data['ATR'] = by_ticker.apply(lambda x: talib.ATR(x.high,
                                                  x.low,
                                                  x.close,
                                                  timeperiod=14)/x.rolling(14).close.mean())

# ---- Cell ----
q = 0.001
with sns.axes_style('white'):
    sns.distplot(data.ATR.clip(upper=data.ATR.quantile(1-q)))
    sns.despine()

# ---- Cell ----
df = price_sample.loc['2013', ['high', 'low', 'close']]

# ---- Cell ----
df['NATR'] = talib.NATR(df.high,
                        df.low,
                        df.close,
                        timeperiod=14)

# ---- Cell ----
ax = df[['close', 'NATR']].plot(figsize=(14, 4),
                           rot=0,
                           secondary_y='NATR', style=['-', '--'])

ax.set_xlabel('')
sns.despine()
plt.tight_layout()

# ---- Cell ----
# data['NATR'] = by_ticker.apply(lambda x: talib.NATR(x.high,
#                                                     x.low,
#                                                     x.close,
#                                                     timeperiod=14))

# ---- Cell ----
# q = 0.001
# sns.distplot(data.NATR.clip(upper=data.NATR.quantile(1-q)));

# ---- Cell ----
factor_data = (web.DataReader('F-F_Research_Data_5_Factors_2x3_daily', 'famafrench',
                              start=2005)[0].rename(columns={'Mkt-RF': 'MARKET'}))
factor_data.index.names = ['date']

# ---- Cell ----
factors = factor_data.columns[:-1]
factors

# ---- Cell ----
t = 1
ret = f'ret_{t:02}'

windows = [21, 63, 252]
for window in windows:
    print(window)
    betas = []
    for ticker, df in data.groupby('ticker', group_keys=False):
        model_data = df[[ret]].merge(factor_data, on='date').dropna()
        model_data[ret] -= model_data.RF

        rolling_ols = RollingOLS(endog=model_data[ret],
                                 exog=sm.add_constant(model_data[factors]), window=window)
        factor_model = rolling_ols.fit(params_only=True).params.rename(columns={'const':'ALPHA'})
        result = factor_model.assign(ticker=ticker).set_index('ticker', append=True).swaplevel()
        betas.append(result)
    betas = pd.concat(betas).rename(columns=lambda x: f'{x}_{window:02}')
    data = data.join(betas)

# ---- Cell ----
data['size_factor'] = by_ticker.close.apply(lambda x: x.fillna(method='bfill').div(x.iloc[0]))

# ---- Cell ----
data['size_proxy'] = data.marketcap.mul(data.size_factor).div(1e6)

# ---- Cell ----
data = (data
        .drop(['open', 'high', 'low', 'close', 'volume', 'marketcap'], axis=1)
        .replace((np.inf, -np.inf), np.nan))

# ---- Cell ----
data.dropna(how='all').info()

# ---- Cell ----
with pd.HDFStore('data.h5') as store:
    store.put('factors/common', data)

# ---- Cell ----

