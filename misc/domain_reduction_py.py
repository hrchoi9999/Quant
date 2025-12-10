# English filename: domain_reduction_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/BayesianOptimization/domain_reduction_clear.py
# Original filename: domain_reduction_clear.py

# ---- Cell ----
!pip install bayesian-optimization

# ---- Cell ----
import numpy as np
from bayes_opt import BayesianOptimization
from bayes_opt import SequentialDomainReductionTransformer
import matplotlib.pyplot as plt

# ---- Cell ----
def ackley(**kwargs):
    x = np.fromiter(kwargs.values(), dtype=float)
    arg1 = -0.2 * np.sqrt(0.5 * (x[0] ** 2 + x[1] ** 2))
    arg2 = 0.5 * (np.cos(2. * np.pi * x[0]) + np.cos(2. * np.pi * x[1]))
    return -1.0 * (-20. * np.exp(arg1) - np.exp(arg2) + 20. + np.e)

# ---- Cell ----

pbounds = {'x': (-5, 5), 'y': (-5, 5)}

# ---- Cell ----
bounds_transformer = SequentialDomainReductionTransformer(minimum_window=0.5)

# ---- Cell ----
mutating_optimizer = BayesianOptimization(
    f=ackley,
    pbounds=pbounds,
    verbose=0,
    random_state=1,
    bounds_transformer=bounds_transformer
)

# ---- Cell ----
mutating_optimizer.maximize(
    init_points=2,
    n_iter=50,
)

# ---- Cell ----
standard_optimizer = BayesianOptimization(
    f=ackley,
    pbounds=pbounds,
    verbose=0,
    random_state=1,
)

# ---- Cell ----
standard_optimizer.maximize(
    init_points=2,
    n_iter=50,
)

# ---- Cell ----
plt.plot(mutating_optimizer.space.target, label='Mutated Optimizer')
plt.plot(standard_optimizer.space.target, label='Standard Optimizer')
plt.legend()

# ---- Cell ----
# example x-bound shrinking - we need to shift the x-axis by the init_points as the bounds
# transformer only mutates when searching - not in the initial phase.
x_min_bound = [b[0][0] for b in bounds_transformer.bounds]
x_max_bound = [b[0][1] for b in bounds_transformer.bounds]
x = [x[0] for x in mutating_optimizer.space.params]
bounds_transformers_iteration = list(range(2, len(x)))

# ---- Cell ----
plt.plot(bounds_transformers_iteration, x_min_bound[1:], label='x lower bound')
plt.plot(bounds_transformers_iteration, x_max_bound[1:], label='x upper bound')
plt.plot(x[1:], label='x')
plt.legend()

