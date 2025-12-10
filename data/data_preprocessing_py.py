# English filename: data_preprocessing_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/1. 금융시계열_LSTM과Atttention/2. Attention/data_preprocessing.py
# Original filename: data_preprocessing.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_pytorch/data.zip && unzip -n data.zip

# ---- Cell ----
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt

# ---- Cell ----
path = "./data/S_P500IndexData-Table1.csv"
data_present = pd.read_csv(path, sep=";")
data_present.head()
# 600 is a bit more than 2 years of data
num_datapoints = 600
# roll by approx. 60 days - 3 months of trading days
step_size = int(0.1 * num_datapoints)
# calculate number of iterations we can do over the entire data set
num_iterations = int(np.ceil((len(data_present)-num_datapoints)/step_size))+2

y_test_lst = []
preds = []
ct = 0


# ---- Cell ----
#data_present=pd.read_csv('data/S&P500IndexData-Table1.csv')
data_present.head()

# ---- Cell ----
for i in data_present.columns:
    if(i!='Ntime' and i!='Time'):
        scaler = MinMaxScaler()
        data_present[i]=scaler.fit_transform(data_present[i].values.reshape(-1, 1))

# ---- Cell ----
a=pd.to_datetime(data_present['Ntime'].astype('str'),yearfirst=True).dt.date
data_present['Ntime']=a
data_present['Date']=data_present['Ntime']
data_present['Year']=pd.DatetimeIndex(data_present['Ntime']).year
data_present['month']=pd.DatetimeIndex(data_present['Ntime']).month
data_present['date']=pd.DatetimeIndex(data_present['Ntime']).day
data_present.drop(['Ntime','time'],axis=1,inplace=True)

# ---- Cell ----
data_present=data_present[(data_present['Year']==2015) | (data_present['Year']==2016) | (data_present['Year']==2014) | (data_present['Year']==2013) | ((data_present['Year']==2012) & ((data_present['month']==10) | (data_present['month']==11) | (data_present['month']==12) | ((data_present['month']==9) & (data_present['date']==28))))]
validation=data_present[(data_present['Year']==2016) & ((data_present['month']==6) | (data_present['month']==5) | (data_present['month']==4))]
test=data_present[(data_present['Year']==2016) & ((data_present['month']==7) | (data_present['month']==8) | (data_present['month']==9))]
train=data_present[(data_present['Year']==2012)| (data_present['Year']==2013) | (data_present['Year']==2014) | (data_present['Year']==2015) | ((data_present['Year']==2016) & ((data_present['month']==1) | (data_present['month']==2) | (data_present['month']==3))) ]
validation.drop(['Year','month','date'],axis=1,inplace=True)
train.drop(['Year','month','date'],axis=1,inplace=True)
test.drop(['Year','month','date'],axis=1,inplace=True)
validation=validation.reset_index(drop=True)
train=train.reset_index(drop=True)
test=test.reset_index(drop=True)

# ---- Cell ----
for i in train.columns:
    if(i!='Date'):
        scaler = MinMaxScaler()
        train[i]=scaler.fit_transform(train[i].values.reshape(-1, 1))
for i in validation.columns:
    if(i!='Date'):
        scaler = MinMaxScaler()
        validation[i]=scaler.fit_transform(validation[i].values.reshape(-1, 1))
for i in test.columns:
    if(i!='Date'):
        scaler = MinMaxScaler()
        test[i]=scaler.fit_transform(test[i].values.reshape(-1, 1))

# ---- Cell ----
train.to_csv('data/train.csv',index=False)
test.to_csv('data/test.csv',index=False)
validation.to_csv('data/validation.csv',index=False)

# ---- Cell ----

