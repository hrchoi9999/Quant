# English filename: lstm_layer_input_output_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/14일차 딥러닝 시계열의 이해_한국주식실습/1 RNN과 LSTM_기초실습/LSTM Layer  input output_clear.py
# Original filename: LSTM Layer  input output_clear.py

# ---- Cell ----
import tensorflow as tf

# ---- Cell ----
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, LSTM, Dense

# ---- Cell ----
import numpy as np

# ---- Cell ----
from tensorflow.keras.preprocessing.text import one_hot

# ---- Cell ----
# 문서의 정의
docs = ['glass of orange juice',
       'bottle of mango juice',
       'glass of mango shake',
       'drink bottle of banana shake',
       'I wnat a glass of cold water',
       'The king and the queen',
       'mand and woman']

# ---- Cell ----
vocab_size =10000

# ---- Cell ----
# 원핫인코딩해보자
encoded_docs = [one_hot(d, vocab_size) for d in docs]

# ---- Cell ----
print(encoded_docs)

# ---- Cell ----
embedding_length = 5 # 임베딩 길이 (단어 하나를 5개의 유닛으로 표현해보자.)
max_doc_len = 10  # 문장 길이

# ---- Cell ----
# 다음의 pad_sequence를 이용해서 10개의 길이가 되도록 패딩 연습해보자. (디폴트인 pre 대신 post를 사용하라)
# (https://www.tensorflow.org/api_docs/python/tf/keras/preprocessing/sequence/pad_sequences)
# tf.keras.preprocessing.sequence.pad_sequences(
#     sequences, maxlen=None, dtype='int32', padding='pre',
#     truncating='pre', value=0.0)

# ---- Cell ----
encoded_docs = pad_sequences(encoded_docs, truncating='post', padding='post', maxlen=max_doc_len)

# ---- Cell ----
print(encoded_docs)

# ---- Cell ----
#힌트: Embedding() 찾아보자 (https://www.tensorflow.org/api_docs/python/tf/keras/layers/Embedding)
# tf.keras.layers.Embedding(
#     input_dim, output_dim, embeddings_initializer='uniform',
#     embeddings_regularizer=None, activity_regularizer=None,
#     embeddings_constraint=None, mask_zero=False, input_length=None, **kwargs
# )
# 이중 input_dim, output_dim과 input_length를 정의해보자.

# ---- Cell ----
model=Sequential()
model.add(Embedding(vocab_size, embedding_length, input_length=max_doc_len))


model.compile('adam', 'mse')
model.summary()

# ---- Cell ----
# 위에서 만든 모델을 이용해 예측하라.
output=model.predict(encoded_docs)
print(output.shape)
print(output)

# ---- Cell ----
# 은닉상태의 차원은 64로 지정하라.

model=Sequential()
model.add(Embedding(vocab_size, embedding_length, input_length=max_doc_len))
model.add(LSTM(units=64))
model.compile('adam', 'mse')
model.summary()

# ---- Cell ----
# LSTM의 출력을 산출하고 이의 차원을 확인하라.

output=model.predict(encoded_docs)
print(output.shape)
print(output)

# ---- Cell ----
# 힌트: 임베딩 -> LSTM -> Dense, 출력의 갯수가 하나이므로 활성함수를 sigmoid로 사용하라.

# ---- Cell ----
model=Sequential()
model.add(Embedding(vocab_size, embedding_length, input_length=max_doc_len))
model.add(LSTM(units=64))
model.add(Dense(1, activation='sigmoid'))

model.compile('adam', 'binary_cross_entropy')
model.summary()

# ---- Cell ----
# 확장된 LSTM의 출력을 산출하고 이의 차원을 확인하라.

# ---- Cell ----
output=model.predict(encoded_docs)
print(output.shape)
print(output)

# ---- Cell ----

