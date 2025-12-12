# English filename: model_20번실행_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/15일차 딥러닝 시계열 분석 실습_ETF실습/1. 금융시계열_LSTM과Atttention/2. Attention/model-20번실행.py
# Original filename: model-20번실행.py

# ---- Cell ----
!wget -nc http://youngminhome.iptime.org:5555/shared/stock-prediction-dual-attention-based-rnn-working/data.zip&& unzip -n data.zip

# ---- Cell ----
import torch
import numpy as np
import pandas as pd
from torch import nn
from torch import optim
import torch.nn.functional as F
import matplotlib.pyplot as plt
from torch.autograd import Variable
from torchvision import transforms, utils
from torch.utils.data import Dataset, DataLoader

# ---- Cell ----
%matplotlib inline

# ---- Cell ----
train_df=pd.read_csv('data/train.csv')
validation_df=pd.read_csv('data/validation.csv')
validation_df=pd.concat([train_df[-9:],validation_df])
validation_df=validation_df.reset_index(drop=True)
test_df=pd.read_csv('data/test.csv')
train_df.drop(['High Price', 'Low Price', 'Date'],axis=1,inplace=True)
validation_df.drop(['High Price', 'Low Price', 'Date'],axis=1,inplace=True)
test_df.drop(['High Price', 'Low Price','Date'],axis=1,inplace=True)

# ---- Cell ----
train_df.head()

# ---- Cell ----
class dataprep(Dataset):
    def __init__(self, dataframe):
        self.df=dataframe
    def __len__(self):
        return self.df.shape[0]-10
    def __getitem__(self,idx):
        if (idx+10<self.df.shape[0]):
            X=torch.from_numpy(self.df.drop('Close Price',axis=1)[idx:idx+10].values)
            targets=torch.from_numpy(self.df['Close Price'][idx:idx+9].values)
            y=torch.tensor([self.df['Close Price'].loc[idx+9]])
            return ({'X':X, 'targets':targets, 'y': y})

# ---- Cell ----
train_set=dataprep(dataframe=train_df)
validation_set=dataprep(dataframe=validation_df)
test_set=dataprep(dataframe=test_df)

# ---- Cell ----
for i in range(60,63):
    sample=validation_set[i]
    print (i,sample['X'].size(),sample['targets'].size(), sample['y'].size())

# ---- Cell ----
len(train_set)

# ---- Cell ----
train_loader = DataLoader(train_set, batch_size=15, shuffle=True)
val_loader = DataLoader(validation_set, batch_size=1, shuffle=False)
test_loader = DataLoader(test_set, batch_size=1, shuffle=False)

# ---- Cell ----
class EncoderRNN(nn.Module):
    def __init__(self,encoder_input_size=16,encoder_hidden_size=64, time_steps=10):
        super(EncoderRNN,self).__init__()
        self.input_size=encoder_input_size
        #input_size=n
        self.hidden_size=encoder_hidden_size
        #hidden_size=1
        self.t_steps=time_steps
        #time_steps=10

        self.input_attention=nn.Linear(time_steps+encoder_hidden_size,1)
        self.rnn=nn.GRU(self.input_size, self.hidden_size)

    def forward(self,encoder_input,batch_size,hidden):
        #encoder_input:batch,T,n
        encoder_input=encoder_input.permute(0,2,1) #batch,n,T
        #print (encoder_input.size())
        #hidden=self.initHidden(batch_size) #hidden : 1,batch,hidden_size
        #print (hidden.size())
        encoded = torch.zeros(batch_size, self.t_steps, self.hidden_size,device=device) #encoded: 1,T,hidden_size
        #print(encoded.size())
        for t in range(self.t_steps):
            x=torch.cat((hidden.repeat(self.input_size,1,1).permute(1,0,2),encoder_input),dim=2)
            #print (x.size())
            #x:batch,n,T+hidden_size
            x=x.view(-1,self.t_steps+self.hidden_size)
            #print (x.size())
            #x:batch*n,T+hidden_size
            x=F.softmax((self.input_attention(x)).view(-1,self.input_size),dim=1)
            #print (x.size())
            #print(encoder_input[:,t,:].size())
            #x:batch,n
            x=torch.mul(x,encoder_input[:,:,t])
            #print (x.size())
            #x:1,n
            output, hidden=self.rnn(x.unsqueeze(0), hidden)
            #print (output.size(), hidden.size())
            encoded[:,t,:]=hidden
            #output,hidden:1,1,hidden
        return encoded

    def initHidden(self,batch_size):
        return torch.zeros(1, batch_size, self.hidden_size, device=device)

# ---- Cell ----
class DecoderRNN(nn.Module):
    def __init__(self,decoder_hidden_size=64,encoder_hidden_size=64,decoder_input_size=1, time_steps=10):
        super(DecoderRNN,self).__init__()
        self.decoder_hidden_size=decoder_hidden_size
        self.encoder_hidden_size=encoder_hidden_size
        self.decoder_input_size=decoder_input_size
        self.t_steps=time_steps

        self.temporal_attention=nn.Linear(decoder_hidden_size+encoder_hidden_size, 1)
        self.rnn=nn.GRU(decoder_input_size,decoder_hidden_size)
        self.fc1 = nn.Linear(encoder_hidden_size + 1, 1)
        self.fc2 = nn.Linear(decoder_hidden_size + encoder_hidden_size, 1)

    def forward(self,encoded,y_history,batch_size,hidden):
        #encoded: batch,T,hidden_size
        #print (encoded.size())

        #y_history: batch,T-1
        #hidden=self.initHidden(batch_size) #hidden:1,batch,hidden_size
        #print (hidden.size())
        for t in range(self.t_steps):
            x=torch.cat((hidden.repeat(self.t_steps,1,1).permute(1,0,2), encoded), dim=2)
            #x:batch,T,enc_hidden_size+dec_hidden_size
            x=F.softmax(self.temporal_attention(x.view(-1,self.decoder_hidden_size+self.encoder_hidden_size)).view(-1,self.t_steps), dim=1)
            #x:batch,T
            x=torch.bmm(x.unsqueeze(1), encoded)[:,0,:]
            #x:batch,hidden_size
            if (t < self.t_steps-1):
                y_tilda=self.fc1(torch.cat((x, y_history[:, t].unsqueeze(1)), dim=1))
                output, hidden=self.rnn(y_tilda.unsqueeze(0), hidden)
        y_pred=self.fc2(torch.cat((hidden[0], x), dim = 1))

        return y_pred


    def initHidden(self,batch_size):
        return torch.zeros(1, batch_size, self.decoder_hidden_size, device=device)


# ---- Cell ----
def train(encoder,decoder,encoder_optimizer, decoder_optimizer, train_loader, loss_criterion, rl, num_epochs, epoch, epochs):
    running_loss=0
    for i, sample in enumerate(train_loader):                   #훈련셋 사용
#         x=Variable(sample['X'].type(torch.cuda.FloatTensor))
#         y=Variable(sample['targets'].type(torch.cuda.FloatTensor))
#         y_true=Variable(sample['y'].type(torch.cuda.FloatTensor))
        x=Variable(sample['X'].type(torch.FloatTensor))
        y=Variable(sample['targets'].type(torch.FloatTensor))
        y_true=Variable(sample['y'].type(torch.FloatTensor))


        encoder_optimizer.zero_grad()
        decoder_optimizer.zero_grad()

        hidden=encoder.initHidden(15)
        encoded=encoder(x,15,hidden)
        hidden=decoder.initHidden(15)
        y_pred=decoder(encoded,y,15,hidden)

        loss=loss_criterion(y_pred,y_true)
        running_loss+=loss.item()
        rl.append(loss.item())

        loss.backward()
        encoder_optimizer.step()
        decoder_optimizer.step()

    print('Epoch: {}/{} | Loss: {}'.format(epoch-epochs+1, num_epochs, running_loss))


# ---- Cell ----
def pp(y_pred,y_true):
    r=0
    for t in range(0,len(y_pred)-1):
        if((y_pred[t+1]>=y_pred[t] and y_true[t+1]>=y_true[t]) or (y_pred[t+1]<y_pred[t] and y_true[t+1]<y_true[t])):
            r=r+1
    return r/len(y_pred)

# ---- Cell ----
def evaluate(encoder,decoder, val_loader, loss_criterion, num_epochs, epoch, epochs):
    eval_loss=0
    y_predicted=[]
    y_actual=[]
    with torch.no_grad():
        for i,sample in enumerate(val_loader):               #검증셋 사용
#             x=sample['X'].type(torch.cuda.FloatTensor)
#             y=sample['targets'].type(torch.cuda.FloatTensor)
#             y_true=sample['y'].type(torch.cuda.FloatTensor)
            x=sample['X'].type(torch.FloatTensor)
            y=sample['targets'].type(torch.FloatTensor)
            y_true=sample['y'].type(torch.FloatTensor)

            hidden=encoder.initHidden(1)
            encoded=encoder(x,1,hidden)
            hidden=decoder.initHidden(1)
            y_pred=decoder(encoded,y,1,hidden)

            loss=loss_criterion(y_pred,y_true)
            eval_loss+=loss.item()
            y_predicted.append(y_pred.item())
            y_actual.append(y_true.item())

        pred_perf=pp(y_predicted, y_actual)

    plt.figure(figsize=(12, 5))
    print('Epoch: {}/{} | Evaluation_Loss: {} | Pred. Power: {}'.format(epoch-epochs+1, num_epochs, eval_loss, pred_perf))
    plt.plot(range(len(y_predicted)),y_predicted,color='red')
    plt.plot(range(len(y_actual)),y_actual,color='blue')
    #print(len(y_predicted),len(y_actual))
    plt.show()


    return eval_loss,pred_perf

# ---- Cell ----
encoder=EncoderRNN()#.cuda()
decoder = DecoderRNN()#.cuda()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ---- Cell ----
encoder_optimizer = optim.Adam(encoder.parameters())
decoder_optimizer = optim.Adam(decoder.parameters())
criterion=nn.MSELoss()

# ---- Cell ----
rl=[]
num_epochs=20 #20
epochs=0
for epoch in range(epochs,epochs+num_epochs):
    print(epoch)
    train(encoder,decoder,encoder_optimizer, decoder_optimizer,train_loader,criterion,rl,num_epochs, epoch, epochs)
    eval_loss, pred_perf=evaluate(encoder,decoder, val_loader, criterion, num_epochs, epoch, epochs)
    if (eval_loss<0.01 and pred_perf>0.5):
        print ('%---Saving the model---%')
        torch.save({
            'epoch': epoch+1,
            'encoder_state_dict': encoder.state_dict(),
            'decoder_state_dict': decoder.state_dict(),
            'encoder_optimizer_state_dict': encoder_optimizer.state_dict(),
            'decoder_optimizer_state_dict': decoder_optimizer.state_dict(),
            'loss': rl,
            },'models/OpenPrice/model_{}.pth'.format(epoch+1))


# ---- Cell ----

