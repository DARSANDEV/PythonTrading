import os
import glob
import pandas as pd
from app.core.config import settings
from app.services.collector import fetch_historic_data
from app.services.ticker_helper import ticker_to_filename

class DataRepository:
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or settings.STOCK_DATA_PATH
        # Ensure directory exists immediately
        os.makedirs(self.storage_path, exist_ok=True)

    def save_historical_data(self, ticker: str, interval: str, count: int) -> str:
        """
        Saves historical data for a single ticker to CSV.
        Returns the full path of the saved file.
        """
        try:
            print(f"Saving data for {ticker}...")
            df = fetch_historic_data(ticker, interval, count)
            filename = ticker_to_filename(ticker, 'csv')
            full_path = os.path.join(self.storage_path, filename)
            df.to_csv(full_path, index=False)
            print(f"Saved {ticker} -> {full_path}")
            return full_path
        except Exception as e:
            print(f"Error saving data for {ticker}: {e}")
            raise e

    def get_latest_csv(self, symbol: str) -> str:
        """
        Retrieves the latest CSV file for a given symbol.
        Searches for files matching the symbol pattern and returns the one with the most recent modification time.
        """
        try:
            # Convert ticker to safe filename format (replace : with _)
            safe_symbol = symbol.replace(":", "_")
            
            # Search pattern: safe_symbol*.csv in the folder_path
            search_pattern = f"{safe_symbol}*.csv"
            full_search_path = os.path.join(self.storage_path, search_pattern)
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

    def get_historic_data_from_storage(self, symbol: str) -> pd.DataFrame:
        """
        Reads the latest CSV for the symbol and returns a DataFrame.
        """
        file_path = self.get_latest_csv(symbol)
        if file_path:
            return pd.read_csv(file_path)
        return pd.DataFrame()
