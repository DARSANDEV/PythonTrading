from logging import exception
import json
from IPython.display import display,clear_output 
from websocket import create_connection
import pandas as pd
from datetime import datetime
import pytz

# Define  timezone
ist = pytz.timezone('Asia/Kolkata')
#symbols = ['NSE:NIFTY','NSE:BANKNIFTY','NASDAQ:COIN','BINANCE:BTCUSD']
socketUrl="wss://data.tradingview.com/socket.io/websocket"
selected_symbol='BINANCE:BTCUSD'
time_frame="5"
period =5
ws=create_connection(socketUrl)


#create and send message
def create_message(ws,func,arg):
    ms=json.dumps({"m":func,"p":arg})
    msg="~m~"+str(len(ms))+"~m~"+ms
    ws.send(msg)

create_message(ws=ws,func="chart_create_session",arg=["cs_DPIuw9YV0JKm",""])
chart_id='='+json.dumps({"adjustment":"splits","session":"regular","symbol": selected_symbol}) # Use the variable here
print(chart_id)
create_message(ws=ws,func="resolve_symbol",arg=["cs_DPIuw9YV0JKm","sds_sym_1",chart_id])
#create_message(ws=ws,func="resolve_symbol",arg=["cs_DPIuw9YV0JKm","sds_sym_1","={\"adjustment\":\"splits\",\"session\":\"regular\",\"symbol\":\"NSE:NIFTY\"}"])
create_message(ws=ws,func="create_series",arg=["cs_DPIuw9YV0JKm","sds_1","s1","sds_sym_1",time_frame,period,""])

data = []
df = pd.DataFrame(data,columns=['TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
# Store error messages
error_logs = []

def extract_candle(res):
    global df
    try:
        start = res.find('"s":[')
        ends = res.find(',"ns":{')
        fdata = json.loads(res[start+4:ends])
        
        if isinstance(fdata, list):  
            for item in fdata:
                if 'v' in item:
                    # Convert timestamp to IST
                    timestamp_utc = datetime.utcfromtimestamp(item['v'][0])  # Assuming first value is timestamp
                    timestamp_ist = timestamp_utc.replace(tzinfo=pytz.utc).astimezone(ist)
                    
                    # Replace the original timestamp with the IST one
                    item['v'][0] = timestamp_ist.strftime('%Y-%m-%d %H:%M:%S')  # Format as string
                    
                    df.loc[len(df)] = item['v']
                else:
                    error_logs.append(f"Warning: Item does not have 'v' key: {item}")
        else:
            error_logs.append(f"Error: fdata is not a list. Type: {type(fdata)}, Value: {fdata}")

    except Exception as e:
        error_logs.append(f"Error extracting candle data: {e}")

    


# WebSocket message receiving loop
while True:
    try:
        res = ws.recv()
        if res:
            extract_candle(res)
        # Clear only the DataFrame output but keep error messages
        clear_output(wait=True)

        for error in error_logs:
          print(error)

        # Display the updated DataFrame
        display(df)  
    except Exception as e:
        print(f"Error receiving message: {e}")
        break  # Exit loop on error

