# English filename: 11_pf_optimization_with_hrp_zipline_benchmark_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/13일차 미국주식 고급머신러닝 투자전략 II/11_pf_optimization_with_hrp_zipline_benchmark_clear.py
# Original filename: 11_pf_optimization_with_hrp_zipline_benchmark_clear.py

# ---- Cell ----
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/libta-lib0_0.4.0-oneiric1_amd64.deb -qO libta.deb
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/ta-lib0-dev_0.4.0-oneiric1_amd64.deb -qO ta.deb
!dpkg -i libta.deb ta.deb
!pip install ta-lib
!pip install zipline-reloaded==3.1.1 pyfolio-reloaded pyportfolioopt
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data/predictions.h5

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/zipline.zip &&unzip -n zipline.zip &&rm -rf /root/.zipline &&cp -r .zipline /root/

# ---- Cell ----
from time import time
import warnings
import sys

from pathlib import Path
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import pandas_datareader.data as web


from zipline import run_algorithm
from zipline.api import (attach_pipeline, pipeline_output,
                         date_rules, time_rules, record,get_datetime,
                         schedule_function, commission, slippage,
                         set_slippage, set_commission, set_max_leverage,
                         order_target, order_target_percent,
                         get_open_orders, cancel_order)
from zipline.data import bundles
from zipline.utils.run_algo import load_extensions
from zipline.pipeline import Pipeline, CustomFactor
from zipline.pipeline.data import Column, DataSet
from zipline.pipeline.domain import US_EQUITIES
from zipline.pipeline.filters import StaticAssets
from zipline.pipeline.loaders.frame import DataFrameLoader

from pypfopt.efficient_frontier import EfficientFrontier
from pypfopt.hierarchical_portfolio import HRPOpt
from pypfopt import risk_models
from pypfopt import expected_returns

import pyfolio as pf
from pyfolio.plotting import plot_rolling_returns, plot_rolling_sharpe
from pyfolio.timeseries import forecast_cone_bootstrap

# ---- Cell ----
sns.set_style('darkgrid')
warnings.filterwarnings('ignore')
np.random.seed(42)

# ---- Cell ----
N_LONGS = 25
MIN_POSITIONS = 20

# ---- Cell ----
bundle_data = bundles.load('quandl')

# ---- Cell ----
def load_predictions(bundle):
    path = Path('')
    predictions = pd.concat([pd.read_hdf(path / 'predictions.h5', 'lgb/train/01'),pd.read_hdf(path / 'predictions.h5', 'lgb/test/01').drop('y_test', axis=1)])
    predictions = (predictions.loc[~predictions.index.duplicated()]
                   .iloc[:, :10]
                   .mean(1)
                   .sort_index()
                   .dropna()
                  .to_frame('prediction'))
    tickers = predictions.index.get_level_values('symbol').unique().tolist()

    assets = bundle.asset_finder.lookup_symbols(tickers, as_of_date=None)
    predicted_sids = pd.Index([asset.sid for asset in assets])
    ticker_map = dict(zip(tickers, predicted_sids))

    return (predictions
            .unstack('symbol')
            .rename(columns=ticker_map)
            .prediction
            .tz_localize(None)), assets

# ---- Cell ----
predictions, assets = load_predictions(bundle_data)

# ---- Cell ----
predictions.info()

# ---- Cell ----
class SignalData(DataSet):
    predictions = Column(dtype=float)
    domain = US_EQUITIES

# ---- Cell ----
signal_loader = {SignalData.predictions:
                     DataFrameLoader(SignalData.predictions, predictions)}

# ---- Cell ----
class MLSignal(CustomFactor):
    """Converting signals to Factor
        so we can rank and filter in Pipeline"""
    inputs = [SignalData.predictions]
    window_length = 1

    def compute(self, today, assets, out, predictions):
        out[:] = predictions

# ---- Cell ----
def compute_signals():
    signals = MLSignal()
    return Pipeline(columns={
        'longs' : signals.top(N_LONGS, mask=signals > 0)
    },
            screen=StaticAssets(assets))

# ---- Cell ----
def before_trading_start(context, data):
    """
    Called every day before market open.
    """
    output = pipeline_output('signals')['longs'].astype(int)
    context.longs = output[output!=0].index
    if len(context.longs) < MIN_POSITIONS:
        context.divest = set(context.portfolio.positions.keys())
    else:
        context.divest = context.portfolio.positions.keys() - context.longs

# ---- Cell ----
def rebalance_equal_weighted(context, data):
    """
    Execute orders according to schedule_function() date & time rules.
    """
    for symbol, open_orders in get_open_orders().items():
        for open_order in open_orders:
            cancel_order(open_order)

    for asset in context.divest:
        order_target(asset, target=0)

    if len(context.longs) > context.min_positions:
        for asset in context.longs:
            order_target_percent(asset, 1/len(context.longs))

# ---- Cell ----
def optimize_weights(prices, short=False):
    """Uses PyPortfolioOpt to optimize weights"""
    returns = expected_returns.mean_historical_return(prices=prices,
                                                      frequency=252)
    cov = risk_models.sample_cov(prices=prices, frequency=252)

    # get weights that maximize the Sharpe ratio
    # using solver SCS which produces slightly fewer errors than default
    # see https://github.com/robertmartin8/PyPortfolioOpt/issues/221
    ef = EfficientFrontier(expected_returns=returns,
                           cov_matrix=cov,
                           weight_bounds=(0, 1),
                           solver='SCS')

    weights = ef.max_sharpe()
    if short:
        return {asset: -weight for asset, weight in ef.clean_weights().items()}
    else:
        return ef.clean_weights()

# ---- Cell ----
def rebalance_markowitz(context, data):
    """
    Execute orders according to schedule_function() date & time rules.
    """
    for symbol, open_orders in get_open_orders().items():
        for open_order in open_orders:
            cancel_order(open_order)

    for asset in context.divest:
        order_target(asset, target=0)

    if len(context.longs) > context.min_positions:
        prices = data.history(context.longs, fields='price',
                          bar_count=252+1, # for 1 year of returns
                          frequency='1d')
        try:
            markowitz_weights = optimize_weights(prices)
            for asset, target in markowitz_weights.items():
                order_target_percent(asset=asset, target=target)
        except Exception as e:
            # log.warn('{} {}'.format(get_datetime().date(), e))
            print('{} {}'.format(get_datetime().date(), e))

# ---- Cell ----
def rebalance_hierarchical_risk_parity(context, data):
    """
    Execute orders according to schedule_function() date & time rules.
    Uses PyPortfolioOpt to optimize weights
    """
    for symbol, open_orders in get_open_orders().items():
        for open_order in open_orders:
            cancel_order(open_order)

    for asset in context.divest:
        order_target(asset, target=0)

    if len(context.longs) > context.min_positions:
        returns = (data.history(context.longs, fields='price',
                          bar_count=252+1, # for 1 year of returns
                          frequency='1d')
                   .pct_change()
                   .dropna(how='all'))
        hrp_weights = HRPOpt(returns=returns).optimize()
        for asset, target in hrp_weights.items():
            order_target_percent(asset=asset, target=target)

# ---- Cell ----
def record_vars(context, data):
    """
    Plot variables at the end of each day.
    """
    record(leverage=context.account.leverage,
           longs=context.longs)

# ---- Cell ----
pf_algos = {
    'ew': rebalance_equal_weighted,
    'markowitz': rebalance_markowitz,
    'hrp': rebalance_hierarchical_risk_parity
}


# ---- Cell ----
# more descriptive labels for plots
algo_labels = {
    'ew': 'Equal Weighted',
    'markowitz': 'Markowitz (MFT)',
    'hrp': 'Hierarchical Risk Parity'
    }

# ---- Cell ----
# selected_pf_algo = 'hrp'
# selected_pf_algo = 'ew'
selected_pf_algo = 'markowitz'

# ---- Cell ----
def initialize(context):
    """
    Called once at the start of the algorithm.
    """
    context.n_longs = N_LONGS
    context.min_positions = MIN_POSITIONS
    context.universe = assets
    context.trades = pd.Series()
    context.longs = 0
    context.pf_algo = pf_algos.get(selected_pf_algo)

    set_slippage(slippage.FixedSlippage(spread=0.00))
    set_commission(commission.PerShare(cost=0.001, min_trade_cost=1))

    schedule_function(context.pf_algo,
                      # run every day after market open
                      date_rules.every_day(),
                      time_rules.market_open(hours=1, minutes=30))

    schedule_function(record_vars,
                      date_rules.every_day(),
                      time_rules.market_close())

    pipeline = compute_signals()
    attach_pipeline(pipeline, 'signals')

# ---- Cell ----
dates = predictions.index.get_level_values('date')
start_date, end_date = dates.min(), dates.max()

# ---- Cell ----
print('Start: {}\nEnd:   {}'.format(start_date.date(), end_date.date()))

# ---- Cell ----
import os
os.environ['ZIPLINE_ROOT'] = '/root/.zipline'

# ---- Cell ----
start = time()
results = run_algorithm(start=start_date,
                        end=end_date,
                        initialize=initialize,
                        before_trading_start=before_trading_start,
                        capital_base=1e5,
                        data_frequency='daily',
                        bundle='quandl',
                        custom_loader=signal_loader)  # need to modify zipline

print('Duration: {:.2f}s'.format(time() - start))

# ---- Cell ----
returns, positions, transactions = pf.utils.extract_rets_pos_txn_from_zipline(results)

# ---- Cell ----
with pd.HDFStore('backtests.h5') as store:
    store.put('returns/{}'.format(selected_pf_algo), returns)
    store.put('positions/{}'.format(selected_pf_algo), positions)
    store.put('transactions/{}'.format(selected_pf_algo), transactions)

# ---- Cell ----
with pd.HDFStore('backtests.h5') as store:
    print(store.info())

# ---- Cell ----
### 위에서 각 알고리즘을 한번씩 돌려서 backtests.h5에 저장.

# ---- Cell ----
# 이미 완성된 파일 다운로드
!rm -rf backtests.h5&& wget http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/13_unsupervised_learning/04_hierarchical_risk_parity/backtests.h5

# ---- Cell ----
benchmark = web.DataReader('SP500', 'fred', '2016', '2018').squeeze()
benchmark = benchmark.pct_change().tz_localize('UTC')

# ---- Cell ----
benchmark = benchmark.add(1).cumprod().reindex(index=returns.index.intersection(benchmark.index)).ffill().pct_change()
returns = returns.loc[benchmark.index[0]:]

# ---- Cell ----
fig, axes = plt.subplots(ncols=3, nrows=2, figsize=(18, 8))

for i, (algo, label) in enumerate(algo_labels.items()):
    returns = pd.read_hdf('backtests.h5', f'returns/{algo}')
    returns = returns.loc[benchmark.index[0]:]
    plot_rolling_returns(returns,
                         factor_returns=benchmark,
                         live_start_date='2017-01-01',
                         logy=False,
                         cone_std=2,
                         legend_loc='best',
                         volatility_match=False,
                         cone_function=forecast_cone_bootstrap,
                        ax=axes[0][i])
    plot_rolling_sharpe(returns, ax=axes[1][i], rolling_window=63)
    axes[0][i].set_title(f'{label} | Cumulative Returns')
    axes[1][i].set_title(f'{label} | Rolling Sharpe Ratio')
    fig.tight_layout()

# ---- Cell ----
def load_results(experiment='hrp'):
    with pd.HDFStore('backtests.h5') as store:
        returns = store.get('returns/{}'.format(experiment))
        returns = returns.loc[benchmark.index[0]:]
        positions = store.get('positions/{}'.format(experiment))
        transactions = store.get('transactions/{}'.format(experiment))
    return returns, positions, transactions

# ---- Cell ----
experiment = 'ew'
returns, positions, transactions = load_results(experiment)

pf.create_full_tear_sheet(returns,
                          positions=positions,
                          transactions=transactions,
                          benchmark_rets=benchmark,
                          live_start_date='2017-01-01',
                          round_trips=True)

# ---- Cell ----
experiment = 'hrp'
returns, positions, transactions = load_results(experiment)
returns = returns.loc[benchmark.index[0]:]

pf.create_full_tear_sheet(returns,
                          positions=positions,
                          transactions=transactions,
                          benchmark_rets=benchmark,
                          live_start_date='2017-01-01',
                          round_trips=True)

# ---- Cell ----
experiment = 'markowitz'
returns, positions, transactions = load_results(experiment)
returns = returns.loc[benchmark.index[0]:]

pf.create_full_tear_sheet(returns,
                          positions=positions,
                          transactions=transactions,
                          benchmark_rets=benchmark,
                          live_start_date='2017-01-01',
                          round_trips=True)

# ---- Cell ----

