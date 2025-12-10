# English filename: 06_evaluating_signals_using_alphalens_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/10일차 머신러닝 투자모델 검증을 위한 전략 백테스트 II/06_evaluating_signals_using_alphalens_wget_clear.py
# Original filename: 06_evaluating_signals_using_alphalens_wget_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/07_linear_models/data.zip&& unzip -n data.zip
!cd ..&& mkdir data&& cd data&&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/data/assets.zip&&unzip -n assets.zip

# ---- Cell ----
!pip install alphalens-reloaded

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
from pathlib import Path
import pandas as pd
from alphalens.tears import create_summary_tear_sheet
from alphalens.utils import get_clean_factor_and_forward_returns

# ---- Cell ----
idx = pd.IndexSlice

# ---- Cell ----
with pd.HDFStore('data.h5') as store:
    lr_predictions = store['lr/predictions']
    lasso_predictions = store['lasso/predictions']
    lasso_scores = store['lasso/scores']
    ridge_predictions = store['ridge/predictions']
    ridge_scores = store['ridge/scores']

# ---- Cell ----
DATA_STORE = Path('..', 'data', 'assets.h5')

# ---- Cell ----
def get_trade_prices(tickers, start, stop):
    prices = (pd.read_hdf(DATA_STORE, 'quandl/wiki/prices').swaplevel().sort_index())
    prices.index.names = ['symbol', 'date']
    prices = prices.loc[idx[tickers, str(start):str(stop)], 'adj_open']
    return (prices
            .unstack('symbol')
            .sort_index()
            .shift(-1)
            .tz_localize('UTC'))

# ---- Cell ----
def get_best_alpha(scores):
    return scores.groupby('alpha').ic.mean().idxmax()

# ---- Cell ----
def get_factor(predictions):
    return (predictions.unstack('symbol')
            .dropna(how='all')
            .stack()
            .tz_localize('UTC', level='date')
            .sort_index())

# ---- Cell ----
lr_factor = get_factor(lr_predictions.predicted.swaplevel())
lr_factor.head()

# ---- Cell ----
tickers = lr_factor.index.get_level_values('symbol').unique()

# ---- Cell ----
trade_prices = get_trade_prices(tickers, 2014, 2017)
trade_prices.info()

# ---- Cell ----
lr_factor_data = get_clean_factor_and_forward_returns(factor=lr_factor,
                                                      prices=trade_prices,
                                                      quantiles=5,
                                                      periods=(1, 5, 10, 21))
lr_factor_data.info()

# ---- Cell ----
create_summary_tear_sheet(lr_factor_data);

# ---- Cell ----
best_ridge_alpha = get_best_alpha(ridge_scores)
ridge_predictions = ridge_predictions[ridge_predictions.alpha==best_ridge_alpha].drop('alpha', axis=1)

# ---- Cell ----
ridge_factor = get_factor(ridge_predictions.predicted.swaplevel())
ridge_factor.head()

# ---- Cell ----
ridge_factor_data = get_clean_factor_and_forward_returns(factor=ridge_factor,
                                                         prices=trade_prices,
                                                         quantiles=5,
                                                         periods=(1, 5, 10, 21))
ridge_factor_data.info()

# ---- Cell ----
create_summary_tear_sheet(ridge_factor_data);

# ---- Cell ----
best_lasso_alpha = get_best_alpha(lasso_scores)
lasso_predictions = lasso_predictions[lasso_predictions.alpha==best_lasso_alpha].drop('alpha', axis=1)

# ---- Cell ----
lasso_factor = get_factor(lasso_predictions.predicted.swaplevel())
lasso_factor.head()

# ---- Cell ----
lasso_factor_data = get_clean_factor_and_forward_returns(factor=lasso_factor,
                                                      prices=trade_prices,
                                                      quantiles=5,
                                                      periods=(1, 5, 10, 21))
lasso_factor_data.info()

# ---- Cell ----
create_summary_tear_sheet(lasso_factor_data);

# ---- Cell ----

