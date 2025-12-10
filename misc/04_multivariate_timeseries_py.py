# English filename: 04_multivariate_timeseries_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/14일차 딥러닝 시계열의 이해_한국주식실습/2. RNN과 LSTM_고급실습/04_multivariate_timeseries_clear.py
# Original filename: 04_multivariate_timeseries_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/machine_learning_for_trading_2307/19_recurrent_neural_nets/data.zip&&unzip -n data.zip

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

from pathlib import Path
import numpy as np
import pandas as pd
import pandas_datareader.data as web

from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import minmax_scale

import tensorflow as tf
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping
from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.layers import Dense, LSTM
import tensorflow.keras.backend as K

import matplotlib.pyplot as plt
import seaborn as sns

# ---- Cell ----
gpu_devices = tf.config.experimental.list_physical_devices('GPU')
if gpu_devices:
    print('Using GPU')
    tf.config.experimental.set_memory_growth(gpu_devices[0], True)
else:
    print('Using CPU')

# ---- Cell ----
sns.set_style('whitegrid')
np.random.seed(42)

# ---- Cell ----
results_path = Path('results', 'multivariate_time_series')
if not results_path.exists():
    results_path.mkdir(parents=True)

# ---- Cell ----
df = web.DataReader(['UMCSENT', 'IPGMFN'], 'fred', '1980', '2019-12').dropna()
df.columns = ['sentiment', 'ip']
df.info()

# ---- Cell ----
df.head()

# ---- Cell ----
df_transformed = (pd.DataFrame({'ip': np.log(df.ip).diff(12),
                                'sentiment': df.sentiment.diff(12)})
                  .dropna())

# ---- Cell ----
df_transformed = df_transformed.apply(minmax_scale)

# ---- Cell ----
fig, axes = plt.subplots(ncols=2, figsize=(14,4))
columns={'ip': 'Industrial Production', 'sentiment': 'Sentiment'}
df.rename(columns=columns).plot(ax=axes[0], title='Original Series')
df_transformed.rename(columns=columns).plot(ax=axes[1], title='Transformed Series')
sns.despine()
fig.tight_layout()
fig.savefig(results_path / 'multi_rnn', dpi=300)

# ---- Cell ----
df.values.reshape(-1, 12, 2).shape

# ---- Cell ----
def create_multivariate_rnn_data(data, window_size):
    y = data[window_size:]
    n = data.shape[0]
    X = np.stack([data[i: j]
                  for i, j in enumerate(range(window_size, n))], axis=0)
    return X, y

# ---- Cell ----
window_size = 18

# ---- Cell ----
X, y = create_multivariate_rnn_data(df_transformed, window_size=window_size)

# ---- Cell ----
X.shape, y.shape

# ---- Cell ----
df_transformed.head()

# ---- Cell ----
test_size =24
train_size = X.shape[0]-test_size

# ---- Cell ----
X_train, y_train = X[:train_size], y[:train_size]
X_test, y_test = X[train_size:], y[train_size:]

# ---- Cell ----
X_train.shape, X_test.shape

# ---- Cell ----
K.clear_session()

# ---- Cell ----
n_features = output_size = 2

# ---- Cell ----
lstm_units = 12
dense_units = 6

# ---- Cell ----
rnn = Sequential([
    LSTM(units=lstm_units,
         dropout=.1,
         recurrent_dropout=.1,
         input_shape=(window_size, n_features), name='LSTM',
         return_sequences=False),
    Dense(dense_units, name='FC'),
    Dense(output_size, name='Output')
])

# ---- Cell ----
rnn.summary()

# ---- Cell ----
rnn.compile(loss='mae', optimizer='RMSProp')

# ---- Cell ----
lstm_path = (results_path / 'lstm.keras').as_posix()

checkpointer = ModelCheckpoint(filepath=lstm_path,
                               verbose=1,
                               monitor='val_loss',
                               mode='min',
                               save_best_only=True)

# ---- Cell ----
early_stopping = EarlyStopping(monitor='val_loss',
                              patience=10,
                              restore_best_weights=True)

# ---- Cell ----
result = rnn.fit(X_train,
                 y_train,
                 epochs=20,
                 batch_size=20,
                 shuffle=False,
                 validation_data=(X_test, y_test),
                 callbacks=[early_stopping, checkpointer],
                 verbose=1)

# ---- Cell ----
pd.DataFrame(result.history).plot();

# ---- Cell ----
y_pred = pd.DataFrame(rnn.predict(X_test),
                      columns=y_test.columns,
                      index=y_test.index)
y_pred.info()

# ---- Cell ----
test_mae = mean_absolute_error(y_pred, y_test)

# ---- Cell ----
print(test_mae)

# ---- Cell ----
y_test.index

# ---- Cell ----
fig, axes = plt.subplots(ncols=3, figsize=(17, 4))
pd.DataFrame(result.history).rename(columns={'loss': 'Training',
                                              'val_loss': 'Validation'}).plot(ax=axes[0], title='Train & Validation Error')
axes[0].set_xlabel('Epoch')
axes[0].set_ylabel('MAE')
col_dict = {'ip': 'Industrial Production', 'sentiment': 'Sentiment'}

for i, col in enumerate(y_test.columns, 1):
    y_train.loc['2010':, col].plot(ax=axes[i], label='training', title=col_dict[col])
    y_test[col].plot(ax=axes[i], label='out-of-sample')
    y_pred[col].plot(ax=axes[i], label='prediction')
    axes[i].set_xlabel('')

axes[1].set_ylim(.5, .9)
axes[1].fill_between(x=y_test.index, y1=0.5, y2=0.9, color='grey', alpha=.5)

axes[2].set_ylim(.3, .9)
axes[2].fill_between(x=y_test.index, y1=0.3, y2=0.9, color='grey', alpha=.5)

plt.legend()
fig.suptitle('Multivariate RNN - Results | Test MAE = {:.4f}'.format(test_mae), fontsize=14)
sns.despine()
fig.tight_layout()
fig.subplots_adjust(top=.85)
fig.savefig(results_path / 'multivariate_results', dpi=300);
