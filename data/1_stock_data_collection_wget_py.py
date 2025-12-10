# English filename: 1_stock_data_collection_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/5일차 머신러닝분석을 위한 금융데이터 생성/1. [프로젝트] 코스피와 코스닥 전종목 주가데이터 수집_wget.py
# Original filename: 1. [프로젝트] 코스피와 코스닥 전종목 주가데이터 수집_wget.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/web_crawling_korea_data.zip && unzip -n web_crawling_korea_data.zip

# ---- Cell ----
!pip install finance-datareader

# ---- Cell ----
import FinanceDataReader as fdr

# ---- Cell ----
# 종목 목록 가져오기
stock_list = fdr.StockListing('KRX')

# ---- Cell ----
stock_list.head(10)

# ---- Cell ----
# 코넥스 종목 제외
stock_list = stock_list.loc[stock_list['Market'] != "KONEX"]

# ---- Cell ----
# 종목 정보 내보내기 (csv로 저장하면 0으로 시작하는 종목 정보가 깨지는 경우가 있어 텍스트로 저장)
# stock_list.to_csv("데이터/stock_info.csv", index=False)

# ---- Cell ----
# 전 종목 순회 및 데이터 저장
import time
from tqdm import tqdm
# for code, name in tqdm(stock_list[['Code', "Name"]].values):
# 시간상 10개만 돌려봅니다.
for code, name in tqdm(stock_list[['Code', "Name"]].values[:10]):
    # print(code, name)
    while True:
        try:
            data = fdr.DataReader(code, "2011-01-01", "2023-05-31")
            if len(data) > 300:
                print(data)
                # data.to_csv("데이터/주가데이터/{}.csv".format(name))
            time.sleep(1)
            break # 정상적으로 데이터 저장까지 완료되면 반복문에서 빠져나감
        except:
            time.sleep(10 * 60) # 연결이 끊어지면 10분 재움

# ---- Cell ----

