import sys
import os
import asyncio
import json
import threading
import datetime
import time
import pdb
import math
from collections import deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from option import BlackScholes, calculate_implied_volatility

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Try importing growwapi
try:
    from growwapi import GrowwAPI, GrowwFeed
    from growwapi.groww.constants import FeedConstants
    from growwapi.groww.proto.proto_parser import get_data_dict
except ImportError:
    GrowwAPI = None
    GrowwFeed = None
    FeedConstants = None
    get_data_dict = None

app = FastAPI(title="Nifty Option Pricing Real-Time Dashboard")

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# Connected WebSocket clients
connected_clients = set()

# Thread-safe state & lock
state_lock = threading.Lock()
state_changed = False

state = {
    "spot_price": 0.0,
    "spot_token": None,
    
    "call_ltp": 0.0,
    "call_token": None,
    "call_iv": 12.0,
    "call_ref_iv": 12.0,
    "call_theo": 0.0,
    "call_delta": 0.0,
    "call_gamma": 0.0,
    "call_vega": 0.0,
    "call_theta": 0.0,
    "call_rho": 0.0,
    "call_zscore": 0.0,
    
    "put_ltp": 0.0,
    "put_token": None,
    "put_iv": 12.0,
    "put_ref_iv": 12.0,
    "put_theo": 0.0,
    "put_delta": 0.0,
    "put_gamma": 0.0,
    "put_vega": 0.0,
    "put_theta": 0.0,
    "put_rho": 0.0,
    "put_zscore": 0.0,
    
    "atm_strike": 0.0,
    "T": 0.0,
    "r": 0.07,
    "expiry_date": "",
    "days_remaining": 0.0,
    "last_update": "",
    
    "spot_time": "-",
    "call_time": "-",
    "put_time": "-",
    
    "timeframes": {
        "10s": {"spot": 0.0, "call_ltp": 0.0, "call_theo": 0.0, "call_zscore": 0.0, "put_ltp": 0.0, "put_theo": 0.0, "put_zscore": 0.0},
        "30s": {"spot": 0.0, "call_ltp": 0.0, "call_theo": 0.0, "call_zscore": 0.0, "put_ltp": 0.0, "put_theo": 0.0, "put_zscore": 0.0},
        "1m": {"spot": 0.0, "call_ltp": 0.0, "call_theo": 0.0, "call_zscore": 0.0, "put_ltp": 0.0, "put_theo": 0.0, "put_zscore": 0.0},
        "5m": {"spot": 0.0, "call_ltp": 0.0, "call_theo": 0.0, "call_zscore": 0.0, "put_ltp": 0.0, "put_theo": 0.0, "put_zscore": 0.0},
    }
}

# Add fallback exchange token for Nifty 50 Index (usually 99926000 or 256)
DEFAULT_NIFTY_TOKEN = "NIFTY"
global_feed = None

def get_atm_strike(spot_price, strikes):
    return min(strikes, key=lambda x: abs(x - spot_price))

def calculate_days_to_expiry(expiry_date_str):
    expiry_date = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    delta = expiry_date - today
    return max(delta.days, 0.5)

call_deviations = deque(maxlen=150)
put_deviations = deque(maxlen=150)

# Timeframe specific deviation change deques for Z-score calculation in movement matrix
timeframe_call_deques = {
    "10s": deque(maxlen=150),
    "30s": deque(maxlen=150),
    "1m": deque(maxlen=150),
    "5m": deque(maxlen=150),
}
timeframe_put_deques = {
    "10s": deque(maxlen=150),
    "30s": deque(maxlen=150),
    "1m": deque(maxlen=150),
    "5m": deque(maxlen=150),
}

def recalculate_greeks_and_prices():
    """Valuate options using the current live state."""
    global state_changed
    
    if state["spot_price"] <= 0 or state["atm_strike"] <= 0 or state["T"] <= 0:
        return

    # Calculate live Implied Volatilities based on current LTP
    if state["call_ltp"] > 0:
        state["call_iv"] = calculate_implied_volatility(
            state["call_ltp"], 
            state["spot_price"], 
            state["atm_strike"], 
            state["T"], 
            state["r"], 
            option_type="call"
        )
    if state["put_ltp"] > 0:
        state["put_iv"] = calculate_implied_volatility(
            state["put_ltp"], 
            state["spot_price"], 
            state["atm_strike"], 
            state["T"], 
            state["r"], 
            option_type="put"
        )

    # Use the stable reference IV for BSM valuation to measure lagging/leading deviations
    ref_call_iv = state.get("call_ref_iv") or state["call_iv"] or 12.0
    ref_put_iv = state.get("put_ref_iv") or state["put_iv"] or 12.0

    # Call Valuation & Greeks (using reference IV)
    bs_call = BlackScholes(state["spot_price"], state["atm_strike"], state["T"], state["r"], ref_call_iv / 100.0)
    state["call_theo"] = bs_call.call_price()
    state["call_delta"] = bs_call.call_delta()
    state["call_gamma"] = bs_call.gamma()
    state["call_vega"] = bs_call.vega()
    state["call_theta"] = bs_call.call_theta()
    state["call_rho"] = bs_call.call_rho()

    # Put Valuation & Greeks (using reference IV)
    bs_put = BlackScholes(state["spot_price"], state["atm_strike"], state["T"], state["r"], ref_put_iv / 100.0)
    state["put_theo"] = bs_put.put_price()
    state["put_delta"] = bs_put.put_delta()
    state["put_gamma"] = bs_put.gamma()
    state["put_vega"] = bs_put.vega()
    state["put_theta"] = bs_put.put_theta()
    state["put_rho"] = bs_put.put_rho()

    # Calculate current deviations
    call_dev = state["call_ltp"] - state["call_theo"]
    put_dev = state["put_ltp"] - state["put_theo"]

    # Append to rolling history
    call_deviations.append(call_dev)
    put_deviations.append(put_dev)

    # Compute Z-score for Call
    if len(call_deviations) > 15:
        call_mean = sum(call_deviations) / len(call_deviations)
        call_var = sum((x - call_mean) ** 2 for x in call_deviations) / len(call_deviations)
        call_std = math.sqrt(call_var)
        if call_std > 1e-4:
            state["call_zscore"] = (call_dev - call_mean) / call_std
        else:
            state["call_zscore"] = 0.0
    else:
        state["call_zscore"] = 0.0

    # Compute Z-score for Put
    if len(put_deviations) > 15:
        put_mean = sum(put_deviations) / len(put_deviations)
        put_var = sum((x - put_mean) ** 2 for x in put_deviations) / len(put_deviations)
        put_std = math.sqrt(put_var)
        if put_std > 1e-4:
            state["put_zscore"] = (put_dev - put_mean) / put_std
        else:
            state["put_zscore"] = 0.0
    else:
        state["put_zscore"] = 0.0

    state["last_update"] = datetime.datetime.now().strftime("%H:%M:%S")
    state_changed = True

def handle_tick(tick_data):
    """WebSocket tick callback."""
    global state_changed, global_feed
    if global_feed is None:
        return

    # tick_data is the metadata of the updated feed topic
    # e.g., {'exchange': 'NSE', 'segment': 'FNO', 'feed_key': '57047', 'feed_type': 'ltp'}
    token = tick_data.get("feed_key")
    feed_type = tick_data.get("feed_type")
    segment = tick_data.get("segment")
    exchange = tick_data.get("exchange")

    if not token or not feed_type:
        return

    # Construct topic to look up the feed object
    if feed_type == FeedConstants.LIVE_DATA:
        topic = FeedConstants.get_live_price_topic(segment, exchange, token).get_topic()
    elif feed_type == FeedConstants.LIVE_INDEX:
        topic = FeedConstants.get_live_index_topic(segment, exchange, token).get_topic()
    else:
        return

    feed_obj = global_feed._feed_station.get_feed(topic)
    if not feed_obj:
        return

    raw_data = feed_obj.get_data()
    if raw_data is None:
        return

    parsed_data = get_data_dict(raw_data, feed_type)
    if not parsed_data:
        return

    # Now get the price from parsed_data
    if feed_type == FeedConstants.LIVE_INDEX:
        ltp = float(parsed_data.get("value") or 0.0)
    else:
        ltp = float(parsed_data.get("ltp") or 0.0)

    if ltp <= 0:
        return

    # Parse timestamp from tick or use system time
    tick_time = parsed_data.get("tsInMillis") or tick_data.get("timestamp") or tick_data.get("time") or tick_data.get("tick_time")
    formatted_time = ""
    if tick_time:
        try:
            if isinstance(tick_time, (int, float)):
                if tick_time > 1e11:
                    tick_time /= 1000.0
                formatted_time = datetime.datetime.fromtimestamp(tick_time).strftime("%H:%M:%S")
            else:
                formatted_time = str(tick_time)
        except Exception:
            formatted_time = datetime.datetime.now().strftime("%H:%M:%S")
    else:
        formatted_time = datetime.datetime.now().strftime("%H:%M:%S")

    with state_lock:
        updated = False
        token_str = str(token)
        instrument_type = "Unknown"

        state_spot_token_str = str(state["spot_token"]) if state["spot_token"] is not None else ""
        state_call_token_str = str(state["call_token"]) if state["call_token"] is not None else ""
        state_put_token_str = str(state["put_token"]) if state["put_token"] is not None else ""

        if token_str == state_spot_token_str:
            state["spot_price"] = ltp
            state["spot_time"] = formatted_time
            updated = True
            instrument_type = "Spot"
        elif token_str == state_call_token_str:
            state["call_ltp"] = ltp
            state["call_time"] = formatted_time
            updated = True
            instrument_type = "Call"
            iv = parsed_data.get("iv") or parsed_data.get("impliedVolatility")
            if iv:
                state["call_iv"] = float(iv)
        elif token_str == state_put_token_str:
            state["put_ltp"] = ltp
            state["put_time"] = formatted_time
            updated = True
            instrument_type = "Put"
            iv = parsed_data.get("iv") or parsed_data.get("impliedVolatility")
            if iv:
                state["put_iv"] = float(iv)

        if updated:
            print(f"[{formatted_time}] WS Tick Received -> {instrument_type} (Token: {token_str}) LTP: {ltp:.2f}")
            recalculate_greeks_and_prices()

# Rolling history buffer (max 5 minutes, i.e., 300 samples at 1Hz)
history_buffer = deque(maxlen=300)

def find_past_snapshot(target_time):
    if not history_buffer:
        return None
    closest = min(history_buffer, key=lambda x: abs(x["timestamp"] - target_time))
    if abs(closest["timestamp"] - target_time) < 3.0:
        return closest
    return None

async def history_sampler_loop():
    global state_changed
    while True:
        try:
            with state_lock:
                if state["spot_price"] > 0:
                    snapshot = {
                        "timestamp": time.time(),
                        "spot": state["spot_price"],
                        "call_ltp": state["call_ltp"],
                        "call_theo": state["call_theo"],
                        "put_ltp": state["put_ltp"],
                        "put_theo": state["put_theo"],
                    }
                    history_buffer.append(snapshot)
                    
                    windows = {
                        "10s": 10,
                        "30s": 30,
                        "1m": 60,
                        "5m": 300
                    }
                    
                    now = time.time()
                    for label, seconds in windows.items():
                        past = find_past_snapshot(now - seconds)
                        if past:
                            call_ltp_move = state["call_ltp"] - past["call_ltp"]
                            call_theo_move = state["call_theo"] - past["call_theo"]
                            put_ltp_move = state["put_ltp"] - past["put_ltp"]
                            put_theo_move = state["put_theo"] - past["put_theo"]
                            
                            call_dev = call_ltp_move - call_theo_move
                            put_dev = put_ltp_move - put_theo_move
                            
                            timeframe_call_deques[label].append(call_dev)
                            timeframe_put_deques[label].append(put_dev)
                            
                            call_z = 0.0
                            qc = timeframe_call_deques[label]
                            if len(qc) > 15:
                                mean_c = sum(qc) / len(qc)
                                var_c = sum((x - mean_c) ** 2 for x in qc) / len(qc)
                                std_c = math.sqrt(var_c)
                                if std_c > 1e-4:
                                    call_z = (call_dev - mean_c) / std_c
                                    
                            put_z = 0.0
                            qp = timeframe_put_deques[label]
                            if len(qp) > 15:
                                mean_p = sum(qp) / len(qp)
                                var_p = sum((x - mean_p) ** 2 for x in qp) / len(qp)
                                std_p = math.sqrt(var_p)
                                if std_p > 1e-4:
                                    put_z = (put_dev - mean_p) / std_p

                            state["timeframes"][label] = {
                                "spot": state["spot_price"] - past["spot"],
                                "call_ltp": call_ltp_move,
                                "call_theo": call_theo_move,
                                "call_zscore": call_z,
                                "put_ltp": put_ltp_move,
                                "put_theo": put_theo_move,
                                "put_zscore": put_z,
                            }
                        else:
                            timeframe_call_deques[label].append(0.0)
                            timeframe_put_deques[label].append(0.0)
                            state["timeframes"][label] = {
                                "spot": 0.0,
                                "call_ltp": 0.0,
                                "call_theo": 0.0,
                                "call_zscore": 0.0,
                                "put_ltp": 0.0,
                                "put_theo": 0.0,
                                "put_zscore": 0.0,
                            }
                    state_changed = True
        except Exception as e:
            print(f"Error in history sampler: {e}")
        await asyncio.sleep(1.0)

# Background broadcast loop
async def broadcast_loop():
    global state_changed
    while True:
        try:
            if state_changed:
                with state_lock:
                    state_changed = False
                    payload = json.dumps(state)
                # Broadcast payload to all open WebSockets
                if connected_clients:
                    await asyncio.gather(
                        *[client.send_text(payload) for client in connected_clients],
                        return_exceptions=True
                    )
        except Exception as e:
            print(f"Error in broadcast loop: {e}")
        await asyncio.sleep(0.05)  # Check every 50ms for low latency

# Start Web Socket server stream thread
def start_groww_feed(api_token, expiry_date):
    """REST initialization and WebSocket connection in a separate thread."""
    try:
        groww = GrowwAPI(api_token)
        
        # Get Option Chain to set up initial state
        print("Fetching initial option chain...")
        option_chain = groww.get_option_chain(exchange="NSE", underlying="NIFTY", expiry_date=expiry_date)
        if not option_chain:
            print("[Error] Empty option chain response.")
            return
        print(option_chain)
        # Get spot price and token
        underlying = option_chain.get("underlying", {})
        spot_price = float(option_chain.get("underlying_ltp") or underlying.get("spot_price") or underlying.get("lastPrice") or option_chain.get("spot_price") or 0.0)
        spot_token = underlying.get("exchange_token") or underlying.get("instrument_token") or underlying.get("token") or DEFAULT_NIFTY_TOKEN

        strikes_dict = option_chain.get("strikes") or {}
        
        if strikes_dict:
            # Handle new dictionary format (e.g. {"23450": {"CE": ..., "PE": ...}})
            strikes = [float(k) for k in strikes_dict.keys()]
            if not strikes:
                print("[Error] No strike prices found in option chain.")
                return
            atm_strike = get_atm_strike(spot_price, strikes)
            atm_data = strikes_dict.get(str(int(atm_strike))) or strikes_dict.get(str(atm_strike)) or strikes_dict.get(atm_strike) or {}
            ce_data = atm_data.get("CE") or atm_data.get("ce") or {}
            pe_data = atm_data.get("PE") or atm_data.get("pe") or {}
        else:
            # Fallback to list format
            contracts = option_chain.get("contracts") or option_chain.get("data") or []
            if not contracts:
                print("[Error] No options contracts found in option chain.")
                return

            strikes = []
            contract_by_strike = {}
            for contract in contracts:
                strike = float(contract.get("strike_price") or contract.get("strikePrice") or 0.0)
                if strike > 0:
                    strikes.append(strike)
                    contract_by_strike[strike] = contract

            atm_strike = get_atm_strike(spot_price, strikes)
            atm_contract = contract_by_strike[atm_strike]
            ce_data = atm_contract.get("ce") or atm_contract.get("CE") or {}
            pe_data = atm_contract.get("pe") or atm_contract.get("PE") or {}
        # Load instruments to resolve tokens if they are not in the option chain response
        instruments_df = None
        try:
            instruments_df = groww._load_instruments()
        except Exception as ex:
            print(f"[Warning] Could not load instruments dataframe: {ex}")

        def resolve_token(contract_data):
            token = contract_data.get("exchange_token") or contract_data.get("instrument_token") or contract_data.get("token")
            if not token and contract_data.get("trading_symbol") and instruments_df is not None:
                match = instruments_df[instruments_df["trading_symbol"] == contract_data["trading_symbol"]]
                if not match.empty:
                    token = match.iloc[0]["exchange_token"]
            return str(token) if token else "None"

        days = calculate_days_to_expiry(expiry_date)

        with state_lock:
            state["spot_price"] = spot_price
            state["spot_token"] = str(spot_token)
            state["atm_strike"] = atm_strike
            state["T"] = days / 365.0
            state["expiry_date"] = expiry_date
            state["days_remaining"] = days
            
            init_time = datetime.datetime.now().strftime("%H:%M:%S")
            state["spot_time"] = init_time
            state["call_time"] = init_time
            state["put_time"] = init_time

            if ce_data:
                state["call_ltp"] = float(ce_data.get("ltp") or ce_data.get("lastPrice") or 0.0)
                state["call_iv"] = float(ce_data.get("iv") or ce_data.get("impliedVolatility") or 12.0)
                state["call_ref_iv"] = state["call_iv"]
                state["call_token"] = resolve_token(ce_data)
                
            if pe_data:
                state["put_ltp"] = float(pe_data.get("pe") or pe_data.get("lastPrice") or pe_data.get("ltp") or 0.0)
                state["put_iv"] = float(pe_data.get("iv") or pe_data.get("impliedVolatility") or 12.0)
                state["put_ref_iv"] = state["put_iv"]
                state["put_token"] = resolve_token(pe_data)

            recalculate_greeks_and_prices()

        print("Connecting Groww WebSocket Feed...")
        global global_feed
        try:
            global_feed = GrowwFeed(groww)
        except Exception:
            global_feed = GrowwFeed(api_token)
        feed = global_feed

        index_instruments = []
        option_instruments = []
        print(state)
        if state["spot_token"] and state["spot_token"] != "None":
            index_instruments.append({"exchange": "NSE", "segment": "CASH", "exchange_token": state["spot_token"]})
        if state["call_token"] and state["call_token"] != "None":
            option_instruments.append({"exchange": "NSE", "segment": "FNO", "exchange_token": state["call_token"]})
        if state["put_token"] and state["put_token"] != "None":
            option_instruments.append({"exchange": "NSE", "segment": "FNO", "exchange_token": state["put_token"]})
            
        if index_instruments:
            feed.subscribe_index_value(index_instruments, on_data_received=handle_tick)
        if option_instruments:
            feed.subscribe_ltp(option_instruments, on_data_received=handle_tick)
        feed.consume()

    except Exception as e:
        print(f"[Error in Groww Feed Thread]: {e}")

@app.on_event("startup")
async def startup_event():
    # Start background loop tasks
    asyncio.create_task(broadcast_loop())
    asyncio.create_task(history_sampler_loop())
    
    # Extract credentials and parameters
    api_token = os.environ.get("GROWW_API_TOKEN")
    if not api_token:
        print("[Warning] GROWW_API_TOKEN not found in .env. Live updates will not start automatically.")
        return
        
    # Standard Nifty Expiry
    # For testing, we can grab a default expiry date. You can also specify it in .env
    expiry_date = os.environ.get("NIFTY_EXPIRY_DATE")
    if not expiry_date:
        # Fallback to nearest Thursday (you can customize this)
        today = datetime.date.today()
        days_ahead = (3 - today.weekday()) % 7
        next_thursday = today + datetime.timedelta(days=days_ahead)
        expiry_date = next_thursday.strftime("%Y-%m-%d")
        print(f"[Info] NIFTY_EXPIRY_DATE not found. Fallback nearest Thursday: {expiry_date}")

    # Launch Groww WebSocket client in a background thread
    feed_thread = threading.Thread(
        target=start_groww_feed, 
        args=(api_token, expiry_date), 
        daemon=True
    )
    feed_thread.start()

@app.get("/")
async def get_index():
    index_path = os.path.join(TEMPLATE_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h3>Error: templates/index.html not found!</h3>")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        # Send current state immediately on connection
        with state_lock:
            initial_payload = json.dumps(state)
        await websocket.send_text(initial_payload)
        
        # Keep connection open
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    # Read port from environment or default to 8000
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting server on http://localhost:{port}...")
    uvicorn.run("web_server:app", host="0.0.0.0", port=port, reload=True)
