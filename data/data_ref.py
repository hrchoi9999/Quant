# English filename: data_ref_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/6일차 기본적 팩터모델의 이해/data_ref_clear.py
# Original filename: data_ref_clear.py

# ---- Cell ----
!sudo apt-get install -y fonts-nanum
!sudo fc-cache -fv
!rm ~/.cache/matplotlib -rf

import matplotlib.pyplot as plt

plt.rc('font', family='NanumBarunGothic')
# 여기까지 실행한 다음에 다시실행 해주세요.

# ---- Cell ----
!pip install xmltodict pymysql
!pip install --upgrade 'sqlalchemy<2.0'

# ---- Cell ----
# import keyring

# keyring.set_password('dart_api_key', 'User Name', 'Password')

# ---- Cell ----
import keyring
import requests as rq
from io import BytesIO
import zipfile

# api_key = keyring.get_password('dart_api_key', 'Henry')
api_key = "9aebac0ee49b223f60f32c0aa868402bfefa5fe8"
codezip_url = f'''https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}'''
codezip_data = rq.get(codezip_url)
codezip_data.headers

# ---- Cell ----
codezip_data.headers['Content-Disposition']

# ---- Cell ----
codezip_file = zipfile.ZipFile(BytesIO(codezip_data.content))
codezip_file.namelist()

# ---- Cell ----
import xmltodict
import json
import numpy as np
import pandas as pd

code_data = codezip_file.read('CORPCODE.xml').decode('utf-8')
data_odict = xmltodict.parse(code_data)
data_dict = json.loads(json.dumps(data_odict))
data = data_dict.get('result').get('list')
corp_list = pd.DataFrame(data)

corp_list.head()

# ---- Cell ----
len(corp_list)

# ---- Cell ----
corp_list["stock_code"] = corp_list["stock_code"].apply(lambda x: np.nan if len(x.replace(" ", "")) == 0 else x)

# ---- Cell ----
corp_list = corp_list[~corp_list["stock_code"].isna()]

# ---- Cell ----
corp_list = corp_list.reset_index(drop=True)

# ---- Cell ----
corp_list.head()

# ---- Cell ----
import sqlite3
from sqlalchemy import create_engine


con = sqlite3.connect("stock.db")
corp_list.to_sql(name='dart_code', con=con, index=True, if_exists='replace')

# ---- Cell ----
from datetime import date
from dateutil.relativedelta import relativedelta

bgn_date = (date.today() + relativedelta(days=-7)).strftime("%Y%m%d")
end_date = (date.today()).strftime("%Y%m%d")

notice_url = f'''https://opendart.fss.or.kr/api/list.json?crtfc_key={api_key}
&bgn_de={bgn_date}&end_de={end_date}&page_no=1&page_count=100'''

notice_data = rq.get(notice_url)
notice_data_df = notice_data.json().get('list')
notice_data_df = pd.DataFrame(notice_data_df)

notice_data_df.tail()

# ---- Cell ----
corp_list[corp_list['corp_name'] == '삼성전자']

# ---- Cell ----
bgn_date = (date.today() + relativedelta(days=-30)).strftime("%Y%m%d")
end_date = (date.today()).strftime("%Y%m%d")
corp_code = '00126380'

notice_url_ss = f'''https://opendart.fss.or.kr/api/list.json?crtfc_key={api_key}
&corp_code={corp_code}&bgn_de={bgn_date}&end_de={end_date}&page_no=1&page_count=100'''

notice_data_ss = rq.get(notice_url_ss)
notice_data_ss_df = notice_data_ss.json().get('list')
notice_data_ss_df = pd.DataFrame(notice_data_ss_df)

notice_data_ss_df.tail()

# ---- Cell ----
notice_url_exam = notice_data_ss_df.loc[0, 'rcept_no']
notice_dart_url = f'http://dart.fss.or.kr/dsaf001/main.do?rcpNo={notice_url_exam}'

print(notice_dart_url)

# ---- Cell ----
corp_code = '00126380'
bsns_year = '2021'
reprt_code = '11011'

url_div = f'''https://opendart.fss.or.kr/api/alotMatter.json?crtfc_key={api_key}
&corp_code={corp_code}&bsns_year={bsns_year}&reprt_code={reprt_code}'''

div_data_ss = rq.get(url_div)
div_data_ss_df = div_data_ss.json().get('list')
div_data_ss_df = pd.DataFrame(div_data_ss_df)

div_data_ss_df.head()

# ---- Cell ----
import pandas_datareader as web
import pandas as pd

t10y2y = web.DataReader('T10Y2Y', 'fred', start='1990-01-01')
t10y3m = web.DataReader('T10Y3M', 'fred', start='1990-01-01')

rate_diff = pd.concat([t10y2y, t10y3m], axis=1)
rate_diff.columns = ['10Y - 2Y', '10Y - 3M']

rate_diff.tail()

# ---- Cell ----
import matplotlib.pyplot as plt
import yfinance as yf

# 주가지수 다운로드
# sp = web.DataReader('^GSPC', 'yahoo', start='1990-01-01')
sp = yf.download("^GSPC", start="1990-01-01")

plt.rc('font', family='NanumBarunGothic')
plt.rc('axes', unicode_minus=False)

fig, ax1 = plt.subplots(figsize=(10, 6))

ax1.plot(t10y2y, color = 'black', linewidth = 0.5, label = '10Y-2Y')
ax1.plot(t10y3m, color = 'gray', linewidth = 0.5, label = '10Y-3M')
ax1.axhline(y=0, color='r', linestyle='dashed')
ax1.set_ylabel('장단기 금리차')
ax1.legend(loc = 'lower right')

ax2 = ax1.twinx()
ax2.plot(np.log(sp['Close']), label = 'S&P500')
ax2.set_ylabel('S&P500 지수(로그)')
ax2.legend(loc = 'upper right')

plt.show()

# ---- Cell ----
import pandas_datareader as web
import pandas as pd

bei = web.DataReader('T10YIE', 'fred', start='1990-01-01')

bei.tail()

# ---- Cell ----
import matplotlib.pyplot as plt

bei.plot(figsize=(10, 6), grid=True)
plt.axhline(y=2, color='r', linestyle='-')

plt.show()

# ---- Cell ----
# !pip install selenium

# ---- Cell ----
# import selenium
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.common.by import By
# chrome_options = webdriver.ChromeOptions()
# chrome_options.add_argument('--headless')
# chrome_options.add_argument('--no-sandbox')
# chrome_options.add_argument('--disable-dev-shm-usage')

# driver = webdriver.Chrome(options=chrome_options)
# driver.get(url='https://edition.cnn.com/markets/fear-and-greed')

# ---- Cell ----
# idx = driver.find_element(By.CLASS_NAME,
#                           value='market-fng-gauge__dial-number-value').text
# driver.close()
# idx = int(idx)

# print(idx)
