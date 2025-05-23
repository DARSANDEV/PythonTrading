import json
import pandas as pd
from datetime import datetime
import pytz
import websocket
from IPython.display import clear_output, display

# Set IST timezone
ist = pytz.timezone('Asia/Kolkata')

# List to store any error messages
error_logs = []

class DataCollector:
    def __init__(self, symbol="NSE:NIFTY", time_frame="5", period=100):
        """
        Initializes the DataCollector with the desired symbol, time frame, and period.
        Sets up WebSocket URL and initializes an empty DataFrame to store the candlestick data.
        """
        self.socketUrl = "wss://data.tradingview.com/socket.io/websocket"
        self.symbol = symbol
        self.time_frame = time_frame
        self.period = period
        self.df = pd.DataFrame(columns=['TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        self.ws = None

    def on_message(self, ws, message):
        """
        Callback for processing incoming WebSocket messages.
        Parses candlestick data from JSON and appends it to the DataFrame.
        Displays the DataFrame in a Jupyter environment.
        """
        try:
            start = message.find('"s":[')
            ends = message.find(',"ns":{')
            fdata = json.loads(message[start+4:ends])

            if isinstance(fdata, list):
                for item in fdata:
                    if 'v' in item:
                        timestamp_utc = datetime.utcfromtimestamp(item['v'][0])
                        timestamp_ist = timestamp_utc.replace(tzinfo=pytz.utc).astimezone(ist)
                        item['v'][0] = timestamp_ist.strftime('%Y-%m-%d %H:%M:%S')
                        self.df.loc[len(self.df)] = item['v']
                    else:
                        error_logs.append(f"Warning: Item does not have 'v' key: {item}")
            else:
                error_logs.append(f"Error: fdata is not a list. Type: {type(fdata)}, Value: {fdata}")

        except Exception as e:
            error_logs.append(f"Error extracting candle data: {e}")

        clear_output(wait=True)
        for error in error_logs:
            print(error)
        display(self.df)

    def on_error(self, ws, error):
        """
        Callback for handling WebSocket errors.
        """
        print(f"WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """
        Callback when the WebSocket connection is closed.
        """
        print("WebSocket Closed")

    def on_open(self, ws):
        """
        Callback when the WebSocket connection is opened.
        Sends initialization messages to set up chart session and request data.
        """
        print("WebSocket Connection Established!")

        def create_message(func, arg):
            ms = json.dumps({"m": func, "p": arg})
            msg = f"~m~{len(ms)}~m~{ms}"
            ws.send(msg)

        session_id = "0.13918.2153_mum1-charts-26-webchart-16"  # Hardcoded session ID
        create_message("chart_create_session", [session_id, ""])
        chart_id = '=' + json.dumps({"adjustment": "splits", "session": "regular", "symbol": self.symbol})
        create_message("resolve_symbol", [session_id, "sds_sym_1", chart_id])
        create_message("create_series", [session_id, "sds_1", "s1", "sds_sym_1", self.time_frame, self.period, ""])

    def start(self):
        """
        Starts the WebSocket client and begins receiving real-time data.
        """
        self.ws = websocket.WebSocketApp(self.socketUrl,
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close)
        self.ws.on_open = self.on_open
        self.ws.run_forever()

def get_live_data(symbol="NSE:NIFTY", time_frame="5", period=100):
    """
    Function to fetch live market data for a given symbol and timeframe.
    Initializes the DataCollector and starts the WebSocket connection.
    Returns the DataFrame containing candlestick data.
    """
    collector = DataCollector(symbol, time_frame, period)
    collector.start()
    return collector.df
