
import pandas_ta as ta

def add_indicators(data):
    """Adds technical indicators to the data."""
    data['5MIN_RSI'] = ta.rsi(data.Close, length=14).round(2)
    data['5MIN_EMA21'] = ta.ema(data.Close, length=21).round(2)
    data['5MIN_EMA9'] = ta.ema(data.Close, length=9).round(2)
    data['5MIN_EMA50'] = ta.ema(data.Close, length=50).round(2)

    data["ATR"] = data.ta.atr(length=14).round(2)
    data["ADX"] = data.ta.adx(length=14)["ADX_14"].round(2)
    dmi = data.ta.adx(length=14)
    data["+DI"] = dmi["DMP_14"].round(2)
    data["-DI"] = dmi["DMN_14"].round(2)

    data["Pivot"] = (data["High"] + data["Low"] + data["Close"]) / 3
    data["R1"] = (2 * data["Pivot"]) - data["Low"]
    data["R2"] = data["Pivot"] + (data["High"] - data["Low"])
    data["S1"] = (2 * data["Pivot"]) - data["High"]
    data["S2"] = data["Pivot"] - (data["High"] - data["Low"])

    data[["Pivot", "S1", "S2", "R1", "R2"]] = data[["Pivot", "S1", "S2", "R1", "R2"]].round(2)
    
    return data
