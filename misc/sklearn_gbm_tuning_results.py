# English filename: 03_sklearn_gbm_tuning_results_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/11일차 고급머신러닝의 이해 및 구현 실습/03_sklearn_gbm_tuning_results_clear.py
# Original filename: 03_sklearn_gbm_tuning_results_clear.py

# ---- Cell ----
!pip install -q --no-deps "numpy==1.24.3" "scikit-learn==1.3.2"
# !pip install scikit-learn==1.3.0
# !pip install numpy==1.24.3

# ---- Cell ----
!mkdir data&& cd data&& wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/data/tuning_sklearn_gbm.h5
!mkdir results&& cd results&& wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/12_gradient_boosting_machines/results/sklearn_gbm_gridsearch.joblib

# ---- Cell ----
import sklearn
sklearn.__version__

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

from pathlib import Path
import os
from datetime import datetime
import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import seaborn as sns
import graphviz

from statsmodels.api import OLS, add_constant
from sklearn.tree import DecisionTreeRegressor, export_graphviz
from sklearn.metrics import roc_auc_score
import joblib

# ---- Cell ----
import sklearn
print(sklearn.__version__)

# ---- Cell ----
sns.set_style("white")
np.random.seed(42)
pd.options.display.float_format = '{:,.4f}'.format

# ---- Cell ----
with pd.HDFStore('data/tuning_sklearn_gbm.h5') as store:
    test_feature_data = store['holdout/features']
    test_features = test_feature_data.columns
    test_target = store['holdout/target']

# ---- Cell ----
class OneStepTimeSeriesSplit:
    pass

# ---- Cell ----
gridsearch_result = joblib.load('results/sklearn_gbm_gridsearch.joblib')

# ---- Cell ----
pd.Series(gridsearch_result.best_params_)

# ---- Cell ----
f'{gridsearch_result.best_score_:.4f}'

# ---- Cell ----
best_model = gridsearch_result.best_estimator_

# ---- Cell ----
idx = pd.IndexSlice
test_dates = sorted(test_feature_data.index.get_level_values('date').unique())

# ---- Cell ----
auc = {}
for i, test_date in enumerate(test_dates):
    test_data = test_feature_data.loc[idx[:, test_date], :]
    preds = best_model.predict(test_data)
    auc[i] = roc_auc_score(y_true=test_target.loc[test_data.index], y_score=preds)

# ---- Cell ----
auc = pd.Series(auc)

# ---- Cell ----
auc.head()

# ---- Cell ----
ax = auc.sort_index(ascending=False).plot.barh(xlim=(.45, .55),
                                               title=f'Test AUC: {auc.mean():.2%}',
                                               figsize=(8, 4))
ax.axvline(auc.mean(), ls='--', lw=1, c='k')
sns.despine()
plt.tight_layout()

# ---- Cell ----
(pd.Series(best_model.feature_importances_,
           index=test_features)
 .sort_values()
 .tail(25)
 .plot.barh(figsize=(8, 5)))
sns.despine()
plt.tight_layout()

# ---- Cell ----
results = pd.DataFrame(gridsearch_result.cv_results_).drop('params', axis=1)
results.info()

# ---- Cell ----
results.head()

# ---- Cell ----
test_scores = results.filter(like='param').join(results[['mean_test_score']])
test_scores = test_scores.rename(columns={c: '_'.join(c.split('_')[1:]) for c in test_scores.columns})
test_scores.info()

# ---- Cell ----
params = test_scores.columns[:-1].tolist()

# ---- Cell ----
test_scores = test_scores.set_index('test_score').stack().reset_index()
test_scores.columns= ['test_score', 'parameter', 'value']
test_scores.head()

# ---- Cell ----
test_scores.info()

# ---- Cell ----
def get_test_scores(df):
    """Select parameter values and test scores"""
    data = df.filter(like='param').join(results[['mean_test_score']])
    return data.rename(columns={c: '_'.join(c.split('_')[1:]) for c in data.columns})

# ---- Cell ----
plot_data = get_test_scores(results).drop('min_impurity_decrease', axis=1)
plot_params = plot_data.columns[:-1].tolist()
plot_data.info()

# ---- Cell ----
fig, axes = plt.subplots(ncols=3, nrows=2, figsize=(12, 6))
axes = axes.flatten()

for i, param in enumerate(plot_params):
    sns.swarmplot(x=param, y='test_score', data=plot_data, ax=axes[i])

fig.suptitle('Mean Test Score Distribution by Hyperparameter', fontsize=14)
fig.tight_layout()
fig.subplots_adjust(top=.94)
fig.savefig('sklearn_cv_scores_by_param', dpi=300);

# ---- Cell ----
data = get_test_scores(results)
params = data.columns[:-1].tolist()
data = pd.get_dummies(data,columns=params, drop_first=False)
data.info()

# ---- Cell ----
reg_tree = DecisionTreeRegressor(
                                 criterion='friedman_mse',
                                 splitter='best',
                                 max_depth=4,
                                 min_samples_split=5,
                                 min_samples_leaf=10,
                                 min_weight_fraction_leaf=0.0,
                                 max_features=None,
                                 random_state=42,
                                 max_leaf_nodes=None,
                                 min_impurity_decrease=0.0,
                                 # min_impurity_split=None
                                )

# ---- Cell ----
gbm_features = data.drop('test_score', axis=1).columns
reg_tree.fit(X=data[gbm_features], y=data.test_score)

# ---- Cell ----
reg_tree.feature_importances_

# ---- Cell ----
out_file = 'results/gbm_sklearn_tree.dot'
dot_data = export_graphviz(reg_tree,
                          out_file=out_file,
                          feature_names=gbm_features,
                          max_depth=4,
                          filled=True,
                          rounded=True,
                          special_characters=True)
if out_file is not None:
    dot_data = Path(out_file).read_text()

graphviz.Source(dot_data)

# ---- Cell ----
reg_tree = DecisionTreeRegressor(criterion='friedman_mse',
                                 splitter='best',
                                 min_samples_split=2,
                                 min_samples_leaf=1,
                                 min_weight_fraction_leaf=0.0,
                                 max_features=None,
                                 random_state=42,
                                 max_leaf_nodes=None,
                                 min_impurity_decrease=0.0,
                                 # min_impurity_split=None
                                )

gbm_features = data.drop('test_score', axis=1).columns
reg_tree.fit(X=data[gbm_features], y=data.test_score)

# ---- Cell ----
gbm_fi = (pd.Series(reg_tree.feature_importances_,
                    index=gbm_features)
          .sort_values(ascending=False))
gbm_fi = gbm_fi[gbm_fi > 0]
idx = [p.split('_') for p in gbm_fi.index]
gbm_fi.index = ['_'.join(p[:-1]) + '=' + p[-1] for p in idx]
gbm_fi.sort_values().plot.barh(figsize=(5,5))
plt.title('Hyperparameter Importance')
sns.despine()
plt.tight_layout();

# ---- Cell ----
data = get_test_scores(results)
params = data.columns[:-1].tolist()
data = pd.get_dummies(data,columns=params, drop_first=True)

model = OLS(endog=data.test_score, exog=add_constant(data.drop('test_score', axis=1).astype(float))).fit(cov_type='HC3')
print(model.summary())

# ---- Cell ----

