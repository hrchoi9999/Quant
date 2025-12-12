# English filename: 2_crawl_basic_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/3일차 맞춤형 펀드 설계 및 운용/2. crawl_basic_clear.py
# Original filename: 2. crawl_basic_clear.py

# ---- Cell ----
import requests as rq

url = 'https://quotes.toscrape.com/'
quote = rq.get(url)

print(quote)

# ---- Cell ----
quote.content[:1000]

# ---- Cell ----
from bs4 import BeautifulSoup

quote_html = BeautifulSoup(quote.content, 'html.parser')
quote_html.head()

# ---- Cell ----
quote_div = quote_html.find_all('div', class_='quote')

quote_div[0]

# ---- Cell ----
quote_span = quote_div[0].find_all('span', class_='text')

quote_span

# ---- Cell ----
quote_span[0].text

# ---- Cell ----
quote_div = quote_html.find_all('div', class_ = 'quote')

[i.find_all('span', class_ ='text')[0].text for i in quote_div]

# ---- Cell ----
quote_text = quote_html.select('div.quote > span.text')

quote_text

# ---- Cell ----
quote_text_list = [i.text for i in quote_text]

quote_text_list

# ---- Cell ----
quote_author = quote_html.select('div.quote > span > small.author')
quote_author_list = [i.text for i in quote_author]

quote_author_list

# ---- Cell ----
quote_link = quote_html.select('div.quote > span > a')

quote_link

# ---- Cell ----
quote_link[0]['href']

# ---- Cell ----
['https://quotes.toscrape.com' + i['href'] for i in quote_link]

# ---- Cell ----
import requests as rq
from bs4 import BeautifulSoup
import time

text_list = []
author_list = []
infor_list = []

for i in range(1, 100):

    url = f'https://quotes.toscrape.com/page/{i}/'
    quote = rq.get(url)
    quote_html = BeautifulSoup(quote.content, 'html.parser')

    quote_text = quote_html.select('div.quote > span.text')
    quote_text_list = [i.text for i in quote_text]

    quote_author = quote_html.select('div.quote > span > small.author')
    quote_author_list = [i.text for i in quote_author]

    quote_link = quote_html.select('div.quote > span > a')
    qutoe_link_list = ['https://quotes.toscrape.com' + i['href'] for i in quote_link]

    if len(quote_text_list) > 0:

        text_list.extend(quote_text_list)
        author_list.extend(quote_author_list)
        infor_list.extend(qutoe_link_list)
        time.sleep(1)

    else:
        break

# ---- Cell ----
import pandas as pd

pd.DataFrame({'text': text_list, 'author': author_list, 'infor': infor_list})

# ---- Cell ----
import requests as rq
from bs4 import BeautifulSoup

url = 'https://finance.naver.com/news/news_list.nhn?mode=LSS2D&section_id=101&section_id2=258'
data = rq.get(url)
html = BeautifulSoup(data.content, 'html.parser')
html_select = html.select('dl > dd.articleSubject > a')

html_select[0:3]

# ---- Cell ----
html_select[0]['title']

# ---- Cell ----
[i['title'] for i in html_select]

# ---- Cell ----
import pandas as pd
import requests

url = 'https://en.wikipedia.org/wiki/List_of_countries_by_stock_market_capitalization'

# Add a User-Agent header to the request
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# Fetch the HTML content with the headers
response = requests.get(url, headers=headers)

# Use the HTML content with read_html
tbl = pd.read_html(response.text)

tbl[1].head()

# ---- Cell ----
import requests as rq
from bs4 import BeautifulSoup
import pandas as pd

url = 'https://kind.krx.co.kr/disclosure/todaydisclosure.do'
payload = {
    'method': 'searchTodayDisclosureSub',
    'currentPageSize': '15',
    'pageIndex': '1',
    'orderMode': '0',
    'orderStat': 'D',
    'marketType': '2',
    'forward': 'todaydisclosure_sub',
    'chose': 'S',
    'todayFlag': 'N',
    'selDate': '2025-10-17'
}

data = rq.post(url, data=payload)
html = BeautifulSoup(data.content, 'html.parser')
print(html)

# ---- Cell ----
html_unicode = html.prettify()
tbl = pd.read_html(html.prettify())

tbl[0]
