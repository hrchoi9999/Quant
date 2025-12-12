# English filename: index_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/코스피지수_로짓-해답_wget.py
# Original filename: 코스피지수_로짓-해답_wget.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/kospi/%E1%84%8F%E1%85%A9%E1%84%89%E1%85%B3%E1%84%91%E1%85%B5_%E1%84%8C%E1%85%B5%E1%84%89%E1%85%AE.csv

# ---- Cell ----
import pandas as pd
import numpy as np

# ---- Cell ----
kospi =  pd.read_csv('코스피_지수.csv', encoding='cp949')

# ---- Cell ----
# kospi =  pd.read_csv('코스피_지수.csv', engine='python')

# ---- Cell ----
kospi.shape

# ---- Cell ----
X=kospi.drop(['코스피지수'], axis=1)
y=kospi['코스피지수']
X.shape

# ---- Cell ----
kospi.head()

# ---- Cell ----
kospi['다음달']=kospi['코스피지수'].shift(-1)
kospi=kospi[:-1]

# ---- Cell ----
kospi.head()

# ---- Cell ----
#kospi['future'] = np.where( kospi['코스피지수'] > kospi['다음달'], 0, 1)

# ---- Cell ----
#kospi.head()

# ---- Cell ----
# def classify(current, future):
#     if float(future) > float(current):
#         return 1
#     else:
#         return 0

# ---- Cell ----
def classify(current, future):
    if future > current:
        return 1
    else:
        return 0

# ---- Cell ----
# kospi['target'] = kospi.apply(lambda x: classify(x['코스피지수'], x['다음달']), axis=1)

# ---- Cell ----
# kospi['target'] = [classify(a, b) for a, b in zip(kospi['코스피지수'], kospi['다음달'])] # list comperehension

# ---- Cell ----
# target_list = []
# for a, b in zip(kospi['코스피지수'], kospi['다음달']):
#     target_list.append(classify(a, b))
# kospi['target'] = target_list

# ---- Cell ----
kospi['target'] = list(map(classify, kospi['코스피지수'], kospi['다음달']))

# ---- Cell ----
kospi.head()

# ---- Cell ----
kospi.drop(['코스피지수','다음달'], axis=1, inplace=True)
kospi.head()

# ---- Cell ----
X=kospi.drop(['target'], axis=1)
y=kospi['target']
X.shape

# ---- Cell ----
X.head()

# ---- Cell ----
from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test =train_test_split(X, y, test_size=0.2,  random_state=42)

# ---- Cell ----
from sklearn.linear_model import LogisticRegression
lr = LogisticRegression()
lr.fit(X_train, y_train)
y_pred= lr.predict(X_test)
from sklearn.metrics import accuracy_score
accuracy_score(y_pred, y_test)

# ---- Cell ----
from sklearn.linear_model import LogisticRegression
lr = LogisticRegression(solver='saga', penalty='l1', C=10)

# ---- Cell ----
lr.fit(X_train, y_train)

# ---- Cell ----
y_pred= lr.predict(X_test)

# ---- Cell ----
from sklearn.metrics import accuracy_score

# ---- Cell ----
accuracy_score(y_pred, y_test)

# ---- Cell ----
from sklearn.linear_model import LogisticRegression
lr = LogisticRegression()
lr.fit(X_train, y_train)
y_pred= lr.predict(X_test)
from sklearn.metrics import accuracy_score
accuracy_score(y_pred, y_test)

# ---- Cell ----


# ---- Cell ----
from sklearn.ensemble import RandomForestClassifier

# Train a Random Forest model
rf = RandomForestClassifier(random_state=42)
rf.fit(X_train, y_train)

# Predict probabilities for Random Forest
y_prob_rf = rf.predict_proba(X_test)[:, 1]

# Calculate ROC AUC for Random Forest
roc_auc_rf = roc_auc_score(y_test, y_prob_rf)
fpr_rf, tpr_rf, thresholds_rf = roc_curve(y_test, y_prob_rf)

# Predict probabilities for Logistic Regression (from previous model)
y_prob_lr = lr.predict_proba(X_test)[:, 1]

# Calculate ROC AUC for Logistic Regression
roc_auc_lr = roc_auc_score(y_test, y_prob_lr)
fpr_lr, tpr_lr, thresholds_lr = roc_curve(y_test, y_prob_lr)

# Plot ROC curves
plt.figure(figsize=(8, 6))
plt.plot(fpr_lr, tpr_lr, label=f'Logistic Regression (AUC = {roc_auc_lr:.2f})')
plt.plot(fpr_rf, tpr_rf, label=f'Random Forest (AUC = {roc_auc_rf:.2f})')
plt.plot([0, 1], [0, 1], 'k--', label='Random Guess')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Curve Comparison')
plt.legend()
plt.show()

print(f"Logistic Regression ROC AUC Score: {roc_auc_lr:.2f}")
print(f"Random Forest ROC AUC Score: {roc_auc_rf:.2f}")
