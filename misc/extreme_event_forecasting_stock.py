# English filename: extreme_event_forecasting_stock_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/1. 금융시계열_LSTM과Atttention/1. LSTM/Extreme_Event_Forecasting_Stock_실습.py
# Original filename: Extreme_Event_Forecasting_Stock_실습.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_pytorch/data.zip&& unzip -n data.zip

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')

# ---- Cell ----
%matplotlib inline

# ---- Cell ----
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tqdm
import tensorflow as tf
from tensorflow import keras

from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_log_error, mean_absolute_error

from tensorflow.keras.models import *
from tensorflow.keras.layers import *
from keras.layers import Lambda
from tensorflow.keras import backend as K

# ---- Cell ----
### 데이터셋 읽기 ###
df = pd.read_csv('data/S_P500IndexData-Table1.csv', sep=';')
print(df.shape)
df.head()

# ---- Cell ----
### 그래프 그리기
def plot_seris():
    plt.figure(figsize=(9,6))
    reg_train = df[df['Ntime']<20160000]
    p_train = reg_train[['Ntime', 'Close Price']].reset_index(drop=True)
    plt.plot(range(0,len(p_train)),p_train['Close Price'].values)

    reg_test = df[df['Ntime']>20160000]
    p_test = reg_test[['Ntime', 'Close Price']].reset_index(drop=True)
    plt.plot(range(len(p_train),len(p_train)+len(p_test)),p_test['Close Price'].values)
    plt.title('Close Price') #+' '+typ.upper()+' '+county)
    plt.show()

# ---- Cell ----
plot_seris()

# ---- Cell ----
### LSTM 윈도우와 레이블을 만드는 GENERATOR 함수 작성 ###
sequence_length = 4

def gen_sequence(id_df, seq_length, seq_cols):

    data_matrix = id_df[seq_cols].values
    num_elements = data_matrix.shape[0]

    for start, stop in zip(range(0, num_elements-seq_length), range(seq_length, num_elements)):
        yield data_matrix[start:stop, :]

def gen_labels(id_df, seq_length, label):

    data_matrix = id_df[label].values
    num_elements = data_matrix.shape[0]

    return data_matrix[seq_length:num_elements, :]

# ---- Cell ----
### 훈련/테스트셋 (X) 작성 ###
X_train = []
X_test = []

for sequence in gen_sequence(df[df["Ntime"] <20160000], sequence_length, ['Close Price']):
    X_train.append(sequence)

for sequence in gen_sequence(df[df["Ntime"]>20160000], sequence_length, ['Close Price']):
    X_test.append(sequence)

X_train = np.asarray(X_train)
X_test = np.asarray(X_test)

# ---- Cell ----
### 훈련/테스트셋 레이블 (y) 작성 ###
y_train = []
y_test = []

for sequence in gen_labels(df[df["Ntime"] <20160000], sequence_length, ['Close Price']):
    y_train.append(sequence)

for sequence in gen_labels(df[df["Ntime"]>20160000], sequence_length, ['Close Price']):
    y_test.append(sequence)

y_train = np.asarray(y_train)
y_test = np.asarray(y_test)

# ---- Cell ----
### 훈련/테스트 데이터와 레이블 결합(CONCATENATE) ###
X = np.concatenate([X_train,X_test],axis=0)
y = np.concatenate([y_train,y_test],axis=0)

print(X.shape,y.shape)

# ---- Cell ----
df.columns

# ---- Cell ----
### 훈련/테스트 외생 특성셋 작성 ###
col = ['Volume', 'MACD', 'CCI', 'ATR', 'BOLL', 'EMA20', 'MA10', 'MTM6', 'MA5',
       'MTM12', 'ROC', 'SMI', 'WVAD', 'US Dollar Index', 'Federal Fund Rate']
f_train= []
f_test = []

for sequence in gen_sequence(df[df["Ntime"]<20160000], sequence_length, col):
    f_train.append(sequence)

for sequence in gen_sequence(df[df["Ntime"]>20160000], sequence_length, col):
    f_test.append(sequence)

f_train = np.asarray(f_train)
f_tes = np.asarray(f_test)

# ---- Cell ----
### 훈련/테스트셋 외생 특성 결합 ###
F = np.concatenate([f_train,f_test],axis=0)

print(F.shape)

# ---- Cell ----
### LSTM 오토인코더 정의 ###
inputs_ae = Input(shape=(sequence_length, 1))
encoded_ae = LSTM(128, return_sequences=True, dropout=0.3)(inputs_ae, training=True)
decoded_ae = LSTM(32, return_sequences=True, dropout=0.3)(encoded_ae, training=True)
out_ae = TimeDistributed(Dense(1))(decoded_ae)

sequence_autoencoder = Model(inputs_ae, out_ae)
sequence_autoencoder.compile(optimizer='adam', loss='mse', metrics=['mse'])
sequence_autoencoder.summary()

# ---- Cell ----
### 오코인코더 학습 ###
sequence_autoencoder.fit(X[:X_train.shape[0]],
                         X[:X_train.shape[0]], batch_size=16, epochs=20, verbose=2, shuffle=True)

# ---- Cell ----
### 가격을 인코드하고 외생 특성과 결합 ###
encoder = Model(inputs_ae, encoded_ae)
XX = encoder.predict(X)
XXF = np.concatenate([XX, F], axis=2)
XXF.shape

# ---- Cell ----
print(X.shape)
print(XX.shape)
print(F.shape)

# ---- Cell ----
### 훈련-테스트 분리 ###
X_train1, X_test1 = XXF[:X_train.shape[0]], XXF[X_train.shape[0]:]
y_train1, y_test1 = y[:y_train.shape[0]], y[y_train.shape[0]:]

# ---- Cell ----
print(X_train1.shape)
print(X_test1.shape)

# ---- Cell ----
### 데이터 스케일링 ###
scaler1 = StandardScaler()
X_train1 = scaler1.fit_transform(X_train1.reshape(-1,143)).reshape(-1,sequence_length,143)
X_test1 = scaler1.transform(X_test1.reshape(-1,143)).reshape(-1,sequence_length,143)

# ---- Cell ----
### 훈련-테스트셋 분리 ###
inputs1 = Input(shape=(X_train1.shape[1], X_train1.shape[2]))
lstm1 = LSTM(128, return_sequences=True, dropout=0.3)(inputs1, training=True)
lstm1 = LSTM(32, return_sequences=False, dropout=0.3)(lstm1, training=True)
dense1 = Dense(50)(lstm1)
out1 = Dense(1)(dense1)

model1 = Model(inputs1, out1)

model1.compile(loss='mse', optimizer='adam', metrics=['mse'])

# ---- Cell ----
### 예측 적합화 ###
# 시간을 위해 50번만 설정
history = model1.fit(X_train1, y_train1, epochs=50, batch_size=128, verbose=2, shuffle=True)

# ---- Cell ----
pred=model1.predict(X_test1)

# ---- Cell ----
np.sqrt(np.mean((pred-y_test1)**2))

# ---- Cell ----
### 특성 결합 ###
XF = np.concatenate([X, F], axis=2)
print(XF.shape)

# ---- Cell ----
### 훈련-테스트 분리 ###
X_train2, X_test2 = XF[:X_train.shape[0]], XF[X_train.shape[0]:]
y_train2, y_test2 = y[:y_train.shape[0]], y[y_train.shape[0]:]

# ---- Cell ----
print(X_train2.shape)
print(X_test2.shape)

# ---- Cell ----
### 데이터 스케일링 ###
scaler2 = StandardScaler()
X_train2 = scaler2.fit_transform(X_train2.reshape(-1,16)).reshape(-1,sequence_length,16)
X_test2 = scaler2.transform(X_test2.reshape(-1,16)).reshape(-1,sequence_length,16)

# ---- Cell ----
### LSTM 예측모델 정의 ###
inputs2 = Input(shape=(X_train2.shape[1], X_train2.shape[2]))
lstm2 = LSTM(128, return_sequences=True, dropout=0.3)(inputs2, training=True)
lstm2 = LSTM(32, return_sequences=False, dropout=0.3)(lstm2, training=True)
dense2 = Dense(50)(lstm2)
out2 = Dense(1)(dense2)

model2 = Model(inputs2, out2)

model2.compile(loss='mse', optimizer='adam', metrics=['mse'])

# ---- Cell ----
### 예측 모델 적합화 ###
history = model2.fit(X_train2, y_train2, epochs=100, batch_size=128, verbose=2, shuffle=True)

# ---- Cell ----
pred=model2.predict(X_test2)

# ---- Cell ----
np.sqrt(np.mean((pred-y_test2)**2))

# ---- Cell ----

