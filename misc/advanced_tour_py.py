# English filename: advanced_tour_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/BayesianOptimization/advanced-tour_clear.py
# Original filename: advanced-tour_clear.py

# ---- Cell ----
!pip install bayesian-optimization

# ---- Cell ----
from bayes_opt import BayesianOptimization

# ---- Cell ----
# Let's start by defining our function, bounds, and instantiating an optimization object.
def black_box_function(x, y):
    return -x ** 2 - (y - 1) ** 2 + 1

# ---- Cell ----
optimizer = BayesianOptimization(
    f=None,
    pbounds={'x': (-2, 2), 'y': (-3, 3)},
    verbose=2,
    random_state=1,
)

# ---- Cell ----
from bayes_opt import UtilityFunction

utility = UtilityFunction(kind="ucb", kappa=2.5, xi=0.0)

# ---- Cell ----
next_point_to_probe = optimizer.suggest(utility)
print("Next point to probe is:", next_point_to_probe)

# ---- Cell ----
target = black_box_function(**next_point_to_probe)
print("Found the target value to be:", target)

# ---- Cell ----
optimizer.register(
    params=next_point_to_probe,
    target=target,
)

# ---- Cell ----
for _ in range(5):
    next_point = optimizer.suggest(utility)
    target = black_box_function(**next_point)
    optimizer.register(params=next_point, target=target)

    print(target, next_point)
print(optimizer.max)

# ---- Cell ----
def func_with_discrete_params(x, y, d):
    # Simulate necessity of having d being discrete.
    assert type(d) == int

    return ((x + y + d) // (1 + d)) / (1 + (x + y) ** 2)

# ---- Cell ----
def function_to_be_optimized(x, y, w):
    d = int(w)
    return func_with_discrete_params(x, y, d)

# ---- Cell ----
optimizer = BayesianOptimization(
    f=function_to_be_optimized,
    pbounds={'x': (-10, 10), 'y': (-10, 10), 'w': (0, 5)},
    verbose=2,
    random_state=1,
)

# ---- Cell ----
optimizer.set_gp_params(alpha=1e-3)
optimizer.maximize()

# ---- Cell ----
optimizer = BayesianOptimization(
    f=black_box_function,
    pbounds={'x': (-2, 2), 'y': (-3, 3)},
    verbose=2,
    random_state=1,
)
optimizer.set_gp_params(alpha=1e-3, n_restarts_optimizer=5)
optimizer.maximize(
    init_points=1,
    n_iter=5
)

# ---- Cell ----
from bayes_opt.event import DEFAULT_EVENTS, Events

# ---- Cell ----
optimizer = BayesianOptimization(
    f=black_box_function,
    pbounds={'x': (-2, 2), 'y': (-3, 3)},
    verbose=2,
    random_state=1,
)

# ---- Cell ----
class BasicObserver:
    def update(self, event, instance):
        """Does whatever you want with the event and `BayesianOptimization` instance."""
        print("Event `{}` was observed".format(event))

# ---- Cell ----
my_observer = BasicObserver()

optimizer.subscribe(
    event=Events.OPTIMIZATION_STEP,
    subscriber=my_observer,
    callback=None, # Will use the `update` method as callback
)

# ---- Cell ----
def my_callback(event, instance):
    print("Go nuts here!")

optimizer.subscribe(
    event=Events.OPTIMIZATION_START,
    subscriber="Any hashable object",
    callback=my_callback,
)

# ---- Cell ----
optimizer.maximize(init_points=1, n_iter=2)

# ---- Cell ----
DEFAULT_EVENTS
