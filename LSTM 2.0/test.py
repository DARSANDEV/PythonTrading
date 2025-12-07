from data_collector import get_live_data,get_historic_data
from data_repository import save_historical_data_to_csv,get_latest_csv 
from ticker_helper import generate_option_tickers
print('welcome')
#print(get_live_data())

print(get_historic_data("NSE:NIFTY","5",10000))
#print(get_live_data("NSE:NIFTY","1",1000000,include_historic_data=False))
#print(get_historic_data("NSE:NIFTY251202C26000","1",100000000))
#ticker = input("Entertiker : eg:NSE:NIFTY251202C26000")
#save_historical_data_to_csv(ticker,"1",1000000)


def options_data_saving_test():
   index_symbol = "NIFTY"
   expiry_date_str = "251209"
   strike_interval = 50
   num_strikes = 3
   option_types = ["C","P"]
   option_settings = {
       "strike_interval": strike_interval,
       "num_strikes": num_strikes,
       "option_types": option_types
   }
   print(generate_option_tickers(index_symbol, expiry_date_str, None, option_settings))

#options_data_saving_test()
#print(get_latest_csv("NSE:NIFTY251125C26000"))

print('App closed')
