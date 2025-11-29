from datetime import datetime
from app.services.collector import fetch_historic_data

def get_current_index_level(index_ticker):
    """
    Fetches current level of the given index (e.g., NIFTY50).
    """
    df = fetch_historic_data(index_ticker, time_frame="1", period=1)
    level = df['close'].iloc[-1] if not df.empty else None
    return level

def round_to_nearest_strike(level, strike_interval):
    """
    Rounds the level to the nearest strike (up or down) based on the interval.
    """
    return int(round(level / strike_interval) * strike_interval)

def generate_strike_list(rounded_strike, num_strikes, interval):
    """
    Returns a list of strike prices around the rounded_strike.
    """
    half = num_strikes // 2
    strikes = [rounded_strike + (i * interval) for i in range(-half, half+1)]
    return strikes

def generate_option_tickers_list(index_symbol, expiry_date_str, strikes, option_types):
    """
    Generates tickers like “NSE:NIFTY251118C26000” given:
      - index_symbol: e.g. "NIFTY"
      - expiry_date_str: e.g. "251118" for 2025-11-18
      - strikes: list of strike prices e.g. [25400,25500,25600]
      - option_types: e.g. ["C","P"]
    Returns list of tickers.
    """
    tickers = []
    for st in strikes:
        for ot in option_types:
            t = f"NSE:{index_symbol}{expiry_date_str}{ot}{st}"
            tickers.append(t)
    return tickers

def generate_option_tickers(index_symbol, expiry_date_str, level=None, option_settings=None):
    """
    Generates option tickers for a given index, expiry date, level, and option types.
    if level is empty it takes current level of index
    """
    try:
        if option_settings is None:
            option_settings = {}
            
        strike_interval = option_settings.get('strike_interval', 5)
        num_strikes = option_settings.get('num_strikes', 5)
        option_types = option_settings.get('option_types', ["C", "P"])

        if level is None:
            level = get_current_index_level(f"NSE:{index_symbol}")
        
        if level is None:
            return []

        rounded = round_to_nearest_strike(level, strike_interval)  
        strikes = generate_strike_list(rounded, num_strikes, strike_interval)
        return generate_option_tickers_list(index_symbol, expiry_date_str, strikes, option_types)
    except Exception as e:
        print(f"Error generating option tickers: {e}")
        return []

def ticker_to_filename(ticker, file_format):
    """
    Converts a ticker to a safe filename.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_t = ticker.replace(":", "_")
    filename = f"{safe_t}-V-{timestamp}.{file_format}"
    return filename
