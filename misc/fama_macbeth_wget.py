# English filename: 02_fama_macbeth_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/8일차 선형모델을 통한 수익률 예측 II/02_fama_macbeth_wget_clear.py
# Original filename: 02_fama_macbeth_wget_clear.py

# ---- Cell ----
!cd ..&& mkdir data&& cd data&&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/data/assets.zip&&unzip -n assets.zip

# ---- Cell ----
!pip install linearmodels

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
import pandas as pd
import numpy as np

from statsmodels.api import OLS, add_constant
import pandas_datareader.data as web

from linearmodels.asset_pricing import LinearFactorModel

import matplotlib.pyplot as plt
import seaborn as sns

# ---- Cell ----
sns.set_style('whitegrid')

# ---- Cell ----
ff_factor = 'F-F_Research_Data_5_Factors_2x3'
ff_factor_data = web.DataReader(ff_factor, 'famafrench', start='2010', end='2017-12')[0]
ff_factor_data.info()

# ---- Cell ----
ff_factor_data.describe()

# ---- Cell ----
ff_portfolio = '17_Industry_Portfolios'
ff_portfolio_data = web.DataReader(ff_portfolio, 'famafrench', start='2010', end='2017-12')[0]
ff_portfolio_data = ff_portfolio_data.sub(ff_factor_data.RF, axis=0)
ff_portfolio_data.info()

# ---- Cell ----
ff_portfolio_data.describe()

# ---- Cell ----
with pd.HDFStore('../data/assets.h5') as store:
    prices = store['/quandl/wiki/prices'].adj_close.unstack().loc['2010':'2017']
    equities = store['/us_equities/stocks'].drop_duplicates()

# ---- Cell ----
sectors = equities.filter(prices.columns, axis=0).sector.to_dict()
sectors

# ---- Cell ----
prices = prices.filter(sectors.keys()).dropna(how='all', axis=1)
prices

# ---- Cell ----
sectors = equities.filter(prices.columns, axis=0).sector.to_dict()
prices = prices.filter(sectors.keys()).dropna(how='all', axis=1)

# ---- Cell ----
returns = prices.resample('M').last().pct_change().mul(100).to_period('M')
returns = returns.dropna(how='all').dropna(axis=1)
returns.info()

# ---- Cell ----
returns.head()

# ---- Cell ----
ff_factor_data = ff_factor_data.loc[returns.index]
ff_portfolio_data = ff_portfolio_data.loc[returns.index]

# ---- Cell ----
ff_portfolio_data.describe()

# ---- Cell ----
ff_factor_data

# ---- Cell ----
excess_returns = returns.sub(ff_factor_data.RF, axis=0)
excess_returns.info()

# ---- Cell ----
excess_returns = excess_returns.clip(lower=np.percentile(excess_returns, 1),
                                     upper=np.percentile(excess_returns, 99))

# ---- Cell ----
ff_portfolio_data.info()

# ---- Cell ----
ff_factor_data = ff_factor_data.drop('RF', axis=1)
ff_factor_data.info()

# ---- Cell ----
ff_portfolio_data

# ---- Cell ----
betas = []
for industry in ff_portfolio_data:
    step1 = OLS(endog=ff_portfolio_data.loc[ff_factor_data.index, industry],
                exog=add_constant(ff_factor_data)).fit()
    betas.append(step1.params.drop('const'))

# ---- Cell ----
betas = pd.DataFrame(betas,
                     columns=ff_factor_data.columns,
                     index=ff_portfolio_data.columns)
betas.info()

# ---- Cell ----
betas

# ---- Cell ----
betas

# ---- Cell ----
ff_portfolio_data

# ---- Cell ----
lambdas = []
for period in ff_portfolio_data.index:
    step2 = OLS(endog=ff_portfolio_data.loc[period, betas.index],
                exog=betas).fit()
    lambdas.append(step2.params)

# ---- Cell ----
lambdas = pd.DataFrame(lambdas,
                       index=ff_portfolio_data.index,
                       columns=betas.columns.tolist())
lambdas.info()

# ---- Cell ----
lambdas

# ---- Cell ----
lambdas.mean().sort_values().plot.barh(figsize=(12, 4))
sns.despine()
plt.tight_layout();

# ---- Cell ----
t = lambdas.mean().div(lambdas.std())*np.sqrt(95)
t

# ---- Cell ----
window = 24  # months
ax1 = plt.subplot2grid((1, 3), (0, 0))
ax2 = plt.subplot2grid((1, 3), (0, 1), colspan=2)
lambdas.mean().sort_values().plot.barh(ax=ax1)
lambdas.rolling(window).mean().dropna().plot(lw=1,
                                             figsize=(14, 5),
                                             sharey=True,
                                             ax=ax2)
sns.despine()
plt.tight_layout()

# ---- Cell ----
window = 24  # months
lambdas.rolling(window).mean().dropna().plot(lw=2,
                                             figsize=(14, 7),
                                             subplots=True,
                                             sharey=True)
sns.despine()
plt.tight_layout()

# ---- Cell ----
mod = LinearFactorModel(portfolios=ff_portfolio_data,
                        factors=ff_factor_data)
res = mod.fit()
print(res)

# ---- Cell ----
print(res.full_summary)

# ---- Cell ----
lambdas.mean()
