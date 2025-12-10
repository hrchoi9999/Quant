# English filename: predict_kospi200실습_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/14일차 딥러닝 시계열의 이해_한국주식실습/2. RNN과 LSTM_고급실습/Predict_KOSPI200실습_clear.py
# Original filename: Predict_KOSPI200실습_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/base_deep_learning_data/stock_data_df_full.csv
!wget -nc http://youngminhome.iptime.org:5555/shared/base_deep_learning_data/stock_data_2022-08-24.csv

# ---- Cell ----
import requests
import json
import pandas as pd
import datetime as datetime
from dateutil.parser import parse
import sys
import numpy as np
import matplotlib.pyplot as plt
from pandas.plotting import register_matplotlib_converters

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.layers import Bidirectional, BatchNormalization
from tensorflow.keras.layers import LSTM, Dense, Dropout,AdditiveAttention

from sklearn.preprocessing import MinMaxScaler

# ---- Cell ----
# def url_per_page(page_no):
#     url=f'https://finance.daum.net/api/market_index/days?page={page_no}&perPage=10&market=KOSPI_200&pagination=true'
#     return url

# ---- Cell ----
# stock_data=[]
# custom_header={'referer':'https://finance.daum.net/domestic/kospi200',
#               'user-agent':'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'}

# for page_no in range(1,101):      # 100번째 페이지까지 다운로드, 이유는 100번째 페이지 이전 자료부터 개인,기관,외인 투자 비율이 없음
#     req=requests.get(url_per_page(page_no), headers=custom_header)
#     if req.status_code==requests.codes.ok:
#         stock_data_temp=json.loads(req.text)
#         stock_data.append(stock_data_temp['data'])
#     else:
#         print('connection failed')

# ---- Cell ----
# stock_data_df=pd.DataFrame(stock_data[0])

# for data in stock_data[1:]:
#     stock_data_df=stock_data_df.append(pd.DataFrame(data), ignore_index=True)

# ---- Cell ----
# stock_data_df.to_csv('stock_data_df_full.csv')
stock_data_df=pd.read_csv('stock_data_df_full.csv', index_col=0)
stock_data_df.head()

# ---- Cell ----
stock_data_df.drop(list(range(995,1000)),inplace=True)
stock_data_df.drop([0],inplace=True)
stock_data_df.drop(['change','changePrice','accTradeVolume','accTradePrice'],axis=1,inplace=True)
# stock_data_df.set_index('date',inplace=True)
stock_data_df.sort_values(by='date',inplace=True)
stock_data_df.columns=['date','tp','indi','fore','inst']
stock_data_df.reset_index(drop=True,inplace=True)
## tp= traed price, indi=individual straight purchase price, fore=foreigner straight purchase price, inst= institution straight purchase price

# ---- Cell ----
stock_data_df

# ---- Cell ----
# stock_data_df.to_csv(f'stock_data_{str(datetime.datetime.now().date())}')

# ---- Cell ----
stock_data_df=pd.read_csv('stock_data_2022-08-24.csv', index_col=0)
stock_data_df.head()

# ---- Cell ----

lookback_step=10  # 학습할 과거의 데이터
predict_step=3  # 현시점부터 예측할 날짜까지의 거리

max_epoch=50
node=50
batch_size=3
dropout=0.1

test_data_ratio=0.1
validation_split=0.2
validation_freq=1

sets=list(stock_data_df.columns)[1:]

num_variables=len(sets)

date=[]
for d in stock_data_df.date:
    date.append(parse(d).date())


# ---- Cell ----
num_variables

# ---- Cell ----
sc=MinMaxScaler(feature_range=(0,1))
sc.fit(stock_data_df.iloc[:,1:])
input_data=sc.transform(stock_data_df.iloc[:,1:])

# ---- Cell ----
x=[]
y=[]
for i in range(len(input_data)-lookback_step-1):
    x.append(list(input_data[i:i+lookback_step,:]))
    y.append(input_data[i+lookback_step,:])

x=np.array(x)
y=np.array(y)

# ---- Cell ----
print(x.shape,y.shape)

# ---- Cell ----
train_end_index=int((1-test_data_ratio)*len(x))

x_train=x[:train_end_index]
y_train=y[:train_end_index]


# ---- Cell ----
train_end_index

# ---- Cell ----
x[train_end_index]  # (10,4)

# ---- Cell ----
# layer=keras.Input(shape=(lookback_step,num_variables))

# # 다음 model.summary 결과를 보고 모델을 완성해 보라
# # attention layer를 넣고 싶으면 은 다음을 참고하라 (https://runebook.dev/ko/docs/tensorflow/keras/layers/additiveattention)
# layer = AdditiveAttention(use_scale=True, causal=True)([layer,layer])

# output=Dense(units=num_variables)(layer)

# model=keras.models.Model(inputs=input,outputs=output)

# model.summary()

# ---- Cell ----
(lookback_step, num_variables)

# ---- Cell ----
input=keras.Input(shape=(lookback_step,num_variables))

layer=Bidirectional(LSTM(units=node, return_sequences=True))(input)
layer = BatchNormalization()(layer)
layer = Dropout(dropout)(layer)
layer = Bidirectional(LSTM(units=node, return_sequences = True))(layer)
layer = BatchNormalization()(layer)
layer = Dropout(dropout)(layer)
layer = Bidirectional(LSTM(units=node, return_sequences = True))(layer)
layer = BatchNormalization()(layer)
layer = AdditiveAttention(use_scale=True)([layer,layer], use_causal_mask=True) #https://www.tensorflow.org/api_docs/python/tf/keras/layers/AdditiveAttention
layer = Bidirectional(LSTM(units=node))(layer)

output=Dense(units=num_variables)(layer)

model=keras.models.Model(inputs=input,outputs=output)

model.summary()

# ---- Cell ----
model.compile(optimizer=keras.optimizers.Adam(0.01), loss='mse')

callbacks = [keras.callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, min_delta=0.00001, patience=10, verbose=1),
             keras.callbacks.EarlyStopping(monitor='val_loss', min_delta=0.00001, patience=30, verbose=1)]

# ---- Cell ----
print("x_train shape:", x_train.shape)
print("y_train shape:", y_train.shape)

# ---- Cell ----
# batch_size=1

# ---- Cell ----
validation_split

# ---- Cell ----
# model.fit(x_train,y_train, epochs=max_epoch, batch_size=batch_size,verbose=2,callbacks=callbacks, validation_split=validation_split)
model.fit(x_train,y_train, epochs=max_epoch, batch_size=batch_size,verbose=2,callbacks=callbacks, validation_split=validation_split)
#         validation_freq=validation_freq)
print('training is done')

# ---- Cell ----
input_data=sc.inverse_transform(input_data)

# ---- Cell ----
input_data[1]

# ---- Cell ----
x_test=x[train_end_index]
x_test=x_test.reshape(1, lookback_step, num_variables)

# ---- Cell ----
## 예측값으로 재 예측

predicted_values=[]
predicted_date=[]

for i in range(len(x)-train_end_index):
    predicted_temp=model.predict(x_test)
    predicted_values.append(predicted_temp)

    predicted_temp=predicted_temp.reshape(1, 1, num_variables)
    x_test=np.delete(x_test, 0, axis=1)
    x_test=np.append(x_test, predicted_temp, axis=1)

    predicted_date.append(date[train_end_index+lookback_step+i])

predicted_values=np.array(predicted_values).squeeze()
predicted_values=sc.inverse_transform(predicted_values)

print(f'predicted date period :{predicted_date[0]}~{predicted_date[-1]} ')

# ---- Cell ----
print(predicted_temp.shape)


# ---- Cell ----
register_matplotlib_converters()
plt.figure(figsize=(14,7))
plt.plot(date[train_end_index:],input_data[train_end_index:,0], color='green')
plt.plot(predicted_date,predicted_values[:,0], color= 'red')

# ---- Cell ----
x_test=x[train_end_index]
x_test=x_test.reshape(1, lookback_step, num_variables)

# ---- Cell ----
predicted_values=[]
predicted_date=[]

for i in range(len(x)-train_end_index):
    x_test=x[train_end_index+i]
    x_test=x_test.reshape(1, lookback_step, num_variables)

    predicted_temp=model.predict(x_test)
    predicted_values.append(predicted_temp)

    predicted_date.append(date[train_end_index+lookback_step+i])

predicted_values=np.array(predicted_values).squeeze()
predicted_values=sc.inverse_transform(predicted_values)

# ---- Cell ----
register_matplotlib_converters()
plt.figure(figsize=(14,7))
plt.plot(date[train_end_index:],input_data[train_end_index:,0], color='green')
plt.plot(predicted_date,predicted_values[:,0], color= 'red')

# ---- Cell ----
## 내일 예측한 값이 당일 종가보다 높으면 사서, 예측했던 날짜에 무조건 팔았을때의 수익률

asset=100000000
profit=0
purchased_stock_list=[]
purchased_stock_date_list=[]
profit_list=[]

for i in range(len(predicted_date)):
    if predicted_values[i,0]>input_data[train_end_index+lookback_step+i,0]:
        purchased_stock_list.append(input_data[train_end_index+lookback_step+i,0])
        purchased_stock_date_list.append(predicted_date[i])
        profit_list.append(input_data[train_end_index+lookback_step+i+1,0]-input_data[train_end_index+lookback_step+i,0])

asset+=sum(profit_list)*100000


print(f'투자기간: {predicted_date[0]}~{predicted_date[-1]} ')
print('매입단가:', format(sum(purchased_stock_list)/len(purchased_stock_list),','))
print('현재가:', format(input_data[-1,0],','))
print('매매손익:', format(sum(profit_list)*100000,","))
print('현재 총 자산:',format(asset,','))
print('자산 증가율:', format((asset-100000000)/100000000,'.3'))
print('코스피 증가율:', format(input_data[-1,0]/input_data[train_end_index,0],'.3f'))

# ---- Cell ----
## predict_step 만큼 뒤에 예측한 값이 당일 종가보다 높으면 사놓고 샀을때 가격보다 오른 경우만 팔았을때의 수익률

asset=100000000
profit=0
purchased_stock_list=[]
purchased_stock_date_list=[]
profit_list=[]



for i in range(len(predicted_date)):
    if predicted_values[i,0]>input_data[train_end_index+lookback_step+i,0]:
        purchased_stock_list.append(input_data[train_end_index+lookback_step+i,0])
        purchased_stock_date_list.append(predicted_date[i])
        asset-=purchased_stock_list[-1]*100000

    purchased_stock_list_temp=[]+purchased_stock_list

    for j in purchased_stock_list:
        if j<input_data[train_end_index+lookback_step+i,0]:
            profit_list.append(input_data[train_end_index+lookback_step+i,0]-j)
            purchased_stock_list_temp.remove(j)
            asset+=profit_list[-1]*100000
            asset+=j*100000

    purchased_stock_list=[]+purchased_stock_list_temp

asset+=len(purchased_stock_list)*input_data[-1,0]*100000

print(f'투자기간: {predicted_date[0]}~{predicted_date[-1]} ')
print('매입단가:', format(sum(purchased_stock_list)/len(purchased_stock_list),','))
print('현재가:', format(input_data[-1,0],','))
print('매입금액:', format(sum(purchased_stock_list)*100000,','))
print('평가금액:', format(len(purchased_stock_list)*input_data[-1,0]*100000,','))
print('평가손익 :', format(len(purchased_stock_list)*input_data[-1,0]*100000-sum(purchased_stock_list)*100000,','))
print('평가손익률 :' ,format((len(purchased_stock_list)*input_data[-1,0]-sum(purchased_stock_list))/sum(purchased_stock_list),'.2f'))
print('매매손익:', format(sum(profit_list)*100000,","))
print('현재 총 자산:',format(asset,','))
print('자산 증가율:', format((asset-100000000)/100000000,'.3'))
print('코스피 증가율:', format(input_data[-1,0]/input_data[train_end_index,0],'.3f'))

# ---- Cell ----
len(x)-train_end_index-predict_step

# ---- Cell ----
# predict_step=3  예측하기 위한 3일간만 예측값으로 대체.

predicted_values=[]
predicted_date=[]


for i in range(len(x)-train_end_index-predict_step):
    predicted_values_temp=[]
    x_test=x[train_end_index+i]
    x_test=x_test.reshape(1, lookback_step, num_variables)

    for j in range(predict_step):
        predicted_temp=model.predict(x_test)
        predicted_values_temp.append(predicted_temp)
        predicted_temp=predicted_temp.reshape(1, 1, num_variables)
        x_test=np.delete(x_test, 0, axis=1)
        x_test=np.append(x_test, predicted_temp, axis=1)

    predicted_values.append(predicted_values_temp[-1])
    predicted_date.append(date[train_end_index+lookback_step+predict_step+i])

predicted_values=np.array(predicted_values).squeeze()
predicted_values=sc.inverse_transform(predicted_values)


# ---- Cell ----
register_matplotlib_converters()
plt.figure(figsize=(14,7))
plt.plot(date[train_end_index:],input_data[train_end_index:,0], color='green')
plt.plot(predicted_date,predicted_values[:,0], color= 'red')

# ---- Cell ----
## predict_step 만큼 뒤에 예측한 값이 당일 종가보다 높으면 사서, 예측했던 날짜에 무조건 팔았을때의 수익률

asset=100000000
profit=0
purchased_stock_list=[]
purchased_stock_date_list=[]
profit_list=[]

for i in range(len(predicted_date)):
    if predicted_values[i,0]>input_data[train_end_index+lookback_step+i,0]:
        purchased_stock_list.append(input_data[train_end_index+lookback_step+i,0])
        purchased_stock_date_list.append(predicted_date[i])
        profit_list.append(input_data[train_end_index+lookback_step+i+predict_step,0]-input_data[train_end_index+lookback_step+i,0])

asset+=sum(profit_list)*100000


print(f'투자기간: {predicted_date[0]}~{predicted_date[-1]} ')
print('매입단가:', format(sum(purchased_stock_list)/len(purchased_stock_list),','))
print('현재가:', format(input_data[-1,0],','))
print('매매손익:', format(sum(profit_list)*100000,","))
print('현재 총 자산:',format(asset,','))

# ---- Cell ----
## predict_step 만큼 뒤에 예측한 값이 당일 종가보다 높으면 사놓고 샀을때 가격보다 오른 경우만 팔았을때의 수익률

asset=100000000
profit=0
purchased_stock_list=[]
purchased_stock_date_list=[]
profit_list=[]



for i in range(len(predicted_date)):
    if predicted_values[i,0]>input_data[train_end_index+lookback_step+i,0]:
        purchased_stock_list.append(input_data[train_end_index+lookback_step+i,0])
        purchased_stock_date_list.append(predicted_date[i])
        asset-=purchased_stock_list[-1]*100000

    purchased_stock_list_temp=[]+purchased_stock_list

    for j in purchased_stock_list:
        if j<input_data[train_end_index+lookback_step+i,0]:
            profit_list.append(input_data[train_end_index+lookback_step+i,0]-j)
            purchased_stock_list_temp.remove(j)
            asset+=profit_list[-1]*100000
            asset+=j*100000
    #print(purchased_stock_list_temp)
    purchased_stock_list=[]+purchased_stock_list_temp

asset+=len(purchased_stock_list)*input_data[-1,0]*100000

print(f'투자기간: {predicted_date[0]}~{predicted_date[-1]} ')
#print('매입단가:', format(sum(purchased_stock_list)/len(purchased_stock_list),','))
print('현재가:', format(input_data[-1,0],','))
print('매입금액:', format(sum(purchased_stock_list)*100000,','))
print('평가금액:', format(len(purchased_stock_list)*input_data[-1,0]*100000,','))
print('평가손익 :', format(len(purchased_stock_list)*input_data[-1,0]*100000-sum(purchased_stock_list)*100000,','))
print('평가손익률 :' ,format((len(purchased_stock_list)*input_data[-1,0]-sum(purchased_stock_list))/sum(purchased_stock_list),'.2f'))
print('매매손익:', format(sum(profit_list)*100000,","))
print('현재 총 자산:',format(asset,','))
print('자산 증가율:', format((asset-100000000)/100000000,'.3'))
print('코스피 증가율:', format(input_data[-1,0]/input_data[train_end_index,0],'.3f'))

# ---- Cell ----

