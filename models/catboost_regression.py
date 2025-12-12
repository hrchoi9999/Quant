# English filename: catboost_regression_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/CatBoost 튜톨리얼/catboost 튜토리얼_regression_clear.py
# Original filename: catboost 튜토리얼_regression_clear.py

# ---- Cell ----
!pip install catboost
!pip install shap

# ---- Cell ----
import catboost as cb
import numpy as np
import pandas as pd
import seaborn as sns
import shap

# ---- Cell ----
from matplotlib import pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from sklearn.metrics import r2_score
from sklearn.inspection import permutation_importance

# ---- Cell ----
data_url = "http://lib.stat.cmu.edu/datasets/boston"
raw_df = pd.read_csv(data_url, sep="\s+", skiprows=22, header=None)
boston_data = np.hstack([raw_df.values[::2, :], raw_df.values[1::2, :2]])
boston_target = raw_df.values[1::2, 2]

# Load Boston Housing Data
boston_data = pd.DataFrame(boston_data)
boston_target = pd.DataFrame(boston_target)

# ---- Cell ----
boston_data.shape

# ---- Cell ----
boston=pd.concat([boston_data, boston_target], axis=1)

# ---- Cell ----

# Define the column names
feature_names = ['CRIM', 'ZN', 'INDUS', 'CHAS', 'NOX', 'RM', 'AGE', 'DIS', 'RAD', 'TAX', 'PTRATIO', 'B', 'LSTAT', 'MEDV']

# Assuming boston is your DataFrame
boston.columns = feature_names

# Now you can display the DataFrame to see the column names applied
print(boston.head())


# ---- Cell ----
boston.head()

# ---- Cell ----
boston.isnull().sum()

# ---- Cell ----
# Splitting data into train and test sets
X_train, X_test, y_train, y_test = train_test_split(boston_data, boston_target, test_size=0.2, random_state=42)

# ---- Cell ----
train_dataset = cb.Pool(X_train, y_train)
test_dataset = cb.Pool(X_test, y_test)

# ---- Cell ----
model = cb.CatBoostRegressor(loss_function='RMSE')

# ---- Cell ----
grid = {'iterations': [100, 150, 200],
        'learning_rate': [0.03, 0.1],
        'depth': [2, 4, 6, 8],
        'l2_leaf_reg': [0.2, 0.5, 1, 3]}
model.grid_search(grid, train_dataset)

# ---- Cell ----
pred = model.predict(X_test)
rmse = (np.sqrt(mean_squared_error(y_test, pred)))
r2 = r2_score(y_test, pred)
print('Testing performance')
print('RMSE: {:.2f}'.format(rmse))
print('R2: {:.2f}'.format(r2))

# ---- Cell ----
sorted_feature_importance = model.feature_importances_.argsort()
plt.barh(boston.columns[sorted_feature_importance],
        model.feature_importances_[sorted_feature_importance],
        color='turquoise')
plt.xlabel("CatBoost Feature Importance")

# ---- Cell ----
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)
shap.summary_plot(shap_values, X_test, feature_names = boston.columns[sorted_feature_importance])

# ---- Cell ----

