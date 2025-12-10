# English filename: 2_xgboost를_customer_churn_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/부스팅과 해석성/2. XGBoost를 실무에 이용해보자_customer_churn_clear.py
# Original filename: 2. XGBoost를 실무에 이용해보자_customer_churn_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/customer_churn.csv

# ---- Cell ----
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import warnings
import datetime
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.dates as mdates
import seaborn as sns
warnings.filterwarnings("ignore")

# ---- Cell ----
#churn_df = pd.read_csv('http://amunategui.github.io/customer_churn.csv')
churn_df = pd.read_csv('customer_churn.csv')
churn_df.head()

# ---- Cell ----
# Binarize area codes
churn_df['Area Code'] = churn_df['Area Code'].apply(str)
pd.get_dummies(churn_df['Area Code']).head()

# ---- Cell ----
churn_df['State'].value_counts()[0:10]

# ---- Cell ----
# fix the outcome
churn_df['Churn?'] = np.where(churn_df['Churn?'] == 'True.', 1, 0)
churn_df["Int'l Plan"] = np.where(churn_df["Int'l Plan"] == 'yes', 1, 0)
churn_df['VMail Plan'] = np.where(churn_df['VMail Plan'] == 'yes', 1, 0)


# ---- Cell ----
# dummify states
pd.get_dummies(churn_df['State']).head()

# ---- Cell ----
# binarize categorical columns
churn_df = pd.concat([churn_df, pd.get_dummies(churn_df['State'])], axis=1)
churn_df = pd.concat([churn_df, pd.get_dummies(churn_df['Area Code'])], axis=1)

churn_df.head()

# ---- Cell ----
# # check for nulls in data and impute if necessary
# for feat in list(churn_df):
#     if (len(churn_df[feat]) - churn_df[feat].count()) > 0:
#         print(feat)
#         print(len(churn_df[feat]) - churn_df[feat].count())
#         # tmp_df.loc[tmp_df[feat].isnull(), feat] = 0

# ---- Cell ----
churn_df.head()

# ---- Cell ----
list(churn_df)

# ---- Cell ----
features = [feat for feat in list(churn_df) if feat not in ['State', 'Churn?', 'Phone', 'Area Code']]

# ---- Cell ----
outcome = 'Churn?'

# ---- Cell ----
# 모델링 준비 작업
from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(churn_df,
                                                 churn_df[outcome],
                                                 test_size=0.3,
                                                 random_state=42)

import xgboost  as xgb
xgb_params = {
    'max_depth':3,
    'eta':0.05,
    'silent':0,
    'eval_metric':'auc',
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'objective':'binary:logistic',
    'seed' : 0
}

dtrain = xgb.DMatrix(X_train[features], y_train, feature_names = features)
dtest = xgb.DMatrix(X_test[features], y_test, feature_names = features)
evals = [(dtrain,'train'),(dtest,'eval')]
xgb_model = xgb.train (params = xgb_params,
              dtrain = dtrain,
              num_boost_round = 2000,
              verbose_eval=50,
              early_stopping_rounds = 500,
              evals=evals,
              #feval = f1_score_cust,
              maximize = True)

# plot the important features
fig, ax = plt.subplots(figsize=(6,9))
xgb.plot_importance(xgb_model,  height=0.8, ax=ax)
plt.show()

# ---- Cell ----
# 특성 중요도의 데이터 프레임 버전 작성
xgb_fea_imp=pd.DataFrame(list(xgb_model.get_fscore().items()),
columns=['feature','importance']).sort_values('importance', ascending=False)
xgb_fea_imp.head(10)

# ---- Cell ----
churn_df['Day Mins'].quantile(0.25)

# ---- Cell ----
churn_df['Day Mins'].quantile(0.75)

# ---- Cell ----
pred_churn = xgb_model.predict(dtest)
plt.plot(sorted(pred_churn))
plt.grid()

# ---- Cell ----
# 모든 수치 특성을 얻는다.
numerics = ['int16', 'int32', 'int64', 'float16', 'float32', 'float64']
numeric_features = list(X_test.head().select_dtypes(include=numerics))
features_to_ignore = ['Account Length', 'Area Code','Churn?', 'Will_Churn']
numeric_features = [nf for nf in numeric_features if nf not in features_to_ignore]

row_counter = 0
X_test['Will_Churn'] = pred_churn
new_df = []
for index, row in X_test.iterrows():
    if row['Will_Churn'] > 0.8:   # 이탈할 가능성이 높은 고객들
        row_counter += 1
        new_df.append(row[list(churn_df)])
        for feat in numeric_features:
            # 단지 높은 이탈확률 고객들만 고려한다.
            if row[feat] < X_test[feat].quantile(0.25):
                print('(ID:', row_counter, ')', feat,  ' is < than 25 percentile')
            if row[feat] > X_test[feat].quantile(0.75):
                print('(ID:', row_counter, ')', feat,  ' is > than 75 percentile')


new_df[0]

# ---- Cell ----
# 이탈하지 않은 사람들의 데이터를 만든다.
not_churn = X_train[X_train['Churn?']==False].copy()

find_closet_df = []

# 인사이트를 발견하기 위해 새로운 행을 더한다.
find_closet_df.append(new_df[0])

for index, row in not_churn.iterrows():
    find_closet_df.append(row[list(churn_df)])

find_closet_df = pd.DataFrame(find_closet_df)
find_closet_df['ID'] = [idx for idx in range(1,len(find_closet_df)+1)]
find_closet_df.head()

# ---- Cell ----
from sklearn.cluster import KMeans
num_clusters = 20
kmeans = KMeans(n_clusters=num_clusters, random_state=0).fit(find_closet_df[features])
labels = kmeans.labels_
find_closet_df['clusters'] = labels
find_closet_df.head()

# ---- Cell ----
find_closet_df[find_closet_df['clusters']==14][features]

# ---- Cell ----
find_closet_df.head()

# ---- Cell ----
mydat = find_closet_df.copy()
mydat[mydat['clusters']==14].head()

# ---- Cell ----
def risk_compare(cluster_df, cluster_number, var1, var2):
    mydat = find_closet_df.copy()
    mydat = mydat[mydat['clusters'] == cluster_number]
    mydat = mydat[[var1, var2, 'clusters']]
    # differentiate high-risk churn customer
    mydat.iat[0, 2] = 0

    sns.scatterplot(x=var1, y=var2, data=mydat,
               hue="clusters",
               legend=False,
               #marker="D",
               s=100)

    plt.xlabel(var1)
    plt.ylabel(var2)
    plt.show()

# ---- Cell ----
risk_compare(find_closet_df.copy(), 14, 'Night Mins', 'Night Calls')


# ---- Cell ----
risk_compare(find_closet_df.copy(), 14, 'Day Mins', 'Eve Mins')


# ---- Cell ----

