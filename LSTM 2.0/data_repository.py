import os
import glob
import pandas as pd
from datetime import datetime
from data_collector import get_historic_data
from ticker_helper import ticker_to_filename
folder_path ='./data/'


def save_historical_for_tickers_to_csv(tickers, interval, count):
    """
    For each ticker, call your get_historic_data and save to CSV.
    """
    for t in tickers:
        save_historical_data_to_csv(t, interval, count)

def save_historical_data_to_csv(ticker, interval, count):
    """
    Saves historical data for a single ticker to CSV.
    """
    try:
        print(f"Saving data for {ticker}...")
        df = get_historic_data(ticker, interval, count)
        filename = ticker_to_filename(ticker,'csv')
        full_path = os.path.join(folder_path, filename)
        df.to_csv(full_path, index=False)
        print(f"Saved {ticker} → {full_path}")
    except Exception as e:
        print(f"Error saving data for {ticker}: {e}")

def get_latest_csv(symbol):
    """
    Retrieves the latest CSV file for a given symbol.
    Searches for files matching the symbol pattern and returns the one with the most recent modification time.
    """
    try:
        # Convert ticker to safe filename format (replace : with _)
        safe_symbol = symbol.replace(":", "_")
        
        # Search pattern: safe_symbol*.csv in the folder_path
        search_pattern = f"{safe_symbol}*.csv"
        full_search_path = os.path.join(folder_path, search_pattern)
        print(f"Searching in: {full_search_path}")
        files = glob.glob(full_search_path)
        
        if not files:
            print(f"No CSV files found for symbol: {symbol}")
            return None
            
        # Get the latest file based on modification time
        latest_file = max(files, key=os.path.getmtime)
        print(f"Found latest file for {symbol}: {latest_file}")
        return latest_file
        
    except Exception as e:
        print(f"Error retrieving CSV for {symbol}: {e}")
        return None
