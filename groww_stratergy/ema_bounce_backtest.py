import os
import sys
import time
import datetime
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Ensure groww_Startergy and root are in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from growwapi import GrowwAPI
    from option import BlackScholes
except ImportError as e:
    print(f"[Error] Required packages or local modules not found: {e}")
    sys.exit(1)

def get_atm_option_price(spot, entry_time, trade_time, strike=None, option_type="CE"):
    """
    Calculate the option price using the Black-Scholes model.
    Assumes standard Nifty options with weekly Tuesday expiry.
    """
    if isinstance(entry_time, str):
        entry_time = pd.to_datetime(entry_time)
    if isinstance(trade_time, str):
        trade_time = pd.to_datetime(trade_time)
        
    # Find the next Tuesday for expiry
    # weekday: Monday=0, Tuesday=1 ...
    days_to_tuesday = (1 - entry_time.weekday()) % 7
    if days_to_tuesday == 0:
        # If entry is on Tuesday itself, check if it's after market close (15:30)
        if entry_time.hour > 15 or (entry_time.hour == 15 and entry_time.minute >= 30):
            days_to_tuesday = 7
            
    expiry_date = entry_time.date() + datetime.timedelta(days=days_to_tuesday)
    expiry_datetime = datetime.datetime.combine(expiry_date, datetime.time(15, 30, 0))
    
    # Time remaining in years
    time_diff = expiry_datetime - trade_time
    seconds_remaining = time_diff.total_seconds()
    
    # Ensure minimum time remaining (5 minutes) to avoid pricing anomalies near zero
    seconds_remaining = max(300.0, seconds_remaining)
    T = seconds_remaining / (365.0 * 24.0 * 3600.0)
    
    # Strike selection (ATM at entry_time)
    if strike is None:
        strike = round(spot / 50.0) * 50.0
        
    # Standard Nifty Option Parameters: Risk-free rate r = 7%, Volatility sigma = 15%
    r = 0.07
    sigma = 0.15
    
    bs = BlackScholes(S=spot, K=strike, T=T, r=r, sigma=sigma)
    if option_type == "CE":
        price = bs.call_price()
    else:
        price = bs.put_price()
        
    return max(0.05, price), strike

# Configurations
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

GROWW_API_TOKEN = os.environ.get("GROWW_API_TOKEN")
CSV_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REPORT_FILE = os.path.join(CSV_DIR, "backtest_trades_report.csv")

# Create data directory if not exists
os.makedirs(CSV_DIR, exist_ok=True)

def download_historical_data(groww_client, start_date_str, end_date_str, trading_symbol="NIFTY"):
    """
    Download Nifty 1-minute historical candles from start_date to end_date day-by-day
    to avoid single-request size limits.
    """
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    
    print(f"[Backtester] Fetching historical 1-minute data from {start_date} to {end_date}...")
    
    all_candles = []
    delta = datetime.timedelta(days=1)
    current_date = start_date
    
    while current_date <= end_date:
        # Skip weekends (Saturday=5, Sunday=6)
        if current_date.weekday() >= 5:
            current_date += delta
            continue
            
        start_str = f"{current_date} 09:15:00"
        end_str = f"{current_date} 15:30:00"
        
        print(f"  Downloading Nifty index candles for {current_date}...", end="", flush=True)
        
        try:
            # Try get_historical_candle_data first
            try:
                res = groww_client.get_historical_candle_data(
                    trading_symbol=trading_symbol,
                    exchange="NSE",
                    segment="CASH",
                    start_time=start_str,
                    end_time=end_str,
                    interval_in_minutes=1
                )
            except Exception:
                # Fallback to get_historical_candles if groww_symbol is required
                res = groww_client.get_historical_candles(
                    exchange="NSE",
                    segment="CASH",
                    groww_symbol=trading_symbol,
                    start_time=start_str,
                    end_time=end_str,
                    candle_interval="1minute"
                )
                
            candles = res.get("candles") or []
            if candles:
                all_candles.extend(candles)
                print(f" Loaded {len(candles)} candles.")
            else:
                print(" No data returned (market holiday?).")
        except Exception as e:
            print(f" Error: {e}")
            
        current_date += delta
        time.sleep(0.2) # modest rate limit delay
        
    if not all_candles:
        print("[Backtester Error] No historical candles were successfully retrieved.")
        return None
        
    # Sort candles by timestamp ascending
    all_candles = sorted(all_candles, key=lambda x: x[0])
    
    bars = []
    for c in all_candles:
        # Filter out empty or None candles
        if c[0] and c[1] and c[2] and c[3] and c[4]:
            bars.append({
                "timestamp": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4])
            })
            
    print(f"[Backtester] Download completed. Loaded a total of {len(bars)} 1-minute bars.")
    return bars

def calculate_indicators(bars_list):
    """
    Compute 1m EMA, 1m ATR, 1m ADX, resample to 5m, compute 5m EMA, and align.
    """
    df = pd.DataFrame(bars_list)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    
    # 9 EMA of 1m Close
    df['ema_1m'] = df['close'].ewm(span=9, adjust=False).mean()
    
    # 14 ATR
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift()).abs()
    low_cp = (df['low'] - df['close'].shift()).abs()
    df['tr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    df['atr_1m'] = df['tr'].ewm(alpha=1/14, adjust=False).mean()
    
    # 14 ADX (Wilder's Smoothing)
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
    df['adx_1m'] = df['dx'].ewm(alpha=1/14, adjust=False).mean()
    
    # Resample 1m bars to 5m bars
    df_5m = df.resample('5Min', on='datetime').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    df_5m['ema_5m'] = df_5m['close'].ewm(span=9, adjust=False).mean()
    df_5m['start_slot'] = df_5m.index.astype(int) // 10**9
    df_5m['completed_at'] = df_5m['start_slot'] + 300
    
    # Merge completed 5m EMA back onto 1m bars without lookahead bias
    df = pd.merge_asof(
        df.sort_values('timestamp'),
        df_5m[['completed_at', 'ema_5m']].sort_values('completed_at'),
        left_on='timestamp',
        right_on='completed_at',
        direction='backward'
    )
    
    return df

def run_simulation(df, adx_threshold=15, atr_threshold=5.0, direction="BOTH"):
    """
    Loop through historical 1-minute bars to simulate entry, target, and stop-loss exits.
    Option entry and exit prices are calculated for the ATM Call/Put option using Black-Scholes.
    """
    in_trade = False
    trade_type = "CE" # "CE" or "PE"
    entry_price = 0.0
    entry_time = None
    target_price = 0.0
    sl_price = 0.0
    strike = 0.0
    buy_option_price = 0.0
    atr = 0.0
    trades = []
    
    print(f"\n[Backtester] Simulating strategy trades ({direction} direction | ADX filter: {adx_threshold} | ATR filter: {atr_threshold} points)...")
    
    for idx, row in df.iterrows():
        current_time = row['datetime']
        
        # Force close open position at the end of the day (3:25 PM) to avoid overnight risk
        if in_trade and current_time.hour == 15 and current_time.minute >= 25:
            exit_p = row['close']
            sell_option_price, _ = get_atm_option_price(exit_p, entry_time, current_time, strike=strike, option_type=trade_type)
            pnl_opt = sell_option_price - buy_option_price
            trades.append({
                "entry_time": entry_time,
                "exit_time": current_time,
                "index_entry_price": entry_price,
                "index_exit_price": exit_p,
                "strike": strike,
                "option_type": trade_type,
                "entry_price": buy_option_price,
                "exit_price": sell_option_price,
                "pnl": pnl_opt,
                "result": "WIN" if pnl_opt > 0 else "LOSS",
                "atr": atr,
                "exit_type": "EOD_FORCE_CLOSE"
            })
            in_trade = False
            continue
            
        if not in_trade:
            # Check entry criteria
            ema_1m = row['ema_1m']
            ema_5m = row['ema_5m']
            atr_1m = row['atr_1m']
            adx_1m = row['adx_1m']
            
            # Make sure indicators are fully initialized
            if pd.isna(ema_1m) or pd.isna(ema_5m) or pd.isna(atr_1m) or pd.isna(adx_1m):
                continue
                
            # Filter checks
            atr_ok = atr_1m >= atr_threshold
            adx_ok = adx_1m > adx_threshold
            
            # Price reaches 1m EMA check: low <= 1m EMA <= high
            price_reaches_ema = row['low'] <= ema_1m and row['high'] >= ema_1m
            
            if atr_ok and adx_ok and price_reaches_ema:
                # 1. CE entry check (Bullish alignment)
                if (ema_1m > ema_5m) and direction in ("CE", "BOTH"):
                    in_trade = True
                    trade_type = "CE"
                    entry_price = ema_1m # assume limit entry at the exact 1m EMA touch price
                    entry_time = current_time
                    atr = atr_1m
                    target_price = entry_price + (0.5 * atr)
                    sl_price = entry_price - (0.5 * atr)
                    
                    # Calculate entry option price and select ATM strike
                    buy_option_price, strike = get_atm_option_price(entry_price, entry_time, entry_time, strike=None, option_type="CE")
                
                # 2. PE entry check (Bearish alignment)
                elif (ema_1m < ema_5m) and direction in ("PE", "BOTH"):
                    in_trade = True
                    trade_type = "PE"
                    entry_price = ema_1m # assume limit entry at the exact 1m EMA touch price
                    entry_time = current_time
                    atr = atr_1m
                    target_price = entry_price - (0.5 * atr) # target is below entry
                    sl_price = entry_price + (0.5 * atr)     # stop loss is above entry
                    
                    # Calculate entry option price and select ATM strike
                    buy_option_price, strike = get_atm_option_price(entry_price, entry_time, entry_time, strike=None, option_type="PE")
        else:
            # We are in trade, monitor exits
            high = row['high']
            low = row['low']
            
            if trade_type == "CE":
                hit_target = high >= target_price
                hit_sl = low <= sl_price
                
                if hit_target and hit_sl:
                    # Conservatively assume SL was hit first
                    exit_p = sl_price
                    sell_option_price, _ = get_atm_option_price(exit_p, entry_time, current_time, strike=strike, option_type="CE")
                    pnl_opt = sell_option_price - buy_option_price
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "index_entry_price": entry_price,
                        "index_exit_price": exit_p,
                        "strike": strike,
                        "option_type": "CE",
                        "entry_price": buy_option_price,
                        "exit_price": sell_option_price,
                        "pnl": pnl_opt,
                        "result": "LOSS",
                        "atr": atr,
                        "exit_type": "STOP_LOSS_DOUBLE_HIT"
                    })
                    in_trade = False
                elif hit_sl:
                    exit_p = sl_price
                    sell_option_price, _ = get_atm_option_price(exit_p, entry_time, current_time, strike=strike, option_type="CE")
                    pnl_opt = sell_option_price - buy_option_price
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "index_entry_price": entry_price,
                        "index_exit_price": exit_p,
                        "strike": strike,
                        "option_type": "CE",
                        "entry_price": buy_option_price,
                        "exit_price": sell_option_price,
                        "pnl": pnl_opt,
                        "result": "LOSS",
                        "atr": atr,
                        "exit_type": "STOP_LOSS"
                    })
                    in_trade = False
                elif hit_target:
                    exit_p = target_price
                    sell_option_price, _ = get_atm_option_price(exit_p, entry_time, current_time, strike=strike, option_type="CE")
                    pnl_opt = sell_option_price - buy_option_price
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "index_entry_price": entry_price,
                        "index_exit_price": exit_p,
                        "strike": strike,
                        "option_type": "CE",
                        "entry_price": buy_option_price,
                        "exit_price": sell_option_price,
                        "pnl": pnl_opt,
                        "result": "WIN" if pnl_opt > 0 else "LOSS",
                        "atr": atr,
                        "exit_type": "TARGET"
                    })
                    in_trade = False
            else: # trade_type == "PE"
                hit_target = low <= target_price  # Target hit if index drops below target
                hit_sl = high >= sl_price        # SL hit if index rises above stop loss
                
                if hit_target and hit_sl:
                    # Conservatively assume SL was hit first
                    exit_p = sl_price
                    sell_option_price, _ = get_atm_option_price(exit_p, entry_time, current_time, strike=strike, option_type="PE")
                    pnl_opt = sell_option_price - buy_option_price
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "index_entry_price": entry_price,
                        "index_exit_price": exit_p,
                        "strike": strike,
                        "option_type": "PE",
                        "entry_price": buy_option_price,
                        "exit_price": sell_option_price,
                        "pnl": pnl_opt,
                        "result": "LOSS",
                        "atr": atr,
                        "exit_type": "STOP_LOSS_DOUBLE_HIT"
                    })
                    in_trade = False
                elif hit_sl:
                    exit_p = sl_price
                    sell_option_price, _ = get_atm_option_price(exit_p, entry_time, current_time, strike=strike, option_type="PE")
                    pnl_opt = sell_option_price - buy_option_price
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "index_entry_price": entry_price,
                        "index_exit_price": exit_p,
                        "strike": strike,
                        "option_type": "PE",
                        "entry_price": buy_option_price,
                        "exit_price": sell_option_price,
                        "pnl": pnl_opt,
                        "result": "LOSS",
                        "atr": atr,
                        "exit_type": "STOP_LOSS"
                    })
                    in_trade = False
                elif hit_target:
                    exit_p = target_price
                    sell_option_price, _ = get_atm_option_price(exit_p, entry_time, current_time, strike=strike, option_type="PE")
                    pnl_opt = sell_option_price - buy_option_price
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_time,
                        "index_entry_price": entry_price,
                        "index_exit_price": exit_p,
                        "strike": strike,
                        "option_type": "PE",
                        "entry_price": buy_option_price,
                        "exit_price": sell_option_price,
                        "pnl": pnl_opt,
                        "result": "WIN" if pnl_opt > 0 else "LOSS",
                        "atr": atr,
                        "exit_type": "TARGET"
                    })
                    in_trade = False
                
    return trades

def generate_performance_report(trades):
    """
    Calculate and display detailed backtest performance statistics.
    """
    if not trades:
        print("\n[Backtester] No trades were generated during the backtest period.")
        return
        
    df_trades = pd.DataFrame(trades)
    
    total_trades = len(df_trades)
    winning_trades = len(df_trades[df_trades["result"] == "WIN"])
    losing_trades = len(df_trades[df_trades["result"] == "LOSS"])
    
    win_rate = (winning_trades / total_trades) * 100.0 if total_trades > 0 else 0.0
    
    total_pnl = df_trades["pnl"].sum()
    avg_pnl = df_trades["pnl"].mean()
    
    gross_profits = df_trades[df_trades["pnl"] > 0]["pnl"].sum()
    gross_losses = abs(df_trades[df_trades["pnl"] < 0]["pnl"].sum())
    profit_factor = gross_profits / gross_losses if gross_losses > 0 else float('inf')
    
    # Calculate Drawdown
    df_trades["cum_pnl"] = df_trades["pnl"].cumsum()
    df_trades["peak"] = df_trades["cum_pnl"].cummax()
    df_trades["drawdown"] = df_trades["cum_pnl"] - df_trades["peak"]
    max_drawdown = df_trades["drawdown"].min()
    
    print("\n" + "=" * 50)
    print("      BACKTEST PERFORMANCE METRICS REPORT")
    print("=" * 50)
    print(f"Total Simulated Trades  : {total_trades}")
    print(f"Winning Trades          : {winning_trades}")
    print(f"Losing Trades           : {losing_trades}")
    print(f"Win Rate                : {win_rate:.2f}%")
    print("-" * 50)
    print(f"Total Net Return        : {total_pnl:+.2f} option points")
    print(f"Average Return / Trade  : {avg_pnl:+.2f} option points")
    print(f"Profit Factor           : {profit_factor:.2f}")
    print(f"Maximum Peak Drawdown   : {max_drawdown:.2f} option points")
    print("=" * 50)
    
    # Save report to CSV
    try:
        df_trades.to_csv(REPORT_FILE, index=False)
        print(f"[Backtester] Detailed transaction log exported to: {REPORT_FILE}\n")
    except PermissionError:
        # Fallback to a backup file if the main file is locked by the user (e.g., open in Excel)
        backup_file = REPORT_FILE.replace(".csv", f"_backup_{int(time.time())}.csv")
        try:
            df_trades.to_csv(backup_file, index=False)
            print(f"\n[Warning] Permission Denied: Could not write to {REPORT_FILE} (is it open in Excel?).")
            print(f"[Backtester] Saved report to backup file: {backup_file}")
            # Overwrite the REPORT_FILE variable so other functions write/read from the backup file
            global REPORT_FILE_LOCKED_FALLBACK
            REPORT_FILE_LOCKED_FALLBACK = backup_file
            print(f"[Backtester] Please close Excel and run again to update the main report.\n")
        except Exception as e:
            print(f"[Error] Failed to save backtest report: {e}\n")
    
    # Show last 10 transactions
    print("Last 10 Transactions:")
    print(df_trades[["entry_time", "exit_time", "option_type", "entry_price", "exit_price", "pnl", "result", "exit_type"]].tail(10))

def main():
    import argparse
    parser = argparse.ArgumentParser(description="EMA Bounce Strategy Historical Backtester")
    parser.add_argument("--start", type=str, required=True, help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, required=True, help="End Date (YYYY-MM-DD)")
    parser.add_argument("--symbol", type=str, default="NIFTY", help="Index underlying symbol (default: NIFTY)")
    parser.add_argument("--adx", type=int, default=15, help="ADX filter threshold (default: 15)")
    parser.add_argument("--atr_min", type=float, default=5.0, help="Min ATR threshold in points (default: 5.0)")
    parser.add_argument("--direction", type=str, default="BOTH", choices=["CE", "PE", "BOTH"], help="Trade direction filter (default: BOTH)")
    
    args = parser.parse_args()
    
    if not GROWW_API_TOKEN:
        print("[Error] GROWW_API_TOKEN environment variable not found in .env. Exiting.")
        sys.exit(1)
        
    # Initialize groww client
    groww = GrowwAPI(GROWW_API_TOKEN)
    
    # Fetch historical data
    bars = download_historical_data(groww, args.start, args.end, trading_symbol=args.symbol)
    if not bars:
        return
        
    # Calculate indicators
    print("\n[Backtester] Calculating strategy indicators (resampling 1m to 5m EMA)...")
    df = calculate_indicators(bars)
    
    # Simulate trades
    trades = run_simulation(df, adx_threshold=args.adx, atr_threshold=args.atr_min, direction=args.direction)
    
    # Generate report
    generate_performance_report(trades)

if __name__ == "__main__":
    main()
