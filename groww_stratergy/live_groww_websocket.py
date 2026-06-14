import sys
import os
import datetime
import math
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
    print("[Warning] The 'growwapi' library is not installed.")
    print("Please install it using: pip install growwapi")
    GrowwAPI = None
    GrowwFeed = None
    FeedConstants = None
    get_data_dict = None

def get_atm_strike(spot_price, strikes):
    """Find the strike price closest to the spot price."""
    return min(strikes, key=lambda x: abs(x - spot_price))

def calculate_days_to_expiry(expiry_date_str):
    """Calculate days to expiry from YYYY-MM-DD string."""
    expiry_date = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    delta = expiry_date - today
    return max(delta.days, 0.5)

# Shared real-time state
state = {
    "spot_price": 0.0,
    "spot_token": None,
    
    "call_ltp": 0.0,
    "call_token": None,
    "call_iv": 12.0,
    "call_ref_iv": 12.0,
    "call_theo": 0.0,
    
    "put_ltp": 0.0,
    "put_token": None,
    "put_iv": 12.0,
    "put_ref_iv": 12.0,
    "put_theo": 0.0,
    
    "atm_strike": 0.0,
    "T": 0.0,
    "r": 0.07,
    "expiry_date": "",
    "days_remaining": 0.0,
}
global_feed = None

def recalculate_and_print():
    """Recalculate BSM theoretical prices and print the update in one row."""
    # Ensure spot price is valid
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

    # Use the stable reference IV for BSM valuation
    ref_call_iv = state.get("call_ref_iv") or state["call_iv"] or 12.0
    ref_put_iv = state.get("put_ref_iv") or state["put_iv"] or 12.0

    # Call valuation
    bs_call = BlackScholes(state["spot_price"], state["atm_strike"], state["T"], state["r"], ref_call_iv / 100.0)
    state["call_theo"] = bs_call.call_price()
    call_diff = state["call_ltp"] - state["call_theo"]

    # Put valuation
    bs_put = BlackScholes(state["spot_price"], state["atm_strike"], state["T"], state["r"], ref_put_iv / 100.0)
    state["put_theo"] = bs_put.put_price()
    put_diff = state["put_ltp"] - state["put_theo"]

    # Print in one row
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    ce_str = f"CE LTP: {state['call_ltp']:.2f} (BSM: {state['call_theo']:.2f}, Diff: {call_diff:+.2f}, IV: {state['call_iv']:.2f}%)"
    pe_str = f"PE LTP: {state['put_ltp']:.2f} (BSM: {state['put_theo']:.2f}, Diff: {put_diff:+.2f}, IV: {state['put_iv']:.2f}%)"
    
    # Print normally so the user has a scrolling log of ticks.
    print(
        f"[{timestamp}] NIFTY: {state['spot_price']:.2f} | ATM Strike: {state['atm_strike']:.0f} | "
        f"{ce_str} | {pe_str}"
    )

def handle_tick(tick_data):
    """
    Callback function called when a new tick is received from Groww WebSocket.
    """
    try:
        global global_feed
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

        updated = False

        # Match tokens
        instrument_type = "Unknown"
        token_str = str(token)
        state_spot_token_str = str(state["spot_token"]) if state["spot_token"] is not None else ""
        state_call_token_str = str(state["call_token"]) if state["call_token"] is not None else ""
        state_put_token_str = str(state["put_token"]) if state["put_token"] is not None else ""

        if token_str == state_spot_token_str:
            state["spot_price"] = ltp
            updated = True
            instrument_type = "Spot"
        elif token_str == state_call_token_str:
            state["call_ltp"] = ltp
            updated = True
            instrument_type = "Call"
            # Dynamically update IV if provided in the feed
            iv = parsed_data.get("iv") or parsed_data.get("impliedVolatility")
            if iv:
                state["call_iv"] = float(iv)
        elif token_str == state_put_token_str:
            state["put_ltp"] = ltp
            updated = True
            instrument_type = "Put"
            iv = parsed_data.get("iv") or parsed_data.get("impliedVolatility")
            if iv:
                state["put_iv"] = float(iv)

        if updated:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] WS Tick Received -> {instrument_type} (Token: {token}) LTP: {ltp:.2f}")
            recalculate_and_print()
            
    except Exception as e:
        # Fail silently in feed thread but prevent crashes
        pass

def main():
    if GrowwAPI is None or GrowwFeed is None:
        print("\nTo run this script, please install growwapi first:")
        print("pip install growwapi")
        return

    print("=" * 60)
    print(" GROWW WEBSOCKET TICK-BY-TICK NIFTY BSM EVALUATION")
    print("=" * 60)

    # Fetch token
    api_token = os.environ.get("GROWW_API_TOKEN")
    if not api_token:
        print("GROWW_API_TOKEN environment variable not found in .env.")
        api_token = input("Please enter your Groww API Auth Token: ").strip()
        if not api_token:
            print("[Error] API Auth Token is required.")
            return

    try:
        # Initialize Groww API
        groww = GrowwAPI(api_token)

        # Expiry date
        expiry_date = input("Expiry Date (YYYY-MM-DD, e.g., 2026-06-04): ").strip()
        if not expiry_date:
            print("[Error] Expiry date is required.")
            return

        # Fetch option chain once via REST to get spot price, ATM strike, and exchange tokens
        print("\nFetching initial option chain to identify tokens...")
        option_chain = groww.get_option_chain(exchange="NSE", underlying="NIFTY", expiry_date=expiry_date)
        
        if not option_chain:
            print("[Error] Failed to fetch initial option chain.")
            return

        underlying = option_chain.get("underlying", {})
        spot_price = float(option_chain.get("underlying_ltp") or underlying.get("spot_price") or underlying.get("lastPrice") or option_chain.get("spot_price") or 0.0)
        spot_token = underlying.get("exchange_token") or underlying.get("instrument_token") or underlying.get("token") or "NIFTY"

        strikes_dict = option_chain.get("strikes") or {}
        
        if strikes_dict:
            # Handle new dictionary format
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

        # Set shared state variables
        days = calculate_days_to_expiry(expiry_date)
        state["spot_price"] = spot_price
        state["spot_token"] = str(spot_token)
        state["atm_strike"] = atm_strike
        state["T"] = days / 365.0
        state["expiry_date"] = expiry_date
        state["days_remaining"] = days

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

        # Recalculate first time
        recalculate_and_print()
        print(f"\n\nSubscribing to live updates for:")
        print(f"  - Nifty 50 Index (Token: {state['spot_token']})")
        print(f"  - ATM Call Strike {state['atm_strike']} (Token: {state['call_token']})")
        print(f"  - ATM Put Strike {state['atm_strike']} (Token: {state['put_token']})")
        print("Listening for ticks (Press Ctrl+C to stop)...\n")

        # Initialize WebSocket Feed
        global global_feed
        try:
            global_feed = GrowwFeed(groww)
        except Exception:
            global_feed = GrowwFeed(api_token)
        feed = global_feed

        # Build subscription list
        # Segment CASH is typical for indices; segment FNO for contracts
        index_instruments = []
        option_instruments = []
        if state["spot_token"] and state["spot_token"] != "None":
            index_instruments.append({
                "exchange": "NSE", 
                "segment": "CASH", 
                "exchange_token": state["spot_token"]
            })
        if state["call_token"] and state["call_token"] != "None":
            option_instruments.append({
                "exchange": "NSE", 
                "segment": "FNO", 
                "exchange_token": state["call_token"]
            })
        if state["put_token"] and state["put_token"] != "None":
            option_instruments.append({
                "exchange": "NSE", 
                "segment": "FNO", 
                "exchange_token": state["put_token"]
            })

        # Register callbacks and start WebSocket
        if index_instruments:
            feed.subscribe_index_value(index_instruments, on_data_received=handle_tick)
        if option_instruments:
            feed.subscribe_ltp(option_instruments, on_data_received=handle_tick)
        feed.consume()

    except KeyboardInterrupt:
        print("\n\nExiting WebSocket loop. Goodbye!")
    except Exception as e:
        print(f"\n[Error] WebSocket connection failed: {e}")

if __name__ == "__main__":
    main()
