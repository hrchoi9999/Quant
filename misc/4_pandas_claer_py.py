# English filename: 4_pandas_claer_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/3일차 맞춤형 펀드 설계 및 운용/4 pandas_claer.py
# Original filename: 4 pandas_claer.py

# ---- Cell ----
import pandas as pd     # pandas 라이브러리를 pd 이름으로 호출

# ---- Cell ----
prices = [1000, 1010, 1020]     # 주가를 담아놓은 리스트 생성

# ---- Cell ----
dates = pd.date_range('20181201', periods=3)     # date_range 함수를 이용해 날짜 생성
dates

# ---- Cell ----
pd.date_range('20181201', '20181231', freq='W')

# ---- Cell ----
s = pd.Series(prices, index=dates)     # 주가를 데이터로, 날짜를 인덱스로 하는 Series 생성
s

# ---- Cell ----
s2 = pd.Series(prices)     # 인덱스를 지정하지 않은 Series
s2

# ---- Cell ----
s2[3] = 1030     # Series에 데이터 추가
s2

# ---- Cell ----
print('123' + '123')
print(123 + 123)

# ---- Cell ----
s[pd.to_datetime('2018-12-04')] = 1030     # 인덱스를 이용한 데이터 추가
s

# ---- Cell ----
s[2]     # 배열 스타일로 데이터 추출

# ---- Cell ----
s['2018-12-03']     # 인덱스를 이용한 데이터 추출

# ---- Cell ----
prices = {'A전자' : [1000, 1010, 1020],
          'B화학' : [2000, 2010, 2020],
          'C금융' : [3000, 3010, 3020]}
df1 = pd.DataFrame(prices)
df1

# ---- Cell ----
df2 = pd.DataFrame(prices, index=dates)     # 인덱스가 있는 DataFrame
df2

# ---- Cell ----
df2.iloc[0]     # 행 선택

# ---- Cell ----
df2.iloc[:, 0]     # 열 선택

# ---- Cell ----
df2.iloc[0, 0]     # 행, 열 지정

# ---- Cell ----
df2.loc['2018-12-01']

# ---- Cell ----
df2.loc[:, 'A전자']

# ---- Cell ----
df2.loc['2018-12-01', 'A전자']

# ---- Cell ----
df2['A전자']     # 열 선택

# ---- Cell ----
df2.A전자     # df2['A전자']  와 동일

# ---- Cell ----
df2['A전자']['2018-12-01']

# ---- Cell ----
df2.loc[:, 'A전자']['2018-12-01']

# ---- Cell ----
df2['D엔터'] = [4000, 4010, 4020]     # DataFrame에 열 추가
df2

# ---- Cell ----
df2['E텔레콤'] = s     # Series로 부터 DataFrame 열 추가
df2

# ---- Cell ----
s.name = 'F소프트'
s

# ---- Cell ----
df2 = pd.concat([df2, s], axis=1)
df2

# ---- Cell ----
df3 = df2.iloc[0]
df3 = df3 + 60
df3.name = pd.to_datetime('20181207')
df3

# ---- Cell ----
type(df3)

# ---- Cell ----
df2 = pd.concat([df2,df3.to_frame().T])
df2

# ---- Cell ----
df3 = df2.iloc[0] + 50
df3.name = pd.to_datetime('20181206')
df2 = pd.concat([df2, df3.to_frame().T])
df2

# ---- Cell ----
df2 = df2.sort_index(axis=0)     # 날짜 순으로 인덱스 재정렬
df2

# ---- Cell ----
help(pd.DataFrame.drop)

# ---- Cell ----
'''
    삭제한 DataFrame을 저장하지 않으므로
    현재 결과값에서는 삭제된것처럼 보이나
    df2에 삭제한 결과가 저장되지 않음에 주의
'''
df2.drop(pd.to_datetime('2018-12-06'))     # 행 삭제

# ---- Cell ----
df2.drop([pd.to_datetime('2018-12-02'), pd.to_datetime('2018-12-06')])     # 여러 행 삭제

# ---- Cell ----
df2.drop('D엔터', axis=1)     # 열 삭제

# ---- Cell ----
df2.drop(['C금융', 'E텔레콤'], axis=1)

# ---- Cell ----
df2.head()     # DataFrame의 최초 5줄 조회

# ---- Cell ----
df2.tail(3)     # DataFrame의 마지막 3줄 조회

# ---- Cell ----
df2.iloc[2]     # 인덱스 위치번호(iloc: Index Location)로 슬라이싱

# ---- Cell ----
df2.loc['2018-12-03']     # 인덱스 이름으로 슬라이싱 시 iloc 대신 loc 사용

# ---- Cell ----
df2.iloc[1:3]     # 행 다중 선택

# ---- Cell ----
df2.loc['2018-12-02':'2018-12-03']     # 행 다중 선택

# ---- Cell ----
df2[1:3]     # 행 다중 선택 시 NumPy 배열처럼 슬라이싱 가능

# ---- Cell ----
df2['C금융']    # 열 슬라이싱은 열 이름으로 가능

# ---- Cell ----
df2.iloc[1:3, 2]     # 위치 번호로 행, 열 선택

# ---- Cell ----
df2.loc['2018-12-02':'2018-12-03', 'C금융']    # 이름으로 행, 열 선택

# ---- Cell ----
df2['E텔레콤'] * 10     # DataFrame의 스칼라 연산

# ---- Cell ----
df2.sum(axis=0)     # 행간 연산, 즉 열별 합산

# ---- Cell ----
df2.median(axis=1)     # 열간 연산, 즉 행별 합산

# ---- Cell ----
df2.describe()     # 통계 요약

# ---- Cell ----
df2

# ---- Cell ----
df2.dropna()     # NaN 제거

# ---- Cell ----
df2.fillna(0)     # NaN을 0으로 바꿈

# ---- Cell ----
df2.fillna(method='ffill')     # NaN을 앞의 값으로 채움

# ---- Cell ----
df2.fillna(method='bfill')     # NaN을 뒤의 값으로 채움

# ---- Cell ----

