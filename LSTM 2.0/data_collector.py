import json
import pandas as pd
from datetime import datetime
import pytz
import websocket
import time
from IPython.display import clear_output, display

# Set IST timezone
ist = pytz.timezone('Asia/Kolkata')

# List to store any error messages
error_logs = []

class DataCollector:
    def __init__(self, symbol="NSE:NIFTY", time_frame="5", period=100, reconnect_delay=2):
        """
        Initializes the DataCollector with the desired symbol, time frame, and period.
        """
        self.socketUrl = "wss://data.tradingview.com/socket.io/websocket"
        self.symbol = symbol
        self.time_frame = time_frame
        self.period = period
        self.reconnect_delay = reconnect_delay
        self.df = pd.DataFrame(columns=['TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        self.ws = None
        self.session_id = "0.13918.2153_mum1-charts-26-webchart-16"  # Hardcoded session ID
        self.include_live_data = True
        self.include_historic_data = True

    def on_message(self, ws, message):
        """
        Callback for processing incoming WebSocket messages.
        Extracts candle data if the message contains du or timescale_update.
        Closes connection after initial history if fetch_live_data=False.
        """
        if ('"m":"du"' not in message) and ('"m":"timescale_update"' not in message):
            return
        if ('"m":"timescale_update"'  in message ):
            if not self.include_historic_data:
                print("Skipping historic data")
                return
        

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
                        # Avoid duplicates: skip if timestamp already exists
                        if not self.df['TimeStamp'].eq(item['v'][0]).any():
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

        if not self.include_live_data and '"m":"timescale_update"' in message:
            print("Historical data loaded. Closing connection...")
            ws.close()

    def on_error(self, ws, error):
        """
        Callback for handling WebSocket errors.
        """
        print(f"WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """
        Callback when the WebSocket connection is closed.
        Auto-reconnect if status code is 1000 (normal closure).
        """
        print(f" WebSocket Closed => Status code: {close_status_code}, message: {close_msg}")
        print("Errors:", error_logs)

        if close_status_code == 1000:
            print(f"Reconnecting in {self.reconnect_delay} seconds...")
            time.sleep(self.reconnect_delay)
            self.start()
        else:
            print("Connection closed unexpectedly. Manual restart may be required.")

    def on_open(self, ws):
        """
        Callback when the WebSocket connection is opened.
        Sends initialization messages to set up chart session and request data.
        """
        print(" WebSocket Connection Established!")

        def create_message(func, arg):
            ms = json.dumps({"m": func, "p": arg})
            msg = f"~m~{len(ms)}~m~{ms}"
            ws.send(msg)

        session_id = self.session_id
        chart_id = '=' + json.dumps({"adjustment": "splits", "session": "regular", "symbol": self.symbol})

        create_message("chart_create_session", [session_id, ""])
        create_message("resolve_symbol", [session_id, "sds_sym_1", chart_id])
        create_message("create_series", [session_id, "sds_1", "s1", "sds_sym_1", self.time_frame, self.period, ""])

    def start(self):
        """
        Starts the WebSocket client and begins receiving real-time data.
        """
        self.ws = websocket.WebSocketApp(
            self.socketUrl,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.on_open = self.on_open
        self.ws.run_forever(ping_interval=30, ping_timeout=10)  # keep-alive pings

def get_live_data(symbol="NSE:NIFTY", time_frame="5", period=100, include_historic_data=True):
    """
    Function to fetch live market data for a given symbol and timeframe.
    Initializes the DataCollector and starts the WebSocket connection.
    Returns the DataFrame containing candlestick data.
    """
    collector = DataCollector(symbol, time_frame, period)
    collector.include_historic_data= include_historic_data
    collector.include_live_data = True
    collector.start()
    return collector.df

def get_historic_data(symbol="NSE:NIFTY", time_frame="5", period=100):
    """
    Function to fetch historic market data for a given symbol and timeframe.
    Initializes the DataCollector and starts the WebSocket connection.
    Returns the DataFrame containing candlestick data.
    """
    collector = DataCollector(symbol, time_frame, period)
    collector.include_live_data = False
    collector.include_historic_data = True
    collector.start()
    return collector.df
