import numpy as np
import tensorflow as tf
from keras.models import Model
from keras.layers import LSTM, Dense, Input, Activation
from sklearn.preprocessing import MinMaxScaler

def train_lstm_model(data):
    """Trains LSTM model and returns trained model."""
    data_set = data.iloc[:, 0:11]
    sc = MinMaxScaler(feature_range=(0, 1))
    data_set_scaled = sc.fit_transform(data_set)

    X, y = [], []
    backcandles = 30
    for i in range(backcandles, data_set_scaled.shape[0]):
        X.append(data_set_scaled[i - backcandles:i])
        y.append(data_set_scaled[i, -1])

    X, y = np.array(X), np.array(y).reshape(-1, 1)

    # Split data
    splitlimit = int(len(X) * 0.8)
    X_train, X_test = X[:splitlimit], X[splitlimit:]
    y_train, y_test = y[:splitlimit], y[splitlimit:]

    # Model definition
    lstm_input = Input(shape=(backcandles, 11), name='lstm_input')
    inputs = LSTM(150, name='first_layer')(lstm_input)
    inputs = Dense(1, name='dense_layer')(inputs)
    output = Activation('linear', name='output')(inputs)
    model = Model(inputs=lstm_input, outputs=output)
    
    model.compile(optimizer='adam', loss='mse')
    model.fit(X_train, y_train, batch_size=15, epochs=30, validation_split=0.1)

    return model, X_test, y_test
