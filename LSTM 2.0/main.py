from data_collector import get_live_data
from indicators import add_indicators
from lstm_model import train_lstm_model
import matplotlib.pyplot as plt

# Step 1: Get live market data
df = get_live_data()

# Step 2: Add indicators
df = add_indicators(df)

# Step 3: Train LSTM model
model, X_test, y_test = train_lstm_model(df)

# Step 4: Make predictions
y_pred = model.predict(X_test)

# Step 5: Plot results
plt.figure(figsize=(16, 8))
plt.plot(y_test, color='black', label='Test')
plt.plot(y_pred, color='green', label='Prediction')
plt.legend()
plt.show()
