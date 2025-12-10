# English filename: 3_collection_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/5일차 머신러닝분석을 위한 금융데이터 생성/3. [프로젝트] 주요 재무지표 수집 및 가공하기_wget.py
# Original filename: 3. [프로젝트] 주요 재무지표 수집 및 가공하기_wget.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/web_crawling_korea_data.zip && unzip -n web_crawling_korea_data.zip

# ---- Cell ----
!pip install --upgrade opendartreader

# ---- Cell ----
import OpenDartReader
my_api = "9aebac0ee49b223f60f32c0aa868402bfefa5fe8"
dart = OpenDartReader(my_api)

# ---- Cell ----
import pandas as pd

stock_list = pd.read_csv(
    "데이터/종목정보.txt",
    encoding="euc-kr",
    sep="\t",
    usecols=["Name", "Symbol"],
    dtype=str)

# ---- Cell ----


# ---- Cell ----
report = dart.finstate("005380", 2020)
display(report[["fs_nm", "account_nm", "thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"]])

# ---- Cell ----
import numpy as np
import pandas as pd

def find_fins_ind_list(stock_code, stock_name, year, ind_list):
    try: # 데이터 가져오기
        report = None
        report = dart.finstate(stock_code, year)
    except:
        pass

    if report is None:  # 리포트가 없다면 (참고: 리포트가 없으면 None을 반환함)
        # 리포트가 없으면 당기, 전기, 전전기 값 모두 제거
        data = [[stock_name, year] + [np.nan] * len(ind_list)]
        data.append([stock_name, year - 1] + [np.nan] * len(ind_list))
        data.append([stock_name, year - 2] + [np.nan] * len(ind_list))

    else:
        report = report[report["account_nm"].isin(ind_list)]  # 관련 지표로 필터링
        if sum(report["fs_nm"] == "연결재무제표") > 0:
            # 연결재무제표 데이터가 있으면 연결재무제표를 사용
            report = report.loc[report["fs_nm"] == "연결재무제표"]
        else:
            # 연결재무제표 데이터가 없으면 일반재무제표를 사용
            report = report.loc[report["fs_nm"] == "재무제표"]
        data = []
        for y, c in zip([year, year - 1, year - 2],
                        ["thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"]):
            record = [stock_name, y]
            for ind in ind_list:
                # account_nm이 indic인 행의 c 컬럼 값을 가져옴
                if sum(report["account_nm"] == ind) > 0:
                    value = report.loc[report["account_nm"] == ind, c].iloc[0]
                else:
                    value = np.nan
                record.append(value)
            data.append(record)

    return pd.DataFrame(data, columns=["기업", "연도"] + ind_list)

# ---- Cell ----
ind_list = ['자산총계', '부채총계', '자본총계', '매출액', '영업이익', '당기순이익(손실)']
display(find_fins_ind_list("005930", "삼성전자", 2020, ind_list))

# ---- Cell ----
import time
data = pd.DataFrame() # 이 데이터프레임에 각각의 데이터를 추가할 예정
for code, name in stock_list[['Symbol', 'Name']].iloc[:30].values:
# 전체 돌리고 싶으면 아래코드 주석 해제하고 위의 코드를 주석 처리
#for code, name in stock_list[['Symbol', 'Name']].values:
    print(name)
    for year in [2015, 2018, 2020]:
        try:
            result = find_fins_ind_list(code, name, year, ind_list) # 재무지표 데이터
            data = pd.concat([data, result], axis = 0, ignore_index = True) # data에 부착
            time.sleep(0.5)
        except Exception as e:
            print(f"Error: {e}")


# ---- Cell ----
data.drop_duplicates(inplace = True)
data.sort_values(by = ['기업', '연도'], inplace = True)

# ---- Cell ----
display(data.head(10))

# ---- Cell ----
# 숫자로 모두 변환
def convert_str_to_float(value):
    if type(value) == float: # nan의 자료형은 float임
        return value
    elif value == '-': # -로 되어 있으면 0으로 변환
        return 0
    else:
        return float(value.replace(',', ''))

for ind in ind_list:
    data[ind] = data[ind].apply(convert_str_to_float)

# ---- Cell ----
display(data.head())

# ---- Cell ----
data['부채비율'] = data['부채총계'] / data['자본총계'] * 100
display(data['부채비율'].head())

# ---- Cell ----
data['매출액증가율'] = (data['매출액'].diff() / data['매출액'].shift(1)) * 100
data.loc[data['연도'] == 2013, '매출액증가율'] = np.nan

# ---- Cell ----
data['영업이익증가율'] = (data['영업이익'].diff() / data['영업이익'].shift(1)) * 100
data.loc[data['연도'] == 2013, '영업이익증가율'] = np.nan

data['당기순이익증가율'] = (data['당기순이익(손실)'].diff() / data['당기순이익(손실)'].shift(1)) * 100
data.loc[data['연도'] == 2013, '당기순이익증가율'] = np.nan

# ---- Cell ----
data = data.replace({np.inf:np.nan, -np.inf: np.nan})

# ---- Cell ----
data.head()

# ---- Cell ----
col="매출액"
data[col+ "_상태"] = np.nan # 상태를 결측으로 초기화 "매출액_상태"
value = data[col].values
cur_value = value[1:]
pre_value = value[:-1]
data.head()

# ---- Cell ----
cond1 = (cur_value > 0) & (pre_value > 0)
cond1

# ---- Cell ----
# 흑자지속
cond1 = np.insert(cond1, 0, np.nan)
cond1

# ---- Cell ----
# 상태를 나타내는 함수 정의
def add_state(data, col):
    # 상태를 문자열 데이터 타입으로 초기화
    data[col + "_상태"] = pd.Series(dtype='string') # Initialize with string dtype

    value = data[col].values
    cur_value = value[1:]
    pre_value = value[:-1]
    # 흑자지속
    cond1 = (cur_value > 0) & (pre_value > 0)
    cond1 = np.insert(cond1, 0, False) # Use False for boolean indexing
    # 적자지속
    cond2 = (cur_value <= 0) & (pre_value <= 0)
    cond2 = np.insert(cond2, 0, False) # Use False for boolean indexing
    # 흑자전환
    cond3 = (cur_value > 0) & (pre_value <= 0)
    cond3 = np.insert(cond3, 0, False) # Use False for boolean indexing
    # 적자전환
    cond4 = (cur_value <= 0) & (pre_value > 0)
    cond4 = np.insert(cond4, 0, False) # Use False for boolean indexing

    # 조건에 따른 변환
    data.loc[cond1, col + "_상태"] = "흑자지속"
    data.loc[cond2, col + "_상태"] = "적자지속"
    data.loc[cond3, col + "_상태"] = "흑자전환"
    data.loc[cond4, col + "_상태"] = "적자전환"

    # 첫 번째 행의 상태를 np.nan으로 설정
    data.loc[data.index[0], col + "_상태"] = np.nan

# ---- Cell ----
add_state(data, "매출액")
add_state(data, "영업이익")
add_state(data, "당기순이익(손실)")

# ---- Cell ----
data.head()

# ---- Cell ----
data['ROA'] = (data['당기순이익(손실)'] / data['자산총계']) * 100

# ---- Cell ----
average_equity = data['자본총계'].rolling(2).mean() # 평균 자기 자본
data['ROE'] = (data['당기순이익(손실)'] / average_equity) * 100
data.loc[data['연도'] == 2013, 'ROE'] = np.nan

# ---- Cell ----
data.head()

# ---- Cell ----
# data.to_csv("데이터/주요재무지표_수정.csv", index = False, encoding = "euc-kr")

# ---- Cell ----

