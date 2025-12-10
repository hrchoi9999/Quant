# English filename: temporal_fusion_transformer_in_pytorch_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/2. 최신딥러닝시계열모델/temporal-fusion-transformer-in-pytorch_clear.py
# Original filename: temporal-fusion-transformer-in-pytorch_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/kaggle_data/tabular-playground-series-sep-2022.zip&& unzip -n tabular-playground-series-sep-2022.zip

# ---- Cell ----
# !pip install lightning==2.0.1
!pip install pytorch_forecasting

# ---- Cell ----
# imports

import copy
from pathlib import Path
import warnings
import holidays
import seaborn as sns
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
plt.style.use('fivethirtyeight') #Not a great fan of their website (I found it super-biased), but this stylesheet is the best

import numpy as np
import pandas as pd
# import pytorch_lightning as pl
import lightning.pytorch as pl
from lightning.pytorch.loggers import TensorBoardLogger
# from pytorch_lightning.callbacks import EarlyStopping, LearningRateMonitor
# from pytorch_lightning.loggers import TensorBoardLogger

from lightning.pytorch.callbacks.early_stopping import EarlyStopping
from lightning.pytorch.callbacks import LearningRateMonitor

import torch
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

from pytorch_forecasting import Baseline, TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data import GroupNormalizer, NaNLabelEncoder
from pytorch_forecasting.metrics import SMAPE, PoissonLoss, QuantileLoss
from pytorch_forecasting.models.temporal_fusion_transformer.tuning import optimize_hyperparameters
import random
import gc
import tensorflow as tf
import tensorboard as tb
# tf.io.gfile = tb.compat.tensorflow_stub.io.gfile

random.seed(30)
np.random.seed(30)
tf.random.set_seed(30)
torch.manual_seed(30)
torch.cuda.manual_seed(30)

# ---- Cell ----
# Data loading

train = pd.read_csv("train.csv")
test = pd.read_csv("test.csv")
train['date'] = pd.to_datetime(train['date'])
test['date'] = pd.to_datetime(test['date'])

data = pd.concat([train, test], axis = 0, ignore_index=True)

# Check that key is country-store-product-date combination
assert len(data.drop_duplicates(['country', 'store', 'product', 'date'])) == len(data)
# Check that there is one date per country-store-product combination
assert len(data.drop_duplicates(['country', 'store', 'product'])) == len(data)//data['date'].nunique()

display(train.sample(4))

# ---- Cell ----
# Number of Nans, num_sold not present in test, it's the column we have to predict

(train.isna().sum(axis = 0).rename('nans_per_column_train').rename_axis('column').reset_index().set_index('column')
 .join(test.isna().sum(axis = 0).rename('nans_per_column_test').rename_axis('column').reset_index().set_index('column')))

# ---- Cell ----
# Number of Unique values, num_sold not present in test, it's the column we have to predict

(train.nunique(axis = 0).rename('n_unique_per_column_train').rename_axis('column').reset_index().set_index('column')
 .join(test.nunique(axis = 0).rename('n_unique_per_column_test').rename_axis('column').reset_index().set_index('column')))

# ---- Cell ----
fig, ax = plt.subplots(1,1, figsize=(20, 6))

sns.kdeplot(data=train, x = 'num_sold', hue = 'country', fill=True, alpha = 0.15, ax = ax, linewidth=3, palette='pastel')
ax.set_xlabel('num_sold', color='black', fontweight='bold', fontsize=13)
ax.set_ylabel('density', color='black', fontweight='bold', fontsize=13)
ax.set_xlim(0, 700)
ax.xaxis.set_tick_params(labelsize=15)
ax.yaxis.set_ticklabels([])
ax.set_title('Density plot for num_sold per country (clipped at 700)', fontweight = 'bold', fontsize = 20);

# ---- Cell ----
fig, ax = plt.subplots(1,1, figsize=(20, 6))

sns.kdeplot(data=train, x = 'num_sold', hue = 'store', fill=True, alpha = 0.15, ax = ax, linewidth=2.5)
ax.set_xlabel('num_sold', color='black', fontweight='bold', fontsize=13)
ax.set_ylabel('density', color='black', fontweight='bold', fontsize=13)
ax.set_xlim(0, 700)
ax.set_title('Density plot for num_sold per store (clipped at 700)', fontweight = 'bold', fontsize = 20)
ax.xaxis.set_tick_params(labelsize=15)
ax.yaxis.set_ticklabels([]);

# ---- Cell ----
fig, ax = plt.subplots(1,1, figsize=(20, 6))

sns.kdeplot(data=train, x = 'num_sold', hue = 'product', fill=True, alpha = 0.05, ax = ax, linewidth=2.5)
ax.set_xlabel('num_sold', color='black', fontweight='bold', fontsize=13)
ax.set_ylabel('density', color='black', fontweight='bold', fontsize=13)
ax.set_xlim(0, 700)
ax.set_title('Density plot for num_sold per product (clipped at 700)', fontweight = 'bold', fontsize = 20)
ax.xaxis.set_tick_params(labelsize=15)
ax.yaxis.set_ticklabels([]);

# ---- Cell ----
fig, ax = plt.subplots(1, 1, figsize = (20, 8))
sns.lineplot(x='date',y='num_sold',hue='country',data=(train.groupby(['date', 'country']).num_sold.sum().rename('num_sold')
                                                       .reset_index().sort_values('date', ascending = True, ignore_index=True)), linewidth = 2, alpha = 0.7)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=120))
ax.set_xlabel('date', color='black', fontweight='bold', fontsize=13)
ax.set_ylabel('num_sold', color='black', fontweight='bold', fontsize=13)
ax.legend(fontsize = 20, loc = 'upper left')
ax.set_title('num_sold per Country and Date', fontweight = 'bold', fontsize = 20);

# ---- Cell ----
fig, ax = plt.subplots(1, 1, figsize = (20, 8))
sns.lineplot(x='date',y='num_sold',hue='store',data=(train.groupby(['date', 'store']).num_sold.sum().rename('num_sold')
                                                       .reset_index().sort_values('date', ascending = True, ignore_index=True)), linewidth = 2, alpha = 0.7)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=120))
ax.set_xlabel('date', color='black', fontweight='bold', fontsize=13)
ax.set_ylabel('num_sold', color='black', fontweight='bold', fontsize=13)
ax.set_title('num_sold per Store and Date', fontweight = 'bold', fontsize = 20)
ax.legend(fontsize = 20, loc = 'upper left');

# ---- Cell ----
fig, ax = plt.subplots(1, 1, figsize = (20, 8))
sns.lineplot(x='date',y='num_sold',hue='product',data=(train.groupby(['date', 'product']).num_sold.sum().rename('num_sold')
                                                       .reset_index().sort_values('date', ascending = True, ignore_index=True)), linewidth = 2, alpha = 0.7)
plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=120))
ax.set_xlabel('date', color='black', fontweight='bold', fontsize=13)
ax.set_ylabel('num_sold', color='black', fontweight='bold', fontsize=13)
ax.set_title('num_sold per Product and Date', fontweight = 'bold', fontsize = 20);

# ---- Cell ----
all_time_series = (train.drop(['row_id'], axis = 1).pivot(columns = ['country', 'store', 'product'], index = 'date', values = 'num_sold'))
all_time_series.columns = list(map(lambda x: "_".join(x), all_time_series.columns))

corr_matrix = round(all_time_series.corr(), 2)
mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
colors = sns.color_palette('coolwarm', 16)
levels = np.linspace(-1, 1, 16)
cmap_plot, norm = matplotlib.colors.from_levels_and_colors(levels, colors, extend="max")

fig, ax = plt.subplots(1, 1, figsize = (30, 30))

mask_feature = np.triu(np.ones_like(corr_matrix, dtype=bool))
sns.heatmap(corr_matrix,
            mask = mask_feature | (np.abs(corr_matrix) < 0.7),
            annot=True, ax = ax, cbar=False,
            cmap = cmap_plot,
            norm = norm, annot_kws={"size": 13, "color": 'black'
                                   # , 'fontweight' : 'bold'
                                   })

ax.hlines(range(corr_matrix.shape[1]), *ax.get_xlim(), color = 'black')
ax.vlines(range(corr_matrix.shape[1]), *ax.get_ylim(), color = 'black')

ax.set_title('Correlation Matrix between each time series: absolute values under 0.7 are masked',
             fontsize = 20, color = 'black', fontweight = 'bold');

# ---- Cell ----
# Add a time_idx (an sequence of consecutive integers that goes from min to max date)

data = (data.merge((data[['date']].drop_duplicates(ignore_index=True)
.rename_axis('time_idx')).reset_index(), on = ['date']))

# ---- Cell ----
# add additional features
data["day_of_week"] = data.date.dt.dayofweek.astype(str).astype("category")  # categories have be strings
data["week_of_year"] = data.date.apply(lambda x: x.weekofyear).astype(str).astype("category")  # categories have be strings
data["month"] = data.date.dt.month.astype(str).astype("category")  # categories have be strings
data["log_num_sold"] = np.log(data.num_sold + 1e-8)
data["avg_volume_by_country"] = data.groupby(["time_idx", "country"], observed=True).num_sold.transform("mean")
data["avg_volume_by_store"] = data.groupby(["time_idx", "store"], observed=True).num_sold.transform("mean")
data["avg_volume_by_product"] = data.groupby(["time_idx", "product"], observed=True).num_sold.transform("mean")

unique_dates_country = data[['date', 'country']].drop_duplicates(ignore_index = True)
unique_dates_country['is_holiday'] = (unique_dates_country
                                      .apply(lambda x: x.date in holidays.country_holidays(x.country), axis = 1).astype('category'))
unique_dates_country['is_holiday_lead_1'] = (unique_dates_country
                                             .apply(lambda x: x.date+pd.Timedelta(days=1) in holidays.country_holidays(x.country), axis = 1).astype('category'))
unique_dates_country['is_holiday_lead_2'] = (unique_dates_country
                                             .apply(lambda x: x.date+pd.Timedelta(days=2) in holidays.country_holidays(x.country), axis = 1).astype('category'))
unique_dates_country['is_holiday_lag_1'] = (unique_dates_country
                                            .apply(lambda x: x.date-pd.Timedelta(days=1) in holidays.country_holidays(x.country), axis = 1).astype('category'))
unique_dates_country['is_holiday_lag_2'] = (unique_dates_country
                                            .apply(lambda x: x.date-pd.Timedelta(days=2) in holidays.country_holidays(x.country), axis = 1).astype('category'))
data = data.merge(unique_dates_country, on = ['date', 'country'], validate = "m:1")
del unique_dates_country
gc.collect()
data.sample(5, random_state=30)


# ---- Cell ----
train = data.iloc[:len(train)]
test = data.iloc[len(train):]

max_prediction_length = 365 # We will predict the entire 2021 year
max_encoder_length = train.date.nunique()
training_cutoff = train["time_idx"].max() - max_prediction_length #we will validate on 2020

# ---- Cell ----
train_col = train.filter(like='is_holiday').columns
train.loc[:, train_col] = train.filter(like='is_holiday').astype(str)
test.loc[:, train_col] = test.filter(like='is_holiday').astype(str)

# ---- Cell ----
# Let's create a Dataset
training = TimeSeriesDataSet(
    train[lambda x: x.time_idx <= training_cutoff].drop('row_id', axis = 1),
    time_idx="time_idx",
    target="num_sold",
    group_ids=["country", "store", "product"],
    min_encoder_length=max_prediction_length,  # keep encoder length long (as it is in the validation set)
    max_encoder_length=max_encoder_length,
    max_prediction_length=max_prediction_length,
    static_categoricals=["country", "store", "product"],
    time_varying_known_categoricals=["month",
                                     "week_of_year",
                                     "day_of_week",
                                    #  "is_holiday",
                                     "is_holiday_lead_1", "is_holiday_lead_2",
                                     "is_holiday_lag_1", "is_holiday_lag_2"],
    #variable_groups={"is_holiday": ["is_holiday"]},  # group of categorical variables can be treated as one variable
    time_varying_known_reals=["time_idx"],
    time_varying_unknown_categoricals=[],
    time_varying_unknown_reals=[
        "num_sold", "log_num_sold", "avg_volume_by_country",
        "avg_volume_by_store", "avg_volume_by_product"
    ],
    target_normalizer=GroupNormalizer(
        groups=["country", "store", "product"], transformation="softplus"
    ),  # use softplus and normalize by group
    categorical_encoders={
        'week_of_year':NaNLabelEncoder(add_nan=True)
    },
    lags={'num_sold': [7, 30, 365]},
    add_relative_time_idx=True,
    add_target_scales=True,
    add_encoder_length=True,

)

# create validation set (predict=True) which means to predict the last max_prediction_length points in time
# for each series
validation = TimeSeriesDataSet.from_dataset(training, train, predict=True, stop_randomization=True)

# create dataloaders for model
batch_size = 128  # set this between 32 to 128
train_dataloader = training.to_dataloader(train=True, batch_size=batch_size, num_workers=0)
val_dataloader = validation.to_dataloader(train=False, batch_size=batch_size * 10, num_workers=0)

# ---- Cell ----
device = 'cuda' if torch.cuda.is_available() else 'cpu'

# ---- Cell ----
#let's see how a naive model does

actuals = torch.cat([y for x, (y, weight) in iter(val_dataloader)]).to(device)
baseline_predictions = Baseline().predict(val_dataloader).to(device)
(actuals - baseline_predictions).abs().mean().item()

sm = SMAPE()

# ---- Cell ----
print(f"Median loss for naive prediction on validation: {sm.loss(actuals, baseline_predictions).mean(axis = 1).median().item()}")

# ---- Cell ----
PATIENCE = 30
# MAX_EPOCHS = 120
MAX_EPOCHS = 20
LEARNING_RATE = 0.03
OPTUNA = False

# ---- Cell ----
early_stop_callback = EarlyStopping(monitor="train_loss", min_delta=1e-2, patience=PATIENCE, verbose=False, mode="min")
lr_logger = LearningRateMonitor()  # log the learning rate
logger = TensorBoardLogger("lightning_logs")  # logging results to a tensorboard



trainer = pl.Trainer(
    max_epochs=MAX_EPOCHS,
    # gpus=1,
    devices=1,
    accelerator="gpu",
    enable_model_summary=True,
    gradient_clip_val=0.25,
    limit_train_batches=10,  # coment in for training, running valiation every 30 batches
    #fast_dev_run=True,  # comment in to check that networkor dataset has no serious bugs
    callbacks=[lr_logger, early_stop_callback],
    logger=logger,
)


tft = TemporalFusionTransformer.from_dataset(
    training,
    learning_rate=LEARNING_RATE,
    lstm_layers=2,
    hidden_size=16,
    attention_head_size=2,
    dropout=0.2,
    hidden_continuous_size=8,
    output_size=1,  # 7 quantiles by default
    loss=SMAPE(),
    log_interval=10,  # uncomment for learning rate finder and otherwise, e.g. to 10 for logging every 10 batches
    reduce_on_plateau_patience=4
)

tft.to(DEVICE)
print(f"Number of parameters in network: {tft.size()/1e3:.1f}k")

# ---- Cell ----
trainer.fit(
    tft,
    train_dataloaders=train_dataloader,
    val_dataloaders=val_dataloader,
)

# ---- Cell ----
if OPTUNA:

    from pytorch_forecasting.models.temporal_fusion_transformer.tuning import optimize_hyperparameters

    # create study
    study = optimize_hyperparameters(
        train_dataloader,
        val_dataloader,
        model_path="optuna_test",
        n_trials=50,
        max_epochs=50,
        gradient_clip_val_range=(0.01, 1.0),
        hidden_size_range=(8, 128),
        hidden_continuous_size_range=(8, 128),
        attention_head_size_range=(1, 4),
        learning_rate_range=(0.001, 0.1),
        dropout_range=(0.1, 0.3),
        trainer_kwargs=dict(limit_train_batches=30),
        reduce_on_plateau_patience=4,
        use_learning_rate_finder=False,  # use Optuna to find ideal learning rate or use in-built learning rate finder
    )

# ---- Cell ----
best_model_path = trainer.checkpoint_callback.best_model_path
best_tft = TemporalFusionTransformer.load_from_checkpoint(best_model_path)
actuals = torch.cat([y[0] for x, y in iter(val_dataloader)]).to(device)
predictions = best_tft.predict(val_dataloader, mode="prediction").to(device)
raw_predictions = best_tft.predict(val_dataloader, mode="raw", return_x=True)

sm = SMAPE()
print(f"Validation median SMAPE loss: {sm.loss(actuals, predictions).mean(axis = 1).median().item()}")

# ---- Cell ----
# for idx in range(raw_predictions.prediction.shape[0]):
for idx in range(raw_predictions.output.prediction.shape[0]):
    best_tft.plot_prediction(raw_predictions.x, raw_predictions.output, idx=idx, add_loss_to_title=True);

# ---- Cell ----
predictions= best_tft.predict(val_dataloader, return_x=True)
predictions_vs_actuals = best_tft.calculate_prediction_actual_by_variable(predictions.x, predictions.output)
all_features = list(set(predictions_vs_actuals['support'].keys())-set(['num_sold_lagged_by_365', 'num_sold_lagged_by_30', 'num_sold_lagged_by_7']))
for feature in all_features:
    best_tft.plot_prediction_actual_by_variable(predictions_vs_actuals, name=feature);

# ---- Cell ----

