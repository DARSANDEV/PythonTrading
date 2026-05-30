import os
import csv
import json
import asyncio
import datetime
import websockets

# Configurations
WS_URI = "ws://localhost:8000/ws"
CSV_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CSV_FILE = os.path.join(CSV_DIR, "nifty_ticks_backtest.csv")

# Create directories if they do not exist
os.makedirs(CSV_DIR, exist_ok=True)

# CSV Header definitions
HEADERS = [
    "Timestamp", 
    "Spot_Time", 
    "Spot_Price",
    "Call_LTP", 
    "Call_Theo", 
    "Call_IV",
    "Put_LTP", 
    "Put_Theo", 
    "Put_IV"
]

TIMEFRAMES = ["10s", "30s", "1m", "5m"]
for tf in TIMEFRAMES:
    HEADERS.extend([
        f"{tf}_Nifty_Move",
        f"{tf}_Call_Mkt_Move",
        f"{tf}_Call_BSM_Move",
        f"{tf}_Call_Dev_Move",
        f"{tf}_Call_ZScore",
        f"{tf}_Put_Mkt_Move",
        f"{tf}_Put_BSM_Move",
        f"{tf}_Put_Dev_Move",
        f"{tf}_Put_ZScore"
    ])

def initialize_csv():
    """Write headers if the CSV file is newly created."""
    file_exists = os.path.isfile(CSV_FILE)
    if not file_exists:
        with open(CSV_FILE, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)
        print(f"[Logger] Created new CSV file with headers at: {CSV_FILE}")
    else:
        print(f"[Logger] Appending to existing CSV file at: {CSV_FILE}")

def parse_and_log_row(data):
    """Extract tick details and timeframe matrix values, then append to CSV."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # Core tick details
    row = [
        now_str,
        data.get("spot_time", "-"),
        data.get("spot_price", 0.0),
        data.get("call_ltp", 0.0),
        data.get("call_theo", 0.0),
        data.get("call_iv", 0.0),
        data.get("put_ltp", 0.0),
        data.get("put_theo", 0.0),
        data.get("put_iv", 0.0)
    ]
    
    # Timeframe movement matrix details
    tf_data = data.get("timeframes", {})
    for tf in TIMEFRAMES:
        vals = tf_data.get(tf, {})
        
        # Moves
        spot_move = vals.get("spot", 0.0)
        call_mkt_move = vals.get("call_ltp", 0.0)
        call_bsm_move = vals.get("call_theo", 0.0)
        call_dev_move = call_mkt_move - call_bsm_move
        call_z = vals.get("call_zscore", 0.0)
        
        put_mkt_move = vals.get("put_ltp", 0.0)
        put_bsm_move = vals.get("put_theo", 0.0)
        put_dev_move = put_mkt_move - put_bsm_move
        put_z = vals.get("put_zscore", 0.0)
        
        row.extend([
            spot_move,
            call_mkt_move,
            call_bsm_move,
            call_dev_move,
            call_z,
            put_mkt_move,
            put_bsm_move,
            put_dev_move,
            put_z
        ])
        
    # Append to CSV
    with open(CSV_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(row)
        
    return now_str, data.get("spot_price"), call_z, put_z

async def start_logger():
    initialize_csv()
    
    while True:
        print(f"[Logger] Connecting to WebSocket at {WS_URI}...")
        try:
            async with websockets.connect(WS_URI) as websocket:
                print("[Logger] Connected! Logging live tick data and matrix variables...")
                row_count = 0
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)
                    
                    # Only write rows if we have a valid spot price
                    if data.get("spot_price", 0.0) > 0:
                        log_time, spot, call_z, put_z = parse_and_log_row(data)
                        row_count += 1
                        
                        # Console log summary every tick to keep visibility
                        print(f"[{log_time}] Row #{row_count} logged | Spot: {spot:.2f} | 10s Call Z: {call_z:+.2f} | 10s Put Z: {put_z:+.2f}")
                        
        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError):
            print("[Logger] Connection lost or refused. Retrying in 5 seconds...")
            await asyncio.sleep(5.0)
        except Exception as e:
            print(f"[Logger] Unexpected error: {e}")
            await asyncio.sleep(5.0)

if __name__ == "__main__":
    try:
        asyncio.run(start_logger())
    except KeyboardInterrupt:
        print("\n[Logger] Stopped logging ticks.")
