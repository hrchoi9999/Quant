# English filename: 스태킹1_data_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_앙상블_수업/스태킹1-test data.py
# Original filename: 스태킹1-test data.py

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

# ---- Cell ----
X_data.shape, y_data.shape

# ---- Cell ----
from sklearn.model_selection import train_test_split

# (Train, Valid), Test 분할
X, X_test, y, y_test = train_test_split(X_data, y_data, test_size=0.2, stratify=y_data, random_state=0)
print(len(X))
print(len(X_test))
print(len(y))
print(len(y_test))
print("")
# Train, Valid 분할
X_train, X_valid, y_train, y_valid = train_test_split(X, y, test_size=0.25, stratify=y, random_state=0)

#size 확인
print(len(X_train))
print(len(X_valid))
print(len(y_train))
print(len(y_valid))

# ---- Cell ----
#y

# ---- Cell ----
# 개별 모델
svm=SVC(random_state=0)
rf=RandomForestClassifier(n_estimators=100)
lr=LogisticRegression()

# ---- Cell ----
!pip install catboost

# ---- Cell ----
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

# ---- Cell ----
#최종모델
lgbm=LGBMClassifier()

# ---- Cell ----
svm.fit(X_train, y_train)
rf.fit(X_train, y_train)
lr.fit(X_train, y_train)

# ---- Cell ----
svm_pred=svm.predict(X_valid)
rf_pred=rf.predict(X_valid)
lr_pred=lr.predict(X_valid)
print("svm:{0:.4f}, rf:{1:.4f}, lr:{2:.4f}".format(accuracy_score(y_valid, svm_pred),
                                                   accuracy_score(y_valid, rf_pred),
                                                   accuracy_score(y_valid, lr_pred)))

# ---- Cell ----
new_data=np.array([svm_pred, rf_pred, lr_pred])
new_data.shape

# ---- Cell ----
new_data=np.transpose(new_data)
new_data.shape

# ---- Cell ----
# np.random.shuffle(new_data)

# ---- Cell ----
new_data[:5]

# ---- Cell ----
lgbm.fit(new_data, y_valid)
lgbm_pred=lgbm.predict(new_data)
print("정확도: {0:.8f}".format(accuracy_score(y_valid, lgbm_pred)))

# ---- Cell ----
# test stacking

# ---- Cell ----
svm_pred=svm.predict(X_test)
rf_pred=rf.predict(X_test)
lr_pred=lr.predict(X_test)
print("svm:{0:.4f}, rf:{1:.4f}, lr:{2:.4f}".format(accuracy_score(y_test, svm_pred),
                                                   accuracy_score(y_test, rf_pred),
                                                   accuracy_score(y_test, lr_pred)))

# ---- Cell ----
new_data2=np.array([svm_pred, rf_pred, lr_pred])
new_data2.shape

# ---- Cell ----
new_data2=np.transpose(new_data2)
new_data2.shape

# ---- Cell ----
#lgbm.fit(new_data2, y_test)
lgbm_pred2=lgbm.predict(new_data2)
print("정확도: {0:.8f}".format(accuracy_score(y_test, lgbm_pred2)))

# ---- Cell ----

