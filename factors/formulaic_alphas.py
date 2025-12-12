# English filename: 03_101_formulaic_alphas_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/1일차 머신러닝 분석을 위한 알파 팩터 수집 및 작성/2_ alpha_factor_library/03_101_formulaic_alphas_clear(오래걸림).py
# Original filename: 03_101_formulaic_alphas_clear(오래걸림).py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/alpha_factor_library_101.zip && unzip -n alpha_factor_library_101.zip

# ---- Cell ----
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/libta-lib0_0.4.0-oneiric1_amd64.deb -qO libta.deb
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/ta-lib0-dev_0.4.0-oneiric1_amd64.deb -qO ta.deb
!dpkg -i libta.deb ta.deb
!pip install ta-lib tables

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression
from scipy.stats import spearmanr
import matplotlib.pyplot as plt
import seaborn as sns
from talib import WMA

# ---- Cell ----
idx= pd.IndexSlice
sns.set_style('whitegrid')

# ---- Cell ----
def rank(df):
    """Return the cross-sectional percentile rank

     Args:
         :param df: tickers in columns, sorted dates in rows.

     Returns:
         pd.DataFrame: the ranked values
     """
    return df.rank(axis=1, pct=True)

# ---- Cell ----
def scale(df):
    """
    Scaling time serie.
    :param df: a pandas DataFrame.
    :param k: scaling factor.
    :return: a pandas DataFrame rescaled df such that sum(abs(df)) = k
    """
    return df.div(df.abs().sum(axis=1), axis=0)

# ---- Cell ----
def log(df):
    return np.log1p(df)

# ---- Cell ----
def sign(df):
    return np.sign(df)

# ---- Cell ----
def power(df, exp):
    return df.pow(exp)

# ---- Cell ----
def ts_lag(df: pd.DataFrame, t: int = 1) -> pd.DataFrame:
    """Return the lagged values t periods ago.

    Args:
        :param df: tickers in columns, sorted dates in rows.
        :param t: lag

    Returns:
        pd.DataFrame: the lagged values
    """
    return df.shift(t)

# ---- Cell ----
def ts_delta(df, period=1):
    """
    Wrapper function to estimate difference.
    :param df: a pandas DataFrame.
    :param period: the difference grade.
    :return: a pandas DataFrame with today’s value minus the value 'period' days ago.
    """
    return df.diff(period)

# ---- Cell ----
def ts_sum(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Computes the rolling ts_sum for the given window size.

    Args:
        df (pd.DataFrame): tickers in columns, dates in rows.
        window      (int): size of rolling window.

    Returns:
        pd.DataFrame: the ts_sum over the last 'window' days.
    """
    return df.rolling(window).sum()

# ---- Cell ----
def ts_mean(df, window=10):
    """Computes the rolling mean for the given window size.

    Args:
        df (pd.DataFrame): tickers in columns, dates in rows.
        window      (int): size of rolling window.

    Returns:
        pd.DataFrame: the mean over the last 'window' days.
    """
    return df.rolling(window).mean()

# ---- Cell ----
def ts_weighted_mean(df, period=10):
    """
    Linear weighted moving average implementation.
    :param df: a pandas DataFrame.
    :param period: the LWMA period
    :return: a pandas DataFrame with the LWMA.
    """
    return (df.apply(lambda x: WMA(x, timeperiod=period)))

# ---- Cell ----
def ts_std(df, window=10):
    """
    Wrapper function to estimate rolling standard deviation.
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: a pandas DataFrame with the time-series min over the past 'window' days.
    """
    return (df
            .rolling(window)
            .std())

# ---- Cell ----
def ts_rank(df, window=10):
    """
    Wrapper function to estimate rolling rank.
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: a pandas DataFrame with the time-series rank over the past window days.
    """
    return (df
            .rolling(window)
            .apply(lambda x: x.rank().iloc[-1]))

# ---- Cell ----
def ts_product(df, window=10):
    """
    Wrapper function to estimate rolling ts_product.
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: a pandas DataFrame with the time-series ts_product over the past 'window' days.
    """
    return (df
            .rolling(window)
            .apply(np.prod))

# ---- Cell ----
def ts_min(df, window=10):
    """
    Wrapper function to estimate rolling min.
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: a pandas DataFrame with the time-series min over the past 'window' days.
    """
    return df.rolling(window).min()

# ---- Cell ----
def ts_max(df, window=10):
    """
    Wrapper function to estimate rolling min.
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: a pandas DataFrame with the time-series max over the past 'window' days.
    """
    return df.rolling(window).max()

# ---- Cell ----
def ts_argmax(df, window=10):
    """
    Wrapper function to estimate which day ts_max(df, window) occurred on
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: well.. that :)
    """
    return df.rolling(window).apply(np.argmax).add(1)

# ---- Cell ----
def ts_argmin(df, window=10):
    """
    Wrapper function to estimate which day ts_min(df, window) occurred on
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: well.. that :)
    """
    return (df.rolling(window)
            .apply(np.argmin)
            .add(1))

# ---- Cell ----
def ts_corr(x, y, window=10):
    """
    Wrapper function to estimate rolling correlations.
    :param x, y: pandas DataFrames.
    :param window: the rolling window.
    :return: a pandas DataFrame with the time-series min over the past 'window' days.
    """
    return x.rolling(window).corr(y)

# ---- Cell ----
def ts_cov(x, y, window=10):
    """
    Wrapper function to estimate rolling covariance.
    :param df: a pandas DataFrame.
    :param window: the rolling window.
    :return: a pandas DataFrame with the time-series min over the past 'window' days.
    """
    return x.rolling(window).cov(y)

# ---- Cell ----
ohlcv = ['open', 'high', 'low', 'close', 'volume']
data = (pd.read_hdf('data.h5', 'data/top500')
        .loc[:, ohlcv + ['ret_01', 'sector', 'ret_fwd']]
        .rename(columns={'ret_01': 'returns'})
        .sort_index())

# ---- Cell ----
adv20 = data.groupby('ticker').rolling(20).volume.mean().reset_index(0, drop=True)

# ---- Cell ----
data = data.assign(adv20=adv20)

# ---- Cell ----
data = data.join(data.groupby('date')[ohlcv].rank(axis=1, pct=True), rsuffix='_rank')

# ---- Cell ----
data.info()

# ---- Cell ----
#data.to_hdf('factors.h5', 'data')

# ---- Cell ----
o = data.open.unstack('ticker')
h = data.high.unstack('ticker')
l = data.low.unstack('ticker')
c = data.close.unstack('ticker')
v = data.volume.unstack('ticker')
vwap = o.add(h).add(l).add(c).div(4)
adv20 = v.rolling(20).mean()
r = data.returns.unstack('ticker')

# ---- Cell ----
alphas = data[['returns', 'ret_fwd']].copy()
mi,ic = {}, {}

# ---- Cell ----
def get_mutual_info_score(returns, alpha, n=100000):
    df = pd.DataFrame({'y': returns, 'alpha': alpha}).dropna().sample(n=n)
    return mutual_info_regression(y=df.y, X=df[['alpha']])[0]

# ---- Cell ----
def alpha001(c, r):
    """(rank(ts_argmax(power(((returns < 0)
        ? ts_std(returns, 20)
        : close), 2.), 5)) -0.5)"""
    c[r < 0] = ts_std(r, 20)
    return (rank(ts_argmax(power(c, 2), 5)).mul(-.5)
            .stack().swaplevel())

# ---- Cell ----
alpha = 1

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha001(c, r)

# ---- Cell ----
alphas.info()

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas)

# ---- Cell ----
mi[1] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[1]

# ---- Cell ----
def alpha002(o, c, v):
    """(-1 * ts_corr(rank(ts_delta(log(volume), 2)), rank(((close - open) / open)), 6))"""
    s1 = rank(ts_delta(log(v), 2))
    s2 = rank((c / o) - 1)
    alpha = -ts_corr(s1, s2, 6)
    return alpha.stack('ticker').swaplevel().replace([-np.inf, np.inf], np.nan)

# ---- Cell ----
alpha = 2

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha002(o, c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas)

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[2]

# ---- Cell ----
def alpha003(o, v):
    """(-1 * ts_corr(rank(open), rank(volume), 10))"""

    return (-ts_corr(rank(o), rank(v), 10)
            .stack('ticker')
            .swaplevel()
            .replace([-np.inf, np.inf], np.nan))

# ---- Cell ----
alpha = 3

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha003(o, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}'].clip(lower=-1));

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha004(l):
    """(-1 * Ts_Rank(rank(low), 9))"""
    return (-ts_rank(rank(l), 9)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 4

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha004(l)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha005(o, vwap, c):
    """(rank((open - ts_mean(vwap, 10))) * (-1 * abs(rank((close - vwap)))))"""
    return (rank(o.sub(ts_mean(vwap, 10)))
            .mul(rank(c.sub(vwap)).mul(-1).abs())
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 5

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha005(o, vwap, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha006(o, v):
    """(-ts_corr(open, volume, 10))"""
    return (-ts_corr(o, v, 10)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 6

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha006(o, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha007(c, v, adv20):
    """(adv20 < volume)
        ? ((-ts_rank(abs(ts_delta(close, 7)), 60)) * sign(ts_delta(close, 7)))
        : -1
    """

    delta7 = ts_delta(c, 7)
    return (-ts_rank(abs(delta7), 60)
            .mul(sign(delta7))
            .where(adv20<v, -1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 7

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha007(c, v, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
ax = sns.distplot(alphas[f'{alpha:03}'], kde=False)
ax.set_yscale('log')
ax.set_ylabel('Frequency (log scale)')
plt.tight_layout();

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
# mi[alpha]

# ---- Cell ----
def alpha008(o, r):
    """-rank(((ts_sum(open, 5) * ts_sum(returns, 5)) -
        ts_lag((ts_sum(open, 5) * ts_sum(returns, 5)),10)))
    """
    return (-(rank(((ts_sum(o, 5) * ts_sum(r, 5)) -
                       ts_lag((ts_sum(o, 5) * ts_sum(r, 5)), 10))))
           .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 8

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha008(o, r)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha009(c):
    """(0 < ts_min(ts_delta(close, 1), 5)) ? ts_delta(close, 1)
    : ((ts_max(ts_delta(close, 1), 5) < 0)
    ? ts_delta(close, 1) : (-1 * ts_delta(close, 1)))
    """
    close_diff = ts_delta(c, 1)
    alpha = close_diff.where(ts_min(close_diff, 5) > 0,
                             close_diff.where(ts_max(close_diff, 5) < 0,
                                              -close_diff))
    return (alpha
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 9

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha009(c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
q = 0.01
sns.distplot(alphas[f'{alpha:03}'].clip(lower=alphas[f'{alpha:03}'].quantile(q),
                                        upper=alphas[f'{alpha:03}'].quantile(1-q)));

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi)

# ---- Cell ----
def alpha010(c):
    """rank(((0 < ts_min(ts_delta(close, 1), 4))
        ? ts_delta(close, 1)
        : ((ts_max(ts_delta(close, 1), 4) < 0)
            ? ts_delta(close, 1)
            : (-1 * ts_delta(close, 1)))))
    """
    close_diff = ts_delta(c, 1)
    alpha = close_diff.where(ts_min(close_diff, 4) > 0,
                             close_diff.where(ts_min(close_diff, 4) > 0,
                                              -close_diff))

    return (rank(alpha)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 10

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha010(c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha011(c, vwap, v):
    """(rank(ts_max((vwap - close), 3)) +
        rank(ts_min(vwap - close), 3)) *
        rank(ts_delta(volume, 3))
        """
    return (rank(ts_max(vwap.sub(c), 3))
            .add(rank(ts_min(vwap.sub(c), 3)))
            .mul(rank(ts_delta(v, 3)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 11

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha011(c, vwap, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha012(v, c):
    """(sign(ts_delta(volume, 1)) *
            (-1 * ts_delta(close, 1)))
        """
    return (sign(ts_delta(v, 1)).mul(-ts_delta(c, 1))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 12

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha012(v, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
q = 0.01
sns.distplot(alphas[f'{alpha:03}'].clip(lower=alphas[f'{alpha:03}'].quantile(q),
                                        upper=alphas[f'{alpha:03}'].quantile(1-q)));

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha013(c, v):
    """-rank(ts_cov(rank(close), rank(volume), 5))"""
    return (-rank(ts_cov(rank(c), rank(v), 5))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 13

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha013(c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha014(o, v, r):
    """
    (-rank(ts_delta(returns, 3))) * ts_corr(open, volume, 10))
    """

    alpha = -rank(ts_delta(r, 3)).mul(ts_corr(o, v, 10)
                                      .replace([-np.inf,
                                                np.inf],
                                               np.nan))
    return (alpha
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 14

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha014(o, v, r)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha015(h, v):
    """(-1 * ts_sum(rank(ts_corr(rank(high), rank(volume), 3)), 3))"""
    alpha = (-ts_sum(rank(ts_corr(rank(h), rank(v), 3)
                          .replace([-np.inf, np.inf], np.nan)), 3))
    return (alpha
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 15

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha015(h, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha016(h, v):
    """(-1 * rank(ts_cov(rank(high), rank(volume), 5)))"""
    return (-rank(ts_cov(rank(h), rank(v), 5))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 16

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha016(h, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);

# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha017(c, v):
    """(((-1 * rank(ts_rank(close, 10))) * rank(ts_delta(ts_delta(close, 1), 1))) *rank(ts_rank((volume / adv20), 5)))
        """
    adv20 = ts_mean(v, 20)
    return (-rank(ts_rank(c, 10))
            .mul(rank(ts_delta(ts_delta(c, 1), 1)))
            .mul(rank(ts_rank(v.div(adv20), 5)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 17

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha017(c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha018(o, c):
    """-rank((ts_std(abs((close - open)), 5) + (close - open)) +
            ts_corr(close, open,10))
    """
    return (-rank(ts_std(c.sub(o).abs(), 5)
                  .add(c.sub(o))
                  .add(ts_corr(c, o, 10)
                       .replace([-np.inf,
                                 np.inf],
                                np.nan)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 18

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha018(o, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha019(c, r):
    """((-1 * sign(((close - ts_lag(close, 7)) + ts_delta(close, 7)))) *
    (1 + rank((1 + ts_sum(returns,250)))))
    """
    return (-sign(ts_delta(c, 7) + ts_delta(c, 7))
            .mul(1 + rank(1 + ts_sum(r, 250)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 19

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha019(c, r)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha020(o, h, l, c):
    """-rank(open - ts_lag(high, 1)) *
        rank(open - ts_lag(close, 1)) *
        rank(open -ts_lag(low, 1))"""
    return (rank(o - ts_lag(h, 1))
            .mul(rank(o - ts_lag(c, 1)))
            .mul(rank(o - ts_lag(l, 1)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 20

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha020(o, h, l, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha021(c, v):
    """ts_mean(close, 8) + ts_std(close, 8) < ts_mean(close, 2)
        ? -1
        : (ts_mean(close,2) < ts_mean(close, 8) - ts_std(close, 8)
            ? 1
            : (volume / adv20 < 1
                ? -1
                : 1))
    """
    sma2 = ts_mean(c, 2)
    sma8 = ts_mean(c, 8)
    std8 = ts_std(c, 8)

    cond_1 = sma8.add(std8) < sma2
    cond_2 = sma8.add(std8) > sma2
    cond_3 = v.div(ts_mean(v, 20)) < 1

    val = np.ones_like(c)
    alpha = pd.DataFrame(np.select(condlist=[cond_1, cond_2, cond_3],
                                   choicelist=[-1, 1, -1], default=1),
                         index=c.index,
                         columns=c.columns)

    return (alpha
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 21

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha021(c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
alphas[f'{alpha:03}'].value_counts()

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
# mi[alpha]

# ---- Cell ----
def alpha022(h, c, v):
    """-(ts_delta(ts_corr(high, volume, 5), 5) *
        rank(ts_std(close, 20)))
    """

    return (ts_delta(ts_corr(h, v, 5)
                     .replace([-np.inf,
                               np.inf],
                              np.nan), 5)
            .mul(rank(ts_std(c, 20)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 22

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha022(h, c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha023(h, c):
    """((ts_mean(high, 20) < high)
            ? (-1 * ts_delta(high, 2))
            : 0
        """

    return (ts_delta(h, 2)
            .mul(-1)
            .where(ts_mean(h, 20) < h, 0)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 23

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha023(h, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
q = 0.025
sns.distplot(alphas[f'{alpha:03}'].clip(lower=alphas[f'{alpha:03}'].quantile(q),
                                        upper=alphas[f'{alpha:03}'].quantile(1-q)));

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha024(c):
    """((((ts_delta((ts_mean(close, 100)), 100) / ts_lag(close, 100)) <= 0.05)
        ? (-1 * (close - ts_min(close, 100)))
        : (-1 * ts_delta(close, 3)))
    """
    cond = ts_delta(ts_mean(c, 100), 100) / ts_lag(c, 100) <= 0.05

    return (c.sub(ts_min(c, 100)).mul(-1).where(cond, -ts_delta(c, 3))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 24

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha024(c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
q = 0.01
sns.distplot(alphas[f'{alpha:03}'].clip(lower=alphas[f'{alpha:03}'].quantile(q),
                                        upper=alphas[f'{alpha:03}'].quantile(1-q)));

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha025(h, c, r, vwap, adv20):
    """rank((-1 * returns) * adv20 * vwap * (high - close))"""
    return (rank(-r.mul(adv20)
                 .mul(vwap)
                 .mul(h.sub(c)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 25

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha025(h, c, r, vwap, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha026(h, v):
    """(-1 * ts_max(ts_corr(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))"""
    return (ts_max(ts_corr(ts_rank(v, 5),
                           ts_rank(h, 5), 5)
                   .replace([-np.inf, np.inf], np.nan), 3)
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 26

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha026(h, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha027(v, vwap):
    """((0.5 < rank(ts_mean(ts_corr(rank(volume), rank(vwap), 6), 2)))
            ? -1
            : 1)"""
    cond = rank(ts_mean(ts_corr(rank(v),
                                rank(vwap), 6), 2))
    alpha = cond.notnull().astype(float)
    return (alpha.where(cond <= 0.5, -alpha)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 27

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha027(v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
# mi[alpha]

# ---- Cell ----
def alpha028(h, l, c, v, adv20):
    """scale(((ts_corr(adv20, low, 5) + (high + low) / 2) - close))"""
    return (scale(ts_corr(adv20, l, 5)
                  .replace([-np.inf, np.inf], 0)
                  .add(h.add(l).div(2).sub(c)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 28

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha028(h, l, c, v, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha029(c, r):
    """(ts_min(ts_product(rank(rank(scale(log(ts_sum(ts_min(rank(rank((-1 *
            rank(ts_delta((close - 1),5))))), 2), 1))))), 1), 5)
        + ts_rank(ts_lag((-1 * returns), 6), 5))
    """
    return (ts_min(rank(rank(scale(log(ts_sum(rank(rank(-rank(ts_delta((c - 1), 5)))), 2))))), 5)
            .add(ts_rank(ts_lag((-1 * r), 6), 5))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 29

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha029(c, r)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha030(c, v):
    """(((1.0 - rank(((sign((close - ts_lag(close, 1))) +
            sign((ts_lag(close, 1) - ts_lag(close, 2)))) +
            sign((ts_lag(close, 2) - ts_lag(close, 3)))))) *
            ts_sum(volume, 5)) / ts_sum(volume, 20))"""
    close_diff = ts_delta(c, 1)
    return (rank(sign(close_diff)
                 .add(sign(ts_lag(close_diff, 1)))
                 .add(sign(ts_lag(close_diff, 2))))
            .mul(-1).add(1)
            .mul(ts_sum(v, 5))
            .div(ts_sum(v, 20))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 30

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha030(c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha031(l, c, adv20):
    """((rank(rank(rank(ts_weighted_mean((-1 * rank(rank(ts_delta(close, 10)))), 10)))) +
        rank((-1 * ts_delta(close, 3)))) + sign(scale(ts_corr(adv20, low, 12))))
    """
    return (rank(rank(rank(ts_weighted_mean(rank(rank(ts_delta(c, 10))).mul(-1), 10))))
            .add(rank(ts_delta(c, 3).mul(-1)))
            .add(sign(scale(ts_corr(adv20, l, 12)
                            .replace([-np.inf, np.inf],
                                     np.nan))))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 31

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha031(l, c, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
def alpha032(c, vwap):
    """scale(ts_mean(close, 7) - close) +
        (20 * scale(ts_corr(vwap, ts_lag(close, 5),230)))"""
    return (scale(ts_mean(c, 7).sub(c))
            .add(20 * scale(ts_corr(vwap,
                                    ts_lag(c, 5), 230)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 32

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha032(c, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd,
                                  alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha033(o, c):
    """rank(-(1 - (open / close)))"""
    return (rank(o.div(c).mul(-1).add(1).mul(-1))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 33

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha033(o, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha034(c, r):
    """rank(((1 - rank((ts_std(returns, 2) / ts_std(returns, 5)))) + (1 - rank(ts_delta(close, 1)))))"""

    return (rank(rank(ts_std(r, 2).div(ts_std(r, 5))
                      .replace([-np.inf, np.inf],
                               np.nan))
                 .mul(-1)
                 .sub(rank(ts_delta(c, 1)))
                 .add(2))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 34

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha034(c, r)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha035(h, l, c, v, r):
    """((ts_Rank(volume, 32) *
        (1 - ts_Rank(((close + high) - low), 16))) *
        (1 -ts_Rank(returns, 32)))
    """
    return (ts_rank(v, 32)
            .mul(1 - ts_rank(c.add(h).sub(l), 16))
            .mul(1 - ts_rank(r, 32))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 35

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha035(h, l, c, v, r)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha036(o, c, v, r, adv20):
    """2.21 * rank(ts_corr((close - open), ts_lag(volume, 1), 15)) +
        0.7 * rank((open- close)) +
        0.73 * rank(ts_Rank(ts_lag(-1 * returns, 6), 5)) +
        rank(abs(ts_corr(vwap,adv20, 6))) +
        0.6 * rank(((ts_mean(close, 200) - open) * (close - open)))
    """

    return (rank(ts_corr(c.sub(o), ts_lag(v, 1), 15)).mul(2.21)
            .add(rank(o.sub(c)).mul(.7))
            .add(rank(ts_rank(ts_lag(-r, 6), 5)).mul(0.73))
            .add(rank(abs(ts_corr(vwap, adv20, 6))))
            .add(rank(ts_mean(c, 200).sub(o).mul(c.sub(o))).mul(0.6))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 36

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha036(o, c, v, r, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha037(o, c):
    """(rank(ts_corr(ts_lag((open - close), 1), close, 200)) + rank((open - close)))"""
    return (rank(ts_corr(ts_lag(o.sub(c), 1), c, 200))
            .add(rank(o.sub(c)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 37

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha037(o, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
pd.Series(mi).to_csv('mi.csv')

# ---- Cell ----
def alpha038(o, c):
    """"-1 * rank(ts_rank(close, 10)) * rank(close / open)"""
    return (rank(ts_rank(o, 10))
            .mul(rank(c.div(o).replace([-np.inf, np.inf], np.nan)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 38

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha038(o, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha039(c, v, r, adv20):
    """-rank(ts_delta(close, 7) * (1 - rank(ts_weighted_mean(volume / adv20, 9)))) *
            (1 + rank(ts_sum(returns, 250)))"""
    return (rank(ts_delta(c, 7).mul(rank(ts_weighted_mean(v.div(adv20), 9)).mul(-1).add(1))).mul(-1)
            .mul(rank(ts_mean(r, 250).add(1)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 39

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha039(c, v, r, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])

# ---- Cell ----
mi[alpha]

# ---- Cell ----
def alpha040(h, v):
    """((-1 * rank(ts_std(high, 10))) * ts_corr(high, volume, 10))
    """
    return (rank(ts_std(h, 10))
            .mul(ts_corr(h, v, 10))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 40

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha040(h, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha041(h, l, vwap):
    """power(high * low, 0.5 - vwap"""
    return (power(h.mul(l), 0.5)
            .sub(vwap)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 41

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha041(h, l, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha042(c, vwap):
    """rank(vwap - close) / rank(vwap + close)"""
    return (rank(vwap.sub(c))
            .div(rank(vwap.add(c)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 42

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha042(c, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha043(c, adv20):
    """(ts_rank((volume / adv20), 20) * ts_rank((-1 * ts_delta(close, 7)), 8))"""

    return (ts_rank(v.div(adv20), 20)
            .mul(ts_rank(ts_delta(c, 7).mul(-1), 8))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 43

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha043(c, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha044(h, v):
    """-ts_corr(high, rank(volume), 5)"""

    return (ts_corr(h, rank(v), 5)
            .replace([-np.inf, np.inf], np.nan)
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 44

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha044(h, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha045(c, v):
    """-(rank((ts_mean(ts_lag(close, 5), 20)) *
        ts_corr(close, volume, 2)) *
        rank(ts_corr(ts_sum(close, 5), ts_sum(close, 20), 2)))"""

    return (rank(ts_mean(ts_lag(c, 5), 20))
            .mul(ts_corr(c, v, 2)
                 .replace([-np.inf, np.inf], np.nan))
            .mul(rank(ts_corr(ts_sum(c, 5),
                              ts_sum(c, 20), 2)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 45

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha045(c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha046(c):
    """0.25 < ts_lag(ts_delta(close, 10), 10) / 10 - ts_delta(close, 10) / 10
            ? -1
            : ((ts_lag(ts_delta(close, 10), 10) / 10 - ts_delta(close, 10) / 10 < 0)
                ? 1
                : -ts_delta(close, 1))
    """

    cond = ts_lag(ts_delta(c, 10), 10).div(10).sub(ts_delta(c, 10).div(10))
    alpha = pd.DataFrame(-np.ones_like(cond),
                         index=c.index,
                         columns=c.columns)
    alpha[cond.isnull()] = np.nan
    return (cond.where(cond > 0.25,
                       -alpha.where(cond < 0,
                       -ts_delta(c, 1)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 46

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha046(c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha047(h, c, v, vwap, adv20):
    """((((rank((1 / close)) * volume) / adv20) * ((high * rank((high - close))) /
        (ts_sum(high, 5) /5))) - rank((vwap - ts_lag(vwap, 5))))"""

    return (rank(c.pow(-1)).mul(v).div(adv20)
            .mul(h.mul(rank(h.sub(c))
                       .div(ts_mean(h, 5)))
                 .sub(rank(ts_delta(vwap, 5))))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 47

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha047(h, c, v, vwap, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha48(c, industry):
    """(indneutralize(((ts_corr(ts_delta(close, 1), ts_delta(ts_lag(close, 1), 1), 250) *
        ts_delta(close, 1)) / close), IndClass.subindustry) /
        ts_sum(((ts_delta(close, 1) / ts_lag(close, 1))^2), 250))"""
    pass

# ---- Cell ----
alpha = 48

# ---- Cell ----
# %%time
# alphas[f'{alpha:03}'] = alpha48(o, c)

# ---- Cell ----
# alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
# sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
# g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);
#

# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
# mi[alpha]

# ---- Cell ----
def alpha049(c):
    """ts_delta(ts_lag(close, 10), 10).div(10).sub(ts_delta(close, 10).div(10)) < -0.1 * c
        ? 1
        : -ts_delta(close, 1)"""
    cond = (ts_delta(ts_lag(c, 10), 10).div(10)
            .sub(ts_delta(c, 10).div(10)) >= -0.1 * c)
    return (-ts_delta(c, 1)
            .where(cond, 1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 49

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha049(c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}'], kde=False);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
def alpha050(v, vwap):
    """-ts_max(rank(ts_corr(rank(volume), rank(vwap), 5)), 5)"""
    return (ts_max(rank(ts_corr(rank(v),
                                rank(vwap), 5)), 5)
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 50

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha050(v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha051(c):
    """ts_delta(ts_lag(close, 10), 10).div(10).sub(ts_delta(close, 10).div(10)) < -0.05 * c
        ? 1
        : -ts_delta(close, 1)"""
    cond = (ts_delta(ts_lag(c, 10), 10).div(10)
            .sub(ts_delta(c, 10).div(10)) >= -0.05 * c)
    return (-ts_delta(c, 1)
            .where(cond, 1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 51

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha051(c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
alphas = []
with pd.HDFStore('alphas.h5') as store:
    keys = [k[1:] for k in store.keys()]
    for key in keys:
        i = int(key.split('/')[-1])
        alphas.append(store[key].to_frame(i))
alphas = pd.concat(alphas, axis=1)
alphas.info(null_counts=True)
alphas.to_hdf('data.h5', 'factors/formulaic')

# ---- Cell ----
# 여기까지만 한다. (메모리 부족)

# ---- Cell ----
def alpha052(l, v, r):
    """(ts_lag(ts_min(low, 5), 5) - ts_min(low, 5)) *
        rank((ts_sum(returns, 240) - ts_sum(returns, 20)) / 220) *
        ts_rank(volume, 5)
    """
    return (ts_delta(ts_min(l, 5), 5)
            .mul(rank(ts_sum(r, 240)
                      .sub(ts_sum(r, 20))
                      .div(220)))
            .mul(ts_rank(v, 5))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 52

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha052(l, v, r)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha053(h, l, c):
    """-1 * ts_delta(1 - (high - close) / (close - low), 9)"""
    inner = (c.sub(l)).add(1e-6)
    return (ts_delta(h.sub(c)
                     .mul(-1).add(1)
                     .div(c.sub(l)
                          .add(1e-6)), 9)
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 53

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha053(h, l, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
# mi[alpha]

# ---- Cell ----
def alpha054(o, h, l, c):
    """-(low - close) * power(open, 5) / ((low - high) * power(close, 5))"""
    return (l.sub(c).mul(o.pow(5)).mul(-1)
            .div(l.sub(h).replace(0, -0.0001).mul(c ** 5))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 54

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha054(o, h, l, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
pd.Series(mi).tail()

# ---- Cell ----
def alpha055(h, l, c):
    """(-1 * ts_corr(rank(((close - ts_min(low, 12)) /
                            (ts_max(high, 12) - ts_min(low,12)))),
                    rank(volume), 6))"""

    return (ts_corr(rank(c.sub(ts_min(l, 12))
                         .div(ts_max(h, 12).sub(ts_min(l, 12))
                              .replace(0, 1e-6))),
                    rank(v), 6)
            .replace([-np.inf, np.inf], np.nan)
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 55

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha055(h, l, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha056(r, cap):
    """-rank(ts_sum(returns, 10) / ts_sum(ts_sum(returns, 2), 3)) *
        rank((returns * cap))
    """
    pass

# ---- Cell ----
def alpha057(c, vwap):
    """-(close - vwap) / ts_weighted_mean(rank(ts_argmax(close, 30)), 2)"""
    return (c.sub(vwap.add(1e-5))
            .div(ts_weighted_mean(rank(ts_argmax(c, 30)))).mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 57

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha057(c, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha58(v, wvap, sector):
    """(-1 * ts_rank(ts_weighted_mean(ts_corr(IndNeutralize(vwap, IndClass.sector), volume, 3), 7), 5))"""
    pass

# ---- Cell ----
def alpha59(v, wvap, industry):
    """-ts_rank(ts_weighted_mean(ts_corr(IndNeutralize(vwap, IndClass.industry), volume, 4), 16), 8)"""
    pass

# ---- Cell ----
def alpha060(l, h, c, v):
    """-((2 * scale(rank(((((close - low) - (high - close)) / (high - low)) * volume)))) -scale(rank(ts_argmax(close, 10))))"""
    return (scale(rank(c.mul(2).sub(l).sub(h)
                       .div(h.sub(l).replace(0, 1e-5))
                       .mul(v))).mul(2)
            .sub(scale(rank(ts_argmax(c, 10)))).mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 60

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha060(l, h, c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha061(v, vwap):
    """rank((vwap - ts_min(vwap, 16))) < rank(ts_corr(vwap, adv180, 17))"""

    return (rank(vwap.sub(ts_min(vwap, 16)))
            .lt(rank(ts_corr(vwap, ts_mean(v, 180), 18)))
            .astype(int)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 61

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha061(v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
alphas.groupby(alphas[f'{alpha:03}']).ret_fwd.describe()

# ---- Cell ----
g = sns.boxenplot(x=f'{alpha:03}', y='ret_fwd', data=alphas[alphas.ret_fwd.between(-.1, .1)]);

# ---- Cell ----
def alpha062(o, h, l, vwap, adv20):
    """((rank(ts_corr(vwap, ts_sum(adv20, 22.4101), 9.91009)) <
    rank(((rank(open) + rank(open)) < (rank(((high + low) / 2)) + rank(high))))) * -1)"""
    return (rank(ts_corr(vwap, ts_sum(adv20, 22), 9))
            .lt(rank(
                rank(o).mul(2))
                .lt(rank(h.add(l).div(2))
                    .add(rank(h))))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 62

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha062(o, h, l, vwap, adv20)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}'], kde=False);

# ---- Cell ----
alphas.groupby(alphas[f'{alpha:03}']).ret_fwd.describe()

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
# mi[alpha]

# ---- Cell ----
def alpha63(v, wvap, industry):
    """((rank(ts_weighted_mean(ts_delta(IndNeutralize(close, IndClass.industry), 2), 8)) -
        rank(ts_weighted_mean(ts_corr(((vwap * 0.318108) + (open * (1 - 0.318108))),
                                        ts_sum(adv180, 37), 13), 12))) * -1)
    """
    pass

# ---- Cell ----
alpha = 63

# ---- Cell ----
# %%time
# alphas[f'{alpha:03}'] = alpha48(o, c)

# ---- Cell ----
# alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
# sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
# g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);
#

# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
# mi[alpha]

# ---- Cell ----
def alpha064(o, h, l, v, vwap):
    """((rank(ts_corr(ts_sum(((open * 0.178404) + (low * (1 - 0.178404))), 12.7054),ts_sum(adv120, 12.7054), 16.6208)) <
        rank(ts_delta(((((high + low) / 2) * 0.178404) + (vwap * (1 -0.178404))), 3.69741))) * -1)"""
    w = 0.178404
    return (rank(ts_corr(ts_sum(o.mul(w).add(l.mul(1 - w)), 12),
                         ts_sum(ts_mean(v, 120), 12), 16))
            .lt(rank(ts_delta(h.add(l).div(2).mul(w)
                               .add(vwap.mul(1 - w)), 3)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 64

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha064(o, h, l, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
alphas.groupby(alphas[f'{alpha:03}']).ret_fwd.describe()

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
def alpha065(o, v, vwap):
    """((rank(ts_corr(((open * 0.00817205) + (vwap * (1 - 0.00817205))),
                        ts_sum(adv60,8.6911), 6.40374)) <
        rank((open - ts_min(open, 13.635)))) * -1)
    """
    w = 0.00817205
    return (rank(ts_corr(o.mul(w).add(vwap.mul(1 - w)),
                         ts_mean(ts_mean(v, 60), 9), 6))
            .lt(rank(o.sub(ts_min(o, 13))))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 65

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha065(o, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
def alpha066(l, h, vwap):
    """((rank(ts_weighted_mean(ts_delta(vwap, 3.51013), 7.23052)) +
        ts_rank(ts_weighted_mean(((((low* 0.96633) + (low *
                                    (1 - 0.96633))) - vwap) /
                                    (open - ((high + low) / 2))), 11.4157), 6.72611)) * -1)
    """
    w = 0.96633
    return (rank(ts_weighted_mean(ts_delta(vwap, 4), 7))
            .add(ts_rank(ts_weighted_mean(l.mul(w).add(l.mul(1 - w))
                                           .sub(vwap)
                                           .div(o.sub(h.add(l).div(2)).add(1e-3)), 11), 7))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 66

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha066(l, h, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha067(h, v, sector, subindustry):
    """(power(rank((high - ts_min(high, 2.14593))),
        rank(ts_corr(IndNeutralize(vwap,IndClass.sector),
                IndNeutralize(adv20, IndClass.subindustry), 6.02936))) * -1)
    """
    pass

# ---- Cell ----
alpha = 67

# ---- Cell ----
# %%time
# alphas[f'{alpha:03}'] = alpha056(r, cap)

# ---- Cell ----
# alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
# sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
# g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);
#

# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
# mi[alpha]

# ---- Cell ----
def alpha068(h, c, v):
    """((ts_rank(ts_corr(rank(high), rank(adv15), 8.91644), 13.9333) <
        rank(ts_delta(((close * 0.518371) + (low * (1 - 0.518371))), 1.06157))) * -1)
    """
    w = 0.518371
    return (ts_rank(ts_corr(rank(h), rank(ts_mean(v, 15)), 9), 14)
            .lt(rank(ts_delta(c.mul(w).add(l.mul(1 - w)), 1)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 68

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha068(h, c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
def alpha069(c, vwap, industry):
    """((power(rank(ts_max(ts_delta(IndNeutralize(vwap, IndClass.industry), 2.72412),4.79344)),
    Ts_Rank(ts_corr(((close * 0.490655) + (vwap * (1 - 0.490655))), adv20, 4.92416),9.0615))) * -1)
    """
    pass

# ---- Cell ----
def alpha076(c, v, vwap, industry):
    """((power(rank(ts_delta(vwap, 1.29456)),
        ts_rank(ts_corr(IndNeutralize(close, IndClass.industry), adv50, 17.8256), 17.9171))) * -1)
    """
    pass

# ---- Cell ----
alpha = 70

# ---- Cell ----
def alpha071(o, c, v, vwap):
    """max(ts_rank(ts_weighted_mean(ts_corr(ts_rank(close, 3.43976), ts_rank(adv180,12.0647), 18.0175), 4.20501), 15.6948),
            ts_rank(ts_weighted_mean((rank(((low + open) - (vwap +vwap)))^2), 16.4662), 4.4388))"""

    s1 = (ts_rank(ts_weighted_mean(ts_corr(ts_rank(c, 3),
                                           ts_rank(ts_mean(v, 180), 12), 18), 4), 16))
    s2 = (ts_rank(ts_weighted_mean(rank(l.add(o).
                                        sub(vwap.mul(2)))
                                   .pow(2), 16), 4))
    return (s1.where(s1 > s2, s2)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 71

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha071(o, c, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha072(h, l, v, vwap):
    """(rank(ts_weighted_mean(ts_corr(((high + low) / 2), adv40, 8.93345), 10.1519)) /
        rank(ts_weighted_mean(ts_corr(ts_rank(vwap, 3.72469), ts_rank(volume, 18.5188), 6.86671), 2.95011)))
    """
    return (rank(ts_weighted_mean(ts_corr(h.add(l).div(2), ts_mean(v, 40), 9), 10))
            .div(rank(ts_weighted_mean(ts_corr(ts_rank(vwap, 3), ts_rank(v, 18), 6), 2)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 72

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha072(h, l, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
def alpha073(l, vwap):
    """(max(rank(ts_weighted_mean(ts_delta(vwap, 4.72775), 2.91864)),
        ts_rank(ts_weighted_mean(((ts_delta(((open * 0.147155) +
            (low * (1 - 0.147155))), 2.03608) /
            ((open *0.147155) + (low * (1 - 0.147155)))) * -1), 3.33829), 16.7411)) * -1)
        """
    w = 0.147155
    s1 = rank(ts_weighted_mean(ts_delta(vwap, 5), 3))
    s2 = (ts_rank(ts_weighted_mean(ts_delta(o.mul(w).add(l.mul(1 - w)), 2)
                                   .div(o.mul(w).add(l.mul(1 - w)).mul(-1)), 3), 16))

    print(s2)
    return (s1.where(s1 > s2, s2)
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 73

# ---- Cell ----
# %%time
alphas[f'{alpha:03}'] = alpha073(l, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha074(v, vwap):
    """((rank(ts_corr(close, ts_sum(adv30, 37.4843), 15.1365)) <
        rank(ts_corr(rank(((high * 0.0261661) + (vwap * (1 - 0.0261661)))), rank(volume), 11.4791)))* -1)"""

    w = 0.0261661
    return (rank(ts_corr(c, ts_mean(ts_mean(v, 30), 37), 15))
            .lt(rank(ts_corr(rank(h.mul(w).add(vwap.mul(1 - w))), rank(v), 11)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 74

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha074(v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
alphas.groupby(alphas[f'{alpha:03}']).ret_fwd.describe()

# ---- Cell ----
def alpha075(l, v, vwap):
    """(rank(ts_corr(vwap, volume, 4.24304)) <
        rank(ts_corr(rank(low), rank(adv50),12.4413)))
    """

    return (rank(ts_corr(vwap, v, 4))
            .lt(rank(ts_corr(rank(l), rank(ts_mean(v, 50)), 12)))
            .astype(int)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 75

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha075(l, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.boxenplot(x=f'{alpha:03}', y='ret_fwd', data=alphas[alphas.ret_fwd.between(-.025, .025)]);

# ---- Cell ----
alphas.groupby(alphas[f'{alpha:03}']).ret_fwd.describe()

# ---- Cell ----
def alpha076(l, vwap, sector):
    """(max(rank(ts_weighted_mean(ts_delta(vwap, 1.24383), 11.8259)),
            ts_rank(ts_weighted_mean(ts_rank(ts_corr(IndNeutralize(low, IndClass.sector), adv81,8.14941), 19.569), 17.1543), 19.383)) * -1)
    """
    pass

# ---- Cell ----
alpha = 76

# ---- Cell ----
def alpha077(l, h, vwap):
    """min(rank(ts_weighted_mean(((((high + low) / 2) + high) - (vwap + high)), 20.0451)),
            rank(ts_weighted_mean(ts_corr(((high + low) / 2), adv40, 3.1614), 5.64125)))
    """

    s1 = rank(ts_weighted_mean(h.add(l).div(2).sub(vwap), 20))
    s2 = rank(ts_weighted_mean(ts_corr(h.add(l).div(2), ts_mean(v, 40), 3), 5))
    return (s1.where(s1 < s2, s2)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 77

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha077(l, h, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha078(l, v, vwap):
    """(rank(ts_corr(ts_sum(((low * 0.352233) + (vwap * (1 - 0.352233))), 19.7428),
        ts_sum(adv40, 19.7428), 6.83313))^rank(ts_corr(rank(vwap), rank(volume), 5.77492)))"""

    w = 0.352233
    return (rank(ts_corr(ts_sum((l.mul(w).add(vwap.mul(1 - w))), 19),
                         ts_sum(ts_mean(v, 40), 19), 6))
            .pow(rank(ts_corr(rank(vwap), rank(v), 5)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 78

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha078(l, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha079(o, v, sector):
    """(rank(ts_delta(IndNeutralize(((close * 0.60733) + (open * (1 - 0.60733))),IndClass.sector), 1.23438)) <
        rank(ts_corr(Ts_Rank(vwap, 3.60973), Ts_Rank(adv150,9.18637), 14.6644)))
    """
    pass

# ---- Cell ----
def alpha080(h, industry):
    """((power(rank(sign(ts_delta(IndNeutralize(((open * 0.868128) + (high * (1 - 0.868128))),IndClass.industry), 4.04545))),
        ts_rank(ts_corr(high, adv10, 5.11456), 5.53756)) * -1)
    """
    pass

# ---- Cell ----
def alpha081(v, vwap):
    """-(rank(log(ts_product(rank((rank(ts_corr(vwap, ts_sum(adv10, 49.6054),8.47743))^4)), 14.9655))) <
        rank(ts_corr(rank(vwap), rank(volume), 5.07914)))"""

    return (rank(log(ts_product(rank(rank(ts_corr(vwap,
                                                  ts_sum(ts_mean(v, 10), 50), 8))
                                     .pow(4)), 15)))
            .lt(rank(ts_corr(rank(vwap), rank(v), 5)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 81

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha081(v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
# mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
# mi[alpha]

# ---- Cell ----
def alpha082(o, v, sector):
    """(min(rank(ts_weighted_mean(ts_delta(open, 1.46063), 14.8717)),
        ts_rank(ts_weighted_mean(ts_corr(IndNeutralize(volume, IndClass.sector),
        ((open * 0.634196) +(open * (1 - 0.634196))), 17.4842), 6.92131), 13.4283)) * -1)

    """
    pass

# ---- Cell ----
def alpha083(h, l, c):
    """(rank(ts_lag((high - low) / ts_mean(close, 5), 2)) * rank(rank(volume)) /
            (((high - low) / ts_mean(close, 5) / (vwap - close)))
    """
    s = h.sub(l).div(ts_mean(c, 5))

    return (rank(rank(ts_lag(s, 2))
                 .mul(rank(rank(v)))
                 .div(s).div(vwap.sub(c).add(1e-3)))
            .stack('ticker')
            .swaplevel()
            .replace((np.inf, -np.inf), np.nan))

# ---- Cell ----
alpha = 83

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha083(h, l, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha084(c, vwap):
    """power(ts_rank((vwap - ts_max(vwap, 15.3217)), 20.7127),
        ts_delta(close,4.96796))"""
    return (rank(power(ts_rank(vwap.sub(ts_max(vwap, 15)), 20),
                       ts_delta(c, 6)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 84

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha084(c, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha085(l, v):
    """power(rank(ts_corr(((high * 0.876703) + (close * (1 - 0.876703))), adv30,9.61331)),
        rank(ts_corr(ts_rank(((high + low) / 2), 3.70596),
                     ts_rank(volume, 10.1595),7.11408)))
                     """
    w = 0.876703
    return (rank(ts_corr(h.mul(w).add(c.mul(1 - w)), ts_mean(v, 30), 10))
            .pow(rank(ts_corr(ts_rank(h.add(l).div(2), 4),
                              ts_rank(v, 10), 7)))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 85

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha085(l, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha086(c, v, vwap):
    """((ts_rank(ts_corr(close, ts_sum(adv20, 14.7444), 6.00049), 20.4195) <
        rank(((open + close) - (vwap + open)))) * -1)
    """
    return (ts_rank(ts_corr(c, ts_mean(ts_mean(v, 20), 15), 6), 20)
            .lt(rank(c.sub(vwap)))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 86

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha086(c, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha087(c, vwap, industry):
    """(max(rank(ts_weighted_mean(ts_delta(((close * 0.369701) + (vwap * (1 - 0.369701))),1.91233), 2.65461)),
            ts_rank(ts_weighted_mean(abs(ts_corr(IndNeutralize(adv81,IndClass.industry), close, 13.4132)), 4.89768), 14.4535)) * -1)
    """
    pass

# ---- Cell ----
def alpha088(o, h, l, c, v):
    """min(rank(ts_weighted_mean(((rank(open) + rank(low)) - (rank(high) + rank(close))),8.06882)),
        ts_rank(ts_weighted_mean(ts_corr(ts_rank(close, 8.44728),
                ts_rank(adv60,20.6966), 8.01266), 6.65053), 2.61957))"""

    s1 = (rank(ts_weighted_mean(rank(o)
                                .add(rank(l))
                                .sub(rank(h))
                                .add(rank(c)), 8)))
    s2 = ts_rank(ts_weighted_mean(ts_corr(ts_rank(c, 8),
                                          ts_rank(ts_mean(v, 60), 20), 8), 6), 2)

    return (s1.where(s1 < s2, s2)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 88

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha088(o, h, l, c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'], n=30000)
mi[alpha]

# ---- Cell ----
def alpha089(l, v, vwap, industry):
    """(ts_rank(ts_weighted_mean(ts_corr(((low * 0.967285) +
        (low * (1 - 0.967285))), adv10,6.94279), 5.51607), 3.79744) -
        ts_rank(ts_weighted_mean(ts_delta(IndNeutralize(vwap,IndClass.industry), 3.48158), 10.1466), 15.3012))
    """
    pass

# ---- Cell ----
def alpha090(c, l, subindustry):
    """((rank((close - ts_max(close, 4.66719)))
        ^ts_rank(ts_corr(IndNeutralize(adv40,IndClass.subindustry), low, 5.38375), 3.21856)) * -1)
    """
    pass

# ---- Cell ----
def alpha091(v, vwap, industry):
    """((ts_rank(ts_weighted_mean(ts_weighted_mean(ts_corr(IndNeutralize(close,IndClass.industry), volume, 9.74928), 16.398), 3.83219), 4.8667) -
        rank(ts_weighted_mean(ts_corr(vwap, adv30, 4.01303), 2.6809))) * -1)
    """
    pass

# ---- Cell ----
def alpha092(o, l, c, v):
    """min(ts_rank(ts_weighted_mean(((((high + low) / 2) + close) < (low + open)), 14.7221),18.8683),
            ts_rank(ts_weighted_mean(ts_corr(rank(low), rank(adv30), 7.58555), 6.94024),6.80584))
    """
    p1 = ts_rank(ts_weighted_mean(h.add(l).div(2).add(c).lt(l.add(o)), 15), 18)
    p2 = ts_rank(ts_weighted_mean(ts_corr(rank(l), rank(ts_mean(v, 30)), 7), 6), 6)

    return (p1.where(p1<p2, p2)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 92

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha092(o, l, c, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha093(c, v, vwap, industry):
    """(ts_rank(ts_weighted_mean(ts_corr(IndNeutralize(vwap, IndClass.industry), adv81,17.4193), 19.848), 7.54455) /
        rank(ts_weighted_mean(ts_delta(((close * 0.524434) + (vwap * (1 -0.524434))), 2.77377), 16.2664)))
    """
    pass

# ---- Cell ----
def alpha094(v, vwap):
    """((rank((vwap - ts_min(vwap, 11.5783)))^ts_rank(ts_corr(ts_rank(vwap,19.6462),
        ts_rank(adv60, 4.02992), 18.0926), 2.70756)) * -1)
    """

    return (rank(vwap.sub(ts_min(vwap, 11)))
            .pow(ts_rank(ts_corr(ts_rank(vwap, 20),
                                 ts_rank(ts_mean(v, 60), 4), 18), 2))
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 94

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha094(v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha095(o, l, v):
    """(rank((open - ts_min(open, 12.4105))) <
        ts_rank((rank(ts_corr(ts_sum(((high + low)/ 2), 19.1351), ts_sum(adv40, 19.1351), 12.8742))^5), 11.7584))
    """

    return (rank(o.sub(ts_min(o, 12)))
            .lt(ts_rank(rank(ts_corr(ts_mean(h.add(l).div(2), 19),
                                     ts_sum(ts_mean(v, 40), 19), 13).pow(5)), 12))
            .astype(int)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 95

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha095(o, l, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}'], kde=False);

# ---- Cell ----
g = sns.boxenplot(x=f'{alpha:03}', y='ret_fwd', data=alphas[alphas.ret_fwd.between(-.025, .025)]);

# ---- Cell ----
alphas.groupby(alphas[f'{alpha:03}']).ret_fwd.describe()

# ---- Cell ----
def alpha096(c, v, vwap):
    """(max(ts_rank(ts_weighted_mean(ts_corr(rank(vwap), rank(volume), 5.83878),4.16783), 8.38151),
        ts_rank(ts_weighted_mean(ts_argmax(ts_corr(ts_rank(close, 7.45404), ts_rank(adv60, 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1)"""

    s1 = ts_rank(ts_weighted_mean(ts_corr(rank(vwap), rank(v), 10), 4), 8)
    s2 = ts_rank(ts_weighted_mean(ts_argmax(ts_corr(ts_rank(c, 7),
                                                    ts_rank(ts_mean(v, 60), 10), 10), 12), 14), 13)
    return (s1.where(s1 > s2, s2)
            .mul(-1)
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 96

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha096(c, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas)


# ---- Cell ----
def alpha097(l):
    """((rank(ts_weighted_mean(ts_delta(IndNeutralize(((low * 0.721001) +
        (vwap * (1 - 0.721001))),IndClass.industry), 3.3705), 20.4523)) -
        ts_rank(ts_weighted_mean(ts_rank(ts_corr(Ts_Rank(low,7.87871),
        ts_rank(adv60, 17.255), 4.97547), 18.5925), 15.7152), 6.71659)) * -1)
    """
    pass

# ---- Cell ----
def alpha098(o, v, vwap):
    """(rank(ts_weighted_mean(ts_corr(vwap, ts_sum(adv5, 26.4719), 4.58418), 7.18088)) -
        rank(ts_weighted_mean(ts_tank(ts_argmin(ts_corr(rank(open),
        rank(adv15), 20.8187), 8.62571),6.95668), 8.07206)))
    """
    adv5 = ts_mean(v, 5)
    adv15 = ts_mean(v, 15)
    return (rank(ts_weighted_mean(ts_corr(vwap, ts_mean(adv5, 26), 4), 7))
            .sub(rank(ts_weighted_mean(ts_rank(ts_argmin(ts_corr(rank(o),
                                                                 rank(adv15), 20), 8), 6))))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 98

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha098(o, v, vwap)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
def alpha099(l, v):
    """((rank(ts_corr(ts_sum(((high + low) / 2), 19.8975),
                    ts_sum(adv60, 19.8975), 8.8136)) <
                    rank(ts_corr(low, volume, 6.28259))) * -1)"""

    return ((rank(ts_corr(ts_sum((h.add(l).div(2)), 19),
                          ts_sum(ts_mean(v, 60), 19), 8))
             .lt(rank(ts_corr(l, v, 6)))
             .mul(-1))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 99

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha099(l, v)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
alphas.groupby(alphas[f'{alpha:03}']).ret_fwd.describe()

# ---- Cell ----
def alpha100(r, cap):
    """(0 - (1 * (((1.5 * scale(indneutralize(
                indneutralize(rank(((((close - low) - (high -close)) / (high - low)) * volume)),
                                IndClass.subindustry), IndClass.subindustry))) -
    scale(indneutralize((ts_corr(close, rank(adv20), 5) - rank(ts_argmin(close, 30))), IndClass.subindustry))) * (volume / adv20))))
    """
    pass

# ---- Cell ----
def alpha101(o, h, l, c):
    """((close - open) / ((high - low) + .001))"""
    return (c.sub(o).div(h.sub(l).add(1e-3))
            .stack('ticker')
            .swaplevel())

# ---- Cell ----
alpha = 101

# ---- Cell ----
%%time
alphas[f'{alpha:03}'] = alpha101(o, h, l, c)

# ---- Cell ----
alphas[f'{alpha:03}'].to_hdf('alphas.h5', f'alphas/{alpha:03}')

# ---- Cell ----
sns.distplot(alphas[f'{alpha:03}']);

# ---- Cell ----
g = sns.jointplot(x=f'{alpha:03}', y='ret_fwd', data=alphas);


# ---- Cell ----
mi[alpha] = get_mutual_info_score(alphas.ret_fwd, alphas[f'{alpha:03}'])
mi[alpha]

# ---- Cell ----
alphas = []
with pd.HDFStore('alphas.h5') as store:
    keys = [k[1:] for k in store.keys()]
    for key in keys:
        i = int(key.split('/')[-1])
        alphas.append(store[key].to_frame(i))
alphas = pd.concat(alphas, axis=1)

# ---- Cell ----
alphas.info(null_counts=True)

# ---- Cell ----
alphas.to_hdf('data.h5', 'factors/formulaic')

# ---- Cell ----
# alphas = []
# with pd.HDFStore('alphas.h5') as store:
#     keys = [k[1:] for k in store.keys()]
#     for key in keys:
#         i = int(key.split('/')[-1])
#         alphas.append(store[key].to_frame(i))
# alphas = pd.concat(alphas, axis=1)
# alphas.info(null_counts=True)
# alphas.to_hdf('data.h5', 'factors/formulaic')
