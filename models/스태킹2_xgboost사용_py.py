# English filename: 스태킹2_xgboost사용_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_앙상블_수업/스태킹2-xgboost사용.py
# Original filename: 스태킹2-xgboost사용.py

# ---- Cell ----
 # 기본 라이브러리를 불러오기
import pandas as pd
import numpy as np

# 시각화 라이브러리 불러오기
import matplotlib.pyplot as plt
import seaborn as sns
%matplotlib inline

# 변환을 위한 라이브러리 불러오기
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer

# 통계 모델 라이브러리 불러오기
from sklearn.linear_model import LogisticRegressionCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.svm import SVC
import xgboost as xgb

# 딥러닝 라이브러리도 일단 불러오기
# from keras.models import Sequential
# from keras.layers import Dense
# from keras.wrappers.scikit_learn import KerasClassifier

# 성과지표를 계산하기 위한 라이브러리 불러오기
from sklearn.metrics import accuracy_score, precision_score, recall_score, confusion_matrix

import warnings
warnings.filterwarnings("ignore")

# ---- Cell ----
from sklearn.datasets import load_breast_cancer
data = load_breast_cancer()

# ---- Cell ----
X_data=data.data
y_data=data.target
X_train, X_test, y_train, y_test = train_test_split(X_data, y_data, test_size=0.2, random_state=0)

# ---- Cell ----
print(X_train.shape, X_test.shape)
print(y_train.shape, y_test.shape)

# ---- Cell ----
# 개별 모델
svm=SVC(random_state=0)
rf=RandomForestClassifier(n_estimators=100, random_state=0)
lr=LogisticRegression()

# ---- Cell ----
#from lightgbm import LGBMClassifier

# ---- Cell ----
#conda install -c anaconda py-xgboost
#pip install xgboost
#from xgboost import XGBoostClassifer

# ---- Cell ----
from xgboost.sklearn import XGBClassifier
#from xgboost.sklearn import XGBRegressor

# ---- Cell ----
#최종모델
xgb=XGBClassifier()

# ---- Cell ----
svm.fit(X_train, y_train)
rf.fit(X_train, y_train)
lr.fit(X_train, y_train)

# ---- Cell ----
svm_pred=svm.predict(X_test)
rf_pred=rf.predict(X_test)
lr_pred=lr.predict(X_test)
print("svm:{0:.4f}, rf:{1:.4f}, lr:{2:.4f}".format(accuracy_score(y_test, svm_pred),
                                                   accuracy_score(y_test, rf_pred),
                                                   accuracy_score(y_test, lr_pred)))

# ---- Cell ----
new_data=np.array([svm_pred, rf_pred, lr_pred])
new_data.shape

# ---- Cell ----
new_data=np.transpose(new_data)
new_data.shape

# ---- Cell ----
new_data[:3]

# ---- Cell ----
xgb.fit(new_data, y_test)
xgb_pred=xgb.predict(new_data)
print("정확도: {0:.4f}".format(accuracy_score(y_test, xgb_pred)))

# ---- Cell ----
# xgboost 연습

# ---- Cell ----
from sklearn import datasets
from sklearn.model_selection import train_test_split
from sklearn.model_selection import cross_val_score

X, y = datasets.make_classification(n_samples=10000, n_features=20,
                                    n_informative=2, n_redundant=10,
                                    random_state=42)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3,
                                                    random_state=42)

from xgboost.sklearn import XGBClassifier
#from xgboost.sklearn import XGBRegressor

xclas = XGBClassifier()  # and for classifier
xclas.fit(X_train, y_train)
xclas.predict(X_test)


print(cross_val_score(xclas, X_train, y_train)  )

# ---- Cell ----

