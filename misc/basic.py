# English filename: basic_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/의사결정트리기초.py
# Original filename: 의사결정트리기초.py

# ---- Cell ----
# ----------------------------------------
# 🎯 결정 트리 구현 및 복잡도 제어 실습
# ----------------------------------------

from sklearn.datasets import load_breast_cancer
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split

# 1️⃣ 데이터 불러오기 (유방암 데이터)
cancer = load_breast_cancer()

# 2️⃣ 학습 / 테스트 데이터 분리
X_train, X_test, y_train, y_test = train_test_split(
    cancer.data, cancer.target, stratify=cancer.target, random_state=42
)

# --------------------------------------------------
# 🌳 [1단계] 기본 결정트리 (제약 없음)
# --------------------------------------------------
tree = DecisionTreeClassifier(random_state=0)
tree.fit(X_train, y_train)

print("=== 기본 결정 트리 ===")
print("훈련 세트 정확도: {:.3f}".format(tree.score(X_train, y_train)))
print("테스트 세트 정확도: {:.3f}".format(tree.score(X_test, y_test)))

# --------------------------------------------------
# 🌳 [2단계] 트리 깊이 제한 (max_depth=4)
# --------------------------------------------------
tree_limit_4 = DecisionTreeClassifier(max_depth=4, random_state=0)
tree_limit_4.fit(X_train, y_train)

print("\n=== 트리 깊이 제한 (max_depth=4) ===")
print("훈련 세트 정확도: {:.3f}".format(tree_limit_4.score(X_train, y_train)))
print("테스트 세트 정확도: {:.3f}".format(tree_limit_4.score(X_test, y_test)))

# --------------------------------------------------
# 🌳 [3단계] 트리 깊이 제한 (max_depth=2)
# --------------------------------------------------
tree_limit_2 = DecisionTreeClassifier(max_depth=2, random_state=0)
tree_limit_2.fit(X_train, y_train)

print("\n=== 트리 깊이 제한 (max_depth=2) ===")
print("훈련 세트 정확도: {:.3f}".format(tree_limit_2.score(X_train, y_train)))
print("테스트 세트 정확도: {:.3f}".format(tree_limit_2.score(X_test, y_test)))

# ---- Cell ----
# ----------------------------------------
# 🎯 결정 트리 구현 및 복잡도 제어 실습
# ----------------------------------------

from sklearn.datasets import load_breast_cancer
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt
import numpy as np

# 1️⃣ 데이터 불러오기 (유방암 데이터)
cancer = load_breast_cancer()

# 2️⃣ 학습 / 테스트 데이터 분리
X_train, X_test, y_train, y_test = train_test_split(
    cancer.data, cancer.target, stratify=cancer.target, random_state=42
)

# --------------------------------------------------
# 🌳 [1단계] 기본 결정트리 (제약 없음)
# --------------------------------------------------
tree = DecisionTreeClassifier(random_state=0)
tree.fit(X_train, y_train)

# --------------------------------------------------
# 🌳 [2단계] 트리 깊이 제한 (max_depth=4)
# --------------------------------------------------
tree_limit = DecisionTreeClassifier(max_depth=4, random_state=0)
tree_limit.fit(X_train, y_train)


def plot_feature_importances_cancer(model):
    n_features = cancer.data.shape[1]
    plt.barh(range(n_features), model.feature_importances_, align='center')
    plt.yticks(np.arange(n_features), cancer.feature_names)
    plt.xlabel("Feature Importance")
    plt.ylabel("Feature")
    plt.ylim(-1, n_features)

print("\n=== Feature Importance (Basic Decision Tree) ===")
plot_feature_importances_cancer(tree)
plt.show()

print("\n=== Feature Importance (Tree Depth Limit: max_depth=4) ===")
plot_feature_importances_cancer(tree_limit)
plt.show()

# ---- Cell ----
from sklearn.ensemble import GradientBoostingClassifier

# 그래디언트 부스팅 모델 (기본 설정)
# max_depth와 learning_rate의 기본값을 사용합니다.
gb = GradientBoostingClassifier(random_state=0)
gb.fit(X_train, y_train)

print("=== 그래디언트 부스팅 (기본 설정) ===")
print("훈련 세트 정확도: {:.3f}".format(gb.score(X_train, y_train)))
print("테스트 세트 정확도: {:.3f}".format(gb.score(X_test, y_test)))

# 그래디언트 부스팅 모델 (트리 깊이 제한: max_depth=1)
# 트리의 깊이를 얕게 하여 모델의 복잡성을 줄입니다.
gb_limited_depth = GradientBoostingClassifier(max_depth=1, random_state=0)
gb_limited_depth.fit(X_train, y_train)

print("\n=== 그래디언트 부스팅 (트리 깊이 제한: max_depth=1) ===")
print("훈련 세트 정확도: {:.3f}".format(gb_limited_depth.score(X_train, y_train)))
print("테스트 세트 정확도: {:.3f}".format(gb_limited_depth.score(X_test, y_test)))

# 그래디언트 부스팅 모델 (학습률 제한: learning_rate=0.01)
# 학습률을 낮게 하여 모델이 천천히 학습하도록 합니다.
gb_limited_lr = GradientBoostingClassifier(learning_rate=0.01, random_state=0)
gb_limited_lr.fit(X_train, y_train)

print("\n=== 그래디언트 부스팅 (학습률 제한: learning_rate=0.01) ===")
print("훈련 세트 정확도: {:.3f}".format(gb_limited_lr.score(X_train, y_train)))
print("테스트 세트 정확도: {:.3f}".format(gb_limited_lr.score(X_test, y_test)))
