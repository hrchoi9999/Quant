# English filename: counterfactual_fairness_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-2. 공정성/Counterfactual_Fairness(오래걸림).py
# Original filename: Counterfactual_Fairness(오래걸림).py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/bar_pass_prediction.csv

# ---- Cell ----
%%capture
!pip3 install pyro-ppl

# ---- Cell ----
import os
import pickle
from tqdm import tqdm
import torch
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import pyro
import pyro.distributions as dist
from torch import nn
import seaborn as sns
from pyro.nn import PyroModule
from sklearn.model_selection import train_test_split

# ---- Cell ----
data_df = pd.read_csv("./bar_pass_prediction.csv")

# ---- Cell ----
cols = ["sex", "race", "ugpa", "lsat", "zfygpa"]
data_df = data_df[cols]
data_df.dropna(inplace=True)

# ---- Cell ----
data_df

# ---- Cell ----
# split the dataset 80/20 into a train/test set, preserving label balance
train_set, test_set = train_test_split(data_df, test_size=0.2, stratify=data_df[['sex', 'race']],  random_state=42)

# ---- Cell ----
# check the distribution of sex and race in split
for attr in ["race", "sex"]:
  f, axes = plt.subplots(1, 3)
  for ax, dataset, name in zip(axes, [data_df, train_set, test_set], ["whole", "train", "test"]):
    ax.hist(dataset[attr])
    ax.set_title(f"Dist. of {attr} in {name} data")
    f.tight_layout()
    f.set_size_inches(9, 3)
plt.show()

# ---- Cell ----
# for CI testing
# smoke_test = ('CI' in os.environ)
pyro.enable_validation(True)
pyro.set_rng_seed(1)
pyro.enable_validation(True)

# setup
assert issubclass(PyroModule[nn.Linear], nn.Linear)
assert issubclass(PyroModule[nn.Linear], PyroModule)

# ---- Cell ----
def train_linear_model(x_train, y_train):

  lin_model = PyroModule[nn.Linear](x_train.shape[1], 1)
  loss_fn = torch.nn.MSELoss()
  optim = torch.optim.Adam(lin_model.parameters(), lr=0.05)
  num_iterations = 500

  def train():
      y_pred = lin_model(x_train).squeeze(-1)
      loss = loss_fn(y_pred, y_train)
      optim.zero_grad()
      loss.backward()
      optim.step()
      return loss

  for j in range(num_iterations):
      loss = train()
      if (j + 1) % 300 == 0:
          print("[iteration %04d] RMSE loss: %.4f" % (j + 1, np.square(loss.item())))
  print("Learned parameters:")
  for name, param in lin_model.named_parameters():
      print(name, param.data.numpy())
  return lin_model

# ---- Cell ----
unaware_sample_train = torch.tensor(train_set[["ugpa", "lsat", "zfygpa"]].values, dtype=torch.float32)
unaware_sample_test = torch.tensor(test_set[["ugpa", "lsat", "zfygpa"]].values, dtype=torch.float32)
train_x_unaware, train_y_unaware = unaware_sample_train[:, :-1], unaware_sample_train[:, -1]
test_x_unaware, test_y_unaware = unaware_sample_test[:, :-1], unaware_sample_test[:, -1]

model_unaware = train_linear_model(train_x_unaware, train_y_unaware)

# ---- Cell ----
loss_fn = torch.nn.MSELoss()
y_pred = model_unaware(test_x_unaware).squeeze(-1)
loss = loss_fn(y_pred, test_y_unaware).item()
print(f"Unaware Model: RMSE on test samples = {np.square(loss):.4f}")

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on train set
fit = train_set.copy()
fit["FYA"] = model_unaware(train_x_unaware).detach().numpy()
f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)

sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on test set
fit = test_set.copy()
fit["FYA"] = model_unaware(test_x_unaware).detach().numpy()

f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)

sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()

# ---- Cell ----
full_sample_train = torch.tensor(train_set[["sex", "race", "ugpa", "lsat", "zfygpa"]].values, dtype=torch.float32)
full_sample_test = torch.tensor(test_set[["sex", "race", "ugpa", "lsat", "zfygpa"]].values, dtype=torch.float32)
train_x_full, train_y_full = full_sample_train[:, :-1], full_sample_train[:, -1]
test_x_full, test_y_full = full_sample_test[:, :-1], full_sample_test[:, -1]

model_full = train_linear_model(train_x_full, train_y_full)

# ---- Cell ----
loss_fn = torch.nn.MSELoss()
y_pred = model_full(test_x_full).squeeze(-1)
loss = loss_fn(y_pred, test_y_full).item()
print(f"Full Model: RMSE on test samples = {np.square(loss):.4f}")

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on train set
fit = train_set.copy()
fit["FYA"] = model_full(train_x_full).detach().numpy()

f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)
sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on test set
fit = test_set.copy()
fit["FYA"] = model_full(test_x_full).detach().numpy()

f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)
sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()

# ---- Cell ----
def LawSchoolModel(race, sex, gpa=None, lsat=None, fya=None):
    distributions = {
        'Inverse Gamma': dist.InverseGamma(torch.tensor(1.), torch.tensor(1.)),
        'Standard Normal': dist.Normal(torch.tensor(0.), torch.tensor(1.)),
    }

    k = pyro.sample("k", distributions['Standard Normal'])
    gpa0 = pyro.sample("gpa0", distributions['Standard Normal'])
    w_k_gpa = pyro.sample("w_k_gpa", distributions['Standard Normal'])
    w_r_gpa = pyro.sample("w_r_gpa", distributions['Standard Normal'])
    w_s_gpa = pyro.sample("w_s_gpa", distributions['Standard Normal'])
    lsat0 = pyro.sample("lsat0", distributions['Standard Normal'])
    w_k_lsat = pyro.sample("w_k_lsat", distributions['Standard Normal'])
    w_r_lsat = pyro.sample("w_r_lsat", distributions['Standard Normal'])
    w_s_lsat = pyro.sample("w_s_lsat", distributions['Standard Normal'])
    w_k_fya = pyro.sample("w_k_fya", distributions['Standard Normal'])
    w_r_fya = pyro.sample("w_r_fya", distributions['Standard Normal'])
    w_s_fya = pyro.sample("w_s_fya", distributions['Standard Normal'])
    sigma_gpa_square = pyro.sample("sigma_gpa_sq", distributions['Inverse Gamma'])

    mean_gpa = gpa0 + k * w_k_gpa + race * w_r_gpa + sex * w_s_gpa
    param_lsat = lsat0 + k * w_k_lsat + race * w_r_lsat + sex * w_s_lsat
    mean_fya = k * w_k_fya + race * w_r_fya + sex * w_s_fya
    with pyro.plate("data", len(race)):
      gpa = pyro.sample("gpa", dist.Normal(mean_gpa, torch.square(sigma_gpa_square)), obs=gpa)
      lsat = pyro.sample("lsat", dist.Poisson(param_lsat.exp()), obs=lsat)
      fya = pyro.sample("fya", dist.Normal(mean_fya, 1), obs=fya)
      return gpa, lsat, fya

# ---- Cell ----
data_tensor = torch.tensor(train_set.values, dtype=torch.float32)
data_test_tensor = torch.tensor(test_set.values, dtype=torch.float32)

# ---- Cell ----
model_graph = pyro.render_model(LawSchoolModel, model_args=(data_tensor[:, 0], data_tensor[:, 1], data_tensor[:, 2], data_tensor[:, 3], data_tensor[:, 4]), render_distributions=True, render_params=True)
model_graph

# ---- Cell ----
K_list = []
for i in tqdm(range(data_tensor.shape[0])):
  conditioned = pyro.condition(LawSchoolModel, data={"gpa": data_tensor[i, 2], "lsat": data_tensor[i, 3].type(torch.int32), "fya": data_tensor[i, 4]})

  posterior = pyro.infer.Importance(conditioned, num_samples=10)
  marginal = pyro.infer.EmpiricalMarginal(posterior.run(race=data_tensor[:, 0], sex=data_tensor[:, 1]), sites="k")
  K_list.append(marginal.mean)

with open('inferred_K_train.pkl', 'wb') as f:
  pickle.dump(K_list, f)

# ---- Cell ----
K_list_test = []
for i in tqdm(range(data_test_tensor.shape[0])):
  conditioned = pyro.condition(LawSchoolModel, data={"gpa": data_test_tensor[i, 2], "lsat": data_test_tensor[i, 3].type(torch.int32), "fya": data_test_tensor[i, 4]})
  posterior = pyro.infer.Importance(conditioned, num_samples=10)
  marginal = pyro.infer.EmpiricalMarginal(posterior.run(race=data_test_tensor[:, 0], sex=data_test_tensor[:, 1]), sites="k")
  K_list_test.append(marginal.mean)

with open('inferred_K_test.pkl', 'wb') as f:
  pickle.dump(K_list_test, f)

# ---- Cell ----
with open('./inferred_K_train.pkl', 'rb') as f:
  K_list = pickle.load(f)

with open('./inferred_K_test.pkl', 'rb') as f:
  K_list_test = pickle.load(f)

# ---- Cell ----
# plt.hist(K_list)
plt.figure(figsize=(7, 5))
sns.kdeplot(np.array(K_list), label="Inferred K density")
sns.kdeplot(np.random.randn(10000), label="Standard Gaussian density")
plt.xlabel("K")
plt.legend()
plt.show()

# ---- Cell ----
x_data, y_data = torch.tensor(K_list, dtype=torch.float32).reshape(-1,1), data_tensor[:, -1]

model_fairK = train_linear_model(x_data, y_data)

# ---- Cell ----
loss_fn = torch.nn.MSELoss()
y_pred_test = model_fairK(torch.tensor(K_list_test, dtype=torch.float32).reshape(-1,1)).squeeze(-1)
loss = loss_fn(y_pred_test, data_test_tensor[:, -1]).item()
print(f"Fair K Model: RMSE on test samples = {np.square(loss):.4f}")

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on train set
fit = train_set.copy()
fit["FYA"] = model_fairK(x_data).detach().numpy()

f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)
sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on test set
fit = test_set.copy()
fit["FYA"] = y_pred_test.detach().numpy()

f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)
sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()

# ---- Cell ----
race_sex_tensor_train = torch.tensor(train_set[["race", "sex"]].values, dtype=torch.float32)
gpa_tensor_train = torch.tensor(train_set[["ugpa"]].values, dtype=torch.float32)[:, 0]
lsat_tensor_train = torch.tensor(train_set[["lsat"]].values, dtype=torch.float32)[:, 0]

print("-"*20)
print("Predict GPA based on race and sex:")
model_gpa_rs = train_linear_model(race_sex_tensor_train, gpa_tensor_train)

print("-"*20)
print("Predict LSAT based on race and sex:")
model_lsat_rs = train_linear_model(race_sex_tensor_train, lsat_tensor_train)

# ---- Cell ----
gpa_tensor_resid = gpa_tensor_train - model_gpa_rs(race_sex_tensor_train).detach().squeeze(0).numpy()[:, 0]
lsat_tensor_resid = lsat_tensor_train - model_lsat_rs(race_sex_tensor_train).detach().squeeze(0).numpy()[:, 0]

x_fair_add = torch.stack((gpa_tensor_resid, lsat_tensor_resid), dim=1)
y_fair_add = torch.tensor(train_set[["zfygpa"]].values, dtype=torch.float32)[:, 0]
print("Predict FYA based on residuals of GPA and LSAT:")
model_fair_add = train_linear_model(x_fair_add, y_fair_add)

# ---- Cell ----
race_sex_tensor_test = torch.tensor(test_set[["race", "sex"]].values, dtype=torch.float32)
gpa_tensor_test = torch.tensor(test_set[["ugpa"]].values, dtype=torch.float32)[:, 0]
lsat_tensor_test = torch.tensor(test_set[["lsat"]].values, dtype=torch.float32)[:, 0]

gpa_tensor_resid_test = gpa_tensor_test - model_gpa_rs(race_sex_tensor_test).detach().squeeze(0).numpy()[:, 0]
lsat_tensor_resid_test = lsat_tensor_test - model_lsat_rs(race_sex_tensor_test).detach().squeeze(0).numpy()[:, 0]

x_fair_add_test = torch.stack((gpa_tensor_resid_test, lsat_tensor_resid_test), dim=1)
y_fair_add_test = torch.tensor(test_set[["zfygpa"]].values, dtype=torch.float32)[:, 0]

loss_fn = torch.nn.MSELoss()
y_pred_test = model_fair_add(x_fair_add_test).squeeze(-1)
loss = loss_fn(y_pred_test, y_fair_add_test).item()
print(f"Fair add Model: RMSE on test samples = {np.square(loss):.4f}")

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on train set
fit = train_set.copy()
fit["FYA"] = model_fair_add(x_fair_add).detach().numpy()

f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)
sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()

# ---- Cell ----
# Look at distribution of FYA on difference races and sex on test set
fit = test_set.copy()
fit["FYA"] = model_fair_add(x_fair_add_test).detach().numpy()

f, (ax1, ax2) = plt.subplots(2)
f.set_size_inches(9, 6)
sns.kdeplot(x="FYA", data=fit, hue="sex", ax=ax1, legend=True, common_norm=False, palette = sns.color_palette(n_colors=2))
sns.kdeplot(x="FYA", data=fit, hue="race", ax=ax2, legend=True, common_norm=False, palette = sns.color_palette(n_colors=8))
plt.show()
