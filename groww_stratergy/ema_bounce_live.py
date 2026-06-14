import os
import sys
import time
import json
import csv
import datetime
import threading
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Ensure groww_Startergy and root are in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from option import BlackScholes
    from growwapi import GrowwAPI, GrowwFeed
    from growwapi.groww.constants import FeedConstants
    from growwapi.groww.proto.proto_parser import get_data_dict
except ImportError as e:
    print(f"[Error] Required packages or local modules not found: {e}")
    sys.exit(1)

# Configurations
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

GROWW_API_TOKEN = os.environ.get("GROWW_API_TOKEN")
NIFTY_EXPIRY_DATE = os.environ.get("NIFTY_EXPIRY_DATE")
PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() != "false"
LOT_SIZE = int(os.environ.get("LOT_SIZE", "65"))
ADX_THRESHOLD = int(os.environ.get("ADX_THRESHOLD", "15"))
STRATEGY_DIRECTION = os.environ.get("STRATEGY_DIRECTION", "BOTH").upper()

CSV_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TRADE_LOG_FILE = os.path.join(CSV_DIR, "paper_trades_log.csv")

# Create data directory if not exists
os.makedirs(CSV_DIR, exist_ok=True)

# State lock
state_lock = threading.Lock()

# Strategy State variables
strategy_state = {
    "spot_price": 0.0,
    "last_spot_update": 0.0,
    
    # 1-minute bars list: list of dicts with {"timestamp", "open", "high", "low", "close"}
    "bars_1m": [],
    
    # Current active bar data
    "current_bar": None,
    
    # Trade State
    "in_trade": False,
    "trade_type": "CE", # "CE" or "PE"
    "entry_index_price": 0.0,
    "entry_option_price": 0.0,
    "entry_time": None,
    "trading_symbol": "",
    "option_token": "",
    "atr": 0.0,
    "target_price": 0.0,
    "sl_price": 0.0,
    
    # Indicators (latest value)
    "ema_1m": 0.0,
    "ema_5m": 0.0,
    "atr_1m": 0.0,
    "adx_1m": 0.0,

    # Cooldown & same-bar entry restriction
    "last_trade_time": 0.0,
    "last_trade_bar_timestamp": 0,

    # Order Execution Control flags
    "is_processing_order": False,
    "last_exit_attempt_time": 0.0,
}

def init_trade_log():
    """Create paper trade log headers if not exists."""
    if not os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp", "Action", "Symbol", "Quantity", 
                "Index_Price", "Option_Price", "Type", 
                "ATR", "Target_Index", "SL_Index", "Net_Profit_Points"
            ])
        print(f"[Strategy] Initialized trade log at: {TRADE_LOG_FILE}")

def log_trade(action, symbol, qty, index_price, option_price, atr=0.0, target=0.0, sl=0.0, net_profit=0.0):
    """Write trade details to CSV."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_type = "PAPER" if PAPER_TRADING else "LIVE"
    with open(TRADE_LOG_FILE, mode='a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            now_str, action, symbol, qty, 
            index_price, option_price, trade_type, 
            atr, target, sl, net_profit
        ])

def place_strategy_order(trading_symbol, quantity, transaction_type, index_price, option_price, groww_client=None, atr=0.0, target=0.0, sl=0.0, net_profit=0.0):
    """
    Wrapper for order placement. Supports Live FNO orders and Excel/CSV paper trade logging.
    """
    trade_mode = "PAPER" if PAPER_TRADING else "LIVE"
    print(f"\n[Trade Execution] {transaction_type} {quantity} shares of {trading_symbol} ({trade_mode} mode)")
    print(f"  Index Price: {index_price:.2f} | Option Price: {option_price:.2f}")

    if PAPER_TRADING:
        # Log paper trade to CSV
        log_trade(transaction_type, trading_symbol, quantity, index_price, option_price, atr, target, sl, net_profit)
        print(f"  [Paper Trade logged successfully to Excel CSV]")
        return {"status": "SUCCESS", "order_id": "PAPER_" + str(int(time.time()))}
    else:
        # Live FNO Trade via Groww API
        if groww_client is None:
            print("  [Error] Live Groww Client not provided to place_strategy_order!")
            return {"status": "FAILED", "error": "No Groww Client"}
            
        try:
            order_res = groww_client.place_order(
                validity="DAY",
                exchange="NSE",
                order_type="MARKET",
                product="NRML",
                quantity=quantity,
                segment="FNO",
                trading_symbol=trading_symbol,
                transaction_type=transaction_type
            )
            print(f"  [Live Trade Response]: {order_res}")
            # Log live trade details for record
            log_trade(transaction_type, trading_symbol, quantity, index_price, option_price, atr, target, sl, net_profit)
            return order_res
        except Exception as e:
            print(f"  [Live Order Error]: {e}")
            return {"status": "FAILED", "error": str(e)}

def execute_entry_order(signal_details, groww_client):
    """
    Background worker to fetch ATM option contract and place order.
    """
    global strategy_state
    
    trade_type = signal_details["trade_type"]
    spot_price = signal_details["spot_price"]
    atr = signal_details["atr"]
    
    print(f"\n[Strategy Alert] {trade_type} BUY SIGNAL DETECTED!")
    print(f"  Spot: {spot_price:.2f} | ATR: {atr:.2f}")
    
    # Fetch option details (network call - outside lock)
    option_data = None
    try:
        if trade_type == "CE":
            option_data = select_atm_call_option(groww_client, spot_price)
        else:
            option_data = select_atm_put_option(groww_client, spot_price)
    except Exception as e:
        print(f"  [Error] Failed to select option: {e}")
        
    if option_data:
        trading_symbol = option_data.get("trading_symbol")
        option_ltp = float(option_data.get("ltp") or option_data.get("lastPrice") or 0.0)
        
        if trade_type == "CE":
            target_idx = spot_price + (0.5 * atr)
            sl_idx = spot_price - (0.5 * atr)
        else:
            target_idx = spot_price - (0.5 * atr)
            sl_idx = spot_price + (0.5 * atr)
            
        # Place order (network call - outside lock)
        order_res = place_strategy_order(
            trading_symbol=trading_symbol,
            quantity=LOT_SIZE,
            transaction_type="BUY",
            index_price=spot_price,
            option_price=option_ltp,
            groww_client=groww_client,
            atr=atr,
            target=target_idx,
            sl=sl_idx
        )
        
        # Check if order placement succeeded
        if order_res and order_res.get("status") == "SUCCESS":
            with state_lock:
                strategy_state["in_trade"] = True
                strategy_state["trade_type"] = trade_type
                strategy_state["entry_index_price"] = spot_price
                strategy_state["entry_option_price"] = option_ltp
                strategy_state["entry_time"] = datetime.datetime.now()
                strategy_state["trading_symbol"] = trading_symbol
                strategy_state["atr"] = atr
                strategy_state["target_price"] = target_idx
                strategy_state["sl_price"] = sl_idx
                strategy_state["is_processing_order"] = False
            print(f"  [Entry Order Executed] Active trade set for {trading_symbol}")
            return
        else:
            print(f"  [Entry Order Failed] Status: {order_res.get('status') if order_res else 'No response'}")
    else:
        print("  [Warning] Could not retrieve Option details from option chain. Trade skipped.")
        
    # If we got here, entry failed or was skipped
    with state_lock:
        strategy_state["is_processing_order"] = False
        # Reset cooldowns so we can try again on next signals
        strategy_state["last_trade_bar_timestamp"] = 0
        strategy_state["last_trade_time"] = 0.0

def execute_exit_order(trade_to_exit, spot_price, groww_client):
    """
    Background worker to fetch option quote, place order, and log P&L.
    """
    global strategy_state
    
    trading_symbol = trade_to_exit["trading_symbol"]
    trade_type = trade_to_exit["trade_type"]
    is_sl = trade_to_exit["is_sl"]
    entry_index_price = trade_to_exit["entry_index_price"]
    entry_option_price = trade_to_exit["entry_option_price"]
    
    alert_type = "STOP LOSS" if is_sl else "TARGET"
    print(f"\n[Strategy Alert] {alert_type} HIT! Index price {spot_price:.2f} (Trade Type: {trade_type})")
    
    # Fetch option LTP at exit to log it accurately (network call - outside lock)
    exit_option_price = entry_option_price  # fallback
    if groww_client:
        try:
            # Fetch latest quote for option
            quote = groww_client.get_quote(trading_symbol=trading_symbol, exchange="NSE", segment="FNO")
            if quote:
                exit_option_price = float(quote.get("ltp") or quote.get("lastPrice") or quote.get("value") or entry_option_price)
        except Exception as e:
            print(f"  [Warning] Could not fetch exit option price quote: {e}. Logging entry option price as fallback.")
                
    # Calculate net profit (option premium points)
    net_option_profit = exit_option_price - entry_option_price
    
    # Place exit order (network call - outside lock)
    order_res = place_strategy_order(
        trading_symbol=trading_symbol,
        quantity=LOT_SIZE,
        transaction_type="SELL",
        index_price=spot_price,
        option_price=exit_option_price,
        groww_client=groww_client,
        net_profit=net_option_profit
    )
    
    if order_res and order_res.get("status") == "SUCCESS":
        with state_lock:
            strategy_state["in_trade"] = False
            strategy_state["is_processing_order"] = False
        print(f"  [Exit Order Executed] Trade closed for {trading_symbol}. Net Option PnL: {net_option_profit:.2f} points.")
    else:
        # Critical error: Exit order failed!
        print(f"\n[CRITICAL ERROR] Exit order for {trading_symbol} FAILED!")
        print("  Please check open positions manually immediately!")
        with state_lock:
            strategy_state["is_processing_order"] = False

def calculate_indicators(bars_list):
    """
    Calculate EMA, ATR, and ADX on the 1-minute historical bars, resample to 5-minute, and align.
    """
    if len(bars_list) < 30:
        return None
        
    df = pd.DataFrame(bars_list)
    
    # 9 EMA of 1m Close
    df['ema_1m'] = df['close'].ewm(span=9, adjust=False).mean()
    
    # 14 ATR
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift()).abs()
    low_cp = (df['low'] - df['close'].shift()).abs()
    df['tr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    df['atr'] = df['tr'].ewm(alpha=1/14, adjust=False).mean()
    
    # 14 ADX (using Wilder's smoothing)
    df['up_move'] = df['high'] - df['high'].shift()
    df['down_move'] = df['low'].shift() - df['low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
    
    smooth_tr = df['tr'].ewm(alpha=1/14, adjust=False).mean()
    smooth_plus_dm = df['plus_dm'].ewm(alpha=1/14, adjust=False).mean()
    smooth_minus_dm = df['minus_dm'].ewm(alpha=1/14, adjust=False).mean()
    
    df['plus_di'] = 100 * smooth_plus_dm / smooth_tr.replace(0, 1e-5)
    df['minus_di'] = 100 * smooth_minus_dm / smooth_tr.replace(0, 1e-5)
    
    df['dx'] = 100 * (df['plus_di'] - df['minus_di']).abs() / (df['plus_di'] + df['minus_di']).replace(0, 1e-5)
    df['adx'] = df['dx'].ewm(alpha=1/14, adjust=False).mean()
    
    # Resample 1m bars to 5m bars
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df_5m = df.resample('5Min', on='datetime').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    df_5m['ema_5m'] = df_5m['close'].ewm(span=9, adjust=False).mean()
    df_5m['start_slot'] = df_5m.index.astype(int) // 10**9
    df_5m['completed_at'] = df_5m['start_slot'] + 300
    
    # Merge completed 5m EMA back onto 1m timeframe (avoids lookahead bias)
    df = pd.merge_asof(
        df.sort_values('timestamp'),
        df_5m[['completed_at', 'ema_5m']].sort_values('completed_at'),
        left_on='timestamp',
        right_on='completed_at',
        direction='backward'
    )
    
    # Drop completed_at column to avoid duplicates next iteration
    df.drop(columns=['completed_at'], inplace=True, errors='ignore')
    
    return df

def bootstrap_historical_bars(groww_client):
    """
    Fetch last 150 1-minute historical candles from Groww API to warm up indicators.
    """
    print("[Strategy] Bootstrapping Nifty 1-minute historical candles...")
    try:
        # Request historical candles for NIFTY from the last 24 hours (covers a trading day)
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(days=2)
        
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Use get_historical_candle_data with fallback
        try:
            res = groww_client.get_historical_candle_data(
                trading_symbol="NIFTY",
                exchange="NSE",
                segment="CASH",
                start_time=start_str,
                end_time=end_str,
                interval_in_minutes=1
            )
        except Exception:
            # Fallback to get_historical_candles if groww_symbol is needed
            res = groww_client.get_historical_candles(
                exchange="NSE",
                segment="CASH",
                groww_symbol="NIFTY",
                start_time=start_str,
                end_time=end_str,
                candle_interval="1minute"
            )
            
        candles = res.get("candles") or []
        if not candles:
            print("[Warning] No historical candles returned. Bootstrapping failed.")
            return False
            
        # Format received candles: [epoch_seconds, open, high, low, close, volume]
        # Sort by timestamp ascending
        candles_sorted = sorted(candles, key=lambda x: x[0])
        
        bars = []
        for c in candles_sorted[-150:]: # keep last 150 bars
            bars.append({
                "timestamp": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4])
            })
            
        with state_lock:
            strategy_state["bars_1m"] = bars
            
        print(f"[Strategy] Successfully loaded {len(bars)} historical bars. Indicators warmed up.")
        return True
    except Exception as e:
        print(f"[Error] Bootstrap failed: {e}")
        return False

def select_atm_call_option(groww_client, spot_price):
    """
    Fetch option chain and return the ATM Call Option contract details.
    """
    try:
        print(f"[Strategy] Identifying ATM Call Option for spot: {spot_price:.2f}...")
        option_chain = groww_client.get_option_chain(exchange="NSE", underlying="NIFTY", expiry_date=NIFTY_EXPIRY_DATE)
        if not option_chain:
            return None
            
        strikes_dict = option_chain.get("strikes") or {}
        if not strikes_dict:
            return None
            
        strikes = sorted([float(k) for k in strikes_dict.keys()])
        atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
        
        atm_data = strikes_dict.get(str(int(atm_strike))) or strikes_dict.get(str(atm_strike)) or {}
        ce_data = atm_data.get("CE") or atm_data.get("ce") or {}
        
        return ce_data
    except Exception as e:
        print(f"[Error] Failed to select call option: {e}")
        return None

def select_atm_put_option(groww_client, spot_price):
    """
    Fetch option chain and return the ATM Put Option contract details.
    """
    try:
        print(f"[Strategy] Identifying ATM Put Option for spot: {spot_price:.2f}...")
        option_chain = groww_client.get_option_chain(exchange="NSE", underlying="NIFTY", expiry_date=NIFTY_EXPIRY_DATE)
        if not option_chain:
            return None
            
        strikes_dict = option_chain.get("strikes") or {}
        if not strikes_dict:
            return None
            
        strikes = sorted([float(k) for k in strikes_dict.keys()])
        atm_strike = min(strikes, key=lambda x: abs(x - spot_price))
        
        atm_data = strikes_dict.get(str(int(atm_strike))) or strikes_dict.get(str(atm_strike)) or {}
        pe_data = atm_data.get("PE") or atm_data.get("pe") or {}
        
        return pe_data
    except Exception as e:
        print(f"[Error] Failed to select put option: {e}")
        return None

def process_tick(spot_price, timestamp_epoch, groww_client):
    """
    Handle live spot price tick, build 1m bar, and evaluate strategy conditions.
    """
    global strategy_state
    
    # 1. Update/Build Bar (needs lock)
    with state_lock:
        strategy_state["spot_price"] = spot_price
        
        # Round timestamp to start of current minute
        bar_timestamp = (timestamp_epoch // 60) * 60
        
        current_bar = strategy_state["current_bar"]
        
        # Check if we transitioned to a new minute
        if current_bar is None:
            # First bar initialization
            strategy_state["current_bar"] = {
                "timestamp": bar_timestamp,
                "open": spot_price,
                "high": spot_price,
                "low": spot_price,
                "close": spot_price
            }
        elif bar_timestamp > current_bar["timestamp"]:
            # Close previous bar and append it
            strategy_state["bars_1m"].append(current_bar)
            # Maintain rolling buffer of 200 bars
            if len(strategy_state["bars_1m"]) > 200:
                strategy_state["bars_1m"].pop(0)
                
            print(f"\n[1m Bar Completed] Time: {datetime.datetime.fromtimestamp(current_bar['timestamp']).strftime('%H:%M:%S')} | "
                  f"O: {current_bar['open']:.2f} | H: {current_bar['high']:.2f} | L: {current_bar['low']:.2f} | C: {current_bar['close']:.2f}")
                  
            # Start new active bar
            strategy_state["current_bar"] = {
                "timestamp": bar_timestamp,
                "open": spot_price,
                "high": spot_price,
                "low": spot_price,
                "close": spot_price
            }
            
            # Recalculate indicators on completed bars
            df_ind = calculate_indicators(strategy_state["bars_1m"])
            if df_ind is not None:
                latest = df_ind.iloc[-1]
                strategy_state["ema_1m"] = float(latest["ema_1m"])
                strategy_state["ema_5m"] = float(latest["ema_5m"]) if "ema_5m" in latest else 0.0
                strategy_state["atr_1m"] = float(latest["atr"])
                strategy_state["adx_1m"] = float(latest["adx"])
                
                print(f"[Indicators] 1m EMA: {strategy_state['ema_1m']:.2f} | 5m EMA: {strategy_state['ema_5m']:.2f} | "
                      f"1m ATR: {strategy_state['atr_1m']:.2f} | 1m ADX: {strategy_state['adx_1m']:.2f}")
        else:
            # Update current active bar
            current_bar["high"] = max(current_bar["high"], spot_price)
            current_bar["low"] = min(current_bar["low"], spot_price)
            current_bar["close"] = spot_price

    # 2. Check if we are currently processing an order
    with state_lock:
        if strategy_state["is_processing_order"]:
            return

    # 3. Evaluate Entry or Exit conditions (needs lock briefly to check signals, then triggers background execution)
    exit_triggered = False
    trade_to_exit = None
    
    entry_triggered = False
    signal_details = None
    
    with state_lock:
        if strategy_state["in_trade"]:
            trade_type = strategy_state["trade_type"]
            hit_target = False
            hit_sl = False
            
            if trade_type == "CE":
                hit_target = spot_price >= strategy_state["target_price"]
                hit_sl = spot_price <= strategy_state["sl_price"]
            else:  # PE
                hit_target = spot_price <= strategy_state["target_price"]
                hit_sl = spot_price >= strategy_state["sl_price"]
                
            if hit_target or hit_sl:
                # Add failed exit cooldown check
                current_time = time.time()
                time_since_last_exit = current_time - strategy_state.get("last_exit_attempt_time", 0.0)
                if time_since_last_exit >= 5.0:
                    exit_triggered = True
                    trade_to_exit = {
                        "trading_symbol": strategy_state["trading_symbol"],
                        "trade_type": trade_type,
                        "entry_index_price": strategy_state["entry_index_price"],
                        "entry_option_price": strategy_state["entry_option_price"],
                        "is_sl": hit_sl
                    }
                    strategy_state["is_processing_order"] = True
                    strategy_state["last_exit_attempt_time"] = current_time
        else:
            ema_1m = strategy_state["ema_1m"]
            ema_5m = strategy_state["ema_5m"]
            atr = strategy_state["atr_1m"]
            adx = strategy_state["adx_1m"]
            
            if ema_1m > 0 and ema_5m > 0 and atr >= 5.0 and adx > ADX_THRESHOLD:
                # 1. CE entry check
                price_reaches_ema_ce = spot_price <= (ema_1m + 2.0) and spot_price >= (ema_1m - 5.0)
                ce_signal = (ema_1m > ema_5m) and price_reaches_ema_ce and STRATEGY_DIRECTION in ("CE", "BOTH")
                
                # 2. PE entry check
                price_reaches_ema_pe = spot_price >= (ema_1m - 2.0) and spot_price <= (ema_1m + 5.0)
                pe_signal = (ema_1m < ema_5m) and price_reaches_ema_pe and STRATEGY_DIRECTION in ("PE", "BOTH")
                
                current_time = time.time()
                time_since_last_trade = current_time - strategy_state["last_trade_time"]
                allow_entry = (strategy_state["last_trade_bar_timestamp"] != bar_timestamp) and (time_since_last_trade >= 60.0)
                
                if (ce_signal or pe_signal) and allow_entry:
                    entry_triggered = True
                    signal_details = {
                        "trade_type": "CE" if ce_signal else "PE",
                        "spot_price": spot_price,
                        "atr": atr,
                        "bar_timestamp": bar_timestamp,
                        "current_time": current_time
                    }
                    strategy_state["is_processing_order"] = True
                    strategy_state["last_trade_bar_timestamp"] = bar_timestamp
                    strategy_state["last_trade_time"] = current_time

    # 4. Launch background threads for API interaction (completely outside state_lock)
    if exit_triggered:
        threading.Thread(
            target=execute_exit_order,
            args=(trade_to_exit, spot_price, groww_client),
            daemon=True
        ).start()
        
    elif entry_triggered:
        threading.Thread(
            target=execute_entry_order,
            args=(signal_details, groww_client),
            daemon=True
        ).start()

def handle_tick(tick_data):
    """WebSocket tick callback."""
    global global_feed
    if global_feed is None:
        return
        
    token = tick_data.get("feed_key")
    feed_type = tick_data.get("feed_type")
    segment = tick_data.get("segment")
    exchange = tick_data.get("exchange")
    
    if not token or not feed_type:
        return
        
    # We only process NIFTY 50 Index ticks for signal generation
    if str(token) != "NIFTY" and str(token) != "99926000" and str(token) != "256":
        return
        
    if feed_type == FeedConstants.LIVE_INDEX:
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
        
    ltp = float(parsed_data.get("value") or 0.0)
    if ltp <= 0:
        return
        
    # Get current timestamp
    epoch_seconds = int(time.time())
    
    # Process tick through strategy pipeline
    # Passing global groww client object
    process_tick(ltp, epoch_seconds, global_groww_client)

def start_strategy():
    """Main strategy startup and WebSocket connection loop."""
    global global_groww_client, global_feed
    
    print("=" * 60)
    print(" 9 EMA MTF BOUNCE LIVE TRADING STRATEGY")
    print("=" * 60)
    print(f"Paper Trading Mode : {PAPER_TRADING}")
    print(f"Option Expiry Date : {NIFTY_EXPIRY_DATE}")
    print(f"Trading Quantity   : {LOT_SIZE} (1 Lot)")
    print(f"ADX Threshold Filter: {ADX_THRESHOLD}")
    print("-" * 60)
    
    if not GROWW_API_TOKEN:
        print("[Error] GROWW_API_TOKEN environment variable not found. Exiting.")
        sys.exit(1)
        
    if not NIFTY_EXPIRY_DATE:
        # Find nearest Thursday as expiry fallback
        today = datetime.date.today()
        days_ahead = (3 - today.weekday()) % 7
        next_thursday = today + datetime.timedelta(days=days_ahead)
        expiry_date = next_thursday.strftime("%Y-%m-%d")
        print(f"[Info] NIFTY_EXPIRY_DATE not found in .env. Fallback to nearest Thursday: {expiry_date}")
        os.environ["NIFTY_EXPIRY_DATE"] = expiry_date
    
    init_trade_log()
    
    # Initialize API Client
    global_groww_client = GrowwAPI(GROWW_API_TOKEN)
    
    # Bootstrap bars
    bootstrapped = bootstrap_historical_bars(global_groww_client)
    if not bootstrapped:
        print("[Warning] Continuing without historical warm-up. Indicators will take time to calculate.")
        
    # Register live WebSocket feed
    print("\nConnecting live Groww WebSocket feed...")
    try:
        global_feed = GrowwFeed(global_groww_client)
    except Exception:
        global_feed = GrowwFeed(GROWW_API_TOKEN)
        
    # Subscribe to Nifty 50 Index CASH segment
    # Groww handles NIFTY index feed key typically as "NIFTY" or "99926000" or "256"
    # We subscribe to NIFTY
    index_instrument = [{"exchange": "NSE", "segment": "CASH", "exchange_token": "NIFTY"}]
    
    global_feed.subscribe_index_value(index_instrument, on_data_received=handle_tick)
    print("[Strategy] Subscribed to Nifty 50 Index live stream. Listening for ticks...\n")
    
    # Consume feed in blocking mode with auto-reconnection
    print("[Strategy] WebSocket feed consumer started.")
    while True:
        try:
            global_feed.consume()
        except KeyboardInterrupt:
            print("\n[Strategy] Strategy stopped by user. Goodbye!")
            break
        except Exception as e:
            print(f"\n[Warning] WebSocket consumer connection error: {e}")
            print("Attempting to reconnect in 5 seconds...")
            time.sleep(5)
            try:
                # Reconnection attempts
                try:
                    global_feed = GrowwFeed(global_groww_client)
                except Exception:
                    global_feed = GrowwFeed(GROWW_API_TOKEN)
                global_feed.subscribe_index_value(index_instrument, on_data_received=handle_tick)
                print("[Strategy] Re-subscribed to Nifty 50 Index live stream.")
            except Exception as re_err:
                print(f"[Error] Reconnection failed: {re_err}")

if __name__ == "__main__":
    start_strategy()
