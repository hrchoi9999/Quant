# English filename: an_introduction_to_explainable_ai_with_shapley_values_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-3. 설명가능성/An introduction to explainable AI with Shapley values.py
# Original filename: An introduction to explainable AI with Shapley values.py

# ---- Cell ----
!pip install shap interpret transformers datasets

# ---- Cell ----
import pandas as pd
import shap
import sklearn

# a classic housing price dataset
X,y = shap.datasets.california(n_points=1000)

X100 = shap.utils.sample(X, 100) # 100 instances for use as the background distribution

# a simple linear model
model = sklearn.linear_model.LinearRegression()
model.fit(X, y)

# ---- Cell ----
print("Model coefficients:\n")
for i in range(X.shape[1]):
    print(X.columns[i], "=", model.coef_[i].round(5))

# ---- Cell ----
shap.partial_dependence_plot(
    "MedInc", model.predict, X100, ice=False,
    model_expected_value=True, feature_expected_value=True
)

# ---- Cell ----
# compute the SHAP values for the linear model
explainer = shap.Explainer(model.predict, X100)
shap_values = explainer(X)

# make a standard partial dependence plot
sample_ind = 20
shap.partial_dependence_plot(
    "MedInc", model.predict, X100, model_expected_value=True,
    feature_expected_value=True, ice=False,
    shap_values=shap_values[sample_ind:sample_ind+1,:]
)

# ---- Cell ----
shap.plots.scatter(shap_values[:,"MedInc"])

# ---- Cell ----
# the waterfall_plot shows how we get from shap_values.base_values to model.predict(X)[sample_ind]
shap.plots.waterfall(shap_values[sample_ind], max_display=14)

# ---- Cell ----
# fit a GAM model to the data
import interpret.glassbox
model_ebm = interpret.glassbox.ExplainableBoostingRegressor(interactions=0)
model_ebm.fit(X, y)

# explain the GAM model with SHAP
explainer_ebm = shap.Explainer(model_ebm.predict, X100)
shap_values_ebm = explainer_ebm(X)

# make a standard partial dependence plot with a single SHAP value overlaid
fig,ax = shap.partial_dependence_plot(
    "MedInc", model_ebm.predict, X100, model_expected_value=True,
    feature_expected_value=True, show=False, ice=False,
    shap_values=shap_values_ebm[sample_ind:sample_ind+1,:]
)

# ---- Cell ----
shap.plots.scatter(shap_values_ebm[:,"MedInc"])

# ---- Cell ----
# the waterfall_plot shows how we get from explainer.expected_value to model.predict(X)[sample_ind]
shap.plots.waterfall(shap_values_ebm[sample_ind])

# ---- Cell ----
# the waterfall_plot shows how we get from explainer.expected_value to model.predict(X)[sample_ind]
shap.plots.beeswarm(shap_values_ebm)

# ---- Cell ----
# train XGBoost model
import xgboost
model_xgb = xgboost.XGBRegressor(n_estimators=100, max_depth=2).fit(X, y)

# explain the GAM model with SHAP
explainer_xgb = shap.Explainer(model_xgb, X100)
shap_values_xgb = explainer_xgb(X)

# make a standard partial dependence plot with a single SHAP value overlaid
fig,ax = shap.partial_dependence_plot(
    "MedInc", model_xgb.predict, X100, model_expected_value=True,
    feature_expected_value=True, show=False, ice=False,
    shap_values=shap_values_xgb[sample_ind:sample_ind+1,:]
)

# ---- Cell ----
shap.plots.scatter(shap_values_xgb[:,"MedInc"])

# ---- Cell ----
shap.plots.scatter(shap_values_xgb[:,"MedInc"], color=shap_values)

# ---- Cell ----
# a classic adult census dataset price dataset
X_adult,y_adult = shap.datasets.adult()

# a simple linear logistic model
model_adult = sklearn.linear_model.LogisticRegression(max_iter=10000)
model_adult.fit(X_adult, y_adult)

def model_adult_proba(x):
    return model_adult.predict_proba(x)[:,1]
def model_adult_log_odds(x):
    p = model_adult.predict_log_proba(x)
    return p[:,1] - p[:,0]

# ---- Cell ----
# make a standard partial dependence plot
sample_ind = 18
fig,ax = shap.partial_dependence_plot(
    "Capital Gain", model_adult_proba, X_adult, model_expected_value=True,
    feature_expected_value=True, show=False, ice=False
)


# ---- Cell ----
# compute the SHAP values for the linear model
background_adult = shap.maskers.Independent(X_adult, max_samples=100)
explainer = shap.Explainer(model_adult_proba, background_adult)
shap_values_adult = explainer(X_adult[:1000])

# ---- Cell ----
shap.plots.scatter(shap_values_adult[:,"Age"])

# ---- Cell ----
# compute the SHAP values for the linear model
explainer_log_odds = shap.Explainer(model_adult_log_odds, background_adult)
shap_values_adult_log_odds = explainer_log_odds(X_adult[:1000])

# ---- Cell ----
shap.plots.scatter(shap_values_adult_log_odds[:,"Age"])

# ---- Cell ----
# make a standard partial dependence plot
sample_ind = 18
fig,ax = shap.partial_dependence_plot(
    "Age", model_adult_log_odds, X_adult, model_expected_value=True,
    feature_expected_value=True, show=False, ice=False
)


# ---- Cell ----
# train XGBoost model
model = xgboost.XGBClassifier(n_estimators=100, max_depth=2).fit(X_adult, y_adult*1)

# compute SHAP values
explainer = shap.Explainer(model, background_adult)
shap_values = explainer(X_adult)

# set a display version of the data to use for plotting (has string values)
shap_values.display_data = shap.datasets.adult(display=True)[0].values

# ---- Cell ----
shap.plots.bar(shap_values)

# ---- Cell ----
shap.plots.bar(shap_values.abs.max(0))

# ---- Cell ----
shap.plots.beeswarm(shap_values)

# ---- Cell ----
shap.plots.beeswarm(shap_values.abs, color="shap_red")

# ---- Cell ----
shap.plots.heatmap(shap_values[:1000])

# ---- Cell ----
shap.plots.scatter(shap_values[:,"Age"])

# ---- Cell ----
shap.plots.scatter(shap_values[:,"Age"], color=shap_values)

# ---- Cell ----
shap.plots.scatter(shap_values[:,"Age"], color=shap_values[:,"Capital Gain"])

# ---- Cell ----
shap.plots.scatter(shap_values[:,"Relationship"], color=shap_values)

# ---- Cell ----
clustering = shap.utils.hclust(X_adult, y_adult)

# ---- Cell ----
shap.plots.bar(shap_values, clustering=clustering)

# ---- Cell ----
shap.plots.bar(shap_values, clustering=clustering, clustering_cutoff=0.8)

# ---- Cell ----
shap.plots.bar(shap_values, clustering=clustering, clustering_cutoff=1.8)

# ---- Cell ----
import transformers
import datasets
import torch
import numpy as np
import scipy as sp

# load a BERT sentiment analysis model
tokenizer = transformers.DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")
model = transformers.DistilBertForSequenceClassification.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english"
).cuda()

# define a prediction function
def f(x):
    tv = torch.tensor([tokenizer.encode(v, padding='max_length', max_length=500, truncation=True) for v in x]).cuda()
    outputs = model(tv)[0].detach().cpu().numpy()
    scores = (np.exp(outputs).T / np.exp(outputs).sum(-1)).T
    val = sp.special.logit(scores[:,1]) # use one vs rest logit units
    return val

# build an explainer using a token masker
explainer = shap.Explainer(f, tokenizer)

# explain the model's predictions on IMDB reviews
imdb_train = datasets.load_dataset("imdb")["train"]
shap_values = explainer(imdb_train[:10], fixed_context=1, batch_size=2)

# ---- Cell ----
# plot a sentence's explanation
shap.plots.text(shap_values[2])

# ---- Cell ----
shap.plots.bar(shap_values.abs.mean(0))

# ---- Cell ----
shap.plots.bar(shap_values.abs.sum(0))

# ---- Cell ----

