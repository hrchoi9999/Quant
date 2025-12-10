# English filename: xgboost_ligthgbm_catboost_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/XgBoost_LightGBM_CatBoost_세모델 비교/XGBoost_LigthGBM_CatBoost_비교_clear.py
# Original filename: XGBoost_LigthGBM_CatBoost_비교_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/lgbm_catboost_xgboost_compare/flights.zip && unzip -n flights.zip
!pip install catboost

# ---- Cell ----
import pandas as pd, numpy as np, time
from sklearn.model_selection import train_test_split

data = pd.read_csv("flights.csv")
data = data.sample(frac = 0.1, random_state=10)

data = data[["MONTH","DAY","DAY_OF_WEEK","AIRLINE","FLIGHT_NUMBER","DESTINATION_AIRPORT",
                 "ORIGIN_AIRPORT","AIR_TIME", "DEPARTURE_TIME","DISTANCE","ARRIVAL_DELAY"]]
data.dropna(inplace=True)

data["ARRIVAL_DELAY"] = (data["ARRIVAL_DELAY"]>10)*1

# ---- Cell ----
data.info()

# ---- Cell ----
cols=data.select_dtypes(include='object').columns
print(cols)

# ---- Cell ----
#cols = ["AIRLINE","FLIGHT_NUMBER","DESTINATION_AIRPORT","ORIGIN_AIRPORT"]
for item in cols:
    data[item] = data[item].astype("category").cat.codes +1

# ---- Cell ----
data

# ---- Cell ----
train, test, y_train, y_test = train_test_split(data.drop(["ARRIVAL_DELAY"], axis=1), data["ARRIVAL_DELAY"],
                                                random_state=10, test_size=0.25)

# ---- Cell ----
# https://injo.tistory.com/44 하이퍼파라미터 참조

# ---- Cell ----
import xgboost as xgb
from sklearn import metrics
from sklearn.model_selection import GridSearchCV

def auc(m, train, test):
    return (metrics.roc_auc_score(y_train,m.predict_proba(train)[:,1]),
                            metrics.roc_auc_score(y_test,m.predict_proba(test)[:,1]))

# Parameter Tuning
model = xgb.XGBClassifier()
# param_dist = {"max_depth": [10,30,50],
#               "min_child_weight" : [1,3,6],
#               "n_estimators": [200],
#               "learning_rate": [0.05, 0.1,0.16],}
param_dist = {"max_depth": [10,30],
              "min_child_weight" : [3],
              "n_estimators": [200],
              "learning_rate": [0.1],}

grid_search = GridSearchCV(model, param_grid=param_dist, cv = 2,
                                   verbose=10, n_jobs=-1)
grid_search.fit(train, y_train)

grid_search.best_estimator_

# ---- Cell ----
model = xgb.XGBClassifier(max_depth=50, min_child_weight=1,  n_estimators=200,\
                          n_jobs=-1 , verbose=1,learning_rate=0.16)
model.fit(train,y_train)

auc(model, train, test)

# ---- Cell ----
# https://injo.tistory.com/48?category=1068433 하이퍼 파라미터 참조

# ---- Cell ----
import lightgbm as lgb
from sklearn import metrics

def auc2(m, train, test):
    return (metrics.roc_auc_score(y_train,m.predict(train)),
                            metrics.roc_auc_score(y_test,m.predict(test)))

lg = lgb.LGBMClassifier(silent=False)
# param_dist = {"max_depth": [25,50, 75],
#               "learning_rate" : [0.01,0.05,0.1],
#               "num_leaves": [300,900,1200],
#               "n_estimators": [200]
#              }
param_dist = {"max_depth": [25,50],
              "learning_rate" : [0.01],
              "num_leaves": [300],
              "n_estimators": [100]
             }
grid_search = GridSearchCV(lg, n_jobs=-1, param_grid=param_dist, cv = 2, scoring="roc_auc", verbose=5)
grid_search.fit(train,y_train)
print(grid_search.best_estimator_)

# ---- Cell ----
d_train = lgb.Dataset(train, label=y_train)
params = {"max_depth": 50, "learning_rate" : 0.1, "num_leaves": 900,  "n_estimators": 300}

# Without Categorical Features
model2 = lgb.train(params, d_train)
auc2(model2, train, test)

# ---- Cell ----
d_train = lgb.Dataset(train, label=y_train)
params = {"max_depth": 50, "learning_rate" : 0.1, "num_leaves": 900,  "n_estimators": 300}

#With Catgeorical Features
cate_features_name = ["MONTH","DAY","DAY_OF_WEEK","AIRLINE","DESTINATION_AIRPORT",
                 "ORIGIN_AIRPORT"]
model2 = lgb.train(params, d_train, categorical_feature = cate_features_name)
auc2(model2, train, test)

# ---- Cell ----
import catboost as cb
cat_features_index = [0,1,2,3,4,5,6]

def auc(m, train, test):
    return (metrics.roc_auc_score(y_train,m.predict_proba(train)[:,1]),
                            metrics.roc_auc_score(y_test,m.predict_proba(test)[:,1]))

# params = {'depth': [4, 7, 10],
#           'learning_rate' : [0.03, 0.1, 0.15],
#          'l2_leaf_reg': [1,4,9],
#          'iterations': [300]}
params = {'depth': [4, 7],
          'learning_rate' : [0.1],
         'l2_leaf_reg': [1,4],
         'iterations': [20]}

cb1 = cb.CatBoostClassifier()
cb_model = GridSearchCV(cb1, params, scoring="roc_auc", cv = 3)
cb_model.fit(train, y_train)



# ---- Cell ----
#With Categorical features
clf = cb.CatBoostClassifier(eval_metric="AUC", depth=10, iterations= 500, l2_leaf_reg= 9, learning_rate= 0.15)
clf.fit(train,y_train)
auc(clf, train, test)

# ---- Cell ----
#With Categorical features
clf = cb.CatBoostClassifier(eval_metric="AUC",one_hot_max_size=31, \
                            depth=10, iterations= 500, l2_leaf_reg= 9, learning_rate= 0.15)
clf.fit(train,y_train, cat_features= cat_features_index)
auc(clf, train, test)

# ---- Cell ----
# 참고 https://www.kdnuggets.com/2018/03/catboost-vs-light-gbm-vs-xgboost.html
# 결과 비교하라.

# ---- Cell ----
from catboost import CatBoostClassifier, Pool

train_data = Pool(data=[[1, 4, 5, 6],
                        [4, 5, 6, 7],
                        [30, 40, 50, 60]],
                  label=[1, 1, -1],
                  weight=[0.1, 0.2, 0.3])

model = CatBoostClassifier(iterations=10)

model.fit(train_data)
preds_class = model.predict(train_data) #data도 됨

# ---- Cell ----
preds_class

# ---- Cell ----

