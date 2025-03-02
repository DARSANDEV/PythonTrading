
import json
import pandas as pd
from datetime import datetime
import pytz
import websocket
from IPython.display import clear_output, display

# Define IST timezone
ist = pytz.timezone('Asia/Kolkata')

# Store error messages
error_logs = []

# WebSocket URL
socketUrl = "wss://data.tradingview.com/socket.io/websocket"
#symbols = ['NSE:NIFTY','NSE:BANKNIFTY','NASDAQ:COIN','BINANCE:BTCUSD']
selected_symbol = "NSE:NIFTY"
time_frame = "5"
period = 1000

# Create empty DataFrame
df = pd.DataFrame(columns=['TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume'])

# WebSocket Event Handlers
def on_message(ws, message):
    """Handles incoming WebSocket messages."""
    try:
        start = message.find('"s":[')
        ends = message.find(',"ns":{')
        fdata = json.loads(message[start+4:ends])

        if isinstance(fdata, list):
            for item in fdata:
                if 'v' in item:
                    # Convert timestamp to IST
                    timestamp_utc = datetime.utcfromtimestamp(item['v'][0])  # Assuming first value is timestamp
                    timestamp_ist = timestamp_utc.replace(tzinfo=pytz.utc).astimezone(ist)

                    # Replace the original timestamp with IST
                    item['v'][0] = timestamp_ist.strftime('%Y-%m-%d %H:%M:%S')  # Format as string

                    # Append to DataFrame
                    df.loc[len(df)] = item['v']
                else:
                    error_logs.append(f"Warning: Item does not have 'v' key: {item}")
        else:
            error_logs.append(f"Error: fdata is not a list. Type: {type(fdata)}, Value: {fdata}")

    except Exception as e:
        error_logs.append(f"Error extracting candle data: {e}")

    clear_output(wait=True)

    for error in error_logs:
        print(error)
    display(df)

def on_error(ws, error):
    """Handles WebSocket errors."""
    print(f"WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    """Handles WebSocket closure."""
    print("WebSocket Closed")

def on_open(ws):
    """Sends initialization messages when WebSocket is opened."""
    print("WebSocket Connection Established!")

    def create_message(func, arg):
        ms = json.dumps({"m": func, "p": arg})
        msg = f"~m~{len(ms)}~m~{ms}"
        ws.send(msg)

    # Send necessary TradingView subscription messages
    session_id = "0.13918.2153_mum1-charts-26-webchart-16"
    create_message("chart_create_session", [session_id, ""])
    
    chart_id = '=' + json.dumps({"adjustment": "splits", "session": "regular", "symbol": selected_symbol})
    create_message("resolve_symbol", [session_id, "sds_sym_1", chart_id])
    create_message("create_series", [session_id, "sds_1", "s1", "sds_sym_1", time_frame, period, ""])


# Initialize WebSocketApp
ws = websocket.WebSocketApp(socketUrl, 
                            on_message=on_message, 
                            on_error=on_error, 
                            on_close=on_close)

ws.on_open = on_open  # Attach open event

# Run WebSocket
ws.run_forever()
# from IPython import get_ipython
# from IPython.display import display
import numpy as np

import pandas as pd
#import yfinance as yf
#import pandas as ta
import pandas_ta as ta

# Download data
data = yf.download(tickers='^RUI', start='2012-03-11', end='2022-07-10')

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