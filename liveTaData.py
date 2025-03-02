#pip install ipython

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
selected_symbol = "BINANCE:BTCUSD"
time_frame = "5"
period = 5

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
