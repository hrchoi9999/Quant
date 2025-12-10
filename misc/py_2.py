# English filename: py_2.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/LightGBM 종합_BPO_심리성향 예측/한번에_하이퍼파라미터 튜닝까지! 베이지안 최적화 적용 베이스라인_clear.py
# Original filename: 한번에_하이퍼파라미터 튜닝까지! 베이지안 최적화 적용 베이스라인_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/lgbm_bpo/data.zip && unzip -n data.zip
!pip install bayesian-optimization

# ---- Cell ----
import pandas as pd
import numpy as np

# ---- Cell ----
# 데이터 로드
train=pd.read_csv('data/train.csv', index_col=0)
test=pd.read_csv('data/test_x.csv', index_col=0)
submission=pd.read_csv('data/sample_submission.csv', index_col=0)

# ---- Cell ----
train

# ---- Cell ----
train.shape

# ---- Cell ----
X = train.drop('voted', axis = 1)
y = train['voted']

# ---- Cell ----
X.info()

# ---- Cell ----
print(X.race.value_counts())

# ---- Cell ----
print(X.age_group.value_counts())

# ---- Cell ----
print(X.gender.value_counts())

# ---- Cell ----
print(X.religion.value_counts())

# ---- Cell ----
print("원본 데이터 칼럼 : ", list(X.columns), "\n")
X_dummies = pd.get_dummies(X)
print("get_dummies된 데이터 칼럼 : ", list(X.columns))

# ---- Cell ----
print("X: {}\tX_dummies: {}".format(X.shape, X_dummies.shape))

# ---- Cell ----
test = pd.get_dummies(test)
test.shape

# ---- Cell ----
# 칼럼 개수 변화
print("X : {}\ntest : {}".format(X_dummies.shape, test.shape))
# 인코딩 확인
print("Encoding Success") if list(X_dummies.columns) == list(test.columns) else list(test.columns)

# ---- Cell ----
X = X_dummies.copy()

# ---- Cell ----
# nan 값 메꾸기
X = X.fillna(X.mean())
# 중복 값 제거
X.drop_duplicates(keep='first', inplace = True)
# 비교 -> nan 없음
X.shape

# ---- Cell ----
pd.set_option('display.max_row', 500)
pd.set_option('display.max_columns', 100)

# ---- Cell ----
X.tail()

# ---- Cell ----


# ---- Cell ----
from sklearn.preprocessing import MinMaxScaler
# 데이터 스케일링 -> 민맥스/스텐다드 모두 성능 비슷함
scaler=MinMaxScaler()
scaler.fit(X)
X=scaler.transform(X)
# 테스트 데이터도 동일 스케일러로
test=scaler.transform(test)

# ---- Cell ----
X

# ---- Cell ----
import lightgbm as lgbm
from bayes_opt import BayesianOptimization  # pip install bayesian-optimization
from sklearn.metrics import roc_auc_score, make_scorer
from sklearn.model_selection import cross_validate

# ---- Cell ----
#목적함수 생성
def lgbm_cv(learning_rate, num_leaves, max_depth, min_child_weight, colsample_bytree, feature_fraction, bagging_fraction, lambda_l1, lambda_l2):
    model = lgbm.LGBMClassifier(learning_rate=learning_rate,
                                n_estimators = 300,
                                #boosting = 'dart',
                                num_leaves = int(round(num_leaves)),
                                max_depth = int(round(max_depth)),
                                min_child_weight = int(round(min_child_weight)),
                                colsample_bytree = colsample_bytree,
                                feature_fraction = max(min(feature_fraction, 1), 0),
                                bagging_fraction = max(min(bagging_fraction, 1), 0),
                                lambda_l1 = max(lambda_l1, 0),
                                lambda_l2 = max(lambda_l2, 0)
                               )
    scoring = {'roc_auc_score': make_scorer(roc_auc_score)}
    result = cross_validate(model, X, y, cv=5, scoring=scoring)
    auc_score = result["test_roc_auc_score"].mean()
    return auc_score

# ---- Cell ----
# 입력값의 탐색 대상 구간
pbounds = {'learning_rate' : (0.0001, 0.05),
           'num_leaves': (300, 600),
           'max_depth': (2, 25),
           'min_child_weight': (30, 100),
           'colsample_bytree': (0, 0.99),
           'feature_fraction': (0.0001, 0.99),
           'bagging_fraction': (0.0001, 0.99),
           'lambda_l1' : (0, 0.99),
           'lambda_l2' : (0, 0.99),
          }

# ---- Cell ----
#객체 생성
lgbmBO = BayesianOptimization(f = lgbm_cv, pbounds = pbounds, verbose = 2, random_state = 0 )

# ---- Cell ----
# 반복적으로 베이지안 최적화 수행
# acq='ei'사용
# xi=0.01 로 exploration의 강도를 조금 높임
lgbmBO.maximize(init_points=5, n_iter = 2)

# ---- Cell ----
# 찾은 파라미터 값 확인
lgbmBO.max

# ---- Cell ----
#파라미터 적용
fit_lgbm = lgbm.LGBMClassifier(learning_rate=lgbmBO.max['params']['learning_rate'],
                               num_leaves = int(round(lgbmBO.max['params']['num_leaves'])),
                               max_depth = int(round(lgbmBO.max['params']['max_depth'])),
                               min_child_weight = int(round(lgbmBO.max['params']['min_child_weight'])),
                               colsample_bytree=lgbmBO.max['params']['colsample_bytree'],
                               feature_fraction = max(min(lgbmBO.max['params']['feature_fraction'], 1), 0),
                               bagging_fraction = max(min(lgbmBO.max['params']['bagging_fraction'], 1), 0),
                               lambda_l1 = lgbmBO.max['params']['lambda_l1'],
                               lambda_l2 = lgbmBO.max['params']['lambda_l2']
                               )

# ---- Cell ----
model = fit_lgbm.fit(X,y)

# ---- Cell ----
import joblib
joblib.dump(model, 'lgbmBO_201006.pkl')

# ---- Cell ----
pred_y = model.predict(test)

# ---- Cell ----
submission['voted']=pred_y
submission.to_csv('lgbmBO_201006.csv')

# ---- Cell ----

