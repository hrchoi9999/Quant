# English filename: 5_lstm_model_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/1. 금융시계열_LSTM과Atttention/1. LSTM/5. LSTM_model.py
# Original filename: 5. LSTM_model.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_keras/features.zip&& unzip -n features.zip
!mkdir sample_predictions
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_keras/stock_data_test.csv

# ---- Cell ----
import keras.layers as kl
from keras.models import Model
from keras import regularizers
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from bokeh.plotting import output_file, figure, show
%matplotlib inline
fig = plt.figure(figsize=(12,5))

class NeuralNetwork:
    def __init__(self, input_shape, stock_or_return):
        self.input_shape = input_shape
        self.stock_or_return = stock_or_return

    def make_train_model(self):
        input_data = kl.Input(shape=(1, self.input_shape))
        lstm = kl.LSTM(5, input_shape=(1, self.input_shape), return_sequences=True, activity_regularizer=regularizers.l2(0.003),
                       recurrent_regularizer=regularizers.l2(0), dropout=0.2, recurrent_dropout=0.2)(input_data)
        perc = kl.Dense(5, activation="sigmoid", activity_regularizer=regularizers.l2(0.005))(lstm)
        lstm2 = kl.LSTM(2, activity_regularizer=regularizers.l2(0.01), recurrent_regularizer=regularizers.l2(0.001),
                        dropout=0.2, recurrent_dropout=0.2)(perc)
        out = kl.Dense(1, activation="sigmoid", activity_regularizer=regularizers.l2(0.001))(lstm2)

        model = Model(input_data, out)
        model.compile(optimizer="adam", loss="mean_squared_error", metrics=["mse"])

        # load data

        train = np.reshape(np.array(pd.read_csv("features/autoencoded_train_data.csv", index_col=0)),
                           (len(np.array(pd.read_csv("features/autoencoded_train_data.csv"))), 1, self.input_shape))
        train_y = np.array(pd.read_csv("features/autoencoded_train_y.csv", index_col=0))
        # train_stock = np.array(pd.read_csv("train_stock.csv"))

        # train model

        model.fit(train, train_y, epochs=20)

        model.save("models/model.h5", overwrite=True, include_optimizer=True)

        test_x = np.reshape(np.array(pd.read_csv("features/autoencoded_test_data.csv", index_col=0)),
                            (len(np.array(pd.read_csv("features/autoencoded_test_data.csv"))), 1, self.input_shape))
        test_y = np.array(pd.read_csv("features/autoencoded_test_y.csv", index_col=0))
        # test_stock = np.array(pd.read_csv("test_stock.csv"))

        stock_data_test = np.array(pd.read_csv("stock_data_test.csv", index_col=0))

        print(model.evaluate(test_x, test_y))
        prediction_data = []
        stock_data = []
        print(len(test_y))
        print(len(stock_data_test))
        for i in range(len(test_y)):
            prediction = (model.predict(np.reshape(test_x[i], (1, 1, self.input_shape))))
            prediction_data.append(np.reshape(prediction, (1,)))
            prediction_corrected = (prediction_data - np.mean(prediction_data))/(np.std(prediction_data)+0.0001)
            stock_price = np.exp(np.reshape(prediction, (1,)))*stock_data_test[i]
            stock_data.append(stock_price[0])
        stock_data[:] = [i - (float(stock_data[0])-float(stock_data_test[0])) for i in stock_data]
        # stock_data = stock_data - stock_data[0]
        if self.stock_or_return:
            plt.plot(stock_data, 'r')
            plt.plot(stock_data_test, 'b')
            stock = pd.DataFrame(stock_data, index=None)
            stock.to_csv("sample_predictions/AAPL_predicted_prices.csv")
            stock_test = pd.DataFrame(stock_data_test, index=None)
            stock_test.to_csv("sample_predictions/AAPL_actual_prices.csv")
            # print(stock_data)
            plt.show()
        else:
            plt.plot(prediction_corrected, 'r')
            #plt.plot(prediction_data, 'r')
            #print(prediction_data)
            plt.plot(test_y, 'b')
            plt.show()


if __name__ == "__main__":
    model = NeuralNetwork(20, True)
    model.make_train_model()
    print('completed')


# ---- Cell ----

