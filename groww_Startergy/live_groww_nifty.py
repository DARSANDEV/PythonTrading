import sys
import os
import datetime
import math
from option import BlackScholes

# Load environment variables from .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Try importing growwapi
try:
    from growwapi import GrowwAPI
except ImportError:
    print("[Warning] The 'growwapi' library is not installed.")
    print("Please install it using: pip install growwapi")
    GrowwAPI = None

def get_atm_strike(spot_price, strikes):
    """Find the strike price closest to the spot price."""
    return min(strikes, key=lambda x: abs(x - spot_price))

def calculate_days_to_expiry(expiry_date_str):
    """Calculate days to expiry from YYYY-MM-DD string."""
    expiry_date = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    today = datetime.date.today()
    delta = expiry_date - today
    return max(delta.days, 0.5)

def main():
    if GrowwAPI is None:
        print("\nTo run this script, please install growwapi first:")
        print("pip install growwapi")
        return

    print("=" * 60)
    print(" GROWW API LIVE NIFTY 50 BLACK-SCHOLES VALUATION")
    print("=" * 60)

    # Fetch token from environment variable or prompt user
    api_token = os.environ.get("GROWW_API_TOKEN")
    if not api_token:
        print("GROWW_API_TOKEN environment variable not found.")
        api_token = input("Please enter your Groww API Auth Token: ").strip()
        if not api_token:
            print("[Error] API Auth Token is required.")
            return

    try:
        
        # Initialize Groww API Client
        groww = GrowwAPI(api_token)
        
        # User input for expiry date
        print("\nSpecify NIFTY 50 Expiry Date:")
        expiry_date = input("Expiry Date (YYYY-MM-DD, e.g., 2026-06-04): ").strip()
        if not expiry_date:
            print("[Error] Expiry date is required.")
            return

        # Fetch option chain for NIFTY
        print("\nFetching option chain data from Groww...")
        option_chain = groww.get_option_chain(exchange="NSE", underlying="NIFTY", expiry_date=expiry_date)
        
        if not option_chain:
            print("[Error] Failed to fetch option chain or empty data returned.")
            return
            
        # Parse underlying price
        underlying = option_chain.get("underlying", {})
        spot_price = float(option_chain.get("underlying_ltp") or underlying.get("spot_price") or underlying.get("lastPrice") or option_chain.get("spot_price") or 0.0)
        if spot_price == 0.0:
            spot_price = float(option_chain.get("underlyingPrice") or 0.0)
            
        if spot_price == 0.0:
            print("[Error] Could not retrieve the spot price of NIFTY 50.")
            return

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
                print("[Error] No options contracts found in option chain response.")
                return

            strikes = []
            contract_by_strike = {}
            for contract in contracts:
                strike = float(contract.get("strike_price") or contract.get("strikePrice") or 0.0)
                if strike > 0:
                    strikes.append(strike)
                    contract_by_strike[strike] = contract

            if not strikes:
                print("[Error] Could not find any valid strike prices.")
                return

            atm_strike = get_atm_strike(spot_price, strikes)
            atm_contract = contract_by_strike[atm_strike]
            ce_data = atm_contract.get("ce") or atm_contract.get("CE") or {}
            pe_data = atm_contract.get("pe") or atm_contract.get("PE") or {}

        days = calculate_days_to_expiry(expiry_date)
        T = days / 365.0
        r = 0.07  # Standard 7% risk-free rate for India

        print("\n" + "=" * 65)
        print(f" NIFTY 55 VALUATION AT ATM STRIKE {atm_strike}")
        print("=" * 65)
        print(f"NIFTY 50 Spot Price : {spot_price:.2f}")
        print(f"Expiry Date         : {expiry_date} ({days:.1f} days remaining)")
        print(f"ATM Strike          : {atm_strike:.2f}")
        print(f"Risk-free Rate (r)  : {r * 100.0:.2f}%")
        print("-" * 65)

        # Extract CE data
        ce_ltp, ce_iv, call_theo, call_diff = 0.0, 0.0, 0.0, 0.0
        api_ce_greeks = {}
        bs_call = None
        if ce_data:
            ce_ltp = float(ce_data.get("ltp") or ce_data.get("lastPrice") or 0.0)
            ce_iv = float(ce_data.get("iv") or ce_data.get("impliedVolatility") or 0.0)
            api_ce_greeks = ce_data.get("greeks") or {}
            calc_ce_iv = ce_iv if ce_iv > 0 else 12.0
            bs_call = BlackScholes(spot_price, atm_strike, T, r, calc_ce_iv / 100.0)
            call_theo = bs_call.call_price()
            call_diff = ce_ltp - call_theo

        # Extract PE data
        pe_ltp, pe_iv, put_theo, put_diff = 0.0, 0.0, 0.0, 0.0
        api_pe_greeks = {}
        bs_put = None
        if pe_data:
            pe_ltp = float(pe_data.get("ltp") or pe_data.get("lastPrice") or 0.0)
            pe_iv = float(pe_data.get("iv") or pe_data.get("impliedVolatility") or 0.0)
            api_pe_greeks = pe_data.get("greeks") or {}
            calc_pe_iv = pe_iv if pe_iv > 0 else 12.0
            bs_put = BlackScholes(spot_price, atm_strike, T, r, calc_pe_iv / 100.0)
            put_theo = bs_put.put_price()
            put_diff = pe_ltp - put_theo

        # Check command-line flag --full or -f
        show_full_data = "--full" in sys.argv or "-f" in sys.argv

        if show_full_data:
            print("\n" + "=" * 65)
            print(f" NIFTY 50 VALUATION AT ATM STRIKE {atm_strike}")
            print("=" * 65)
            print(f"NIFTY 50 Spot Price : {spot_price:.2f}")
            print(f"Expiry Date         : {expiry_date} ({days:.1f} days remaining)")
            print(f"ATM Strike          : {atm_strike:.2f}")
            print(f"Risk-free Rate (r)  : {r * 100.0:.2f}%")
            print("-" * 65)

            if ce_data and bs_call:
                print(f"ATM CALL (CE) OPTION:")
                print(f"  Market Price (LTP)  : {ce_ltp:.2f}")
                print(f"  Implied Volatility  : {ce_iv:.2f}%")
                print(f"  Theoretical (BSM)   : {call_theo:.2f} (Diff: {call_diff:+.2f})")
                print("  Greeks Comparison   | Groww API       | Calculated BSM")
                print("-" * 65)
                print(f"  Delta               | {api_ce_greeks.get('delta', 'N/A'):<15} | {bs_call.call_delta():.4f}")
                print(f"  Gamma               | {api_ce_greeks.get('gamma', 'N/A'):<15} | {bs_call.gamma():.4f}")
                print(f"  Vega (1% vol)       | {api_ce_greeks.get('vega', 'N/A'):<15} | {bs_call.vega():.4f}")
                print(f"  Theta (daily)       | {api_ce_greeks.get('theta', 'N/A'):<15} | {bs_call.call_theta():.4f}")
                print(f"  Rho (1% rate)       | {api_ce_greeks.get('rho', 'N/A'):<15} | {bs_call.call_rho():.4f}")
            else:
                print("ATM CALL option data not found.")

            print("-" * 65)

            if pe_data and bs_put:
                print(f"ATM PUT (PE) OPTION:")
                print(f"  Market Price (LTP)  : {pe_ltp:.2f}")
                print(f"  Implied Volatility  : {pe_iv:.2f}%")
                print(f"  Theoretical (BSM)   : {put_theo:.2f} (Diff: {put_diff:+.2f})")
                print("  Greeks Comparison   | Groww API       | Calculated BSM")
                print("-" * 65)
                print(f"  Delta               | {api_pe_greeks.get('delta', 'N/A'):<15} | {bs_put.put_delta():.4f}")
                print(f"  Gamma               | {api_pe_greeks.get('gamma', 'N/A'):<15} | {bs_put.gamma():.4f}")
                print(f"  Vega (1% vol)       | {api_pe_greeks.get('vega', 'N/A'):<15} | {bs_put.vega():.4f}")
                print(f"  Theta (daily)       | {api_pe_greeks.get('theta', 'N/A'):<15} | {bs_put.put_theta():.4f}")
                print(f"  Rho (1% rate)       | {api_pe_greeks.get('rho', 'N/A'):<15} | {bs_put.put_rho():.4f}")
            else:
                print("ATM PUT option data not found.")

            print("=" * 65)
        else:
            # One-row print layout
            ce_str = f"CE LTP: {ce_ltp:.2f} (BSM: {call_theo:.2f}, Diff: {call_diff:+.2f})" if ce_data else "CE: N/A"
            pe_str = f"PE LTP: {pe_ltp:.2f} (BSM: {put_theo:.2f}, Diff: {put_diff:+.2f})" if pe_data else "PE: N/A"
            print(f"NIFTY: {spot_price:.2f} | ATM Strike: {atm_strike:.0f} | Expiry: {expiry_date} ({days:.1f} days) | {ce_str} | {pe_str}")

    except Exception as e:
        print(f"\n[Error] An error occurred while fetching or parsing Groww data: {e}")

if __name__ == "__main__":
    main()
