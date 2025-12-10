# English filename: py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/코스피 지수 예측-해답 (3).py
# Original filename: 코스피 지수 예측-해답 (3).py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/kospi/%E1%84%8F%E1%85%A9%E1%84%89%E1%85%B3%E1%84%91%E1%85%B5_%E1%84%8C%E1%85%B5%E1%84%89%E1%85%AE.csv

# ---- Cell ----
import pandas as pd
import numpy as np

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
kospi=pd.read_csv('코스피_지수.csv', encoding='cp949')

# ---- Cell ----
#kospi=pd.read_csv('코스피_지수.csv', engine='python')

# ---- Cell ----
kospi.shape

# ---- Cell ----
kospi.head()

# ---- Cell ----
X= kospi.drop(['코스피지수'], axis=1)

# ---- Cell ----
X.head()

# ---- Cell ----
y=kospi['코스피지수']

# ---- Cell ----
y.head()

# ---- Cell ----
y.tail()

# ---- Cell ----
from sklearn.model_selection import train_test_split

# ---- Cell ----
X_train, X_test = train_test_split(X,test_size=0.2,random_state=2025)
X_train.head()

# ---- Cell ----
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# ---- Cell ----
X_train.head()

# ---- Cell ----
columns = X_train.columns
columns

# ---- Cell ----
from sklearn.preprocessing import StandardScaler

# ---- Cell ----
std=StandardScaler()

# ---- Cell ----
X_train=std.fit_transform(X_train)
X_test=std.transform(X_test)  # 여기서느 fit하면 안됨.

# ---- Cell ----


# ---- Cell ----
# 1. 인스턴스화
from sklearn.linear_model import LinearRegression
lr = LinearRegression()

# ---- Cell ----
# 2. 적합화
lr.fit(X_train, y_train)

# ---- Cell ----
# 3. 예측
y_pred = lr.predict(X_test)

# ---- Cell ----
# 4. 평가
from sklearn.metrics import mean_squared_error as mse, r2_score as r2
import math

# ---- Cell ----
# RMSE와 R^2 구하라
print('RMSE: ', math.sqrt(mse(y_pred, y_test)))
print('R^2: ', r2(y_pred, y_test)*100)

# ---- Cell ----
np.mean(y_test)

# ---- Cell ----
107/1589.578125

# ---- Cell ----
# 2_1. 계수 프린트
c1=lr.coef_.reshape(1,-1)
c2=pd.DataFrame(c1, columns=columns)
c2

# ---- Cell ----
#1. 인스턴스화
from sklearn.linear_model import Ridge
ridge_model= Ridge(alpha=100)

# 2. 적합화
ridge_model.fit(X_train, y_train)

# 3. 예측
y_pred = ridge_model.predict(X_test)

# 4. 평가 RMSE와 R^2
from sklearn.metrics import mean_squared_error as mse, r2_score as r2
import math
print(math.sqrt(mse(y_pred, y_test))) # RMSE
print(r2(y_pred, y_test)*100) #R^2

# 2_1. 계수 프린트
c1=ridge_model.coef_.reshape(1,-1)
c2=pd.DataFrame(c1, columns=columns)
c2

# ---- Cell ----
c1.shape

# ---- Cell ----
#1. 인스턴스화
from sklearn.linear_model import Lasso
lasso_model= Lasso(alpha=100)
# 2. 적합화(학습)
lasso_model.fit(X_train, y_train)

# 3. 예측
y_pred = lasso_model.predict(X_test)

# 4. 평가 RMSE와 R^2
from sklearn.metrics import mean_squared_error as mse, r2_score as r2
import math
print(math.sqrt(mse(y_pred, y_test))) # RMSE
print(r2(y_pred, y_test)*100) #R^2

# 2_1. 계수 프린트
c1=lasso_model.coef_.reshape(1,-1)
c2=pd.DataFrame(c1, columns=columns)
c2.T

# ---- Cell ----
from sklearn.preprocessing import PolynomialFeatures

# ---- Cell ----
# 인스턴스화
poly= PolynomialFeatures(degree=2)

# ---- Cell ----
# X를 변환한다.
poly_X_train=poly.fit_transform(X_train)  # fit_transform => fit + transfomr 같이 사용한 것임.

# ---- Cell ----
poly_X_test=poly.transform(X_test)

# ---- Cell ----
poly_X_train.shape

# ---- Cell ----
poly_X_test.shape

# ---- Cell ----
lr=LinearRegression()
lr.fit(poly_X_train, y_train)
y_pred=lr.predict(poly_X_test)
print(math.sqrt(mse(y_pred, y_test)))
print(r2(y_pred, y_test))

# ---- Cell ----
#1. 인스턴스화
from sklearn.linear_model import Lasso
lasso_model= Lasso(alpha=100)

# 2. 적합화(학습)
lasso_model.fit(poly_X_train, y_train)

# 3. 예측
y_pred = lasso_model.predict(poly_X_test)

# 4. 평가 RMSE와 R^2
from sklearn.metrics import mean_squared_error as mse, r2_score as r2
import math
print(math.sqrt(mse(y_pred, y_test))) # RMSE
print(r2(y_pred, y_test)*100) #R^2

# 2_1. 계수 프린트
c1=lasso_model.coef_.reshape(1,-1)
c2=pd.DataFrame(c1)
c2

# ---- Cell ----
#1. 인스턴스화
from sklearn.linear_model import Ridge
ridge_model= Ridge(alpha=1)

# 2. 적합화(학습)
ridge_model.fit(poly_X_train, y_train)

# 3. 예측
y_pred = ridge_model.predict(poly_X_test)

# 4. 평가 RMSE와 R^2
from sklearn.metrics import mean_squared_error as mse, r2_score as r2
import math
print(math.sqrt(mse(y_pred, y_test))) # RMSE
print(r2(y_pred, y_test)*100) #R^2

# 2_1. 계수 프린트
c1=ridge_model.coef_.reshape(1,-1)
c2=pd.DataFrame(c1)
c2

# ---- Cell ----

