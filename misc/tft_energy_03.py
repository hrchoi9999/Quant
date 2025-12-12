# English filename: tft_energy_03_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/2. 최신딥러닝시계열모델/TFT_energy_03_clear.py
# Original filename: TFT_energy_03_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/etc_data/energy_weather_features.zip&& unzip -n energy_weather_features.zip
!pip install darts

# ---- Cell ----
import os
LOAD = False         # True = load previously saved model from disk?  False = (re)train the model
SAVE = "\_TFT_model_02.pth.tar"   # file name to save the model under

EPOCHS = 2
INLEN = 32          # input size
HIDDEN = 64         # hidden layers
LSTMLAYERS = 2      # recurrent layers
ATTH = 4            # attention heads
BATCH = 32          # batch size
LEARN = 1e-3        # learning rate
DROPOUT = 0.1       # dropout rate
VALWAIT = 1         # epochs to wait before evaluating the loss on the test/validation set
N_FC = 1            # output size

RAND = 42           # random seed
N_SAMPLES = 100     # number of times a prediction is sampled from a probabilistic model
N_JOBS = 3          # parallel processors to use;  -1 = all processors

# default quantiles for QuantileRegression
QUANTILES = [0.01, 0.1, 0.2, 0.5, 0.8, 0.9, 0.99]

SPLIT = 0.9         # train/test %

FIGSIZE = (9, 6)


qL1, qL2 = 0.01, 0.10        # percentiles of predictions: lower bounds
qU1, qU2 = 1-qL1, 1-qL2,     # upper bounds derived from lower bounds
label_q1 = f'{int(qU1 * 100)} / {int(qL1 * 100)} percentile band'
label_q2 = f'{int(qU2 * 100)} / {int(qL2 * 100)} percentile band'

mpath = os.path.abspath(os.getcwd()) + SAVE     # path and file name to save the model

# ---- Cell ----
%matplotlib inline
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import sys
import missingno as mno

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)


from darts import TimeSeries, concatenate
from darts.dataprocessing.transformers import Scaler
from darts.models import TFTModel
from darts.metrics import mape, rmse
from darts.utils.timeseries_generation import datetime_attribute_timeseries
from darts.utils.likelihood_models import QuantileRegression


pd.set_option("display.precision",2)
np.set_printoptions(precision=2, suppress=True)
pd.options.display.float_format = '{:,.2f}'.format

# ---- Cell ----
# load
df0 = pd.read_csv("energy_dataset.csv", header=0, parse_dates=["time"])
dfw0 = pd.read_csv("weather_features.csv", header=0, parse_dates=["dt_iso"])

# ---- Cell ----
df0.iloc[[0, -1]]

# ---- Cell ----
dfw0.iloc[[0, -1]]

# ---- Cell ----
# backup of original sources
df1 = df0.copy()
dfw1 = dfw0.copy()

# ---- Cell ----
df1.info()

# ---- Cell ----
# datetime
df1["time"] = pd.to_datetime(df1["time"], utc=True, infer_datetime_format=True)


# any duplicate time periods?
print("count of duplicates:",df1.duplicated(subset=["time"], keep="first").sum())


df1.set_index("time", inplace=True)


# any non-numeric types?
print("non-numeric columns:",list(df1.dtypes[df1.dtypes == "object"].index))


# any missing values?
def gaps(df):
    if df.isnull().values.any():
        print("MISSING values:\n")
        mno.matrix(df)
    else:
        print("no missing values\n")
gaps(df1)


# ---- Cell ----
# drop the NaN and zero columns, and also the 'forecast' columns
df1 = df1.drop(df1.filter(regex="forecast").columns, axis=1, errors="ignore")
df1.dropna(axis=1, how="all", inplace=True)
df1 = df1.loc[:, (df1!=0).any(axis=0)]

# ---- Cell ----
# handle missing values in rows of remaining columns
df1 = df1.interpolate(method ="bfill")
# any missing values left?
gaps(df1)

df1 = df1.loc[:, (df1!=0).any(axis=0)]

# ---- Cell ----
# rename columns
colnames_old = df1.columns
colnames_new = ["gen_bio", "gen_lig", "gen_gas", "gen_coal", \
                "gen_oil", "gen_hyd_pump", "gen_hyd_river", "gen_hyd_res", \
                "gen_nuc", "gen_other", "gen_oth_renew", "gen_solar", \
                "gen_waste", "gen_wind", "load_actual", "price_dayahead", \
                "price"]
dict_cols = dict(zip(colnames_old, colnames_new))
df1.rename(columns=dict_cols, inplace=True)
print(df1.info())
df1.describe()


# ---- Cell ----
# convert int and float64 columns to float32
intcols = list(df1.dtypes[df1.dtypes == np.int64].index)
df1[intcols] = df1[intcols].applymap(np.float32)

f64cols = list(df1.dtypes[df1.dtypes == np.float64].index)
df1[f64cols] = df1[f64cols].applymap(np.float32)

# ---- Cell ----
plt.figure(100, figsize=(20, 7))
sns.lineplot(x = "time", y = "price", data = df1, palette="coolwarm");

# ---- Cell ----
dfw1.info()

# ---- Cell ----
# datetime
dfw1["time"] = pd.to_datetime(dfw1["dt_iso"], utc=True, infer_datetime_format=True)
dfw1.set_index("time", inplace=True)


# any non-numeric types?
print("non-numeric columns:",list(dfw1.dtypes[dfw1.dtypes == "object"].index))


# any missing values?
def gaps(df):
    if df.isnull().values.any():
        print("MISSING values:\n")
        mno.matrix(df)
    else:
        print("no missing values\n")
gaps(dfw1)


dfw1.describe()

# ---- Cell ----
# drop unnecessary columns
dfw1.drop(["rain_3h", "weather_id", "weather_main", "weather_description", "weather_icon"],
          inplace=True, axis=1, errors="ignore")


# temperature: kelvin to celsius
temp_cols = [col for col in dfw1.columns if "temp" in col]
dfw1[temp_cols] = dfw1[temp_cols].filter(like="temp").applymap(lambda t: t - 273.15)


# ---- Cell ----
# convert int and float64 columns to float32
intcols = list(dfw1.dtypes[dfw1.dtypes == np.int64].index)
dfw1[intcols] = dfw1[intcols].applymap(np.float32)

f64cols = list(dfw1.dtypes[dfw1.dtypes == np.float64].index)
dfw1[f64cols] = dfw1[f64cols].applymap(np.float32)

f32cols = list(dfw1.dtypes[dfw1.dtypes == np.float32].index)
dfw1.info()

# ---- Cell ----
#investigate the outliers in the pressure column
dfw1["pressure"].nlargest(10)

# ---- Cell ----
#investigate the outliers in the wind_speed column
dfw1["wind_speed"].nlargest(10)

# ---- Cell ----
# boxplots
for i, c in enumerate(f32cols):
    sns.boxplot(x=dfw1[c], palette="coolwarm")
    plt.show();

# ---- Cell ----
# or use distplot to visualize outliers
fig = plt.figure(figsize=(5, 4))
ax = sns.distplot(dfw1["temp"])
xmin = dfw1["temp"].min()
xmax = dfw1["temp"].max()
ax.set_xlim(xmin, xmax)
ax.set_title("temp");

fig = plt.figure(figsize=(5, 4))
ax = sns.distplot(dfw1["pressure"])
xmin = dfw1["pressure"].min()
xmax = dfw1["pressure"].max()
ax.set_xlim(xmin, xmax)
ax.set_title("pressure");

fig = plt.figure(figsize=(5, 4))
ax = sns.distplot(dfw1["wind_speed"])
xmin = dfw1["wind_speed"].min()
xmax = dfw1["wind_speed"].max()
ax.set_xlim(xmin, xmax)
ax.set_title("wind_speed");

# ---- Cell ----
# treatment of outliers: replace with NaN, then interpolate
dfw1["pressure"].where( dfw1["pressure"] <= 1050, inplace=True)
dfw1["pressure"].where( dfw1["pressure"] >= 948, inplace=True)
dfw1["wind_speed"].where( dfw1["wind_speed"] <= 120, inplace=True)
dfw1["clouds_all"].where( dfw1["clouds_all"] <= 40, inplace=True)
dfw1 = dfw1.interpolate(method ="bfill")

sns.boxplot(x=dfw1["pressure"], palette="coolwarm")
plt.show();
sns.boxplot(x=dfw1["wind_speed"], palette="coolwarm")
plt.show();
sns.boxplot(x=dfw1["clouds_all"], palette="coolwarm")
plt.show();

dfw1.describe()

# ---- Cell ----
# start and end of energy and weather time series
print("earliest weather time period:", dfw1.index.min())
print("latest weather time period:", dfw1.index.max())

print("earliest energy time period:", df1.index.min())
print("latest energy time period:", df1.index.max())

# ---- Cell ----
# cities in weather data
cities = dfw1["city_name"].unique()
cities

# ---- Cell ----
# drop duplicate time periods
print("count of duplicates before treatment:",dfw1.duplicated(subset=["dt_iso", "city_name"], keep="first").sum())

dfw1 = dfw1.drop_duplicates(subset=["dt_iso", "city_name"], keep="first")
dfw1.reset_index()
print("count of duplicates after treatment:",dfw1.duplicated(subset=["dt_iso", "city_name"], keep="first").sum())

# set datetime index
dfw1["time"] = pd.to_datetime(dfw1["dt_iso"], utc=True, infer_datetime_format=True)
dfw1.set_index("time", inplace=True)
dfw1.drop("dt_iso", inplace=True, axis=1)


print("size of energy dataframe:", df1.shape[0])
dfw1_city = dfw1.groupby("city_name").count()
dfw1_city

# ---- Cell ----
# count of weather observations by city
print("size of energy dataframe:", df1.shape[0])

dfw1["city_name"] = dfw1["city_name"].replace(" Barcelona", "Barcelona")   # remove space in name
dfw1_city = dfw1.groupby("city_name")
print("size of city groups in weather dataframe:")
dfw1_city.count()

# ---- Cell ----
# separate the cities: a weather dataframe for each of them
dict_city_weather = {city:df_city for city,df_city in dfw1_city}
dict_city_weather.keys()

# ---- Cell ----
# example: Bilbao weather dataframe
dfw_Bilbao = dict_city_weather.get("Bilbao")
print("Bilbao weather:")
dfw_Bilbao.describe()

# ---- Cell ----
dfw_Bilbao.iloc[[0,-1]]

# ---- Cell ----
# merge the energy and weather dataframes
df2 = df1.copy()
for city,df in dict_city_weather.items():
    city_name = str(city) + "_"
    df = df.add_suffix("_{}".format(city))
    df2 = pd.concat([df2, df], axis=1)
    df2.drop("city_name_" + city, inplace=True, axis=1)
print(df2.info())
df2.iloc[[0,-1]]

# ---- Cell ----
# any null values?
print("any missing values?", df2.isnull().values.any())

# any ducplicate time periods?
print("count of duplicates:", df2.duplicated(keep="first").sum())

# ---- Cell ----


# ---- Cell ----
# limit the dataframe's date range
df2 = df2[df2.index >= "2018-01-01 00:00:00+00:00"]
df2.iloc[[0,-1]]

# ---- Cell ----
# check correlations of features with price
df_corr = df2.corr(method="pearson")
print(df_corr.shape)
print("correlation with price:")
df_corrP = pd.DataFrame(df_corr["price"].sort_values(ascending=False))
df_corrP

# ---- Cell ----
# highest absolute correlations with price
pd.options.display.float_format = '{:,.2f}'.format
df_corrH = df_corrP[np.abs(df_corrP["price"]) > 0.25]
df_corrH

# ---- Cell ----
# correlation matrix, limited to highly correlated features
df3 = df2[df_corrH.index]

idx = df3.corr().sort_values("price", ascending=False).index
df3_sorted = df3.loc[:, idx]  # sort dataframe columns by their correlation with Appliances

plt.figure(figsize = (15,15))
sns.set(font_scale=0.75)
ax = sns.heatmap(df3_sorted.corr().round(3),
            annot=True,
            square=True,
            linewidths=.75, cmap="coolwarm",
            fmt = ".2f",
            annot_kws = {"size": 11})
ax.xaxis.tick_bottom()
plt.title("correlation matrix")
plt.show()

# ---- Cell ----
# limit energy dataframe to columns that have
# at least a moderate correlation with price
df3 = df2[df_corrH.index]
df3.info()

# ---- Cell ----
# additional datetime columns: feature engineering
df3["month"] = df3.index.month

df3["wday"] = df3.index.dayofweek
dict_days = {0:"1_Mon", 1:"2_Tue", 2:"3_Wed", 3:"4_Thu", 4:"5_Fri", 5:"6_Sat", 6:"7_Sun"}
df3["weekday"] = df3["wday"].apply(lambda x: dict_days[x])

df3["hour"] = df3.index.hour

df3 = df3.astype({"hour":float, "wday":float, "month": float})

df3.iloc[[0, -1]]

# ---- Cell ----
# pivot table: weekdays in months
piv = pd.pivot_table(   df3,
                        values="price",
                        index="month",
                        columns="weekday",
                        aggfunc="mean",
                        margins=True, margins_name="Avg",
                        fill_value=0)
pd.options.display.float_format = '{:,.0f}'.format

plt.figure(figsize = (10,15))
sns.set(font_scale=1)
sns.heatmap(piv.round(0), annot=True, square = True, \
            linewidths=.75, cmap="coolwarm", fmt = ".0f", annot_kws = {"size": 11})
plt.title("price by weekday by month")
plt.show()

# ---- Cell ----
# pivot table: hours in weekdays
piv = pd.pivot_table(   df3,
                        values="price",
                        index="hour",
                        columns="weekday",
                        aggfunc="mean",
                        margins=True, margins_name="Avg",
                        fill_value=0)
pd.options.display.float_format = '{:,.0f}'.format

plt.figure(figsize = (7,20))
sns.set(font_scale=1)
sns.heatmap(piv.round(0), annot=True, square = True, \
            linewidths=.75, cmap="coolwarm", fmt = ".0f", annot_kws = {"size": 11})
plt.title("price by hour by weekday")
plt.show()

# ---- Cell ----
# dataframe with price and features only
df4 = df3.copy()
df4.drop(["weekday", "month", "wday", "hour"], inplace=True, axis=1)

# ---- Cell ----
# create time series object for target variable
ts_P = TimeSeries.from_series(df4["price"])

# check attributes of the time series
print("components:", ts_P.components)
print("duration:",ts_P.duration)
print("frequency:",ts_P.freq)
print("frequency:",ts_P.freq_str)
print("has date time index? (or else, it must have an integer index):",ts_P.has_datetime_index)
print("deterministic:",ts_P.is_deterministic)
print("univariate:",ts_P.is_univariate)

# ---- Cell ----
# create time series object for the feature columns
df_covF = df4.loc[:, df4.columns != "price"]
ts_covF = TimeSeries.from_dataframe(df_covF)

# check attributes of the time series
print("components (columns) of feature time series:", ts_covF.components)
print("duration:",ts_covF.duration)
print("frequency:",ts_covF.freq)
print("frequency:",ts_covF.freq_str)
print("has date time index? (or else, it must have an integer index):",ts_covF.has_datetime_index)
print("deterministic:",ts_covF.is_deterministic)
print("univariate:",ts_covF.is_univariate)


# ---- Cell ----
# example: operating with time series objects:
# we can also create a 3-dimensional numpy array from a time series object
# 3 dimensions: time (rows) / components (columns) / samples
ar_covF = ts_covF.all_values()
print(type(ar_covF))
ar_covF.shape

# ---- Cell ----
# example: operating with time series objects:
# we can also create a pandas series or dataframe from a time series object
df_covF = ts_covF.to_dataframe()
type(df_covF)

# ---- Cell ----
# train/test split and scaling of target variable
ts_train, ts_test = ts_P.split_after(SPLIT)
print("training start:", ts_train.start_time())
print("training end:", ts_train.end_time())
print("training duration:",ts_train.duration)
print("test start:", ts_test.start_time())
print("test end:", ts_test.end_time())
print("test duration:", ts_test.duration)


scalerP = Scaler()
scalerP.fit_transform(ts_train)
ts_ttrain = scalerP.transform(ts_train)
ts_ttest = scalerP.transform(ts_test)
ts_t = scalerP.transform(ts_P)

# make sure data are of type float
ts_t = ts_t.astype(np.float32)
ts_ttrain = ts_ttrain.astype(np.float32)
ts_ttest = ts_ttest.astype(np.float32)

print("first and last row of scaled price time series:")
pd.options.display.float_format = '{:,.2f}'.format
ts_t.to_dataframe().iloc[[0,-1]]

# ---- Cell ----
# train/test split and scaling of feature covariates
covF_train, covF_test = ts_covF.split_after(SPLIT)

scalerF = Scaler()
scalerF.fit_transform(covF_train)
covF_ttrain = scalerF.transform(covF_train)
covF_ttest = scalerF.transform(covF_test)
covF_t = scalerF.transform(ts_covF)

# make sure data are of type float
covF_ttrain = covF_ttrain.astype(np.float32)
covF_ttest = covF_ttest.astype(np.float32)

pd.options.display.float_format = '{:.2f}'.format
print("first and last row of scaled feature covariates:")
covF_t.to_dataframe().iloc[[0,-1]]

# ---- Cell ----
# feature engineering - create time covariates: hour, weekday, month, year, country-specific holidays
covT = datetime_attribute_timeseries( ts_P.time_index, attribute="hour", add_length=48 )   # 48 hours beyond end of test set to prepare for out-of-sample forecasting
covT = covT.stack(  datetime_attribute_timeseries(covT.time_index, attribute="day_of_week")  )
covT = covT.stack(  datetime_attribute_timeseries(covT.time_index, attribute="month")  )
covT = covT.stack(  datetime_attribute_timeseries(covT.time_index, attribute="year")  )

covT = covT.add_holidays(country_code="ES")
covT = covT.astype(np.float32)


# train/test split
covT_train, covT_test = covT.split_after(ts_train.end_time())


# rescale the covariates: fitting on the training set
scalerT = Scaler()
scalerT.fit(covT_train)
covT_ttrain = scalerT.transform(covT_train)
covT_ttest = scalerT.transform(covT_test)
covT_t = scalerT.transform(covT)

covT_t = covT_t.astype(np.float32)


pd.options.display.float_format = '{:.0f}'.format
print("first and last row of unscaled time covariates:")
covT.to_dataframe().iloc[[0,-1]]

# ---- Cell ----
# combine feature and time covariates along component dimension: axis=1
ts_cov = ts_covF.concatenate( covT.slice_intersect(ts_covF), axis=1 )                      # unscaled F+T
cov_t = covF_t.concatenate( covT_t.slice_intersect(covF_t), axis=1 )                       # scaled F+T
cov_ttrain = covF_ttrain.concatenate( covT_ttrain.slice_intersect(covF_ttrain), axis=1 )   # scaled F+T training set
cov_ttest = covF_ttest.concatenate( covT_ttest.slice_intersect(covF_ttest), axis=1 )       # scaled F+T test set


pd.options.display.float_format = '{:.2f}'.format
print("first and last row of unscaled covariates:")
ts_cov.to_dataframe().iloc[[0,-1]]

# ---- Cell ----
pd.options.display.float_format = '{:.2f}'.format
print("first and last row of scaled covariates, training + test set:")
cov_t.to_dataframe().iloc[[0,-1]]

# ---- Cell ----
pd.options.display.float_format = '{:.2f}'.format
print("first and last row of scaled covariates, training + test set:")
cov_t.to_dataframe().iloc[[0,-1]]

# ---- Cell ----
model = TFTModel(   input_chunk_length=INLEN,
                    output_chunk_length=N_FC,
                    hidden_size=HIDDEN,
                    lstm_layers=LSTMLAYERS,
                    num_attention_heads=ATTH,
                    dropout=DROPOUT,
                    batch_size=BATCH,
                    n_epochs=EPOCHS,
                    nr_epochs_val_period=VALWAIT,
                    likelihood=QuantileRegression(QUANTILES),
                    optimizer_kwargs={"lr": LEARN},
                    model_name="TFT_EnergyES",
                    log_tensorboard=True,
                    random_state=RAND,
                    force_reset=True,
                    save_checkpoints=True
                )

# ---- Cell ----
# training: load a saved model or (re)train
if LOAD:
    print("have loaded a previously saved model from disk:" + mpath)
    model = TFTModel.load_model(mpath)                            # load previously model from disk
else:
    model.fit(  series=ts_ttrain,
                future_covariates=cov_t,
                val_series=ts_ttest,
                val_future_covariates=cov_t,
                verbose=True)
    print("have saved the model after training:", mpath)
    # model.save_model(mpath)

# ---- Cell ----
# testing: generate predictions
ts_tpred = model.predict(   n=len(ts_ttest),
                            num_samples=N_SAMPLES,
                            n_jobs=N_JOBS,
                            verbose=True)

# ---- Cell ----
# retrieve forecast series for chosen quantiles,
# inverse-transform each series,
# insert them as columns in a new dataframe dfY
q50_RMSE = np.inf
q50_MAPE = np.inf
ts_q50 = None
pd.options.display.float_format = '{:,.2f}'.format
dfY = pd.DataFrame()
dfY["Actual"] = TimeSeries.to_series(ts_test)


# helper function: get forecast values for selected quantile q and insert them in dataframe dfY
def predQ(ts_t, q):
    ts_tq = ts_t.quantile(q)
    ts_q = scalerP.inverse_transform(ts_tq)
    s = TimeSeries.to_series(ts_q)
    header = "Q" + format(int(q*100), "02d")
    dfY[header] = s
    if q==0.5:
        ts_q50 = ts_q
        q50_RMSE = rmse(ts_q50, ts_test)
        q50_MAPE = mape(ts_q50, ts_test)
        print("RMSE:", f'{q50_RMSE:.2f}')
        print("MAPE:", f'{q50_MAPE:.2f}')


# call helper function predQ, once for every quantile
_ = [predQ(ts_tpred, q) for q in QUANTILES]

# move Q50 column to the left of the Actual column
col = dfY.pop("Q50")
dfY.insert(1, col.name, col)
dfY.iloc[np.r_[0:2, -2:0]]

# ---- Cell ----
# plot the forecast
plt.figure(100, figsize=(20, 7))
sns.set(font_scale=1.3)
p = sns.lineplot(x = "time", y = "Q50", data = dfY, palette="coolwarm")
sns.lineplot(x = "time", y = "Actual", data = dfY, palette="coolwarm")
plt.legend(labels=["forecast median price Q50", "actual price"])
p.set_ylabel("price")
p.set_xlabel("")
p.set_title("energy price (test set)");

# ---- Cell ----
# choose forecast horizon: k hours beyond end of test set
k = 12

n_FC = k + len(ts_ttest)   # length of test set + k hours
print("forecast beyond end of training set:", n_FC,
      "hours beyond", ts_ttrain.end_time())

# last 24 hours of feature covariates available => copy them to future 24 hours:
covF_t_fut = covF_t.concatenate(    other=covF_t.tail(size=24),
                                    ignore_time_axis=True
                                    )
# combine feature and time covariates:
cov_t_fut = covF_t_fut.concatenate(covT_t.slice_intersect(covF_t_fut), axis=1)
cov_t_fut.to_dataframe().iloc[[0,-1]]

# ---- Cell ----
# forecast from end of training set until k hours beyond end of test set
ts_tpred = model.predict(   n=n_FC,
                            future_covariates=cov_t_fut,
                            num_samples=N_SAMPLES,
                            verbose=True,
                            n_jobs=N_JOBS)
print("start:", ts_tpred.start_time(), "; end:",ts_tpred.end_time())


# ---- Cell ----
# retrieve forecast series for chosen quantiles,
# inverse-transform each series,
# insert them as columns in a new dataframe dfY
q50_RMSE = np.inf
q50_MAPE = np.inf
ts_q50 = None
pd.options.display.float_format = '{:,.2f}'.format
dfY = pd.DataFrame()
#dfY["Actual"] = TimeSeries.to_series(ts_test)

# call helper function predQ, once for every quantile
_ = [predQ(ts_tpred, q) for q in QUANTILES]

# move Q50 column to the left, then insert Actual column
col = dfY.pop("Q50")
dfY.insert(0, col.name, col)
dfY.insert(0, "Actual", TimeSeries.to_series(ts_test))

# show first and last 13 timestamps of forecast
dfY.iloc[np.r_[0:1, -13:0]]

# ---- Cell ----
# plot the forecast
plt.figure(100, figsize=(20, 7))
sns.set(font_scale=1.3)
p = sns.lineplot(x = "time", y = "Q50", data = dfY, palette="coolwarm")
sns.lineplot(x = "time", y = "Actual", data = dfY, palette="coolwarm")
plt.legend(labels=["forecast median price Q50", "actual price"])
p.set_ylabel("price")
p.set_xlabel("")
end = ts_tpred.end_time()
p.set_title("energy price until {} (test set + {} hours out-of-sample)".format(end, k));
