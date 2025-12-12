# English filename: tutorial_multiclass_classification_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/7일차 선형모델을 통한 수익률 예측 I/보조실습_앙상블_수업/Tutorial - Multiclass Classification_clear.py
# Original filename: Tutorial - Multiclass Classification_clear.py

# ---- Cell ----
!pip install pycaret[full]

# ---- Cell ----
# check installed version
import pycaret
pycaret.__version__

# ---- Cell ----
# loading sample dataset from pycaret dataset module
from pycaret.datasets import get_data
data = get_data('iris')

# ---- Cell ----
# import pycaret classification and init setup
from pycaret.classification import *
s = setup(data, target = 'species', session_id = 123, use_gpu=True)

# ---- Cell ----
# import ClassificationExperiment and init the class
from pycaret.classification import ClassificationExperiment
exp = ClassificationExperiment()

# ---- Cell ----
# check the type of exp
type(exp)

# ---- Cell ----
# init setup on exp
exp.setup(data, target = 'species', session_id = 123)

# ---- Cell ----
# compare baseline models
best = compare_models()

# ---- Cell ----
# compare models using OOP
exp.compare_models()

# ---- Cell ----
# plot confusion matrix
plot_model(best, plot = 'confusion_matrix')

# ---- Cell ----
# plot AUC
plot_model(best, plot = 'auc')

# ---- Cell ----
# plot feature importance
plot_model(best, plot = 'feature')

# ---- Cell ----
# check docstring to see available plots
help(plot_model)

# ---- Cell ----
evaluate_model(best)

# ---- Cell ----
# predict on test set
holdout_pred = predict_model(best)

# ---- Cell ----
# show predictions df
holdout_pred.head()

# ---- Cell ----
# copy data and drop Class variable

new_data = data.copy()
new_data.drop('species', axis=1, inplace=True)
new_data.head()

# ---- Cell ----
# predict model on new_data
predictions = predict_model(best, data = new_data)
predictions.head()

# ---- Cell ----
# save pipeline
save_model(best, 'my_first_pipeline')

# ---- Cell ----
# load pipeline
loaded_best_pipeline = load_model('my_first_pipeline')
loaded_best_pipeline

# ---- Cell ----
s = setup(data, target = 'species', session_id = 123)

# ---- Cell ----
# check all available config
get_config()

# ---- Cell ----
# lets access X_train_transformed
get_config('X_train_transformed')

# ---- Cell ----
# another example: let's access seed
print("The current seed is: {}".format(get_config('seed')))

# now lets change it using set_config
set_config('seed', 786)
print("The new seed is: {}".format(get_config('seed')))

# ---- Cell ----
# help(setup)

# ---- Cell ----
# init setup with normalize = True

s = setup(data, target = 'species', session_id = 123,
          normalize = True, normalize_method = 'minmax')

# ---- Cell ----
# lets check the X_train_transformed to see effect of params passed
get_config('X_train_transformed')['sepal_length'].hist()

# ---- Cell ----
get_config('X_train')['sepal_length'].hist()

# ---- Cell ----
best = compare_models()

# ---- Cell ----
# check available models
models()

# ---- Cell ----
compare_tree_models = compare_models(include = ['dt', 'rf', 'et', 'gbc', 'xgboost', 'lightgbm','catboost'])

# ---- Cell ----
compare_tree_models

# ---- Cell ----
compare_tree_models_results = pull()
compare_tree_models_results

# ---- Cell ----
best_recall_models_top3 = compare_models(sort = 'Recall', n_select = 3)

# ---- Cell ----
# list of top 3 models by Recall
best_recall_models_top3

# ---- Cell ----
# help(compare_models)

# ---- Cell ----
# from pycaret.classification import *
# s = setup(data, target = 'Class variable', log_experiment='mlflow', experiment_name='iris_experiment')

# ---- Cell ----
# compare models
# best = compare_models()

# ---- Cell ----
# start mlflow server on localhost:5000
# !mlflow ui

# ---- Cell ----
# help(setup)

# ---- Cell ----
# check all the available models
models()

# ---- Cell ----
# train logistic regression with default fold=10
lr = create_model('lr')

# ---- Cell ----
lr_results = pull()
print(type(lr_results))
lr_results

# ---- Cell ----
# train logistic regression with fold=3
lr = create_model('lr', fold=3)

# ---- Cell ----
# train logistic regression with specific model parameters
create_model('lr', C = 0.5, l1_ratio = 0.15)

# ---- Cell ----
# train lr and return train score as well alongwith CV
create_model('lr', return_train_score=True)

# ---- Cell ----
# help(create_model)

# ---- Cell ----
# train a dt model with default params
dt = create_model('dt')

# ---- Cell ----
# tune hyperparameters of dt
tuned_dt = tune_model(dt)

# ---- Cell ----
dt

# ---- Cell ----
# define tuning grid
dt_grid = {'max_depth' : [None, 2, 4, 6, 8, 10, 12]}

# tune model with custom grid and metric = F1
tuned_dt = tune_model(dt, custom_grid = dt_grid, optimize = 'F1')

# ---- Cell ----
# to access the tuner object you can set return_tuner = True
tuned_dt, tuner = tune_model(dt, return_tuner=True)

# ---- Cell ----
# model object
tuned_dt

# ---- Cell ----
# tuner object
tuner

# ---- Cell ----
# tune dt using optuna
tuned_dt = tune_model(dt, search_library = 'optuna')

# ---- Cell ----
# help(tune_model)

# ---- Cell ----
# ensemble with bagging
ensemble_model(dt, method = 'Bagging')

# ---- Cell ----
# ensemble with boosting
ensemble_model(dt, method = 'Boosting')

# ---- Cell ----
# help(ensemble_model)

# ---- Cell ----
# top 3 models based on recall
best_recall_models_top3

# ---- Cell ----
# blend top 3 models
blend_models(best_recall_models_top3)

# ---- Cell ----
# help(blend_models)

# ---- Cell ----
# stack models
stack_models(best_recall_models_top3)

# ---- Cell ----
# help(stack_models)

# ---- Cell ----
# plot class report
plot_model(best, plot = 'class_report')

# ---- Cell ----
# to control the scale of plot
plot_model(best, plot = 'class_report', scale = 2)

# ---- Cell ----
# to save the plot
plot_model(best, plot = 'class_report', save=True)

# ---- Cell ----
# help(plot_model)

# ---- Cell ----
# train lightgbm model
lightgbm = create_model('lightgbm')

# ---- Cell ----
# interpret summary model
interpret_model(lightgbm, plot = 'summary')

# ---- Cell ----
# reason plot for test set observation 1
interpret_model(lightgbm, plot = 'reason', observation = 1)

# ---- Cell ----
# help(interpret_model)

# ---- Cell ----
# get leaderboard
lb = get_leaderboard()
lb

# ---- Cell ----
# select the best model based on F1
lb.sort_values(by='F1', ascending=False)['Model'].iloc[0]

# ---- Cell ----
# help(get_leaderboard)

# ---- Cell ----
automl()

# ---- Cell ----
# dashboard function
dashboard(dt, display_format ='inline')

# ---- Cell ----
# create gradio app
create_app(best)

# ---- Cell ----
# create api
create_api(best, api_name = 'my_first_api')

# ---- Cell ----
# !python my_first_api.py

# ---- Cell ----
# check out the .py file created with this magic command
# %load my_first_api.py

# ---- Cell ----
create_docker('my_first_api')

# ---- Cell ----
# check out the DockerFile file created with this magic command
# %load DockerFile

# ---- Cell ----
# check out the requirements file created with this magic command
# %load requirements.txt

# ---- Cell ----
final_best = finalize_model(best)

# ---- Cell ----
final_best

# ---- Cell ----
# transpiles learned function to java
print(convert_model(dt, language = 'java'))

# ---- Cell ----
# deploy model on aws s3
# deploy_model(best, model_name = 'my_first_platform_on_aws',
#             platform = 'aws', authentication = {'bucket' : 'pycaret-test'})

# ---- Cell ----
# load model from aws s3
# loaded_from_aws = load_model(model_name = 'my_first_platform_on_aws', platform = 'aws',
#                              authentication = {'bucket' : 'pycaret-test'})

# loaded_from_aws

# ---- Cell ----
# save model
save_model(best, 'my_first_model')

# ---- Cell ----
# load model
loaded_from_disk = load_model('my_first_model')
loaded_from_disk

# ---- Cell ----
# save experiment
save_experiment('my_experiment')

# ---- Cell ----
# load experiment from disk
exp_from_disk = load_experiment('my_experiment', data=data)
