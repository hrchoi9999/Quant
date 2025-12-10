# English filename: 스태킹2_cv_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_앙상블_수업/스태킹2-CV.py
# Original filename: 스태킹2-CV.py

# ---- Cell ----
 # 기본 라이브러리
import pandas as pd
import numpy as np
# 시각화 라이브러리
import matplotlib.pyplot as plt
import seaborn as sns
%matplotlib inline
# 변환용 라이브러리
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
# 통계 및 모델링 라이브러리
from sklearn.linear_model import LogisticRegressionCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.svm import SVC
import xgboost as xgb
# 딥러닝 라이브러리
from keras.models import Sequential
from keras.layers import Dense
# 성과 지표 라이브러리
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
from sklearn.model_selection import KFold

# ---- Cell ----
#n_folds=3

# ---- Cell ----
def get_stacking_data(model, X_train, y_train, X_test, n_folds=3):
    kfold=KFold(n_splits=n_folds, random_state=0, shuffle=True)
    train_fold_predict=np.zeros((X_train.shape[0], 1))
    test_predict=np.zeros((X_test.shape[0], n_folds))
    print("model :", model.__class__.__name__)

    for cnt, (train_index, valid_index) in enumerate(kfold.split(X_train)):
        X_train_ = X_train[train_index]
        y_train_ = y_train[train_index]
        X_validation=X_train[valid_index]

        #학습
        model.fit(X_train, y_train)
        # 해당 폴드에서 학습된 모델에 검증 데이터로 예측후 저장
        train_fold_predict[valid_index, :]=model.predict(X_validation).reshape(-1,1)
        # 해당 폴드에서 생성된 모델에 원본 테스트를 이용해 예측 수행하고 저장
        test_predict[:, cnt]=model.predict(X_test)
    #for 문이 끝나면 test_pred는 평균을 내서 하나로 합친다.
    test_predict_mean=np.mean(test_predict, axis=1).reshape(-1,1)

    return train_fold_predict, test_predict_mean

# ---- Cell ----
# 개별 모델
svm=SVC(random_state=0)
rf=RandomForestClassifier(n_estimators=100, random_state=0)
lr=LogisticRegression()

# ---- Cell ----
#from lightgbm import LGBMClassifier
from xgboost.sklearn import XGBClassifier

# ---- Cell ----
#최종모델
#lgbm=LGBMClassifier()
xgb=XGBClassifier()

# ---- Cell ----
svm_train1, svm_test1 = get_stacking_data(svm, X_train, y_train, X_test)
rf_train1, rf_test1 = get_stacking_data(rf, X_train, y_train, X_test)
lr_train1, lr_test1 = get_stacking_data(lr, X_train, y_train, X_test)

# ---- Cell ----
new_X_train1=np.concatenate((svm_train1, rf_train1, lr_train1), axis=1)
new_X_test1=np.concatenate((svm_test1, rf_test1, lr_test1), axis=1)

# ---- Cell ----
print("원본: ", X_train.shape, X_test.shape)
print("새것: ", new_X_train1.shape, new_X_test1.shape)

# ---- Cell ----
xgb.fit(new_X_train1, y_train)
stack_pred1=xgb.predict(new_X_test1)
print("정확도: {0:.4f}".format(accuracy_score(stack_pred1, y_test)))

# ---- Cell ----
#stratifiedKFold 기반 stacking ensemble
from sklearn.model_selection import KFold, StratifiedKFold

# ---- Cell ----
def get_stacking_data2(model, X_train, y_train, X_test, n_folds=6):
    stk=StratifiedKFold(n_splits=n_folds)
    #kfold=KFold(n_splits=n_folds, random_state=0)
    train_fold_predict=np.zeros((X_train.shape[0], 1))
    test_predict=np.zeros((X_test.shape[0], n_folds))
    print("model :", model.__class__.__name__)

    for cnt, (train_index, valid_index) in enumerate(stk.split(X_train,y_train)):
        X_train_ = X_train[train_index]
        y_train_ = y_train[train_index]
        X_validation=X_train[valid_index]

        #학습
        model.fit(X_train, y_train)
        # 해당 폴드에서 학습된 모델에 검증 데이터로 예측후 저장
        train_fold_predict[valid_index, :]=model.predict(X_validation).reshape(-1,1)
        # 해당 폴드에서 생성된 모델에 원본 테스트를 이용해 예측 수행하고 저장
        test_predict[:, cnt]=model.predict(X_test)
    #for 문이 끝나면 test_pred는 평균을 내서 하나로 합친다.
    test_predict_mean=np.mean(test_predict, axis=1).reshape(-1,1)

    return train_fold_predict, test_predict_mean

# ---- Cell ----
svm_train2, svm_test2 = get_stacking_data2(svm, X_train, y_train, X_test)
rf_train2, rf_test2 = get_stacking_data2(rf, X_train, y_train, X_test)
lr_train2, lr_test2 = get_stacking_data2(lr, X_train, y_train, X_test)

# ---- Cell ----
new_X_train2=np.concatenate((svm_train2, rf_train2, lr_train2), axis=1)
new_X_test2=np.concatenate((svm_test2, rf_test2, lr_test2), axis=1)

# ---- Cell ----
print("원본: ", X_train.shape, X_test.shape)
print("새것: ", new_X_train2.shape, new_X_test2.shape)

# ---- Cell ----
xgb.fit(new_X_train2, y_train)
stack_pred2=xgb.predict(new_X_test2)
print("정확도: {0:.4f}".format(accuracy_score(stack_pred2, y_test)))

# ---- Cell ----

