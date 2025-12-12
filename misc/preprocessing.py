# English filename: 2_preprocessing_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/1. 금융시계열_LSTM과Atttention/1. LSTM/2. Preprocessing_clear.py
# Original filename: 2. Preprocessing_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_keras/stock_data.csv

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_keras/stock_data.csv
!mkdir preprocessing
!pip install PyWavelets

# ---- Cell ----
import numpy as np
import pandas as pd
import pywt
import matplotlib.pyplot as plt

# ---- Cell ----
class PreProcessing:
    def __init__(self, split, feature_split):
        self.split = split
        self.feature_split = feature_split
        self.stock_data = pd.read_csv("stock_data.csv")

    # wavelet transform and create autoencoder data
    def make_wavelet_train(self):
        train_data = []
        test_data = []
        log_train_data = []
        for i in range((len(self.stock_data)//10)*10 - 11):
            train = []
            log_ret = []
            for j in range(1, 5):
                x = np.array(self.stock_data.iloc[i: i + 11, j])
                (ca, cd) = pywt.dwt(x, "haar")
                cat = pywt.threshold(ca, np.std(ca), mode="soft")
                cdt = pywt.threshold(cd, np.std(cd), mode="soft")
                tx = pywt.idwt(cat, cdt, "haar")
#                 if j==5:
#                     print(tx)
#                     break
                tx=abs(tx) # 한번 시도
                log = np.diff(np.log(tx))*100
                macd = np.mean(x[5:]) - np.mean(x)
                # ma = np.mean(x)
                sd = np.std(x)
                log_ret = np.append(log_ret, log)
                x_tech = np.append(macd*10, sd)
                train = np.append(train, x_tech)
            train_data.append(train)
            log_train_data.append(log_ret)
        trained = pd.DataFrame(train_data)
        trained.to_csv("preprocessing/indicators.csv")
        log_train = pd.DataFrame(log_train_data, index=None)
        log_train.to_csv("preprocessing/log_train.csv")
        # auto_train = pd.DataFrame(train_data[0:800])
        # auto_test = pd.DataFrame(train_data[801:1000])
        # auto_train.to_csv("auto_train.csv")
        # auto_test.to_csv("auto_test.csv")
        rbm_train = pd.DataFrame(log_train_data[0:int(self.split*self.feature_split*len(log_train_data))], index=None)
        rbm_train.to_csv("preprocessing/rbm_train.csv")
        rbm_test = pd.DataFrame(log_train_data[int(self.split*self.feature_split*len(log_train_data))+1:
                                               int(self.feature_split*len(log_train_data))])
        rbm_test.to_csv("preprocessing/rbm_test.csv")
        for i in range((len(self.stock_data) // 10) * 10 - 11):
            y = 100*np.log(self.stock_data.iloc[i + 11, 5] / self.stock_data.iloc[i + 10, 5])
            test_data.append(y)
        test = pd.DataFrame(test_data)
        test.to_csv("preprocessing/stock_data.csv")  # adjust_price의 수익률  (y)

    def make_test_data(self):
        test_stock = []
        stock_data = pd.read_csv("preprocessing/stock_data.csv", index_col=0)

        for i in range((len(self.stock_data) // 10) * 10 - 11):
            l = self.stock_data.iloc[i+11, 5]
            test_stock.append(l)
            test = pd.DataFrame(test_stock)
            test.to_csv("preprocessing/test_stock.csv")  #Adjusted Price

        stock_test_data = np.array(test_stock)[int(self.feature_split*len(test_stock) +
                                               self.split*(1-self.feature_split)*len(test_stock)):]
        stock = pd.DataFrame(stock_test_data, index=None)
        stock.to_csv("stock_data_test.csv")

        # print(train_data[1:5])
        # print(test_data[1:5])
        # plt.plot(train_data[1])
        # plt.show()


if __name__ == "__main__":
    preprocess = PreProcessing(0.8, 0.25)
    preprocess.make_wavelet_train()
    preprocess.make_test_data()
    print('completed')


# ---- Cell ----
stock = pd.read_csv("stock_data.csv")
stock.head()

# ---- Cell ----
for j in range(1,6):
    print(stock.iloc[0,j])

# ---- Cell ----
stock_data = pd.read_csv("stock_data.csv")
stock_data.head()

# ---- Cell ----
b= pd.read_csv("preprocessing/indicators.csv")
b.head()

# ---- Cell ----
# 예제

# ---- Cell ----
import pywt
x = [3, 7, 1, 1, -2, 5, 4, 6]
ca, cd = pywt.dwt(x, 'haar')

# ---- Cell ----
print(ca)
print(cd)

# ---- Cell ----
print(pywt.idwt(ca, cd, 'haar'))

# ---- Cell ----
cat=pywt.threshold(ca, 2, 'hard')
cdt=pywt.threshold(cd, 2, 'hard')

# ---- Cell ----
cat=pywt.threshold(ca, 2, 'soft')
cdt=pywt.threshold(cd, 2, 'soft')

# ---- Cell ----
print(cat)
print(cdt)

# ---- Cell ----
print(np.round(pywt.idwt(cat, cdt, 'haar'),0))

# ---- Cell ----
catt=pywt.threshold(ca, 2, 'hard')
cdtt=pywt.threshold(cd, 2, 'hard')

# ---- Cell ----
print(catt)
print(cdtt)

# ---- Cell ----
print(np.round(pywt.idwt(catt, cdtt, 'haar'),0))

# ---- Cell ----
x = [3, 7, 1, 1, -2, 5, 4, 6]

# ---- Cell ----

