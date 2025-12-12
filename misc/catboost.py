# English filename: catboost_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/CatBoost 튜톨리얼/catboost 튜토리얼_clear.py
# Original filename: catboost 튜토리얼_clear.py

# ---- Cell ----
!pip install  catboost
# !pip install ipywidgets
!pip install shap
# !pip install sklearn
# !jupyter nbextension enable --py widgetsnbextension

# ---- Cell ----
%matplotlib inline

# ---- Cell ----
import os
import pandas as pd
import numpy as np
np.set_printoptions(precision=4)

import catboost
print(catboost.__version__)

# ---- Cell ----
from catboost.datasets import amazon

# If you have "URLError: SSL: CERTIFICATE_VERIFY_FAILED" uncomment next two lines:
# import ssl
# ssl._create_default_https_context = ssl._create_unverified_context

# If you have any other error:
# Download datasets from http://bit.ly/2ZUXTSv and uncomment next line:
# train_df = pd.read_csv('train.csv', sep=',', header='infer')

(train_df, test_df) = amazon()

# ---- Cell ----
train_df.head()

# ---- Cell ----
train_df.info()

# ---- Cell ----
y = train_df.ACTION
X = train_df.drop('ACTION', axis=1)

# ---- Cell ----
cat_features = list(range(0, X.shape[1]))
print(cat_features)

# ---- Cell ----
print('Labels: {}'.format(set(y)))
print('Zero count = {}, One count = {}'.format(len(y) - sum(y), sum(y)))

# ---- Cell ----
cat_features

# ---- Cell ----
from catboost import CatBoostClassifier
model = CatBoostClassifier(iterations=100)
model.fit(X, y, cat_features=cat_features, verbose=10)

# ---- Cell ----
model.predict_proba(X)

# ---- Cell ----
from catboost import Pool
pool = Pool(data=X, label=y, cat_features=cat_features)

# ---- Cell ----
from sklearn.model_selection import train_test_split

data = train_test_split(X, y, test_size=0.2, random_state=0)

X_train, X_validation, y_train, y_validation = data

train_pool = Pool(
    data=X_train,
    label=y_train,
    cat_features=cat_features
)

validation_pool = Pool(
    data=X_validation,
    label=y_validation,
    cat_features=cat_features
)

# ---- Cell ----
model = CatBoostClassifier(
    iterations=50,
    learning_rate=0.1,
    loss_function='CrossEntropy'
    #loss_function = 'logloss'
)
model.fit(train_pool, eval_set=validation_pool, verbose=True)

print('Model is fitted: {}'.format(model.is_fitted()))
print('Model params:\n{}'.format(model.get_params()))

# ---- Cell ----
model = CatBoostClassifier(
    iterations=15,
#     verbose=5,
)
model.fit(train_pool, eval_set=validation_pool);

# ---- Cell ----
model = CatBoostClassifier(
    iterations=50,
    learning_rate=0.5,
    custom_loss=['AUC', 'Accuracy']
)

model.fit(
    train_pool,
    eval_set=validation_pool,
    verbose=False,
    plot=True
);

# ---- Cell ----
model1 = CatBoostClassifier(
    learning_rate=0.7,
    iterations=100,
    train_dir='learing_rate_0.7'
)

model2 = CatBoostClassifier(
    learning_rate=0.01,
    iterations=100,
    train_dir='learing_rate_0.01'
)

model1.fit(train_pool, eval_set=validation_pool, verbose=20)
model2.fit(train_pool, eval_set=validation_pool, verbose=20);

# ---- Cell ----
from catboost import MetricVisualizer
MetricVisualizer(['learing_rate_0.7', 'learing_rate_0.01']).start()

# ---- Cell ----
model = CatBoostClassifier(
    iterations=100,
#     use_best_model=False
)
model.fit(
    train_pool,
    eval_set=validation_pool,
    verbose=False,
    plot=True
);

# ---- Cell ----
print('Tree count: ' + str(model.tree_count_))

# ---- Cell ----
from catboost import cv

params = {
    'loss_function': 'Logloss',
    'iterations': 80,
    'custom_loss': 'AUC',
    'learning_rate': 0.5,
}

cv_data = cv(
    params = params,
    pool = train_pool,
    fold_count=5,
    shuffle=True,
    partition_random_seed=0,
    plot=True,
    verbose=False
)

# ---- Cell ----
cv_data.head(10)

# ---- Cell ----
best_value = np.min(cv_data['test-Logloss-mean'])
best_iter = np.argmin(cv_data['test-Logloss-mean'])

print('Best validation Logloss score, not stratified: {:.4f}±{:.4f} on step {}'.format(
    best_value,
    cv_data['test-Logloss-std'][best_iter],
    best_iter)
)

# ---- Cell ----
from catboost import cv

params = {
    'loss_function': 'Logloss',
    'iterations': 80,
    'custom_loss': 'AUC',
    'learning_rate': 0.5,
}

cv_data = cv(
    params = params,
    pool = train_pool,
    fold_count=5,
    shuffle=True,
    partition_random_seed=0,
    plot=True,
    stratified=False,
    verbose=False
)

# ---- Cell ----
best_value = cv_data['test-Logloss-mean'].min()
best_iter = cv_data['test-Logloss-mean'].values.argmin()

print('Best validation Logloss score, stratified: {:.4f}±{:.4f} on step {}'.format(
    best_value,
    cv_data['test-Logloss-std'][best_iter],
    best_iter)
)

# ---- Cell ----
cv_data[30:50]

# ---- Cell ----
from sklearn.model_selection import GridSearchCV

param_grid = {
#    "learning_rate": [0.001, 0.01, 0.5],
    "eta": [0.001, 0.01, 0.5],  #alias: eta
}

clf = CatBoostClassifier(
    iterations=20,
    cat_features=cat_features,
    verbose=20
)
grid_search = GridSearchCV(clf, param_grid=param_grid, cv=3)
results = grid_search.fit(X_train, y_train)
results.best_estimator_.get_params()

# ---- Cell ----
model_with_early_stop = CatBoostClassifier(
    iterations=200,
    learning_rate=0.5,
    early_stopping_rounds=10
)

model_with_early_stop.fit(
    train_pool,
    eval_set=validation_pool,
    verbose=False,
    plot=True
);

# ---- Cell ----
print(model_with_early_stop.tree_count_)

# ---- Cell ----
model_with_early_stop = CatBoostClassifier(
    eval_metric='AUC',
    iterations=200,
    learning_rate=0.5,
    early_stopping_rounds=20
)
model_with_early_stop.fit(
    train_pool,
    eval_set=validation_pool,
    verbose=False,
    plot=True
);

# ---- Cell ----
print(model_with_early_stop.tree_count_)

# ---- Cell ----
model = CatBoostClassifier(iterations=200, learning_rate=0.03)
model.fit(train_pool, verbose=50);

# ---- Cell ----
print(model.predict(X_validation))

# ---- Cell ----
print(model.predict_proba(X_validation))

# ---- Cell ----
raw_pred = model.predict(
    X_validation,
    prediction_type='RawFormulaVal'
)

print(raw_pred)

# ---- Cell ----
from numpy import exp

sigmoid = lambda x: 1 / (1 + exp(-x))

probabilities = sigmoid(raw_pred)

print(probabilities)

# ---- Cell ----
import matplotlib.pyplot as plt
from catboost.utils import get_roc_curve
from catboost.utils import get_fpr_curve
from catboost.utils import get_fnr_curve

curve = get_roc_curve(model, validation_pool)
(fpr, tpr, thresholds) = curve

(thresholds, fpr) = get_fpr_curve(curve=curve)
(thresholds, fnr) = get_fnr_curve(curve=curve)

# ---- Cell ----
plt.figure(figsize=(16, 8))
style = {'alpha':0.5, 'lw':2}

plt.plot(thresholds, fpr, color='blue', label='FPR', **style)
plt.plot(thresholds, fnr, color='green', label='FNR', **style)

plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xticks(fontsize=16)
plt.yticks(fontsize=16)
plt.grid(True)
plt.xlabel('Threshold', fontsize=16)
plt.ylabel('Error Rate', fontsize=16)
plt.title('FPR-FNR curves', fontsize=20)
plt.legend(loc="lower left", fontsize=16);

# ---- Cell ----
from catboost.utils import select_threshold

print(select_threshold(model, validation_pool, FNR=0.01))
print(select_threshold(model, validation_pool, FPR=0.01))

# ---- Cell ----
metrics = model.eval_metrics(
    data=validation_pool,
    metrics=['Logloss','AUC'],
    ntree_start=0,
    ntree_end=0,
    eval_period=1,
    plot=True
)

# ---- Cell ----
print('AUC values:\n{}'.format(np.array(metrics['AUC'])))

# ---- Cell ----
np.array(model.get_feature_importance(prettified=True))

# ---- Cell ----
np.array(model.get_feature_importance(
    data=train_pool,
    type='LossFunctionChange',
    prettified=True
))

# ---- Cell ----
print(model.predict_proba([X.iloc[1,:]]))
print(model.predict_proba([X.iloc[91,:]]))

# ---- Cell ----
shap_values = model.get_feature_importance(
    data=validation_pool,
    type='ShapValues'
)

# ---- Cell ----
shap_values[0, :]

# ---- Cell ----
expected_value = shap_values[0,-1]
shap_values = shap_values[:,:-1]
print(shap_values.shape)

# ---- Cell ----
proba = model.predict_proba([X.iloc[1,:]])[0]
raw = model.predict([X.iloc[1,:]], prediction_type='RawFormulaVal')[0]
print('Probabilities', proba)
print('Raw formula value %.4f' % raw)
print('Probability from raw value %.4f' % sigmoid(raw))

# ---- Cell ----
import shap

shap.initjs()
shap.force_plot(expected_value, shap_values[1,:], X_validation.iloc[1,:])

# ---- Cell ----
proba = model.predict_proba([X.iloc[91,:]])[0]
raw = model.predict([X.iloc[91,:]], prediction_type='RawFormulaVal')[0]
print('Probabilities', proba)
print('Raw formula value %.4f' % raw)
print('Probability from raw value %.4f' % sigmoid(raw))

# ---- Cell ----
import shap
shap.initjs()
shap.force_plot(expected_value, shap_values[91,:], X_validation.iloc[91,:])

# ---- Cell ----
shap.summary_plot(shap_values, X_validation)

# ---- Cell ----
# #!rm 'catboost_info/snapshot.bkp'

# model = CatBoostClassifier(
#     iterations=10,
#     save_snapshot=True,
#     snapshot_file='snapshot.bkp',
#     snapshot_interval=1
# )

# model.fit(train_pool, eval_set=validation_pool, verbose=10);

# ---- Cell ----
model = CatBoostClassifier(iterations=10)
model.fit(train_pool, eval_set=validation_pool, verbose=False)
model.save_model('catboost_model.bin')
model.save_model('catboost_model.json', format='json')

# ---- Cell ----
model.load_model('catboost_model.bin')
print(model.get_params())
print(model.learning_rate_)

# ---- Cell ----
tunned_model = CatBoostClassifier(
    iterations=1000,
    learning_rate=0.03,
    depth=6,
    l2_leaf_reg=3,
    random_strength=1,
    bagging_temperature=1
)

tunned_model.fit(
    X_train, y_train,
    cat_features=cat_features,
    verbose=False,
    eval_set=(X_validation, y_validation),
    plot=True
);

# ---- Cell ----
fast_model = CatBoostClassifier(
    boosting_type='Plain',
    rsm=0.5,
    one_hot_max_size=50,
    leaf_estimation_iterations=1,
    max_ctr_complexity=1,
    iterations=100,
    learning_rate=0.3,
    bootstrap_type='Bernoulli',
    subsample=0.5
)
fast_model.fit(
    X_train, y_train,
    cat_features=cat_features,
    verbose=False,
    eval_set=(X_validation, y_validation),
    plot=True
);

# ---- Cell ----
small_model = CatBoostClassifier(
    learning_rate=0.03,
    iterations=500,
    model_size_reg=50,
    max_ctr_complexity=1,
    ctr_leaf_count_limit=100
)
small_model.fit(
    X_train, y_train,
    cat_features=cat_features,
    verbose=False,
    eval_set=(X_validation, y_validation),
    plot=True
);

# ---- Cell ----

