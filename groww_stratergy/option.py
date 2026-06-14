import math

def normal_cdf(x):
    """Cumulative distribution function for standard normal distribution."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def normal_pdf(x):
    """Probability density function for standard normal distribution."""
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def calculate_implied_volatility(market_price, S, K, T, r, option_type="call", max_iter=100, tolerance=1e-4):
    """
    Calculate the implied volatility of an option using the Bisection method.
    Returns the IV as a percentage (e.g. 12.5% as 12.5).
    """
    if market_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return 12.0  # default fallback
        
    low = 1e-5
    high = 5.0
    option_type = option_type.lower()
    is_call = option_type in ("call", "ce", "c")
    
    def get_price(sig):
        bs = BlackScholes(S, K, T, r, sig)
        return bs.call_price() if is_call else bs.put_price()
        
    price_low = get_price(low)
    price_high = get_price(high)
    
    # If market price is out of bounds, return the boundaries
    if market_price <= price_low:
        return low * 100.0
    if market_price >= price_high:
        return high * 100.0
        
    for _ in range(max_iter):
        mid = (low + high) / 2.0
        price_mid = get_price(mid)
        
        if abs(price_mid - market_price) < tolerance:
            return mid * 100.0
            
        if price_mid < market_price:
            low = mid
        else:
            high = mid
            
    return mid * 100.0

class BlackScholes:
    """
    Black-Scholes-Merton Model Calculator for European options.
    
    Attributes:
        S (float): Current price of the underlying asset
        K (float): Strike price of the option
        T (float): Time to expiration in years (e.g. 30 days = 30/365)
        r (float): Risk-free interest rate (annualized, e.g. 0.05 for 5%)
        sigma (float): Volatility of the underlying asset (annualized, e.g. 0.20 for 20%)
    """
    def __init__(self, S, K, T, r, sigma):
        self.S = float(S)
        self.K = float(K)
        # Prevent division by zero if T is exactly 0
        self.T = max(float(T), 1e-5)
        self.r = float(r)
        self.sigma = max(float(sigma), 1e-5)
        
        # Calculate d1 and d2
        self.d1 = (math.log(self.S / self.K) + (self.r + 0.5 * self.sigma**2) * self.T) / (self.sigma * math.sqrt(self.T))
        self.d2 = self.d1 - self.sigma * math.sqrt(self.T)

    def call_price(self):
        """Calculate call option price."""
        return self.S * normal_cdf(self.d1) - self.K * math.exp(-self.r * self.T) * normal_cdf(self.d2)

    def put_price(self):
        """Calculate put option price."""
        return self.K * math.exp(-self.r * self.T) * normal_cdf(-self.d2) - self.S * normal_cdf(-self.d1)

    def call_delta(self):
        """Calculate call option Delta."""
        return normal_cdf(self.d1)

    def put_delta(self):
        """Calculate put option Delta."""
        return normal_cdf(self.d1) - 1.0

    def gamma(self):
        """Calculate Gamma (same for Call and Put)."""
        return normal_pdf(self.d1) / (self.S * self.sigma * math.sqrt(self.T))

    def vega(self):
        """Calculate Vega (same for Call and Put) per 1% change in volatility."""
        # Standard Vega is dV/d(sigma). To get vega per 1% change, we divide by 100.
        return (self.S * normal_pdf(self.d1) * math.sqrt(self.T)) / 100.0

    def call_theta(self, days_per_year=365.0):
        """Calculate Call Theta (daily decay)."""
        term1 = -(self.S * normal_pdf(self.d1) * self.sigma) / (2.0 * math.sqrt(self.T))
        term2 = -self.r * self.K * math.exp(-self.r * self.T) * normal_cdf(self.d2)
        annual_theta = term1 + term2
        return annual_theta / days_per_year

    def put_theta(self, days_per_year=365.0):
        """Calculate Put Theta (daily decay)."""
        term1 = -(self.S * normal_pdf(self.d1) * self.sigma) / (2.0 * math.sqrt(self.T))
        term2 = self.r * self.K * math.exp(-self.r * self.T) * normal_cdf(-self.d2)
        annual_theta = term1 + term2
        return annual_theta / days_per_year

    def call_rho(self):
        """Calculate Call Rho per 1% change in interest rate."""
        # Annual Rho is dV/dr. To get Rho per 1% change, divide by 100.
        return (self.K * self.T * math.exp(-self.r * self.T) * normal_cdf(self.d2)) / 100.0

    def put_rho(self):
        """Calculate Put Rho per 1% change in interest rate."""
        return (-self.K * self.T * math.exp(-self.r * self.T) * normal_cdf(-self.d2)) / 100.0


def print_results(bs):
    """Print option pricing and Greeks in a clean, readable format."""
    print("=" * 50)
    print(" BLACK-SCHOLES OPTION CALCULATOR RESULTS")
    print("=" * 50)
    print(f"Underlying Price (S) : ${bs.S:.2f}")
    print(f"Strike Price (K)     : ${bs.K:.2f}")
    print(f"Days to Expiry       : {bs.T * 365.0:.1f} days ({bs.T:.4f} years)")
    print(f"Risk-free Rate (r)   : {bs.r * 100.0:.2f}%")
    print(f"Volatility (sigma)   : {bs.sigma * 100.0:.2f}%")
    print("-" * 50)
    print(f"d1 parameter         : {bs.d1:.4f}")
    print(f"d2 parameter         : {bs.d2:.4f}")
    print("-" * 50)
    
    c_price = bs.call_price()
    p_price = bs.put_price()
    
    print(f"{'Metric':<20} | {'Call Option':<14} | {'Put Option':<14}")
    print("-" * 50)
    print(f"{'Premium (Price)':<20} | ${c_price:<13.4f} | ${p_price:<13.4f}")
    print(f"{'Delta':<20} | {bs.call_delta():<14.4f} | {bs.put_delta():<14.4f}")
    print(f"{'Gamma':<20} | {bs.gamma():<14.4f} | {bs.gamma():<14.4f}")
    print(f"{'Vega (per 1% vol)':<20} | {bs.vega():<14.4f} | {bs.vega():<14.4f}")
    print(f"{'Theta (daily decay)':<20} | {bs.call_theta():<14.4f} | {bs.put_theta():<14.4f}")
    print(f"{'Rho (per 1% rate)':<20} | {bs.call_rho():<14.4f} | {bs.put_rho():<14.4f}")
    print("=" * 50)


def main():
    print("Welcome to the Black-Scholes-Merton Option Calculator!")
    print("Please enter the parameters below:")
    
    try:
        S = float(input("Underlying Asset Price (S): "))
        K = float(input("Strike Price (K): "))
        days = float(input("Days to Expiration (T days): "))
        r_percent = float(input("Risk-free Interest Rate % (r, e.g. 5 for 5%): "))
        sigma_percent = float(input("Implied Volatility % (sigma, e.g. 25 for 25%): "))
        
        # Convert values to decimal and years
        T = days / 365.0
        r = r_percent / 100.0
        sigma = sigma_percent / 100.0
        
        bs = BlackScholes(S, K, T, r, sigma)
        print_results(bs)
        
    except ValueError:
        print("\n[Error] Invalid numeric input. Please enter numbers only.")
    except ZeroDivisionError:
        print("\n[Error] Volatility or time cannot be zero.")

if __name__ == "__main__":
    main()
