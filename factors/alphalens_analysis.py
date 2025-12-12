# English filename: 05_alphalens_analysis_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/1일차 머신러닝 분석을 위한 알파 팩터 수집 및 작성/2_ alpha_factor_library/05_alphalens_analysis_clear.py
# Original filename: 05_alphalens_analysis_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/alpha_factor_library_101.zip && unzip -n alpha_factor_library_101.zip

# ---- Cell ----
!cd ..&& mkdir data&& cd data&&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/data/assets.zip&&unzip -n assets.zip

# ---- Cell ----
!pip install --upgrade alphalens-reloaded tables

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
from pathlib import Path
from collections import defaultdict
from time import time

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from alphalens.tears import (create_returns_tear_sheet,
                             create_summary_tear_sheet,
                             create_full_tear_sheet)
from alphalens.utils import get_clean_factor_and_forward_returns, rate_of_return, std_conversion
from alphalens import plotting
from alphalens import performance as perf
from alphalens import utils

# ---- Cell ----
sns.set_style('whitegrid')
np.random.seed(42)
idx = pd.IndexSlice

# ---- Cell ----
DATA_STORE = Path('..', 'data', 'assets.h5')

# ---- Cell ----
factors = (pd.concat([pd.read_hdf('data.h5', 'factors/common'),
                      pd.read_hdf('data.h5', 'factors/formulaic')
                      .rename(columns=lambda x: f'alpha_{int(x):03}')],
                     axis=1)
           .dropna(axis=1, thresh=100000)
           .sort_index())

# ---- Cell ----
factors.info()

# ---- Cell ----
tickers = factors.index.get_level_values('ticker').unique()

# ---- Cell ----
alpha = 'alpha_050'

# ---- Cell ----
factor = (factors[alpha]
          .unstack('ticker')
          .stack()
          .tz_localize('UTC', level='date')
          .sort_index())

# ---- Cell ----
def get_trade_prices(tickers):
    return (pd.read_hdf(DATA_STORE, 'quandl/wiki/prices')
              .loc[idx['2006':'2017', tickers], 'adj_open']
              .unstack('ticker')
              .sort_index()
            .shift(-1)
            .tz_localize('UTC'))

# ---- Cell ----
trade_prices = get_trade_prices(tickers)

# ---- Cell ----
trade_prices.info()

# ---- Cell ----
factor_data = utils.get_clean_factor_and_forward_returns(factor=factor,
                                                   prices=trade_prices,
                                                   quantiles=5,
                                                   max_loss=1.0,
                                                   periods=(1, 5, 10)).sort_index()
factor_data.info()

# ---- Cell ----
mean_quant_ret_bydate, std_quant_daily = perf.mean_return_by_quantile(
    factor_data,
    by_date=True,
    by_group=False,
    demeaned=True,
    group_adjust=False,
)

mean_quant_rateret_bydate = mean_quant_ret_bydate.apply(
    rate_of_return,
    base_period=mean_quant_ret_bydate.columns[0],
)

compstd_quant_daily = std_quant_daily.apply(std_conversion,
                                            base_period=std_quant_daily.columns[0])

alpha_beta = perf.factor_alpha_beta(factor_data,
                                    demeaned=True)

mean_ret_spread_quant, std_spread_quant = perf.compute_mean_returns_spread(
    mean_quant_rateret_bydate,
    factor_data["factor_quantile"].max(),
    factor_data["factor_quantile"].min(),
    std_err=compstd_quant_daily,
)

# ---- Cell ----
mean_ret_spread_quant.mean().mul(10000).to_frame('Mean Period Wise Spread (bps)').join(alpha_beta.T).T

# ---- Cell ----
fig, axes = plt.subplots(ncols=3, figsize=(20, 5))

mean_quant_ret, std_quantile = perf.mean_return_by_quantile(factor_data,
                                                       by_group=False,
                                                       demeaned=True)

mean_quant_rateret = mean_quant_ret.apply(rate_of_return, axis=0,
                                          base_period=mean_quant_ret.columns[0])

plotting.plot_quantile_returns_bar(mean_quant_rateret, ax=axes[0])


factor_returns = perf.factor_returns(factor_data)

title = "Factor Weighted Long/Short Portfolio Cumulative Return (1D Period)"
plotting.plot_cumulative_returns(factor_returns['1D'],
                                 period='1D',
                                 freq=pd.tseries.offsets.BDay(),
                                 title=title,
                                 ax=axes[1])

plotting.plot_cumulative_returns_by_quantile(mean_quant_ret_bydate['1D'],
                                             freq=pd.tseries.offsets.BDay(),
                                             period='1D',
                                             ax=axes[2])
fig.tight_layout();

# ---- Cell ----
create_summary_tear_sheet(factor_data)

# ---- Cell ----
create_full_tear_sheet(factor_data)
