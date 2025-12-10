# English filename: 2_collection_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/5일차 머신러닝분석을 위한 금융데이터 생성/2. [프로젝트] 배당 정보 수집 및 가공하기_wget.py
# Original filename: 2. [프로젝트] 배당 정보 수집 및 가공하기_wget.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/web_crawling_korea_data.zip && unzip -n web_crawling_korea_data.zip

# ---- Cell ----
!pip install --upgrade opendartreader tables

# ---- Cell ----
import OpenDartReader
my_api = "9aebac0ee49b223f60f32c0aa868402bfefa5fe8"
dart = OpenDartReader(my_api)

# ---- Cell ----
# SK하이닉스
SK_report = dart.report("SK하이닉스", "배당", 2020, "11011")
display(SK_report)

# ---- Cell ----
# 삼성전자
SAMSUNG_report = dart.report("삼성전자", "배당", 2020, "11011")
display(SAMSUNG_report)

# ---- Cell ----
# 3S
threeS_report = dart.report("3S", "배당", 2020, "11011")
display(threeS_report)

# ---- Cell ----
import numpy as np
def find_div_and_EPS(stock, year):
    report = dart.report(stock, "배당", year, "11011") # 데이터 가져오기
    output = dict() # 출력 초기화
    if report is None: # 리포트가 없다면 (참고: 리포트가 없으면 None을 반환함)
        output['주당배당금'] = np.nan, np.nan, np.nan
        output['주당순이익'] = np.nan, np.nan, np.nan

    else:
        # 주당배당금 (div) 관련 행 필터링
        div_row = report.loc[(report['se'] == '주당 현금배당금(원)')].iloc[0]  # 데이털 프레임이 아니라 시리즈 만들기 위해
        #print(div_row)

        # 전전기(second previous: spre), 전기(previous: pre), 당기(current: cur)
        # 하이픈 0으로 변환 및 콤마 제거
        cur_div = int(div_row['thstrm'].replace('-', '0').replace(',', ''))
        pre_div = int(div_row['frmtrm'].replace('-', '0').replace(',', ''))
        spre_div = int(div_row['lwfr'].replace('-', '0').replace(',', ''))
        output['주당배당금'] = spre_div, pre_div, cur_div

        # 주당순이익 (EPS) 관련 행 필터링
        EPS_row = report.loc[(report['se'].str.contains('주당순이익'))].iloc[0]  # 데이터 프레임이 아니라 시리즈로 나오게 함

        # 하이픈 0으로 변환 및 콤마 제거
        cur_EPS = int(EPS_row['thstrm'].replace('-', '0').replace(',', ''))
        pre_EPS = int(EPS_row['frmtrm'].replace('-', '0').replace(',', ''))
        spre_EPS = int(EPS_row['lwfr'].replace('-', '0').replace(',', ''))
        output['주당순이익'] = spre_EPS, pre_EPS, cur_EPS

    return output

# ---- Cell ----
print(find_div_and_EPS("삼성전자", 2020))
#print(find_div_and_EPS("SK하이닉스", 2020))

# ---- Cell ----
print(find_div_and_EPS("SK하이닉스", 2020))

# ---- Cell ----
# import time
# import pandas as pd

# stock_list = pd.read_csv("데이터/stock_info.csv")
# stock_name_list = stock_list["Name"].values

# ---- Cell ----
import time
import pandas as pd

stock_list = pd.read_csv("데이터/stock_info.csv")
stock_name_list = stock_list["Name"].values
div_data = []
EPS_data = []

# for idx, stock_name in enumerate(stock_name_list):
# 시간을 위해 10개만 돌려본다.
stock_name_list = ['삼성전자', '두산']
for idx, stock_name in enumerate(stock_name_list):
    print(idx + 1, "/", len(stock_name_list))  # 현재까지 진행된 상황 출력
    # 레코드 초기화
    div_record = [stock_name]
    EPS_record = [stock_name]
    # for year in [2015, 2018, 2020]:
    for year in [2018, 2020]:
        while True:
            try:
                output = find_div_and_EPS(stock_name, year)  # 배당 정보 가져오기
                time.sleep(0.5)  # 0.5초씩 재움
                break
            except:
                time.sleep(1 * 1)
        try:
            # 주당 배당금 정리
            spre_divs, pre_divs, cur_divs = output["주당배당금"]
            if year != 2020:
                div_record += [spre_divs, pre_divs, cur_divs]
            else:
                div_record += [pre_divs, cur_divs]
            # 주당 순이익 정리
            spre_EPS, pre_EPS, cur_EPS = output["주당순이익"]
            if year != 2020:
                EPS_record += [spre_EPS, pre_EPS, cur_EPS]
            else:
                EPS_record += [pre_EPS, cur_EPS]
        except:
            pass
    div_data.append(div_record)
    EPS_data.append(EPS_record)

# ---- Cell ----
div_data

# ---- Cell ----
EPS_data

# ---- Cell ----
columns = ["stock_name", "2016", "2017", "2018", "2019", "2020"]
div_data = pd.DataFrame(div_data, columns = columns)
EPS_data = pd.DataFrame(EPS_data, columns = columns)

# div_data.to_csv("데이터/주당배당금.csv", encoding = "euc-kr", index = False)
# EPS_data.to_csv("데이터/주당순이익.csv", encoding = "euc-kr", index = False)

# ---- Cell ----
div_data

# ---- Cell ----
EPS_data

# ---- Cell ----
import pandas as pd
sub_due_data = [] # 제출 마감일을 담을 데이터
for settle_month in range(1, 13): # 결산월
    for year in range(2013, 2021): # 사업연도
        # 사업연도경과후 기준일 계산
        if settle_month < 12:
            after_bs_year_day = pd.to_datetime("{}-{}-1".format(year, settle_month+1))  # 예: 결산월 1월 2013년 => 2013-2-1
        else:
            after_bs_year_day = pd.to_datetime("{}-1-1".format(year+1)) #예: 12월 2013년 -> 2014-1-1
        # 90일을 더해서 제출 마감일을 구한다.
        due_date = after_bs_year_day + pd.to_timedelta(90, "D")
        sub_due_data.append([settle_month, year, due_date])
sub_due_data = pd.DataFrame(sub_due_data, columns = ["결산월", "사업연도", "제출마감일"])
#sub_due_data.to_csv("데이터/사업보고서_제출마감일.csv", index = False, encoding = "euc-kr")

# ---- Cell ----
sub_due_data.head()

# ---- Cell ----
def find_closest_stock_price(sp_data, date):
    date = pd.to_datetime(date) # 날짜 자료형으로 변환
    # 주가 데이터를 벗어나는 범위의 날짜가 입력되면 결측을 반환
    if sp_data['Date'].max() < date:
        return np.nan
    else:
        while True:
            # date와 같은 날짜가 Date에 있으면
            if sum(sp_data['Date'] == date) > 0:
                # 해당 날짜의 종가를 저장
                value = sp_data.loc[sp_data['Date'] == date, 'Close'].iloc[0]
                break
            else: # date와 같은 날짜의 Date가 없으면, 하루 증가
                date += pd.to_timedelta(1, 'D')
        return value

# ---- Cell ----
sp_data = pd.read_csv("데이터/주가데이터/삼성전자.csv")
sp_data['Date'] = pd.to_datetime(sp_data['Date'])
date = "2020-04-06" # 날짜 정의
print(find_closest_stock_price(sp_data, date))

# ---- Cell ----
sp_data = pd.read_csv("데이터/주가데이터/삼성전자.csv")
sp_data.tail(10)

# ---- Cell ----
sp_data['Date'] = pd.to_datetime(sp_data['Date'])
date = "2021-09-18" # 날짜 정의
print(find_closest_stock_price(sp_data, date))

# ---- Cell ----



# ---- Cell ----
display(EPS_data)

# ---- Cell ----
print(stock_list.loc[stock_list['Name'] == "삼성전자", "SettleMonth"].iloc[0])

# ---- Cell ----
display(sub_due_data[(sub_due_data['결산월'] == 12) & (sub_due_data['사업연도'] == 2017)].iloc[0])

# ---- Cell ----
settle_month_dict = stock_list.set_index('Name')['SettleMonth']
print(settle_month_dict['삼성전자'])


# ---- Cell ----
settle_month_dict = settle_month_dict.apply(lambda x:int(x[:-1])).to_dict()  # 월 문자제거
print(settle_month_dict['삼성전자'])

# ---- Cell ----
sub_due_dict = sub_due_data.set_index(['결산월', '사업연도'])['제출마감일'].to_dict()
print(sub_due_dict[12, 2017])

# ---- Cell ----
settle_month_dict = stock_list.set_index('Name')['SettleMonth']
settle_month_dict = settle_month_dict.apply(lambda x:int(x[:-1])).to_dict()  # 월 문자제거
sub_due_dict = sub_due_data.set_index(['결산월', '사업연도'])['제출마감일'].to_dict()

# ---- Cell ----
print(settle_month_dict['삼성전자'])
print(sub_due_dict[12, 2017])

# ---- Cell ----
EPS_data

# ---- Cell ----
import os
sp_data = []
for sn in EPS_data["stock_name"].values: # EPS_data의 종목명을 순회하면서
    record = [sn]
    if sn + ".csv" not in os.listdir("데이터/주가데이터"):
        # 주가 데이터 폴더 내에 해당 파일이 없으면 전부 결측으로 채움
        record += [np.nan] * (len(EPS_data.columns) - 1)
    else:
        # 주가 데이터 불러오기
        sn_sp_data = pd.read_csv("데이터/주가데이터/{}.csv".format(sn),
                                 parse_dates=["Date"])
        settle_month = settle_month_dict[sn]
        for year in range(2016, 2021):
            # 제출 마감일의 주가 찾기
            sub_date = sub_due_dict[settle_month, year]
            sp = find_closest_stock_price(sn_sp_data, sub_date)
            record.append(sp)
    sp_data.append(record)
sp_data = pd.DataFrame(sp_data, columns=EPS_data.columns)

# ---- Cell ----
sp_data

# ---- Cell ----
for i in range(2016, 2021):
  print (i)

# ---- Cell ----
PER_data = sp_data.values[:, 1:] / EPS_data.replace(0, np.nan).values[:, 1:]
PER_data = pd.DataFrame(PER_data, columns = EPS_data.columns[1:])
PER_data['stock_name'] = EPS_data['stock_name']

# ---- Cell ----
PER_data

# ---- Cell ----


# ---- Cell ----

