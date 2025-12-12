# English filename: 06_evaluate_trading_signals_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/12일차 미국주식 고급머신러닝 투자전략 I/06_evaluate_trading_signals_clear.py
# Original filename: 06_evaluate_trading_signals_clear.py

# ---- Cell ----
# !mkdir results&& cd results&& mkdir us_stocks&& cd us_stocks && wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/results/us_stocks/tuning_lgb.h5
!mkdir data&& cd data&& wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data/model_tuning.h5 &&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data/predictions.h5
!cd ..&& mkdir data&& cd data&&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/data/assets.zip&&unzip -n assets.zip
!cd ..&& wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/utils.py

# ---- Cell ----
!pip install alphalens-reloaded

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

from time import time
from io import StringIO
import sys, os
import numpy as np
import warnings
from pathlib import Path
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
import seaborn as sns

import lightgbm as lgb

from scipy.stats import spearmanr, pearsonr

from alphalens import plotting
from alphalens import performance as perf
from alphalens.utils import get_clean_factor_and_forward_returns, rate_of_return, std_conversion
from alphalens.tears import (create_summary_tear_sheet,
                             create_full_tear_sheet)

# ---- Cell ----
sys.path.insert(1, os.path.join(sys.path[0], '..'))
from utils import MultipleTimeSeriesCV

# ---- Cell ----
sns.set_style('whitegrid')

# ---- Cell ----
YEAR = 252
idx = pd.IndexSlice

# ---- Cell ----
scope_params = ['lookahead', 'train_length', 'test_length']
daily_ic_metrics = ['daily_ic_mean', 'daily_ic_mean_n', 'daily_ic_median', 'daily_ic_median_n']
lgb_train_params = ['learning_rate', 'num_leaves', 'feature_fraction', 'min_data_in_leaf']
catboost_train_params = ['max_depth', 'min_child_samples']

# ---- Cell ----
results_path = Path('results', 'us_stocks')
if not results_path.exists():
    results_path.mkdir(parents=True)

# ---- Cell ----
# with pd.HDFStore(results_path / 'tuning_lgb.h5') as store:
#     for i, key in enumerate(
#         [k[1:] for k in store.keys() if k[1:].startswith('metrics')]):
#         _, t, train_length, test_length = key.split('/')[:4]
#         attrs = {
#             'lookahead': t,
#             'train_length': train_length,
#             'test_length': test_length
#         }
#         s = store[key].to_dict()
#         s.update(attrs)
#         if i == 0:
#             lgb_metrics = pd.Series(s).to_frame(i)
#         else:
#             lgb_metrics[i] = pd.Series(s)

# id_vars = scope_params + lgb_train_params + daily_ic_metrics
# lgb_metrics = pd.melt(lgb_metrics.T.drop('t', axis=1),
#                   id_vars=id_vars,
#                   value_name='ic',
#                   var_name='boost_rounds').dropna().apply(pd.to_numeric)

# ---- Cell ----
# lgb_metrics.to_hdf('data/model_tuning.h5', 'lgb/metrics')
# lgb_metrics.info()

# ---- Cell ----
# lgb_metrics.groupby(scope_params).size()

# ---- Cell ----
int_cols = ['lookahead', 'train_length', 'test_length', 'boost_rounds']

# ---- Cell ----
# lgb_ic = []
# with pd.HDFStore(results_path / 'tuning_lgb.h5') as store:
#     keys = [k[1:] for k in store.keys()]
#     for key in keys:
#         _, t, train_length, test_length = key.split('/')[:4]
#         if key.startswith('daily_ic'):
#             df = (store[key]
#                   .drop(['boosting', 'objective', 'verbose'], axis=1)
#                  .assign(lookahead=t,
#                          train_length=train_length,
#                          test_length=test_length))
#             lgb_ic.append(df)
#     lgb_ic = pd.concat(lgb_ic).reset_index()

# ---- Cell ----
# id_vars = ['date'] + scope_params + lgb_train_params
# lgb_ic = pd.melt(lgb_ic,
#                  id_vars=id_vars,
#                  value_name='ic',
#                  var_name='boost_rounds').dropna()
# lgb_ic.loc[:, int_cols] = lgb_ic.loc[:, int_cols].astype(int)

# ---- Cell ----
# lgb_ic.to_hdf('data/model_tuning.h5', 'lgb/ic')
# lgb_ic.info()

# ---- Cell ----
# lgb_daily_ic = lgb_ic.groupby(id_vars[1:] + ['boost_rounds']).ic.mean().to_frame('ic').reset_index()
# lgb_daily_ic.to_hdf('data/model_tuning.h5', 'lgb/daily_ic')
# lgb_daily_ic.info()

# ---- Cell ----
lgb_ic = pd.read_hdf('data/model_tuning.h5', 'lgb/ic')
lgb_daily_ic = pd.read_hdf('data/model_tuning.h5', 'lgb/daily_ic')

# ---- Cell ----
# with pd.HDFStore(results_path / 'tuning_catboost.h5') as store:
#     for i, key in enumerate(
#             [k[1:] for k in store.keys() if k[1:].startswith('metrics')]):
#         _, t, train_length, test_length = key.split('/')[:4]
#         attrs = {
#             'lookahead'   : t,
#             'train_length': train_length,
#             'test_length' : test_length
#         }
#         s = store[key].to_dict()
#         s.update(attrs)
#         if i == 0:
#             catboost_metrics = pd.Series(s).to_frame(i)
#         else:
#             catboost_metrics[i] = pd.Series(s)

# id_vars = scope_params + catboost_train_params + daily_ic_metrics
# catboost_metrics = pd.melt(catboost_metrics.T.drop('t', axis=1),
#                            id_vars=id_vars,
#                            value_name='ic',
#                            var_name='boost_rounds').dropna().apply(pd.to_numeric)

# ---- Cell ----
# catboost_metrics.info()

# ---- Cell ----
# catboost_metrics.groupby(scope_params).size()

# ---- Cell ----
# catboost_ic = []
# with pd.HDFStore(results_path / 'tuning_catboost.h5') as store:
#     keys = [k[1:] for k in store.keys()]
#     for key in keys:
#         _, t, train_length, test_length = key.split('/')[:4]
#         if key.startswith('daily_ic'):
#             df = (store[key].drop('task_type', axis=1)
#                  .assign(lookahead=t,
#                          train_length=train_length,
#                          test_length=test_length))
#             catboost_ic.append(df)
#     catboost_ic = pd.concat(catboost_ic).reset_index()

# ---- Cell ----
# id_vars = ['date'] + scope_params + catboost_train_params
# catboost_ic = pd.melt(catboost_ic,
#                       id_vars=id_vars,
#                       value_name='ic',
#                       var_name='boost_rounds').dropna()
# catboost_ic.loc[:, int_cols] = catboost_ic.loc[:, int_cols].astype(int)

# ---- Cell ----
# catboost_ic.to_hdf('data/model_tuning.h5', 'catboost/ic')
# catboost_ic.info()

# ---- Cell ----
# catboost_daily_ic = catboost_ic.groupby(id_vars[1:] + ['boost_rounds']).ic.mean().to_frame('ic').reset_index()
# catboost_daily_ic.to_hdf('data/model_tuning.h5', 'catboost/daily_ic')
# catboost_daily_ic.info()

# ---- Cell ----
catboost_ic = pd.read_hdf('data/model_tuning.h5', 'catboost/ic')
catboost_daily_ic = pd.read_hdf('data/model_tuning.h5', 'catboost/daily_ic')

# ---- Cell ----
# _data = pd.concat([
#     catboost_metrics.assign(model='catboost'),lgb_metrics.assign(model='lightgbm')
# ])

# ---- Cell ----
# fig, axes = plt.subplots(ncols=2, figsize=(15, 5), sharey=True)
# sns.boxenplot(x='lookahead', y='ic', hue='model',
#               data=_data, ax=axes[0])
# axes[0].axhline(0, ls='--', lw=1, c='k')
# axes[0].set_title('Overall IC')
# sns.boxenplot(x='lookahead', y='ic', hue='model',
#               data=pd.concat([catboost_daily_ic.assign(model='catboost')
#               ,lgb_daily_ic.assign(model='lightgbm')]), ax=axes[1])
# axes[1].axhline(0, ls='--', lw=1, c='k')
# axes[1].set_title('Daily IC')
# fig.tight_layout()

# ---- Cell ----
# lin_reg = {}
# for t in [1, 21]:
#     df_ = lgb_ic[lgb_ic.lookahead==t]
#     y, X = df_.ic, df_.drop(['ic'], axis=1)
#     X = sm.add_constant(pd.get_dummies(X, columns=X.columns, drop_first=True))
#     model = sm.OLS(endog=y, exog=X.astype(float))
#     lin_reg[t] = model.fit()
#     s = lin_reg[t].summary()
#     coefs = pd.read_csv(StringIO(s.tables[1].as_csv())).rename(columns=lambda x: x.strip())
#     coefs.columns = ['variable', 'coef', 'std_err', 't', 'p_value', 'ci_low', 'ci_high']
#     coefs.to_csv(f'results/linreg_result_{t:02}.csv', index=False)

# ---- Cell ----
# def visualize_lr_result(model, ax):
#     ci = model.conf_int()
#     errors = ci[1].sub(ci[0]).div(2)

#     coefs = (model.params.to_frame('coef').assign(error=errors)
#              .reset_index().rename(columns={'index': 'variable'}))
#     coefs = coefs[~coefs['variable'].str.startswith('date')&(coefs.variable!='const')]

#     coefs.plot(x='variable', y='coef', kind='bar',
#                  ax=ax, color='none', capsize=3,
#                  yerr='error', legend=False)
#     ax.set_ylabel('IC')
#     ax.set_xlabel('')
#     ax.scatter(x=np.arange(len(coefs)), marker='_', s=120, y=coefs['coef'], color='black')
#     ax.axhline(y=0, linestyle='--', color='black', linewidth=1)
#     ax.xaxis.set_ticks_position('none')

# ---- Cell ----
# fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(20, 8), sharey=True)
# axes = axes.flatten()
# for i, t in enumerate([1, 21]):
#     visualize_lr_result(lin_reg[t], axes[i])
#     axes[i].set_title(f'Lookahead: {t} Day(s)')
# fig.suptitle('OLS Coefficients & Confidence Intervals', fontsize=20)
# fig.tight_layout()
# fig.subplots_adjust(top=.92);

# ---- Cell ----
# group_cols = scope_params + lgb_train_params + ['boost_rounds']
# lgb_daily_ic.groupby('lookahead', group_keys=False).apply(lambda x: x.nlargest(3, 'ic'))

# ---- Cell ----
# lgb_metrics.groupby('lookahead', group_keys=False).apply(lambda x: x.nlargest(3, 'ic'))
# lgb_metrics.groupby('lookahead', group_keys=False).apply(lambda x: x.nlargest(3, 'ic')).to_csv('results/best_lgb_model.csv', index=False)

# ---- Cell ----
# lgb_metrics.groupby('lookahead', group_keys=False).apply(lambda x: x.nlargest(3, 'daily_ic_mean'))

# ---- Cell ----
# group_cols = scope_params + catboost_train_params + ['boost_rounds']
# catboost_daily_ic.groupby('lookahead', group_keys=False).apply(lambda x: x.nlargest(3, 'ic'))

# ---- Cell ----
# catboost_metrics.groupby('lookahead', group_keys=False).apply(lambda x: x.nlargest(3, 'ic'))

# ---- Cell ----
# catboost_metrics.groupby('lookahead', group_keys=False).apply(lambda x: x.nlargest(3, 'daily_ic_mean'))

# ---- Cell ----
# sns.jointplot(x=lgb_metrics.daily_ic_mean,y=lgb_metrics.ic);

# ---- Cell ----
# g = sns.catplot(x='lookahead', y='ic',
#                 col='train_length', row='test_length',
#                 data=lgb_metrics,
#                 kind='box')

# ---- Cell ----
# t=1
# g=sns.catplot(x='boost_rounds',
#             y='ic',
#             col='train_length',
#             row='test_length',
#             data=lgb_daily_ic[lgb_daily_ic.lookahead == t],
#             kind='box')

# ---- Cell ----
# t = 1
# g=sns.catplot(x='boost_rounds',
#             y='ic',
#             col='train_length',
#             row='test_length',
#             data=catboost_metrics[catboost_metrics.lookahead == t],
#             kind='box')

# ---- Cell ----
# t = 1
# train_length = 1134
# test_length = 63
# g = sns.catplot(
#     x='boost_rounds',
#     y='ic',
#     col='max_depth',
#     hue='min_child_samples',
#     data=catboost_daily_ic[(catboost_daily_ic.lookahead == t) &
#                       (catboost_daily_ic.train_length == train_length) &
#                       (catboost_daily_ic.test_length == test_length)],
#     kind='swarm')

# ---- Cell ----
# lgb_daily_ic = pd.read_hdf('data/model_tuning.h5', 'lgb/daily_ic')
# lgb_daily_ic.info()

# ---- Cell ----
# def get_lgb_params(data, t=5, best=0):
#     param_cols = scope_params[1:] + lgb_train_params + ['boost_rounds']
#     df = data[data.lookahead==t].sort_values('ic', ascending=False).iloc[best]
#     return df.loc[param_cols]

# ---- Cell ----
# def get_lgb_key(t, p):
#     key = f'{t}/{int(p.train_length)}/{int(p.test_length)}/{p.learning_rate}/'
#     return key + f'{int(p.num_leaves)}/{p.feature_fraction}/{int(p.min_data_in_leaf)}'

# ---- Cell ----
# best_params = get_lgb_params(lgb_daily_ic, t=1, best=0)
# best_params

# ---- Cell ----
# best_params.to_hdf('data.h5', 'best_params')

# ---- Cell ----
# def select_ic(params, ic_data, lookahead):
#     return ic_data.loc[(ic_data.lookahead == lookahead) &
#                        (ic_data.train_length == params.train_length) &
#                        (ic_data.test_length == params.test_length) &
#                        (ic_data.learning_rate == params.learning_rate) &
#                        (ic_data.num_leaves == params.num_leaves) &
#                        (ic_data.feature_fraction == params.feature_fraction) &
#                        (ic_data.boost_rounds == params.boost_rounds), ['date', 'ic']].set_index('date')

# ---- Cell ----
# fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(20, 5))
# axes = axes.flatten()
# for i, t in enumerate([1, 21]):
#     params = get_lgb_params(lgb_daily_ic, t=t)
#     data = select_ic(params, lgb_ic, lookahead=t).sort_index()
#     rolling = data.rolling(63).ic.mean().dropna()
#     avg = data.ic.mean()
#     med = data.ic.median()
#     rolling.plot(ax=axes[i], title=f'Horizon: {t} Day(s) | IC: Mean={avg*100:.2f}   Median={med*100:.2f}')
#     axes[i].axhline(avg, c='darkred', lw=1)
#     axes[i].axhline(0, ls='--', c='k', lw=1)

# fig.suptitle('3-Month Rolling Information Coefficient', fontsize=16)
# fig.tight_layout()
# fig.subplots_adjust(top=0.92);

# ---- Cell ----
lookahead = 1
# topn = 10
# for best in range(topn):
#     best_params = get_lgb_params(lgb_daily_ic, t=lookahead, best=best)
#     key = get_lgb_key(lookahead, best_params)
#     rounds = str(int(best_params.boost_rounds))
#     if best == 0:
#         best_predictions = pd.read_hdf(results_path / 'tuning_lgb.h5', 'predictions/' + key)
#         best_predictions = best_predictions[rounds].to_frame(best)
#     else:
#         best_predictions[best] = pd.read_hdf(results_path / 'tuning_lgb.h5',
#                                              'predictions/' + key)[rounds]
# best_predictions = best_predictions.sort_index()

# ---- Cell ----
# best_predictions.to_hdf('data/predictions.h5', f'lgb/train/{lookahead:02}')
# best_predictions.info()

# ---- Cell ----
best_predictions = pd.read_hdf('data/predictions.h5', f'lgb/train/{lookahead:02}')

# ---- Cell ----
def get_trade_prices(tickers):
    idx = pd.IndexSlice
    DATA_STORE = '../data/assets.h5'
    prices = (pd.read_hdf(DATA_STORE, 'quandl/wiki/prices').swaplevel().sort_index())
    prices.index.names = ['symbol', 'date']
    return (prices.loc[idx[tickers, '2015': '2017'], 'adj_open']
            .unstack('symbol')
            .sort_index()
            .shift(-1)
            .tz_localize(None))

# ---- Cell ----
test_tickers = best_predictions.index.get_level_values('symbol').unique()

# ---- Cell ----
trade_prices = get_trade_prices(test_tickers)
trade_prices.info()

# ---- Cell ----
# persist result in case we want to rerun:
# trade_prices.to_hdf('data/model_tuning.h5', 'trade_prices/model_selection')
trade_prices = pd.read_hdf('data/model_tuning.h5', 'trade_prices/model_selection')

# ---- Cell ----
factor = best_predictions.iloc[:, :5].mean(1).dropna().tz_localize(None, level='date').swaplevel()

# ---- Cell ----
factor

# ---- Cell ----
trade_prices = trade_prices.tz_localize(None)

# ---- Cell ----
factor_data = get_clean_factor_and_forward_returns(factor=factor,
                                                   prices=trade_prices,
                                                   quantiles=5,
                                                   periods=(1, 5, 10, 21))

# ---- Cell ----
mean_quant_ret_bydate, std_quant_daily = perf.mean_return_by_quantile(
    factor_data,
    by_date=True,
    by_group=False,
    demeaned=True,
    group_adjust=False,
)

# ---- Cell ----
factor_returns = perf.factor_returns(factor_data)

# ---- Cell ----
mean_quant_ret, std_quantile = perf.mean_return_by_quantile(factor_data,
                                                            by_group=False,
                                                            demeaned=True)



mean_quant_rateret = mean_quant_ret.apply(rate_of_return, axis=0,
                                          base_period=mean_quant_ret.columns[0])

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
fig, axes = plt.subplots(ncols=3, figsize=(18, 4))


plotting.plot_quantile_returns_bar(mean_quant_rateret, ax=axes[0])
plt.setp(axes[0].xaxis.get_majorticklabels(), rotation=0)
axes[0].set_xlabel('Quantile')

plotting.plot_cumulative_returns_by_quantile(mean_quant_ret_bydate['1D'],
                                             freq=pd.tseries.offsets.BDay(),
                                             period='1D',
                                             ax=axes[1])
axes[1].set_title('Cumulative Return by Quantile (1D Period)')

title = "Cumulative Return - Factor-Weighted Long/Short PF (1D Period)"
plotting.plot_cumulative_returns(factor_returns['1D'],
                                 period='1D',
                                 freq=pd.tseries.offsets.BDay(),
                                 title=title,
                                 ax=axes[2])

fig.suptitle('Alphalens - Validation Set Performance', fontsize=14)
fig.tight_layout()
fig.subplots_adjust(top=.85);

# ---- Cell ----
create_summary_tear_sheet(factor_data)

# ---- Cell ----
create_full_tear_sheet(factor_data)

# ---- Cell ----
catboost_daily_ic = pd.read_hdf('data/model_tuning.h5', 'catboost/daily_ic')
catboost_daily_ic.info()

# ---- Cell ----
catboost_daily_ic

# ---- Cell ----
def get_cb_params(data, t=5, best=0):
    param_cols = scope_params[1:] + catboost_train_params + ['boost_rounds']
    # param_cols = ['train_length', 'test_length', 'max_depth']
    df = data[data.lookahead==t].sort_values('ic', ascending=False).iloc[best]
    return df.loc[param_cols]

# ---- Cell ----
def get_cb_key(t, p):
    key = f'{t}/{int(p.train_length)}/{int(p.test_length)}/'
    return key + f'{int(p.max_depth)}/{int(p.min_child_samples)}'

# ---- Cell ----
best_params = get_cb_params(catboost_daily_ic, t=1, best=0)
best_params

# ---- Cell ----
def select_cb_ic(params, ic_data, lookahead):
    return ic_data.loc[(ic_data.lookahead == lookahead) &
                       (ic_data.train_length == params.train_length) &
                       (ic_data.test_length == params.test_length) &
                       (ic_data.max_depth == params.max_depth) &
                       (ic_data.min_child_samples == params.min_child_samples)].set_index('date')

# ---- Cell ----
fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(20, 5))
axes = axes.flatten()
for i, t in enumerate([1, 21]):
    params = get_cb_params(catboost_daily_ic, t=t)
    data = select_cb_ic(params, catboost_ic, lookahead=t).sort_index()
    rolling = data.rolling(63).ic.mean().dropna()
    avg = data.ic.mean()
    med = data.ic.median()
    rolling.plot(ax=axes[i], title=f'Horizon: {t} Day(s) | IC: Mean={avg*100:.2f}   Median={med*100:.2f}')
    axes[i].axhline(avg, c='darkred', lw=1)
    axes[i].axhline(0, ls='--', c='k', lw=1)

fig.suptitle('3-Month Rolling Information Coefficient', fontsize=16)
fig.tight_layout()
fig.subplots_adjust(top=0.92);

# ---- Cell ----
lookahead = 1
# topn = 10
# for best in range(topn):
#     best_params = get_cb_params(catboost_daily_ic, t=lookahead, best=best)
#     key = get_cb_key(lookahead, best_params)
#     rounds = str(int(best_params.boost_rounds))
#     # key = '/1/1134/63'
#     if best == 0:
#         best_predictions = pd.read_hdf(results_path / 'tuning_catboost.h5', 'predictions/' + key)
#         best_predictions = best_predictions[rounds].to_frame(best)
#     else:
#         best_predictions[best] = pd.read_hdf(results_path / 'tuning_catboost.h5',
#                                              'predictions/' + key)[rounds]
# best_predictions = best_predictions.sort_index()

# ---- Cell ----
# best_predictions.to_hdf('data/predictions.h5', f'catboost/train/{lookahead:02}')
best_predictions = pd.read_hdf('data/predictions.h5', f'catboost/train/{lookahead:02}')
best_predictions.info()

# ---- Cell ----
def get_trade_prices(tickers):
    idx = pd.IndexSlice
    DATA_STORE = '../data/assets.h5'
    prices = (pd.read_hdf(DATA_STORE, 'quandl/wiki/prices').swaplevel().sort_index())
    prices.index.names = ['symbol', 'date']
    return (prices.loc[idx[tickers, '2015': '2017'], 'adj_open']
            .unstack('symbol')
            .sort_index()
            .shift(-1)
            .tz_localize('UTC'))

# ---- Cell ----
test_tickers = best_predictions.index.get_level_values('symbol').unique()

# ---- Cell ----
trade_prices = get_trade_prices(test_tickers)
trade_prices.info()

# ---- Cell ----
# only generate once to save time
trade_prices.to_hdf('data/model_tuning.h5', 'trade_prices/model_selection')

# ---- Cell ----
trade_prices = pd.read_hdf('data/model_tuning.h5', 'trade_prices/model_selection')

# ---- Cell ----
factor = best_predictions.iloc[:, :5].mean(1).dropna().tz_localize('UTC', level='date').swaplevel()

# ---- Cell ----
factor_data = get_clean_factor_and_forward_returns(factor=factor,
                                                   prices=trade_prices,
                                                   quantiles=5,
                                                   periods=(1, 5, 10, 21))

# ---- Cell ----
create_summary_tear_sheet(factor_data)

# ---- Cell ----
create_full_tear_sheet(factor_data)

# ---- Cell ----

