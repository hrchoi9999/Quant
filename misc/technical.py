# English filename: technical_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/6일차 기본적 팩터모델의 이해/technical_clear.py
# Original filename: technical_clear.py

# ---- Cell ----
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/libta-lib0_0.4.0-oneiric1_amd64.deb -qO libta.deb
!wget https://launchpad.net/~mario-mariomedina/+archive/ubuntu/talib/+files/ta-lib0-dev_0.4.0-oneiric1_amd64.deb -qO ta.deb
!dpkg -i libta.deb ta.deb
!pip install ta-lib

# ---- Cell ----
# cd [C:\파일이 있는 폴더]

# pip install [다운로드 받은 파일 명.whl]

# ---- Cell ----
# import pandas_datareader as web
import yfinance as yf

# stock_data = web.DataReader('^GSPC', 'yahoo')
stock_data = yf.download('^GSPC')
stock_data = stock_data.tail(500)

# ---- Cell ----
import talib
import matplotlib.pyplot as plt

stock_data['SMA_20'] = talib.SMA(stock_data['Close'],
                                 timeperiod=20)  # 20일 단순 이동평균
stock_data['SMA_60'] = talib.SMA(stock_data['Close'],
                                 timeperiod=60)  # 60일 단순 이동평균
stock_data[['Close', 'SMA_20', 'SMA_60']].plot(figsize=(10, 6))
plt.show()

# ---- Cell ----
stock_data['EMA_60'] = talib.EMA(stock_data['Close'], 60)  # 60일 지수 이동평균
stock_data[['Close', 'SMA_60', 'EMA_60']].plot(figsize=(10, 6))
plt.show()

# ---- Cell ----
from matplotlib import gridspec

stock_data['RSI_14'] = talib.RSI(stock_data['Close'], timeperiod=14)
stock_data['RSI_14'].fillna(0, inplace=True)
fig = plt.subplots(figsize=(10, 6), sharex=True)
gs = gridspec.GridSpec(nrows=2, ncols=1, height_ratios=[2, 1])

# 주가 나타내기
ax1 = plt.subplot(gs[0])
ax1 = stock_data['Close'].plot()
ax1.set_xlabel('')
ax1.axes.xaxis.set_ticks([])

# RSI 나타내기
ax2 = plt.subplot(gs[1])
ax2 = stock_data['RSI_14'].plot(color='black', ylim=[0, 100])
ax2.axhline(y=70, color='r', linestyle='-')
ax2.axhline(y=30, color='r', linestyle='-')
ax2.set_xlabel
plt.subplots_adjust(wspace=0, hspace=0)

plt.show()

# ---- Cell ----
import pandas as pd

upper_2sd, mid_2sd, lower_2sd = talib.BBANDS(stock_data['Close'],
                                             nbdevup=2,
                                             nbdevdn=2,
                                             timeperiod=20)

bb = pd.concat([upper_2sd, mid_2sd, lower_2sd, stock_data['Close']], axis=1)
bb.columns = ['Upper Band', 'Mid Band', 'Lower Band', 'Close']
bb.plot(figsize=(10, 6),
        color={
            'Upper Band': 'red',
            'Lower Band': 'blue',
            'Mid Band': 'green',
            'Close': 'black'
        })
plt.show()
