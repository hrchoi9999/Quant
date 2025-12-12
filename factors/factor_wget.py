# English filename: factor_wget_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/6일차 기본적 팩터모델의 이해/factor_wget.py
# Original filename: factor_wget.py

# ---- Cell ----
!sudo apt-get install -y fonts-nanum
!sudo fc-cache -fv
!rm ~/.cache/matplotlib -rf

import matplotlib.pyplot as plt

plt.rc('font', family='NanumBarunGothic')
# 여기까지 실행한 다음에 다시실행 해주세요.

# ---- Cell ----
!pip install pymysql
!pip install --upgrade 'sqlalchemy<2.0'

# ---- Cell ----
!apt-get update
!apt-get install mysql-server -y

# ---- Cell ----
!service mysql start

# ---- Cell ----
!mysql -u root -e "CREATE DATABASE stock_db;"

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/stock_db.zip && unzip -n stock_db.zip

# ---- Cell ----
!mysql -u root stock_db < stock_db.sql

# ---- Cell ----
!mysql -u root -e "USE mysql; update user set plugin='mysql_native_password' where user='root'; flush privileges;"

# ---- Cell ----
import yfinance as yf
import pandas as pd

tickers = ['^KS11', '039490.KS']

all_data = {}
for ticker in tickers:
    all_data[ticker] = yf.download(ticker,
                                   start="2016-01-01",
                                   end='2021-12-31')

prices = pd.DataFrame({tic: data['Close'] for tic, data in all_data.items()})
ret = prices.pct_change().dropna()

# ---- Cell ----
import statsmodels.api as sm

ret['intercept'] = 1
reg = sm.OLS(ret[['039490.KS']], ret[['^KS11', 'intercept']]).fit()

# ---- Cell ----
reg.summary()

# ---- Cell ----
print(reg.params)

# ---- Cell ----
import pandas_datareader.data as web
from pandas_datareader.famafrench import get_available_datasets

datasets = get_available_datasets()
datasets[1:20]

# ---- Cell ----
import pandas_datareader.data as web

df_pbr = web.DataReader('Portfolios_Formed_on_BE-ME',
                        'famafrench',
                        start='1900-01-01')
df_pbr[0].head()

# ---- Cell ----
import matplotlib.pyplot as plt
from matplotlib import cm

plt.rc('font', family='NanumBarunGothic')
plt.rc('axes', unicode_minus=False)

df_pbr_vw = df_pbr[0].loc[:, ['Lo 20', 'Qnt 2', 'Qnt 3', 'Qnt 4', 'Hi 20']]
df_pbr_cum = (1 + df_pbr_vw / 100).cumprod()
df_pbr_cum.plot(figsize=(10, 6),
                colormap=cm.jet,
                legend='reverse',
                title='PBR별 포트폴리오의 누적 수익률')
plt.show()

# ---- Cell ----
import numpy as np

df_pbr_cum = np.log(1 + df_pbr_vw / 100).cumsum()
df_pbr_cum.plot(figsize=(10, 6),
                colormap=cm.jet,
                legend='reverse',
                title='PBR별 포트폴리오의 누적 수익률')
plt.show()

# ---- Cell ----
import pandas as pd


def factor_stat(df):
    n = len(df)

    ret_ari = (df / 100).mean(axis=0) * 12
    ret_geo = (1 + df / 100).prod() ** (12 / n) - 1
    vol = (df / 100).std(axis=0) * np.sqrt(12)
    sharp = ret_ari / vol

    stat = pd.DataFrame(
        [ret_ari, ret_geo, vol, sharp],
        index=['연율화 수익률(산술)', '연율화 수익률(기하)', '연율화 변동성', '샤프지수']).round(4)

    stat.iloc[0:3, ] = stat.iloc[0:3, ] * 100

    return stat

# ---- Cell ----
factor_stat(df_pbr_vw)

# ---- Cell ----
df_per = web.DataReader('Portfolios_Formed_on_E-P',
                        'famafrench',
                        start='1900-01-01')
df_per_vw = df_per[0].loc[:, ['Lo 20', 'Qnt 2', 'Qnt 3', 'Qnt 4', 'Hi 20']]
df_per_cum = np.log(1 + df_per_vw / 100).cumsum()
df_per_cum.plot(figsize=(10, 6),
                colormap=cm.jet,
                legend='reverse',
                title='PER별 포트폴리오의 누적 수익률')
plt.show()

# ---- Cell ----
df_pcr = web.DataReader('Portfolios_Formed_on_CF-P',
                        'famafrench',
                        start='1900-01-01')
df_pcr_vw = df_pcr[0].loc[:, ['Lo 20', 'Qnt 2', 'Qnt 3', 'Qnt 4', 'Hi 20']]
df_pcr_cum = np.log(1 + df_pcr_vw / 100).cumsum()
df_pcr_cum.plot(figsize=(10, 6),
                colormap=cm.jet,
                legend='reverse',
                title='PCR별 포트폴리오의 누적 수익률')
plt.show()

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd
import numpy as np

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
	ticker_list = pd.read_sql("""select * from kor_ticker
	where 기준일 = (select max(기준일) from kor_ticker)
		and 종목구분 = '보통주';
	""", con=conn.connection)

with engine.connect() as conn:
	value_list = pd.read_sql("""
		select * from kor_value
		where 기준일 = (select max(기준일) from kor_value);
		""", con=conn.connection)


	# ticker_list = pd.read_sql("""select * from kor_ticker
	# where 기준일 = (select max(기준일) from kor_ticker)
	# 	and 종목구분 = '보통주';
	# """, con=engine)

	# value_list = pd.read_sql("""
	# select * from kor_value
	# where 기준일 = (select max(기준일) from kor_value);
	# """, con=engine)


engine.dispose()

# ---- Cell ----
value_list.loc[value_list['값'] <= 0, '값'] = np.nan
value_pivot = value_list.pivot(index='종목코드', columns='지표', values='값')
data_bind = ticker_list[['종목코드', '종목명']].merge(value_pivot,
                                               how='left',
                                               on='종목코드')

data_bind.head()

# ---- Cell ----
value_rank = data_bind[['PER', 'PBR']].rank(axis=0)
value_sum = value_rank.sum(axis=1, skipna=False).rank()
data_bind.loc[value_sum <= 20, ['종목코드', '종목명', 'PER', 'PBR']]

# ---- Cell ----
import matplotlib.pyplot as plt
import seaborn as sns

value_list_copy = data_bind.copy()
value_list_copy['DY'] = 1 / value_list_copy['DY']
value_list_copy = value_list_copy[['PER', 'PBR', 'PCR', 'PSR', "DY"]]
value_rank_all = value_list_copy.rank(axis=0)
mask = np.triu(value_rank_all.corr())

mask = np.triu(value_rank_all.corr())
fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(value_rank_all.corr(),
            annot=True,
            mask=mask,
            annot_kws={"size": 16},
            vmin=0,
            vmax=1,
            center=0.5,
            cmap='coolwarm',
            square=True)
ax.invert_yaxis()
plt.show()

# ---- Cell ----
value_sum_all = value_rank_all.sum(axis=1, skipna=False).rank()
data_bind.loc[value_sum_all <= 20]

# ---- Cell ----
import pandas_datareader.data as web
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm

df_mom = web.DataReader('10_Portfolios_Prior_12_2',
                        'famafrench',
                        start='1900-01-01')
df_mom_vw = df_mom[0]
df_mom_cum = np.log(1 + df_mom_vw / 100).cumsum()

plt.rc('font', family='NanumBarunGothic')
plt.rc('axes', unicode_minus=False)

df_mom_cum.plot(figsize=(10, 6),
                colormap=cm.jet,
                legend='reverse',
                title='모멘텀별 포트폴리오의 누적 수익률')
plt.show()

# ---- Cell ----
factor_stat(df_mom_vw)

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
    ticker_list = pd.read_sql(
        """
        select * from kor_ticker
        where 기준일 = (select max(기준일) from kor_ticker)
            and 종목구분 = '보통주';
        """, con=conn.connection)

with engine.connect() as conn:
    price_list = pd.read_sql(
        """
        select 날짜, 종가, 종목코드
        from kor_price
        where 날짜 >= (select (select max(날짜) from kor_price) - interval 1 year);
        """, con=conn.connection)

engine.dispose()

price_list.head()

# ---- Cell ----
price_list.info()

# ---- Cell ----
price_pivot = price_list.pivot(index='날짜', columns='종목코드', values='종가')
price_pivot.iloc[0:5, 0:5]

# ---- Cell ----
ret_list = pd.DataFrame(data=(price_pivot.iloc[-1] / price_pivot.iloc[0]) - 1,
                        columns=['return'])
data_bind = ticker_list[['종목코드', '종목명']].merge(ret_list, how='left', on='종목코드')

data_bind.head()

# ---- Cell ----
momentum_rank = data_bind['return'].rank(axis=0, ascending=False)
data_bind[momentum_rank <= 20]

# ---- Cell ----
price_momentum = price_list[price_list['종목코드'].isin(
    data_bind.loc[momentum_rank <= 20, '종목코드'])]

import matplotlib.pyplot as plt
import seaborn as sns

plt.rc('font', family='NanumBarunGothic')
g = sns.relplot(data=price_momentum,
                x='날짜',
                y='종가',
                col='종목코드',
                col_wrap=5,
                kind='line',
                facet_kws={
                    'sharey': False,
                    'sharex': True
                })
g.set(xticklabels=[])
g.set(xlabel=None)
g.set(ylabel=None)
g.fig.set_figwidth(15)
g.fig.set_figheight(8)
plt.subplots_adjust(wspace=0.5, hspace=0.2)
plt.show()

# ---- Cell ----
import statsmodels.api as sm
import numpy as np

ret = price_pivot.pct_change().iloc[1:]
ret_cum = np.log(1 + ret).cumsum()

x = np.array(range(len(ret)))
y = ret_cum.iloc[:, 0].values

# ---- Cell ----
reg = sm.OLS(y, x).fit()
reg.summary()

# ---- Cell ----
print(reg.params, reg.bse, (reg.params / reg.bse))

# ---- Cell ----
x = np.array(range(len(ret)))
k_ratio = {}

for i in range(0, len(ticker_list)):

    ticker = data_bind.loc[i, '종목코드']

    try:
        y = ret_cum.loc[:, price_pivot.columns == ticker]
        reg = sm.OLS(y, x).fit()
        res = float(reg.params / reg.bse)
    except:
        res = np.nan

    k_ratio[ticker] = res

k_ratio_bind = pd.DataFrame.from_dict(k_ratio, orient='index').reset_index()
k_ratio_bind.columns = ['종목코드', 'K_ratio']

k_ratio_bind.head()

# ---- Cell ----
data_bind = data_bind.merge(k_ratio_bind, how='left', on='종목코드')
k_ratio_rank = data_bind['K_ratio'].rank(axis=0, ascending=False)
data_bind[k_ratio_rank <= 20]

# ---- Cell ----
k_ratio_momentum = price_list[price_list['종목코드'].isin(
    data_bind.loc[k_ratio_rank <= 20, '종목코드'])]

plt.rc('font', family='NanumBarunGothic')
g = sns.relplot(data=k_ratio_momentum,
                x='날짜',
                y='종가',
                col='종목코드',
                col_wrap=5,
                kind='line',
                facet_kws={
                    'sharey': False,
                    'sharex': True
                })
g.set(xticklabels=[])
g.set(xlabel=None)
g.set(ylabel=None)
g.fig.set_figwidth(15)
g.fig.set_figheight(8)
plt.subplots_adjust(wspace=0.5, hspace=0.2)
plt.show()

# ---- Cell ----
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm

url = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Portfolios_Formed_on_OP_CSV.zip'
df_op = pd.read_csv(url, skiprows=24, encoding='cp1252', index_col=0)
end_point = np.where(pd.isna(df_op.iloc[:, 2]))[0][0]
df_op_vw = df_op.iloc[0:end_point][[
    'Lo 20', 'Qnt 2', 'Qnt 3', 'Qnt 4', 'Hi 20'
]].apply(pd.to_numeric)
df_op_cum = np.log(1 + df_op_vw / 100).cumsum()

plt.rc('font', family='NanumBarunGothic')
plt.rc('axes', unicode_minus=False)

df_op_cum.plot(figsize=(10, 6),
               colormap=cm.jet,
               legend='reverse',
               title='수익성별 포트폴리오의 누적 수익률')
plt.show()

# ---- Cell ----
factor_stat(df_op_vw)

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd
import numpy as np

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
    ticker_list = pd.read_sql("""
    select * from kor_ticker
    where 기준일 = (select max(기준일) from kor_ticker)
    and 종목구분 = '보통주';
    """, con=conn.connection)

with engine.connect() as conn:
    fs_list = pd.read_sql("""
    select * from kor_fs
    where 계정 in ('당기순이익', '매출총이익', '영업활동으로인한현금흐름', '자산', '자본')
    and 공시구분 = 'q';
    """, con=conn.connection)

engine.dispose()

# ---- Cell ----
fs_list = fs_list.sort_values(['종목코드', '계정', '기준일'])
fs_list['ttm'] = fs_list.groupby(['종목코드', '계정'], as_index=False)['값'].rolling(
    window=4, min_periods=4).sum()['값']
fs_list_clean = fs_list.copy()
fs_list_clean['ttm'] = np.where(fs_list_clean['계정'].isin(['자산', '자본']),
                                fs_list_clean['ttm'] / 4, fs_list_clean['ttm'])
fs_list_clean = fs_list_clean.groupby(['종목코드', '계정']).tail(1)

fs_list_pivot = fs_list_clean.pivot(index='종목코드', columns='계정', values='ttm')
fs_list_pivot['ROE'] = fs_list_pivot['당기순이익'] / fs_list_pivot['자본']
fs_list_pivot['GPA'] = fs_list_pivot['매출총이익'] / fs_list_pivot['자산']
fs_list_pivot['CFO'] = fs_list_pivot['영업활동으로인한현금흐름'] / fs_list_pivot['자산']

quality_list = ticker_list[['종목코드', '종목명']].merge(fs_list_pivot,
                                                  how='left',
                                                  on='종목코드')
quality_list.round(4).head()

# ---- Cell ----
quality_list_copy = quality_list[['ROE', 'GPA', 'CFO']].copy()
quality_rank = quality_list_copy.rank(ascending=False, axis=0)

# ---- Cell ----
import matplotlib.pyplot as plt
import seaborn as sns

mask = np.triu(quality_rank.corr())
fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(quality_rank.corr(),
            annot=True,
            mask=mask,
            annot_kws={"size": 16},
            vmin=0,
            vmax=1,
            center=0.5,
            cmap='coolwarm',
            square=True)
ax.invert_yaxis()
plt.show()

# ---- Cell ----
quality_sum = quality_rank.sum(axis=1, skipna=False).rank()
quality_list.loc[quality_sum <= 20,
['종목코드', '종목명', 'ROE', 'GPA', 'CFO']].round(4)

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd
import numpy as np

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
    value_list = pd.read_sql("""
    select * from kor_value
    where 기준일 = (select max(기준일) from kor_value)
    and 지표 = 'PBR';
    """, con=conn.connection)

with engine.connect() as conn:
    fs_list = pd.read_sql("""
    select * from kor_fs
    where 계정 in ('매출총이익', '자산')
    and 공시구분 = 'y';
    """, con=conn.connection)

engine.dispose()

# 밸류 지표
value_list.loc[value_list['값'] < 0, '값'] = np.nan
value_pivot = value_list.pivot(index='종목코드', columns='지표', values='값')

# 퀄리티 지표
fs_list = fs_list.sort_values(['종목코드', '계정', '기준일'])
fs_list = fs_list.groupby(['종목코드', '계정']).tail(1)
fs_list_pivot = fs_list.pivot(index='종목코드', columns='계정', values='값')
fs_list_pivot['GPA'] = fs_list_pivot['매출총이익'] / fs_list_pivot['자산']

# 데이터 합치기
bind_rank = value_pivot['PBR'].rank().to_frame().merge(
    fs_list_pivot['GPA'].rank(ascending=False), how='inner', on='종목코드')

# 상관관계
bind_rank.corr()

# ---- Cell ----
import matplotlib.pyplot as plt

bind_data = value_list.merge(fs_list_pivot, how='left', on='종목코드')
bind_data = bind_data.dropna()
bind_data['PBR_quantile'] = pd.qcut(bind_data['값'], q=5, labels=range(1, 6))
bind_group = bind_data.groupby('PBR_quantile').mean('GPA')

fig, ax = plt.subplots(figsize=(10, 6))
plt.rc('font', family='NanumBarunGothic')
plt.bar(x=np.arange(5), height=bind_group['GPA'])
plt.xlabel('PBR')
plt.ylabel('GPA')

plt.show()

# ---- Cell ----
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm

url = 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_BEME_OP_5x5_CSV.zip'
df_qv = pd.read_csv(url, skiprows=21, encoding='cp1252', index_col=0)
end_point = np.where(pd.isna(df_qv.iloc[:, 2]))[0][0]
df_qv = df_qv.iloc[0:end_point].apply(pd.to_numeric)

df_qv.head()

# ---- Cell ----
df_qv_quality = df_qv.loc[:, ['LoBM HiOP', 'BM2 OP5', 'BM3 OP5']].mean(axis=1)  # Quality
df_qv_value = df_qv.loc[:, ['HiBM LoOP', 'BM5 OP2', 'BM5 OP3']].mean(axis=1)  # Value
df_qv_worst = df_qv.loc[:, ['LoBM LoOP', 'BM1 OP2', 'BM2 OP1', 'BM2 OP2']].mean(axis=1)  # Worst
df_qv_best = df_qv.loc[:, ['BM5 OP4', 'HiBM HiOP', 'BM4 OP4', 'BM4 OP5']].mean(axis=1)  # Best
df_qv_bind = pd.concat([df_qv_quality, df_qv_value, df_qv_worst, df_qv_best], axis=1)
df_qv_bind.columns = ['Quality', 'Value', 'Worst', 'Best']
df_qv_bind_cum = np.log(1 + df_qv_bind / 100).cumsum()

plt.rc('font', family='NanumBarunGothic')
df_qv_bind_cum.plot(figsize=(10, 6),
                    colormap=cm.jet,
                    legend='reverse',
                    title='퀄리티/밸류별 누적 수익률')
plt.show()

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd
import numpy as np

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
    ticker_list = pd.read_sql("""
    select * from kor_ticker
    where 기준일 = (select max(기준일) from kor_ticker)
    and 종목구분 = '보통주';
    """, con=conn.connection)

with engine.connect() as conn:
    fs_list = pd.read_sql("""
    select * from kor_fs
    where 계정 in ('매출액', '당기순이익', '법인세비용', '이자비용', '현금및현금성자산',
    '부채', '유동부채', '유동자산', '비유동자산', '감가상각비')
    and 공시구분 = 'q';
    """, con=conn.connection)

engine.dispose()

fs_list = fs_list.sort_values(['종목코드', '계정', '기준일'])
fs_list['ttm'] = fs_list.groupby(['종목코드', '계정'], as_index=False)['값'].rolling(
    window=4, min_periods=4).sum()['값']
fs_list_clean = fs_list.copy()
fs_list_clean['ttm'] = np.where(
    fs_list_clean['계정'].isin(['부채', '유동부채', '유동자산', '비유동자산']),
    fs_list_clean['ttm'] / 4, fs_list_clean['ttm'])

fs_list_clean = fs_list_clean.groupby(['종목코드', '계정']).tail(1)
fs_list_pivot = fs_list_clean.pivot(index='종목코드', columns='계정', values='ttm')

data_bind = ticker_list[['종목코드', '종목명', '시가총액']].merge(fs_list_pivot,
                                                       how='left',
                                                       on='종목코드')
data_bind['시가총액'] = data_bind['시가총액'] / 100000000

data_bind.head()

# ---- Cell ----
# 분자(EBIT)
magic_ebit = data_bind['당기순이익'] + data_bind['법인세비용'] + data_bind['이자비용']

# 분모
magic_cap = data_bind['시가총액']
magic_debt = data_bind['부채']

## 분모: 여유자금
magic_excess_cash = data_bind['유동부채'] - data_bind['유동자산'] + data_bind[
    '현금및현금성자산']
magic_excess_cash[magic_excess_cash < 0] = 0
magic_excess_cash_final = data_bind['현금및현금성자산'] - magic_excess_cash

magic_ev = magic_cap + magic_debt - magic_excess_cash_final

# 이익수익률
magic_ey = magic_ebit / magic_ev

# ---- Cell ----
# 투하자본 수익률
magic_ic = (data_bind['유동자산'] - data_bind['유동부채']) + (data_bind['비유동자산'] -
                                                      data_bind['감가상각비'])
magic_roc = magic_ebit / magic_ic

# ---- Cell ----
# 열 입력하기
data_bind['이익 수익률'] = magic_ey
data_bind['투하자본 수익률'] = magic_roc

magic_rank = (magic_ey.rank(ascending=False, axis=0) +
              magic_roc.rank(ascending=False, axis=0)).rank(axis=0)
data_bind.loc[magic_rank <= 20, ['종목코드', '종목명', '이익 수익률', '투하자본 수익률']].round(4)

# ---- Cell ----
import matplotlib.pyplot as plt
import seaborn as sns

data_bind['투자구분'] = np.where(magic_rank <= 20, '마법공식', '기타')

plt.subplots(1, 1, figsize=(10, 6))
sns.scatterplot(data=data_bind,
                x='이익 수익률',
                y='투하자본 수익률',
                hue='투자구분',
                style='투자구분',
                s=200)
plt.xlim(0, 1)
plt.ylim(0, 1)
plt.show()

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd
from scipy.stats import zscore

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
    ticker_list = pd.read_sql("""
    select * from kor_ticker
    where 기준일 = (select max(기준일) from kor_ticker)
        and 종목구분 = '보통주';
    """, con=conn.connection)

    sector_list = pd.read_sql("""
    select * from kor_sector
    where 기준일 = (select max(기준일) from kor_ticker) ;
    """, con=conn.connection)

    price_list = pd.read_sql("""
    select 날짜, 종가, 종목코드
    from kor_price
    where 날짜 >= (select (select max(날짜) from kor_price) - interval 1 year);
    """, con=conn.connection)

engine.dispose()

price_pivot = price_list.pivot(index='날짜', columns='종목코드', values='종가')
ret_list = pd.DataFrame(data=(price_pivot.iloc[-1] / price_pivot.iloc[0]) - 1,
                        columns=['return'])

# ---- Cell ----
data_bind = ticker_list[['종목코드',
                         '종목명']].merge(sector_list[['CMP_CD', 'SEC_NM_KOR']],
                                       how='left',
                                       left_on='종목코드',
                                       right_on='CMP_CD').merge(ret_list,
                                                                how='left',
                                                                on='종목코드')

data_bind.head()

# ---- Cell ----
import matplotlib.pyplot as plt

data_bind['rank'] = data_bind['return'].rank(axis=0, ascending=False)
# sector_count = pd.DataFrame(data_bind.loc[data_bind['rank'] <= 20, 'SEC_NM_KOR'].value_counts())
sector_count = pd.DataFrame(data_bind.loc[data_bind['rank'] <= 20, 'SEC_NM_KOR'].value_counts())
plt.rc('font', family='NanumBarunGothic')
sector_count.plot.barh(figsize=(10, 6), legend=False)
plt.gca().invert_yaxis()
# for y, x in enumerate(sector_count['SEC_NM_KOR']):
for y, x in enumerate(sector_count.squeeze().values):
    plt.annotate(str(x), xy=(x, y), va='center')

# ---- Cell ----
data_bind.loc[data_bind['SEC_NM_KOR'].isnull(), 'SEC_NM_KOR'] = '기타'
# data_bind['z-score'] = data_bind.groupby('SEC_NM_KOR', dropna=False)['return'].apply(zscore, nan_policy='omit')
data_bind['z-score'] = pd.concat(
    [zscore(x, nan_policy='omit') for _, x in data_bind.groupby('SEC_NM_KOR', dropna=False)['return']])
data_bind['z-rank'] = data_bind['z-score'].rank(axis=0, ascending=False)
sector_neutral_count = pd.DataFrame(data_bind.loc[data_bind['z-rank'] <= 20,
'SEC_NM_KOR'].value_counts())

plt.rc('font', family='NanumBarunGothic')
sector_neutral_count.plot.barh(figsize=(10, 6), legend=False)
plt.gca().invert_yaxis()

# for y, x in enumerate(sector_neutral_count['SEC_NM_KOR']):
for y, x in enumerate(sector_neutral_count.squeeze().values):
    plt.annotate(str(x), xy=(x, y), va='center')

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd
import numpy as np

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
    value_list = pd.read_sql("""
    select * from kor_value
    where 기준일 = (select max(기준일) from kor_value);
    """, con=conn.connection)

engine.dispose()

value_pbr = value_list[value_list['지표'] == 'PBR']

print(value_pbr['값'].max(), '\n', value_pbr['값'].min())

# ---- Cell ----
import matplotlib.pyplot as plt

value_pbr['값'].plot.hist(bins=100, figsize=(10, 6))
plt.xlim(0, 40)
plt.show()

# ---- Cell ----
q_low = value_pbr['값'].quantile(0.01)
q_hi = value_pbr['값'].quantile(0.99)

value_trim = value_pbr.loc[(value_pbr['값'] > q_low) & (value_pbr['값'] < q_hi),
['값']]

value_trim.plot.hist(figsize=(10, 6), bins=100, legend=False)
plt.show()

# ---- Cell ----
value_winsor = value_pbr[['값']].copy()
value_winsor.loc[value_winsor["값"] < q_low, '값'] = q_low
value_winsor.loc[value_winsor["값"] > q_hi, '값'] = q_hi

fig, ax = plt.subplots(figsize=(10, 6))
n, bins, patches = plt.hist(value_winsor, bins=100)
patches[0].set_fc('red')
patches[-1].set_fc('red')
plt.show()

# ---- Cell ----
value_pivot = value_list.pivot(index='종목코드', columns='지표', values='값')
value_rank = value_pivot.rank(axis=0)

fig, axes = plt.subplots(5, 1, figsize=(10, 6), sharex=True)
for n, ax in enumerate(axes.flatten()):
    ax.hist(value_rank.iloc[:, n])
    ax.set_title(value_rank.columns[n], size=12)

fig.tight_layout()

# ---- Cell ----
value_pivot.isna().sum()

# ---- Cell ----
from scipy.stats import zscore

value_rank_z = value_rank.apply(zscore, nan_policy='omit')

fig, axes = plt.subplots(5, 1, figsize=(10, 6), sharex=True, sharey=True)
for n, ax in enumerate(axes.flatten()):
    ax.hist(value_rank_z.iloc[:, n])
    ax.set_title(value_rank.columns[n], size=12)

fig.tight_layout()
plt.show()

# ---- Cell ----
from sqlalchemy import create_engine
import pandas as pd
import numpy as np
import statsmodels.api as sm
from scipy.stats import zscore
import matplotlib.pyplot as plt

engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/stock_db')

with engine.connect() as conn:
	ticker_list = pd.read_sql("""
	select * from kor_ticker
	where 기준일 = (select max(기준일) from kor_ticker)
		and 종목구분 = '보통주';
	""", con=conn.connection)

	fs_list = pd.read_sql("""
	select * from kor_fs
	where 계정 in ('당기순이익', '매출총이익', '영업활동으로인한현금흐름', '자산', '자본')
	and 공시구분 = 'q';
	""", con=conn.connection)

	value_list = pd.read_sql("""
	select * from kor_value
	where 기준일 = (select max(기준일) from kor_value);
	""", con=conn.connection)

	price_list = pd.read_sql("""
	select 날짜, 종가, 종목코드
	from kor_price
	where 날짜 >= (select (select max(날짜) from kor_price) - interval 1 year);
	""", con=conn.connection)

	sector_list = pd.read_sql("""
	select * from kor_sector
	where 기준일 = (select max(기준일) from kor_ticker);
	""", con=conn.connection)

engine.dispose()

# ---- Cell ----
fs_list = fs_list.sort_values(['종목코드', '계정', '기준일'])
fs_list['ttm'] = fs_list.groupby(['종목코드', '계정'], as_index=False)['값'].rolling(
    window=4, min_periods=4).sum()['값']
fs_list_clean = fs_list.copy()
fs_list_clean['ttm'] = np.where(fs_list_clean['계정'].isin(['자산', '지배기업주주지분']),
                                fs_list_clean['ttm'] / 4, fs_list_clean['ttm'])
fs_list_clean = fs_list_clean.groupby(['종목코드', '계정']).tail(1)

fs_list_pivot = fs_list_clean.pivot(index='종목코드', columns='계정', values='ttm')
fs_list_pivot['ROE'] = fs_list_pivot['당기순이익'] / fs_list_pivot['자본']
fs_list_pivot['GPA'] = fs_list_pivot['매출총이익'] / fs_list_pivot['자산']
fs_list_pivot['CFO'] = fs_list_pivot['영업활동으로인한현금흐름'] / fs_list_pivot['자산']

fs_list_pivot.round(4).head()

# ---- Cell ----
value_list.loc[value_list['값'] <= 0, '값'] = np.nan
value_pivot = value_list.pivot(index='종목코드', columns='지표', values='값')

value_pivot.head()

# ---- Cell ----
price_pivot = price_list.pivot(index='날짜', columns='종목코드', values='종가')
ret_list = pd.DataFrame(data=(price_pivot.iloc[-1] / price_pivot.iloc[0]) - 1,
                        columns=['12M'])

ret = price_pivot.pct_change().iloc[1:]
ret_cum = np.log(1 + ret).cumsum()

x = np.array(range(len(ret)))
k_ratio = {}

for i in range(0, len(ticker_list)):

    ticker = ticker_list.loc[i, '종목코드']

    try:
        y = ret_cum.loc[:, price_pivot.columns == ticker]
        reg = sm.OLS(y, x).fit()
        res = float(reg.params / reg.bse)
    except:
        res = np.nan

    k_ratio[ticker] = res

k_ratio_bind = pd.DataFrame.from_dict(k_ratio, orient='index').reset_index()
k_ratio_bind.columns = ['종목코드', 'K_ratio']

k_ratio_bind.head()

# ---- Cell ----
data_bind = ticker_list[['종목코드', '종목명']].merge(
    sector_list[['CMP_CD', 'SEC_NM_KOR']],
    how='left',
    left_on='종목코드',
    right_on='CMP_CD').merge(
    fs_list_pivot[['ROE', 'GPA', 'CFO']], how='left',
    on='종목코드').merge(value_pivot, how='left',
                     on='종목코드').merge(ret_list, how='left',
                                      on='종목코드').merge(k_ratio_bind,
                                                       how='left',
                                                       on='종목코드')

data_bind.loc[data_bind['SEC_NM_KOR'].isnull(), 'SEC_NM_KOR'] = '기타'
data_bind = data_bind.drop(['CMP_CD'], axis=1)

data_bind.round(4).head()

# ---- Cell ----
def col_clean(df, cutoff=0.01, asc=False):
    q_low = df.quantile(cutoff)
    q_hi = df.quantile(1 - cutoff)

    df_trim = df[(df > q_low) & (df < q_hi)]

    if asc == False:
        df_z_score = df_trim.rank(axis=0, ascending=False).apply(
            zscore, nan_policy='omit')
    if asc == True:
        df_z_score = df_trim.rank(axis=0, ascending=True).apply(
            zscore, nan_policy='omit')

    return (df_z_score)

# ---- Cell ----
data_bind_group = data_bind.set_index(['종목코드',
                                       'SEC_NM_KOR']).groupby('SEC_NM_KOR')

data_bind_group.head(1).round(4)

# ---- Cell ----
z_quality = data_bind_group[['ROE', 'GPA', 'CFO'
                             ]].apply(lambda x: col_clean(x, 0.01, False)).sum(
    axis=1, skipna=False).to_frame('z_quality')
z_quality = z_quality.droplevel(0)
data_bind = data_bind.merge(z_quality, how='left', on=['종목코드', 'SEC_NM_KOR'])

data_bind.round(4).head()

# ---- Cell ----
value_1 = data_bind_group[['PBR', 'PCR', 'PER', 'PSR']].apply(lambda x: col_clean(x, 0.01, True))
value_2 = data_bind_group[['DY']].apply(lambda x: col_clean(x, 0.01, False))

value_1.index = value_1.index.droplevel(0)
value_2.index = value_2.index.droplevel(0)

z_value = value_1.merge(value_2, on=['종목코드', 'SEC_NM_KOR'
                                     ]).sum(axis=1,
                                            skipna=False).to_frame('z_value')

data_bind = data_bind.merge(z_value, how='left', on=['종목코드', 'SEC_NM_KOR'])

data_bind.round(4).head()

# ---- Cell ----
z_momentum = data_bind_group[[
    '12M', 'K_ratio'
]].apply(lambda x: col_clean(x, 0.01, False)).sum(
    axis=1, skipna=False).to_frame('z_momentum')

z_momentum.index = z_momentum.index.droplevel(0)
data_bind = data_bind.merge(z_momentum, how='left', on=['종목코드', 'SEC_NM_KOR'])

data_bind.round(4).head()

# ---- Cell ----
data_z = data_bind[['z_quality', 'z_value', 'z_momentum']].copy()

plt.rc('axes', unicode_minus=False)
fig, axes = plt.subplots(3, 1, figsize=(10, 6), sharex=True, sharey=True)
for n, ax in enumerate(axes.flatten()):
    ax.hist(data_z.iloc[:, n])
    ax.set_title(data_z.columns[n], size=12)
fig.tight_layout()
plt.show()

# ---- Cell ----
data_bind_final = data_bind[['종목코드', 'z_quality', 'z_value', 'z_momentum'
                             ]].set_index('종목코드').apply(zscore,
                                                        nan_policy='omit')
data_bind_final.columns = ['quality', 'value', 'momentum']

plt.rc('axes', unicode_minus=False)
fig, axes = plt.subplots(3, 1, figsize=(10, 6), sharex=True, sharey=True)
for n, ax in enumerate(axes.flatten()):
    ax.hist(data_bind_final.iloc[:, n])
    ax.set_title(data_bind_final.columns[n], size=12)
fig.tight_layout()
plt.show()

# ---- Cell ----
import seaborn as sns

mask = np.triu(data_bind_final.corr())
fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(data_bind_final.corr(),
            annot=True,
            mask=mask,
            annot_kws={"size": 16},
            vmin=0,
            vmax=1,
            center=0.5,
            cmap='coolwarm',
            square=True)
ax.invert_yaxis()
plt.show()

# ---- Cell ----
wts = [0.3, 0.3, 0.3]
data_bind_final_sum = (data_bind_final * wts).sum(axis=1,
                                                  skipna=False).to_frame()
data_bind_final_sum.columns = ['qvm']
port_qvm = data_bind.merge(data_bind_final_sum, on='종목코드')
port_qvm['invest'] = np.where(port_qvm['qvm'].rank() <= 20, 'Y', 'N')

port_qvm[port_qvm['invest'] == 'Y'].round(4)

# ---- Cell ----
import seaborn as sns


def plot_rank(df):
    ax = sns.relplot(data=df,
                     x='rank',
                     y=1,
                     col='variable',
                     hue='invest',
                     style='invest',
                     palette=['grey', 'red'],
                     size='invest',
                     sizes=(100, 10),
                     kind="scatter",
                     col_wrap=5)
    ax.set(xlabel=None)
    ax.set(ylabel=None)

    sns.move_legend(ax, "lower center", bbox_to_anchor=(0.5, -.1), ncol=2)

    plt.show()

# ---- Cell ----
data_melt = port_qvm.melt(id_vars='invest',
                          value_vars=[
                              'ROE', 'GPA', 'CFO', 'PER', 'PBR', 'PCR', 'PSR',
                              'DY', '12M', 'K_ratio'
                          ])

data_melt.head()

# ---- Cell ----
hist_quality = data_melt[data_melt['variable'].isin(['ROE', 'GPA',
                                                     'CFO'])].copy()
hist_quality['rank'] = hist_quality.groupby('variable')['value'].rank(
    ascending=False)
plot_rank(hist_quality)

# ---- Cell ----
hist_value = data_melt[data_melt['variable'].isin(
    ['PER', 'PBR', 'PCR', 'PSR', 'DY'])].copy()
hist_value['value'] = np.where(hist_value['variable'] == 'DY',
                               1 / hist_value['value'], hist_value['value'])
hist_value['rank'] = hist_value.groupby('variable')['value'].rank()
plot_rank(hist_value)

# ---- Cell ----
hist_momentum = data_melt[data_melt['variable'].isin(['12M', 'K_ratio'])].copy()
hist_momentum['rank'] = hist_momentum.groupby('variable')['value'].rank(ascending=False)
plot_rank(hist_momentum)

# ---- Cell ----
port_qvm[port_qvm['invest'] == 'Y']['종목코드'].to_excel('model.xlsx', index=False)

# ---- Cell ----

