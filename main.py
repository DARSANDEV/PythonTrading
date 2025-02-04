from tradingview_ta import TA_Handler, Interval, Exchange

#import pandas as pd

# Create a handler for the desired symbol
handler = TA_Handler(
    symbol="AAPL",
    exchange="NASDAQ",
    screener="america",
    interval=Interval.INTERVAL_1_MINUTE,
    timeout=10
)

# Get the analysis
analysis = handler.get_analysis()

# Access live data
live_data = handler.get_live_data()

# Print the live data
print(live_data)