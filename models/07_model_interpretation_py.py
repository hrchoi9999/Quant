# English filename: 07_model_interpretation_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/13일차 미국주식 고급머신러닝 투자전략 II/07_model_interpretation_clear.py
# Original filename: 07_model_interpretation_clear.py

# ---- Cell ----
!cd ..&& mkdir data&& cd data&&wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/data/assets.zip&&unzip -n assets.zip
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data.h5
!mkdir results&& cd results&& mkdir baseline && cd baseline && wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/results/baseline/sklearn_gbm_model.joblib

# ---- Cell ----
!pip install shap

# ---- Cell ----
%matplotlib inline

from pathlib import Path
import warnings
from random import randint
import joblib
from itertools import product

import numpy as np
import pandas as pd

import shap
import lightgbm as lgb
# from sklearn.inspection import (
#     plot_partial_dependence,
#                                 partial_dependence)

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.mplot3d import Axes3D
import seaborn as sns

# ---- Cell ----
warnings.filterwarnings('ignore')
sns.set_style('darkgrid')
idx = pd.IndexSlice
np.random.seed(42)

# ---- Cell ----
DATA_STORE = Path('../data/assets.h5')

# ---- Cell ----
with pd.HDFStore('data.h5') as store:
    best_params = store['best_params']

# ---- Cell ----
best_params

# ---- Cell ----
data = pd.read_hdf('data.h5', 'model_data').sort_index()
data = data.loc[idx[:, '2013':'2018'], :]

# ---- Cell ----
data.info()

# ---- Cell ----
dates = sorted(data.index.get_level_values('date').unique())

# ---- Cell ----
train_dates = dates[-int(best_params.train_length):]

# ---- Cell ----
data = data.loc[idx[:, train_dates], :]

# ---- Cell ----
labels = sorted(data.filter(like='_fwd').columns)
features = data.columns.difference(labels).tolist()

# ---- Cell ----
lookahead = 1
label = f'r{lookahead:02}_fwd'

# ---- Cell ----
categoricals = ['year', 'month', 'sector', 'weekday']

# ---- Cell ----
lgb_train = lgb.Dataset(data=data[features],
                       label=data[label],
                       categorical_feature=categoricals,
                       free_raw_data=False)

# ---- Cell ----
params = dict(boosting='gbdt', objective='regression', verbose=-1)

# ---- Cell ----
train_params = ['learning_rate', 'num_leaves', 'feature_fraction', 'min_data_in_leaf']

# ---- Cell ----
params.update(best_params.loc[train_params].to_dict())
for p in ['min_data_in_leaf', 'num_leaves']:
    params[p] = int(params[p])

# ---- Cell ----
# 좀더 오버피팅시켜서 feature importance보기
params['max_depth'] = 20
params['num_leaves'] = 2**8

# ---- Cell ----
lgb_model = lgb.train(params=params,
                  train_set=lgb_train,
                  num_boost_round=int(best_params.boost_rounds))

# ---- Cell ----
def get_feature_importance(model, importance_type='split'):
    fi = pd.Series(model.feature_importance(importance_type=importance_type),
                   index=model.feature_name())
    return fi/fi.sum()

# ---- Cell ----
feature_importance = (get_feature_importance(lgb_model).to_frame('Split').
                      join(get_feature_importance(lgb_model, 'gain').to_frame('Gain')))

# ---- Cell ----
(feature_importance
 .nlargest(20, columns='Gain')
 .sort_values('Gain', ascending=False)
 .plot
 .bar(subplots=True,
      layout=(2, 1),
      figsize=(14, 6),
      legend=False,
      sharey=True,
      rot=0))
plt.suptitle('Normalized Importance (Top 20 Features)', fontsize=14)
plt.tight_layout()
plt.subplots_adjust(top=.9);

# ---- Cell ----
class OneStepTimeSeriesSplit:
    pass

# ---- Cell ----
# gb_clf = joblib.load('results/baseline/sklearn_gbm_model.joblib')

# ---- Cell ----
def get_data(start='2000', end='2018', holding_period=1, dropna=False):
    idx = pd.IndexSlice
    target = f'target_{holding_period}m'
    with pd.HDFStore(DATA_STORE) as store:
        df = store['engineered_features']

    if start is not None and end is not None:
        df = df.loc[idx[:, start: end], :]
    if dropna:
        df = df.dropna()

    y = (df[target] > 0).astype(int)
    X = df.drop([c for c in df.columns if c.startswith('target')], axis=1)
    return y, X

# ---- Cell ----
def factorize_cats(df, cats=['sector']):
    cat_cols = ['year', 'month', 'age', 'msize'] + cats
    for cat in cats:
        df[cat] = pd.factorize(df[cat])[0]
    df.loc[:, cat_cols] = df.loc[:, cat_cols].fillna(-1)
    return df

# ---- Cell ----
y_clean, features_clean = get_data(dropna=True)
X = factorize_cats(features_clean).drop(['year', 'month'], axis=1)

# ---- Cell ----
X = data[features].sample(n=1000)

# ---- Cell ----
# load JS visualization code to notebook
shap.initjs()

# explain the model's predictions using SHAP values
explainer = shap.TreeExplainer(lgb_model)
shap_values = explainer.shap_values(X=X)

shap.summary_plot(shap_values, X, show=False)
plt.tight_layout();

# ---- Cell ----
shap.summary_plot(shap_values, X, plot_type="bar",show=False)
plt.tight_layout();

# ---- Cell ----
shap.initjs()
i = randint(0, len(X))
# visualize the first prediction's explanation
shap.force_plot(explainer.expected_value, shap_values[i,:], X.iloc[i,:])

# ---- Cell ----
shap.initjs()
shap.force_plot(explainer.expected_value, shap_values[:1000,:], X.iloc[:1000])

# ---- Cell ----
shap.dependence_plot(ind='r01',
                     shap_values=shap_values,
                     features=X,
                     interaction_index='r05',
                     title='Interaction between 1- and 5-Day Returns')

# ---- Cell ----

