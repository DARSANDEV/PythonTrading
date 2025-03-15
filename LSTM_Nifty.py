
import pandas as pd
from datetime import datetime
import pytz

from IPython.display import clear_output, display

# Define IST timezone

import numpy as np

import pandas as pd
import pandas_ta as ta
import io
df = pd.read_csv('./datas/NiftyData.csv')
#df = pd.DataFrame(columns=['TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
# Download data
print(df)


data = df
# Add indicators
data['5MIN_RSI']=ta.rsi(data.Close, length=14).round(2)
data['5MIN_EMA21']=ta.ema(data.Close, length=21).round(2)
data['5MIN_EMA9']=ta.ema(data.Close, length=9).round(2)
data['5MIN_EMA50']=ta.ema(data.Close, length=50).round(2)

data["ATR"] = data.ta.atr(length=14).round(2)
data["ADX"] = data.ta.adx(length=14)["ADX_14"].round(2)
dmi = data.ta.adx(length=14)  # ADX function also returns +DI and -DI
data["+DI"] = dmi["DMP_14"].round(2)  # Positive Directional Indicator
data["-DI"] = dmi["DMN_14"].round(2) # Negative Directional Indicator

data["Pivot"] = (data["High"] + data["Low"] + data["Close"]) / 3

# Calculate Support & Resistance Levels
data["R1"] = (2 * data["Pivot"]) - data["Low"]
data["R2"] = data["Pivot"] + (data["High"] - data["Low"])
data["S1"] = (2 * data["Pivot"]) - data["High"]
data["S2"] = data["Pivot"] - (data["High"] - data["Low"])

data[["Pivot", "S1", "S2", "R1", "R2"]] = data[["Pivot", "S1", "S2", "R1", "R2"]].round(2)

data["Adj Close"] = data["Close"].shift(1)
data['Target'] = data['Adj Close'] - data.Open
data['Target'] = data['Target'].shift(-1)

data['TargetClass'] = [1 if data.Target[i]>0 else 0 for i in range(len(data))]

data['TargetNextClose'] = data['Adj Close'].shift(-1)
#data['MACD']=ta.macd(data.Close)
#data.dropna(inplace=True)
#data.reset_index(inplace = True)

#display(data)
data.dropna(inplace=True)
data.reset_index(inplace=True)
data.drop(['Close', 'TimeStamp'], axis=1, inplace=True)

# Prepare data for scaling
data_set = data.iloc[:, 0:11] 

# Scale data
from sklearn.preprocessing import MinMaxScaler
sc = MinMaxScaler(feature_range=(0, 1))
data_set_scaled = sc.fit_transform(data_set)

# Create X and y
X = []
backcandles = 30
for j in range(8): 
    X.append([])
    for i in range(backcandles, data_set_scaled.shape[0]):
        X[j].append(data_set_scaled[i - backcandles:i, j])

X = np.moveaxis(X, [0], [2])
X, yi = np.array(X), np.array(data_set_scaled[backcandles:, -1])
y = np.reshape(yi, (len(yi), 1))

# Split data
splitlimit = int(len(X) * 0.8)
X_train, X_test = X[:splitlimit], X[splitlimit:]
y_train, y_test = y[:splitlimit], y[splitlimit:]

# Build and train model
from keras.models import Sequential, Model
from keras.layers import LSTM, Dropout, Dense, Input, Activation, concatenate
from keras import optimizers
import tensorflow as tf
import keras
#tf.random.set_seed(20)
np.random.seed(10)

lstm_input = Input(shape=(backcandles, 8), name='lstm_input')
inputs = LSTM(150, name='first_layer')(lstm_input)
inputs = Dense(1, name='dense_layer')(inputs)
output = Activation('linear', name='output')(inputs)
model = Model(inputs=lstm_input, outputs=output)
adam = optimizers.Adam()
model.compile(optimizer=adam, loss='mse')
model.fit(x=X_train, y=y_train, batch_size=15, epochs=30, shuffle=True, validation_split=0.1)

# Make predictions and plot results
y_pred = model.predict(X_test)
import matplotlib.pyplot as plt
plt.figure(figsize=(16, 8))
plt.plot(y_test, color='black', label='Test')
plt.plot(y_pred, color='green', label='pred')
plt.legend()
plt.show()