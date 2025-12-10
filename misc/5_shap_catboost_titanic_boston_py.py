# English filename: 5_shap_catboost_titanic_boston_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/부스팅과 해석성/5. SHAP_Catboost_Titanic_Boston_clear.py
# Original filename: 5. SHAP_Catboost_Titanic_Boston_clear.py

# ---- Cell ----
!!pip install scikit-learn==1.0.2

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/titanic3.csv

# ---- Cell ----
!pip install shap
!pip install catboost

# ---- Cell ----
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns
from sklearn.model_selection import train_test_split

import catboost
print('catboost version:', catboost.__version__)
from catboost import CatBoostClassifier

# ---- Cell ----
# Catboost classifier를 사용해 타이타닉 데이터셋에 적용해보자.

# ---- Cell ----
titanic_df = pd.read_csv(
    'titanic3.csv')
titanic_df.head()

# ---- Cell ----
# 캐빈번호에서 첫번째 문자가 있는 경우 이를 빼낸다.
titanic_df['cabin'] = titanic_df['cabin'].replace(np.NaN, 'U')
titanic_df['cabin'] = [ln[0] for ln in titanic_df['cabin'].values]
titanic_df['cabin'] = titanic_df['cabin'].replace('U', 'Unknown')

# isfemale 필드를 작성하고, 수치값으로 변환한다.
titanic_df['isfemale'] = np.where(titanic_df['sex'] == 'female', 1, 0)

# 모델에 필요없는 특성을 제거한다.
titanic_df = titanic_df[[f for f in list(titanic_df) if f not in ['sex', 'name', 'boat','body', 'ticket', 'home.dest']]]

# pclass를 명목변수 범주형 열로 만든다.
titanic_df['pclass'] = np.where(titanic_df['pclass'] == 1, 'First',
                                np.where(titanic_df['pclass'] == 2, 'Second', 'Third'))


titanic_df['embarked'] = titanic_df['embarked'].replace(np.NaN, 'Unknown')

# 나이 결측치를 평균으로 대체한다.
titanic_df['age'] = titanic_df['age'].fillna(titanic_df['age'].mean())
titanic_df['age']

titanic_df.head()

# ---- Cell ----
# 범주형 특성을 매핑한다.
titanic_catboost_ready_df = titanic_df.dropna()

features = [feat for feat in list(titanic_catboost_ready_df)
            if feat != 'survived']
print(features)
categorical_features = np.where(titanic_catboost_ready_df[features].dtypes != np.float64)[0]


X_train, X_test, y_train, y_test = train_test_split(titanic_df[features],
                                                    titanic_df[['survived']],
                                                    test_size=0.3,
                                                     random_state=1)

params = {'iterations':5000,
        'learning_rate':0.01,
        'cat_features':categorical_features,
        'depth':3,
        'eval_metric':'AUC',
        'verbose':200,
        'od_type':"Iter", # overfit detector
        'od_wait':500, # most recent best iteration to wait before stopping
        'random_seed': 1
          }

cat_model = CatBoostClassifier(**params)
cat_model.fit(X_train, y_train,
          eval_set=(X_test, y_test),
          use_best_model=True, # True if we don't want to save trees created after iteration with the best validation score
          plot=True
         );


# ---- Cell ----
import shap  # 샤플리 값(SHAP value)을 계산하기 위한 패키지
# SHAP(SHapley Additive exPlanations): 샤플리 가산성 설명
# SHAP의 목적은 샘플 x에 대한 예측을 각 특성의 예측 기여도로를 계산해서 설명하고자 하는 것이다.
# SHAP 설명방법은 협동 게입이론의 샤플리값을 계산한다.
# 즉 데이터 샘플의 특성값이 협력 게임의 플레이어이며, 샤플리값은 각 특성 간에 이익(예측)을 공정하게 분배하는 법을 알려준다.

from catboost import CatBoostClassifier, Pool
shap_values = cat_model.get_feature_importance(Pool(X_test, label=y_test,cat_features=categorical_features),type="ShapValues")

expected_value = shap_values[0,-1]
shap_values = shap_values[:,:-1]

shap.initjs()
shap.force_plot(expected_value, shap_values[0,:], X_test.iloc[0,:])

# ---- Cell ----
shap.summary_plot(shap_values, X_test)

# ---- Cell ----
# catboost regressor를 사용해 보스톤 주택가격에 대해서 적용해보자.

# ---- Cell ----
from sklearn.datasets import load_boston
boston_dataset = load_boston()
print(boston_dataset.keys())

for ln in boston_dataset.DESCR.split('\n'):
    print(ln)

# ---- Cell ----
boston = pd.DataFrame(boston_dataset.data, columns=boston_dataset.feature_names)
boston.head(10)


# ---- Cell ----
# 우리의 타겟변수는 자가소유주택의 중위가격(천달러단위)이다.
boston['MEDV'] = boston_dataset.target
boston.head()

# ---- Cell ----
boston.info()

# ---- Cell ----
from catboost import CatBoostRegressor

# 데이터 분할
outome_name = 'MEDV'
features_for_model = [f for f in list(boston) if f not in [outome_name, 'TAX']]

# 범주를 얻고 문자열로 정의
boston_categories = np.where([boston[f].apply(float.is_integer).all() for f in features_for_model])[0]
print('boston_categories:', boston_categories)

# 값을 문자열로 변환
for feature in [list(boston[features_for_model])[f] for f in list(boston_categories)]:
    print(feature)
    boston[feature] = boston[feature].to_string()


# 데이터 분할
from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(boston[features_for_model],
                                                 boston[outome_name],
                                                 test_size=0.3,
                                                 random_state=1)




params = {'iterations':5000,
        'learning_rate':0.001,
        'depth':3,
        'loss_function':'RMSE',
        'eval_metric':'RMSE',
        'random_seed':55,
        'cat_features':boston_categories,
        'metric_period':200,
        'od_type':"Iter",
        'od_wait':20,
        'verbose':True,
        'use_best_model':True}


model_regressor = CatBoostRegressor(**params)

model_regressor.fit(X_train, y_train,
          eval_set=(X_test, y_test),
          use_best_model=True,
          plot= True
         );

# ---- Cell ----
shap_values = model_regressor.get_feature_importance(Pool(X_test, label=y_test, cat_features=boston_categories) , type="ShapValues")

expected_value = shap_values[0,-1]
shap_values = shap_values[:,:-1]

shap.initjs()
shap.force_plot(expected_value, shap_values[0,:], X_test.iloc[0,:])

# ---- Cell ----
shap.summary_plot(shap_values, X_test)

# ---- Cell ----
boston['MEDV'].describe()

# ---- Cell ----

