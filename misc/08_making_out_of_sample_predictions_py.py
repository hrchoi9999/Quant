# English filename: 08_making_out_of_sample_predictions_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/13일차 미국주식 고급머신러닝 투자전략 II/08_making_out_of_sample_predictions_clear.py
# Original filename: 08_making_out_of_sample_predictions_clear.py

# ---- Cell ----
!mkdir data&& cd data&& wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data/model_tuning.h5
!cd ..&& wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/utils.py
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data.zip&& unzip -n data.zip

# ---- Cell ----
!pip install catboost

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

from time import time
import sys, os
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

import lightgbm as lgb
from catboost import Pool, CatBoostRegressor

import matplotlib.pyplot as plt
import seaborn as sns

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
base_params = dict(boosting='gbdt',
                   objective='regression',
                   verbose=-1)

categoricals = ['year', 'month', 'sector', 'weekday']

# ---- Cell ----
lookahead = 1
store = Path('data/predictions.h5')

# ---- Cell ----
data = pd.read_hdf('data.h5', 'model_data').sort_index()

# ---- Cell ----
labels = sorted(data.filter(like='_fwd').columns)
features = data.columns.difference(labels).tolist()
label = f'r{lookahead:02}_fwd'

# ---- Cell ----
data = data.loc[idx[:, '2010':], features + [label]].dropna()

# ---- Cell ----
for feature in categoricals:
    data[feature] = pd.factorize(data[feature], sort=True)[0]

# ---- Cell ----
lgb_data = lgb.Dataset(data=data[features],
                       label=data[label],
                       categorical_feature=categoricals,
                       free_raw_data=False)

# ---- Cell ----
lgb_ic = pd.read_hdf('data/model_tuning.h5', 'lgb/ic')
lgb_daily_ic = pd.read_hdf('data/model_tuning.h5', 'lgb/daily_ic')

# ---- Cell ----
def get_lgb_params(data, t=5, best=0):
    param_cols = scope_params[1:] + lgb_train_params + ['boost_rounds']
    df = data[data.lookahead==t].sort_values('ic', ascending=False).iloc[best]
    return df.loc[param_cols]

# ---- Cell ----
for position in range(10):
    params = get_lgb_params(lgb_daily_ic,
                            t=lookahead,
                            best=position)

    params = params.to_dict()

    for p in ['min_data_in_leaf', 'num_leaves']:
        params[p] = int(params[p])
    train_length = int(params.pop('train_length'))
    test_length = int(params.pop('test_length'))
    num_boost_round = int(params.pop('boost_rounds'))
    params.update(base_params)

    print(f'\nPosition: {position:02}')

    # 1-year out-of-sample period
    n_splits = int(YEAR / test_length)
    cv = MultipleTimeSeriesCV(n_splits=n_splits,
                              test_period_length=test_length,
                              lookahead=lookahead,
                              train_period_length=train_length)

    predictions = []
    start = time()
    for i, (train_idx, test_idx) in enumerate(cv.split(X=data), 1):
        print(i, end=' ', flush=True)
        lgb_train = lgb_data.subset(used_indices=train_idx.tolist(),
                                    params=params).construct()

        model = lgb.train(params=params,
                          train_set=lgb_train,
                          num_boost_round=num_boost_round,
                          # verbose_eval=False
                         )

        test_set = data.iloc[test_idx, :]
        y_test = test_set.loc[:, label].to_frame('y_test')
        y_pred = model.predict(test_set.loc[:, model.feature_name()])
        predictions.append(y_test.assign(prediction=y_pred))

    if position == 0:
        test_predictions = (pd.concat(predictions)
                            .rename(columns={'prediction': position}))
    else:
        test_predictions[position] = pd.concat(predictions).prediction

by_day = test_predictions.groupby(level='date')
for position in range(10):
    if position == 0:
        ic_by_day = by_day.apply(lambda x: spearmanr(
            x.y_test, x[position])[0]).to_frame()
    else:
        ic_by_day[position] = by_day.apply(
            lambda x: spearmanr(x.y_test, x[position])[0])
print(ic_by_day.describe())
test_predictions.to_hdf(store, f'lgb/test/{lookahead:02}')

# ---- Cell ----
lookaheads = [1, 5, 21]

# ---- Cell ----
label_dict = dict(zip(lookaheads, labels))

# ---- Cell ----
lookahead = 1
store = Path('data/predictions.h5')

# ---- Cell ----
data = pd.read_hdf('data.h5', 'model_data').sort_index()

# ---- Cell ----
labels = sorted(data.filter(like='_fwd').columns)
features = data.columns.difference(labels).tolist()
label = f'r{lookahead:02}_fwd'

# ---- Cell ----
data = data.loc[idx[:, '2010':], features + [label]].dropna()

# ---- Cell ----
for feature in categoricals:
    data[feature] = pd.factorize(data[feature], sort=True)[0]

# ---- Cell ----
cat_cols_idx = [data.columns.get_loc(c) for c in categoricals]

# ---- Cell ----
catboost_data = Pool(label=data[label],
                     data=data.drop(label, axis=1),
                     cat_features=cat_cols_idx)

# ---- Cell ----
catboost_ic = pd.read_hdf('data/model_tuning.h5', 'catboost/ic')
catboost_ic_avg = pd.read_hdf('data/model_tuning.h5', 'catboost/daily_ic')

# ---- Cell ----
def get_cb_params(data, t=5, best=0):
    param_cols = scope_params[1:] + catboost_train_params + ['boost_rounds']
    df = data[data.lookahead==t].sort_values('ic', ascending=False).iloc[best]
    return df.loc[param_cols]

# ---- Cell ----
for position in range(10):
    params = get_cb_params(catboost_ic_avg,
                    t=lookahead,
                    best=position)

    params = params.to_dict()

    for p in ['max_depth', 'min_child_samples']:
        params[p] = int(params[p])
    train_length = int(params.pop('train_length'))
    test_length = int(params.pop('test_length'))
    num_boost_round = int(params.pop('boost_rounds'))
    # params['task_type'] = 'GPU'

    print(f'\nPosition: {position:02}')

    # 1-year out-of-sample period
    n_splits = int(YEAR / test_length)
    cv = MultipleTimeSeriesCV(n_splits=n_splits,
                              test_period_length=test_length,
                              lookahead=lookahead,
                              train_period_length=train_length)

    predictions = []
    start = time()
    for i, (train_idx, test_idx) in enumerate(cv.split(X=data), 1):
        print(i, end=' ', flush=True)
        train_set = catboost_data.slice(train_idx.tolist())

        model = CatBoostRegressor(**params)
        model.fit(X=train_set,
                  # verbose_eval=False
                 )

        test_set = data.iloc[test_idx, :]
        y_test = test_set.loc[:, label].to_frame('y_test')
        y_pred = model.predict(test_set.loc[:, model.feature_names_])
        predictions.append(y_test.assign(prediction=y_pred))

    if position == 0:
        test_predictions = (pd.concat(predictions)
                            .rename(columns={'prediction': position}))
    else:
        test_predictions[position] = pd.concat(predictions).prediction

by_day = test_predictions.groupby(level='date')
for position in range(10):
    if position == 0:
        ic_by_day = by_day.apply(lambda x: spearmanr(x.y_test, x[position])[0]).to_frame()
    else:
        ic_by_day[position] = by_day.apply(lambda x: spearmanr(x.y_test, x[position])[0])
print(ic_by_day.describe())
test_predictions.to_hdf(store, f'catboost/test/{lookahead:02}')

# ---- Cell ----

