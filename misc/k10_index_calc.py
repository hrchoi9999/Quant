# English filename: 2_k10_index_calc_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/2일차 금융 데이터 수집 및 가공/2 K10 지수 산출_clear.py
# Original filename: 2 K10 지수 산출_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/k10_historical_price.csv
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/k200.csv

# ---- Cell ----
import bs4
from tqdm import tqdm
from urllib.request import urlopen

# ---- Cell ----
# 크롤링 차단 장치 우회를 위해 웹사이트 호출 시 headers 값을 추가
import urllib.request
headers = {
    'User-Agent': 'Mozilla/5.0',
    'X-Requested-With': 'XMLHttpRequest',
}

# ---- Cell ----
# url_float = 'http://companyinfo.stock.naver.com/v1/company/c1010001.aspx?cmp_cd=035420'
url_float = 'https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd=005930'
# Floating ratio from Naver
url_float

# ---- Cell ----
source = urlopen(url_float).read()
soup = bs4.BeautifulSoup(source, 'lxml')

# ---- Cell ----
soup.find(id='cTB11').find_all('tr')[6].td.text

# ---- Cell ----
tmp = soup.find(id='cTB11').find_all('tr')[6].td.text
tmp = tmp.replace('\r', '')
tmp = tmp.replace('\n', '')
tmp = tmp.replace('\t', '')
tmp

# ---- Cell ----
import re

# ---- Cell ----
tmp = re.split('/', tmp)
tmp

# ---- Cell ----
tmp[0]

# ---- Cell ----
tmp[1]

# ---- Cell ----
outstanding = tmp[0].replace(',', '')
outstanding = outstanding.replace('주', '')
outstanding = outstanding.replace(' ', '')
outstanding

# ---- Cell ----
floating = tmp[1].replace(' ', '')
floating = floating.replace('%', '')
floating

# ---- Cell ----
outstanding = int(outstanding)
outstanding

# ---- Cell ----
floating = float(floating)
floating

# ---- Cell ----
# 구성종목 기본정보
def stock_info(stock_cd):
    url_float = 'http://companyinfo.stock.naver.com/v1/company/c1010001.aspx?cmp_cd=' + stock_cd
    source = urlopen(url_float).read()
    soup = bs4.BeautifulSoup(source, 'lxml')

    tmp = soup.find(id='cTB11').find_all('tr')[6].td.text
    tmp = tmp.replace('\r', '')
    tmp = tmp.replace('\n', '')
    tmp = tmp.replace('\t', '')

    tmp = re.split('/', tmp)

    outstanding = tmp[0].replace(',', '')
    outstanding = outstanding.replace('주', '')
    outstanding = outstanding.replace(' ', '')
    outstanding = int(outstanding)

    floating = tmp[1].replace(' ', '')
    floating = floating.replace('%', '')
    floating = float(floating)

    name = soup.find(id='pArea').find('div').find('div').find('tr').find('td').find('span').text

    k10_outstanding[stock_cd] = outstanding
    k10_floating[stock_cd] = floating
    k10_name[stock_cd] = name

# ---- Cell ----
'''
한국거래소 시가총액 상위 10종목 (2019년1월 기준)
005930	삼성전자
000660	SK하이닉스
068270	셀트리온
005380	현대차
207940	삼성바이오로직스
051910	LG화학
005490	POSCO
035420	NAVER
017670	SK텔레콤
015760	한국전력
'''
k10_component = ['005930', '000660', '068270', '005380', '207940',\
                 '051910', '005490', '035420', '017670', '015760']

# ---- Cell ----
k10_outstanding = dict()
k10_floating = dict()
k10_name = dict()
for stock_cd in k10_component:
    print(stock_cd)
    stock_info(stock_cd)

# ---- Cell ----
k10_outstanding

# ---- Cell ----
k10_floating

# ---- Cell ----
import datetime as dt
import pandas as pd

# ---- Cell ----
def date_format(d):
    d = str(d).replace('-', '.')

    yyyy = int(d.split('.')[0])
    mm = int(d.split('.')[1])
    dd = int(d.split('.')[2])

    this_date= dt.date(yyyy, mm, dd)
    return this_date

# ---- Cell ----
def historical_stock_naver(stock_cd, start_date='', end_date='', page_n=1, last_page=0):

    if start_date:   # start_date가 있으면
        start_date = date_format(start_date)   # date 포맷으로 변환
    else:    # 없으면
        start_date = dt.date.today()   # 오늘 날짜를 지정
    if end_date:   # end_date가 없으면
        end_date = date_format(end_date)   # date 포맷으로 변환
    else:   # end_date가 있으면
        end_date = dt.date.today()   # 오늘 날짜를 end_date로 지정

    naver_stock = 'http://finance.naver.com/item/sise_day.nhn?code=' + stock_cd + '&page=' + str(page_n)

    # 기존 코드
    # source = urlopen(naver_stock).read()

    # 개정 코드 (1줄에서 2줄로 늘어남)
    url = urllib.request.Request(naver_stock, headers=headers)   # headers 정보 보내기
    source = urlopen(url).read()

    source = bs4.BeautifulSoup(source, 'lxml')

    dates = source.find_all('span', class_='tah p10 gray03')   # 날짜 수집
    prices = source.find_all('td', class_='num')   # 종가 수집

    for n in range(len(dates)):

        if len(dates) > 0:

            # 날짜 처리
            this_date = dates[n].text
            this_date = date_format(this_date)

            if this_date <= end_date and this_date >= start_date:
            # start_date와 end_date 사이에서 데이터 저장
                # 종가 처리
                this_close = prices[n*6].text
                this_close = this_close.replace(',', '')
                this_close = float(this_close)

                # 딕셔너리에 저장
                historical_prices[this_date] = this_close

            elif this_date < start_date:
            # start_date 이전이면 함수 종료
                return historical_prices

    # 페이지 네비게이션
    if last_page == 0:
        last_page = source.find_all('table')[1].find('td', class_='pgRR').find('a')['href']
        last_page = last_page.split('&')[1]
        last_page = last_page.split('=')[1]
        last_page = float(last_page)

    # 다음 페이지 호출
    if page_n < last_page:
        page_n = page_n + 1
        historical_stock_naver(stock_cd, start_date, end_date, page_n, last_page)

    return historical_prices

# ---- Cell ----
# 미리 서버에 저장
# k10_historical_prices = dict()

# for stock_cd in tqdm(k10_component):

#     historical_prices = dict()
#     start_date = '2024-1-1'
#     end_date = '2024-12-31'
#     historical_stock_naver(stock_cd, start_date, end_date)

#     k10_historical_prices[stock_cd] = historical_prices

# k10_historical_price = pd.DataFrame(k10_historical_prices)
# k10_historical_price.sort_index(axis=1, inplace=True)

# k10_historical_price.index.name = "date"
# k10_historical_price.to_csv("k10_historical_price.csv")

# ---- Cell ----
k10_historical_price = pd.read_csv("k10_historical_price.csv", index_col=0)

# ---- Cell ----
k10_historical_price = k10_historical_price.fillna(method='ffill')   # ffill로 구멍을 채우고
if k10_historical_price.isnull().values.any():   # 그래도 구멍이 남아 있으면
    k10_historical_price = k10_historical_price.fillna(method='bfill')   # bfill로 채워라
k10_historical_price.head(3)

# ---- Cell ----
k10_historical_price['005930'] = k10_historical_price['005930'] / 50   # 삼성전자 액면분할에 따른 수정주가 계산
k10_historical_price.head(3)

# ---- Cell ----
tmp = {'Outstanding' : k10_outstanding,\
       'Floating' : k10_floating,\
       'Price' : k10_historical_price.iloc[0],\
       'Name' : k10_name}
k10_info = pd.DataFrame(tmp)

# ---- Cell ----
k10_info['f Market Cap'] = k10_info['Outstanding'] * k10_info['Floating'] * k10_info['Price'] * 0.01
k10_info['Market Cap'] = k10_info['Outstanding'] * k10_info['Price']
k10_info

# ---- Cell ----
k10_historical_mc = k10_historical_price * k10_info['Outstanding'] * k10_info['Floating'] * 0.01
k10_historical_mc.head(3)

# ---- Cell ----
'''
<데이터프레임>.sum() 은 각 열의 합 (세로방향)
<데이터프레임>.sum(axis=1) 은 각 행의 합 (가로방향)
'''
k10_historical_mc.sum(axis=1)     # 일자별 시가총액 합

# ---- Cell ----
k10 = pd.DataFrame()
k10['K10 Market Cap'] = k10_historical_mc.sum(axis=1)
k10.head(3)

# ---- Cell ----
k10['K10 Market Cap'].head()

# ---- Cell ----
k10['K10'] = k10['K10 Market Cap'] / k10['K10 Market Cap'][0] * 100
k10.tail()

# ---- Cell ----
k10.head()

# ---- Cell ----
import matplotlib.pyplot as plt
%matplotlib inline

# ---- Cell ----
plt.figure(figsize=(10, 5))
plt.plot(k10['K10'], label='K10')
plt.legend(loc=0)
plt.grid(True, color='0.7', linestyle=':', linewidth=1)

# ---- Cell ----
def historical_index_naver(index_cd, start_date='', end_date='', page_n=1, last_page=0):

    index_cd = index_cd   # 인덱스 코드
    page_n = page_n   # 페이지 번호

    if start_date:   # start_date가 있으면
        start_date = date_format(start_date)   # date 포맷으로 변환
    else:    # 없으면
        start_date = dt.date.today()   # 오늘 날짜를 지정
    if not end_date:   # end_date가 없으면
        end_date = dt.date.today()   # 오늘 날짜를 end_date로 지정
    else:   # end_date가 있으면
        end_date = date_format(end_date)   # date 포맷으로 변환

    naver_index = 'http://finance.naver.com/sise/sise_index_day.nhn?code=' + index_cd + '&page=' + str(page_n)

    # source = urlopen(naver_index).read()   # 지정한 페이지에서 코드 읽기

    url = urllib.request.Request(naver_index, headers=headers)   # headers 정보 보내기
    source = urlopen(url).read()

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
# historical_prices = dict()     # 딕셔너리 초기화
# kospi200 = historical_index_naver('KPI200', '2024-1-1', '2024-12-31')

# k200 = pd.DataFrame({'K200' : kospi200})
# k200.index.name = "date"
# k200.to_csv("k200.csv")

# ---- Cell ----
k200 = pd.read_csv("k200.csv", index_col=0)

# ---- Cell ----
k200.tail()

# ---- Cell ----
k10.sort_index(inplace=True)
k200.sort_index(inplace=True)

# ---- Cell ----
plt.figure(figsize=(10, 5))
plt.plot(k10['K10'] / k10['K10'][0] * 100, label='K10')
plt.plot(k200['K200'] / k200['K200'][0] * 100, label='K200')
plt.legend(loc=0)
plt.grid(True, color='0.7', linestyle=':', linewidth=1)

# ---- Cell ----
import math

# ---- Cell ----
def futures_price (S, r, d, T, t0):
    t = (T - t0).days / 252
    F = S * math.exp((r-d)*t)
    return F

# ---- Cell ----
T = dt.date(2018, 12, 14)     # 만기일
t0 = dt.date(2018, 6, 15)     # 현재일

futures_price(100.0, 0.02, 0.015, T, t0)

# ---- Cell ----
T = dt.date(2018, 12, 14)     # 만기일
t0 = dt.date(2018, 12, 10)     # 현재일

futures_price(100.0, 0.02, 0.015, T, t0)

# ---- Cell ----

