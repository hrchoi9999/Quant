# English filename: xgboost_practice_예제1_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/Xgboost 튜토리얼/xgboost 실습 예제1_clear.py
# Original filename: xgboost 실습 예제1_clear.py

# ---- Cell ----
# conda install graphviz phthon-graphviz

# ---- Cell ----
!pip install scikit-learn==1.1.3
!wget -nc http://youngminhome.iptime.org:5555/shared/xgboost_tutorial/WA_Fn-UseC_-Telco-Customer-Churn.csv

# ---- Cell ----
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import balanced_accuracy_score, roc_auc_score, make_scorer
from sklearn.metrics import confusion_matrix
from sklearn.metrics import plot_confusion_matrix

# ---- Cell ----
df=pd.read_csv('WA_Fn-UseC_-Telco-Customer-Churn.csv')

# ---- Cell ----
df.head()

# ---- Cell ----
df['gender'].unique()

# ---- Cell ----
df['SeniorCitizen'].unique()

# ---- Cell ----
df.columns

# ---- Cell ----
df.info()

# ---- Cell ----
df.dtypes

# ---- Cell ----


# ---- Cell ----
df['PhoneService'].unique()

# ---- Cell ----
df['TotalCharges'].unique()

# ---- Cell ----
#df['TotalCharges']=pd.to_numeric(df['TotalCharges'])

# ---- Cell ----
len(df.loc[df['TotalCharges']==' '])

# ---- Cell ----
df.loc[df['TotalCharges']==' ']  # Just signed up

# ---- Cell ----
df.loc[(df['TotalCharges']==' '), 'TotalCharges']=0

# ---- Cell ----
df.loc[df['TotalCharges']==0]

# ---- Cell ----
# xgboost 단지 int, float와 boolean만 받아들인다.

# ---- Cell ----
df['TotalCharges']=pd.to_numeric(df['TotalCharges'])
df.dtypes

# ---- Cell ----
df['PaymentMethod']

# ---- Cell ----
df.replace(' ', '_', regex=True, inplace=True)  # 예쁘게 트리 그리기 위해

# ---- Cell ----
df['PaymentMethod']

# ---- Cell ----
df.head()

# ---- Cell ----
X=df.drop('Churn', axis=1).copy()

# ---- Cell ----
y=df['Churn']

# ---- Cell ----
y.unique()

# ---- Cell ----
X.dtypes

# ---- Cell ----
df['PaymentMethod'].unique()

# ---- Cell ----
# ColumnTranformer()
# get_dummies()

# ---- Cell ----
pd.get_dummies(X, columns=['PaymentMethod']).head()  #원핫인코딩

# ---- Cell ----
df_with_cat=df.select_dtypes(include='object')  #데이터 타이프가 object인 변수들을 추출한다.
df_with_cat.columns  #그 변수들의 열이름 추출한다.

# ---- Cell ----
del X['customerID']

# ---- Cell ----
X.head()

# ---- Cell ----
X_with_cat=X.select_dtypes(include='object')
X_cat_cols = X_with_cat.columns

# ---- Cell ----
X_cat_cols

# ---- Cell ----
X_encoded = pd.get_dummies(X, columns=X_cat_cols)

# ---- Cell ----
X_encoded.head()

# ---- Cell ----
y.unique()

# ---- Cell ----
#방법1
# y1 = y.replace("No", 0).replace("Yes", 1)

# ---- Cell ----
#sum(y1)

# ---- Cell ----
y=np.where(y=='No', 0, 1)

# ---- Cell ----
y

# ---- Cell ----
sum(y)/len(y)  # 전체 샘플 중 27%정도가 탈퇴고객이다.

# ---- Cell ----
X_train, X_test, y_train, y_test =train_test_split(X_encoded, y, random_state=42, stratify=y)

# ---- Cell ----
# stratfy가 잘 작동하는지

# ---- Cell ----
sum(y_train)/len(y_train)

# ---- Cell ----
sum(y_test)/len(y_test)

# ---- Cell ----
clf_xgb=xgb.XGBClassifier(
    objective='binary:logistic',
    eval_metric='aucpr',  # area under curve precision-recall curve 아래 면적
    missing=1,
    seed=42
)

# ---- Cell ----
clf_xgb.fit(X_train,
           y_train,
           verbose=True,
           eval_set=[(X_test, y_test)])

# ---- Cell ----
plot_confusion_matrix(clf_xgb,
                     X_test,
                     y_test,
                     values_format='d',
                     display_labels=['Did not leave', 'left'])

# ---- Cell ----
# scale_pos_weight

# ---- Cell ----
# 불균형시는 AUC를 성과척도로
# scale_pos_weight로 균형을 잡아라.

# ---- Cell ----
# max_depth  # 나무 깊이
# learning rate(eta)  #학습률
# gamma: pruning 컨트롤  # 미니멈 불순도 감소
# reg_lambda: 규제화 파라미터 람다
#

# ---- Cell ----
## 1 라운드
param_grid={
    'max_depth': [3,4,5],  # 8~32 표준
    'learning_rate': [0.1, 0.01, 0.05],
    'gamma': [0, 0.25, 1.0],
    'reg_lambda':[0, 1.0, 10.0],
    'scale_pos_weight': [1, 3, 5] # sum(neg)/sum(pos)
}

# ---- Cell ----
# 출력: [4, 0.1, 0.25, 10, 3]

# ---- Cell ----
## 2 라운드
param_grid={
    'max_depth': [4],
    'learning_rate': [0.1, 0.5, 1.0],
    'gamma': [0.25],
    'reg_lambda':[10.0, 20, 100],
    'scale_pos_weight': [3] # sum(neg)/sum(pos)
}

# ---- Cell ----
[4, 0.1, 10]

# ---- Cell ----
from sklearn.model_selection import GridSearchCV

# ---- Cell ----
optimal_params = GridSearchCV(
    estimator=xgb.XGBClassifier(objective='binary:logistic',
                                seed=42,
                                subsample=0.9,
                                colsample_bytree=0.5,
                                eval_metric='auc',
                                ),
    param_grid=param_grid,
    scoring='roc_auc',
    verbose=2,
    n_jobs=-1,
    cv=3
)

# ---- Cell ----
optimal_params.fit(X_train,
                  y_train,
                  eval_set=[(X_test, y_test)],
                  verbose=False)
print(optimal_params.best_params_)

# ---- Cell ----
#0.25, 4, 0.1, 10, 3

# ---- Cell ----
clf_xgb=xgb.XGBClassifier(seed=42,
                          objective='binary:logistic',
                          gamma=0.25,
                          learn_rate=0.1,
                          max_depth=4,
                          reg_lambda=100,
                          scale_pos_weight=3,
                          subsample=0.9,
                          colsample_bytree=0.5,
                          eval_metric='aucpr',
                          )

# ---- Cell ----
clf_xgb.fit(X_train,
           y_train,
           verbose=True,
           eval_set=[(X_test, y_test)])

# ---- Cell ----
plot_confusion_matrix(clf_xgb,
                     X_test,
                     y_test,
                     values_format='d',
                     display_labels=['Did not leave', 'left'])

# ---- Cell ----
clf_xgb=xgb.XGBClassifier(seed=42,
                          objective='binary:logistic',
                          gamma=0.25,
                          learn_rate=0.1,
                          max_depth=4,
                          reg_lambda=10,
                          scale_pos_weight=3,
                          subsample=0.9,
                          colsample_bytree=0.5,
                         n_estimators=1)  #그림 하나 그리기 위해서
clf_xgb.fit(X_train, y_train)

# ---- Cell ----
# weight = number of times a feature is used in a branch or root across the trees
# gain = average gain across the all splits that feature is used in
# cover = average coverage across all splits a feature is used in
# total_gain =total gain across all splits the feature is used in
# total_cover = total coverage all splits the feature is used in
## 한 트리만 구축했으므로 gain=total_gain이고, cover=total_cover이다.

# ---- Cell ----
bst=clf_xgb.get_booster()

# ---- Cell ----
for importance_type in ('weight', 'gain', 'cover', 'total_gain', 'total_cover'):
    print('%s: ' % importance_type, bst.get_score(importance_type=importance_type))

# ---- Cell ----
node_params ={'shape': 'box',
             'style': 'filled, rounded',
             'fillcolor': '#78cbe'}
leaf_params={'shape': 'box',
             'style': 'filled',
             'fillcolor': '#e48038'}
# xgb.to_graphviz(clf_xgb, num_trees=0, size="10, 10")
xgb.to_graphviz(clf_xgb, num_trees=0, size="10, 10",
               condition_node_params=node_params,
               leaf_node_params=leaf_params)

# ---- Cell ----
# 저장하고 싶으면
graph_data=xgb.to_graphviz(clf_xgb, num_trees=0, size="10, 10",
               condition_node_params=node_params,
               leaf_node_params=leaf_params)
graph_data.view(filename='xgboost_tree_customer_churn')  #pdf로 저장

# ---- Cell ----
# 리프값을 확률로 바꾸자 -> 1/(1+np.exp(-1*0.167528))=0.5417843204057448

# ---- Cell ----

