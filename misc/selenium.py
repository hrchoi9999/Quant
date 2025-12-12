# English filename: 3_selenium_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/3일차 맞춤형 펀드 설계 및 운용/3.selenium.py
# Original filename: 3.selenium.py

# ---- Cell ----
!sudo apt-get install -y fonts-nanum
!sudo fc-cache -fv
!rm ~/.cache/matplotlib -rf


# ---- Cell ----
!pip install selenium

# ---- Cell ----
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
# from webdriver_manager.chrome import ChromeDriverManager
import time
from bs4 import BeautifulSoup

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
# driver = webdriver.Chrome(options=chrome_options)

# ---- Cell ----
driver = webdriver.Chrome(options=chrome_options)

# ---- Cell ----
url = 'https://www.naver.com/'
driver.get(url)
driver.page_source[1:1000]

# ---- Cell ----
driver.window_handles

# ---- Cell ----
driver.find_element(By.LINK_TEXT , value = '뉴스').click()

# ---- Cell ----
driver.window_handles

# ---- Cell ----
# driver.switch_to.window(window_name="닫고싶은탭_id입력")

# ---- Cell ----
# 마지막에 연 탭으로 이동
last_tab = driver.window_handles[-1]
driver.switch_to.window(window_name=last_tab)
time.sleep(5)

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
# driver.switch_to.window(window_name="닫고싶은탭_id입력")
# driver.close()

# ---- Cell ----
driver.window_handles

# ---- Cell ----
# 원래의 탭으로 이동
Orignial_tab = driver.window_handles[0]
driver.switch_to.window(window_name=Orignial_tab)
time.sleep(5)

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
# driver.back()

# ---- Cell ----
url = 'https://www.naver.com/'
driver.get(url)
driver.page_source[1:1000]

# ---- Cell ----
driver.find_element(By.CLASS_NAME, value = 'search_input').send_keys('퀀트 투자 포트폴리오 만들기')

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
driver.find_element(By.CLASS_NAME, value = 'btn_search').send_keys(Keys.ENTER)

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
driver.find_element(By.CLASS_NAME, value = 'box_window').clear()
driver.find_element(By.CLASS_NAME, value = 'box_window').send_keys('이현열 퀀트')
driver.find_element(By.CLASS_NAME, value = 'bt_search').click()

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
# driver.current_url

# ---- Cell ----
/html/body/div[3]/div[1]/div/div[2]/div[1]/div/div[1]/div/div[1]/div[1]/a

# ---- Cell ----
driver.find_element(By.XPATH, value = '/html/body/div[3]/div[1]/div/div[2]/div[1]/div/div[1]/div/div[1]/div[1]/a').click()

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
/html/body/div[3]/div[2]/div[1]/div[1]/div[1]/div[1]/div/div[1]/a[2]

# ---- Cell ----
# /html/body/div[3]/div[2]/div[1]/div[1]/div[1]/div[2]/ul/li[1]/div/div/a[2]

# ---- Cell ----
driver.find_element(By.CLASS_NAME, value = 'option_filter').click()
driver.find_element(By.XPATH, value = '/html/body/div[3]/div[2]/div/div[1]/div[1]/div[1]/div/div[1]/a[2]').click()

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')

# ---- Cell ----
prev_height = driver.execute_script('return document.body.scrollHeight')

# ---- Cell ----
prev_height

# ---- Cell ----
prev_height = driver.execute_script('return document.body.scrollHeight')

while True:
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    time.sleep(2)

    curr_height = driver.execute_script('return document.body.scrollHeight')
    if curr_height == prev_height:
        break
    prev_height = curr_height

# ---- Cell ----
driver.save_screenshot("test.png")

# ---- Cell ----
html = BeautifulSoup(driver.page_source, 'lxml')
txt = html.find_all(class_ ="sds-comps-text sds-comps-text-ellipsis sds-comps-text-ellipsis-1 sds-comps-text-type-headline1 sds-comps-text-weight-sm")
txt_list = [i.get_text() for i in txt]

txt_list[0:50]

# ---- Cell ----
driver.quit()

# ---- Cell ----
import re

data = '동 기업의 매출액은 전년 대비 29.2% 늘어났습니다.'
re.findall('\d+.\d+%', data)

# ---- Cell ----
import re

p = re.compile('[a-z]+')
type(p)

# ---- Cell ----
m = p.match('pyThon')
print(m)

# ---- Cell ----
m.group()

# ---- Cell ----
m = p.match('Use python')
print(m)

# ---- Cell ----
m = p.match('PYTHON')
print(m)

# ---- Cell ----
p = re.compile('[가-힣]+')
m = p.match('파이썬')
print(m)

# ---- Cell ----
p = re.compile('[a-z]+')
m = p.search('python')
print(m)

# ---- Cell ----
m = p.search('Use python')
print(m)

# ---- Cell ----
p = re.compile('[a-zA-Z]+')
m = p.findall('Life is too short, You need Python.')
print(m)

# ---- Cell ----
p = re.compile('[a-zA-Z]+')
m = p.finditer('Life is too short, You need Python.')
print(m)

# ---- Cell ----
for i in m:
    print(i)

# ---- Cell ----
num = """r\n\t\t\t\t\t\t\t\r\n\t\t\t\t\t\t\t\t15\r\n\t\t\t\t\t\t\t\t23\r\n\t\t\t\t\t\t\t\t29\r\n\t\t\t\t\t\t\t\t34\r\n\t\t\t\t\t\t\t\t40\r\n\t\t\t\t\t\t\t\t44\r\n\t\t\t\t\t\t\t\r\n\t\t\t\t\t\t"""

# ---- Cell ----
import re

p = re.compile('[0-9]+')
m = p.findall(num)
print(m)

# ---- Cell ----
dt = '> 오늘의 날짜는 2022.12.31 입니다.'

# ---- Cell ----
p = re.compile('[0-9]+.[0-9]+.[0-9]+')
p.findall(dt)

# ---- Cell ----
p = re.compile('[0-9]+')
m = p.findall(dt)
print(m)

# ---- Cell ----
'-'.join(m)

# ---- Cell ----

