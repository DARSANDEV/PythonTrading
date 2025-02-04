from logging import exception
import json
import pandas as pd
from websocket import create_connection


#symbols = ['NSE:NIFTY','NSE:BANKNIFTY','NASDAQ:COIN','BINANCE:BTCUSD']
socketUrl="wss://data.tradingview.com/socket.io/websocket"
selected_symbol='NSE:NIFTY'
time_frame="1"
period =100
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
#display as a table
def extract_candle(res):
    try:
      start = res.find('"s":[')
      ends = res.find(',"ns":{')
      fdata = json.loads(res[start+4:ends])

      for item in fdata:
        data.append(item['v'])
      #print(fdata)
      df=pd.DataFrame(data)
      print(df)
    except Exception as e:
      print(f"Error extracting candle data: {e}")



#receive message
while True:

    try:
        res = ws.recv()
        # if "series_loading" in res:
        extract_candle(res)

        #print(res)
        print("/n")
        # if "series_completed" in res:
        #     break
    except Exception as e:
        print(f"Error receiving message: {e}")
        # Handle the error, e.g., break the loop or reconnect
        break  # Example: break the loop if there's an error

