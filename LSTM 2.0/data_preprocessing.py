import pandas as pd

def add_target_class(data):
    """Adds Target and TargetClass to the dataset."""
    data["Adj Close"] = data["Close"].shift(1)
    data['Target'] = data['Adj Close'] - data['Open']
    data['Target'] = data['Target'].shift(-1)

    # Add TargetClass (Binary classification: 1 if price increases, 0 otherwise)
    data['TargetClass'] = (data['Target'] > 0).astype(int)

    return data

def drop_data(data):
    """Cleans and preprocesses data by removing NaN values and unnecessary columns."""
    data = data.dropna().reset_index(drop=True)  # Ensures fresh indexing
    data = data.drop(['Close', 'TimeStamp'], axis=1, errors='ignore')  # Prevent KeyError if column is missing
    return data

def preprocess_data(data):
    """Runs the full preprocessing pipeline."""
    data = add_target_class(data)
    data = drop_data(data)
    return data
