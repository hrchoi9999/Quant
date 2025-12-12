# English filename: visualization_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_부스팅모델 실습_수업/BayesianOptimization/visualization_clear.py
# Original filename: visualization_clear.py

# ---- Cell ----
!pip install bayesian-optimization

# ---- Cell ----
from bayes_opt import BayesianOptimization
from bayes_opt import UtilityFunction
import numpy as np

import matplotlib.pyplot as plt
from matplotlib import gridspec
%matplotlib inline

# ---- Cell ----
def target(x):
    return np.exp(-(x - 2)**2) + np.exp(-(x - 6)**2/10) + 1/ (x**2 + 1)

# ---- Cell ----
x = np.linspace(-2, 10, 10000).reshape(-1, 1)
y = target(x)

plt.plot(x, y);

# ---- Cell ----
optimizer = BayesianOptimization(target, {'x': (-2, 10)}, random_state=27)

# ---- Cell ----
acq_function = UtilityFunction(kind="ucb", kappa=5)
optimizer.maximize(init_points=2, n_iter=0, acquisition_function = acq_function)

# ---- Cell ----
def posterior(optimizer, x_obs, y_obs, grid):
    optimizer._gp.fit(x_obs, y_obs)

    mu, sigma = optimizer._gp.predict(grid, return_std=True)
    return mu, sigma

def plot_gp(optimizer, x, y):
    fig = plt.figure(figsize=(16, 10))
    steps = len(optimizer.space)
    fig.suptitle(
        'Gaussian Process and Utility Function After {} Steps'.format(steps),
        fontdict={'size':30}
    )

    gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1])
    axis = plt.subplot(gs[0])
    acq = plt.subplot(gs[1])

    x_obs = np.array([[res["params"]["x"]] for res in optimizer.res])
    y_obs = np.array([res["target"] for res in optimizer.res])

    mu, sigma = posterior(optimizer, x_obs, y_obs, x)
    axis.plot(x, y, linewidth=3, label='Target')
    axis.plot(x_obs.flatten(), y_obs, 'D', markersize=8, label=u'Observations', color='r')
    axis.plot(x, mu, '--', color='k', label='Prediction')

    axis.fill(np.concatenate([x, x[::-1]]),
              np.concatenate([mu - 1.9600 * sigma, (mu + 1.9600 * sigma)[::-1]]),
        alpha=.6, fc='c', ec='None', label='95% confidence interval')

    axis.set_xlim((-2, 10))
    axis.set_ylim((None, None))
    axis.set_ylabel('f(x)', fontdict={'size':20})
    axis.set_xlabel('x', fontdict={'size':20})

    utility_function = UtilityFunction(kind="ucb", kappa=5, xi=0)
    utility = utility_function.utility(x, optimizer._gp, 0)
    acq.plot(x, utility, label='Utility Function', color='purple')
    acq.plot(x[np.argmax(utility)], np.max(utility), '*', markersize=15,
             label=u'Next Best Guess', markerfacecolor='gold', markeredgecolor='k', markeredgewidth=1)
    acq.set_xlim((-2, 10))
    acq.set_ylim((0, np.max(utility) + 0.5))
    acq.set_ylabel('Utility', fontdict={'size':20})
    acq.set_xlabel('x', fontdict={'size':20})

    axis.legend(loc=2, bbox_to_anchor=(1.01, 1), borderaxespad=0.)
    acq.legend(loc=2, bbox_to_anchor=(1.01, 1), borderaxespad=0.)

# ---- Cell ----
plot_gp(optimizer, x, y)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=1)
plot_gp(optimizer, x, y)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=1, acquisition_function=acq_function)
plot_gp(optimizer, x, y)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=1, acquisition_function=acq_function)
plot_gp(optimizer, x, y)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=1, acquisition_function=acq_function)
plot_gp(optimizer, x, y)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=1, acquisition_function=acq_function)
plot_gp(optimizer, x, y)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=1, acquisition_function=acq_function)
plot_gp(optimizer, x, y)

# ---- Cell ----
optimizer.maximize(init_points=0, n_iter=1, acquisition_function=acq_function)
plot_gp(optimizer, x, y)

# ---- Cell ----

