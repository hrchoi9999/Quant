# English filename: causal_effects_regression_example_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-5. 인과관계/causal_effects_regression_example.py
# Original filename: causal_effects_regression_example.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/df_causal_effects.parquet

# ---- Cell ----
!pip install econml
!pip install dowhy

# ---- Cell ----
import pickle

import econml
import dowhy
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor

# ---- Cell ----
# df = pickle.load(open( "df_causal_effects.p", "rb" ) ).astype(int)
df = pd.read_parquet('df_causal_effects.parquet')

# ---- Cell ----
model = dowhy.CausalModel(
        data = df,
        treatment= "hasGraduateDegree",
        outcome= "greaterThan50k",
        common_causes="age",
        )

# ---- Cell ----
estimand = model.identify_effect(proceed_when_unidentifiable=True)

LR_estimate = model.estimate_effect(estimand, method_name="backdoor.linear_regression")

# ---- Cell ----
print(LR_estimate)

# ---- Cell ----
DML_estimate = model.estimate_effect(estimand,
                                     method_name="backdoor.econml.dml.DML",
                                     method_params={"init_params":{
                                         'model_y':LinearRegression(),
                                         'model_t':LinearRegression(),
                                         'model_final':LinearRegression()
                                                                  },
                                                   "fit_params":{}
                                              })

# ---- Cell ----
print(DML_estimate)

# ---- Cell ----
Xlearner_estimate = model.estimate_effect(estimand,
                                method_name="backdoor.econml.metalearners.XLearner",
                                method_params={"init_params":{
                                                    'models': DecisionTreeRegressor()
                                                    },
                                               "fit_params":{}
                                              })

# ---- Cell ----
print(Xlearner_estimate)

# ---- Cell ----

