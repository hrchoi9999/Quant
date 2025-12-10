# English filename: 07_logistic_regression_macro_data_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/10일차 머신러닝 투자모델 검증을 위한 전략 백테스트 II/07_logistic_regression_macro_data_wget_clear.py
# Original filename: 07_logistic_regression_macro_data_wget_clear.py

# ---- Cell ----
%matplotlib inline
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
import seaborn as sns

# ---- Cell ----
sns.set_style('whitegrid')

# ---- Cell ----
data = pd.DataFrame(sm.datasets.macrodata.load().data)
data.info()

# ---- Cell ----
data.head()

# ---- Cell ----
data['growth_rate'] = data.realgdp.pct_change(4)
data['target'] = (data.growth_rate > data.growth_rate.rolling(20).mean()).astype(int).shift(-1)
data.quarter = data.quarter.astype(int)

# ---- Cell ----
data.target.value_counts()

# ---- Cell ----
data.tail()

# ---- Cell ----
pct_cols = ['realcons', 'realinv', 'realgovt', 'realdpi', 'm1']
drop_cols = ['year', 'realgdp', 'pop', 'cpi', 'growth_rate']
data.loc[:, pct_cols] = data.loc[:, pct_cols].pct_change(4)

# ---- Cell ----
data = pd.get_dummies(data.drop(drop_cols, axis=1), columns=['quarter'], drop_first=True).dropna()

# ---- Cell ----
data.head()

# ---- Cell ----
data.info()

# ---- Cell ----
model = sm.Logit(data.target, sm.add_constant(data.drop('target', axis=1).astype(float)))
result = model.fit()
result.summary()

# ---- Cell ----
plt.rc('figure', figsize=(12, 7))
plt.text(0.01, 0.05, str(result.summary()), {'fontsize': 14}, fontproperties = 'monospace')
plt.axis('off')
plt.tight_layout()
plt.subplots_adjust(left=0.2, right=0.8, top=0.8, bottom=0.1)
plt.savefig('logistic_example.png', bbox_inches='tight', dpi=300);

# ---- Cell ----

