# English filename: validation_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_앙상블_수업/검증과 앙상블 해답/검증과 앙상블 해답.py
# Original filename: 검증과 앙상블 해답.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/data_adult.zip&& unzip -n data_adult.zip

# ---- Cell ----
import os
from os.path import join
import copy
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

import sklearn

import matplotlib.pyplot as plt

adult_path = join('data', 'adult_data.csv')
column_path = join('data', 'adult_names.txt')

adult_columns = list()
for l in open(column_path):
    adult_columns = l.split()

# ---- Cell ----
adult_columns

# ---- Cell ----
data = pd.read_csv(adult_path, names = adult_columns)
label = data['income']

del data['income']
data.head()

# ---- Cell ----
data.shape

# ---- Cell ----
data.describe()

# ---- Cell ----
data.info()

# ---- Cell ----
data.shape

# ---- Cell ----
data = pd.get_dummies(data)
label = label.map(lambda x : 0 if x =='>50K' else 1)

# ---- Cell ----
data.shape

# ---- Cell ----
label.sum()

# ---- Cell ----
print('ones : {:.2f}%'.format((np.sum(label==1, axis=0)/len(data))*100))
print('zeros : {:.2f}%'.format((np.sum(label==0, axis=0)/len(data))*100))

# ---- Cell ----
from sklearn.model_selection import train_test_split

# (Train, Valid), Test 분할
x, x_test, y, y_test = train_test_split(data, label, test_size=0.2, stratify=label, shuffle=True)

# ---- Cell ----
# Train, Valid 분할
x_train, x_valid, y_train, y_valid = train_test_split(x, y, test_size=0.2, stratify=y, shuffle=True)

# ---- Cell ----
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier  #max_depth= 1, 3, 5
from sklearn.metrics import accuracy_score

#lr = LogisticRegression(random_state=2019, C=10.0)
lr = RandomForestClassifier(random_state=2019, max_depth=5)
# Train 데이터로 학습
lr.fit(x_train, y_train)

# ---- Cell ----
# Valid 데이터로 검증
y_pred_val = lr.predict(x_valid)
print('랜덤포리스트 회귀 검증 데이터 정확도 :  {:.2f}%'.format(accuracy_score(y_valid, y_pred_val)*100))

# ---- Cell ----
lr1 = LogisticRegression(random_state=2019, C=10.0)
#lr = RandomForestClassifier(random_state=2019, max_depth=5)
# Train 데이터로 학습
lr1.fit(x_train, y_train)

# ---- Cell ----
# Valid 데이터로 검증
y_pred_val = lr1.predict(x_valid)
print('로지스틱 회귀 검증 데이터 정확도 :  {:.2f}%'.format(accuracy_score(y_valid, y_pred_val)*100))

# ---- Cell ----
# Test 데이터로 모델 평가
y_pred = lr.predict(x_test)
print('랜덤포리스트 회귀 테스트 데이터 정확도 : {:.2f}%'.format(accuracy_score(y_test, y_pred)*100))

# ---- Cell ----
lr_opt =  RandomForestClassifier(random_state=2019, max_depth=5)
# Train 데이터로 학습
lr_opt.fit(x, y)

# ---- Cell ----
# Test 데이터로 모델 평가
y_pred = lr_opt.predict(x_test)
print('랜덤 포리스트 회귀 테스트 데이터 정확도 : {:.2f}%'.format(accuracy_score(y_test, y_pred)*100))

# ---- Cell ----


# ---- Cell ----
from sklearn.datasets import load_iris
iris = load_iris()

kf_data = iris.data
kf_label = iris.target
kf_columns = iris.feature_names

# ---- Cell ----
kf_data = pd.DataFrame(kf_data, columns = kf_columns)
kf_data.head()

# ---- Cell ----
kf_label

# ---- Cell ----
from sklearn.model_selection import KFold
kf = KFold(n_splits=5, shuffle=False)

# ---- Cell ----
for i, (trn_idx, val_idx) in enumerate(kf.split(kf_data.values, kf_label)) :
    trn_data, trn_label = kf_data.values[trn_idx, :], kf_label[trn_idx]
    val_data, val_label = kf_data.values[val_idx, :], kf_label[val_idx]

    print('{} Fold, trn label\n {}'.format(i, trn_label))
    print('{} Fold, val label\n {}\n'.format(i, val_label))

# ---- Cell ----
#### 셔플 테스트

# ---- Cell ----
from sklearn.model_selection import KFold
kf = KFold(n_splits=5, shuffle=True, random_state=42)

# ---- Cell ----
for trn_idx, val_idx in kf.split(kf_data.values, kf_label) :
    print(val_idx)
    print(trn_idx)
    break

# ---- Cell ----
# from sklearn.model_selection import StratifiedKFold
# skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

# ---- Cell ----
# for trn_idx, val_idx in skf.split(kf_data.values, kf_label) :
#     print(val_idx)
#     print(trn_idx)
#     break

# ---- Cell ----
from sklearn.model_selection import StratifiedKFold
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2019)

# ---- Cell ----
for i, (trn_idx, val_idx) in enumerate(skf.split(kf_data, kf_label)) :
    trn_data, trn_label = kf_data.values[trn_idx,:], kf_label[trn_idx]
    val_data, val_label = kf_data.values[val_idx,:], kf_label[val_idx]

    print('{} Fold, trn label\n {}'.format(i, trn_label))
    print('{} Fold, val label\n {}\n'.format(i, val_label))

# ---- Cell ----
from sklearn.ensemble import RandomForestClassifier

val_scores = list()

for i, (trn_idx, val_idx) in enumerate(skf.split(kf_data, kf_label)) :
    trn_data, trn_label = kf_data.values[trn_idx, :], kf_label[trn_idx]
    val_data, val_label = kf_data.values[val_idx, :], kf_label[val_idx]

    # 모델 정의
    clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=2019)

    # 모델 학습
    clf.fit(trn_data, trn_label)

    # 훈련, 검증 데이터 정확도 확인
    trn_acc = clf.score(trn_data, trn_label)*100
    val_acc = clf.score(val_data, val_label)*100  # score = predict + evaluation
    print('{} Fold, train Accuracy : {:.2f}%, validation Accuracy : {:.2f}%'.format(i, trn_acc, val_acc))

    val_scores.append(val_acc)

# 교차 검증 정확도 평균 계산하기
print('Cross Validation Score : {:.2f}%'.format(np.mean(val_scores)))

# ---- Cell ----
from sklearn.model_selection import cross_val_score

# ---- Cell ----
# 숫자로 전달하는 경우
rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=2019)
print('랜덤 포레스트 k-Fold CV Score(Acc) : {}'.format(np.mean(cross_val_score(rf, kf_data, kf_label, cv=5))))

# ---- Cell ----
# 객체로 전달하는 경우
rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=2019)
print('랜덤 포레스트 k-Fold CV Score(Acc) : {}'.format(np.mean(cross_val_score(rf, kf_data, kf_label, cv=skf))))

# ---- Cell ----
# fold 객체를 전달하는 경우 (연습)
# print('랜덤 포레스트 k-Fold CV Score(Acc) : {:.2f}%'.format()
# print('랜덤 포레스트 Stratify k-Fold CV Score(Acc) : {:.2f}%'.format()

# ---- Cell ----
from sklearn.model_selection import GridSearchCV
rf = RandomForestClassifier()

# ---- Cell ----
params = {'n_estimators' : [50, 100, 150, 200],
          'max_depth' : [5, 10 ,15, 20],
          'min_samples_split': [2, 5, 10]}

# ---- Cell ----
clf = GridSearchCV(rf, params, cv=skf)

# ---- Cell ----
#clf = GridSearchCV(RandomForestClassifier(), params, cv=skf)

# ---- Cell ----
clf.fit(kf_data, kf_label)

# ---- Cell ----
print('GridSearchCV best score : {:.2f}%, best_params : {}'.format(clf.best_score_*100, clf.best_params_))

# ---- Cell ----
clf.best_estimator_

# ---- Cell ----
# 문제: SVC를 시도하라 C=1, 10, 100  gamma=0.1, 1, 10
from sklearn.svm import SVC
svc=SVC()
params = {'C' : [1, 10, 100],
          'gamma' : [0.1, 1, 10]}
# GridSearchCV를 이용해서 best_params을 찾아라.

# ---- Cell ----
clf = GridSearchCV(svc, params, cv=skf)

# ---- Cell ----
clf.fit(kf_data, kf_label)

# ---- Cell ----
print('GridSearchCV best score : {:.2f}%, best_params : {}'.format(clf.best_score_*100, clf.best_params_))

# ---- Cell ----
clf.best_estimator_

# ---- Cell ----
from sklearn.model_selection import RandomizedSearchCV
rf = RandomForestClassifier()

# ---- Cell ----
params = {'n_estimators' : [50, 100, 150, 200],
          'max_depth' : [5, 10 ,15, 20],
          'min_samples_split': [2, 5, 10]}

# ---- Cell ----
clf = RandomizedSearchCV(rf,  param_distributions=params, scoring='accuracy', cv=skf)

# ---- Cell ----
clf.fit(kf_data, kf_label)

# ---- Cell ----
print('RadomizedSearchCV best score : {:.2f}%, best_params : {}'.format(clf.best_score_*100, clf.best_params_))

# ---- Cell ----
clf.best_estimator_

# ---- Cell ----
from sklearn.neural_network import MLPClassifier

# ---- Cell ----
from sklearn.ensemble import VotingClassifier
clfs = [('LR', LogisticRegression()),
        ('RF', RandomForestClassifier(max_depth=5)),
        ('MLP', MLPClassifier()) ]

vote_clf = VotingClassifier(clfs,voting='soft')

# ---- Cell ----
vote_clf.fit(x_train, y_train)

# ---- Cell ----
print('Cross Validation Acc : {:.2f}%'.format(vote_clf.score(x_valid, y_valid)*100))

# ---- Cell ----
y_pred = vote_clf.predict(x_test)

# ---- Cell ----
y_pred

# ---- Cell ----
print('Voting Ensemble Acc : {:.2f}%'.format(vote_clf.score(x_test, y_test)*100))

# ---- Cell ----
# 단일 모델에서의 Random Forest 성능
clf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=2019)
clf.fit(x_train, y_train)
print('Single Random Forest Acc : {:.2f}%'.format(clf.score(x_test, y_test)*100))

# ---- Cell ----
from sklearn.model_selection import StratifiedKFold
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=2019)

# ---- Cell ----
val_scores = list()
y_pred = np.zeros_like(y_test, dtype=np.float32)
for i, (trn_idx, val_idx) in enumerate(skf.split(x_train, y_train)) :
    trn_data, trn_label = x_train.values[trn_idx, :], y_train.values[trn_idx]
    val_data, val_label = x_train.values[val_idx, :], y_train.values[val_idx]
    # 모델 정의
    clf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=2019)
    # 모델 학습
    clf.fit(trn_data, trn_label)
#     trn_acc = clf.score(trn_data, trn_label)*100
#     val_acc = clf.score(val_data, val_label)*100
#     print('{} Fold, train Accuracy : {:.2f}%, validation Accuracy : {:.2f}%'.format(i, trn_acc, val_acc))
#    val_scores.append(val_acc)
    y_pred += (clf.predict_proba(x_test)[:, 1] / skf.n_splits)
    print(y_pred)
# Mean Validation Score
#print('Cross Validation Score : {:.2f}%'.format(np.mean(val_scores)))

# ---- Cell ----
y_pred

# ---- Cell ----
# 확률을 이진 라벨로 변경해줍니다.
y_pred = [0 if y < 0.5 else 1 for y in y_pred]
print('Average Blending Acc : {:.2f}%'.format(accuracy_score(y_test, y_pred)*100))

# ---- Cell ----


# ---- Cell ----
!pip install scikit_optimize

# ---- Cell ----
#[참고] 베이지안 탐색
# example of bayesian optimization with scikit-optimize
from numpy import mean
from sklearn.datasets import make_blobs
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from skopt.space import Integer
from skopt.utils import use_named_args
from skopt import gp_minimize

# generate 2d classification dataset
X, y = make_blobs(n_samples=500, centers=3, n_features=2)
# define the model
model = KNeighborsClassifier()
# define the space of hyperparameters to search
search_space = [Integer(1, 5, name='n_neighbors'), Integer(1, 2, name='p')]

# define the function used to evaluate a given configuration
@use_named_args(search_space)
def evaluate_model(**params):
	# something
	model.set_params(**params)
	# calculate 5-fold cross validation
	result = cross_val_score(model, X, y, cv=5, n_jobs=-1, scoring='accuracy')
	# calculate the mean of the scores
	estimate = mean(result)
	return 1.0 - estimate

# perform optimization
result = gp_minimize(evaluate_model, search_space)
# summarizing finding:
print('Best Accuracy: %.3f' % (1.0 - result.fun))
print('Best Parameters: n_neighbors=%d, p=%d' % (result.x[0], result.x[1]))

# ---- Cell ----
#[참고] 베이지안 탐색
# example of bayesian optimization with scikit-optimize
from numpy import mean
from sklearn.datasets import make_blobs
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier
from skopt.space import Integer
from skopt.utils import use_named_args
from skopt import gp_minimize

# generate 2d classification dataset
X, y = make_blobs(n_samples=500, centers=3, n_features=2)
# define the model
model = RandomForestClassifier()
# define the space of hyperparameters to search
search_space = [Integer(50, 200, name='n_estimators'), Integer(1, 10, name='max_depth')]

# define the function used to evaluate a given configuration
@use_named_args(search_space)
def evaluate_model(**params):
	# something
	model.set_params(**params)
	# calculate 5-fold cross validation
	result = cross_val_score(model, X, y, cv=5, n_jobs=-1, scoring='accuracy')
	# calculate the mean of the scores
	estimate = mean(result)
	return 1.0 - estimate

# perform optimization
result = gp_minimize(evaluate_model, search_space)
# summarizing finding:
print('Best Accuracy: %.3f' % (1.0 - result.fun))
print('Best Parameters: n_neighbors=%d, p=%d' % (result.x[0], result.x[1]))

# ---- Cell ----

