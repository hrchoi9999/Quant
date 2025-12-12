# English filename: 04_statistical_inference_of_stock_returns_with_statsmodels_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/9일차 머신러닝 투자모델 검증을 위한 전략 백테스트 I/04_statistical_inference_of_stock_returns_with_statsmodels_wget_clear.py
# Original filename: 04_statistical_inference_of_stock_returns_with_statsmodels_wget_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/07_linear_models/data.zip&& unzip -n data.zip

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

import pandas as pd

from statsmodels.api import OLS, add_constant, graphics
from statsmodels.graphics.tsaplots import plot_acf
from scipy.stats import norm

import seaborn as sns
import matplotlib.pyplot as plt

# ---- Cell ----
sns.set_style('whitegrid')
idx = pd.IndexSlice

# ---- Cell ----
with pd.HDFStore('data.h5') as store:
    data = (store['model_data']
            .dropna()
            .drop(['open', 'close', 'low', 'high'], axis=1))

# ---- Cell ----
data = data[data.dollar_vol_rank<100]

# ---- Cell ----
data.info()

# ---- Cell ----
data.head()

# ---- Cell ----
y = data.filter(like='target')
X = data.drop(y.columns, axis=1)
X = X.drop(['dollar_vol', 'dollar_vol_rank', 'volume', 'consumer_durables'], axis=1)

# ---- Cell ----
sns.clustermap(y.corr(), cmap=sns.diverging_palette(h_neg=20, h_pos=220), center=0, annot=True, fmt='.2%');

# ---- Cell ----
sns.clustermap(X.corr(), cmap=sns.diverging_palette(h_neg=20, h_pos=220), center=0);
plt.gcf().set_size_inches((14, 14))

# ---- Cell ----
corr_mat = X.corr().stack().reset_index()
corr_mat.columns=['var1', 'var2', 'corr']
corr_mat = corr_mat[corr_mat.var1!=corr_mat.var2].sort_values(by='corr', ascending=False)

# ---- Cell ----
corr_mat.head(10)

# ---- Cell ----
y.boxplot();

# ---- Cell ----
X.columns

# ---- Cell ----
sectors = X.iloc[:, -10:]
X = (X.drop(sectors.columns, axis=1)
     .groupby(level='ticker')
     .transform(lambda x: (x - x.mean()) / x.std())
    .join(sectors)
    .fillna(0))

# ---- Cell ----
X = X.astype(float)

# ---- Cell ----
target = 'target_1d'
model = OLS(endog=y[target], exog=add_constant(X))
trained_model = model.fit()
print(trained_model.summary())

# ---- Cell ----
target = 'target_5d'
model = OLS(endog=y[target], exog=add_constant(X))
trained_model = model.fit()
print(trained_model.summary())

# ---- Cell ----
preds = trained_model.predict(add_constant(X))
residuals = y[target] - preds

# ---- Cell ----
fig, axes = plt.subplots(ncols=2, figsize=(14,4))
sns.distplot(residuals, fit=norm, ax=axes[0], axlabel='Residuals', label='Residuals')
axes[0].set_title('Residual Distribution')
axes[0].legend()
plot_acf(residuals, lags=10, zero=False, ax=axes[1], title='Residual Autocorrelation')
axes[1].set_xlabel('Lags')
sns.despine()
fig.tight_layout();

# ---- Cell ----
target = 'target_10d'
model = OLS(endog=y[target], exog=add_constant(X))
trained_model = model.fit()
print(trained_model.summary())

# ---- Cell ----
target = 'target_21d'
model = OLS(endog=y[target], exog=add_constant(X))
trained_model = model.fit()
print(trained_model.summary())

# ---- Cell ----

