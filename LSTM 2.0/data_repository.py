import os
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
        df.to_csv(filename, index=False)
        full_path = os.path.join(folder_path, filename)
        print(f"Saved {ticker} → {full_path}")
    except Exception as e:
        print(f"Error saving data for {ticker}: {e}")
