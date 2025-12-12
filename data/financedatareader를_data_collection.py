# English filename: 2_1_financedatareader를_data_collection_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/1일차 머신러닝 분석을 위한 알파 팩터 수집 및 작성/1. 금융데이터수집/2-1. FinanceDataReader를 이용한 금융 데이터 수집_clear.py
# Original filename: 2-1. FinanceDataReader를 이용한 금융 데이터 수집_clear.py

# ---- Cell ----
!pip install finance-datareader

# ---- Cell ----
import FinanceDataReader as fdr

# ---- Cell ----
KP_stock_list = fdr.StockListing("KOSPI") # 코스피 종목 목록
display(KP_stock_list)

# ---- Cell ----
type(KP_stock_list)

# ---- Cell ----
sp_data = fdr.DataReader("005380", "2020-10-01", "2023-05-31")
display(sp_data)

# ---- Cell ----
nasdaq_stock_list = fdr.StockListing("NASDAQ")
display(nasdaq_stock_list)

# ---- Cell ----
sp_data = fdr.DataReader('MMM', "2020-10-01", "2022-09-30")
display(sp_data)

# ---- Cell ----
KP_idx_data = fdr.DataReader("KS11", "2010-01-01", "2022-6-10")
display(KP_idx_data)

# ---- Cell ----
DJI_idx_data = fdr.DataReader("DJI", "2010-01-01", "2023-6-10")
display(DJI_idx_data)

# ---- Cell ----
display(fdr.DataReader("CL", "2020-01-01", "2023-6-10")) # WTI유 선물

# ---- Cell ----
display(fdr.DataReader("USD/KRW", "2020-01-01", "2023-06-10")) #달러/원 환율

# ---- Cell ----

