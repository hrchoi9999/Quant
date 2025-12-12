# English filename: run_training_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/1. 금융시계열_LSTM과Atttention/1. LSTM/run_training.py
# Original filename: run_training.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_pytorch/data.zip&& unzip -n data.zip
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_pytorch/models.zip&& unzip -n models.zip
!wget -nc http://youngminhome.iptime.org:5555/shared/wae_lstm_pytorch/utils.zip && unzip -n utils.zip

# ---- Cell ----
!pip install PyWavelets

# ---- Cell ----
import warnings
warnings.filterwarnings('ignore')
%matplotlib inline
## 외부 패키지
import pandas as pd
import numpy as np
import pickle
import shutil
import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import torch.nn.functional as F
import numpy as np
import sklearn
import time
import os
import random
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt

##내부 함수
from models import Autoencoder
from models import Sequence
from models import waveletSmooth

from utils import prepare_data_lstm, ExampleDataset, save_checkpoint, evaluate_lstm, backtest

# ---- Cell ----

# ---------------------------------------------------------------------------
# --------------------------- 1단계: 데이터 로딩 -----------------------------
# ---------------------------------------------------------------------------

path = "data/S_P500IndexData-Table1.csv"
data_master = pd.read_csv(path, sep=";")

# ---- Cell ----
tmp = pd.Series([1,2,3])

# ---- Cell ----
tmp.values

# ---- Cell ----


# 600일을 사용 (2년 이상)
num_datapoints = 600
# 60일 단위로 롤링 (3개월 정도의 트레이딩일)
step_size = int(0.1 * num_datapoints)
# 전체에 대해서 반복시행을 돌릴 수 있는 회수를 계산
num_iterations = int(np.ceil((len(data_master)-num_datapoints)/step_size))+2

y_test_lst = []
preds = []
ct = 0

for n in range(num_iterations):
    print(n)
    data = data_master.iloc[n*step_size:num_datapoints+n*step_size,:]
    data.columns = [col.strip() for col in data.columns.tolist()]
    print(data.shape)
    ct +=1

    feats = data.iloc[:,2:]

    # 입력 단위 조정
    feats["Close Price"].loc[:] = feats["Close Price"].loc[:]/1000
    feats["Open Price"].loc[:] = feats["Open Price"].loc[:]/1000
    feats["High Price"].loc[:] = feats["High Price"].loc[:]/1000
    feats["Low Price"].loc[:] = feats["Low Price"].loc[:]/1000
    feats["Volume"].loc[:] = feats["Volume"].loc[:]/1000000
    feats["MACD"].loc[:] = feats["MACD"].loc[:]/10
    feats["CCI"].loc[:] = feats["CCI"].loc[:]/100
    feats["ATR"].loc[:] = feats["ATR"].loc[:]/100
    feats["BOLL"].loc[:] = feats["BOLL"].loc[:]/1000
    feats["EMA20"].loc[:] = feats["EMA20"].loc[:]/1000
    feats["MA10"].loc[:] = feats["MA10"].loc[:]/1000
    feats["MTM6"].loc[:] = feats["MTM6"].loc[:]/100
    feats["MA5"].loc[:] = feats["MA5"].loc[:]/1000
    feats["MTM12"].loc[:] = feats["MTM12"].loc[:]/100
    feats["ROC"].loc[:] = feats["ROC"].loc[:]/10
    feats["SMI"].loc[:] = feats["SMI"].loc[:] * 10
    feats["WVAD"].loc[:] = feats["WVAD"].loc[:]/100000000
    feats["US Dollar Index"].loc[:] = feats["US Dollar Index"].loc[:]/100
    feats["Federal Fund Rate"].loc[:] = feats["Federal Fund Rate"].loc[:]

    data_close = feats["Close Price"].copy()
    data_close_new = data_close

    # 훈련-검증-테스트셋 분리

    test = feats[-step_size:]
    validate = feats[-2*step_size:-step_size]
    train = feats[:-2*step_size]

    y_test = data_close_new[-step_size:].values
    y_validate = data_close_new[-2*step_size:-step_size].values
    y_train = data_close_new[:-2*step_size].values
    feats_train = train.values.astype(np.float64)
    feats_validate = validate.values.astype(np.float64)
    feats_test = test.values.astype(np.float64)

    # ---------------------------------------------------------------------------
    # ----------------------- 2단계: 데이터 정규화 --------------------------
    # ---------------------------------------------------------------------------

    # 여기서는 정규화 대신 위의 크기 조정을 상용

    """
    scaler = StandardScaler().fit(feats_train)

    feats_norm_train = scaler.transform(feats_train)
    feats_norm_validate = scaler.transform(feats_validate)
    feats_norm_test = scaler.transform(feats_test)
    """
    """
    scaler = MinMaxScaler(feature_range=(0,1))
    scaler.fit(feats_train)

    feats_norm_train = scaler.transform(feats_train)
    feats_norm_validate = scaler.transform(feats_validate)
    feats_norm_test = scaler.transform(feats_test)
    """
    data_close = pd.Series(np.concatenate((y_train, y_validate, y_test)))

    feats_norm_train = feats_train.copy()
    feats_norm_validate = feats_validate.copy()
    feats_norm_test = feats_test.copy()

    # ---------------------------------------------------------------------------
    # ----------------------- 2-1단계: DWT를 사용해 잡음제거-----------------------
    # ---------------------------------------------------------------------------

    for i in range(feats_norm_train.shape[1]):
        feats_norm_train[:,i] = waveletSmooth(feats_norm_train[:,i], level=1)[-len(feats_norm_train):]

    # 검증을 위해 훈련데이터 + 현재 이전의 검증데이터를 사용해 변환
    # 미래를 볼 수 없으므로 검증데이터 모두를 사용할 수 없다.
    temp = np.copy(feats_norm_train)
    feats_norm_validate_WT = np.copy(feats_norm_validate)
    for j in range(feats_norm_validate.shape[0]):
        # 우선 훈련셋과 최근 검증 샘플을 결합(concatenate)한다.
        temp = np.append(temp, np.expand_dims(feats_norm_validate[j,:], axis=0), axis=0)
        for i in range(feats_norm_validate.shape[1]):
            feats_norm_validate_WT[j,i] = waveletSmooth(temp[:,i], level=1)[-1]

    # 테스트를 위해서는 훈련데이터+검증데이터+과거테스트데이터를 사용해 변환
    # 즉 미래를 볼 수 없으므로 테스트데이터 모두를 사용할 수 없다.
    temp_train = np.copy(feats_norm_train)
    temp_val = np.copy(feats_norm_validate)
    temp = np.concatenate((temp_train, temp_val))
    feats_norm_test_WT = np.copy(feats_norm_test)
    for j in range(feats_norm_test.shape[0]):
        #우선 훈련과 최근 검증 샘플과 결합한다.
        temp = np.append(temp, np.expand_dims(feats_norm_test[j,:], axis=0), axis=0)
        for i in range(feats_norm_test.shape[1]):
            feats_norm_test_WT[j,i] = waveletSmooth(temp[:,i], level=1)[-1]

    # ---------------------------------------------------------------------------
    # ------------- 3단계: 적층 오토인코더를 사용한 특성 추출 -----------
    # ---------------------------------------------------------------------------

    num_hidden_1 = 10
    num_hidden_2 = 10
    num_hidden_3 = 10
    num_hidden_4 = 10

    n_epoch=100#20000

    # ---- 훈련셋으로 학습

    # n=0에서 네트워크를 설정하고 학습 진행

    if n == 0:
        auto1 = Autoencoder(feats_norm_train.shape[1], num_hidden_1)
    auto1.fit(feats_norm_train, n_epoch=n_epoch)

    inputs = torch.autograd.Variable(torch.from_numpy(feats_norm_train.astype(np.float32)))

    if n == 0:
        auto2 = Autoencoder(num_hidden_1, num_hidden_2)
    auto1_out = auto1.encoder(inputs).data.numpy()
    auto2.fit(auto1_out, n_epoch=n_epoch)

    if n == 0:
        auto3 = Autoencoder(num_hidden_2, num_hidden_3)
    auto1_out = torch.autograd.Variable(torch.from_numpy(auto1_out.astype(np.float32)))
    auto2_out = auto2.encoder(auto1_out).data.numpy()
    auto3.fit(auto2_out, n_epoch=n_epoch)

    if n == 0:
        auto4 = Autoencoder(num_hidden_3, num_hidden_4)
    auto2_out = torch.autograd.Variable(torch.from_numpy(auto2_out.astype(np.float32)))
    auto3_out = auto3.encoder(auto2_out).data.numpy()
    auto4.fit(auto3_out, n_epoch=n_epoch)


    # 평가모드에서 네트워크는 다르게 작동 즉 dropout이 꺼지는 등
    auto1.eval()
    auto2.eval()
    auto3.eval()
    auto4.eval()

    X_train = feats_norm_train
    X_train = torch.autograd.Variable(torch.from_numpy(X_train.astype(np.float32)))
    train_encoded = auto4.encoder(auto3.encoder(auto2.encoder(auto1.encoder(X_train))))
    train_encoded = train_encoded.data.numpy()

    # 훈련셋으로 학습한 오토인코더를 이용해 검증과 테스트 데이터 인코딩
    X_validate = feats_norm_validate_WT
    X_validate = torch.autograd.Variable(torch.from_numpy(X_validate.astype(np.float32)))
    validate_encoded = auto4.encoder(auto3.encoder(auto2.encoder(auto1.encoder(X_validate))))
    validate_encoded = validate_encoded.data.numpy()

    X_test = feats_norm_test_WT
    X_test = torch.autograd.Variable(torch.from_numpy(X_test.astype(np.float32)))
    test_encoded = auto4.encoder(auto3.encoder(auto2.encoder(auto1.encoder(X_test))))
    test_encoded = test_encoded.data.numpy()

    # 훈련모드로 다시 전환
    auto1.train()
    auto2.train()
    auto3.train()
    auto4.train()


    # ---------------------------------------------------------------------------
    # -------------------- 4 단계: 시계열 준비        --------------------------
    # ---------------------------------------------------------------------------

    # 전체 시계열을 LSTM에서 설정하고자 하는 타임스텝에 맞춰서 샘플로 분리

    time_steps = 4

    args = (train_encoded, validate_encoded, test_encoded)

    x_concat = np.concatenate(args)

    validate_encoded_extra = np.concatenate((train_encoded[-time_steps:], validate_encoded))
    test_encoded_extra = np.concatenate((validate_encoded[-time_steps:], test_encoded))

    y_train_input = data_close[:-len(validate_encoded)-len(test_encoded)]
    y_val_input = data_close[-len(test_encoded)-len(validate_encoded)-1:-len(test_encoded)]
    y_test_input = data_close[-len(test_encoded)-1:]

    x, y = prepare_data_lstm(train_encoded, y_train_input, time_steps, log_return=True, train=True)
    x_v, y_v = prepare_data_lstm(validate_encoded_extra, y_val_input, time_steps, log_return=False, train=False)
    x_te, y_te = prepare_data_lstm(test_encoded_extra, y_test_input, time_steps, log_return=False, train=False)


    x_test = x_te
    x_validate = x_v
    x_train = x

    y_test = y_te
    y_validate = y_v
    y_train = y

    y_train = y_train.values

    # ---------------------------------------------------------------------------
    # ------------- 5단계: LSTM을 이용한 시계열 회귀분석 -------------------
    # ---------------------------------------------------------------------------

    batchsize = 60

    trainloader = ExampleDataset(x_train, y_train, batchsize)
    valloader = ExampleDataset(x_validate, y_validate, 1)
    testloader = ExampleDataset(x_test, y_test, 1)

    # 랜덤시드를 0로 설정
    np.random.seed(0)
    torch.manual_seed(0)

    # 모델 구축
    if n == 0:
        seq = Sequence(num_hidden_4, hidden_size=100, nb_layers=3)

    resume = ""

    # 경로가 resume에 주어져 있으면, 체크포인트로부터 resume한다.
    if os.path.isfile(resume):
        print("=> loading checkpoint '{}'".format(resume))
        checkpoint = torch.load(resume)
        start_epoch = checkpoint['epoch']
        seq.load_state_dict(checkpoint['state_dict'])
        print("=> loaded checkpoint '{}' (epoch {})"
              .format(resume, checkpoint['epoch']))
    else:
        print("=> no checkpoint found at '{}'".format(resume))

    # 모델 파라미터를 얻는다.
    print('Number of model parameters: {}'.format(
        sum([p.data.nelement() for p in seq.parameters()])))

    # MSE를 사용
    criterion = nn.MSELoss()

    optimizer = optim.Adam(params=seq.parameters(), lr=0.0005)

    start_epoch = 0
    epochs = 1#5000

    global_loss_val = np.inf
    # 학습 시작
    global_profit_val = -np.inf

    for i in range(start_epoch, epochs):
        seq.train()
        loss_train = 0

        # 훈련셋만 셔플한다
        combined = list(zip(x_train, y_train))
        random.shuffle(combined)
        x_train=[]
        y_train=[]
        x_train[:], y_train[:] = zip(*combined)

        # 셔플된 훈련데이터로 trainloader를 초기화한다.
        trainloader = ExampleDataset(x_train, y_train, batchsize)

        pred_train = []
        target_train = []
        for j in range(len(trainloader)):
            sample = trainloader[j]
            sample_x = sample["x"]

            if len(sample_x) != 0:

                sample_x = np.stack(sample_x)
                input = Variable(torch.FloatTensor(sample_x), requires_grad=False)
                input = torch.transpose(input, 0, 1)
                target = Variable(torch.FloatTensor([x for x in sample["y"]]), requires_grad=False)

                optimizer.zero_grad()
                out = seq(input)
                loss = criterion(out, target)

                loss_train += float(loss.data.numpy())
                pred_train.extend(out.data.numpy().flatten().tolist())
                target_train.extend(target.data.numpy().flatten().tolist())

                loss.backward()

                optimizer.step()


        if i % 100 == 0:

            plt.plot(pred_train)
            plt.plot(target_train)
            plt.show()

            loss_val, pred_val, target_val = evaluate_lstm(dataloader=valloader, model=seq, criterion=criterion)

            plt.scatter(range(len(pred_val)), pred_val)
            plt.scatter(range(len(pred_val)), target_val)
            plt.show()

            index, real = backtest(pred_val, y_validate)

            print(index[-1])
            # 수익성에 따라 저장
            if index[-1]>global_profit_val and i>200:
                print("CURRENT BEST")
                global_profit_val = index[-1]
                save_checkpoint({'epoch': i + 1, 'state_dict': seq.state_dict()}, is_best=True, filename='checkpoint_lstm.pth.tar')

            save_checkpoint({'epoch': i + 1, 'state_dict': seq.state_dict()}, is_best=False, filename='checkpoint_lstm.pth.tar')

            print("LOSS TRAIN: " + str(float(loss_train)))
            print("LOSS VAL: " + str(float(loss_val)))
            print(i)

    # 마지막 테스트 실행
    # 우선 검증셋에서 최적 체크포인트를 로딩한다.

    resume = "./runs/checkpoint/model_best.pth.tar"
    #resume = "./runs/HF/checkpoint_lstm.pth.tar"

    if os.path.isfile(resume):
        print("=> loading checkpoint '{}'".format(resume))
        checkpoint = torch.load(resume)
        start_epoch = checkpoint['epoch']
        seq.load_state_dict(checkpoint['state_dict'])
        print("=> loaded checkpoint '{}' (epoch {})"
              .format(resume, checkpoint['epoch']))
    else:
        print("=> no checkpoint found at '{}'".format(resume))

    seq.eval()

    loss_test, preds_test, target_test = evaluate_lstm(dataloader=testloader, model=seq, criterion=criterion)

    print("LOSS TEST: " + str(float(loss_test)))

    temp2 = y_test.values.flatten().tolist()
    y_test_lst.extend(temp2)

    plt.plot(preds_test)
    plt.plot(y_test_lst)
    plt.scatter(range(len(preds_test)), preds_test)
    plt.scatter(range(len(y_test_lst)), y_test_lst)
    plt.savefig("test_preds.pdf")

    # ---------------------------------------------------------------------------
    # ------------------ STEP 6: BACKTEST (ARTICLE WAY) -------------------------
    # ---------------------------------------------------------------------------

    index, real = backtest(preds_test, pd.DataFrame(y_test_lst))

    plt.close()
    plt.plot(index, label="strat")
    plt.plot(real, label="bm")
    plt.legend()
    plt.savefig("performance_article_way.pdf")
    plt.close()



# ---- Cell ----

