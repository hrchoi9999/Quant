# English filename: recurrent_neural_network_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/14일차 딥러닝 시계열의 이해_한국주식실습/1 RNN과 LSTM_기초실습/Recurrent_Neural_Network_old_clear.py
# Original filename: Recurrent_Neural_Network_old_clear.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/base_deep_learning_data/data-02-stock_daily.csv

# ---- Cell ----
## 라이브러리 임포트
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.utils import to_categorical
import numpy as np
import matplotlib.pyplot as plt
import os

print(tf.__version__)

# ---- Cell ----
# 'hello'의 각 문자를 원핫인코딩한다.
h = [1, 0, 0, 0]
e = [0, 1, 0, 0]
l = [0, 0, 1, 0]
o = [0, 0, 0, 1]

# ---- Cell ----
### 힌트: SimpleRNN을 사용하고, units= hidden_size, return_sequences=True, return_state=True)로 설정해보라.
x_data = np.array([[h]], dtype=np.float32)

hidden_size = 2

rnn = layers.SimpleRNN(units=hidden_size, return_sequences=True,
                       return_state=True) # layers.SimpleRNNCell + layers.RNN

outputs, states = rnn(x_data)

print('x_data: {}, shape: {}'.format(x_data, x_data.shape))
print('outputs: {}, shape: {}'.format(outputs, outputs.shape))
print('states: {}, shape: {}'.format(states, states.shape))

# ---- Cell ----
# 여전히 One cell RNN을 사용한다. 단 sequence가 5가 된다.
# input_dim (4) -> output_dim (2)

x_data = np.array([[h, e, l, l, o]], dtype=np.float32)

hidden_size = 2
rnn = layers.SimpleRNN(units=2, return_sequences=True, return_state=True)
outputs, states = rnn(x_data)

print('x_data: {}, shape: {} \n'.format(x_data, x_data.shape))
print('outputs: {}, shape: {} \n'.format(outputs, outputs.shape))
print('states: {}, shape: {}'.format(states, states.shape))

# ---- Cell ----
# 여전히 One cell RNN을 사용한다. 이번에는 배치가 3이다.
# input_dim (4) -> output_dim (2). sequence: 5, batch 3
# 3 배치는 다음으로 하자 (임의)
# 'hello', 'eolll', 'lleel'

x_data = np.array([[h, e, l, l, o],
                   [e, o, l, l, l],
                   [l, l, e, e, l]], dtype=np.float32)

hidden_size = 2
rnn = layers.SimpleRNN(units=2, return_sequences=True, return_state=True)
outputs, states = rnn(x_data)

print('x_data: {}, shape: {} \n'.format(x_data, x_data.shape))
print('outputs: {}, shape: {} \n'.format(outputs, outputs.shape))
print('states: {}, shape: {}'.format(states, states.shape))

# ---- Cell ----
# return_sequences=False로 놓고 결과를 확인하라.
rnn = layers.SimpleRNN(units=2, return_sequences=False, return_state=True)
outputs, states = rnn(x_data)

print('x_data: {}, shape: {} \n'.format(x_data, x_data.shape))
print('outputs: {}, shape: {} \n'.format(outputs, outputs.shape))
print('states: {}, shape: {}'.format(states, states.shape))

# ---- Cell ----
# return_state=False도 추가하고 결과를 살펴보자.
rnn = layers.SimpleRNN(units=2, return_sequences=False, return_state=False)

outputs= rnn(x_data)

print('x_data: {}, shape: {} \n'.format(x_data, x_data.shape))
print('outputs: {}, shape: {} \n'.format(outputs, outputs.shape))

# ---- Cell ----
rnn = layers.LSTM(units=2, return_sequences=True, return_state=True)
outputs, h_states, c_states = rnn(x_data)

print('x_data: {}, shape: {} \n'.format(x_data, x_data.shape))
print('outputs: {}, shape: {} \n'.format(outputs, outputs.shape))
print('hidden_states: {}, shape: {}'.format(h_states, h_states.shape))
print('cell_states: {}, shape: {}'.format(c_states, c_states.shape))

# ---- Cell ----
x_data.shape

# ---- Cell ----
rnn = layers.GRU(units=2, return_sequences=True, return_state=True)
outputs, a, b, states = rnn(x_data)

print('x_data: {}, shape: {} \n'.format(x_data, x_data.shape))
print('outputs: {}, shape: {} \n'.format(outputs, outputs.shape))
print('states: {}, shape: {}'.format(states, states.shape))

# ---- Cell ----
model = keras.Sequential()
model.add(layers.LSTM(2, return_sequences=True, input_shape=(5,4)))
model.add(layers.LSTM(2, return_sequences=True))
model.add(layers.LSTM(2, return_sequences=True))  #False 놓아도 됨.
model.summary()

# ---- Cell ----
## 하이퍼 파라미터
learning_rate = 0.001
training_epochs = 15
batch_size = 100
n_class = 10

# ---- Cell ----
## Data 준비
## MNIST Dataset #########################################################
mnist = keras.datasets.mnist
class_names = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
##########################################################################

## Fashion MNIST Dataset #################################################
#mnist = keras.datasets.fashion_mnist
#class_names = ['T-shirt/top', 'Trouser', 'Pullover', 'Dress', 'Coat', 'Sandal', 'Shirt', 'Sneaker', 'Bag', 'Ankle boot']
##########################################################################

# ---- Cell ----
## Dataset 만들기
(train_images, train_labels), (test_images, test_labels) = mnist.load_data()

n_train = train_images.shape[0]
n_test = test_images.shape[0]
print(train_images.shape, test_images.shape)

# ---- Cell ----
# pixel값을 0~1사이 범위로 조정
train_images = train_images.astype(np.float32) / 255.
test_images = test_images.astype(np.float32) / 255.

# label을 onehot-encoding
train_labels = to_categorical(train_labels, 10)
test_labels = to_categorical(test_labels, 10)

# Dataset 구성
train_dataset = tf.data.Dataset.from_tensor_slices((train_images, train_labels)).shuffle(
                buffer_size=100000).batch(batch_size).repeat()
test_dataset = tf.data.Dataset.from_tensor_slices((test_images, test_labels)).batch(batch_size).repeat()

# ---- Cell ----
## Model 만들기 (아리 서머리 참조)
def create_model():
    model = keras.Sequential()
    model.add(layers.LSTM(units=128, return_sequences=False, input_shape=(28,28)))
    model.add(layers.Dense(units=10, activation='softmax'))
    return model

# ---- Cell ----
model = create_model()
model.summary()

# ---- Cell ----
## model compile
model.compile(optimizer=keras.optimizers.Adam(learning_rate),
              loss='categorical_crossentropy',  #softmax
              metrics=['accuracy'])

# ---- Cell ----
## Training
steps_per_epoch = n_train/batch_size
validation_steps = n_test/batch_size

# ---- Cell ----
history = model.fit(
    train_dataset,
    epochs=int(training_epochs),
    steps_per_epoch=int(steps_per_epoch),
    validation_data=test_dataset,
    validation_steps=int(validation_steps)
)

# ---- Cell ----
def plot_image(i, predictions_array, true_label, img):
    predictions_array, true_label, img = predictions_array[i], true_label[i], img[i]
    plt.grid(False)
    plt.xticks([])
    plt.yticks([])

    plt.imshow(img,cmap=plt.cm.binary)

    predicted_label = np.argmax(predictions_array)
    if predicted_label == true_label:
        color = 'blue'
    else:
        color = 'red'

    plt.xlabel("{} {:2.0f}% ({})".format(class_names[predicted_label],
                                100*np.max(predictions_array),
                                class_names[true_label]),
                                color=color)

def plot_value_array(i, predictions_array, true_label):
    predictions_array, true_label = predictions_array[i], true_label[i]
    plt.grid(False)
    #plt.xticks([])
    plt.xticks(range(n_class), class_names, rotation=90)
    plt.yticks([])
    thisplot = plt.bar(range(n_class), predictions_array, color="#777777")
    plt.ylim([0, 1])
    predicted_label = np.argmax(predictions_array)

    thisplot[predicted_label].set_color('red')
    thisplot[true_label].set_color('blue')

# ---- Cell ----
rnd_idx = np.random.randint(1, n_test//batch_size)
img_cnt = 0
for images, labels in test_dataset:
    img_cnt += 1
    if img_cnt != rnd_idx:
        continue
    predictions = model(images, training=False)
    num_rows = 5
    num_cols = 3
    num_images = num_rows*num_cols
    labels = tf.argmax(labels, axis=-1)
    plt.figure(figsize=(3*2*num_cols, 4*num_rows))
    plt.subplots_adjust(hspace=1.0)
    for i in range(num_images):
        plt.subplot(num_rows, 2*num_cols, 2*i+1)
        plot_image(i, predictions.numpy(), labels.numpy(), images.numpy())
        plt.subplot(num_rows, 2*num_cols, 2*i+2)
        plot_value_array(i, predictions.numpy(), labels.numpy())
    break

# ---- Cell ----
## 하이퍼 파라미터
seq_length = 7
data_dim = 5
hidden_size = 10
output_dim = 1
learning_rate = 0.001
training_epochs = 500
batch_size = 25

# ---- Cell ----
## 데이터 전처리
def MinMaxScaler(data):
    numerator = data - np.min(data, 0)
    denominator = np.max(data, 0) - np.min(data, 0)
    # noise term prevents the zero division
    return numerator / (denominator + 1e-7)

# ---- Cell ----
# ## Google Drive 동기화
# from google.colab import drive
# drive.mount('/content/drive')

# ---- Cell ----
## 데이타 로딩
# 시가, 고가, 저가, 거래량, 종가의 순으로 데이터가 저장돼있다.
xy = np.loadtxt('data-02-stock_daily.csv', delimiter=',')
xy = xy[::-1]  # 데이터를 보면 날짜 순서가 거꾸로 돼있어 바로 잡는다.
xy = MinMaxScaler(xy).astype(np.float32) # 정규화하고,
x = xy           # 일단 모든 데이터를 다 사용하는데.
y = xy[:, [-1]]  # 종가를 레이블로 만든다.

# ---- Cell ----
# 데이터 구축  (LSTM에서가장 중요한 부분 중 하나)
dataX = []
dataY = []
for i in range(0, len(y) - seq_length):
    _x = x[i:i + seq_length]
    _y = y[i + seq_length]  # 다음날의 종가
    dataX.append(_x)
    dataY.append(_y)

# ---- Cell ----
print(np.array(dataX).shape)
print(np.array(dataY).shape)

# ---- Cell ----
dataX[:1]

# ---- Cell ----
## 훈련/테스트셋 분리
train_size = int(len(dataY) * 0.7 + 18)
test_size = len(dataY) - train_size
trainX, testX = np.array(dataX[0:train_size]), np.array(
    dataX[train_size:len(dataX)])
trainY, testY = np.array(dataY[0:train_size]), np.array(
    dataY[train_size:len(dataY)])
print(trainX.shape, trainY.shape)
print(testX.shape, testY.shape)

# ---- Cell ----
## 데이터셋을 만들자
train_dataset = tf.data.Dataset.from_tensor_slices((trainX, trainY)).shuffle(
                buffer_size=1000).prefetch(buffer_size=batch_size).batch(batch_size).repeat()
test_dataset = tf.data.Dataset.from_tensor_slices((testX, testY)).prefetch(
                buffer_size=batch_size).batch(batch_size)

# ---- Cell ----
## 모델을 만들자.
def create_model():
    model = keras.Sequential()
    model.add(keras.layers.LSTM(units=hidden_size, return_sequences=True,
                                     input_shape=(trainX.shape[1],trainX.shape[2])))
    model.add(keras.layers.LSTM(units=hidden_size))
    model.add(keras.layers.Dense(units=output_dim))
    return model

# ---- Cell ----
model = create_model()
model.summary()

# ---- Cell ----
## 손실함수와 최적화 정의
def rmse_opt(learning_rate):
    return keras.optimizers.RMSprop(learning_rate)

model.compile(optimizer=rmse_opt(learning_rate),
              loss='mse',
              metrics=[keras.metrics.RootMeanSquaredError()])  #RMSE

# ---- Cell ----
## 적합화
model.fit(train_dataset, epochs=training_epochs,
          steps_per_epoch=trainX.shape[0]//batch_size,
          validation_data=test_dataset,
          )

# ---- Cell ----
## 결과 확인
prediction = model.predict(test_dataset)

plt.plot(testY)
plt.plot(prediction)
plt.xlabel("Time Period")
plt.ylabel("Stock Price")
plt.legend(['real', 'prediction'])
plt.show()

# ---- Cell ----


# ---- Cell ----

