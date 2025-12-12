# English filename: kc_house_data_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/kc_house_data_clear.py
# Original filename: kc_house_data_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/kc_house_data.csv

# ---- Cell ----
!pip install shap

# ---- Cell ----
# library import
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# ---- Cell ----
# 현재경로 확인
# os.getcwd()

# 데이터 불러오기
data = pd.read_csv("./kc_house_data.csv")
data.head() # 데이터 확인

# ---- Cell ----
# shape 파악
nCar = data.shape[0] # 데이터 개수
nVar = data.shape[1] # 변수 개수
print('nCar: %d' % nCar, 'nVar: %d' % nVar )

# ---- Cell ----
# 의미가 없다고 생각되는 변수 제거
data = data.drop(['id', 'date', 'zipcode', 'lat', 'long'], axis = 1) # id, date, zipcode, lat, long  제거

# ---- Cell ----
feature_columns = list(data.columns.difference(['price'])) # price-target, 그 외 feature
X = data[feature_columns]
y = data['price']
train_x, test_x, train_y, test_y = train_test_split(X, y, test_size = 0.3, random_state = 1999)
# train/test 비율을 7:3
print(train_x.shape, test_x.shape, train_y.shape, test_y.shape) # 데이터 확인

# ---- Cell ----
# lightgbm을 구현하여 shap value를 예측할 것
# ligthgbm 구현

# library
import lightgbm as lgb  # 없을 경우 cmd/anaconda prompt에서 install
from math import sqrt
from sklearn.metrics import mean_squared_error

# lightgbm model
lgb_dtrain = lgb.Dataset(data = train_x, label = train_y) # LightGBM 모델에 맞게 변환
lgb_param = {'max_depth': 10,
            'learning_rate': 0.01, # Step Size
            'n_estimators': 1000, # Number of trees
            'objective': 'regression'} # 목적 함수 (L2 Loss)
lgb_model = lgb.train(params = lgb_param, train_set = lgb_dtrain) # 학습 진행
lgb_model_predict = lgb_model.predict(test_x) # test data 예측
print("RMSE: {}".format(sqrt(mean_squared_error(lgb_model_predict, test_y)))) # RMSE

# ---- Cell ----
# shap value를 이용하여 각 변수의 영향도 파악

# !pip install shap (에러 발생시, skimage version 확인 (0.14.2 이상 권장))
# import skimage -> skimage.__version__ (skimage version 확인)
# skimage version upgrade -> !pip install --upgrade scikit-image

# shap value
import shap
explainer = shap.TreeExplainer(lgb_model) # Tree model Shap Value 확인 객체 지정
shap_values = explainer.shap_values(test_x) # Shap Values 계산

# ---- Cell ----
# version 확인
import skimage
skimage.__version__

# ---- Cell ----
shap.initjs() # javascript 초기화 (graph 초기화)
shap.force_plot(explainer.expected_value, shap_values[100,:], test_x.iloc[100,:])

# ---- Cell ----
# 전체 검증 데이터 셋에 대해서 적용
shap.initjs()
shap.force_plot(explainer.expected_value, shap_values[:100,:], test_x.iloc[:100,:])

# ---- Cell ----
# summary
shap.summary_plot(shap_values, test_x)

# ---- Cell ----
 # 각 변수에 대한 |Shap Values|을 통해 변수 importance 파악
shap.summary_plot(shap_values, test_x, plot_type = "bar")

# ---- Cell ----
 # 변수 간의 shap value 파악
shap.dependence_plot("yr_built", shap_values, test_x)
