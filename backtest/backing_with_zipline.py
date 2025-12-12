# English filename: 09_backing_with_zipline_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/13일차 미국주식 고급머신러닝 투자전략 II/09_backtesting_with_zipline_clear.py
# Original filename: 09_backtesting_with_zipline_clear.py

# ---- Cell ----
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/libta-lib0_0.4.0-oneiric1_amd64.deb -qO libta.deb
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/ta-lib0-dev_0.4.0-oneiric1_amd64.deb -qO ta.deb
!dpkg -i libta.deb ta.deb
!pip install ta-lib
!pip install zipline-reloaded==3.1.1 pyfolio-reloaded

# ---- Cell ----
!mkdir data&& cd data&& wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data/predictions.h5

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/zipline.zip &&unzip -n zipline.zip &&rm -rf /root/.zipline &&cp -r .zipline /root/

# ---- Cell ----
from collections import defaultdict
from time import time
import warnings

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import pandas_datareader.data as web
# from logbook import Logger, StderrHandler, INFO, WARNING

from zipline import run_algorithm
from zipline.api import (attach_pipeline, pipeline_output,
                         date_rules, time_rules, record,
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
from zipline.pipeline.loaders import USEquityPricingLoader
from zipline.pipeline.loaders.frame import DataFrameLoader
# from trading_calendars import get_calendar

import pyfolio as pf
from pyfolio.plotting import plot_rolling_returns, plot_rolling_sharpe
from pyfolio.timeseries import forecast_cone_bootstrap

# ---- Cell ----
# optional; not pre-installed; see above
# import seaborn as sns
# sns.set_style('darkgrid')

# ---- Cell ----
warnings.filterwarnings('ignore')
np.random.seed(42)

# ---- Cell ----
# import os
# os.environ['ZIPLINE_ROOT'] = '/root/.ziplin'

# ---- Cell ----
# load_extensions(default=True,
#                 extensions=[],
#                 strict=True,
#                 environ=None)

# ---- Cell ----
# log_handler = StderrHandler(format_string='[{record.time:%Y-%m-%d %H:%M:%S.%f}]: ' +
#                             '{record.level_name}: {record.func_name}: {record.message}',
#                             level=WARNING)
# log_handler.push_application()
# log = Logger('Algorithm')

# ---- Cell ----
N_LONGS = 25
N_SHORTS = 25
MIN_POSITIONS = 20

# ---- Cell ----
%load_ext zipline

# ---- Cell ----
bundle_data = bundles.load('quandl')

# ---- Cell ----
# !pip install --upgrade tables

# ---- Cell ----
def load_predictions(bundle):
    predictions = pd.concat(
        [pd.read_hdf('data/predictions.h5', 'lgb/train/01'), pd.read_hdf('data/predictions.h5', 'lgb/test/01').drop('y_test', axis=1)]
    )
    # predictions = (pd.read_hdf('data/predictions.h5', 'lgb/train/01')
    #                .append(pd.read_hdf('data/predictions.h5', 'lgb/test/01').drop('y_test', axis=1)))
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

    def compute(self, today, assets, out, predictions):  #inputs가 predictions로 들어간다.
        out[:] = predictions

# ---- Cell ----
def compute_signals():
    signals = MLSignal()
    return Pipeline(columns={
        'longs' : signals.top(N_LONGS, mask=signals > 0),
        'shorts': signals.bottom(N_SHORTS, mask=signals < 0)},
            screen=StaticAssets(assets))

# ---- Cell ----
def initialize(context):
    """
    Called once at the start of the algorithm.
    """
    context.n_longs = N_LONGS
    context.n_shorts = N_SHORTS
    context.min_positions = MIN_POSITIONS
    context.universe = assets
    context.trades = pd.Series()
    context.longs = context.shorts = 0

    set_slippage(slippage.FixedSlippage(spread=0.00))
    set_commission(commission.PerShare(cost=0.001, min_trade_cost=0))

    schedule_function(rebalance,
                      date_rules.every_day(),
#                       date_rules.week_start(),
                      time_rules.market_open(hours=1, minutes=30))

    schedule_function(record_vars,
                      date_rules.every_day(),
                      time_rules.market_close())

    pipeline = compute_signals()
    attach_pipeline(pipeline, 'signals')

# ---- Cell ----
def before_trading_start(context, data):
    """
    Called every day before market open.
    """
    output = pipeline_output('signals')
    df = pd.concat([output['longs'].astype(int),output['shorts'].astype(int).mul(-1)])

    holdings = df[df!=0]
    other = df[df==0]
    other = other[~other.index.isin(holdings.index) & ~other.index.duplicated()]
    context.trades = pd.concat([holdings,other])
    assert len(context.trades.index.unique()) == len(context.trades)

# ---- Cell ----
# 참고 defaultdic()
# d = {}
# # d['apple']에 값을 할당하지 않고 바로 접근하면 KeyError가 발생
# d['apple'].append('red')  # KeyError 발생

# from collections import defaultdict
# d = defaultdict(list)
# # d['apple']에 아무 값도 할당하지 않았지만, defaultdict 덕분에 # 빈 리스트로 자동 초기화
# d['apple'].append('red')  # 이제 오류 없이 작동합니다.
# print(d)
# 출력: defaultdict(<class 'list'>, {'apple': ['red']})

# ---- Cell ----
def rebalance(context, data):
    """
    Execute orders according to schedule_function() date & time rules.
    """
    trades = defaultdict(list)
    for symbol, open_orders in get_open_orders().items():
        for open_order in open_orders:
            cancel_order(open_order)

    positions = context.portfolio.positions
    s=pd.Series({s:v.amount*v.last_sale_price for s, v in positions.items()}).sort_values(ascending=False)
    for stock, trade in context.trades.items():
        if trade == 0:
            order_target(stock, target=0)
        else:
            trades[trade].append(stock)

            #{
            #    1: ['AAPL'],
            #   -1: ['MSFT', 'AMZN']
            #}


    context.longs, context.shorts = len(trades[1]), len(trades[-1])
#     log.warning('{} {:,.0f}'.format(len(positions), context.portfolio.portfolio_value))
    if context.longs > context.min_positions and context.shorts > context.min_positions:
        for stock in trades[-1]:
            order_target_percent(stock, -1 / context.shorts)
        for stock in trades[1]:
            order_target_percent(stock, 1 / context.longs)
    else:
        for stock in trades[-1] + trades[1]:
            if stock in positions:
                order_target(stock, 0)

# ---- Cell ----
def record_vars(context, data):
    """
    Plot variables at the end of each day.
    """
    record(leverage=context.account.leverage,
           longs=context.longs,
           shorts=context.shorts)

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
returns, positions, transactions = pf.utils.extract_rets_pos_txn_from_zipline(results) #

# ---- Cell ----
benchmark = web.DataReader('SP500', 'fred', '2014', '2018').squeeze()
benchmark = benchmark.pct_change().tz_localize('UTC')

# ---- Cell ----
benchmark = benchmark.add(1).cumprod().reindex(index=returns.index.intersection(benchmark.index)).ffill().pct_change()
returns = returns.loc[benchmark.index[0]:]

# ---- Cell ----
fig, axes = plt.subplots(ncols=2, figsize=(16, 5))
plot_rolling_returns(returns,
                     factor_returns=benchmark,
                     live_start_date='2017-01-01',
                     logy=False,
                     cone_std=2,
                     legend_loc='best',
                     volatility_match=False,
                     cone_function=forecast_cone_bootstrap,
                    ax=axes[0])
plot_rolling_sharpe(returns, ax=axes[1], rolling_window=63)
axes[0].set_title('Cumulative Returns - In and Out-of-Sample')
axes[1].set_title('Rolling Sharpe Ratio (3 Months)')
fig.tight_layout();

# ---- Cell ----
pf.create_full_tear_sheet(returns,                #
                          positions=positions,
                          transactions=transactions,
                          benchmark_rets=benchmark,
                          live_start_date='2017-01-01',
                          round_trips=True)

# ---- Cell ----

