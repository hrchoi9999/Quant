# English filename: 1_collection_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/2일차 금융 데이터 수집 및 가공/1. 과거시세 수집_clear.py
# Original filename: 1. 과거시세 수집_clear.py

# ---- Cell ----
start_date = '2025-09-01'
end_date = '2025-09-30'

# ---- Cell ----


# ---- Cell ----
index_cd = 'KPI200'
page_n = 1
naver_index = 'http://finance.naver.com/sise/sise_index_day.nhn?code=' + index_cd + '&page=' + str(page_n)

# ---- Cell ----
from urllib.request import urlopen
source = urlopen(naver_index).read()
source

# ---- Cell ----
import bs4
source = bs4.BeautifulSoup(source, 'lxml')

# ---- Cell ----
print(source.prettify())

# ---- Cell ----
td = source.find_all('td')
len(td)

# ---- Cell ----
# /html/body/div/table[1]/tbody/tr[3]/td[1]
source.find_all('table')[0].find_all('tr')[2].find_all('td')[0]


# ---- Cell ----
d = source.find_all('td', class_='date')[0].text
d

# ---- Cell ----
import datetime as dt

# ---- Cell ----
yyyy = int(d.split('.')[0])
mm = int(d.split('.')[1])
dd = int(d.split('.')[2])

this_date= dt.date(yyyy, mm, dd)
this_date

# ---- Cell ----
def date_format(d):
    d = str(d).replace('-', '.')

    yyyy = int(d.split('.')[0])
    mm = int(d.split('.')[1])
    dd = int(d.split('.')[2])

    this_date= dt.date(yyyy, mm, dd)
    return this_date

# ---- Cell ----
# /html/body/div/table[1]/tbody/tr[3]/td[2]

# ---- Cell ----
this_close = source.find_all('tr')[2].find_all('td')[1].text
this_close = this_close.replace(',', '')
this_close = float(this_close)
this_close

# ---- Cell ----
p = source.find_all('td', class_='number_1')[0].text
p

# ---- Cell ----
dates = source.find_all('td', class_='date')
prices = source.find_all('td', class_='number_1')

# ---- Cell ----
len(dates)

# ---- Cell ----
len(prices)

# ---- Cell ----
for n in range(len(dates)):
    this_date = dates[n].text
    this_date = date_format(this_date)

    this_close = prices[n*4].text
    # 0, 4, 8, ... 4의 배수로 돌아가는 가격 추출
    this_close = this_close.replace(',', '')
    this_close = float(this_close)
    this_close

    print(this_date, this_close)

# ---- Cell ----
# /html/body/div/table[2]/tbody/tr/td[7]/a

# ---- Cell ----
paging = source.find('td', class_='pgRR').find('a')['href']
paging

# ---- Cell ----
paging = paging.split('&')[1]
paging

# ---- Cell ----
paging = paging.split('=')[1]
paging

# ---- Cell ----
naver_index = 'http://finance.naver.com/sise/sise_index_day.nhn?code=' + index_cd + '&page=' + str(505)

source = urlopen(naver_index).read()
source = bs4.BeautifulSoup(source, 'lxml')

if source.find('td', class_='pgRR'):
    last_page = source.find('td', class_='pgRR').find('a')['href']
    last_page = last_page.split('&')[1]
    last_page = last_page.split('=')[1]
    last_page = int(last_page)

# ---- Cell ----
last_page

# ---- Cell ----
def historical_index_naver(index_cd, page_n=1, last_page=0):

    naver_index = 'http://finance.naver.com/sise/sise_index_day.nhn?code=' + index_cd + '&page=' + str(page_n)

    source = urlopen(naver_index).read()   # 지정한 페이지에서 코드 읽기
    source = bs4.BeautifulSoup(source, 'lxml')   # 뷰티풀 스프로 태그별로 코드 분류

    dates = source.find_all('td', class_='date')   # <td class="date">태그에서 날짜 수집
    prices = source.find_all('td', class_='number_1')   # <td class="number_1">태그에서 지수 수집

    for n in range(len(dates)):

        if dates[n].text.split('.')[0].isdigit():

            # 날짜 처리
            this_date = dates[n].text
            this_date= date_format(this_date)

            # 종가 처리
            this_close = prices[n*4].text   # prices 중 종가지수인 0,4,8,...번째 데이터 추출
            this_close = this_close.replace(',', '')
            this_close = float(this_close)

            # 딕셔너리에 저장
            historical_prices[this_date] = this_close

    # 페이지 네비게이션
    if last_page == 0:
        last_page = source.find('td', class_='pgRR').find('a')['href']
        # 마지막페이지 주소 추출
        last_page = last_page.split('&')[1]   # & 뒤의 page=506 부분 추출
        last_page = last_page.split('=')[1]   # = 뒤의 페이지번호만 추출
        last_page = int(last_page)   # 숫자형 변수로 변환

    # 다음 페이지 호출
    if page_n < last_page:
        page_n = page_n + 1
        historical_index_naver(index_cd, start_date, end_date, page_n, last_page)

    return historical_prices

# ---- Cell ----
def historical_index_naver(index_cd, start_date='', end_date='', page_n=1, last_page=0):

    if start_date:   # start_date가 있으면
        start_date = date_format(start_date)   # date 포맷으로 변환
    else:    # 없으면
        start_date = dt.date.today()   # 오늘 날짜를 지정
    if end_date:
        end_date = date_format(end_date)
    else:
        end_date = dt.date.today()


    naver_index = 'http://finance.naver.com/sise/sise_index_day.nhn?code=' + index_cd + '&page=' + str(page_n)

    source = urlopen(naver_index).read()   # 지정한 페이지에서 코드 읽기
    source = bs4.BeautifulSoup(source, 'lxml')   # 뷰티풀 스프로 태그별로 코드 분류

    dates = source.find_all('td', class_='date')   # <td class="date">태그에서 날짜 수집
    prices = source.find_all('td', class_='number_1')   # <td class="number_1">태그에서 지수 수집

    for n in range(len(dates)):

        if dates[n].text.split('.')[0].isdigit():

            # 날짜 처리
            this_date = dates[n].text
            this_date= date_format(this_date)

            if this_date <= end_date and this_date >= start_date:
            # start_date와 end_date 사이에서 데이터 저장
                # 종가 처리
                this_close = prices[n*4].text   # prices 중 종가지수인 0,4,8,...번째 데이터 추출
                this_close = this_close.replace(',', '')
                this_close = float(this_close)

                # 딕셔너리에 저장
                historical_prices[this_date] = this_close

            elif this_date < start_date:
            # start_date 이전이면 함수 종료
                return historical_prices

    # 페이지 네비게이션
    if last_page == 0:
        last_page = source.find('td', class_='pgRR').find('a')['href']
        # 마지막페이지 주소 추출
        last_page = last_page.split('&')[1]   # & 뒤의 page=506 부분 추출
        last_page = last_page.split('=')[1]   # = 뒤의 페이지번호만 추출
        last_page = int(last_page)   # 숫자형 변수로 변환

    # 다음 페이지 호출
    if page_n < last_page:
        page_n = page_n + 1
        historical_index_naver(index_cd, start_date, end_date, page_n, last_page)

    return historical_prices

# ---- Cell ----
start_date = '2025-09-01'
end_date = '2025-10-17'

# ---- Cell ----
index_cd = 'KPI200'
historical_prices = dict()
historical_index_naver(index_cd, start_date, end_date)
historical_prices

# ---- Cell ----
import pandas as pd
import requests, json   # 해외지수는 json 형태로 표출됨
headers = {
    'User-Agent': 'Mozilla/5.0',
    'X-Requested-With': 'XMLHttpRequest',
}

# ---- Cell ----
symbol = 'SPI@SPX'
page = 1

# ---- Cell ----
url = 'https://finance.naver.com/world/worldDayListJson.nhn?symbol='+symbol+'&fdtc=0&page='+str(page)
r = requests.post(url, headers=headers)
data = json.loads(r.text)

# ---- Cell ----
data[0]

# ---- Cell ----
data[0]['symb']

# ---- Cell ----
data[0]['xymd']

# ---- Cell ----
data[0]['clos']

# ---- Cell ----
len(data)

# ---- Cell ----
d = dict()
for n in range(len(data)):
    date = pd.to_datetime(data[n]['xymd']).date()
    price = float(data[n]['clos'])
    d[date] = price
print(d)

# ---- Cell ----
def read_json(d, symbol, page=1):
    url = 'https://finance.naver.com/world/worldDayListJson.nhn?symbol='+symbol+'&fdtc=0&page='+str(page)
    r = requests.post(url, headers=headers)
    data = json.loads(r.text)

    for n in range(len(data)):
        date = pd.to_datetime(data[n]['xymd']).date()
        price = float(data[n]['clos'])
        d[date] = price

    if len(data) >= 9 and page<3:  # 연습용 각가 조정
        page += 1
        read_json(d, symbol, page)

    return d

# ---- Cell ----
historical_index = dict()
historical_index = read_json(historical_index, symbol, page)

# ---- Cell ----
historical_index

# ---- Cell ----
indices = {
    'SPI@SPX' : 'S&P 500',
    'NAS@NDX' : 'Nasdaq 100',
    'NII@NI225' : 'Nikkei 225',
}

# ---- Cell ----
historical_indices = dict()
for key, value in indices.items():
    print (key, value)
    s = dict()
    s = read_json(s, key, 1)
    historical_indices[value] = s
prices_df = pd.DataFrame(historical_indices)
prices_df.sort_index(inplace=True)

# ---- Cell ----
prices_df.tail(3)

# ---- Cell ----
def date_format(d=''):
    if d != '':
        this_date = pd.to_datetime(d).date()
    else:
        this_date = pd.Timestamp.today().date()   # 오늘 날짜를 지정
    return (this_date)

# ---- Cell ----
def index_global(d, symbol, start_date='', end_date='', page=1):

    end_date = date_format(end_date)
    if start_date == '':
        start_date = end_date - pd.DateOffset(months=1)
    start_date = date_format(start_date)

    url = 'https://finance.naver.com/world/worldDayListJson.nhn?symbol='+symbol+'&fdtc=0&page='+str(page)
    r = requests.post(url, headers=headers)
    data = json.loads(r.text)

    if len(data) > 0:

        for n in range(len(data)):
            date = pd.to_datetime(data[n]['xymd']).date()

            if date <= end_date and date >= start_date:
            # start_date와 end_date 사이에서 데이터 저장
                # 종가 처리
                price = float(data[n]['clos'])
                # 딕셔너리에 저장
                d[date] = price
            elif date < start_date:
            # start_date 이전이면 함수 종료
                return d

        if len(data) >= 9:
            page += 1
            index_global(d, symbol, start_date, end_date, page)

    return d

# ---- Cell ----
historical_indices = dict()
start_date = '2025-09-01'
end_date = '2025-09-30'
for key, value in indices.items():
    s = dict()
    s = index_global(s, key, start_date, end_date)
    historical_indices[value] = s
prices_df = pd.DataFrame(historical_indices)

# ---- Cell ----
prices_df[:30]

# ---- Cell ----
index_cd = 'KPI200'
historical_prices = dict()
kospi200 = historical_index_naver(index_cd, start_date, end_date)

# ---- Cell ----
index_cd = 'SPI@SPX'
historical_prices = dict()
sp500 = index_global(historical_prices, index_cd, start_date, end_date)    # 대체 코드

# ---- Cell ----
tmp = {'S&P500':sp500, 'KOSPI200':kospi200}

# ---- Cell ----
import pandas as pd

# ---- Cell ----
df = pd.DataFrame(tmp)
df.sort_index(inplace=True)
df

# ---- Cell ----
df = df.fillna(method='ffill')
if df.isnull().values.any():
    df = df.fillna(method='bfill')
df

# ---- Cell ----
df.head()

# ---- Cell ----
index_cd = 'KPI200'
historical_prices = dict()
kospi200 = historical_index_naver(index_cd, start_date, end_date)

# ---- Cell ----
index_cd = 'SPI@SPX'
historical_prices = dict()
sp500 = index_global(historical_prices, index_cd, start_date, end_date)    # 대체 코드

# ---- Cell ----
tmp = {'S&P500':sp500, 'KOSPI200':kospi200}

# ---- Cell ----
df = pd.DataFrame(tmp)
df.sort_index(inplace=True)
df

# ---- Cell ----
df = df.fillna(method='ffill')
if df.isnull().values.any():
    df = df.fillna(method='bfill')
df

# ---- Cell ----
import matplotlib.pyplot as plt
%matplotlib inline

# ---- Cell ----
plt.figure(figsize=(10, 5))
plt.plot(df['S&P500'], label='S&P500')
plt.plot(df['KOSPI200'], label='KOSPI200')
plt.legend(loc=0)
plt.grid(True, color='0.7', linestyle=':', linewidth=1)

# ---- Cell ----
df.iloc[0]

# ---- Cell ----
plt.figure(figsize=(10, 5))
plt.plot(df['S&P500'] / df['S&P500'].loc[dt.date(2025, 9, 1)] * 100, label='S&P500')
plt.plot(df['KOSPI200'] / df['KOSPI200'].loc[dt.date(2025, 9, 1)] * 100, label='KOSPI200')
plt.legend(loc=0)
plt.grid(True, color='0.7', linestyle=':', linewidth=1)

# ---- Cell ----
df_ratio_2021_now = df.loc[dt.date(2024, 1, 1):] / df.loc[dt.date(2024, 1, 4)] * 100
df_ratio_2021_now.head(3)

# ---- Cell ----
plt.figure(figsize=(10, 5))
plt.plot(df_ratio_2021_now['S&P500'], label='S&P500')
plt.plot(df_ratio_2021_now['KOSPI200'], label='KOSPI200')
plt.legend(loc=0)
plt.grid(True, color='0.7', linestyle=':', linewidth=1)

# ---- Cell ----
plt.figure(figsize=(7,7))
plt.scatter(df_ratio_2021_now['S&P500'], df_ratio_2021_now['KOSPI200'], marker='.')
plt.grid(True, color='0.7', linestyle=':', linewidth=1)
plt.xlabel('S&P500')
plt.ylabel('KOSPI200')

# ---- Cell ----
import numpy as np
from sklearn.linear_model import LinearRegression

x = df_ratio_2021_now['S&P500']
y = df_ratio_2021_now['KOSPI200']

# 1개 컬럼 np.array로 변환
independent_var = np.array(x).reshape(-1, 1)
dependent_var = np.array(y).reshape(-1, 1)

# Linear Regression
regr = LinearRegression()
regr.fit(independent_var, dependent_var)

result = {'Slope':regr.coef_[0,0], 'Intercept':regr.intercept_[0], 'R^2':regr.score(independent_var, dependent_var) }
result

# ---- Cell ----
plt.figure(figsize=(7,7))
plt.scatter(independent_var, dependent_var, marker='.', color='skyblue')
plt.plot(independent_var, regr.predict(independent_var), color='r', linewidth=3)
plt.grid(True, color='0.7', linestyle=':', linewidth=1)
plt.xlabel('S&P500')
plt.ylabel('KOSPI200')

# ---- Cell ----

