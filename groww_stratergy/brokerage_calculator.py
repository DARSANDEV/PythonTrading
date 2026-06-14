import os
import sys
import argparse
import pandas as pd

# Fix Windows terminal encoding crashes
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Configurations
DEFAULT_REPORT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "backtest_trades_report.csv")

def calculate_net_profit(csv_file, premium_entry, delta, lot_size, lots):
    """
    Load the backtest report and calculate option premiums, turnover, brokerage,
    and statutory taxes per trade. Supports direct option pricing from report or index delta fallback.
    """
    if not os.path.exists(csv_file):
        print(f"[Error] Backtest report file not found at: {csv_file}")
        return
        
    df = pd.read_csv(csv_file)
    if len(df) == 0:
        print("[Warning] Backtest report is empty.")
        return

    qty = lots * lot_size
    
    # Check if backtest report contains option-level pricing directly
    has_direct_option_prices = "index_entry_price" in df.columns
    
    # Track totals
    total_trades = len(df)
    total_gross_pnl_val = 0.0
    total_brokerage = 0.0
    total_stt = 0.0
    total_exchange_fees = 0.0
    total_gst = 0.0
    total_sebi = 0.0
    total_stamp_duty = 0.0
    total_charges = 0.0
    total_net_pnl_val = 0.0
    
    detailed_rows = []
    
    # Calculate average option entry price if direct prices exist
    total_entry_premium_sum = 0.0
    
    for idx, row in df.iterrows():
        # Option Premium calculations
        if has_direct_option_prices:
            buy_premium = float(row["entry_price"])
            sell_premium = float(row["exit_price"])
        else:
            index_pnl = float(row["pnl"])
            buy_premium = premium_entry
            sell_premium = max(1e-2, buy_premium + (index_pnl * delta))
        
        total_entry_premium_sum += buy_premium
        
        buy_value = buy_premium * qty
        sell_value = sell_premium * qty
        premium_turnover = buy_value + sell_value
        
        # 1. Groww Brokerage: Flat Rs. 20 per executed order (Rs. 20 Buy + Rs. 20 Sell)
        brokerage = 40.0
        
        # 2. STT (Securities Transaction Tax): 0.05% on Sell Premium value
        stt = 0.0005 * sell_value
        
        # 3. Exchange Transaction Charges (NSE Options rate): 0.03503% of premium turnover
        exchange_fee = 0.0003503 * premium_turnover
        
        # 4. SEBI Turnover Fee: 0.0001% of premium turnover
        sebi_fee = 0.000001 * premium_turnover
        
        # 5. Stamp Duty: 0.003% of Buy premium value (buy side only)
        stamp_duty = 0.00003 * buy_value
        
        # 6. GST: 18% of (Brokerage + Exchange Fees + SEBI Fees)
        gst = 0.18 * (brokerage + exchange_fee + sebi_fee)
        
        trade_charges = brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst
        gross_trade_pnl = sell_value - buy_value
        net_trade_pnl = gross_trade_pnl - trade_charges
        
        # Accumulate
        total_gross_pnl_val += gross_trade_pnl
        total_brokerage += brokerage
        total_stt += stt
        total_exchange_fees += exchange_fee
        total_sebi += sebi_fee
        total_stamp_duty += stamp_duty
        total_gst += gst
        total_charges += trade_charges
        total_net_pnl_val += net_trade_pnl
        
        detailed_rows.append({
            "entry_time": row.get("entry_time"),
            "exit_time": row.get("exit_time"),
            "index_entry_price": row.get("index_entry_price", row.get("entry_price") if not has_direct_option_prices else "-"),
            "index_exit_price": row.get("index_exit_price", row.get("exit_price") if not has_direct_option_prices else "-"),
            "option_type": row.get("option_type", "CE") if has_direct_option_prices else "CE",
            "buy_premium": buy_premium,
            "sell_premium": sell_premium,
            "gross_pnl": gross_trade_pnl,
            "brokerage": brokerage,
            "stt": stt,
            "exchange_fees": exchange_fee,
            "gst": gst,
            "stamp_duty": stamp_duty,
            "total_charges": trade_charges,
            "net_pnl": net_trade_pnl
        })
        
    avg_premium = (total_entry_premium_sum / total_trades) if total_trades > 0 else premium_entry
        
    # Print performance report
    print("\n" + "=" * 55)
    print("        GROWW POST-TRADE BROKERAGE & TAX REPORT")
    print("=" * 55)
    print(f"Total Completed Trades  : {total_trades}")
    print(f"Option Lots Traded      : {lots} ({lot_size} qty per lot)")
    if has_direct_option_prices:
        print(f"Average Option Premium  : {avg_premium:.2f} points (Initial size: {format_currency(avg_premium * qty)})")
        print(f"Pricing Method          : Direct ATM Options (Black-Scholes model)")
    else:
        print(f"Average Option Premium  : {premium_entry:.2f} points (Initial size: {format_currency(premium_entry * qty)})")
        print(f"Assumed Option Delta    : {delta:.2f}")
        print(f"Pricing Method          : Index Delta Estimation Fallback")
    print("-" * 55)
    print(f"Total Gross Return      : {format_currency(total_gross_pnl_val)}")
    print("-" * 55)
    print(f"Brokerage Charges       : {format_currency(total_brokerage)}")
    print(f"STT Charges             : {format_currency(total_stt)}")
    print(f"Exchange Transaction Chg: {format_currency(total_exchange_fees)}")
    print(f"GST (18% on Broker/Exch): {format_currency(total_gst)}")
    print(f"SEBI Fees & Stamp Duty  : {format_currency(total_sebi + total_stamp_duty)}")
    print(f"Total Taxes & Charges   : {format_currency(total_charges)}")
    print("-" * 55)
    print(f"NET PROFIT (After Fees) : {format_currency(total_net_pnl_val)}")
    print(f"Net Option Points Won   : {total_net_pnl_val / qty:+.2f} points")
    print(f"Brokerage Drag on PnL   : {(total_charges / (abs(total_gross_pnl_val) if total_gross_pnl_val != 0 else 1)) * 100:.2f}%")
    print("=" * 55)
    
    # Save detailed report
    output_path = csv_file.replace("report.csv", "report_with_brokerage.csv")
    pd.DataFrame(detailed_rows).to_csv(output_path, index=False)
    print(f"[Calculator] Detailed brokerage analysis exported to: {output_path}\n")

def format_currency(val):
    prefix = "-Rs. " if val < 0 else "Rs. "
    return f"{prefix}{abs(val):,.2f}"

def main():
    parser = argparse.ArgumentParser(description="Groww F&O Brokerage & Tax Post-Trade Calculator")
    parser.add_argument("--csv", type=str, default=DEFAULT_REPORT_FILE, help="Path to backtest report CSV")
    parser.add_argument("--premium", type=float, default=100.0, help="Average premium of ATM option at entry (default: 100.0)")
    parser.add_argument("--delta", type=float, default=0.5, help="Estimated option delta (default: 0.5)")
    parser.add_argument("--lot_size", type=int, default=75, help="Size of 1 lot (default: 75 for Nifty 50)")
    parser.add_argument("--lots", type=int, default=1, help="Number of option lots traded (default: 1)")
    
    args = parser.parse_args()
    calculate_net_profit(args.csv, args.premium, args.delta, args.lot_size, args.lots)

if __name__ == "__main__":
    main()
