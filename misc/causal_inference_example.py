# English filename: causal_inference_example_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-5. 인과관계/causal_inference_example.py
# Original filename: causal_inference_example.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/df_causal_inference.parquet

# ---- Cell ----
!pip install econml
!pip install dowhy

# ---- Cell ----
import pickle
import matplotlib.pyplot as plt
import pandas as pd
import econml
import dowhy
from dowhy import CausalModel

# ---- Cell ----
# df = pickle.load(open( "df_causal_inference.p", "rb" ) )
df = pd.read_parquet("df_causal_inference.parquet")

# ---- Cell ----
model=CausalModel(
        data = df,
        treatment= "hasGraduateDegree",
        outcome= "greaterThan50k",
        common_causes="age",
        )

# ---- Cell ----
# View model
model.view_model()
from IPython.display import Image, display
display(Image(filename="causal_model.png"))

# ---- Cell ----
identified_estimand= model.identify_effect(proceed_when_unidentifiable=True)
print(identified_estimand)

# ---- Cell ----
identified_estimand_experiment = model.identify_effect(proceed_when_unidentifiable=True)

from sklearn.ensemble import RandomForestRegressor
metalearner_estimate = model.estimate_effect(identified_estimand_experiment,
                                method_name="backdoor.econml.metalearners.TLearner",
                                confidence_intervals=False,
                                method_params={"init_params":{
                                                    'models': RandomForestRegressor()
                                                    },
                                               "fit_params":{}
                                              })
print(metalearner_estimate)

# ---- Cell ----
# print histogram of causal effects for each sample
plt.hist(metalearner_estimate.cate_estimates)

# ---- Cell ----

