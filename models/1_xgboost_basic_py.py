# English filename: 1_xgboost_basic_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/부스팅과 해석성/1. Xgboost 기초_보스톤 주택가격_clear.py
# Original filename: 1. Xgboost 기초_보스톤 주택가격_clear.py

# ---- Cell ----
# XGboost 모델을 보스톤 주택가격에 적용해보자

# ---- Cell ----
!!pip install scikit-learn==1.0.2

# ---- Cell ----
from sklearn.datasets import load_boston
boston = load_boston()

# ---- Cell ----
#print(boston.keys())

# ---- Cell ----
#print(boston.data.shape)

# ---- Cell ----
#print(boston.feature_names)

# ---- Cell ----
#print(boston.DESCR)

# ---- Cell ----
import pandas as pd
data = pd.DataFrame(boston.data)
data.columns = boston.feature_names

# ---- Cell ----
data.head()

# ---- Cell ----
data['PRICE'] = boston.target

# ---- Cell ----
#data.info()

# ---- Cell ----
#data.describe()

# ---- Cell ----
# Xgboost는 NA를 처리하는 능력있다는 것을 기억해두라.

# ---- Cell ----
# pip install xgboost

# ---- Cell ----
import xgboost as xgb
from sklearn.metrics import mean_squared_error
import pandas as pd
import numpy as np

# ---- Cell ----
X, y = data.iloc[:,:-1],data.iloc[:,-1]

# ---- Cell ----
# xgboost의 성능을 올리기 위해 DMatrix를 사용한다.
data_dmatrix = xgb.DMatrix(data=X,label=y)

# ---- Cell ----
# xgboost의 하이퍼 파라미터 (읽고 싶은 사람 읽도록)
#
# learning_rate: step size shrinkage used to prevent overfitting. Range is [0,1]
# max_depth: determines how deeply each tree is allowed to grow during any boosting round.
# subsample: percentage of samples used per tree. Low value can lead to underfitting.
# colsample_bytree: percentage of features used per tree. High value can lead to overfitting.
# n_estimators: number of trees you want to build.
# objective: determines the loss function to be used like reg:linear for regression problems,
# reg:logistic for classification problems with only decision,
# binary:logistic for classification problems with probability.

# XGBoost also supports regularization parameters to penalize models
# as they become more complex and reduce them to simple (parsimonious) models.
# gamma: controls whether a given node will split based on the expected reduction in loss after the split.
#        A higher value leads to fewer splits. Supported only for tree-based learners.
# alpha: L1 regularization on leaf weights. A large value leads to more regularization.
# lambda: L2 regularization on leaf weights and is smoother than L1 regularization.
#
# It's also worth mentioning that though you are using trees as your base learners,
# you can also use XGBoost's relatively less popular linear base learners and one other tree learner known as dart.
# All you have to do is set the booster parameter to either gbtree (default),gblinear or dart.

# ---- Cell ----
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=123)

# ---- Cell ----
xg_reg = xgb.XGBRegressor(objective ='reg:squarederror', colsample_bytree = 0.3, learning_rate = 0.1,
                max_depth = 5, alpha = 10, n_estimators = 10)

# ---- Cell ----
xg_reg.fit(X_train,y_train)

preds = xg_reg.predict(X_test)

# ---- Cell ----
rmse = np.sqrt(mean_squared_error(y_test, preds))
print("RMSE: %f" % (rmse))

# ---- Cell ----
# XGBoost를 사용한 k겹 교차 검증을 수해하라.

# ---- Cell ----
# XGBoost는 cv() 메소드를 사용하는 k겹 교차검증을 지원한다.
# 이 경우 단지 검증의 수인 nfolds 파라미터만 설정하면 된다.
# 그 외에 다른 파라미터들도 지원하는데 이는 다음과 같다.

# num_boost_round: 트리의 수를 지정한다. (n_estimators와 유사하다)
# metrics: CV를 하는 동안 관찰할 평가 척도를 지정한다.
# as_pandas: 결과를 판다스 데이터프레임으로 반환한다.
# early_stopping_rounds: 만약 홀드 아웃 척도(우리의 경우 'rmse')가 더 이상 개선되지 않을 때) 조기 종료한다.
# seed: 결과의 재현성을 위해서 고정한다.

# 이들을 지정하기 위해 딕셔너리를 사용할 것인데, 모든 하이퍼 파라미터와 그 값을 키-값 쌍으로 지정한다.
# n_estimators는 하이퍼 파라미터 딕셔너리에서 제외하는데 이는 대신 num_boost_round를 사용할 것이기 때문이다.

# 다음에서 이들 파라미터를 XGBoost의 cv() 메소드를 일으켜 3겹 교차검증을 구축하고 결과를 cv_results 데이터프레임에 저장한다.
# 이전에 작성한 Dmatrix 객체를 사용하는 것을 주의하라. (싸이킷런은 변환되지 않은 배열도 받아들이지만
# XGBoost의 다양한 옵션을 사용하기 위해서는 Dmatrx를 사용하는 것을 권장한다.)


# ---- Cell ----
params = {"objective":"reg:squarederror",'colsample_bytree': 0.3,'learning_rate': 0.1,
                'max_depth': 5, 'alpha': 10}

cv_results = xgb.cv(dtrain=data_dmatrix, params=params, nfold=3,
                    num_boost_round=50,early_stopping_rounds=10,metrics="rmse", as_pandas=True, seed=123)

# ---- Cell ----
cv_results.head()

# ---- Cell ----
print((cv_results["test-rmse-mean"]).tail(1))

# ---- Cell ----
# 부스팅 트리와 특성 중요도를 시각화한다.

# ---- Cell ----
# 전체 주책 데이터셋을 이용해 XGBosst가 만든 부스트모델로부터 개별 트리를 시각화할 수 있다.
# XGBoost는 이런 종류의 시각화를 용이하게 하는 plot_tree() 함수를 갖고 있다.
# 일단 XGBoost 학습 API를 사용해 모델을 학습시키면 이를 num_trees 인수를 사용해 그리기를 원하는
# 개수의 트리 수와 함께 plot_tree() 함수로 전달할 수 있다.

# ---- Cell ----
xg_reg = xgb.train(params=params, dtrain=data_dmatrix, num_boost_round=10)

# ---- Cell ----
import matplotlib.pyplot as plt

xgb.plot_tree(xg_reg, num_trees=0)
plt.rcParams['figure.figsize'] = [50, 10]
plt.show()

# ---- Cell ----
xgb.plot_importance(xg_reg)
plt.rcParams['figure.figsize'] = [5, 5]
plt.show()

# ---- Cell ----

