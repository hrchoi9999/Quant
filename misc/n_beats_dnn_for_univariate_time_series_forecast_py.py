# English filename: n_beats_dnn_for_univariate_time_series_forecast_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/2. 최신딥러닝시계열모델/n-beats-dnn-for-univariate-time-series-forecast_clear.py
# Original filename: n-beats-dnn-for-univariate-time-series-forecast_clear.py

# ---- Cell ----
#!pip install tensorflow==2.13.0

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/kaggle_data/tabular-playground-series-sep-2022.zip&& unzip -n tabular-playground-series-sep-2022.zip

# ---- Cell ----
%pip install tensorflow-addons==0.22.0

# ---- Cell ----
## Parameters
data_config = {
    'train.csv': 'train.csv',
    'test.csv': 'test.csv',
    'sample_submission.csv': 'sample_submission.csv',
}

exp_config = {
    'competition_name': 'tps-sep-2022',
    'history_period': 60,  ## Lookback period (days)
    'horizon_period': 30,  ## Forecast period (days)
    'val_ratio': 0.2,  ## Train-vaild split ratio
    'batch_size': 512,
    'train_epochs': 10,
    'learning_rate': 5e-3,
    'gamma': 0.95,  ## parameter of learning scheduler
    'train_limit': True,  ## Use or not the data before 2020
    'checkpoint_filepath': './tmp/model/checkpoint.cpt',
    'finalize': True,  ## For the model finalization
    'finalize_epochs': 5,  ## None or int
    'finalized_filepath': './tmp/model/finalized.cpt',
}

model_config = {
    'emb_dim': 6,  ## categorical features' representation dim
    'n_blocks': 2,  ## number of N-BEATS blocks in a stack
    'n_stacks': 4,  ## number of N-BEATS stacks
    'width': 32,  ## hidden dim in N-BEATS
}

print('Parameters setted!')

# ---- Cell ----
## Import dependencies
import numpy as np
import pandas as pd
import scipy as sp
import matplotlib.pyplot as plt
%matplotlib inline

import seaborn as sns
import matplotlib.ticker as ticker
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import os, sys, pathlib, gc
import re, math, random, time
import datetime as dt
from tqdm import tqdm
from typing import Optional, Union, Tuple
from collections import OrderedDict

import sklearn
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler, OrdinalEncoder

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
## For reproducible results
def seed_all(s):
    random.seed(s)
    np.random.seed(s)
    tf.random.set_seed(s)
    torch.manual_seed(s)
    torch.cuda.manual_seed(s)
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms = True
    os.environ['TF_CUDNN_DETERMINISTIC'] = '1'
    os.environ['PYTHONHASHSEED'] = str(s)
    print('Seeds setted!')
global_seed = 42
seed_all(global_seed)


## Limit GPU Memory in TensorFlow
## Because TensorFlow, by default, allocates the full amount of available GPU memory when it is launched.
physical_devices = tf.config.list_physical_devices('GPU')
if len(physical_devices) > 0:
    for device in physical_devices:
        tf.config.experimental.set_memory_growth(device, True)
        print('{} memory growth: {}'\
              .format(device, tf.config.experimental.get_memory_growth(device)))
else:
    print("Not enough GPU hardware devices available")


## For Seaborn Setting
custom_params = {
    "axes.spines.right": False,
    "axes.spines.top": False,
    'grid.alpha': 0.3,
    'figure.figsize': (16, 6),
    'axes.titlesize': 'Large',
    'axes.labelsize': 'Large',
    'figure.facecolor': '#fdfcf6',
    'axes.facecolor': '#fdfcf6',
}
#cluster_colors = ['#b4d2b1', '#568f8b', '#1d4a60', '#cd7e59', '#ddb247', '#d15252']
sns.set_theme(
    style='whitegrid',
    #palette=sns.color_palette(cluster_colors),
    rc=custom_params,
)

# ---- Cell ----
## Data Loading
train_df = pd.read_csv(data_config['train.csv'])
test_df = pd.read_csv(data_config['test.csv'])
submission_df = pd.read_csv(data_config['sample_submission.csv'])

print(f'train_length: {len(train_df)}')
print(f'test_lenght: {len(test_df)}')
print(f'submission_length: {len(submission_df)}')

# ---- Cell ----
## Null Value Check
print('train_df.info()'); print(train_df.info(), '\n')
print('test_df.info()'); print(test_df.info(), '\n')

## train_df Check
train_df.head()

# ---- Cell ----
## Features and Targets
original_features = ['date', 'country', 'store', 'product']
target = 'num_sold'

## Number of unique values in each features.
n_unique_features = {feature: train_df[feature].nunique() for feature in original_features}
n_unique_features

# ---- Cell ----
## test_df Check
test_df.head()

# ---- Cell ----
## Statistics of num_sold
train_df['num_sold'].describe()

# ---- Cell ----
## num_sold of each product in each country
ax = sns.barplot(data=train_df, x='product', y='num_sold', hue='country')

# ---- Cell ----
## Total sells by Country
train_df['date'] = pd.to_datetime(train_df['date'])

ax = sns.lineplot(
    data=train_df.groupby([
        train_df.date.dt.strftime('%Y-%m'),
        train_df.country
    ])['num_sold'].sum().reset_index(),
    x='date',
    y='num_sold',
    hue='country',
)

ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=20))

# ---- Cell ----
## Distrubutions of num_sold
fig, ax = plt.subplots(12, 4, figsize=(25, 50))
ax = ax.flatten()

for i, (combination, df) in enumerate(train_df.groupby(['country', 'store', 'product'])):
    sns.histplot(df.num_sold, ax=ax[i])
    ax[i].set_title(' | '.join(combination))

plt.tight_layout()

# ---- Cell ----
## Datetime Feature Engineering
def date_feature_eng(df, date_column_name, drop=True):
    df[date_column_name] = pd.to_datetime(df[date_column_name])
    df['year'] = df[date_column_name].dt.year
    df['month'] = df[date_column_name].dt.month
    df['day'] = df[date_column_name].dt.day
    df['dayofweek'] = df[date_column_name].dt.dayofweek

    if drop:
        df = df.drop(date_column_name, axis=1)

    return df

## Create date-related features
train_df = date_feature_eng(train_df, 'date')
test_df = date_feature_eng(test_df, 'date')

## Use or not the data before 2020
if exp_config['train_limit']:
    train_df = train_df[train_df['year']==2020]
    train_df = train_df.reset_index(drop=True)

# ---- Cell ----
## Standardization of numerical featurs and target

## Only 'num_sold' is numerical in this data set
train_num_sold = train_df['num_sold'].values
train_num_sold = train_num_sold.reshape(-1, 1)

## Using sklearn.preprocessing.StandardScaler
sc = StandardScaler()
sc.fit(train_num_sold)
print('StandardScaler mean: ', sc.mean_)
print('StandardScaler scale: ', sc.scale_)

## Check
train_df['num_sold'] = sc.transform(train_num_sold)
train_df['num_sold'].describe()

# ---- Cell ----
## Making Lookup table of categorical featurs and target
numerical_columns = ['num_sold']
categorical_columns = ['country', 'store', 'product', 'month', 'day', 'dayofweek']
## I will not use 'year' as a categorical feature.
## Because there are no overlapping in 'year' feature between train and test data.
## It means that the model can't learn the embedding of year==2021.

## Using sklearn.preprocessing.OrdinalEncoder
oe = OrdinalEncoder(handle_unknown='error',
                    dtype=np.int64)
encoded = oe.fit_transform(train_df[categorical_columns].values)
#decoded = oe.inverse_transform(encoded)
train_df[categorical_columns] = encoded
test_df[categorical_columns] = oe.transform(test_df[categorical_columns].values)

## Check
encoder_categories = oe.categories_
encoder_categories

# ---- Cell ----
train_data = train_df.copy()

## Settings
n_country = 6
n_store = 2
n_product = 4
n_items = n_country * n_store * n_product ## 48
n_days = int(len(train_data) / n_items) ## 1461

history_period = exp_config['history_period']  ## Lookback period
horizon_period = exp_config['horizon_period']  ## Forecast period
before_start_idx = n_items * history_period
after_end_idx = n_items * horizon_period

## Helper Functions
def collect_past_data(idx, period, n_items) -> list:
    if idx < n_items * period:
        return []
    past_start_idx = idx - n_items * period
    past_data_ids = [i * n_items + past_start_idx for i in range(period)]
    return past_data_ids

def collect_future_data(idx, period, n_items) -> list:
    future_data_ids = [i * n_items + idx for i in range(period)]
    return future_data_ids

## Operation Check
a = 10000
b = collect_past_data(a, history_period, n_items)
c = collect_future_data(a, horizon_period, n_items)
print('index example: ', a, '\n')
print('history index: \n', b, '\n')
print('prediction index: \n', c, '\n')

# ---- Cell ----
## Dataset
class TPSSep22TrainDataset(torch.utils.data.Dataset):
    def __init__(self, df, numerical_columns,
                 categorical_columns,
                 history_period=30,
                 horizon_period=30,
                 n_items=48,
                 target=None):
        self.df = df
        self.numerical_columns = numerical_columns
        self.categorical_columns = categorical_columns
        self.history_period = history_period
        self.horizon_period = horizon_period
        self.n_items = n_items
        self.target = target
        self.before_start_idx = n_items * history_period
        self.after_end_idx = n_items * horizon_period

    def __len__(self):
        return (len(self.df) - self.before_start_idx - self.after_end_idx)

    def __getitem__(self, index):
        data = OrderedDict()
        index = index + self.before_start_idx

        data['row_id'] = self.df['row_id'][index]

        for nc in self.numerical_columns:
            past_data_ids = collect_past_data(
                index,
                self.history_period,
                self.n_items
            )
            x = torch.tensor(
                self.df[nc][past_data_ids].values,
                dtype=torch.float32
            )
            name = 'past_' + nc
            data[name] = x

        for cc in self.categorical_columns:
            x = torch.tensor(
                self.df[cc][index],
                dtype=torch.int32
            )
            x = torch.unsqueeze(x, dim=0)
            data[cc] = x

        if self.target is not None:
            if index + self.after_end_idx < len(self.df):
                future_data_ids = collect_future_data(
                    index,
                    self.horizon_period,
                    self.n_items
                )
                label = torch.tensor(
                    self.df[self.target][future_data_ids].values,
                    dtype=torch.float32
                )
            else:
                label = torch.tensor(
                    self.df[self.target][index],
                    dtype=torch.float32
                )
            return data, label
        else:
            return data

# ---- Cell ----
## train-valid split
if exp_config['train_limit']:
    val_ratio = 0.3
else:
    val_ratio = exp_config['val_ratio']

n_val = int((len(train_data) - before_start_idx - after_end_idx) / n_items * val_ratio) * n_items
n_train = len(train_data) - before_start_idx - after_end_idx - n_val
print(n_train, n_val)

train = train_data[:n_train + before_start_idx].reset_index(drop=True)
valid = train_data[-(n_val + after_end_idx):].reset_index(drop=True)
print(len(train), len(valid))

# ---- Cell ----
## Making Dataset
train_ds = TPSSep22TrainDataset(
    train,
    numerical_columns,
    categorical_columns,
    history_period,
    horizon_period,
    n_items,
    target
)

val_ds = TPSSep22TrainDataset(
    valid,
    numerical_columns,
    categorical_columns,
    history_period,
    horizon_period,
    n_items,
    target
)

## Operation Check
print('length of train_ds: ', len(train_ds))
print('length of val_ds: ', len(val_ds))
index = 0
sample = train_ds.__getitem__(index)
print('\n', sample)

# ---- Cell ----
## Making DataLoader
batch_size =exp_config['batch_size']

train_dl = torch.utils.data.DataLoader(
    train_ds,
    batch_size=batch_size,
    shuffle=False,
    drop_last=True
)

val_dl = torch.utils.data.DataLoader(
    val_ds,
    batch_size=batch_size,
    shuffle=False,
    drop_last=True
)

dl_dict = {'train': train_dl, 'val': val_dl}

## Operation Check
for dl_sample in (train_dl):
    break
x_sample = dl_sample[0]
y_sample = dl_sample[1]
print('input keys: ', x_sample.keys())
print('label shape: ', y_sample.shape)

# ---- Cell ----
class Preprocessor(nn.Module):
    def __init__(self, numerical_features,
                 categorical_features,
                 encoder_categories, emb_dim):
        super().__init__()
        self.numerical_features = numerical_features
        self.categorical_features = categorical_features
        self.encoder_categories = encoder_categories
        self.emb_dim = emb_dim
        self.embed_layers = nn.ModuleDict()

        for i, categorical in enumerate(categorical_features):
            embedding = nn.Embedding(num_embeddings=len(encoder_categories[i]),
                                     embedding_dim=self.emb_dim,)
            self.embed_layers[categorical] = embedding

    def forward(self, x):
        x_nums = []
        for numerical in self.numerical_features:
            x_num = x[numerical]
            x_nums.append(x_num)
        if len(x_nums) > 0:
            x_nums = torch.cat(x_nums, dim=1)
        else:
            x_nums = torch.tensor(x_nums, dtype=torch.float32)

        x_cats = []
        for categorical in self.categorical_features:
            x_cat = self.embed_layers[categorical](x[categorical])
            x_cats.append(x_cat)
        if len(x_cats) > 0:
            x_cats = torch.cat(x_cats, dim=1)
        else:
            x_cats = torch.tensor(x_cats, dtype=torch.float32)

        return x_nums, x_cats

# ---- Cell ----
class NBeatsBlock(nn.Module):
    def __init__(self, input_dim, output_dim, width):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, width)
        self.fc2 = nn.Linear(width, width)
        self.fc3 = nn.Linear(width, width)
        self.fc4 = nn.Linear(width, width)
        self.fc_b = nn.Linear(width, width, bias=False)
        self.fc_f = nn.Linear(width, width, bias=False)
        self.g_b = nn.Linear(width, input_dim)
        self.g_f = nn.Linear(width, output_dim)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = F.relu(self.fc4(x))

        theta_b = self.fc_b(x)
        theta_f = self.fc_f(x)

        backcast = self.g_b(theta_b)
        forecast = self.g_f(theta_f)

        return backcast, forecast

# ---- Cell ----
class NBeatsStack(nn.Module):
    def __init__(self, n_blocks, input_dim, output_dim, width):
        super().__init__()
        self.n_blocks = n_blocks
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.width = width

        self.blocks = nn.ModuleList()
        for _ in range(n_blocks):
            block = NBeatsBlock(input_dim, output_dim, width)
            self.blocks.append(block)

    def forward(self, x):
        stack_forecast = []
        for i in range(self.n_blocks):
            backcast, forecast = self.blocks[i](x)
            x = x - backcast
            stack_forecast.append(forecast)
        stack_forecast = torch.stack(stack_forecast, axis=-1)
        stack_forecast = torch.sum(stack_forecast, axis=-1)
        stack_residual = x
        return stack_residual, stack_forecast

# ---- Cell ----
class NBeatsModel(nn.Module):
    def __init__(self, n_blocks, n_stacks,
                 input_dim, output_dim, width):
        super().__init__()
        self.n_blocks = n_blocks
        self.n_stacks = n_stacks
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.width = width

        self.stacks = nn.ModuleList()
        for _ in range(n_stacks):
            stack = NBeatsStack(n_blocks, input_dim, output_dim, width)
            self.stacks.append(stack)

    def forward(self, x):
        global_forecast = []
        for i in range(self.n_stacks):
            stack_residual, stack_forecast = self.stacks[i](x)
            x = stack_residual
            global_forecast.append(stack_forecast)
        global_forecast = torch.stack(global_forecast, axis=-1)
        global_forecast = torch.sum(global_forecast, axis=-1)
        return global_forecast

# ---- Cell ----
## settings for models
emb_dim = model_config['emb_dim']
n_blocks = model_config['n_blocks']
n_stacks = model_config['n_stacks']
input_dim = exp_config['history_period']
output_dim = exp_config['horizon_period']
width = model_config['width']
num_epochs = exp_config['train_epochs']

numerical_features = ['past_num_sold']
categorical_features = ['country', 'store', 'product', 'month', 'day', 'dayofweek']

## Building Models
preprocessor = Preprocessor(
    numerical_features,
    categorical_features,
    encoder_categories,
    emb_dim
)

model = NBeatsModel(
    n_blocks,
    n_stacks,
    input_dim,
    output_dim,
    width
)

## Operation, Parameters and Model Structure Check
x_nums, x_cats = preprocessor(x_sample)
y = model(x_nums)
print('Input shape: ', x_nums.shape)
print('Output shape: ', y.shape)

print('# of Preprocessor parameters: ',\
      sum(p.numel() for p in preprocessor.parameters() if p.requires_grad))
print('# of N-BEATS parameters: ',\
      sum(p.numel() for p in model.parameters() if p.requires_grad))

model

# ---- Cell ----
## Loss Function
criterion = nn.MSELoss()

## Optimizer and Learning Rate Scheduler
learning_rate = exp_config['learning_rate']
gamma = exp_config['gamma']
steps_per_epoch = len(train) // batch_size

params = list(preprocessor.parameters()) + list(model.parameters())
optimizer = torch.optim.Adam(
    params=params,
    lr=learning_rate
)
#lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer=optimizer,
#                                                          T_max=num_epochs*steps_per_epoch)
lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(
    optimizer,
    gamma=gamma
)

# ---- Cell ----
## Model Save & Load
cpt_filepath = exp_config['checkpoint_filepath']

## Function for Saving Model
def model_save(model, preprocessor,
               optimizer, scheduler, path):
    directory = path.split('/')[:-1]
    directory = '/'.join(directory)
    os.makedirs(directory, exist_ok=True)

    ## When you use multi GPUs with DataParallel
    model_to_save = model.module if hasattr(model, "module") else model

    checkpoint = {
        "model": model_to_save.state_dict(),
        "preprocessor": preprocessor.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "random": random.getstate(),
        "np_random": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "torch_random": torch.random.get_rng_state(),
    }

    if torch.cuda.is_available():
        cuda_random_state = {
            "cuda_random": torch.cuda.get_rng_state(),
            "cuda_random_all": torch.cuda.get_rng_state_all(),
        }
        checkpoint.update(cuda_random_state)

    torch.save(checkpoint, path)
    print('Model saved!')


## Function for Loading Model
def model_load(model, preprocessor,
               optimizer, scheduler, path):
    checkpoint = torch.load(path, weights_only=False)

    ## When you use multi GPUs with DataParallel
    if hasattr(model, "module"):
        model.module.load_state_dict(checkpoint["model"])
    else:
        model.load_state_dict(checkpoint["model"])

    preprocessor.load_state_dict(checkpoint["preprocessor"])
    optimizer.load_state_dict(checkpoint["optimizer"])
    scheduler.load_state_dict(checkpoint["scheduler"])
    random.setstate(checkpoint["random"])
    np.random.set_state(checkpoint["np_random"])
    torch.set_rng_state(checkpoint["torch"])
    torch.random.set_rng_state(checkpoint["torch_random"])

    if torch.cuda.is_available():
        torch.cuda.set_rng_state(checkpoint["cuda_random"])
        torch.cuda.torch.cuda.set_rng_state_all(checkpoint["cuda_random_all"])

    print('Model loaded!')

# ---- Cell ----
## Function for the Model Training
def train_model(model, preprocessor, dl_dict,
                criterion, optimizer, lr_scheduler,
                num_epochs, cpt_filepath=None,
                finalize=False):

    ## Checking usability of GUP
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    print(f'device: {device}')
    print('-------Start Training-------')
    model.to(device)
    ## We use preprocessor on CPU

    ## training and validation loop
    if finalize:
        phases = ['train']
    else:
        phases = ['train', 'val']

    losses = {phase: [] for phase in phases}
    best_val_loss = 100.
    best_epoch = 1
    for epoch in range(num_epochs):
        for phase in phases:
            if phase == 'train':
                preprocessor.train()
                model.train()
            else:
                preprocessor.eval()
                model.eval()

            epoch_loss = 0.0

            for data, labels in tqdm(dl_dict[phase]):
                x_nums, x_cats = preprocessor(data)

                x_nums = x_nums.to(device)
                labels = labels.to(device)

                ## Optimizer Initialization
                optimizer.zero_grad()

                ## Forward Processing
                with torch.set_grad_enabled(phase=='train'):
                    outputs = model(x_nums)
                    loss = criterion(outputs, labels)

                    ## Backward Processing and Optimization
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()
                        lr_scheduler.step()

                    epoch_loss += loss.item() * x_nums.size(0)

            epoch_loss = epoch_loss / len(dl_dict[phase].dataset)
            losses[phase].append(epoch_loss)

            ## Saving the best Model
            if phase == 'val':
                if cpt_filepath is not None:
                    if epoch_loss < best_val_loss:
                        best_epoch = epoch + 1
                        best_val_loss = epoch_loss
                        model_save(
                            model, preprocessor,
                            optimizer, lr_scheduler,
                            cpt_filepath
                        )

            ## Displaying results
            print('Epoch {}/{} | {:^5} |  Loss: {:.4f}'.format(epoch+1, num_epochs, phase, epoch_loss ))

    if finalize:
    ## Saving finalized Model
        if cpt_filepath is not None:
            model_save(
                model, preprocessor,
                optimizer, lr_scheduler,
                cpt_filepath
            )

    return model, preprocessor, losses, best_epoch

# ---- Cell ----
## Function for Plotting Losses
def plot_losses(losses, title=None):
    plt.figure(figsize=(7, 5))
    losses = pd.DataFrame(losses)
    losses.index = [i+1 for i in range(len(losses))]
    ax = sns.lineplot(data=losses)
    ax.set_xlabel('Epoch')
    ax.set_ylabel('Loss')
    ax.legend()
    ax.set_title(title)

# ---- Cell ----
## Training
num_epochs = exp_config['train_epochs']
cpt_filepath = exp_config['checkpoint_filepath']

model, preprocessor, losses, best_epoch = train_model(
    model,
    preprocessor,
    dl_dict,
    criterion,
    optimizer,
    lr_scheduler,
    num_epochs,
    cpt_filepath
)

## Load the Best Model
model_load(
    model,
    preprocessor,
    optimizer,
    lr_scheduler,
    cpt_filepath,
)

## Plot Losses
plot_losses(losses)

# ---- Cell ----
## Finalizing
if exp_config['finalize']:

    ## Setting Finalize Epochs
    if exp_config['finalize_epochs'] is not None:
        num_epochs = exp_config['finalize_epochs']
    else:
        num_epochs = best_epoch

    ## Making Dataset and DataLoader for Finalizing
    train_all_ds = TPSSep22TrainDataset(
        train_data,
        numerical_columns,
        categorical_columns,
        history_period,
        horizon_period,
        n_items,
        target
    )

    train_all_dl = torch.utils.data.DataLoader(
        train_all_ds,
        batch_size=batch_size,
        shuffle=False,
        drop_last=True
    )

    finalize_dl_dict = {'train': train_all_dl}

    ## Building Models
    preprocessor = Preprocessor(
        numerical_features,
        categorical_features,
        encoder_categories,
        emb_dim
    )

    model = NBeatsModel(
        n_blocks,
        n_stacks,
        input_dim,
        output_dim,
        width
    )

    ## Loss Function
    criterion = nn.MSELoss()

    ## Optimizer and Learning Rate Scheduler
    learning_rate = exp_config['learning_rate']
    gamma = exp_config['gamma']
    params = list(preprocessor.parameters()) + list(model.parameters())
    optimizer = torch.optim.Adam(
        params=params,
        lr=learning_rate
    )
    lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(
        optimizer,
        gamma=gamma
    )

    ## Model Training
    finalized_filepath = exp_config['finalized_filepath']

    model, preprocessor, losses, _ = train_model(
        model,
        preprocessor,
        finalize_dl_dict,
        criterion,
        optimizer,
        lr_scheduler,
        num_epochs,
        finalized_filepath,
        finalize=True
    )

    ## Plot losses
    plot_losses(losses)

# ---- Cell ----
## Dataset for Test Data
class TPSSep22TestDataset(torch.utils.data.Dataset):
    def __init__(self, test_df, train_df,
                 numerical_columns,
                 categorical_columns,
                 history_period=30,
                 horizon_period=30,
                 n_items=48):
        self.train_df = train_df
        self.numerical_columns = numerical_columns
        self.categorical_columns = categorical_columns
        self.history_period = history_period
        self.horizon_period = horizon_period
        self.n_items = n_items
        self.before_start_idx = n_items * history_period
        self.after_end_idx = n_items * horizon_period

        last_train_data = self.train_df.iloc[-self.before_start_idx:]
        self.test_df = pd.concat([last_train_data, test_df], axis=0, ignore_index=True)

    def __len__(self):
        return (len(self.test_df) - self.before_start_idx) // self.after_end_idx + 1

    def __getitem__(self, index):
        data = {}
        index = (index * self.after_end_idx + self.before_start_idx)

        for i in range(self.n_items):
            item_index = index + i
            data[str(i)] = {}
            data[str(i)]['row_id'] = item_index

            past_data_ids = collect_past_data(item_index,
                                              self.history_period,
                                              self.n_items)
            x = torch.tensor(self.test_df['num_sold'][past_data_ids].values,
                             dtype=torch.float32)
            data[str(i)]['history'] = x

        return data

    def update(self, new_data, column, row_id):
        row_ids = collect_future_data(row_id,
                                      self.horizon_period,
                                      self.n_items)
        max_id = self.test_df.iloc[-1]['row_id']
        if row_ids[-1] <= max_id:
            self.test_df.loc[self.test_df['row_id'].isin(row_ids), column] = new_data
        else:
            row_ids = np.array(row_ids)
            max_len = (row_ids <= max_id).sum()
            row_ids = row_ids[:max_len]

            row_ids = row_ids.tolist()
            new_data = new_data[:max_len]
            self.test_df.loc[self.test_df['row_id'].isin(row_ids), column] = new_data

# ---- Cell ----
## Making Test Dataset
test_data = test_df.copy()
test_ds = TPSSep22TestDataset(
    test_data,
    train_data,
    numerical_columns,
    categorical_columns,
    history_period,
    horizon_period,
    n_items
)

## Making Test DataLoader
test_dl = torch.utils.data.DataLoader(
    test_ds,
    batch_size=1,
    shuffle=False,
    drop_last=False
)

## Operation Check
print('length of test_ds: ', len(test_ds), '\n')
index = 0
test_sample = test_ds.__getitem__(index)
print('number of keys in test data: ', len(test_sample.keys()))
for key in test_sample.keys():
    print('row_id sample: ', test_sample[key]['row_id'])
    print('history sample shape: ', test_sample[key]['history'].shape)
    break

# ---- Cell ----
## Function for the Test Data Prediction
def model_predict(model, preprocessor, test_dl):

    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    print(f'device: {device}')
    print('-------Start Prediction-------')
    model.to(device)

    preprocessor.eval()
    model.eval()

    for data_set in tqdm(test_dl):
        for i in range(n_items):
            data = data_set[str(i)]
            row_id = data['row_id'].item()
            row_id = row_id + test_dl.dataset.test_df['row_id'][0]
            x_nums = data['history']
            x_nums = x_nums.to(device)

            with torch.no_grad():
                outputs = model(x_nums)
                outputs = torch.squeeze(outputs)
                outputs = outputs.to('cpu').detach().numpy().copy()

            test_dl.dataset.update(outputs, 'num_sold', row_id)

    outputs = test_dl.dataset.test_df['num_sold']
    return outputs

# ---- Cell ----
## Prediction
outputs = model_predict(model, preprocessor, test_dl)
preds_normed = outputs.iloc[test_dl.dataset.before_start_idx:]

## post-processing
preds = (preds_normed * sc.scale_) + sc.mean_
submission_df['num_sold'] = preds.values
submission_df.to_csv('submission_cv.csv', index=False)

## Check
print('The number of null values: \n', submission_df.isnull().sum())
submission_df.head(10)
