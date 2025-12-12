# English filename: lstm_mtm_practice_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/1. 금융시계열_LSTM과Atttention/2. Attention/lstm_mtm-실습.py
# Original filename: lstm_mtm-실습.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/stock-price-predict-using%20attention_china_stock/data.zip&& unzip -n data.zip
!wget -nc http://youngminhome.iptime.org:5555/shared/stock-price-predict-using%20attention_china_stock/utils.py

# ---- Cell ----
%matplotlib inline

# ---- Cell ----
#5일 예측
import sys
import csv
import math
import numpy as np
import matplotlib.pyplot as plt
from keras.models import Sequential, load_model
from keras.layers import TimeDistributed
from keras.layers import Dense, Activation, Dropout, Lambda, RepeatVector
from keras.layers import LSTM
from keras.callbacks import ModelCheckpoint
from sklearn.preprocessing import MinMaxScaler

from utils import *

def load_data(data, time_step=20, after_day=1, validate_percent=0.67):
    seq_length = time_step + after_day
    result = []
    for index in range(len(data) - seq_length + 1):
        result.append(data[index: index + seq_length])

    result = np.array(result)
    print('total data: ', result.shape)

    train_size = int(len(result) * validate_percent)
    train = result[:train_size, :]
    validate = result[train_size:, :]

    x_train = train[:, :time_step]
    y_train = train[:, time_step:]
    x_validate = validate[:, :time_step]
    y_validate = validate[:, time_step:]

    return [x_train, y_train, x_validate, y_validate]

def base_model(feature_len=1, after_day=1, input_shape=(20, 1)):
    model = Sequential()

    model.add(LSTM(units=100, return_sequences=False, input_shape=input_shape))
    #model.add(LSTM(units=100, return_sequences=False, input_shape=input_shape))

    # one to many
    model.add(RepeatVector(after_day))
    model.add(LSTM(200, return_sequences=True))
    #model.add(LSTM(50, return_sequences=True))

    model.add(TimeDistributed(Dense(units=feature_len, activation='linear')))

    return model

if __name__ == '__main__':
#     class_list = ['50', '51', '52', '53', '54', '55', '56', '57', '58',
#                   '59', '6201', '6203', '6204', '6208', '690', '692', '701', '713']
    class_list = ['50', '51']
    scaler = MinMaxScaler(feature_range=(0, 1))

    validate_percent = 0.8
    time_step = 20
    after_day = 5
    batch_size = 64
    epochs = 10
    output = []

    #model_name = sys.argv[0].replace(".py", "")
    model_name='lstm_mtm'

    for index in range(len(class_list)):
        _class = class_list[index]
        print('******************************************* class 00{} *******************************************'.format(_class))

        #  csv로부터 데이터 읽기: (Samples, feature)
        data = file_processing(
            # 'data/20180525_process/20180525_{}.csv'.format(_class))
            'data/20180511_process/20180511_{}.csv'.format(_class))

        feature_len = data.shape[1]

        # 데이터 정규화
        data = normalize_data(data, scaler, feature_len)

        # 테스트 데이터
        x_test = data[-time_step:]
        x_test = np.reshape(x_test, (1, x_test.shape[0], x_test.shape[1]))

        # 훈련셋과 검증셋 분리
        x_train, y_train, x_validate, y_validate = load_data(
            data, time_step=time_step, after_day=after_day, validate_percent=validate_percent)

        print('train data: ', x_train.shape, y_train.shape)
        print('validate data: ', x_validate.shape, y_validate.shape)

        # 모델 구축
        input_shape = (time_step, feature_len)
        model = base_model(feature_len, after_day, input_shape)
        model.compile(loss='mse', optimizer='adam')
        model.summary()
        #plot_model_architecture(model, model_name=model_name)

        # Add Tensorboard
        #tbCallBack = keras.callbacks.TensorBoard(log_dir='./Graph', histogram_freq=0, write_graph=True, write_images=True)

        # EarlyStop
        #earlyStopping = keras.callbacks.EarlyStopping(monitor='val_loss', patience=150, verbose=1, mode='min')

        # checkoutpoint
        #checkpointer = ModelCheckpoint(filepath="model/model-3/weights.h5", monitor='val_loss', mode='min', verbose=1, save_best_only=True)

        history = model.fit(x_train, y_train, batch_size=batch_size, epochs=epochs, validation_data=(x_validate, y_validate), verbose=2)
        model_class_name = model_name + '_00{}'.format(_class)
        save_model(model, model_name=model_class_name)

        print('-' * 100)
        train_score = model.evaluate(x_train, y_train, batch_size=batch_size, verbose=0)
        print('Train Score: %.8f MSE (%.8f RMSE)' % (train_score, math.sqrt(train_score)))

        validate_score = model.evaluate(x_validate, y_validate, batch_size=batch_size, verbose=0)
        print('Test Score: %.8f MSE (%.8f RMSE)' % (validate_score, math.sqrt(validate_score)))

        train_predict = model.predict(x_train)
        validate_predict = model.predict(x_validate)
        test_predict = model.predict(x_test)

        # 예측값을 원래크기 값으로 회복
        train_predict = inverse_normalize_data(train_predict, scaler)
        y_train = inverse_normalize_data(y_train, scaler)
        validate_predict = inverse_normalize_data(validate_predict, scaler)
        y_validate = inverse_normalize_data(y_validate, scaler)
        test_predict = inverse_normalize_data(test_predict, scaler)

        '''
        print('-' * 100)
        print("last y_validate: \n", y_validate[-1])
        print("last y_predict: \n", validate_predict[-1])
        print("test: \n", test_predict)
        '''

        #  3: close의 열위치, 0:5 5일 예측
        ans = np.append(y_validate[-1, -1, 3], test_predict[-1, 0:5, 3])
        output.append(ans)
        #print("output: \n", output)

        # 예측값 그래프 (save in images/result)
        file_name = 'result_' + model_name + '_00{}'.format(_class)
        plot_predict(y_validate, validate_predict, file_name=file_name)

        # 손실 그래프 (save in images/loss)
        file_name = 'loss_' + model_name + '_00{}'.format(_class)
        plot_loss(history, file_name)

    output = np.array(output)
    #print(output)
    generate_output(output, model_name=model_name, class_list=class_list)


# ---- Cell ----

