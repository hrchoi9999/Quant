# English filename: basic_tour_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/BayesianOptimization/basic-tour_clear.py
# Original filename: basic-tour_clear.py

# ---- Cell ----
!pip install bayesian-optimization

# ---- Cell ----
def black_box_function(x, y):
    """Function with unknown internals we wish to maximize.

    This is just serving as an example, for all intents and
    purposes think of the internals of this function, i.e.: the process
    which generates its output values, as unknown.
    """
    return -x ** 2 - (y - 1) ** 2 + 1

# ---- Cell ----
from bayes_opt import BayesianOptimization

# ---- Cell ----
# Bounded region of parameter space
pbounds = {'x': (2, 4), 'y': (-3, 3)}

# ---- Cell ----
optimizer = BayesianOptimization(
    f=black_box_function,
    pbounds=pbounds,
    verbose=2, # verbose = 1 prints only when a maximum is observed, verbose = 0 is silent
    random_state=1,
)

# ---- Cell ----
optimizer.maximize(
    init_points=2,
    n_iter=3,
)

# ---- Cell ----
print(optimizer.max)

# ---- Cell ----
for i, res in enumerate(optimizer.res):
    print("Iteration {}: \n\t{}".format(i, res))

# ---- Cell ----
optimizer.set_bounds(new_bounds={"x": (-2, 3)})

# ---- Cell ----
optimizer.maximize(
    init_points=0,
    n_iter=5,
)

# ---- Cell ----
optimizer.probe(
    params={"x": 0.5, "y": 0.7},
    lazy=True,
)

# ---- Cell ----
print(optimizer.space.keys)

# ---- Cell ----
optimizer.probe(
    params=[-0.3, 0.1],
    lazy=True,
)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=0)

# ---- Cell ----
from bayes_opt.logger import JSONLogger
from bayes_opt.event import Events

# ---- Cell ----
logger = JSONLogger(path="./logs.log")
optimizer.subscribe(Events.OPTIMIZATION_STEP, logger)

# ---- Cell ----
optimizer.maximize(
    init_points=2,
    n_iter=3,
)

# ---- Cell ----
from bayes_opt.util import load_logs

# ---- Cell ----
new_optimizer = BayesianOptimization(
    f=black_box_function,
    pbounds={"x": (-2, 2), "y": (-2, 2)},
    verbose=2,
    random_state=7,
)
print(len(new_optimizer.space))

# ---- Cell ----
load_logs(new_optimizer);

# ---- Cell ----
print("New optimizer is now aware of {} points.".format(len(new_optimizer.space)))

# ---- Cell ----
new_optimizer.maximize(
    init_points=0,
    n_iter=10,
)
